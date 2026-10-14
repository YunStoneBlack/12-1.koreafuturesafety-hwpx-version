"""시특법 정밀안전점검 상태평가 집계(2026-10-13 밤, ③ 단계) — 결함현황표 + 재료시험(tests) + 표본층별 부재 전체 개수 → rating.evaluate() 입력 → 결과·근거·부록 결과자료 PDF.

민재형·사용자 10/13 결정: 균열·박리·박락·층분리·누수·백태·철근노출은 결함현황표의 **구조체** 줄에서 자동으로 SafetyMan 칸(폭·깊이·면적률)에 넣고, 부재 전체 개수는 표본층마다
부재 종류별 한 번 입력(균열 A와 표면노후 4항목 "발생 없음"에 같은 수, 결함만큼 빼서 B~E) · 결함현황표 개수 = 결함 부재 수 · 결함의 층이 표본층 대표 범위 안이면 그 표본층에 합산 ·
조적벽·파라펫·마감재·계단·처마는 제외 · "보"는 큰보로 · 깊이·면적률이 없는 결함은 B(가장 가벼운 결함 등급) · 변위·변형 = 기울기·부등침하 중 나쁜 쪽 · 안전성(정밀안전진단)은 아직.
계산 규칙(퍼지·Choquet·최소범위)은 rating.py — SafetyMan을 직접 돌려 맞춤(작업내용 43차 ③).
"""
from __future__ import annotations

import re
from pathlib import Path

from server.sitok import kinds, rating

MEMBERS = rating.MEMBERS  # 기둥 내력벽 큰보 작은보 슬래브 테두리보 접합부 — SafetyMan 갑지 열 순서
STEEL_MEMBERS = ("강재기둥", "강재보")  # 철골조(구조재료 철골)일 때 개수·점수(10/14 형: 정밀점검은 강재 규격만) — 갑지 표엔 없고 아래 줄로 덧붙임
STEEL_SUB = {"기둥": "강재기둥", "큰보": "강재보", "작은보": "강재보"}  # 재료시험 강재 줄의 '기둥/큰보/작은보'(sub) → 강재 부재
ITEMS = ("DS", "CA", "CR", "SD")
SURFACE = ("scaling", "spalling", "leak", "rebar")
SURFACE_LABEL = {"scaling": "박리", "spalling": "박락·층분리", "leak": "누수·백태", "rebar": "철근노출"}
ITEM_LABEL = {"DS": "콘크리트 강도", "CA": "콘크리트 중성화", "CR": "균열", "SD": "표면노후"}
CRACK_ROWS = ("0.1mm 미만", "0.2mm 미만", "0.3mm 미만", "0.5mm 미만", "0.5mm 이상")
SCALING_ROWS = ("발생 없음", "0.5mm 미만", "1.0mm 미만", "2.5mm 미만", "2.5mm 이상")
SPALLING_ROWS = ("발생 없음", "15mm 미만", "20mm 미만", "25mm 미만", "25mm 이상")
LEAK_ROWS = ("누수·백태 없음", "경미 — 면적 5% 미만", "현저 — 면적 10% 미만", "진행 관찰 — 면적 20% 미만", "진행 확연 — 면적 20% 이상")
REBAR_ROWS = ("노출 없음", "면적률 1% 미만", "면적률 3% 미만", "면적률 5% 미만", "면적률 5% 이상")


# ---------- 이름 → SafetyMan 부재 ----------

def member_kind(name: str) -> str | None:
    """결함현황표 부재·재료시험 부재부위 이름 → SafetyMan 부재. "기둥(C5)"·"기둥 중앙부" → 기둥, "보 단부"·"큰보" → 큰보, "슬라브" → 슬래브, "내력벽(W5)"·"벽체" → 내력벽."""
    n = (name or "").replace(" ", "")
    if not n:
        return None
    if "접합부" in n:
        return "접합부"
    if "테두리보" in n:
        return "테두리보"
    if "작은보" in n:
        return "작은보"
    if "기둥" in n:
        return "기둥"
    if "슬라브" in n or "슬래브" in n or "바닥" in n:
        return "슬래브"
    if "큰보" in n or re.search(r"(^|[^가-힣])보", n) or n.startswith("보") or "보(" in n or n.endswith("보"):
        return "큰보"
    if "내력벽" in n or "벽" in n:
        return "내력벽"
    return None


