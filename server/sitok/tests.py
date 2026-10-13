"""시특법 정밀안전점검 재료시험(2026-10-13 밤, ② 단계) — 회차 tests JSON(입력)을 받아 등급·계산값을 붙인 보기(view)를 만든다.

입력(사용자가 적는 것)과 계산(우리가 붙이는 것)을 나눠 둔다. 저장은 입력만, 화면·보고서는 compute()가 돌려주는 값을 쓴다.
계산식은 다산은혜교회 26년 상반기 정밀안전점검 보고서(4장 재료시험·부록 성과표)와 맞춤:
- 표본층 수 = 지침 표 6.19·6.20(rating.sample_floors), 수량 = 층 × 2부재 × (강도 2·규격 3·탄산화 1)(rating.sample_quantities), 기울기 4면, 부등침하 X·Y 2개소.
- 표본층 범위: 요원이 층만 고르면 자동 분할(사용자 10/13) — 두 표본층 사이 가운데, 지하/지상 경계가 사이에 있으면 거기서(다산 -3~-1 / 1~5). 고칠 수 있음.
- 부재 규격: "300×600"·"300" → 면적(두께) 비율 → rating.grade_section, 100% 이상이면 "O.K".
- 강도: 슈미트 추정강도(MPa) ÷ 설계기준강도 → rating.grade_strength(건전부/손상).
- 탄산화(mm, 경과년수 t = 준공 ~ 점검): 잔여 = 피복 − 깊이, 속도계수 A = 깊이/√t, 이론치 = R·(4.6·(W/C) − 1.76)/√7.2 · √t (cm → mm; 기시타니 식, 다산 4.37mm),
  잔존수명 = (피복/A)² − t(100년 넘으면 "100년 이상", 다산 C1 80.7년), 등급 = rating.grade_carbonation(깊이/피복).
- 기울기: 1/N, N = 측정높이 ÷ 변위량 → rating.grade_tilt. 부등침하: 구간(측점 3개·거리 2개) → 변위 = 앞 측점 − 뒤 측점, N = 거리 ÷ |변위|.
"""
from __future__ import annotations

import datetime
import math
import re

from server.sitok import rating

DEFAULT_WC = 0.51  # 물-시멘트비(다산 보고서) — 탄산화 이론치에만 씀
DEFAULT_R = 1.0  # 탄산화 비율(R)
STRUCTURES = ("라멘", "벽식", "무량판")
MATERIALS = ("RC", "SRC", "철골", "조적")
TILT_DIRS = ("좌측", "우측", "전면", "후면")
MEMBER_SPOTS = ("기둥 중앙부", "기둥 단부", "보 중앙부", "보 단부")  # 강도 기본 부재부위(층마다 2부재 × 2개소)


# ---------- 층 ----------

def floor_keys(above: int, below: int) -> list[int]:
    """아래서부터 층 번호(지하 -k, 지상 k, 0 없음)."""
    return list(range(-(below or 0), 0)) + list(range(1, (above or 0) + 1))


def floor_label(k: int) -> str:
    return f"지하{-k}층" if k < 0 else f"지상{k}층"


def range_label(start: int, end: int) -> str:
    return f"{floor_label(start)}~{floor_label(end)}" if start != end else floor_label(start)


def split_ranges(samples: list[int], above: int, below: int) -> list[tuple[int, int]]:
    """표본층마다 대표 범위 (start, end) — 두 표본층 사이 가운데, 지하/지상 경계가 사이에 있으면 거기서."""
    keys = floor_keys(above, below)
    idx = {k: i for i, k in enumerate(keys)}
    fl = sorted(k for k in samples if k in idx)
    if not fl:
        return []
    out = []
    start = keys[0]
    for j, f in enumerate(fl):
        if j + 1 < len(fl):
            g = fl[j + 1]
            if f < 0 < g:
                end, nxt = -1, 1
            else:
                mid = (idx[f] + idx[g]) // 2
                end, nxt = keys[mid], keys[mid + 1]
        else:
            end, nxt = keys[-1], None
        out.append((start, end))
        start = nxt
    return out


