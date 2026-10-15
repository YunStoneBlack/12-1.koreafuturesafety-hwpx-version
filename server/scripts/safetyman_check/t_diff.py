"""SafetyMan ↔ 우리 상태평가(rating.py) 차등 시험 — 무작위 입력을 .sfm으로 만들어 SafetyMan 평가 결과와 우리 계산을 비교.
사용: python t_diff.py <건수> <시작 seed>   결과는 diff_results.jsonl(한 줄 = 한 건)."""
from __future__ import annotations

import copy
import json
import os
import tempfile
import random
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
WORK = Path(os.environ.get("SM_WORK") or (Path(tempfile.gettempdir()) / "safetyman_check"))  # 시험 파일·결과(저장소 밖)
WORK.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # 저장소 뿌리
import sfm  # noqa: E402
import smrun  # noqa: E402
from server.sitok import rating  # noqa: E402

K = 2753.416 / 27  # 저장 강도 = 값 × K(다산 27 → 2753.416)
SLOT = {"기둥": 0, "내력벽": 1, "슬래브": 2, "큰보": 5, "작은보": 6}  # 강도·균열·표면노후 칸
CSLOT = SLOT  # 탄산화 칸도 같은 순서(화면 저장 비교로 확인)
MEM = ("기둥", "내력벽", "큰보", "작은보", "슬래브")
BASE = sfm.read(open(r"C:\Users\윤석현1\Desktop\시특법 견본\정밀\상태평가-다산은혜교회.sfm", "rb").read())
RES_COL = {"기둥": 19, "내력벽": 26, "큰보": 33, "작은보": 40, "슬래브": 47}  # T AA AH AO AV(0부터)
BQ = 68  # 종합
BX = 75  # 기울기 및 침하


def counts_random(rng, n, bad_p):
    """n개를 A~E에 — 대부분 A, 가끔 B~E."""
    c = [0] * 5
    for _ in range(n):
        if rng.random() < bad_p:
            c[rng.choice([1, 1, 1, 2, 2, 3, 4])] += 1
        else:
            c[0] += 1
    return c


def make_case(rng) -> dict:
    above, below = rng.randint(3, 20), rng.randint(0, 3)
    levels = [x for x in range(-below, above + 1) if x != 0]
    nfl = rng.randint(1, min(4, len(levels)))
    reps = sorted(rng.sample(levels, nfl))
    floors = []
    for rep in reps:
        fl = {"rep": rep, "members": {}}
        for m in MEM:
            if rng.random() < 0.12:
                continue
            n = rng.randint(4, 50)
            bad = rng.choice([0, 0.05, 0.15, 0.35, 0.6])
            mm = {"n": n}
            mm["crack"] = counts_random(rng, n, bad)
            ar = rng.choice([0, 0, 0, rng.randint(0, n)])
            mm["crack_area"] = [n - ar, ar]
            for it in ("scaling", "spalling", "leak", "rebar"):
                mm[it] = counts_random(rng, n, bad * rng.choice([0, 0.5, 1]))
            mm["scaling_area"] = [n, 0]
            mm["spalling_area"] = [n, 0]
            k = rng.choice([0, 0, 1, 2, 3])
            mm["strength"] = [(round(rng.uniform(0.62, 1.2) * 24, 2), 24.0, rng.random() < 0.2) for _ in range(k)]
            if rng.random() < 0.4:
                mm["carb"] = [(round(rng.uniform(0.0, 1.3) * 4.0, 3), 4.0)]
            fl["members"][m] = mm
        floors.append(fl)
    return {"above": above, "below": below, "floors": floors, "tilt": rng.randint(0, 4), "settle": rng.randint(0, 4)}


def to_sfm(case: dict, path: Path) -> None:
    if not (WORK / "dummy.jpg").exists():  # SafetyMan은 이미지 경로의 파일이 없으면 평가를 멈춤
        from PIL import Image
        Image.new("RGB", (400, 300), (200, 200, 200)).save(WORK / "dummy.jpg")
    h = copy.deepcopy(BASE)
    h["img"] = str(WORK / "dummy.jpg")
    h["above"], h["below"] = case["above"], case["below"]
    h["tilt"], h["settle"] = case["tilt"], case["settle"]
    h["deform_note"] = ""
    tmpl = BASE["floors"][0]
    out = []
    for fl in case["floors"]:
        f = copy.deepcopy(tmpl)
        f["start"] = f["end"] = f["rep"] = fl["rep"]
        f["strength"] = [[] for _ in range(7)]
        f["carb"] = [[] for _ in range(7)]
        for it in sfm.ITEMS8 + sfm.ITEMS6:
            f[it] = [None] * 7
        for m, mm in fl["members"].items():
            s = SLOT[m]
            f["strength"][s] = [(a * K, 0.0, 0.0, d * K, 1 if dmg else 0) for a, d, dmg in mm["strength"]]
            if m in CSLOT and mm.get("carb"):
                f["carb"][CSLOT[m]] = [(dp, 0.0, 0.0, cv) for dp, cv in mm["carb"]]
            f["crack"][s] = mm["crack"] + mm["crack_area"]
            f["scaling"][s] = mm["scaling"] + mm["scaling_area"]
            f["spalling"][s] = mm["spalling"] + mm["spalling_area"]
            f["leak"][s] = mm["leak"]
            f["rebar"][s] = mm["rebar"]
        out.append(f)
    h["floors"] = out
    path.write_bytes(sfm.write(h))