def floor_key(text: str) -> int | None:
    """"지하1층" → -1, "지상2층"·"2층" → 2, 옥상·옥탑·PIT → None(표본층에 못 넣음)."""
    t = (text or "").replace(" ", "")
    m = re.match(r"^지하(\d+)층?", t)
    if m:
        return -int(m[1])
    m = re.match(r"^(?:지상)?(\d+)층?", t)
    if m:
        return int(m[1])
    return None


def _num(v) -> float | None:
    try:
        s = str(v).replace(",", "").replace("%", "").strip()
        return float(s) if s not in ("", "-") else None
    except (TypeError, ValueError):
        return None


def defect_item(dtype: str) -> str | None:
    """결함유형 → 상태평가 항목: CR 균열(마감층 균열 제외) / scaling 박리 / spalling 박락·층분리 / leak 누수·백태 / rebar 철근노출. 그 밖(이격·파손·재료분리)은 None."""
    t = kinds.norm(dtype)
    if "균열" in t:
        return None if kinds.is_finish_crack(t) else "CR"
    if "박리" in t:
        return "scaling"
    if "박락" in t or "층분리" in t:
        return "spalling"
    if "누수" in t or "백태" in t or "백화" in t:
        return "leak"
    if "철근" in t:
        return "rebar"
    return None


def defect_grade(item: str, width, depth, area) -> tuple[str, str]:
    """결함 한 줄의 등급과 근거 글. 깊이·면적률이 없으면 b(결함은 있으나 가장 가벼운 등급, 사용자 10/13)."""
    w, d, a = _num(width), _num(depth), _num(area) or 0.0
    if item == "CR":
        if w is None:
            return "b", "폭 없음 → b"
        return rating.grade_crack(w, a), f"폭 {w}mm" + (f" · 면적률 {a}% ≥ 20 → 한 등급 내림" if a >= 20 else "")
    if item == "scaling":
        if d is None:
            return ("c" if a >= 10 else "b"), "깊이 없음 → b" + (" · 면적률 ≥ 10 → c" if a >= 10 else "")
        return rating.grade_scaling(d, a), f"깊이 {d}mm" + (f" · 면적률 {a}% ≥ 10 → 한 등급 내림" if a >= 10 else "")
    if item == "spalling":
        if d is None:
            return ("c" if a >= 20 else "b"), "깊이 없음 → b" + (" · 면적률 ≥ 20 → c" if a >= 20 else "")
        return rating.grade_spalling(d, a), f"깊이 {d}mm" + (f" · 면적률 {a}% ≥ 20 → 한 등급 내림" if a >= 20 else "")
    if item == "leak":
        if _num(area) is None:
            return "b", "면적률 없음 → b"
        return rating.grade_leak(a), f"면적률 {a}%"
    if item == "rebar":
        if _num(area) is None:
            return "b", "면적률 없음 → b"
        return rating.grade_rebar_exposure(a), f"면적률 {a}%"
    return "b", ""


# ---------- 집계 ----------

def _empty_counts() -> dict[str, int]:
    return {g: 0 for g in rating.GRADES}