def age_years(completion: datetime.date | None, when: datetime.date | None) -> int | None:
    """경과년수 = 점검 연도 − 준공 연도(다산: 2022.05.31 준공, 2026.05 점검 → 4년 — 날짜는 안 봄)."""
    if not completion:
        return None
    when = when or datetime.date.today()
    return max(0, when.year - completion.year)


# ---------- 값 다듬기 ----------

def _f(v) -> float | None:
    try:
        s = str(v).replace(",", "").strip()
        return float(s) if s not in ("", "-") else None
    except (TypeError, ValueError):
        return None


def _i(v) -> int | None:
    f = _f(v)
    return int(round(f)) if f is not None else None


def _dims(s: str) -> float | None:
    """"300×600" → 180000, "300" → 300(두께·폭 하나). ×·x·X·* 다 됨."""
    nums = [_f(p) for p in re.split(r"[×xX*]", str(s or "")) if p.strip()]
    if not nums or any(n is None for n in nums):
        return None
    return math.prod(nums)


def ratio_text(n: float | None) -> str:
    return f"1/{int(round(n)):,}" if n and n > 0 else "-"


# ---------- 항목 계산 ----------

def section_row(r: dict) -> dict:
    d, m = _dims(r.get("design")), _dims(r.get("measured"))
    out = {**r, "ratio": None, "grade": None, "ok": None}
    if d and m is not None:
        out["ratio"] = round(m / d * 100, 1)
        out["grade"] = rating.grade_section(m, d)
        out["ok"] = m >= d
    return out


def strength_row(r: dict) -> dict:
    est, design = _f(r.get("est")), _f(r.get("design"))
    out = {**r, "ratio": None, "grade": None}
    if est is not None and design:
        out["ratio"] = round(est / design * 100, 1)
        out["grade"] = rating.grade_strength(est, design, bool(r.get("damaged")))
    return out


def carbonation_row(r: dict, t: int | None, wc: float, R: float) -> dict:
    cover, depth = _f(r.get("cover")), _f(r.get("depth"))
    out = {**r, "age": t, "remain": None, "coef": None, "theory": None, "life": None, "life_text": "", "grade": None}
    if cover is None or depth is None:
        return out
    out["remain"] = round(cover - depth, 2)
    if cover > 0:
        out["grade"] = rating.grade_carbonation(depth, cover)
    if t and t > 0:
        out["theory"] = round(R * (4.6 * wc - 1.76) / math.sqrt(7.2) * math.sqrt(t) * 10, 2)
        if depth > 0:
            a = depth / math.sqrt(t)
            out["coef"] = round(a, 2)
            life = (cover / a) ** 2 - t
            out["life"] = round(life, 1)
            out["life_text"] = "100년 이상" if life >= 100 else f"{life:.1f}"
        else:
            out["coef"] = 0.0
            out["life_text"] = "100년 이상"
    return out


def tilt_row(r: dict) -> dict:
    h, d = _f(r.get("height")), _f(r.get("disp"))
    out = {**r, "n": None, "ratio_text": "-", "grade": None}
    if h and d is not None:
        if d == 0:
            out["n"], out["ratio_text"], out["grade"] = None, "-", "a"
        else:
            n = h / abs(d)
            out["n"], out["ratio_text"], out["grade"] = round(n), ratio_text(n), rating.grade_tilt(1 / n)
    return out


def settlement_section(sec: dict) -> dict:
    levels = [_f(v) for v in sec.get("levels") or []]
    dists = [_f(v) for v in sec.get("distances") or []]
    rows = []
    for i, lv in enumerate(levels):
        row = {"no": i + 1, "level": lv, "disp": None, "distance": None, "n": None, "ratio_text": "", "grade": None}
        if i + 1 < len(levels) and levels[i + 1] is not None and lv is not None:
            disp = lv - levels[i + 1]
            dist = dists[i] if i < len(dists) else None
            row["disp"], row["distance"] = round(disp, 1), dist
            if dist:
                if disp == 0:
                    row["ratio_text"], row["grade"] = "-", "a"
                else:
                    n = dist / abs(disp)
                    row["n"], row["ratio_text"], row["grade"] = round(n), ratio_text(n), rating.grade_tilt(1 / n)
        rows.append(row)
    return {**sec, "rows": rows}


