"""목표 시험 — 층마다 부재 5개에 서로 다른 균열·탄산화 조건을 넣고 SafetyMan 부재 점수로 규칙 확인.
부재 점수 = 2×(1이 있는 가장 오른쪽 등급)+1 이라 균열만 넣으면 균열 등급이 그대로 보임(표면노후는 a로 채움 — 점수에 안 닿음).
사용: python t_rule.py <세트 이름>"""
from __future__ import annotations

import json
import os
import tempfile
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
WORK = Path(os.environ.get("SM_WORK") or (Path(tempfile.gettempdir()) / "safetyman_check"))  # 시험 파일·결과(저장소 밖)
WORK.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(HERE))
import t_diff as D  # noqa: E402
import smrun  # noqa: E402


def mem(width, area_ge=0, carb=None, strength=None):
    n = sum(width)
    m = {"n": n, "crack": list(width), "crack_area": [n - area_ge, area_ge]}
    for it in ("scaling", "spalling", "leak", "rebar"):
        m[it] = [n, 0, 0, 0, 0]
    m["scaling_area"] = [n, 0]
    m["spalling_area"] = [n, 0]
    m["strength"] = strength or []
    if carb:
        m["carb"] = carb
    return m


B = lambda: mem([7, 3, 0, 0, 0])  # noqa: E731 — 보·슬래브 기준 b(최소범위 3 → b,b,b)
SETS = {
    # 반올림·균열 면적률 20% 이상(어느 부재·몇 개부터·a에서도 내리나)
    "crack": [
        {"기둥": mem([9, 1, 0, 0, 0]), "내력벽": mem([8, 2, 0, 0, 0], 10), "큰보": mem([7, 3, 0, 0, 0], 10), "작은보": mem([7, 3, 0, 0, 0], 10), "슬래브": mem([10, 0, 0, 0, 0], 10)},
        {"기둥": mem([8, 1, 0, 0, 1]), "내력벽": mem([8, 2, 0, 0, 0]), "큰보": B(), "작은보": B(), "슬래브": mem([7, 3, 0, 0, 0], 1)},
        {"기둥": mem([8, 2, 0, 0, 0], 10), "내력벽": mem([8, 2, 0, 0, 0], 1), "큰보": mem([7, 3, 0, 0, 0], 1), "작은보": mem([7, 3, 0, 0, 0], 3), "슬래브": mem([7, 3, 0, 0, 0], 3)},
        {"기둥": mem([8, 2, 0, 0, 0], 2), "내력벽": mem([8, 2, 0, 0, 0], 2), "큰보": mem([7, 3, 0, 0, 0], 2), "작은보": mem([7, 3, 0, 0, 0], 4), "슬래브": mem([7, 3, 0, 0, 0], 2)},
        {"기둥": mem([10, 0, 0, 0, 0], 10), "내력벽": mem([10, 0, 0, 0, 0], 10), "큰보": mem([10, 0, 0, 0, 0], 10), "작은보": mem([7, 0, 0, 0, 3], 10), "슬래브": mem([7, 3, 0, 0, 0], 6)},
        {"기둥": mem([18, 1, 0, 0, 1]), "내력벽": mem([28, 1, 1, 0, 0]), "큰보": mem([7, 3, 0, 0, 0], 5), "작은보": mem([7, 0, 3, 0, 0], 3), "슬래브": mem([7, 3, 0, 0, 0], 5)},
    ],
    # c·d 등급에서 면적률 20% 이상
    "crack2": [
        {"기둥": mem([8, 0, 2, 0, 0], 10), "내력벽": mem([8, 0, 2, 0, 0], 10), "큰보": mem([7, 0, 3, 0, 0], 10), "작은보": mem([7, 0, 0, 3, 0], 10), "슬래브": mem([7, 0, 3, 0, 0], 10)},
        {"기둥": mem([8, 0, 2, 0, 0], 2), "내력벽": mem([8, 0, 2, 0, 0], 1), "큰보": mem([7, 0, 3, 0, 0], 3), "작은보": mem([7, 0, 0, 3, 0], 3), "슬래브": mem([7, 0, 3, 0, 0], 1)},
        {"기둥": mem([8, 0, 2, 0, 0], 0), "내력벽": mem([8, 0, 0, 2, 0], 10), "큰보": mem([7, 0, 3, 0, 0], 2), "작은보": mem([7, 0, 0, 3, 0], 2), "슬래브": mem([7, 0, 3, 0, 0], 3)},
        {"기둥": mem([8, 0, 0, 2, 0], 2), "내력벽": mem([8, 0, 0, 2, 0], 1), "큰보": mem([7, 0, 0, 3, 0], 1), "작은보": mem([7, 0, 0, 3, 0], 5), "슬래브": mem([7, 0, 3, 0, 0], 5)},
        {"기둥": mem([8, 2, 0, 0, 0], 10), "내력벽": mem([7, 2, 1, 0, 0], 10), "큰보": mem([7, 2, 1, 0, 0], 10), "작은보": mem([5, 3, 3, 1, 3], 6), "슬래브": mem([19, 12, 7, 5, 0], 36)},
        {"기둥": mem([6, 1, 0, 0, 0], 6), "내력벽": mem([7, 2, 1, 0, 0], 3), "큰보": mem([5, 3, 3, 1, 3], 0), "작은보": mem([5, 3, 3, 1, 3], 1), "슬래브": mem([19, 12, 7, 5, 0], 0)},
    ],
    # 균열폭 고정, 면적률 개수만 바꿈
    "area3": [
        {"기둥": mem([7, 2, 1, 0, 0], 0), "내력벽": mem([7, 2, 1, 0, 0], 10), "큰보": mem([7, 2, 1, 0, 0], 0), "작은보": mem([7, 2, 1, 0, 0], 3), "슬래브": mem([7, 2, 1, 0, 0], 10)},
        {"기둥": mem([7, 2, 1, 0, 0], 10), "내력벽": mem([7, 2, 1, 0, 0], 0), "큰보": mem([7, 2, 1, 0, 0], 1), "작은보": mem([7, 2, 1, 0, 0], 2), "슬래브": mem([7, 2, 1, 0, 0], 5)},
        {"기둥": mem([7, 0, 3, 0, 0], 10), "내력벽": mem([7, 0, 3, 0, 0], 2), "큰보": mem([7, 0, 3, 0, 0], 0), "작은보": mem([7, 0, 3, 0, 0], 3), "슬래브": mem([7, 0, 3, 0, 0], 4)},
        {"기둥": mem([8, 1, 1, 0, 0], 0), "내력벽": mem([8, 1, 1, 0, 0], 10), "큰보": mem([8, 1, 1, 0, 0], 3), "작은보": mem([8, 1, 1, 0, 0], 1), "슬래브": mem([8, 1, 1, 0, 0], 10)},
        {"기둥": mem([6, 3, 1, 0, 0], 0), "내력벽": mem([6, 3, 1, 0, 0], 10), "큰보": mem([6, 3, 1, 0, 0], 10), "작은보": mem([6, 3, 1, 0, 0], 1), "슬래브": mem([6, 3, 1, 0, 0], 0)},
        {"기둥": mem([5, 2, 2, 1, 0], 0), "내력벽": mem([5, 2, 2, 1, 0], 10), "큰보": mem([5, 2, 2, 1, 0], 0), "작은보": mem([5, 2, 2, 1, 0], 10), "슬래브": mem([5, 2, 2, 1, 0], 4)},
    ],
}