def aggregate(defects: list, tests_view: dict, counts: dict, *, above: int, below: int, tilt_note: str = "", settlement_note: str = "") -> dict:
    """defects = SitokDefect 줄(결함현황표에 찍히는 것), tests_view = tests.compute() 결과, counts = {"-3": {"기둥": 48, …}} →
    {building(rating.Building), floors: [{floor, label, range, members: [{kind, total, items: {DS: {grade, rows}, CA, CR: {counts, grade}, SD: {sub: {…}, grade}}, defects: [...]}]}],
     excluded: [...], unassigned: [...]}."""
    sample = tests_view["sample"]["floors"]
    ranges = [(f["floor"], f["start"], f["end"], f) for f in sample if f.get("start") is not None and f.get("end") is not None]

    def sample_of(k: int | None):
        if k is None:
            return None
        for key, s, e, _ in ranges:
            if s <= k <= e:
                return key
        return None

    per: dict[int, dict[str, dict]] = {key: {} for key, *_ in ranges}  # 표본층 → 부재 → {item → counts/rows}
    used, excluded, unassigned = [], [], []
    for d in defects:
        info = {"id": d.id, "floor": d.floor, "seq": d.seq, "part": d.part, "member": d.member, "dtype": d.dtype, "count": d.count, "width": d.width,
                "depth": d.depth, "area_ratio": d.area_ratio}
        if not kinds.counts_for_rating(d.part, d.dtype):
            excluded.append({**info, "why": "비구조체" if d.part != "구조체" else "마감층 균열·기록·보수 완료"})
            continue
        item = defect_item(d.dtype)
        kind = member_kind(d.member)
        if item is None or kind is None:
            excluded.append({**info, "why": "상태평가 항목이 아님" if item is None else "구조 부재가 아님(조적벽·파라펫·계단·처마 등)"})
            continue
        key = sample_of(floor_key(d.floor))
        if key is None:
            unassigned.append({**info, "why": "표본층 범위 밖(옥상·옥탑 또는 범위 밖 층)"})
            continue
        g, why = defect_grade(item, d.width, d.depth, d.area_ratio)
        n = int(_num(d.count) or 1)
        slot = per[key].setdefault(kind, {})
        if item == "CR":
            c = slot.setdefault("CR", {"counts": _empty_counts(), "defects": []})
        else:
            c = slot.setdefault("SD", {}).setdefault(item, {"counts": _empty_counts(), "defects": []})
        c["counts"][g] += n
        c["defects"].append({**info, "grade": g, "why": why, "n": n})
        used.append(info["id"])

    def test_rows(section: str, key: int, kind: str) -> list[dict]:
        rows = []
        for r in tests_view[section]["rows"]:
            if r.get("floor") == key and member_kind(r.get("member")) == kind and r.get("grade"):
                rows.append(r)
        return rows

    def steel_rows(key: int, sub_kinds: tuple) -> list[dict]:
        """재료시험 규격 조사의 강재 줄(member 강재, sub 기둥/큰보/작은보)로 그 표본층 강재 규격 등급."""
        return [r for r in tests_view["sections"] if r.get("floor") == key and r.get("member") == "강재" and r.get("sub") in sub_kinds and r.get("grade")]

    out_floors = []
    members_for_eval = []
    for key, s, e, f in ranges:
        fl = {"floor": key, "label": f["label"], "range_label": f.get("range_label", ""), "structure": f.get("structure", "라멘"), "material": f.get("material", "RC"), "members": []}
        members = []
        for kind in MEMBERS:
            total = int(_num((counts.get(str(key)) or {}).get(kind)) or 0)
            slot = per.get(key, {}).get(kind, {})
            items: dict = {}
            ds = test_rows("strength", key, kind)
            if ds:
                items["DS"] = {"grade": rating.mean_grade([r["grade"] for r in ds]), "rows": ds}
            ca = test_rows("carbonation", key, kind)
            if ca:
                items["CA"] = {"grade": rating.mean_grade([r["grade"] for r in ca]), "rows": ca}
            if fl["material"] == "SRC":  # 철골+철콘: 같은 부재에 강재 규격 항목을 같이(Choquet RC 0.9·STL 0.9)
                ss = steel_rows(key, (kind,))
                if ss:
                    items["SS"] = {"grade": rating.mean_grade([r["grade"] for r in ss]), "rows": ss}
            cr = slot.get("CR")
            sd = slot.get("SD", {})
            if total > 0 or cr or sd:
                crc = dict(cr["counts"]) if cr else _empty_counts()
                crc["a"] = max(0, total - sum(v for g, v in crc.items() if g != "a"))
                items["CR"] = {"grade": rating.grade_from_counts(crc, kind), "counts": crc, "defects": cr["defects"] if cr else [], "total": total}
                sub = {}
                for name in SURFACE:
                    c = dict(sd[name]["counts"]) if name in sd else _empty_counts()
                    c["a"] = max(0, total - sum(v for g, v in c.items() if g != "a"))
                    sub[name] = {"grade": rating.grade_from_counts(c, kind), "counts": c, "defects": sd[name]["defects"] if name in sd else []}
                items["SD"] = {"grade": rating.worst(*[x["grade"] for x in sub.values()]), "sub": sub, "total": total}
            if not items:
                fl["members"].append({"kind": kind, "total": total, "items": {}, "skip": True})
                continue
            grades = {k: v["grade"] for k, v in items.items() if v.get("grade")}
            cond = rating.member_condition(grades)
            fl["members"].append({"kind": kind, "total": total, "items": items, "grades": grades, "score": cond["score"], "possibility": cond["possibility"], "skip": False})
            if cond["score"] is not None:
                members.append(rating.Member(kind, grades))
        if fl["material"] == "철골":  # 철골조: 강재기둥·강재보 — 규격 등급만(대푯값), 개수는 상태평가 화면에서
            for sk in STEEL_MEMBERS:
                total = int(_num((counts.get(str(key)) or {}).get(sk)) or 0)
                ss = steel_rows(key, tuple(k for k, v in STEEL_SUB.items() if v == sk))
                if not ss:
                    fl["members"].append({"kind": sk, "total": total, "items": {}, "skip": True})
                    continue
                grades = {"SS": rating.mean_grade([r["grade"] for r in ss])}
                cond = rating.member_condition(grades)
                fl["members"].append({"kind": sk, "total": total, "items": {"SS": {"grade": grades["SS"], "rows": ss}}, "grades": grades, "score": cond["score"],
                                      "possibility": cond["possibility"], "skip": False})
                members.append(rating.Member(sk, grades))
        out_floors.append(fl)
        members_for_eval.append(rating.Floor(f"{f['label']}({fl['range_label']})", key, members, structure=f"{fl['structure']}({fl['material']})"))
    tilt_g, sett_g = tests_view["tilt"]["grade"], tests_view["settlement"]["grade"]
    b = rating.Building(above=above or 0, below=below or 0, floors=members_for_eval, tilt=tilt_g, settlement=sett_g, kind="정밀점검")
    return {"building": b, "floors": out_floors, "excluded": excluded, "unassigned": unassigned, "used": used,
            "deform": {"tilt": tilt_g, "settlement": sett_g, "tilt_note": tilt_note, "settlement_note": settlement_note}}