def _worst(grades) -> str | None:
    return rating.worst(*[g for g in grades if g])


def _summary(vals: list[float | None]) -> dict:
    xs = [v for v in vals if v is not None]
    return {"min": round(min(xs), 2) if xs else None, "max": round(max(xs), 2) if xs else None, "mean": round(sum(xs) / len(xs), 1) if xs else None, "count": len(xs)}


# ---------- 전체 ----------

def empty() -> dict:
    return {"sample": {"floors": []}, "sections": [], "strength": {"rows": [], "file": ""},
            "carbonation": {"wc": DEFAULT_WC, "ratio": DEFAULT_R, "rows": []}, "tilt": {"rows": [], "note": ""},
            "settlement": {"floor": None, "sections": [], "note": ""}}


def normalize(raw: dict | None) -> dict:
    """저장할 입력만 남기고 모양을 맞춤(계산값은 버림)."""
    base = empty()
    raw = raw or {}
    s = raw.get("sample") or {}
    floors = []
    for f in s.get("floors") or []:
        k = _i(f.get("floor"))
        if k is None or k == 0:
            continue
        floors.append({"floor": k, "start": _i(f.get("start")), "end": _i(f.get("end")),
                       "structure": f.get("structure") if f.get("structure") in STRUCTURES else "라멘",
                       "material": f.get("material") if f.get("material") in MATERIALS else "RC"})
    base["sample"] = {"floors": sorted(floors, key=lambda x: x["floor"])}
    base["sections"] = [{"floor": _i(r.get("floor")), "position": str(r.get("position") or "").strip(), "member": str(r.get("member") or "").strip(),
                         "design": str(r.get("design") or "").strip(), "measured": str(r.get("measured") or "").strip()} for r in raw.get("sections") or []]
    st = raw.get("strength") or {}
    base["strength"] = {"file": str(st.get("file") or ""), "rows": [
        {"floor": _i(r.get("floor")), "member": str(r.get("member") or "").strip(), "position": str(r.get("position") or "").strip(),
         "r0": _f(r.get("r0")), "fc_mat": _f(r.get("fc_mat")), "fc_arch": _f(r.get("fc_arch")), "est": _f(r.get("est")), "design": _f(r.get("design")),
         "damaged": bool(r.get("damaged")), "note": str(r.get("note") or "").strip()} for r in st.get("rows") or []]}
    ca = raw.get("carbonation") or {}
    base["carbonation"] = {"wc": _f(ca.get("wc")) or DEFAULT_WC, "ratio": _f(ca.get("ratio")) or DEFAULT_R, "rows": [
        {"floor": _i(r.get("floor")), "member": str(r.get("member") or "").strip(), "position": str(r.get("position") or "").strip(),
         "cover": _f(r.get("cover")), "depth": _f(r.get("depth"))} for r in ca.get("rows") or []]}
    ti = raw.get("tilt") or {}
    base["tilt"] = {"note": str(ti.get("note") or ""), "rows": [
        {"height": _f(r.get("height")), "direction": r.get("direction") if r.get("direction") in TILT_DIRS else "", "disp": _f(r.get("disp"))}
        for r in ti.get("rows") or []]}
    se = raw.get("settlement") or {}
    base["settlement"] = {"floor": _i(se.get("floor")), "note": str(se.get("note") or ""), "sections": [
        {"axis": "Y" if str(sec.get("axis") or "").upper() == "Y" else "X", "no": _i(sec.get("no")) or 1,
         "levels": [_f(v) for v in sec.get("levels") or []], "distances": [_f(v) for v in sec.get("distances") or []]} for sec in se.get("sections") or []]}
    return base


