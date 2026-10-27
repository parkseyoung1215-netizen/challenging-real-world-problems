# -*- coding: utf-8 -*-
"""
3차 실험: 검증 장치가 어떤 실수를 고치는가
- 사각지대 문제(패턴을 짐작하고 멈추면 틀리는 문제) vs 계산 실수 문제
- 방법: 그냥 풀기 / 다수결 / 코드로 계산 / 다른 방법으로 재확인 / 추론+코드 대조

실행 전:
  pip3 install openai
  export OPENAI_API_KEY="sk-..."
실행:
  python3 run_experiment3.py
요약만 다시 보기 (API 호출 없음):
  python3 run_experiment3.py --summary

주의: 모델이 쓴 파이썬 코드를 이 맥에서 직접 실행합니다.
      위험한 명령(파일 삭제, 인터넷 접속, 다른 프로그램 실행 등)이 들어 있으면 실행하지 않고 건너뜁니다.
      코드는 임시 폴더에서 60초 제한으로 돌아갑니다.
중간에 멈춰도 같은 명령으로 다시 실행하면 끝난 것은 건너뛰고 이어서 합니다.
"""

import csv
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== 여기만 바꾸면 됩니다 ====================
MODEL = "gpt-5-mini"
REPEATS = 5
WORKERS = 6
# =============================================================

OUTFILE = f"results3_{MODEL}.csv"

# ---------- 문제 (정답은 전부 컴퓨터로 직접 세서 확인함) ----------
# kind: blind = 사각지대형 (패턴을 짐작하고 멈추면 틀림), slip = 계산 실수형
PROBLEMS = [
    ("S1", "blind", "Find the sum of all positive integers n <= 10000 such that n divides 2^n + 1.", 29677),
    ("S2", "blind", "Find the sum of all positive integers n <= 10000 such that n divides 3^n + 1.", 12863),
    ("S3", "blind", "Find the sum of all positive integers n <= 10000 such that n divides 2^n + 2.", 9667),
    ("S4", "blind", "Find the sum of all composite integers n <= 10000 such that n divides 2^n - 2.", 84170),
    ("S5", "blind", "Find the smallest positive integer n such that n, n + 1, and n + 2 each have "
                    "exactly 6 positive divisors.", 242),
    ("S6", "slip", "How many permutations s of {1, 2, ..., 9} satisfy |s(i) - i| != 1 for every i?", 55005),
    ("S7", "slip", "Let f(n) be the number of ordered ways to write n as a sum of parts, each part equal "
                   "to 1, 3, or 5 (order matters). Find f(2026) mod 1000.", 609),
    ("S8", "slip", "How many ordered triples (x, y, z) of integers (positive, negative, or zero) satisfy "
                   "x^2 + y^2 + z^2 = 2025?", 510),
]
P = {pid: (kind, text, ans) for pid, kind, text, ans in PROBLEMS}

ANSWER_FMT = "\n\nEnd your response with a final line of the form: ANSWER: <integer>"

CODE_PROMPT = (
    "\n\nWrite a self-contained Python 3 program (standard library only) that computes the answer "
    "exactly by direct computation. Do not hard-code the answer. The program must print only the "
    "final integer. Put the program in a single ```python code block."
)

RECHECK_PROMPT = (
    "Now check your answer using a completely different method. If the two methods disagree, "
    "find the mistake and fix it." + ANSWER_FMT
)

RECONCILE_TMPL = (
    "{problem}\n\n"
    "Your step-by-step reasoning gave the answer {a}. A Python program written for this problem "
    "printed {b}. Here is the program:\n```python\n{code}\n```\n"
    "These disagree. Work out which one is correct (or whether both are wrong) and give the correct answer."
    + ANSWER_FMT
)

BANNED = ["import os", "from os", "subprocess", "shutil", "socket", "requests", "urllib", "http",
          "open(", "__import__", "eval(", "exec(", "compile(", "pathlib", "sys.modules", "ctypes",
          "multiprocessing", "remove(", "rmdir", "unlink"]


def get_answer(text):
    m = re.findall(r"ANSWER:?\s*[}\*\$\\\(\)\[\]\s]*(?:boxed\{)?\s*(-?\d[\d,]*)", text or "")
    return m[-1].replace(",", "") if m else ""


def extract_code(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text or "", re.S)
    return blocks[-1].strip() if blocks else ""


def run_code(code):
    """모델이 쓴 코드를 안전 검사 후 60초 제한으로 실행. (출력 정수, 상태)"""
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
                               text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return "", "timeout"
    nums = re.findall(r"-?\d+", r.stdout)
    if r.returncode != 0 or not nums:
        return "", "code_error"
    return nums[-1], "ok"