def evaluate(agg: dict) -> dict | None:
    """rating.evaluate — 평가할 부재가 하나도 없으면 None."""
    b = agg["building"]
    if not any(f.members for f in b.floors):
        return None
    return rating.evaluate(b)


# ---------- 부록 "상태평가 결과 자료" PDF(SafetyMan 출력 모양) ----------

def _fmt(x) -> str:
    return "-" if x is None else f"{x:.2f}"


SM_CRACK = ("0.1mm미만의 균열발견", "0.2mm미만의 균열발견", "0.3mm미만의 균열발견", "0.5mm미만의 균열발견", "0.5mm이상의 균열발견")
SM_SCALING = ("발생없음", "0.5mm미만의 박리발생", "1.0mm미만의 박리발생", "2.5mm미만의 박리발생", "2.5mm이상의 박리발생")
SM_SPALLING = ("발생없음", "15mm미만의 박리발생", "20mm미만의 박리발생", "25mm미만의 박리발생", "25mm이상의 박리발생")
SM_LEAK = ("누수 및 백태발생 없음", "경미한 누수/백태발생면적 5%미만", "현저한 누수/백태발생면적 10%미만", "누수진행 관찰/백태발생면적 20%미만", "누수진행 확연/백태발생면적 20%이상")
SM_REBAR = ("노출발생없음", "노출발생면적율 1%미만", "노출발생면적율 3%미만", "노출발생면적율 5%미만", "노출발생면적율 5%이상")
RED = (0.85, 0.1, 0.1)
BLUE = (0.1, 0.2, 0.75)
HEAD_FILL = (0.96, 0.96, 0.85)  # SafetyMan 머리칸(연노랑)


