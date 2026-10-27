# -*- coding: utf-8 -*-
"""
6차 실험: 실제 답 목록(데이터)을 보여주면 스스로 규칙을 찾아 고칠 수 있는가

4·5차와 같은 문제(범위 10억). 이번엔 문제와 함께 "100만 이하의 답 전체 목록"을 보여준다.
  D1_data        : 목록을 보고 규칙을 찾아 코드 작성 (한 번)
  D2_data_check  : D1 + 확인 후 다시 쓰기 (최대 2번)
     확인 A: 코드의 LIMIT를 10^7로 바꿔 돌리고, 10^7까지 직접 센 답과 비교 (목록 밖 범위라 진짜 시험)
     확인 B: 코드 속 큰 상수를 2배, 10배로 키워 답이 바뀌는지
     10억 범위에서 시간 초과·에러가 나도 실패로 본다 (5차 버그 수정)
비교 기준(데이터 없이): 5차 처음 코드 3/24, 4차 0/32.
정답(10억 범위 답)은 모델에게 알려주지 않는다.

실행:   python3 run_experiment6.py
요약만: python3 run_experiment6.py --summary
"""

import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== 여기만 바꾸면 됩니다 ====================
MODEL = "gpt-5-mini"
REPEATS = 6              # 조건·문제마다 몇 번 반복할지
WORKERS = 4
MAX_FIXES = 2            # D2에서 확인에 걸렸을 때 다시 쓰게 하는 최대 횟수
CONDS = ["D1_data", "D2_data_check"]
TOKEN_CAP = 1_500_000    # 이번 실행에서 쓸 출력 토큰 상한 (넘으면 새 질문 중단)
# =============================================================

OUTFILE = f"results6_{MODEL}.csv"
RUN_TIMEOUT = 90         # 코드 한 번 실행 제한 (초)
SMALL = 10**7
DATA_N = 10**6

# ---------- 문제 (정답: 1부터 10억까지 전부 확인해서 계산함) ----------
PROBLEMS = [
    ("L1", "Find the sum of all positive integers n <= 10^9 such that n divides 2^n + 1.", 33691587268),
    ("L2", "Find the sum of all positive integers n <= 10^9 such that n divides 3^n + 1.", 8013250633),
    ("L3", "Find the sum of all positive integers n <= 10^9 such that n divides 2^n + 2.", 8862521077),
    ("L4", "Find the number of positive integers n <= 10^9 such that n divides 2^n + 1.", 188),
]
P = {pid: (text, ans) for pid, text, ans in PROBLEMS}
PATTERN = {"L1": "581130733", "L2": "610351563", "L4": "19"}  # 패턴만 센 값


DATA = {"L1": [1, 3, 9, 27, 81, 171, 243, 513, 729, 1539, 2187, 3249, 4617, 6561, 9747, 13203, 13851, 19683, 29241, 39609, 41553, 59049, 61731, 87723, 97641, 118827, 124659, 177147, 185193, 250857, 263169, 292923, 354537, 356481, 373977, 531441, 555579, 752571, 789507, 878769], "L2": [1, 2, 10, 50, 250, 1250, 5050, 6250, 11810, 25250, 31250, 59050, 126250, 156250, 295250, 510050, 631250, 750250, 781250], "L3": [1, 2, 6, 66, 946, 8646, 180246, 199606, 265826, 383846], "L4": [1, 3, 9, 27, 81, 171, 243, 513, 729, 1539, 2187, 3249, 4617, 6561, 9747, 13203, 13851, 19683, 29241, 39609, 41553, 59049, 61731, 87723, 97641, 118827, 124659, 177147, 185193, 250857, 263169, 292923, 354537, 356481, 373977, 531441, 555579, 752571, 789507, 878769]}
# 10^7까지 하나씩 다 센 답 (C 프로그램으로 계산, 10^4에서 3차 정답과 일치 확인)
TRUTH_1E7 = {"L1": 122452330, "L2": 33701573, "L3": 15911701, "L4": 68}
# 데이터 범위(100만)까지만 센 값
DATA_ONLY = {"L1": "6498598", "L2": "3390773", "L3": "1039191", "L4": "40"}