def chat(client, messages):
    last = ""
    for attempt in range(4):
        try:
            r = client.chat.completions.create(model=MODEL, messages=messages)
            text = r.choices[0].message.content or ""
            try:
                rt = r.usage.completion_tokens_details.reasoning_tokens
            except Exception:
                rt = ""
            return text, rt, ""
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
                print(f"\n[중단] 크레딧이 부족합니다.\n{last}")
                os._exit(1)
            print(f"  (재시도 {attempt + 1}/4: {last[:120]})")
            time.sleep(5 * (attempt + 1))
    return "", "", last


def pipeline(client, pid, rep):
    """한 문제 한 번 반복에 대해 네 가지 방법을 차례로 실행"""
    kind, text, ans = P[pid]
    out = []

    def row(method, got, extra="", reply="", code="", rt="", err=""):
        res = "error" if err else ("correct" if got == str(ans) else ("no_answer" if got == "" else "wrong"))
        out.append({"method": method, "pid": pid, "kind": kind, "rep": rep, "answer": ans, "got": got,
                    "result": res, "extra": extra, "reasoning_tokens": rt, "error": err,
                    "code": code, "reply": reply})

    # M1: 그냥 풀기
    q1 = text + ANSWER_FMT
    r1, t1, e1 = chat(client, [{"role": "user", "content": q1}])
    a1 = get_answer(r1)
    row("M1_direct", a1, reply=r1, rt=t1, err=e1)

    # M3: 코드로 계산 (모델이 코드를 쓰고, 이 맥에서 실행)
    r3, t3, e3 = chat(client, [{"role": "user", "content": text + CODE_PROMPT}])
    code = extract_code(r3)
    b, status = run_code(code) if not e3 else ("", "")
    row("M3_code", b, extra=status, reply=r3, code=code, rt=t3, err=e3)

    # M4: 다른 방법으로 재확인 (M1 답변에 이어서)
    if not e1:
        r4, t4, e4 = chat(client, [{"role": "user", "content": q1},
                                   {"role": "assistant", "content": r1},
                                   {"role": "user", "content": RECHECK_PROMPT}])
        row("M4_recheck", get_answer(r4), reply=r4, rt=t4, err=e4)

    # M5: 추론 답과 코드 답을 대조, 다르면 모델에게 판정시키기
    if not e1 and not e3:
        if b and a1 == b:
            row("M5_reconcile", a1, extra="agree")
        elif not b:
            row("M5_reconcile", a1, extra=f"code_{status}")
        else:
            q5 = RECONCILE_TMPL.format(problem=text, a=a1 or "(none)", b=b, code=code)
            r5, t5, e5 = chat(client, [{"role": "user", "content": q5}])
            g5 = get_answer(r5)
            pick = "chose_reasoning" if g5 == a1 else ("chose_code" if g5 == b else "chose_new")
            row("M5_reconcile", g5, extra=pick, reply=r5, rt=t5, err=e5)
    return out


FIELDS = ["method", "pid", "kind", "rep", "answer", "got", "result", "extra",
          "reasoning_tokens", "error", "code", "reply"]
METHODS = ["M1_direct", "M2_majority", "M3_code", "M4_recheck", "M5_reconcile"]