def compute(raw: dict | None, *, above: int, below: int, area: float, kind: str, completion: datetime.date | None, when: datetime.date | None) -> dict:
    """입력 + 계산값. above·below·area = 시설물, kind = 정밀점검/정밀안전진단, completion = 준공일, when = 점검일."""
    data = normalize(raw)
    total_floors = (above or 0) + (below or 0)
    need = rating.sample_floors(total_floors, area or 0, "정밀안전진단" if "진단" in (kind or "") else "정밀안전점검") if total_floors else None
    floors = data["sample"]["floors"]
    ranges = dict(zip([f["floor"] for f in floors], split_ranges([f["floor"] for f in floors], above or 0, below or 0)))
    for f in floors:
        auto = ranges.get(f["floor"])
        if auto and (f["start"] is None or f["end"] is None):
            f["start"], f["end"] = auto
        f["label"] = floor_label(f["floor"])
        f["range_label"] = range_label(f["start"], f["end"]) if f["start"] is not None and f["end"] is not None else ""
        f["auto"] = list(auto) if auto else None
    n = len(floors)
    qty = rating.sample_quantities(n) if n else {"strength": 0, "section": 0, "carbonation": 0}
    t = age_years(completion, when)
    sections = [section_row(r) for r in data["sections"]]
    strength = [strength_row(r) for r in data["strength"]["rows"]]
    carb = [carbonation_row(r, t, data["carbonation"]["wc"], data["carbonation"]["ratio"]) for r in data["carbonation"]["rows"]]
    tilt = [tilt_row(r) for r in data["tilt"]["rows"]]
    sett = [settlement_section(s) for s in data["settlement"]["sections"]]
    sett_rows = [r for s in sett for r in s["rows"] if r["grade"]]
    view = {
        "building": {"above": above, "below": below, "area": area, "floors": [{"key": k, "label": floor_label(k)} for k in floor_keys(above or 0, below or 0)],
                     "completion": completion.isoformat() if completion else None, "when": when.isoformat() if when else None, "age": t},
        "sample": {"need": need, "count": n, "floors": floors,
                   "quantity": {"strength": {"need": qty["strength"], "have": len(strength)}, "section": {"need": qty["section"], "have": len(sections)},
                                "carbonation": {"need": qty["carbonation"], "have": len(carb)}, "tilt": {"need": 4, "have": len(tilt)},
                                "settlement": {"need": 4, "have": len(sett)}}},
        "sections": sections, "sections_grade": _worst(r["grade"] for r in sections),
        "strength": {"file": data["strength"]["file"], "rows": strength, "summary": _summary([r["est"] for r in strength]), "grade": _worst(r["grade"] for r in strength)},
        "carbonation": {"wc": data["carbonation"]["wc"], "ratio": data["carbonation"]["ratio"], "rows": carb,
                        "summary": _summary([r["depth"] for r in carb]), "grade": _worst(r["grade"] for r in carb)},
        "tilt": {"note": data["tilt"]["note"], "rows": tilt, "grade": _worst(r["grade"] for r in tilt),
                 "range": {"min_n": min((r["n"] for r in tilt if r["n"]), default=None), "max_n": max((r["n"] for r in tilt if r["n"]), default=None)}},
        "settlement": {"floor": data["settlement"]["floor"], "floor_label": floor_label(data["settlement"]["floor"]) if data["settlement"]["floor"] else "",
                       "note": data["settlement"]["note"], "sections": sett, "grade": _worst(r["grade"] for r in sett_rows),
                       "range": {"min_disp": min((abs(r["disp"]) for r in sett_rows), default=None), "max_disp": max((abs(r["disp"]) for r in sett_rows), default=None)}},
    }
    return view


def default_strength_rows(floors: list[dict]) -> list[dict]:
    """표본층마다 강도 기본 줄 4개(2부재 × 중앙부·단부) — 슈미트 성과표를 올리기 전 자리."""
    rows = []
    for f in floors:
        for m in MEMBER_SPOTS:
            rows.append({"floor": f["floor"], "member": m, "position": "", "r0": None, "fc_mat": None, "fc_arch": None, "est": None, "design": None,
                         "damaged": False, "note": "건전부"})
    return rows