def make_pdf(dest: Path, agg: dict, result: dict | None, building: dict, tests_view: dict, prev_grade: str = "") -> Path:
    """건축물 평가결과 — SafetyMan 출력(형 10/14 "상태평가결과 엑셀과 똑같은 양식, 지침이 SafetyMan 사용")과 같은 짜임:
    건물개요(한 열 이름·값) → 평가결과(층 묶음마다 부재 머리줄 + '상태' 줄, 오른쪽 '기울기 및 침하' 세로 칸, 종합·최종은 빨강) → 최종결과 →
    입력자료(층 묶음마다 콘크리트강도·균열·중성화·박리·박락·누수·철근노출·강재규격, SafetyMan 줄 이름·값 꼴 "24.2, 0, 0 / 24(D)") → 기울기 및 침하. A4 세로, pymupdf."""
    import pymupdf

    from server.sitok.album_make import FONT, FONT_B, M, W, _fonts, _scale

    doc = pymupdf.open()
    page = doc.new_page(width=W, height=841.68)
    _fonts(page)
    y = M
    PH = 841.68

    def newpage():
        nonlocal page, y
        page = doc.new_page(width=W, height=PH)
        _fonts(page)
        y = M

    def need(h):
        if y + h > PH - M:
            newpage()

    def text(x, yy, t, size=9, bold=False, color=(0, 0, 0)):
        page.insert_text((x, yy), t, fontname="mgb" if bold else "mg", fontsize=size, color=color)

    def cell(rect, t, size=7.5, bold=False, fill=None, color=(0, 0, 0), align="center"):
        if fill:
            page.draw_rect(rect, color=None, fill=fill)
        page.draw_rect(rect, color=(0.3, 0.3, 0.3), width=0.5)
        lines = str(t).split("\n")
        lh = size * 1.3
        yy = rect.y0 + (rect.height - lh * len(lines)) / 2 + size * 0.95
        f = pymupdf.Font(fontfile=FONT_B if bold else FONT)
        for ln in lines:
            sz = size
            tw = f.text_length(ln, fontsize=sz)
            while tw > rect.width - 3 and sz > 4:
                sz -= 0.3
                tw = f.text_length(ln, fontsize=sz)
            x = rect.x0 + 3 if align == "left" else rect.x0 + (rect.width - tw) / 2
            page.insert_text((x, yy), ln, fontname="mgb" if bold else "mg", fontsize=sz, color=color)
            yy += lh

    def title(t, size=14, gap=6):
        nonlocal y
        need(size + gap + 4)
        text(M, y + size, t, size, True)
        y += size + gap

    def grid(cols, rows, row_h=13, size=7.5, head=True, head_fill=HEAD_FILL):
        """cols = [(이름, 폭비)], rows = [[값 또는 (값, {bold, color, fill})…]] — 쪽이 모자라면 새 쪽(머리줄 다시)."""
        nonlocal y
        widths = _scale(cols, W - 2 * M)

        def head_row():
            nonlocal y
            x = M
            for name, w in widths:
                cell(pymupdf.Rect(x, y, x + w, y + row_h), name, size, True, head_fill)
                x += w
            y += row_h

        need(row_h * 2)
        if head:
            head_row()
        for row in rows:
            if y + row_h > PH - M:
                newpage()
                if head:
                    head_row()
            x = M
            for (name, w), val in zip(widths, row):
                opt = {}
                if isinstance(val, tuple):
                    val, opt = val
                cell(pymupdf.Rect(x, y, x + w, y + row_h), "" if val is None else str(val), size, opt.get("bold", False), opt.get("fill"), opt.get("color", (0, 0, 0)), opt.get("align", "center"))
                x += w
            y += row_h

    # ---- 건축물 평가결과 / 건물개요
    need(60)
    f = pymupdf.Font(fontfile=FONT_B)
    tw = f.text_length("건축물 평가결과", fontsize=17)
    text(M + (W - 2 * M - tw) / 2, y + 17, "건축물 평가결과", 17, True)
    y += 30
    title("건물개요", 13)
    bi = building
    pairs = [("건물명", bi.get("name", "")), ("소재지", bi.get("address", "")), ("준공년도", bi.get("completion", "")), ("주용도", bi.get("use", "")), ("구조형식", bi.get("structure", "")),
             ("소유주", bi.get("owner", "")), ("연락처", ""), ("관리주체", bi.get("owner", "")), ("연락처", ""),
             ("대지면적", bi.get("land_area") or "-"), ("건축면적", bi.get("building_area") or "-"), ("건축연면적", bi.get("total_area") or "-"), ("건폐율", "-"), ("용적율", "-"),
             ("지상", f"{bi.get('above', '')} 층"), ("지하", f"{bi.get('below', '')} 층")]
    lw, vw = (W - 2 * M) * 0.22, (W - 2 * M) * 0.78
    for k, v in pairs:
        need(13)
        cell(pymupdf.Rect(M, y, M + lw, y + 13), k, 8, False, None, align="left")
        cell(pymupdf.Rect(M + lw, y, M + lw + vw, y + 13), v, 8, False, None, align="left")
        y += 13
    half = (W - 2 * M) / 2
    for (k1, v1, k2, v2) in (("평가종류", "정밀점검", "평가기관", bi.get("company", "")), ("평가일시", bi.get("when", ""), "연락처", bi.get("phone", ""))):
        need(13)
        cell(pymupdf.Rect(M, y, M + lw, y + 13), k1, 8, align="left")
        cell(pymupdf.Rect(M + lw, y, M + half, y + 13), v1, 8, k1 == "평가종류", align="left")
        cell(pymupdf.Rect(M + half, y, M + half + lw * 0.8, y + 13), k2, 8)
        cell(pymupdf.Rect(M + half + lw * 0.8, y, W - M, y + 13), v2, 8, align="left")
        y += 13
    y += 12
    # ---- 평가결과
    title("평가결과", 13)
    floors = result["floors"] if result else []
    deform = result["deform"] if result and result.get("deform") else None
    total_w = W - 2 * M
    c_floor, c_def = total_w * 0.17, total_w * 0.11
    c_mid = total_w - c_floor - c_def
    c_lab = c_mid * 0.09
    c_mem = (c_mid - c_lab) / (len(MEMBERS) + 1)
    rh = 14
    need(rh * (2 + 2 * max(len(floors), 1)) + 4)
    cell(pymupdf.Rect(M, y, M + c_floor, y + rh * 2), "층", 9, True, HEAD_FILL)
    cell(pymupdf.Rect(M + c_floor, y, M + c_floor + c_mid, y + rh * 2), "안전성 / 상태", 9, True, HEAD_FILL)
    cell(pymupdf.Rect(M + c_floor + c_mid, y, W - M, y + rh * 2), "기울기\n및 침하", 9, True, HEAD_FILL)
    y += rh * 2
    body_top = y
    for fl in floors:
        scores = {m["kind"]: m["condition"] for m in fl["members"]}
        cell(pymupdf.Rect(M, y, M + c_floor, y + rh * 2), f"{fl['label'].split('(')[0]}\n({fl.get('g') or fl['label'].split('(')[-1].rstrip(')')})\n{fl.get('structure', '')}", 7.5)
        x = M + c_floor
        cell(pymupdf.Rect(x, y, x + c_lab, y + rh), "", 7.5)
        xx = x + c_lab
        for k in MEMBERS:
            cell(pymupdf.Rect(xx, y, xx + c_mem, y + rh), k, 7.5, True)
            xx += c_mem
        cell(pymupdf.Rect(xx, y, xx + c_mem, y + rh), "종합", 7.5, True)
        cell(pymupdf.Rect(x, y + rh, x + c_lab, y + rh * 2), "상태", 7.5, False, None, BLUE)
        xx = x + c_lab
        for k in MEMBERS:
            v = scores.get(k)
            cell(pymupdf.Rect(xx, y + rh, xx + c_mem, y + rh * 2), "-" if v is None else (f"{v:g}" if abs(v - round(v)) < 1e-9 else f"{v:.2f}"), 7.5)
            xx += c_mem
        cell(pymupdf.Rect(xx, y + rh, xx + c_mem, y + rh * 2), f"{fl['condition']:.2f}({rating.grade_of(fl['condition'])})" if fl["condition"] is not None else "-", 7.5, False, None, RED)
        y += rh * 2
    if not floors:
        cell(pymupdf.Rect(M, y, M + c_floor + c_mid, y + rh), "평가할 부재 없음", 7.5)
        y += rh
    cell(pymupdf.Rect(M + c_floor + c_mid, body_top, W - M, y), f"{deform['score']:.2f}({deform['grade']})" if deform else "-", 8, False, None, RED)
    steel_lines = [f"{fl['label'].split('(')[0]} {m['kind']} {m['condition']:.2f}({rating.grade_of(m['condition'])})"
                   for fl in floors for m in fl["members"] if m["kind"] in STEEL_MEMBERS and m["condition"] is not None]
    if steel_lines:
        cell(pymupdf.Rect(M, y, M + c_floor, y + rh), "강재 부재", 7.5, True, HEAD_FILL)
        cell(pymupdf.Rect(M + c_floor, y, W - M, y + rh), " · ".join(steel_lines), 7.5, False, None, RED)
        y += rh
    y += 4
    if result:
        lines = [f"상태평가: {result['condition']['score']:.2f}({result['condition']['grade']}등급)" if result.get("condition") else "상태평가: -",
                 f"종합평가: {result['total']['score']:.2f}({result['total']['grade']}등급)" if result.get("total") else "종합평가: -"]
        cell(pymupdf.Rect(M, y, M + c_floor, y + rh * 2), "최종결과", 9, True, HEAD_FILL)
        cell(pymupdf.Rect(M + c_floor, y, W - M, y + rh * 2), "\n".join(lines), 8.5, False, None, RED)
        y += rh * 2
    # ---- 입력자료
    y += 14
    title("입력자료", 13)
    for fl in agg["floors"]:
        need(60)
        title(f"{fl['label']}[{fl['range_label']}]{fl['structure']}({fl['material']})", 10, 4)
        mem = {m["kind"]: m for m in fl["members"]}

        def label_row(t):
            nonlocal y
            need(14)
            cell(pymupdf.Rect(M, y, W - M, y + 13), t, 8, True, None, align="left")
            y += 13

        def item_rows(item, key_rows, sub=None, area_rows=()):
            out = []
            for i, name in enumerate(key_rows):
                g = rating.GRADES[i]
                row = [("균열폭" if item == "CR" else "발생정도") if i == 0 else "", name]
                for k in MEMBERS:
                    m = mem.get(k)
                    it = (m or {}).get("items", {}).get(item)
                    if sub and it:
                        it = it["sub"].get(sub)
                    row.append("" if not it else (it["counts"][g] or ""))
                out.append(row)
            for j, name in enumerate(area_rows):  # 면적율 줄 — 전부 기준 미만(우리는 면적률 20% 미만 등급만 셈)
                row = ["면적율" if j == 0 else "", name]
                for k in MEMBERS:
                    m = mem.get(k)
                    it = (m or {}).get("items", {}).get(item)
                    if sub and it:
                        it = it["sub"].get(sub)
                    row.append((it.get("total") or sum(it["counts"].values()) or "") if it and j == 0 else "")
                out.append(row)
            return out

        cols7 = [("평가부재", 1.3)] + [(k, 1) for k in MEMBERS]
        for item, label, fmt in (("DS", "콘크리트강도(측정강도, 0, 0 / 설계강도:MPa)", lambda r: f"{r.get('est')}, 0, 0 / {r.get('design')}" + ("(D)" if r.get("damaged") else "")),
                                 ("CA", "콘크리트중성화(중성화깊이, 0, 0 / 피복두께:mm)", lambda r: f"{r.get('depth')}, 0, 0 / {r.get('cover')}")):
            maxn = max((len((mem[k].get("items", {}).get(item) or {}).get("rows", [])) for k in MEMBERS if k in mem), default=0)
            if not maxn:
                continue
            label_row(label)
            rows = []
            for i in range(maxn):
                row = [f"평가부재{i + 1}"]
                for k in MEMBERS:
                    rs = (mem.get(k, {}).get("items", {}).get(item) or {}).get("rows", [])
                    row.append(fmt(rs[i]) if i < len(rs) else "")
                rows.append(row)
            grid(cols7, rows, row_h=13, size=7)
            y += 5
        ss_rows = [(k, r) for k in (*MEMBERS, *STEEL_MEMBERS) for r in ((mem.get(k) or {}).get("items", {}).get("SS") or {}).get("rows", [])]
        if ss_rows:
            label_row("강재규격(측정값/설계값:mm²)")
            grid([("평가부재", 1.3), ("부재", 1), ("기호", 1), ("설계 규격", 1.4), ("측정 규격", 1.4), ("측정값/설계값(mm²)", 1.4), ("등급", 0.7)],
                 [[f"평가부재{i + 1}", k, r.get("position") or "-", r.get("design") or "-", r.get("measured") or "-",
                   (f"{r['area_measured'] * 100:.0f} / {r['area_design'] * 100:.0f}" if r.get("area_measured") and r.get("area_design") else "-"), (r.get("grade") or "-").upper()]
                  for i, (k, r) in enumerate(ss_rows)], row_h=13, size=7)
            y += 5
        cols9 = [("평가내용", 0.7), ("", 2.2)] + [(k, 1) for k in MEMBERS]
        for label, item, krows, sub, area in (("콘크리트균열", "CR", SM_CRACK, None, ("면적율 20% 미만", "면적율 20% 이상")),
                                               ("박리", "SD", SM_SCALING, "scaling", ("면적율 10% 미만", "면적율 10% 이상")),
                                               ("박락 · 층분리", "SD", SM_SPALLING, "spalling", ("면적율 20% 미만", "면적율 20% 이상")),
                                               ("누수 · 백태", "SD", SM_LEAK, "leak", ()), ("철근노출", "SD", SM_REBAR, "rebar", ())):
            label_row(label)
            grid(cols9, item_rows(item, krows, sub, area), row_h=12, size=6.8)
            y += 5
        y += 6
    need(60)
    title("기울기 및 침하", 10, 4)
    de = agg["deform"]
    tv = tests_view
    grid([("평가내용", 1), ("각변위", 1.3), ("상태", 2.8)], [
        ["기울기", f"1/{tv['tilt']['range']['min_n']:,} ~ 1/{tv['tilt']['range']['max_n']:,}" if tv["tilt"]["range"]["min_n"] else "-", f"{(de['tilt'] or '-').upper()} {de['tilt_note']}"],
        ["부동침하", f"{tv['settlement']['range']['min_disp']}~{tv['settlement']['range']['max_disp']}mm" if tv["settlement"]["range"]["max_disp"] is not None else "-",
         f"{(de['settlement'] or '-').upper()} {de['settlement_note']}"]], row_h=14)
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.subset_fonts()
    doc.save(str(dest), garbage=3, deflate=True)
    doc.close()
    return dest


def _selfcheck() -> None:
    assert member_kind("기둥(C5)") == "기둥" and member_kind("보 단부") == "큰보" and member_kind("슬라브 중앙부") == "슬래브" and member_kind("내력벽(W5)") == "내력벽"
    assert member_kind("작은보") == "작은보" and member_kind("조적벽") == "내력벽" and member_kind("파라펫") is None and member_kind("보(B1)") == "큰보"
    assert floor_key("지하1층") == -1 and floor_key("지상2층") == 2 and floor_key("옥상층") is None and floor_key("3층") == 3
    assert defect_item("미장균열") is None and defect_item("균열") == "CR" and defect_item("박락") == "spalling" and defect_item("누수·백태") == "leak"
    assert defect_grade("CR", "0.1", None, "3")[0] == "b" and defect_grade("CR", "0.3", None, "25")[0] == "e" and defect_grade("scaling", None, None, None)[0] == "b"
    assert defect_grade("spalling", None, "20", "5")[0] == "d" and defect_grade("leak", None, None, "7")[0] == "c"
    print("상태평가 집계 검증 통과")


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    _selfcheck()