def summarize(rows):
    L = [f"모델: {MODEL}\n"]
    # M2 다수결: M1의 반복 답 중 가장 많이 나온 답 (문제마다 1개)
    maj = {}
    for pid in P:
        gots = [r["got"] for r in rows if r["method"] == "M1_direct" and r["pid"] == pid and r["got"]]
        maj[pid] = Counter(gots).most_common(1)[0][0] if gots else ""

    def rate(method, kind=None, pid=None):
        if method == "M2_majority":
            ps = [p for p in P if (kind is None or P[p][0] == kind) and (pid is None or p == pid)]
            c = sum(maj[p] == str(P[p][2]) for p in ps)
            return c, len(ps)
        rs = [r for r in rows if r["method"] == method and r["result"] != "error"
              and (kind is None or r["kind"] == kind) and (pid is None or r["pid"] == pid)]
        return sum(r["result"] == "correct" for r in rs), len(rs)

    L.append("[방법별 정답률]  (다수결은 문제 단위: 문제마다 5번 답 중 가장 많은 답이 맞았는지)")
    L.append(f"{'방법':<15}{'사각지대형':>14}{'계산실수형':>14}{'전체':>14}")
    for m in METHODS:
        cells = []
        for k in ("blind", "slip", None):
            c, n = rate(m, k)
            cells.append(f"{c}/{n} ({100 * c / n:.0f}%)" if n else "-")
        L.append(f"{m:<15}" + "".join(f"{x:>14}" for x in cells))
    L.append("")
    L.append("[문제별 정답 수]  (M2는 1=다수결 정답, 0=오답)")
    L.append(f"{'문제':<5}{'유형':<7}" + "".join(f"{m.split('_')[0]:>5}" for m in METHODS))
    for pid in P:
        line = f"{pid:<5}{P[pid][0]:<7}"
        for m in METHODS:
            c, n = rate(m, pid=pid)
            line += f"{c:>5}"
        L.append(line)
    L.append("")
    L.append("[코드(M3)가 틀린 경우: 코드가 낸 값과 상태]")
    for pid in P:
        rs = [r for r in rows if r["method"] == "M3_code" and r["pid"] == pid and r["result"] != "correct"]
        if rs:
            c = Counter((r["got"] or r["extra"]) for r in rs)
            L.append(f"  {pid} 정답 {P[pid][2]}: " + ", ".join(f"{k} x{v}" for k, v in c.most_common()))
    L.append("")
    L.append("[추론(M1)이 틀린 경우의 답]")
    for pid in P:
        rs = [r for r in rows if r["method"] == "M1_direct" and r["pid"] == pid and r["result"] != "correct"]
        if rs:
            c = Counter((r["got"] or "(답없음)") for r in rs)
            L.append(f"  {pid} 정답 {P[pid][2]}: " + ", ".join(f"{k} x{v}" for k, v in c.most_common()))
    L.append("")
    L.append("[대조(M5)에서 둘이 달랐을 때 모델이 고른 쪽]")
    c = Counter(r["extra"] for r in rows if r["method"] == "M5_reconcile")
    names = {"agree": "추론=코드 (일치)", "chose_reasoning": "추론 답을 고름", "chose_code": "코드 답을 고름",
             "chose_new": "새 답을 냄"}
    for k, v in c.most_common():
        sub = [r for r in rows if r["method"] == "M5_reconcile" and r["extra"] == k]
        ok = sum(r["result"] == "correct" for r in sub)
        L.append(f"  {names.get(k, k)}: {v}번 (그중 정답 {ok}번)")
    return "\n".join(L)


def load_rows():
    if not os.path.exists(OUTFILE):
        return []
    return list(csv.DictReader(open(OUTFILE, encoding="utf-8-sig")))


def main():
    if "--summary" in sys.argv:
        print(summarize(load_rows()))
        return
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY가 없습니다. 먼저 export OPENAI_API_KEY=\"sk-...\" 를 실행하세요.")
        sys.exit(1)
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"].strip())

    old = load_rows()
    # 네 방법이 모두 오류 없이 끝난 (문제, 반복)만 완료로 봄
    done = set()
    for pid in P:
        for rep in range(1, REPEATS + 1):
            ms = {r["method"] for r in old if r["pid"] == pid and str(r["rep"]) == str(rep) and r["result"] != "error"}
            if {"M1_direct", "M3_code", "M4_recheck", "M5_reconcile"} <= ms:
                done.add((pid, str(rep)))
    keep = [r for r in old if (r["pid"], str(r["rep"])) in done]
    todo = [(pid, rep) for pid in P for rep in range(1, REPEATS + 1) if (pid, str(rep)) not in done]
    print(f"모델 {MODEL}: 전체 {len(P) * REPEATS}세트 중 {len(done)}세트 끝남, {len(todo)}세트 새로 합니다.")
    print("(1세트 = 한 문제에 대해 그냥 풀기, 코드, 재확인, 대조를 차례로 실행)\n")

    rows = list(keep)
    with open(OUTFILE, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(keep)
        f.flush()
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futs = {pool.submit(pipeline, client, pid, rep): (pid, rep) for pid, rep in todo}
            for i, fut in enumerate(as_completed(futs), 1):
                pid, rep = futs[fut]
                out = fut.result()
                rows.extend(out)
                w.writerows(out)
                f.flush()
                brief = " ".join(f"{r['method'].split('_')[0]}={r['result']}" for r in out)
                print(f"[{i}/{len(todo)}] {pid} 반복{rep}: {brief}")

    s = summarize(rows)
    print("\n" + s)
    with open(f"summary3_{MODEL}.txt", "w", encoding="utf-8") as f:
        f.write(s)
    print(f"\n결과 파일: {OUTFILE}, summary3_{MODEL}.txt")


if __name__ == "__main__":
    main()