def run(name: str) -> list[dict]:
    floors = [{"rep": k + 1, "members": ms} for k, ms in enumerate(SETS[name])]
    case = {"above": 10, "below": 0, "floors": floors, "tilt": 0, "settle": 0}
    p = WORK / "cases" / f"rule_{name}.sfm"
    p.parent.mkdir(exist_ok=True)
    D.to_sfm(case, p)
    vals = smrun.run(p)
    t = D.theirs(vals)
    o = D.ours(case)
    rows = []
    for fl, tf, of in zip(floors, t["floors"], o["floors"]):
        for m, mm in fl["members"].items():
            rows.append({"floor": fl["rep"], "member": m, "width": mm["crack"], "area_ge": mm["crack_area"][1], "carb": mm.get("carb"),
                         "sm": tf["members"].get(m), "ours": of["members"].get(m)})
    json.dump({"case": case, "rows": rows}, open(WORK / f"rule_{name}.json", "w", encoding="utf-8"), ensure_ascii=False)
    return rows


if __name__ == "__main__":
    for r in run(sys.argv[1]):
        flag = "" if r["sm"] == r["ours"] else "  ← 다름"
        print(f"{r['floor']}층 {r['member']:<3} 균열폭 {r['width']} 20%이상 {r['area_ge']:>2} {('탄산화 ' + str(r['carb'])) if r['carb'] else ''} | SM {r['sm']}  우리 {r['ours']}{flag}")