def brute_small(pid, N=SMALL):
    """확인 A용: 10^7 정답 (모델과 독립)"""
    return TRUTH_1E7[pid]


def _unused(pid, N):
    if pid == "L1":
        return sum(n for n in range(1, N + 1) if (pow(2, n, n) + 1) % n == 0)
    if pid == "L2":
        return sum(n for n in range(1, N + 1) if (pow(3, n, n) + 1) % n == 0)
    if pid == "L3":
        return sum(n for n in range(1, N + 1) if (pow(2, n, n) + 2) % n == 0)
    if pid == "L4":
        return sum(1 for n in range(1, N + 1) if (pow(2, n, n) + 1) % n == 0)


CODE_PROMPT = (
    "\n\nWrite a self-contained Python 3 program (standard library only) that computes the answer "
    "exactly. Do not hard-code the answer or the list. The program must finish within 60 seconds on a laptop "
    "in plain CPython, so checking every n one by one is too slow; use the mathematical structure "
    "of the problem (the data above may help you find it). Before the code, state in one line the rule "
    "you inferred, starting with `RULE:`. Define the bound as a top-level line exactly of the form `LIMIT = 10**9` and use "
    "LIMIT everywhere instead of writing the number again. The program must print only the final "
    "integer. Put the program in a single ```python code block."
)

FIX_TMPL = (
    "Your program was checked before being trusted, and the check failed:\n{why}\n\n"
    "Find what is wrong in your reasoning or code, and write a corrected program. Same rules as before: "
    "standard library only, finishes within 60 seconds, top-level `LIMIT = 10**9`, prints only the final "
    "integer, one ```python code block."
)

BANNED = ["import os", "from os", "subprocess", "shutil", "socket", "requests", "urllib", "http",
          "open(", "__import__", "eval(", "exec(", "compile(", "pathlib", "sys.modules", "ctypes",
          "multiprocessing", "remove(", "rmdir", "unlink"]

LIMIT_RE = re.compile(r"^(\s*LIMIT\s*=\s*)(.+?)\s*(#.*)?$", re.M)
BIGLIT_RE = re.compile(r"(?<![\w.])(\d+e\d+|10\s*\*\*\s*\d+|\d{4,})(?![\w.])")

_lock = threading.Lock()
_tokens_used = 0


def extract_code(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text or "", re.S)
    return blocks[-1].strip() if blocks else ""


def run_code(code):
    """(출력 정수 문자열, 상태)"""
    if not code:
        return "", "no_code"
    low = code.lower()
    for b in BANNED:
        if b in low:
            return "", f"blocked({b})"
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "prog.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        try:
            r = subprocess.run([sys.executable, "-I", path], cwd=d, capture_output=True,
                               text=True, timeout=RUN_TIMEOUT)
        except subprocess.TimeoutExpired:
            return "", "timeout"
    nums = re.findall(r"-?\d+", r.stdout)
    if r.returncode != 0 or not nums:
        return "", "code_error"
    return nums[-1], "ok"


def with_limit(code, value):
    if not LIMIT_RE.search(code):
        return None
    return LIMIT_RE.sub(lambda m: f"{m.group(1)}{value}", code, count=1)


def scaled(code, factor):
    """LIMIT 줄을 뺀 큰 숫자 상수를 전부 factor배로. (바뀐 코드, 바꾼 상수 목록)"""
    out, changed = [], []
    for line in code.split("\n"):
        if LIMIT_RE.match(line) or line.lstrip().startswith("#"):
            out.append(line)
            continue
        def rep(m):
            tok = m.group(1)
            compact = tok.replace(" ", "")
            if compact in ("10**9", "1000000000", "1e9", "10**9+7", "1000000007"):
                return tok
            changed.append(compact)
            return f"({factor}*{tok})" if ("**" in tok or "e" in tok) else str(factor * int(tok))
        code_part, sep, comment = line.partition("#")
        out.append(BIGLIT_RE.sub(rep, code_part) + sep + comment)
    return "\n".join(out), changed


