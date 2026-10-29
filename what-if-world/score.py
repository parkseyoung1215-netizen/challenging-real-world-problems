"""
What-If World - prediction log and scoring.

A question is a prediction made before an event. After the event, the real market
moves are compared with what the simulator said:

1. The outcome that really happened: did its branch get the direction of each market
   right, and how far off was the size?
2. The forecast before anyone knew the outcome: the probability-weighted average of all
   outcome branches. This is the number a trading rule would have to use, so it is
   scored too.

Real moves come from the "markets" block that the daily scheduled update writes into
today.json (latest closing levels). A question saves the levels known when it was asked;
scoring uses the first snapshot taken after the event. Moves can also be typed in by hand.
"""

import glob
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from engine import HERE

HISTORY = os.path.join(HERE, "today_history")
SNAPSHOT_TZ = ZoneInfo("Europe/Berlin")  # the scheduled update writes Berlin time

# simulator item -> (key in today.json "markets", sign)
# sign -1: the market quote moves opposite to the simulator item
# (USD/KRW up = won weaker, but the item is "won vs dollar")
MARKETS = {
    "united_states.stocks": ("sp500", 1, "미국 주식 (S&P 500)"),
    "united_states.currency": ("dxy", 1, "달러 지수"),
    "south_korea.stocks": ("kospi", 1, "한국 주식 (KOSPI)"),
    "south_korea.currency": ("usdkrw", -1, "원화 (원/달러 반대)"),
    "japan.stocks": ("nikkei", 1, "일본 주식 (닛케이)"),
    "european_union.stocks": ("stoxx600", 1, "유럽 주식 (STOXX 600)"),
    "global.gold": ("gold", 1, "금"),
    "global.oil": ("brent", 1, "유가 (브렌트)"),
    "global.fear": ("vix", 1, "공포지수 (VIX)"),
    "global.bitcoin": ("bitcoin", 1, "비트코인"),
}
FLAT = 0.2  # moves smaller than this (in %) count as "flat"


def when(text, default_tz=None):
    """Parse an ISO time. Times without a zone use default_tz (or this computer's zone)."""
    t = datetime.fromisoformat(str(text))
    if t.tzinfo is None:
        t = t.replace(tzinfo=default_tz) if default_tz else t.astimezone()
    return t


def snapshots():
    """All saved today.json copies that carry market levels, oldest first."""
    out = []
    for path in sorted(glob.glob(os.path.join(HISTORY, "*.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                s = json.load(f)
            t = when(s["updated"], SNAPSHOT_TZ)
        except (OSError, ValueError, KeyError):
            continue
        levels = {k: v for k, v in (s.get("markets") or {}).items() if isinstance(v, (int, float))}
        if levels:
            out.append({"time": t, "file": os.path.basename(path), "markets": levels})
    return sorted(out, key=lambda s: s["time"])


def levels_before(t):
    """Market levels known at time t (last snapshot at or before t)."""
    before = [s for s in snapshots() if s["time"] <= t]
    return before[-1] if before else None


def levels_after(t):
    """First snapshot after time t."""
    after = [s for s in snapshots() if s["time"] > t]
    return after[0] if after else None


def actual_moves(start, end):
    """% change per simulator item between two snapshots."""
    moves = {}
    for item, (key, sign, _) in MARKETS.items():
        a, b = start["markets"].get(key), end["markets"].get(key)
        if a and b:
            moves[item] = round(sign * (b / a - 1) * 100, 2)
    return moves


def predicted_moves(history, from_week):
    """Total % change per market item over the question's steps (compounded)."""
    total = {}
    for h in history:
        if h["week"] <= from_week:
            continue
        for c in h.get("changes", []):
            if c["item"] in MARKETS and c.get("unit") == "%":
                v = total.get(c["item"], 0.0)
                total[c["item"]] = (1 + v / 100) * (1 + c["change"] / 100) * 100 - 100
    return {k: round(v, 2) for k, v in total.items()}


def direction(x):
    return 0 if abs(x) < FLAT else (1 if x > 0 else -1)


def compare(pred, actual):
    rows = []
    for item, (_, _, label) in MARKETS.items():
        if item not in actual:
            continue
        p = pred.get(item, 0.0)
        a = actual[item]
        rows.append({"item": item, "label": label, "predicted": round(p, 2), "actual": a,
                     "hit": direction(p) == direction(a), "error": round(abs(p - a), 2)})
    hits = sum(r["hit"] for r in rows)
    return {"rows": rows, "hits": hits, "count": len(rows),
            "mean_error": round(sum(r["error"] for r in rows) / len(rows), 2) if rows else None}


def score(question, histories, happened, actual):
    """histories: {branch name: history list}. happened: outcome name that really happened."""
    from_week = question.get("from_week", 0)
    preds = {o["name"]: predicted_moves(histories.get(o["branch"], []), from_week)
             for o in question["outcomes"]}
    total_p = sum(o["prob"] for o in question["outcomes"]) or 1
    weighted = {}
    for o in question["outcomes"]:
        for item, v in preds[o["name"]].items():
            weighted[item] = weighted.get(item, 0.0) + v * o["prob"] / total_p
    return {
        "happened": happened,
        "outcome_score": compare(preds.get(happened, {}), actual),
        "forecast_score": compare(weighted, actual),
        "actual": actual,
    }


def scoreboard(questions):
    """Totals over every scored question."""
    rows = {"outcome_score": [], "forecast_score": []}
    for q in questions:
        r = q.get("result")
        if r:
            for k in rows:
                rows[k] += r[k]["rows"]
    out = {"questions": sum(1 for q in questions if q.get("result"))}
    for k, rs in rows.items():
        out[k] = {"hits": sum(r["hit"] for r in rs), "count": len(rs),
                  "mean_error": round(sum(r["error"] for r in rs) / len(rs), 2) if rs else None}
    return out
