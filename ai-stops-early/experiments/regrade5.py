# -*- coding: utf-8 -*-
"""5차 결과 다시 세기: 10억 범위에서 시간 초과·에러가 난 코드를 '확인 통과'가 아니라 '실패'로 센다 (API 호출 없음)"""
import csv
import json
from collections import Counter

rows = [r for r in csv.DictReader(open("results5_gpt-5-mini.csv", encoding="utf-8-sig")) if not r.get("error")]
BAD = ("timeout", "code_error", "no_code")
caught = missed = fa = good = 0
missed_vals = Counter()
for r in rows:
    for rd in json.loads(r["rounds_json"]):
        failed_run = str(rd["full"]).startswith(BAD) or str(rd["full"]).startswith("blocked")
        passed = rd["passed"] and not failed_run
        if not rd["correct"] and not passed:
            caught += 1
        elif not rd["correct"] and passed:
            missed += 1
            missed_vals[(r["pid"], rd["full"])] += 1
        elif rd["correct"] and not passed:
            fa += 1
        else:
            good += 1
print("5차 확인 장치 성능 (시간 초과·에러 = 실패로 다시 셈)")
print(f"  틀린 코드를 잡음: {caught}")
print(f"  틀린 코드인데 통과: {missed}")
print(f"  맞는 코드 오경보: {fa}")
print(f"  맞는 코드 통과: {good}")
print("  통과해 버린 오답: " + ", ".join(f"{p} {v} x{k}" for (p, v), k in missed_vals.most_common()))
