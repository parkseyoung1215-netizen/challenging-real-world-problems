"""
What-If World - start the app.

Run:  python3 app.py
Then open http://localhost:8000 in your browser.
No extra packages needed (standard library only).
"""

import json
import os
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from urllib.parse import parse_qs, urlparse

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from engine import HERE, SAVES, World, list_branches, load_today, suggest_outcomes
import score

PORT = int(os.environ.get("WHATIF_PORT", "8000"))
lock = Lock()  # one change at a time

names = list_branches() or ["main"]
branches = {n: World(n) for n in names}
active = "main" if "main" in branches else names[0]


QUESTIONS = os.path.join(SAVES, "questions.json")


def load_questions():
    if os.path.exists(QUESTIONS):
        with open(QUESTIONS, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_questions(qs):
    os.makedirs(SAVES, exist_ok=True)
    with open(QUESTIONS, "w", encoding="utf-8") as f:
        json.dump(qs, f, ensure_ascii=False, indent=1)


def run_question(question, outcomes, weeks, span="week", start="fresh"):
    """One branch per outcome, all run at once.
    start="fresh": each outcome starts from a clean world dated today.
    start="branch": each outcome forks from the active branch."""
    span = "day" if span == "day" else "week"
    base = branches[active] if start == "branch" else None
    weeks = max(1, min(int(weeks or 1), 5))
    outcomes = [o for o in outcomes if str(o.get("event") or "").strip()][:4]
    if len(outcomes) < 2:
        raise ValueError("결과가 두 개 이상 필요해요")
    probs = {str(o.get("name") or f"결과{i+1}").strip()[:40]: float(o.get("prob") or 0) for i, o in enumerate(outcomes)}
    use_exp = sum(probs.values()) > 0
    source = "AI 추정" if all(o.get("prob_source") == "AI" for o in outcomes) else "author"
    short = question.strip()[:24]
    made = []
    for i, o in enumerate(outcomes):
        oname = list(probs)[i]
        name, k = f"{short} · {oname}", 2
        while name in branches:
            name, k = f"{short} · {oname} ({k})", k + 1
        w = base.fork(name, base.state["week"]) if base else World(name)
        known = None
        if use_exp:
            eid = w.set_expectation(f"q_{len(load_questions()) + 1}", question, probs, source=source)
            known = {"id": eid, "outcome": oname}
        branches[name] = w
        made.append((w, o["event"].strip(), known))

    def run(job):
        w, event, known = job
        w.step(event, known=known, span=span)
        for _ in range(weeks - 1):
            w.step(None, span=span)
        return w.name

    with ThreadPoolExecutor(max_workers=len(made)) as pool:
        names = list(pool.map(run, made))
    now = datetime.now().astimezone()
    known = score.levels_before(now)
    q = {"question": question, "asked": now.isoformat(timespec="minutes"),
         "markets_at_ask": {"file": known["file"], "markets": known["markets"]} if known else None,
         "from_branch": base.name if base else "(새 현재 세계)", "from_week": base.state["week"] if base else 0,
         "weeks": weeks, "span": span,
         "outcomes": [{"name": list(probs)[i], "event": o["event"], "prob": list(probs.values())[i],
                       "prob_source": o.get("prob_source", "author"), "branch": names[i]}
                      for i, o in enumerate(outcomes)]}
    qs = load_questions()
    qs.append(q)
    save_questions(qs)
    return q


def resolve_question(index, happened, actual=None, event_time=None):
    """Score a question after the event. actual: {item: %} typed by hand, else from snapshots."""
    qs = load_questions()
    if not 0 <= index < len(qs):
        raise ValueError("그런 질문이 없어요")
    q = qs[index]
    if happened not in [o["name"] for o in q["outcomes"]]:
        raise ValueError("실제로 일어난 결과를 골라주세요")
    note = "직접 입력"
    if actual:
        actual = {k: float(v) for k, v in actual.items() if k in score.MARKETS and str(v).strip() != ""}
    else:
        start = q.get("markets_at_ask") or score.levels_before(score.when(q["asked"]))
        end = (score.levels_after(score.when(event_time)) if event_time
               else score.levels_before(datetime.now().astimezone()))
        if not start or not end or start["file"] == end["file"]:
            raise ValueError("질문 전후의 시장 기록이 아직 없어요. 다음 자동 업데이트 뒤에 다시 채점하거나 숫자를 직접 넣어주세요")
        actual = score.actual_moves(start, end)
        note = f"{start['file']} → {end['file']}"
    if not actual:
        raise ValueError("비교할 실제 숫자가 없어요")
    histories = {o["branch"]: (branches[o["branch"]].history if o["branch"] in branches else [])
                 for o in q["outcomes"]}
    q["result"] = score.score(q, histories, happened, actual)
    q["result"]["source"] = note
    q["result"]["scored"] = datetime.now().astimezone().isoformat(timespec="minutes")
    save_questions(qs)
    return q


def branch_info():
    return [{"name": n, "week": w.state["week"], "parent": w.parent} for n, w in branches.items()]


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def everything(self):
        w = branches[active]
        qs = load_questions()
        for i, q in enumerate(qs):
            q["index"] = i
        return {"config": w.cfg, "active": active, "branches": branch_info(),
                "state": w.state, "history": w.history, "questions": qs[-20:],
                "scoreboard": score.scoreboard(qs),
                "markets": {k: v[2] for k, v in score.MARKETS.items()},
                "today": load_today()}

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                self.send(200, f.read(), "text/html")
        elif url.path == "/api/world":
            self.send(200, self.everything())
        elif url.path == "/api/branch":
            name = parse_qs(url.query).get("name", [""])[0]
            if name not in branches:
                return self.send(404, {"error": "no such branch"})
            w = branches[name]
            self.send(200, {"name": name, "state": w.state, "history": w.history, "parent": w.parent})
        else:
            self.send(404, {"error": "not found"})

    def do_POST(self):
        global active
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        try:
            with lock:
                w = branches[active]
                if self.path == "/api/question/outcomes":
                    q = str(body.get("question") or "").strip()
                    if not q:
                        return self.send(400, {"error": "질문을 적어주세요"})
                    return self.send(200, {"outcomes": suggest_outcomes(q, w.cfg["context"], int(body.get("n") or 3))})
                elif self.path == "/api/question/run":
                    q = str(body.get("question") or "").strip()
                    if not q:
                        return self.send(400, {"error": "질문을 적어주세요"})
                    result = run_question(q, body.get("outcomes") or [], body.get("weeks"),
                                          body.get("span"), body.get("start") or "fresh")
                    data = self.everything()
                    data["last_question"] = result
                    return self.send(200, data)
                elif self.path == "/api/question/resolve":
                    resolve_question(int(body.get("index", -1)), str(body.get("happened") or ""),
                                     body.get("actual") or None, body.get("event_time") or None)
                elif self.path == "/api/context":
                    w.set_context(body.get("lines") or [])
                    for other in branches.values():
                        other.cfg["context"] = w.cfg["context"]
                elif self.path == "/api/step":
                    w.step(body.get("event"))
                elif self.path == "/api/undo":
                    w.undo()
                elif self.path == "/api/reset":
                    w.reset()
                elif self.path == "/api/expect/set":
                    w.set_expectation(body.get("id"), body.get("topic"), body.get("outcomes"))
                elif self.path == "/api/expect/delete":
                    w.delete_expectation(body.get("id"))
                elif self.path == "/api/branch/new":
                    name = str(body.get("name") or "").strip()[:40]
                    if not name or name in branches:
                        return self.send(400, {"error": "이름이 비어 있거나 이미 있는 갈래예요"})
                    branches[name] = w.fork(name, body.get("from_week", w.state["week"]))
                    active = name
                elif self.path == "/api/branch/switch":
                    if body.get("name") not in branches:
                        return self.send(404, {"error": "no such branch"})
                    active = body["name"]
                elif self.path == "/api/branch/delete":
                    name = body.get("name")
                    if name not in branches or len(branches) == 1:
                        return self.send(400, {"error": "지울 수 없는 갈래예요"})
                    branches.pop(name).delete()
                    if active == name:
                        active = next(iter(branches))
                else:
                    return self.send(404, {"error": "not found"})
            self.send(200, self.everything())
        except ValueError as e:
            self.send(400, {"error": str(e)})
        except Exception as e:
            traceback.print_exc()
            self.send(500, {"error": str(e)})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    url = f"http://localhost:{PORT}"
    print(f"What-If World is running at {url}  (stop with Ctrl+C)")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
