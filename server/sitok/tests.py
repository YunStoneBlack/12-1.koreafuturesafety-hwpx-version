"""시특법 정밀안전점검 재료시험(2026-10-13 밤, ② 단계) — 회차 tests JSON(입력)을 받아 등급·계산값을 붙인 보기(view)를 만든다.

입력(사용자가 적는 것)과 계산(우리가 붙이는 것)을 나눠 둔다. 저장은 입력만, 화면·보고서는 compute()가 돌려주는 값을 쓴다.
계산식은 다산은혜교회 26년 상반기 정밀안전점검 보고서(4장 재료시험·부록 성과표)와 맞춤:
- 표본층 수 = 지침 표 6.19·6.20(rating.sample_floors), 수량 = 층 × 2부재 × (강도 2·규격 3·탄산화 1)(rating.sample_quantities), 기울기 4면, 부등침하 X·Y 2개소.
- 표본층 범위: 요원이 층만 고르면 자동 분할(사용자 10/13) — 두 표본층 사이 가운데, 지하/지상 경계가 사이에 있으면 거기서(다산 -3~-1 / 1~5). 고칠 수 있음.
- 부재 규격: "300×600"·"300" → 면적(두께) 비율 → rating.grade_section, 100% 이상이면 "O.K".
- 강도: 슈미트 추정강도(MPa) ÷ 설계기준강도 → rating.grade_strength(건전부/손상).
- 탄산화(mm, 경과년수 t = 준공 ~ 점검): 잔여 = 피복 − 깊이, 속도계수 A = 깊이/√t, 이론치 = R·(4.6·(W/C) − 1.76)/√7.2 · √t (cm → mm; 기시타니 식, 다산 4.37mm),
  잔존수명 = (피복/A)² − t(100년 넘으면 "100년 이상", 다산 C1 80.7년), 등급 = rating.grade_carbonation(깊이/피복).
- 기울기: 1/N, N = 측정높이 ÷ 변위량 → rating.grade_tilt. 부등침하: 구간(측점 3개 이상·거리는 측점 − 1) → 변위 = 앞 측점 − 뒤 측점, N = 거리 ÷ |변위|.
10/14 형 피드백(작업내용 46차): 부재는 선택(기둥·큰보·작은보·슬래브·벽체) + 강도는 부위(중앙부·단부) 따로, 표본층을 고르면 기준 수량만큼 기본 줄을 자동으로
(sync_defaults — 모자란 줄만, 값 있는 줄은 안 지움), 기울기 8줄(모서리 4 × X·Y)·부등침하 4구간(X1·X2·Y1·Y2)은 비었을 때 한 번, 구조 일람표 도면 → 설계 치수(schedule_fill).
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
MEMBERS = ("기둥", "큰보", "작은보", "슬래브", "벽체", "강재")  # 선택 칸(10/14 형) — 치수는 기둥·보 가로×세로, 슬래브·벽체 두께, 강재 H형강 규격(단면적 비교, 표 6.36)
# KS D 3503 H형강 필릿 반지름 r(mm) — (H 계열, B)별. 단면적 = 2·B·t2 + (H−2·t2)·t1 + (4−π)·r² (형이 보낸 표 값과 일치: 100×100 21.90, 200×200 63.53, 300×300 119.8, 588×300 192.5)
H_FILLET = {(100, 50): 8, (100, 100): 10, (125, 60): 8, (125, 125): 10, (150, 75): 8, (150, 100): 11, (150, 150): 11, (175, 90): 9, (175, 175): 12, (200, 100): 11, (200, 150): 11,
            (200, 200): 13, (250, 125): 12, (250, 175): 13, (250, 250): 16, (300, 150): 13, (300, 200): 13, (300, 300): 18, (350, 175): 14, (350, 250): 16, (350, 350): 20,
            (400, 200): 16, (400, 300): 20, (400, 400): 22, (450, 200): 18, (450, 300): 22, (500, 200): 20, (500, 300): 22, (600, 200): 22, (600, 300): 28, (700, 300): 28,
            (800, 300): 28, (900, 300): 28}
SPOTS = ("중앙부", "단부")
THICK_MEMBERS = ("슬래브", "벽체")
DEFAULT_STRENGTH = (("기둥", "중앙부"), ("기둥", "단부"), ("큰보", "중앙부"), ("큰보", "단부"))  # 층마다 2부재 × 2개소
DEFAULT_SECTION = ("기둥",) * 3 + ("큰보",) * 3  # 층마다 2부재 × 3개소
MATCH = ("일치", "일부 일치", "불일치")  # 조사결과(10/29 — 내진 부재 단면과 같게, 예전 "다름" = 불일치). 못 잰 변은 "□"(비율·평가 안 냄)
SCHED_KIND = {"기둥": "기둥", "큰보": "보", "작은보": "보", "벽체": "벽체"}  # 구조 일람표 부재 목록(rebar_schedule) 종류 — 슬래브·강재는 목록 없음
DEFAULT_CARB = ("기둥", "큰보")  # 층마다 2부재 × 1개소
TILT_LABELS = tuple(f"모서리{i} {ax}" for i in (1, 2, 3, 4) for ax in ("X", "Y"))  # 기본 8줄
SETT_DEFAULT = (("X", 1), ("X", 2), ("Y", 1), ("Y", 2))  # 기본 4구간


def member_of(text: str) -> str:
    """옛 글자("기둥 중앙부"·"보 단부"·"기둥(C5)"·"내력벽") → 선택 값. 모르면 그대로."""
    t = (text or "").replace(" ", "")
    if t in MEMBERS:
        return t
    for key, m in (("작은보", "작은보"), ("기둥", "기둥"), ("슬라브", "슬래브"), ("슬래브", "슬래브"), ("바닥", "슬래브"), ("벽", "벽체"), ("보", "큰보")):
        if key in t:
            return m
    return (text or "").strip()


def spot_of(text: str) -> str:
    t = (text or "").replace(" ", "")
    return "중앙부" if "중앙" in t else "단부" if "단부" in t else ""


def member_text(r: dict) -> str:
    """보고서·상태평가에 쓰는 글자 — "기둥 중앙부"."""
    return " ".join(x for x in (r.get("member") or "", r.get("spot") or "") if x)


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


def steel_area(s: str) -> float | None:
    """강재 규격 글자 → 단면적 cm²(표엔 글자 그대로, 상태평가 비교에만 씀 — 형 10/14 "H-100×100×6×8 이런 식으로 써져야").
    H형강 "H-400×200×8×13"(숫자 4개, KS 필릿 반지름 표) / 앵글(L형강) "L-100×100×7"·"ㄱ-90×90×7"(숫자 3개 a×b×t, KS 등변·부등변 어림:
    t(a+b-t) + 필릿 0.107t²) / 숫자 하나면 단면적 직접(cm²). 그 밖(두께 없는 "100×100" 등)은 None."""
    raw = str(s or "").strip().upper().replace(" ", "")
    angle = raw.startswith(("L-", "L", "ㄱ-", "ㄱ"))
    t = raw.replace("H-", "").replace("H", "").replace("L-", "").replace("L", "").replace("ㄱ-", "").replace("ㄱ", "")
    nums = [_f(p) for p in re.split(r"[×XÅ*]", t) if p.strip()]
    if len(nums) == 1 and nums[0]:
        return nums[0]
    if len(nums) == 3 and all(n for n in nums) and (angle or True):  # 숫자 3개는 앵글(a×b×t)
        a, b, tt = nums
        return round((tt * (a + b - tt) + 0.107 * tt * tt) / 100, 2)
    if len(nums) != 4 or any(n is None for n in nums):
        return None
    h, b, t1, t2 = nums
    hs = min(H_FILLET, key=lambda k: (abs(k[0] - h) + abs(k[1] - b) * 0.5)) if H_FILLET else None
    r = H_FILLET.get(hs, 13) if hs and abs(hs[0] - h) <= 30 and abs(hs[1] - b) <= 30 else 13
    return round((2 * b * t2 + (h - 2 * t2) * t1 + (4 - math.pi) * r * r) / 100, 2)


def _dims(s: str) -> float | None:
    """"300×600" → 180000, "300" → 300(두께·폭 하나). ×·x·X·* 다 됨."""
    parts = re.split(r"[×xX*]", str(s or ""))
    if len(parts) > 1 and any(not p.strip() for p in parts):  # 한 변이 빈 "×600"(못 잰 변 □를 지운 뒤 등)은 비교 안 함(10/29)
        return None
    nums = [_f(p) for p in parts if p.strip()]
    if not nums or any(n is None for n in nums):
        return None
    return math.prod(nums)


def ratio_text(n: float | None) -> str:
    return f"1/{int(round(n)):,}" if n and n > 0 else "-"


# ---------- 항목 계산 ----------

def section_row(r: dict) -> dict:
    steel = r.get("member") == "강재"
    d, m = (steel_area(r.get("design")), steel_area(r.get("measured"))) if steel else (_dims(r.get("design")), _dims(r.get("measured")))
    r = {**r, "thick": r.get("member") in THICK_MEMBERS, "steel": steel, "area_design": d if steel else None, "area_measured": m if steel else None}
    out = {**r, "ratio": None, "grade": None, "ok": None}
    if d and m is not None:
        out["ratio"] = round(m / d * 100, 1)
        out["grade"] = rating.grade_section(m, d)
        out["ok"] = m >= d
    return out


def strength_row(r: dict) -> dict:
    est, design = _f(r.get("est")), _f(r.get("design"))
    out = {**r, "member_text": member_text(r), "ratio": None, "grade": None}
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
    return {"sample": {"floors": []}, "sections": [], "section_plan": {}, "strength": {"rows": [], "file": ""},
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
    secs = []
    for r in raw.get("sections") or []:
        design, measured = _dim_text(r.get("design")), _dim_text(r.get("measured"))
        same = bool(r.get("same")) if "same" in r else (bool(design) and design == measured)
        match = r.get("match") if r.get("match") in MATCH else ("일치" if same else "불일치")  # 10/29 일부 일치(한 변만 다름)
        same = match == "일치"
        if same:
            measured = design  # 조사결과 "일치" → 설계값 그대로(10/14 형)
        member = member_of(r.get("member"))
        sub = (r.get("sub") if r.get("sub") in ("기둥", "큰보", "작은보") else "기둥") if member == "강재" else ""  # 강재 줄: 어느 부재인지(상태평가 철골조 기둥·큰보·작은보, 10/15 SafetyMan 강재 표)
        secs.append({"floor": _i(r.get("floor")), "position": str(r.get("position") or "").strip(), "member": member,
                     "design": design, "measured": measured, "same": same, "match": match, "sub": sub,
                     "item_id": str(r.get("item_id") or "").strip()[:40]})  # 고른 구조 일람표 칸(10/29)
    base["sections"] = secs
    plan = {}
    for k, v in (raw.get("section_plan") or {}).items() if isinstance(raw.get("section_plan"), dict) else []:  # 칸 수 표 {"층|부재": n}(10/29)
        fl, _, m = str(k).partition("|")
        n = _i(v)
        if _i(fl) not in (None, 0) and m in MEMBERS and n is not None:
            plan[f"{_i(fl)}|{m}"] = max(0, min(40, n))
    base["section_plan"] = plan
    st = raw.get("strength") or {}
    base["strength"] = {"file": str(st.get("file") or ""), "rows": [
        {"floor": _i(r.get("floor")), "member": member_of(r.get("member")), "spot": spot_of(r.get("member")) or (r.get("spot") if r.get("spot") in SPOTS else ""),
         "position": str(r.get("position") or "").strip(),
         "r0": _f(r.get("r0")), "fc_mat": _f(r.get("fc_mat")), "fc_arch": _f(r.get("fc_arch")), "est": _f(r.get("est")), "design": _f(r.get("design")),
         "damaged": bool(r.get("damaged")), "note": str(r.get("note") or "").strip()} for r in st.get("rows") or []]}
    ca = raw.get("carbonation") or {}
    base["carbonation"] = {"wc": _f(ca.get("wc")) or DEFAULT_WC, "ratio": _f(ca.get("ratio")) or DEFAULT_R, "rows": [
        {"floor": _i(r.get("floor")), "member": member_of(r.get("member")), "position": str(r.get("position") or "").strip(),
         "cover": _f(r.get("cover")), "depth": _f(r.get("depth")), "photo": str(r.get("photo") or "").strip()} for r in ca.get("rows") or []]}  # photo = 부록 3-1 사진현황(10/14)
    ti = raw.get("tilt") or {}
    base["tilt"] = {"note": str(ti.get("note") or ""), "rows": [
        {"label": str(r.get("label") or "").strip(), "height": _f(r.get("height")), "direction": r.get("direction") if r.get("direction") in TILT_DIRS else "",
         "disp": _f(r.get("disp"))} for r in ti.get("rows") or []]}
    se = raw.get("settlement") or {}
    base["settlement"] = {"floor": _i(se.get("floor")), "note": str(se.get("note") or ""), "sections": [
        {"axis": "Y" if str(sec.get("axis") or "").upper() == "Y" else "X", "no": _i(sec.get("no")) or 1,
         "levels": [_f(v) for v in sec.get("levels") or []], "distances": [_f(v) for v in sec.get("distances") or []]} for sec in se.get("sections") or []]}
    for sec in base["settlement"]["sections"]:
        if len(sec["levels"]) < 2:
            sec["levels"] += [None] * (2 - len(sec["levels"]))
        sec["distances"] = (sec["distances"] + [None] * len(sec["levels"]))[:len(sec["levels"]) - 1]
    return base


def _dim_text(v) -> str:
    """치수 글자 정리 — "300x600"·"300*600"·"300 × 600" → "300×600"."""
    s = str(v or "").strip().replace("x", "×").replace("X", "×").replace("*", "×").replace(" ", "")
    return s


# ---------- 기본 줄(10/14 형 피드백) ----------

def _section_empty(r: dict) -> bool:
    return not (r.get("design") or r.get("measured") or r.get("position"))


def _strength_empty(r: dict) -> bool:
    return r.get("est") is None and r.get("r0") is None and not r.get("position")


def _carb_empty(r: dict) -> bool:
    return r.get("cover") is None and r.get("depth") is None and not r.get("photo")


def _sync_rows(rows: list[dict], floors: list[int], combos: tuple, keyf, is_empty, make) -> list[dict]:
    """표본층마다 기준 수량(combos 수)만큼 — 모자라면 없는 조합부터 더하고, 표본층에서 빠진 층의 빈 줄은 뺌. 값 있는 줄은 안 건드림."""
    rows = [r for r in rows if not (r.get("floor") is not None and r["floor"] not in floors and is_empty(r))]
    for k in floors:
        mine = [r for r in rows if r.get("floor") == k]
        if len(mine) >= len(combos):
            continue
        have = {}
        for r in mine:
            have[keyf(r)] = have.get(keyf(r), 0) + 1
        for c in combos:
            if len(mine) >= len(combos):
                break
            if have.get(c, 0) > 0:
                have[c] -= 1
                continue
            row = make(k, c)
            rows.append(row)
            mine.append(row)
    order = {k: i for i, k in enumerate(floors)}
    rows.sort(key=lambda r: order.get(r.get("floor"), len(order)))  # 층 순서로(안정 정렬 — 같은 층 안 순서는 그대로)
    return rows


def _blank_section(k: int, m: str) -> dict:
    return {"floor": k, "position": "", "member": m, "design": "", "measured": "", "same": True, "match": "일치", "sub": "", "item_id": ""}


def sync_sections(rows: list[dict], floors: list[int], plan: dict) -> tuple[list[dict], dict]:
    """부재 규격 줄 맞추기(10/29 — 내진 부재 단면처럼 칸 수 표) → (줄, 칸 수 {"층|부재": n}).
    칸 수 표에 그 층이 있으면 그 수대로(모자라면 빈 칸 더하고, 넘치면 빈 칸만 뺌 — 값 있는 칸은 안 지움, 표에 없는 부재는 지금 수 그대로),
    없으면 예전처럼 기준(기둥 3·큰보 3)에서 모자란 것만. 표본층에서 빠진 층의 빈 줄은 뺌."""
    rows = [r for r in rows if not (r.get("floor") is not None and r["floor"] not in floors and _section_empty(r))]
    for k in floors:
        keys = {key.split("|", 1)[1]: n for key, n in plan.items() if key.split("|", 1)[0] == str(k)}
        if not keys:
            mine = [r for r in rows if r.get("floor") == k]
            if len(mine) < len(DEFAULT_SECTION):
                have = {}
                for r in mine:
                    have[r.get("member")] = have.get(r.get("member"), 0) + 1
                for m in DEFAULT_SECTION:
                    if len(mine) >= len(DEFAULT_SECTION):
                        break
                    if have.get(m, 0) > 0:
                        have[m] -= 1
                        continue
                    row = _blank_section(k, m)
                    rows.append(row)
                    mine.append(row)
            continue
        for m, want in keys.items():
            idx = [i for i, r in enumerate(rows) if r.get("floor") == k and r.get("member") == m]
            want = max(want, sum(1 for i in idx if not _section_empty(rows[i])))
            drop = []
            for i in reversed(idx):
                if len(idx) - len(drop) <= want:
                    break
                if _section_empty(rows[i]):
                    drop.append(i)
            rows = [r for i, r in enumerate(rows) if i not in drop]
            cur = [i for i, r in enumerate(rows) if r.get("floor") == k and r.get("member") == m]
            at = (cur[-1] + 1) if cur else (max([i for i, r in enumerate(rows) if r.get("floor") == k], default=len(rows) - 1) + 1)
            for _ in range(want - len(cur)):
                rows.insert(at, _blank_section(k, m))
                at += 1
    order = {k: i for i, k in enumerate(floors)}
    rows.sort(key=lambda r: order.get(r.get("floor"), len(order)))  # 층 순서로(같은 층 안 차례는 그대로)
    eff = {}
    for k in floors:
        for m in MEMBERS:
            c = sum(1 for r in rows if r.get("floor") == k and r.get("member") == m)
            if c or plan.get(f"{k}|{m}") == 0:
                eff[f"{k}|{m}"] = c
        if not any(key.startswith(f"{k}|") for key in eff):
            eff[f"{k}|기둥"] = 0  # 그 층은 칸 수 표대로(다시 기본으로 채우지 않게)
    return rows, eff


def section_plan_default(floors: list[int]) -> dict:
    """[기본 칸 수로] — 표본층마다 기둥 3·큰보 3, 나머지 0(값 있는 칸은 그대로 남음)."""
    return {f"{k}|{m}": DEFAULT_SECTION.count(m) for k in floors for m in MEMBERS}


def fill_from_items(data: dict, items: dict, above: int | None) -> int:
    """고른 일람표 칸(item_id) → 빈 설계 칸·위치 칸 채우기(화면도 채우지만 서버에서 한 번 더). 보는 위층 바닥보 부호(10/29). 돌려주는 값 = 채운 줄 수."""
    from server.sitok import rebar_schedule as RS

    n = 0
    for r in data["sections"]:
        it = items.get(r.get("item_id") or "")
        if it is None:
            continue
        if not r.get("design"):
            d = _dim_text(it.get("size")) if r.get("member") not in THICK_MEMBERS else str(it.get("thickness") or "")
            if d:
                r["design"] = d
                if r.get("same"):
                    r["measured"] = d
                n += 1
        if not r.get("position"):
            mk = RS.marks_for(it, r.get("floor"), above) or it.get("marks") or []
            if mk:
                r["position"] = mk[0]
    return n


def sync_defaults(data: dict) -> bool:
    """표본층에 맞춰 규격·강도·탄산화 기본 줄, 기울기 8줄·부등침하 4구간(비었을 때만). 바뀌었으면 True."""
    before = repr(data)
    floors = [f["floor"] for f in data["sample"]["floors"]]
    if floors:
        data["sections"], eff = sync_sections(data["sections"], floors, data.get("section_plan") or {})
        if data.get("section_plan"):  # 칸 수 표를 쓴 회차만 저장(예전 회차는 열기만 해선 안 바뀜)
            data["section_plan"] = eff
        data["strength"]["rows"] = _sync_rows(data["strength"]["rows"], floors, DEFAULT_STRENGTH, lambda r: (r.get("member"), r.get("spot")), _strength_empty,
                                              lambda k, c: {"floor": k, "member": c[0], "spot": c[1], "position": "", "r0": None, "fc_mat": None, "fc_arch": None,
                                                            "est": None, "design": None, "damaged": False, "note": "건전부"})
        data["carbonation"]["rows"] = _sync_rows(data["carbonation"]["rows"], floors, DEFAULT_CARB, lambda r: r.get("member"), _carb_empty,
                                                 lambda k, m: {"floor": k, "member": m, "position": "", "cover": None, "depth": None, "photo": ""})
        for st in data["strength"]["rows"]:
            if st["design"] is None:
                st["design"] = next((x["design"] for x in data["strength"]["rows"] if x["design"] is not None), None)  # 설계기준강도는 한 건물에 보통 하나
    if not data["tilt"]["rows"]:
        data["tilt"]["rows"] = [{"label": lb, "height": None, "direction": "", "disp": None} for lb in TILT_LABELS]
    if not data["settlement"]["sections"]:
        data["settlement"]["sections"] = [{"axis": ax, "no": no, "levels": [None, None, None], "distances": [None, None]} for ax, no in SETT_DEFAULT]
    return repr(data) != before


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
                                "carbonation": {"need": qty["carbonation"], "have": len(carb)}, "tilt": {"need": 8, "have": len(tilt)},
                                "settlement": {"need": 4, "have": len(sett)}}},
        "sections": sections, "sections_grade": _worst(r["grade"] for r in sections),
        "section_plan": sync_sections([dict(r) for r in data["sections"]], [f["floor"] for f in floors], data.get("section_plan") or {})[1],
        "section_plan_default": section_plan_default([f["floor"] for f in floors]), "section_plan_on": bool(data.get("section_plan")),
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
        for m, sp in DEFAULT_STRENGTH:
            rows.append({"floor": f["floor"], "member": m, "spot": sp, "position": "", "r0": None, "fc_mat": None, "fc_arch": None, "est": None, "design": None,
                         "damaged": False, "note": "건전부"})
    return rows


def spots_to_rows(spots: list, floors: list[dict], existing: list[dict]) -> list[dict]:
    """슈미트 성과표 위치들 → 강도 줄. 기존 줄이 있으면 순서대로 값만 채우고(층·부재·설계강도는 남김), 모자라면 표본층 순서로 기본 부재부위를 붙임."""
    rows = [dict(r) for r in existing]
    defaults = default_strength_rows(floors)
    for i, s in enumerate(spots):
        if i >= len(rows):
            rows.append(defaults[i] if i < len(defaults) else {"floor": floors[-1]["floor"] if floors else None, "member": "", "spot": "", "position": "",
                                                                 "design": None, "damaged": False, "note": "건전부"})
        r1 = lambda v: round(v, 1) if v is not None else None  # noqa: E731 — 보고서 표는 소수 1자리
        rows[i].update({"position": s.position, "r0": r1(s.r0), "fc_mat": r1(s.est_mat), "fc_arch": r1(s.est_arch), "est": r1(s.est)})
        hint = f"{s.position} {s.note}"  # 위치 글자에 기둥/보/중앙부/단부가 있으면 그대로(10/14 결정 ⑨), 없으면 줄 순서대로
        if member_of(hint) in MEMBERS and any(k in hint for k in ("기둥", "보", "슬래브", "슬라브", "벽")):
            rows[i]["member"] = member_of(hint)
        if spot_of(hint):
            rows[i]["spot"] = spot_of(hint)
        if s.note and not rows[i].get("note"):
            rows[i]["note"] = s.note
    return rows


SCHEDULE_PROMPT = """아래 그림(과 글자)은 건축 구조도면의 구조 일람표(기둥·보·슬래브·벽체 단면 치수표)입니다.
{facility} 건물의 재료시험 "부재 규격 조사"에 넣을 설계 치수를 찾아 주세요.
찾을 줄(번호 · 층 · 부재 · 기호):
{rows}