def check(pid, code):
    """확인 A, B. (통과 여부, 실패 이유 문장, 기록용 dict)"""
    info = {}
    small_code = with_limit(code, SMALL)
    if small_code is None:
        info["A"] = "no_limit_line"
        return False, "The program does not define a top-level `LIMIT = 10**9` line, so it could not be checked.", info
    got_small, st = run_code(small_code)
    truth_small = brute_small(pid)
    info["A"] = f"{got_small or st} vs {truth_small}"
    if st != "ok" or got_small != str(truth_small):
        why = (f"With LIMIT = {SMALL}, your program printed {got_small or '(' + st + ')'}, "
               f"but checking every n from 1 to {SMALL} directly gives {truth_small}.")
        return False, why, info
    _, consts = scaled(code, 2)
    if not consts:
        info["B"] = "no_constants"
        return True, "", info
    base, st1 = run_code(code)
    notes = []
    for factor in (2, 10):
        scode, _ = scaled(code, factor)
        big, st2 = run_code(scode)
        notes.append(f"x{factor}: {base or st1} -> {big or st2}")
        if st1 == "ok" and st2 == "ok" and base != big:
            info["B"] = f"{','.join(consts)} " + "; ".join(notes)
            why = (f"Multiplying the numeric constants {', '.join(consts)} in your program (all other than LIMIT) "
                   f"by {factor} changed the printed answer from {base} to {big}. So at least one of those bounds is "
                   f"not actually sufficient, and the answer depends on an unchecked cutoff.")
            return False, why, info
    info["B"] = f"{','.join(consts)} " + "; ".join(notes)
    return True, "", info


def chat(client, messages):
    global _tokens_used
    last = ""
    for attempt in range(4):
        try:
            r = client.chat.completions.create(model=MODEL, messages=messages)
            text = r.choices[0].message.content or ""
            ct = getattr(r.usage, "completion_tokens", 0) or 0
            with _lock:
                _tokens_used += ct
            return text, ct, ""
        except Exception as e:
            last = str(e)
            low = last.lower()
            if "model" in low and ("not found" in low or "does not exist" in low):
                print(f"\n[중단] 모델 이름 '{MODEL}'을 쓸 수 없습니다.\n{last}")
                os._exit(1)
            if "api key" in low or "401" in low:
                print(f"\n[중단] API 키 문제입니다.\n{last}")
                os._exit(1)
            if "insufficient_quota" in low:
                print(f"\n[중단] 크레딧이 부족합니다. 같은 명령으로 나중에 이어서 할 수 있습니다.\n{last}")
                os._exit(1)
            print(f"  (재시도 {attempt + 1}/4: {last[:120]})")
            time.sleep(5 * (attempt + 1))
    return "", 0, last


def data_text(pid):
    lst = ", ".join(map(str, DATA[pid]))
    what = {"L1": "n divides 2^n + 1", "L2": "n divides 3^n + 1", "L3": "n divides 2^n + 2", "L4": "n divides 2^n + 1"}[pid]
    return (f"\n\nData: here is the complete list of all positive integers n <= 10^6 such that {what} "
            f"({len(DATA[pid])} numbers, computed by checking every n): {lst}.")


