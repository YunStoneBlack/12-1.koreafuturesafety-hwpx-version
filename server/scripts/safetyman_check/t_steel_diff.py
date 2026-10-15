"""강재 섞인 무작위 건물 — SafetyMan ↔ rating.py(강재 규칙) 비교. 사용: python t_steel_diff.py <건수> <시작 seed>
층 재료: RC / 철골조 / SRC / 형 방식(같은 층 RC + 철골조 표본층). 화면에서 못 넣는 칸(철골조 기둥·보 콘크리트, SRC 기둥 강재, RC 강재)은 안 넣음."""
from __future__ import annotations

import json
import random
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import smrun  # noqa: E402
import t_diff as D  # noqa: E402
import t_steel as S  # noqa: E402
from server.sitok import rating  # noqa: E402

MAT = {0: "RC", 1: "SRC", 2: "철골"}
STEEL_ONLY = "--steel" in sys.argv  # 층마다 강재(철골조·SRC·형 방식)만


def rc_mem(rng):
    n = rng.randint(4, 40)
    bad = rng.choice([0, 0.05, 0.15, 0.35, 0.6])
    mm = {"n": n, "crack": D.counts_random(rng, n, bad)}
    ar = rng.choice([0, 0, 0, rng.randint(0, n)])
    mm["crack_area"] = [n - ar, ar]
    for it in ("scaling", "spalling", "leak", "rebar"):
        mm[it] = D.counts_random(rng, n, bad * rng.choice([0, 0.5, 1]))
    mm["scaling_area"] = [n, 0]
    mm["spalling_area"] = [n, 0]
    mm["strength"] = [(round(rng.uniform(0.62, 1.2) * 24, 2), 24.0, rng.random() < 0.2) for _ in range(rng.choice([0, 0, 1, 2, 3]))]
    if rng.random() < 0.4:
        mm["carb"] = [(round(rng.uniform(0.0, 1.3) * 4.0, 3), 4.0)]
    return mm


