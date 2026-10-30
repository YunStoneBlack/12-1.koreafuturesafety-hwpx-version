"""AI 토큰·가격 집계 — python -m server.scripts.ai_usage_report [--since 2026-10-30T21:00] [--until 2026-10-30T23:59] [--by caller|day]
(core/ai_usage.py가 쌓은 DATA_DIR/_ai_usage/*.jsonl). 가격은 입력·출력 토큰만(캐시는 쓰는 곳이 없어 0)."""
from __future__ import annotations

import argparse
import collections
import json
import sys

from core import ai_usage
from core.db import DATA_DIR


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="")
    ap.add_argument("--until", default="9999")
    ap.add_argument("--by", default="caller", choices=["caller", "day"])
    a = ap.parse_args()
    rows = []
    for p in sorted((DATA_DIR / "_ai_usage").glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if a.since <= r["at"] <= a.until:
                rows.append(r)
    if not rows:
        print("기록 없음 — 기록은 이 기능을 넣은 뒤(API 재시작 뒤)의 AI 호출부터 쌓입니다.")
        return
    agg: dict[str, list] = collections.defaultdict(lambda: [0, 0, 0, 0.0])
    for r in rows:
        k = r["at"][:10] if a.by == "day" else (r["caller"].split(" < ")[0] or "?")
        s = agg[k]
        s[0] += 1; s[1] += r["in"]; s[2] += r["out"]; s[3] += ai_usage.price(r["model"], r["in"], r["out"])
    print(f"{'구분':44} {'횟수':>5} {'입력':>10} {'출력':>10} {'달러':>8}")
    for k, s in sorted(agg.items(), key=lambda x: -x[1][3]):
        print(f"{k[:44]:44} {s[0]:5d} {s[1]:10,d} {s[2]:10,d} {s[3]:8.3f}")
    t = [sum(s[i] for s in agg.values()) for i in range(4)]
    print(f"{'합계':44} {t[0]:5d} {t[1]:10,d} {t[2]:10,d} {t[3]:8.3f}  (≈ {t[3] * 1400:,.0f}원, 환율 1400 가정)")


if __name__ == "__main__":
    main()