def pipeline(client, pid, rep, cond):
    text, ans = P[pid]
    max_fix = MAX_FIXES if cond == "D2_data_check" else 0
    msgs = [{"role": "user", "content": text + data_text(pid) + CODE_PROMPT}]
    rounds = []
    for k in range(max_fix + 1):
        with _lock:
            over = _tokens_used >= TOKEN_CAP
        if over:
            return None
        reply, ct, err = chat(client, msgs)
        if err:
            return {"pid": pid, "rep": rep, "cond": cond, "error": err}
        code = extract_code(reply)
        m = re.findall(r"RULE:\s*(.+)", reply)
        rule = m[0].strip()[:300] if m else ""
        full, st = run_code(code)
        if not code:
            ok, why, info = False, "No ```python code block was found.", {"A": "no_code"}
        elif st != "ok":
            ok, why, info = False, f"With LIMIT = 10**9 the program did not finish correctly ({st}; the limit is 60 seconds).", {"A": "", "B": "", "full": st}
        else:
            ok, why, info = check(pid, code)
        rounds.append({"round": k, "full": full or st, "correct": full == str(ans), "passed": ok,
                       "A": info.get("A", ""), "B": info.get("B", ""), "why": why, "tokens": ct, "rule": rule, "code": code})
        if ok or k == max_fix:
            break
        msgs += [{"role": "assistant", "content": reply}, {"role": "user", "content": FIX_TMPL.format(why=why)}]
    return {"pid": pid, "rep": rep, "cond": cond, "error": "", "rounds": rounds}


FIELDS = ["cond", "pid", "rep", "answer", "first_got", "first_correct", "final_got", "final_correct",
          "n_rounds", "final_passed", "rounds_json", "error"]


def to_row(res):
    if res.get("error"):
        return {"cond": res["cond"], "pid": res["pid"], "rep": res["rep"], "answer": P[res["pid"]][1], "error": res["error"]}
    rs = res["rounds"]
    return {"cond": res["cond"], "pid": res["pid"], "rep": res["rep"], "answer": P[res["pid"]][1],
            "first_got": rs[0]["full"], "first_correct": rs[0]["correct"],
            "final_got": rs[-1]["full"], "final_correct": rs[-1]["correct"],
            "n_rounds": len(rs), "final_passed": rs[-1]["passed"],
            "rounds_json": json.dumps(rs, ensure_ascii=False), "error": ""}


def tag(pid, v):
    if PATTERN.get(pid) == str(v):
        return f"{v} (패턴만 셈)"
    if DATA_ONLY.get(pid) == str(v):
        return f"{v} (100만까지만 셈)"
    return str(v)


def summarize_one(rows, title):
    T = lambda v: str(v) == "True"
    L = [f"===== {title} ====="]
    n = len(rows)
    if not n:
        return "\n".join(L + ["  (아직 결과 없음)"])
    L.append(f"  처음 코드 정답: {sum(T(r['first_correct']) for r in rows)}/{n}")
    L.append(f"  최종 정답:      {sum(T(r['final_correct']) for r in rows)}/{n}")
    for pid in P:
        rs = [r for r in rows if r["pid"] == pid]
        if rs:
            L.append(f"    {pid}: {sum(T(r['first_correct']) for r in rs)}/{len(rs)} → {sum(T(r['final_correct']) for r in rs)}/{len(rs)}")
    c = Counter((r["pid"], tag(r["pid"], r["final_got"])) for r in rows if not T(r["final_correct"]))
    if c:
        L.append("  최종 오답: " + ", ".join(f"{p} {v} x{k}" for (p, v), k in c.most_common()))
    return "\n".join(L)


def summarize(rows):
    rows = [r for r in rows if not r.get("error")]
    L = [f"모델: {MODEL} / 데이터: 100만 이하 답 전체 목록 / 확인 A는 10^7에서\n",
         "비교 기준 (데이터 없음): 4차 처음 코드 0/32, 5차 처음 코드 3/24, 5차 확인+다시 쓰기 후 3/24\n"]
    for cond in CONDS:
        L.append(summarize_one([r for r in rows if r["cond"] == cond], cond))
        L.append("")
    # 확인 장치 성능 (D2만)
    caught = missed = false_alarm = good = 0
    for r in rows:
        if r["cond"] != "D2_data_check":
            continue
        for rd in json.loads(r["rounds_json"]):
            if not rd["correct"] and not rd["passed"]:
                caught += 1
            elif not rd["correct"] and rd["passed"]:
                missed += 1
            elif rd["correct"] and not rd["passed"]:
                false_alarm += 1
            else:
                good += 1
    L.append(f"[D2 확인 장치] 틀린 코드 잡음 {caught} / 놓침 {missed} / 맞는 코드 오경보 {false_alarm} / 맞는 코드 통과 {good}")
    return "\n".join(L)