def steel_mem(rng):
    st = {}
    while not st:
        if rng.random() < 0.8:
            st["ss"] = [(round(rng.choice([rng.uniform(70, 110), 100.0, 97.0]), 1), 100) for _ in range(rng.randint(1, 3))]
        if rng.random() < 0.4:
            st["weld"] = D.counts_random(rng, rng.randint(1, 20), rng.choice([0.1, 0.3, 0.6]))
        if rng.random() < 0.4:
            n = rng.randint(5, 200)
            st["bolt"] = [rng.choice([0, 0, rng.randint(0, n // 3)]), n]
        if rng.random() < 0.4:
            st["corr"] = D.counts_random(rng, rng.randint(1, 20), rng.choice([0.1, 0.3, 0.6]))
        if rng.random() < 0.3:
            st["fire"] = [(round(rng.uniform(1.2, 2.4), 2), 2.0, int(rng.random() < 0.3)) for _ in range(rng.randint(1, 2))]
    return st


def make_case(rng) -> dict:
    above, below = rng.randint(3, 15), rng.randint(0, 2)
    levels = [x for x in range(-below, above + 1) if x != 0]
    reps = sorted(rng.sample(levels, rng.randint(1, min(3, len(levels)))))
    floors = []
    for rep in reps:
        kind = rng.choice(["철골", "SRC", "형", "철골", "형"] if STEEL_ONLY else ["RC", "RC", "철골", "SRC", "형"])
        if kind in ("RC", "형"):
            floors.append({"rep": rep, "material": 0, "members": {m: rc_mem(rng) for m in D.MEM if rng.random() < 0.8}})
        if kind in ("철골", "형"):
            fl = {"rep": rep, "material": 2, "steel": {m: steel_mem(rng) for m in rating.STEEL_KINDS if rng.random() < 0.8}}
            if kind == "철골" and rng.random() < 0.6:
                fl["members"] = {"슬래브": rc_mem(rng)}
            floors.append(fl)
        if kind == "SRC":
            floors.append({"rep": rep, "material": 1, "members": {m: rc_mem(rng) for m in D.MEM if rng.random() < 0.8},
                           "steel": {m: steel_mem(rng) for m in ("큰보", "작은보") if rng.random() < 0.7}})
    return {"above": above, "below": below, "floors": floors, "tilt": rng.randint(0, 4), "settle": rng.randint(0, 4)}


def steel_scores(st: dict) -> dict:
    g = rating.GRADES
    out = {}
    if st.get("ss"):
        out["SS"] = rating.mean_score([rating.grade_section(a, d) for a, d in st["ss"]])
    if st.get("fire"):
        out["FP"] = rating.mean_score([rating.grade_fireproof(a, d, bool(x)) for a, d, x in st["fire"]])
    if st.get("weld"):
        out["WE"] = rating.count_score(dict(zip(g, st["weld"])))
    if st.get("bolt"):
        b = rating.grade_bolt(*st["bolt"])
        out["BO"] = float(rating.SCORE[b]) if b else None
    if st.get("corr"):
        out["SC"] = rating.count_score(dict(zip(g, st["corr"])))
    return out


def ours(case: dict) -> dict:
    floors = []
    for fl in case["floors"]:
        members = []
        for m in D.MEM:
            mm = (fl.get("members") or {}).get(m)
            st = (fl.get("steel") or {}).get(m)
            if not mm and not st:
                continue
            items = {}
            if mm:
                if mm["strength"]:
                    items["DS"] = rating.mean_grade([rating.grade_strength(a, d, dmg) for a, d, dmg in mm["strength"]])
                if mm.get("carb"):
                    items["CA"] = rating.mean_grade([rating.grade_carbonation(dp, cv) for dp, cv in mm["carb"]])
                items["CR"] = rating.grade_from_counts(dict(zip(rating.GRADES, mm["crack"])), m, mm["crack_area"][1])
                items["SD"] = rating.worst(*[rating.grade_from_counts(dict(zip(rating.GRADES, mm[it])), m) for it in ("scaling", "spalling", "leak", "rebar")])
            members.append(rating.Member(m, items, steel=steel_scores(st) if st else {}))
        floors.append(rating.Floor(f"{fl['rep']}층", fl["rep"], members, material=MAT[fl.get("material", 0)]))
    b = rating.Building(above=case["above"], below=case["below"], floors=floors, tilt=rating.GRADES[case["tilt"]], settlement=rating.GRADES[case["settle"]])
    r = rating.evaluate(b)
    mats = [MAT[x.get("material", 0)] for x in case["floors"]]
    return {"floors": [{"floor": f["floor"], "material": fm, "members": {x["kind"]: x["condition"] for x in f["members"]}, "condition": f["condition"]}
                       for f, fm in zip(r["floors"], mats)],
            "condition": r["condition"], "deform": r["deform"], "total": r["total"]}


def theirs(vals: list[list]) -> dict:
    t = D.theirs(vals)
    mats = []
    for i, row in enumerate(vals):
        b = str(row[1] or "")
        m = re.match(r"^(-?\d+)층\s*\n?\(.*?\)\s*\n?.*?\((RC|SRC|철골조)\)", b, re.S)
        if m and i + 1 < len(vals) and str(vals[i + 1][13] or "").strip() == "상태":
            mats.append({"RC": "RC", "SRC": "SRC", "철골조": "철골"}[m[2]])
    for f, mt in zip(t["floors"], mats):
        f["material"] = mt
    return t


def compare(o: dict, t: dict) -> list[str]:
    bad = []
    if len(o["floors"]) != len(t["floors"]):
        return [f"층 수 다름 {len(o['floors'])} vs {len(t['floors'])}"]
    left = list(t["floors"])
    for of in o["floors"]:
        tf = next((x for x in left if x["floor"] == of["floor"] and x.get("material") == of["material"]), None)
        if tf is None:
            bad.append(f"{of['floor']}층 {of['material']} 짝 없음")
            continue
        left.remove(tf)
        for k in D.MEM:
            a, b = of["members"].get(k), tf["members"].get(k)
            if (a is None) != (b is None) or (a is not None and abs(a - b) > 0.006):
                bad.append(f"{of['floor']}층{of['material']} {k}: 우리 {a} / SM {b}")
        tt = re.match(r"([\d.]+)", tf["total_text"] or "")
        if (of["condition"] is None) != (tt is None) or (tt and abs(of["condition"] - float(tt[1])) > 0.006):
            bad.append(f"{of['floor']}층{of['material']} 종합: 우리 {of['condition']} / SM {tf['total_text']}")
    if t["condition"] and o["condition"] and abs(o["condition"]["score"] - t["condition"][0]) > 0.006:
        bad.append(f"상태평가: 우리 {o['condition']} / SM {t['condition']}")
    if t["total"] and o["total"] and abs(o["total"]["score"] - t["total"][0]) > 0.006:
        bad.append(f"종합평가: 우리 {o['total']} / SM {t['total']}")
    return bad


if __name__ == "__main__":
    n, seed0 = int(sys.argv[1]), int(sys.argv[2])
    out = open(D.WORK / "steel_diff.jsonl", "a", encoding="utf-8")
    ok = 0
    for k in range(n):
        seed = seed0 + k
        case = make_case(random.Random(seed))
        p = D.WORK / "cases" / f"steel_{seed}.sfm"
        p.parent.mkdir(exist_ok=True)
        S.to_sfm(case, p)
        t0 = time.time()
        try:
            vals = smrun.run(p)
            t = theirs(vals)
            o = ours(case)
            bad = compare(o, t) if t["floors"] else ["SafetyMan 결과 못 읽음"]
        except Exception as e:  # noqa: BLE001
            t, o, bad = {}, {}, [f"오류: {e!r}"]
        ok += not bad
        mats = "".join({0: "R", 1: "S", 2: "철"}[f.get("material", 0)] for f in case["floors"])
        print(f"[{seed}] {'일치' if not bad else '다름'} ({time.time() - t0:.0f}초) 층 {mats}" + ("" if not bad else " — " + " / ".join(bad[:6])), flush=True)
        out.write(json.dumps({"seed": seed, "case": case, "ours": o, "theirs": t, "bad": bad}, ensure_ascii=False, default=str) + "\n")
        out.flush()
    print(f"끝: {ok}/{n} 일치")