규칙: 기둥·큰보·작은보는 "가로×세로"(mm, 예 500×600 — 기둥은 b×h, 보는 b×D), 슬래브·벽체는 두께 "150"처럼 숫자만, 강재는 H형강 규격 "H-400×200×8×13"(H×B×t1×t2).
기호가 적힌 줄은 **그 기호**의 치수를 그 층(구간)에서 찾으세요(일람표가 층 구간별로 다르면 그 층 구간 값; 기호가 "C1"이면 "C1, C2"처럼 묶인 칸이나 "-2~2TC1"처럼 층 접두가 붙은 부호도 같은 것). 기호가 없는 줄은
그 층(또는 괄호의 대표 범위)에 쓰이는 부재 중 가장 많이 쓰이는 대표 부재(일반 부재 — "1개소"·"계단실" 같은 특수 부재 말고)의 치수를 넣고, 부재 기호(C1·G2·S1·W1 등)를 같이 적어 주세요.
표의 적용 층 구간에 그 층이 글자 그대로 없으면 대표 범위가 겹치는 구간, 그것도 없으면 가장 가까운 구간의 치수를 쓰세요(보·슬래브는 그 층의 천장 = 윗층 바닥 구조라 한 층 어긋나는 게 보통). 그 부재 종류 자체가 표에 없을 때만 "".
기호가 적힌 줄의 기호가 일람표에 없으면 design을 ""로 두고 "missing": true. 표에 "상동"은 윗줄(윗층)과 같다는 뜻입니다.
JSON 배열만 답하세요: [{{"no": 1, "design": "500×600", "mark": "C1"}}, …]
{text}"""


def schedule_fill(data: dict, facility: str, company_id: int, text: str, imgs: list[bytes]) -> int:
    """구조 일람표 도면(글자·쪽 그림) → 빈 설계도면 칸 채우기(10/14 형 피드백 ④). 돌려주는 값 = 채운 줄 수. 위치 칸이 비었으면 부재 기호를 넣음."""
    from server.sitok import vision

    todo = [(i, r) for i, r in enumerate(data["sections"]) if not r.get("design") and r.get("member")]
    if not todo:
        return 0
    ranges = {f["floor"]: range_label(f["start"], f["end"]) for f in data["sample"]["floors"] if f.get("start") is not None and f.get("end") is not None}
    lines = "\n".join(f"{i + 1} · {floor_label(r['floor']) if r.get('floor') else '층 미정'}{'(대표 범위 ' + ranges[r['floor']] + ')' if r.get('floor') in ranges else ''} · {r['member']}"
                      f" · 기호 {r['position'] if r.get('position') else '(없음 — 대표 부재 고르기)'}" for i, r in todo)
    got = vision.ask_json(company_id, imgs, SCHEDULE_PROMPT.format(facility=facility, rows=lines, text=(text[:12000] if text else "(글자 없음 — 그림으로)")), max_tokens=8000, side=1568, effort="medium")
    by_no = {int(x.get("no")): x for x in (got if isinstance(got, list) else got.get("rows") or []) if isinstance(x, dict) and str(x.get("no", "")).isdigit()}
    n = 0
    for i, r in todo:
        x = by_no.get(i + 1)
        if not x:
            continue
        d = _dim_text(x.get("design"))
        if r["member"] == "강재":
            d = str(x.get("design") or "").strip().replace(" ", "")
            if not d.upper().startswith("H") and steel_area(d) is not None and len(d.split("×")) == 4:
                d = "H-" + d
        if not d or (steel_area(d) if r["member"] == "강재" else _dims(d)) is None:
            if r.get("position"):
                data.setdefault("_notes", []).append(f"B{i + 1} {r['position']}: 일람표에서 못 찾음")
            continue
        r["design"] = d
        if r.get("same", True):
            r["measured"] = d
        if not r.get("position") and x.get("mark"):
            r["position"] = str(x["mark"]).strip()[:20]
        n += 1
    return n


def _selfcheck() -> None:
    # 다산: 지하3·지상5, 표본층 -3·5 → -3~-1 / 1~5 ; 조훈 -2·8·16(지하2·지상16) → 가운데 나눔
    assert split_ranges([-3, 5], 5, 3) == [(-3, -1), (1, 5)]
    assert abs(steel_area("L-100×100×7") - 13.56) < 0.1 and abs(steel_area("L-200×200×15") - 58.0) < 0.3 and abs(steel_area("L-50×50×4") - 3.86) < 0.1  # KS 13.62·57.75·3.89
    assert steel_area("100×100") is None and steel_area("13.4") == 13.4
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
    assert member_of("기둥 중앙부") == "기둥" and member_of("보 단부") == "큰보" and spot_of("보 단부") == "단부" and member_of("내력벽(W5)") == "벽체"
    d0 = normalize({"sample": {"floors": [{"floor": -3}, {"floor": 5}]}, "strength": {"rows": [{"floor": 5, "member": "기둥 단부", "est": 27.7, "design": 24}]},
                    "sections": [{"floor": 5, "member": "기둥(C5)", "design": "300x600", "same": True}]})
    assert d0["strength"]["rows"][0]["member"] == "기둥" and d0["strength"]["rows"][0]["spot"] == "단부" and d0["sections"][0]["measured"] == "300×600"
    assert sync_defaults(d0) and len(d0["sections"]) == 12 and len(d0["strength"]["rows"]) == 8 and len(d0["carbonation"]["rows"]) == 4
    assert len(d0["tilt"]["rows"]) == 8 and len(d0["settlement"]["sections"]) == 4 and d0["strength"]["rows"][-1]["design"] == 24
    assert [r for r in d0["strength"]["rows"] if r["floor"] == 5 and r["est"] == 27.7] and not sync_defaults(d0)  # 값 있는 줄 유지·두 번째는 변화 없음
    d0["sample"]["floors"].pop()  # 5층을 빼면 빈 줄만 빠지고 값 있는 줄은 남음
    assert sync_defaults(d0) and len([r for r in d0["strength"]["rows"] if r["floor"] == 5]) == 1 and len([r for r in d0["sections"] if r["floor"] == 5]) == 1
    assert all(abs(steel_area(k) - v) < 0.1 for k, v in (("H-200×200×8×12", 63.53), ("400x200x8x13", 84.12), ("H 300*300*10*15", 119.8), ("150×75×5×7", 17.85), ("588×300×12×20", 192.5)))
    st = section_row({"member": "강재", "design": "H-200×200×8×12", "measured": "H-200×200×8×11"})
    assert st["steel"] and st["area_design"] == 63.53 and st["grade"] == "c" and 90 <= st["ratio"] < 95, st
    sec = section_row({"design": "800×800", "measured": "800×800"})
    assert sec["ok"] and sec["grade"] == "a" and section_row({"design": "300", "measured": "280"})["grade"] == "c"
    st = strength_row({"est": 30.9, "design": 30})
    assert st["grade"] == "a" and strength_row({"est": 19.5, "design": 21})["grade"] == "c"
    v = compute({"sample": {"floors": [{"floor": -3}, {"floor": 5}]}}, above=5, below=3, area=6882.61, kind="정밀점검",
                completion=datetime.date(2022, 5, 31), when=datetime.date(2026, 5, 21))
    assert v["sample"]["need"] == 2 and v["sample"]["floors"][0]["range_label"] == "지하3층~지하1층" and v["sample"]["quantity"]["strength"]["need"] == 8
    # 10/29 칸 수 표·일치/일부 일치/불일치·□
    d1 = normalize({"sample": {"floors": [{"floor": 1}, {"floor": 3}]}, "sections": [{"floor": 1, "member": "기둥", "design": "400×500", "same": False, "measured": "□×500"}]})
    assert d1["sections"][0]["match"] == "불일치" and section_row(d1["sections"][0])["ratio"] is None and section_row(d1["sections"][0])["ok"] is None
    assert normalize({"sections": [{"member": "기둥", "design": "400×500", "match": "일부 일치", "measured": "400×480"}]})["sections"][0]["same"] is False
    sync_defaults(d1)
    assert len(d1["sections"]) == 12 and d1["section_plan"] == {}  # 칸 수 표 안 쓴 회차 = 예전대로, 저장 안 바뀜
    d1["section_plan"] = {"1|기둥": 1, "1|큰보": 4, "3|벽체": 2}
    sync_defaults(d1)
    one = [r["member"] for r in d1["sections"] if r["floor"] == 1]
    assert one.count("기둥") == 1 and one.count("큰보") == 4 and d1["sections"][0]["design"] == "400×500"  # 값 있는 기둥은 남음
    three = [r["member"] for r in d1["sections"] if r["floor"] == 3]
    assert three.count("벽체") == 2 and three.count("기둥") == 3 and three.count("큰보") == 3  # 표에 없는 부재는 지금 수 그대로
    assert d1["section_plan"]["1|기둥"] == 1 and d1["section_plan"]["3|벽체"] == 2 and not sync_defaults(d1)
    d1["section_plan"]["1|기둥"] = 0
    sync_defaults(d1)
    assert [r["member"] for r in d1["sections"] if r["floor"] == 1].count("기둥") == 1  # 값 있는 칸은 0으로 해도 안 지움
    fi = fill_from_items({"sections": [{"floor": 1, "member": "큰보", "item_id": "g", "design": "", "measured": "", "same": True, "position": ""},
                                       {"floor": 2, "member": "벽체", "item_id": "w", "design": "", "measured": "", "same": False, "position": "W1 / X1"}]},
                         {"g": {"kind": "보", "marks": ["1-5G1"], "floors": "", "size": "400 x 600"}, "w": {"kind": "벽체", "marks": ["W1"], "floors": "", "thickness": 200}}, 5)
    assert fi == 2 and _dims("×600") is None and _dims("300") == 300 and _dims("□×600") is None
    fd = {"sections": [{"floor": 1, "member": "큰보", "item_id": "g", "design": "", "measured": "", "same": True, "position": ""}]}
    fill_from_items(fd, {"g": {"kind": "보", "marks": ["1-5G1"], "floors": "", "size": "400 x 600"}}, 5)
    assert fd["sections"][0]["design"] == "400×600" and fd["sections"][0]["measured"] == "400×600" and fd["sections"][0]["position"] == "2G1"  # 1층 보 = 2층 바닥보
    print("재료시험 계산 검증 통과 — 다산은혜교회 보고서 값과 일치")


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    _selfcheck()