def write_rules(rows):
    T = lambda v: str(v) == "True"
    with open(f"rules6_{MODEL}.txt", "w", encoding="utf-8") as f:
        for r in sorted(rows, key=lambda r: (r["pid"], r["cond"])):
            if r.get("error"):
                continue
            for rd in json.loads(r["rounds_json"]):
                f.write(f"[{r['pid']} {r['cond']} 반복{r['rep']} 라운드{rd['round']}] {'정답' if rd['correct'] else '오답 ' + tag(r['pid'], rd['full'])}\n  RULE: {rd.get('rule', '')}\n")


def load_rows():
    if not os.path.exists(OUTFILE):
        return []
    return list(csv.DictReader(open(OUTFILE, encoding="utf-8-sig")))


def main():
    if "--summary" in sys.argv:
        rows = load_rows()
        write_rules(rows)
        print(summarize(rows))
        return
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY가 없습니다. 먼저 export OPENAI_API_KEY=\"sk-...\" 를 실행하세요.")
        sys.exit(1)
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"].strip())

    old = [r for r in load_rows() if not r.get("error")]
    done = {(r["cond"], r["pid"], str(r["rep"])) for r in old}
    todo = [(cond, pid, rep) for rep in range(1, REPEATS + 1) for cond in CONDS for pid in P
            if (cond, pid, str(rep)) not in done]
    print(f"모델 {MODEL}: 전체 {len(CONDS) * len(P) * REPEATS}세트 중 {len(done)}세트 끝남, {len(todo)}세트 새로 합니다.")
    print(f"(토큰 상한 {TOKEN_CAP:,}. 넘으면 새 질문을 멈춥니다)\n")

    rows = list(old)
    stopped = 0
    with open(OUTFILE, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(old)
        f.flush()
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futs = {pool.submit(pipeline, client, pid, rep, cond): (cond, pid, rep) for cond, pid, rep in todo}
            for i, fut in enumerate(as_completed(futs), 1):
                cond, pid, rep = futs[fut]
                res = fut.result()
                if res is None:
                    stopped += 1
                    continue
                row = to_row(res)
                rows.append(row)
                w.writerow(row)
                f.flush()
                if res.get("error"):
                    print(f"[{i}/{len(todo)}] {cond} {pid} 반복{rep}: 오류 {res['error'][:80]}")
                else:
                    trail = " → ".join(("O" if rd["correct"] else "X") + ("" if rd["passed"] else "!") for rd in res["rounds"])
                    print(f"[{i}/{len(todo)}] {cond:<14} {pid} 반복{rep}: {trail}   (사용 토큰 누계 {_tokens_used:,})")
    if stopped:
        print(f"\n[토큰 상한 도달] {stopped}세트는 시작하지 않았습니다. 같은 명령으로 나중에 이어서 하세요.")
    write_rules(rows)
    s = summarize(rows)
    print("\n" + s)
    print("\n표시 읽는 법: O=정답 X=오답, !=확인에 걸려서 다시 쓰게 함. 예) X! → O : 처음 틀린 코드가 확인에 걸렸고, 고친 코드가 맞음")
    with open(f"summary6_{MODEL}.txt", "w", encoding="utf-8") as f:
        f.write(s)
    print(f"\n결과 파일: {OUTFILE}, summary6_{MODEL}.txt, rules6_{MODEL}.txt (모델이 찾은 규칙)")


if __name__ == "__main__":
    main()
