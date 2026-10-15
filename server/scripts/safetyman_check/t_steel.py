"""강재(철골조·SRC) 시험 — 층마다 재료·RC 부재·강재 항목을 넣어 SafetyMan 부재 점수 보기.
case = {"above", "below", "tilt", "settle", "floors": [{"rep", "start"?, "end"?, "material": 0 RC·1 SRC·2 철골조, "members": {RC 부재: t_diff mem}, "steel": {기둥|큰보|작은보: {ss, fire, weld, bolt, corr}}}]}"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import sfm  # noqa: E402
import smrun  # noqa: E402
import t_diff as D  # noqa: E402

COLS = {"기둥": 19, "내력벽": 26, "큰보": 33, "작은보": 40, "슬래브": 47}


def to_sfm(case: dict, path: Path) -> None:
    D.to_sfm({"above": 1, "below": 0, "floors": [], "tilt": 0, "settle": 0}, D.WORK / "_dummy.sfm")  # 더미 그림 만들기
    h = copy.deepcopy(D.BASE)
    h["img"] = str(D.WORK / "dummy.jpg")
    h["above"], h["below"] = case.get("above", 20), case.get("below", 0)
    h["tilt"], h["settle"] = case.get("tilt", 0), case.get("settle", 0)
    h["deform_note"] = ""
    tmpl = D.BASE["floors"][0]
    out = []
    for fl in case["floors"]:
        f = copy.deepcopy(tmpl)
        f["rep"] = fl["rep"]
        f["start"], f["end"] = fl.get("start", fl["rep"]), fl.get("end", fl["rep"])
        f["material"] = fl.get("material", 0)
        f["strength"] = [[] for _ in range(7)]
        f["carb"] = [[] for _ in range(7)]
        for it in sfm.ITEMS8 + sfm.ITEMS6:
            f[it] = [None] * 7
        for m, mm in (fl.get("members") or {}).items():
            s = D.SLOT[m]
            f["strength"][s] = [(a * D.K, 0.0, 0.0, d * D.K, 1 if dmg else 0) for a, d, dmg in mm.get("strength", [])]
            if mm.get("carb"):
                f["carb"][s] = [(dp, 0.0, 0.0, cv) for dp, cv in mm["carb"]]
            f["crack"][s] = mm["crack"] + mm["crack_area"]
            f["scaling"][s] = mm["scaling"] + mm["scaling_area"]
            f["spalling"][s] = mm["spalling"] + mm["spalling_area"]
            f["leak"][s] = mm["leak"]
            f["rebar"][s] = mm["rebar"]
        f["ss"] = [[], [], []]
        f["fire"] = [[], [], []]
        for k in sfm.JOINT_N:
            f[k] = [None, None, None]
        for m, st in (fl.get("steel") or {}).items():
            i = sfm.STEEL3.index(m)
            f["ss"][i] = [tuple(map(float, x)) for x in st.get("ss", [])]
            f["fire"][i] = [(float(a), float(b), int(c)) for a, b, c in st.get("fire", [])]
            for k in sfm.JOINT_N:
                if st.get(k):
                    f[k][i] = list(st[k])
        out.append(f)
    h["floors"] = out
    path.write_bytes(sfm.write(h))


def theirs(vals: list[list]) -> dict:
    t = D.theirs(vals)
    return t


def run(case: dict, name: str) -> dict:
    p = D.WORK / "cases" / f"{name}.sfm"
    p.parent.mkdir(exist_ok=True)
    to_sfm(case, p)
    vals = smrun.run(p)
    t = theirs(vals)
    json.dump({"case": case, "theirs": t}, open(D.WORK / f"{name}.json", "w", encoding="utf-8"), ensure_ascii=False, default=str)
    return t


def show(case: dict, t: dict) -> None:
    for fl, tf in zip(case["floors"], t["floors"]):
        print(f"{fl['rep']}층 재료{fl.get('material', 0)} 종합 {tf['total_text']}")
        for m in ("기둥", "내력벽", "큰보", "작은보", "슬래브"):
            st = (fl.get("steel") or {}).get(m)
            rc = (fl.get("members") or {}).get(m)
            v = tf["members"].get(m)
            if st or rc or v is not None:
                print(f"   {m:<3} SM {v}   강재 {st or ''}   RC {'있음' if rc else ''}")
    print("상태평가", t["condition"], "종합", t["total"])


def mem(width, area_ge=0, strength=None, carb=None):
    """RC 부재 — 균열 개수(A~E)만, 표면노후는 a."""
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


SS = lambda a: [(a, 100)]  # noqa: E731
W = {1: [10, 0, 0, 0, 0], 9: [0, 0, 0, 0, 10], 5: [0, 0, 10, 0, 0]}  # 용접·부식 점수 → 개수