def ours(case: dict) -> dict:
    floors = []
    for fl in case["floors"]:
        members = []
        for m in MEM:
            mm = fl["members"].get(m)
            if not mm:
                continue
            items = {}
            if mm["strength"]:
                items["DS"] = rating.mean_grade([rating.grade_strength(a, d, dmg) for a, d, dmg in mm["strength"]])
            if mm.get("carb"):
                items["CA"] = rating.mean_grade([rating.grade_carbonation(dp, cv) for dp, cv in mm["carb"]])
            items["CR"] = rating.grade_from_counts(dict(zip(rating.GRADES, mm["crack"])), m, mm["crack_area"][1])
            items["SD"] = rating.worst(*[rating.grade_from_counts(dict(zip(rating.GRADES, mm[it])), m) for it in ("scaling", "spalling", "leak", "rebar")])
            members.append(rating.Member(m, items))
        floors.append(rating.Floor(f"{fl['rep']}층", fl["rep"], members))
    b = rating.Building(above=case["above"], below=case["below"], floors=floors, tilt=rating.GRADES[case["tilt"]], settlement=rating.GRADES[case["settle"]])
    r = rating.evaluate(b)
    return {"floors": [{"floor": f["floor"], "members": {x["kind"]: x["condition"] for x in f["members"]}, "condition": f["condition"]} for f in r["floors"]],
            "condition": r["condition"], "deform": r["deform"], "total": r["total"]}


def theirs(vals: list[list]) -> dict:
    floors = []
    cond = total = deform = None
    for i, row in enumerate(vals):
        b = str(row[1] or "")
        m = re.match(r"^(-?\d+)층\s*\n?\(", b)
        if m and i + 1 < len(vals) and str(vals[i + 1][13] or "").strip() == "상태":
            nxt = vals[i + 1]
            mem = {k: (None if str(nxt[c]).strip() in ("-", "", "None") else float(nxt[c])) for k, c in RES_COL.items()}
            floors.append({"floor": int(m[1]), "members": mem, "total_text": str(nxt[BQ])})
            if deform is None and row[BX]:
                deform = str(row[BX])
        txt = " ".join(str(c) for c in row if c)
        mm = re.search(r"상태평가:\s*([\d.]+)\((\w)등급\)\s*종합평가:\s*([\d.]+)\((\w)등급\)", txt)
        if mm:
            cond, total = (float(mm[1]), mm[2]), (float(mm[3]), mm[4])
    return {"floors": floors, "condition": cond, "total": total, "deform": deform}


def compare(o: dict, t: dict) -> list[str]:
    bad = []
    if len(o["floors"]) != len(t["floors"]):
        return [f"층 수 다름 {len(o['floors'])} vs {len(t['floors'])}"]
    for of, tf in zip(o["floors"], t["floors"]):
        for k in MEM:
            a, b = of["members"].get(k), tf["members"].get(k)
            if (a is None) != (b is None) or (a is not None and abs(a - b) > 0.006):
                bad.append(f"{of['floor']}층 {k}: 우리 {a} / SM {b}")
        tt = re.match(r"([\d.]+)", tf["total_text"] or "")
        if (of["condition"] is None) != (tt is None) or (tt and abs(of["condition"] - float(tt[1])) > 0.006):
            bad.append(f"{of['floor']}층 종합: 우리 {of['condition']} / SM {tf['total_text']}")
    if t["condition"] and (abs(o["condition"]["score"] - t["condition"][0]) > 0.006):
        bad.append(f"상태평가: 우리 {o['condition']} / SM {t['condition']}")
    if t["total"] and (abs(o["total"]["score"] - t["total"][0]) > 0.006):
        bad.append(f"종합평가: 우리 {o['total']} / SM {t['total']}")
    dm = re.match(r"([\d.]+)", t["deform"] or "")
    if dm and o["deform"] and abs(o["deform"]["score"] - float(dm[1])) > 0.006:
        bad.append(f"기울기 및 침하: 우리 {o['deform']} / SM {t['deform']}")
    return bad


if __name__ == "__main__":
    n, seed0 = int(sys.argv[1]), int(sys.argv[2])
    out = open(WORK / "diff_results.jsonl", "a", encoding="utf-8")
    ok = 0
    for k in range(n):
        seed = seed0 + k
        rng = random.Random(seed)
        case = make_case(rng)
        p = WORK / "cases" / f"case_{seed}.sfm"
        p.parent.mkdir(exist_ok=True)
        to_sfm(case, p)
        t0 = time.time()
        try:
            vals = smrun.run(p)
            t = theirs(vals)
            o = ours(case)
            bad = compare(o, t) if t["floors"] else ["SafetyMan 결과 못 읽음"]
        except Exception as e:  # noqa: BLE001
            t, o, bad = {}, {}, [f"오류: {e}"]
        ok += not bad
        print(f"[{seed}] {'일치' if not bad else '다름'} ({time.time() - t0:.0f}초) 층 {len(case['floors'])}" + ("" if not bad else " — " + " / ".join(bad[:6])), flush=True)
        out.write(json.dumps({"seed": seed, "case": case, "ours": o, "theirs": t, "bad": bad}, ensure_ascii=False, default=str) + "\n")
        out.flush()
    print(f"끝: {ok}/{n} 일치")
