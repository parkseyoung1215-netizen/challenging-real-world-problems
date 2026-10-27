# -*- coding: utf-8 -*-
"""
2차 실험 결과 분석 (API 호출 없음, 돈 안 듦)
실행: python3 analyze2.py
"""
import csv
import random
import sys
from collections import Counter, defaultdict

PATH = sys.argv[1] if len(sys.argv) > 1 else "results2_gpt-5-mini.csv"
rows = [r for r in csv.DictReader(open(PATH, encoding="utf-8-sig"))
        if r["kind"] == "numeric" and r["result"] != "error"]

# ---------- 1. 자주 틀린 문제에서 모델이 낸 답 ----------
print("=" * 60)
print("1. 자주 틀린 문제에서 모델이 낸 답 (답: 횟수)")
print("=" * 60)
by_pid = defaultdict(list)
for r in rows:
    by_pid[r["pid"]].append(r)
for pid, rs in sorted(by_pid.items(), key=lambda kv: int(kv[0][1:])):
    wrong = [r for r in rs if r["result"] != "correct"]
    if len(wrong) < 3:
        continue
    cnt = Counter(r["got"] or "(답없음)" for r in wrong)
    top = ", ".join(f"{a}: {n}번" for a, n in cnt.most_common(5))
    print(f"{pid} 정답 {rs[0]['answer']} | {len(wrong)}/{len(rs)}번 틀림 | 오답: {top}")

# ---------- 2. 생각량 차이가 우연인지 ----------
def tok(r):
    v = r.get("reasoning_tokens", "")
    return int(v) if str(v).isdigit() else None

data = [(r["cond"], r["pid"], tok(r), r["result"] == "correct") for r in rows if tok(r) is not None]
conds = sorted({c for c, _, _, _ in data})

def mean(xs):
    return sum(xs) / len(xs) if xs else 0

def strat_perm_test(cond_x, cond_y="C_neutral", n_iter=5000, seed=0):
    """같은 문제끼리만 섞는 순열 검정: 문제 난이도 차이를 빼고 조건 차이만 봄"""
    rng = random.Random(seed)
    groups = defaultdict(list)
    for c, p, t, _ in data:
        if c in (cond_x, cond_y):
            groups[p].append((c, t))
    def diff(assign):
        xs = [t for g in assign.values() for c, t in g if c == cond_x]
        ys = [t for g in assign.values() for c, t in g if c == cond_y]
        return mean(xs) - mean(ys)
    obs = diff(groups)
    extreme = 0
    for _ in range(n_iter):
        shuffled = {}
        for p, g in groups.items():
            labels = [c for c, _ in g]
            rng.shuffle(labels)
            shuffled[p] = [(labels[i], g[i][1]) for i in range(len(g))]
        if abs(diff(shuffled)) >= abs(obs) - 1e-9:
            extreme += 1
    return obs, (extreme + 1) / (n_iter + 1)

print()
print("=" * 60)
print("2. 생각량 차이 (C_neutral 기준, 같은 문제끼리 비교)")
print("=" * 60)
base = mean([t for c, _, t, _ in data if c == "C_neutral"])
print(f"C_neutral 평균 생각량: {base:.0f}")
for c in conds:
    if c == "C_neutral":
        continue
    d, p = strat_perm_test(c)
    print(f"{c:<18} 차이 {d:+7.0f} ({100 * d / base:+.1f}%)  p = {p:.4f}"
          + ("  <- 우연일 가능성 낮음" if p < 0.05 else ""))
print("(p가 0.05보다 작으면 우연으로 보기 어려운 차이)")

# ---------- 3. 맞힐 때와 틀릴 때 생각량 ----------
print()
print("=" * 60)
print("3. 맞힐 때 vs 틀릴 때 생각량 (같은 문제 안에서)")
print("=" * 60)
for pid in sorted(by_pid, key=lambda x: int(x[1:])):
    ok = [t for c, p, t, k in data if p == pid and k]
    ng = [t for c, p, t, k in data if p == pid and not k]
    if ok and ng:
        print(f"{pid}: 맞힘 {len(ok)}번 평균 {mean(ok):.0f} | 틀림 {len(ng)}번 평균 {mean(ng):.0f}")