def spots_to_rows(spots: list, floors: list[dict], existing: list[dict]) -> list[dict]:
    """슈미트 성과표 위치들 → 강도 줄. 기존 줄이 있으면 순서대로 값만 채우고(층·부재·설계강도는 남김), 모자라면 표본층 순서로 기본 부재부위를 붙임."""
    rows = [dict(r) for r in existing]
    defaults = default_strength_rows(floors)
    for i, s in enumerate(spots):
        if i >= len(rows):
            rows.append(defaults[i] if i < len(defaults) else {"floor": floors[-1]["floor"] if floors else None, "member": "", "position": "", "design": None,
                                                                 "damaged": False, "note": "건전부"})
        r1 = lambda v: round(v, 1) if v is not None else None  # noqa: E731 — 보고서 표는 소수 1자리
        rows[i].update({"position": s.position, "r0": r1(s.r0), "fc_mat": r1(s.est_mat), "fc_arch": r1(s.est_arch), "est": r1(s.est)})
        if s.note and not rows[i].get("note"):
            rows[i]["note"] = s.note
    return rows


def _selfcheck() -> None:
    # 다산: 지하3·지상5, 표본층 -3·5 → -3~-1 / 1~5 ; 조훈 -2·8·16(지하2·지상16) → 가운데 나눔
    assert split_ranges([-3, 5], 5, 3) == [(-3, -1), (1, 5)]
    assert split_ranges([-2, 8, 16], 16, 2) == [(-2, -1), (1, 12), (13, 16)]
    assert age_years(datetime.date(2022, 5, 31), datetime.date(2026, 5, 21)) == 4 and age_years(datetime.date(2022, 5, 1), datetime.date(2026, 5, 21)) == 4
    c1 = carbonation_row({"cover": 61, "depth": 13.26}, 4, 0.51, 1.0)
    assert c1["remain"] == 47.74 and c1["coef"] == 6.63 and c1["theory"] == 4.37 and abs(c1["life"] - 80.7) < 0.2 and c1["grade"] == "a", c1
    c2 = carbonation_row({"cover": 51, "depth": 8.02}, 4, 0.51, 1.0)
    assert c2["life_text"] == "100년 이상" and c2["grade"] == "a"
    t1 = tilt_row({"height": 29200, "disp": 25})
    assert t1["ratio_text"] == "1/1,168" and t1["grade"] == "a", t1
    s1 = settlement_section({"axis": "X", "no": 1, "levels": [1350, 1341, 1344], "distances": [9300, 9300]})
    assert [r["disp"] for r in s1["rows"]] == [9, -3, None] and s1["rows"][0]["ratio_text"] == "1/1,033" and s1["rows"][1]["ratio_text"] == "1/3,100"
    s2 = settlement_section({"axis": "Y", "no": 2, "levels": [1365, 1348, 1354], "distances": [7500, 6800]})
    assert s2["rows"][0]["grade"] == "c" and s2["rows"][0]["ratio_text"] == "1/441" and s2["rows"][1]["grade"] == "a"
    sec = section_row({"design": "800×800", "measured": "800×800"})
    assert sec["ok"] and sec["grade"] == "a" and section_row({"design": "300", "measured": "280"})["grade"] == "c"
    st = strength_row({"est": 30.9, "design": 30})
    assert st["grade"] == "a" and strength_row({"est": 19.5, "design": 21})["grade"] == "c"
    v = compute({"sample": {"floors": [{"floor": -3}, {"floor": 5}]}}, above=5, below=3, area=6882.61, kind="정밀점검",
                completion=datetime.date(2022, 5, 31), when=datetime.date(2026, 5, 21))
    assert v["sample"]["need"] == 2 and v["sample"]["floors"][0]["range_label"] == "지하3층~지하1층" and v["sample"]["quantity"]["strength"]["need"] == 8
    print("재료시험 계산 검증 통과 — 다산은혜교회 보고서 값과 일치")


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    _selfcheck()
