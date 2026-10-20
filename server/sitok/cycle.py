"""정밀안전점검·정밀안전진단 도래주기 — 시설물의 안전 및 유지관리에 관한 특별법 시행령 [별표 3](2026-08-18 개정, 10/20 민재형 첨부).

계약서를 쓸 때 회차 줄(반기)마다 실시할 점검(정기 / 정밀 = 정밀안전점검 / 진단 = 정밀안전진단)을 정함(10/20 민재형):
1종 = 정기~정밀안전진단, 2종 = 정기~정밀안전점검, 3종 = 정기만. 건축물과 토목(건축물 외)은 정밀안전점검 주기가 다름.

- 정밀안전점검: 건축물 A 4년·B·C 3년·D·E 2년 / 건축물 외 A 3년·B·C 2년·D·E 1년. 최초 = 준공(사용승인) 후 4년(건축물)·3년 이내(비고 5).
- 정밀안전진단: A 6년·B·C 5년·D·E 4년. 최초 = 준공 후 10년이 지난 때부터 1년 이내(비고 6).
- 주기는 이전 정밀안전점검·진단을 완료한 달의 마지막 날부터(비고 8), 진단을 하면 정밀점검 주기도 진단 완료 기준(비고 8 단서).
- 정밀점검·진단 반기의 정기는 생략(비고 9 — 그 반기 줄이 정밀·진단이 됨), 진단 완료 6개월 전 이내에 기한이 오는 정밀점검은 생략 가능(비고 10).
- 예외(5의2 3종 D·E 최초 정밀점검, 6의2·6의3 진단)는 계산을 바꾸지 않고 알림만.

전회차 시기 = 우리 정밀 회차(만든 보고서) · 전회차 보고서 1.2.6 이력(survey.prev.history) · 사람이 넣은 날짜(sitok_facility.last_precision 등, 0056)
· 이미 계약된 정밀·진단 회차(새 계약 첫 반기 전 — 그 반기 끝에 한다고 봄, 예: 기존 계약 2027 상반기 정밀 → 2028 계약은 그것부터) 중 가장 늦은 것.
"""
from __future__ import annotations

import calendar
import datetime
import re
from dataclasses import dataclass, field as dc_field

from server.sitok import seasons

PRECISION_YEARS = {"건축": {"A": 4, "B": 3, "C": 3, "D": 2, "E": 2}, "토목": {"A": 3, "B": 2, "C": 2, "D": 1, "E": 1}}
DIAGNOSIS_YEARS = {"A": 6, "B": 5, "C": 5, "D": 4, "E": 4}
FIRST_PRECISION = {"건축": 4, "토목": 3}  # 비고 5 — 준공 후 N년 이내
FIRST_DIAGNOSIS = 10  # 비고 6 — 준공 후 10년이 지난 때부터 1년 이내
ORDER = {"정기": 0, "정밀": 1, "진단": 2}
WORD = {"정기": "정기안전점검", "정밀": "정밀안전점검", "진단": "정밀안전진단"}


def month_end(d: datetime.date) -> datetime.date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def add_years(d: datetime.date, n: int) -> datetime.date:
    """n년 뒤 같은 달 마지막 날(주기 기준 = 완료한 달의 마지막 날, 비고 8)."""
    return month_end(datetime.date(d.year + n, d.month, 1))


def ym(d: datetime.date | None) -> str:
    return f"{d:%Y.%m}" if d else ""


def half_bounds(year: int, half: str) -> tuple[datetime.date, datetime.date]:
    return (datetime.date(year, 1, 1), datetime.date(year, 6, 30)) if seasons.bucket(half) == "상반기" else (datetime.date(year, 7, 1), datetime.date(year, 12, 31))


def class_of(text: str | None, template: str | None, legal: bool | None) -> int | None:
    """종별 1·2·3 — 시설물 칸(1종/2종/3종)이 있으면 그것, 없으면 보고서 틀(3종 틀이면 3종, 아니면 2종), 법정 외면 None."""
    m = re.search(r"[123]", text or "")
    if m:
        return int(m.group())
    if legal is False:
        return None
    return 3 if (template or "").startswith("3종") else 2


def field_of(kind: str | None) -> str:
    """시설물 구분 → 건축/토목(건축물 외) — 정밀안전점검 주기가 다름(10/20 민재형)."""
    return "건축" if (kind or "건축물").startswith("건축") else "토목"


def letter(g: str | None) -> str:
    m = re.search(r"[A-E]", (g or "").upper())
    return m.group() if m else ""


@dataclass
class Info:
    """건물 하나의 도래주기 재료 — gather()가 DB에서 채움."""
    id: int = 0
    name: str = ""
    class_no: int | None = 2
    class_src: str = ""  # "입력" / "보고서 틀"
    field: str = "건축"
    grade: str = "B"
    grade_src: str = ""  # "입력" / "2026 하반기 보고서" / "전회차 보고서 이력" / "기본(B·C로 봄)"
    completion: datetime.date | None = None
    last_precision: datetime.date | None = None
    lp_src: str = ""
    precision_first: bool = False
    last_diagnosis: datetime.date | None = None
    ld_src: str = ""
    diagnosis_first: bool = False
    notes: list[str] = dc_field(default_factory=list)


def needs(info: Info) -> list[str]:
    """사람이 넣어야 할 것 — 2종 = 전회차 정밀점검, 1종 = + 전회차 정밀진단(처음이면 '아직 안 함'), 최초인데 준공일이 없으면 준공일. 3종은 없음(10/20 민재형)."""
    if info.class_no not in (1, 2):
        return []
    out = []
    if not info.last_precision and not info.precision_first:
        out.append("precision")
    if info.class_no == 1 and not info.last_diagnosis and not info.diagnosis_first:
        out.append("diagnosis")
    first = (info.precision_first and not info.last_precision) or (info.class_no == 1 and info.diagnosis_first and not info.last_diagnosis)
    if first and not info.completion:
        out.append("completion")
    return out


def plan(info: Info, halves: list[tuple[int, str]]) -> dict:
    """회차 줄(연도·반기)마다 {kind 정기|정밀|진단, why} + next(다음 정밀점검·진단 기한 글) + warn(예외 알림)."""
    rows = {(y, h): {"kind": "정기", "why": ""} for y, h in halves}
    out = {"rounds": rows, "next": "", "warn": []}
    if info.class_no is None:
        out["next"] = "법정 외 — 정기만"
        return out
    if info.class_no == 3:
        out["next"] = "3종 — 정기안전점검만"
        if info.grade in "DE":
            out["warn"].append("3종 D·E등급 — 정기점검 완료일부터 1년 이내 최초 정밀안전점검(별표 3 비고 5의2)")
        return out
    g = info.grade if info.grade in "ABCDE" else "B"
    py, dy = PRECISION_YEARS[info.field][g], DIAGNOSIS_YEARS[g]
    one = info.class_no == 1
    lp = info.last_precision
    ld = info.last_diagnosis if one else None
    # 정밀점검 기한 — 진단을 했으면 진단 완료 기준(비고 8 단서)
    base = max([d for d in (lp, ld) if d], default=None)
    due_p = p_note = None
    if base is not None:
        due_p = add_years(base, py)
        what = "정밀안전진단" if ld and base == ld and (not lp or ld >= lp) else "정밀안전점검"
        p_note = f"전회차 {what} {ym(base)} · {g}등급 {info.field} {py}년 → {ym(due_p)}"
    elif info.precision_first and info.completion:
        n = FIRST_PRECISION[info.field]
        due_p = add_years(info.completion, n)
        p_note = f"최초 정밀안전점검 — 준공 {ym(info.completion)} 후 {n}년 이내 → {ym(due_p)}까지"
    due_d = d_note = d_start = None
    if one:
        if ld is not None:
            due_d = add_years(ld, dy)
            d_note = f"전회차 정밀안전진단 {ym(ld)} · {g}등급 {dy}년 → {ym(due_d)}"
        elif info.diagnosis_first and info.completion:
            d_start = add_years(info.completion, FIRST_DIAGNOSIS)
            due_d = add_years(info.completion, FIRST_DIAGNOSIS + 1)
            d_note = f"최초 정밀안전진단 — 준공 {ym(info.completion)} 후 10년이 지난 때부터 1년 이내 → {ym(d_start)}~{ym(due_d)}"
    for y, h in sorted(halves, key=lambda x: (x[0], seasons.order(x[1]))):
        a, b = half_bounds(y, h)
        late = lambda d: f" — 기한 {ym(d)} 지남" if d < a else ""  # noqa: E731
        if due_d is not None and due_d <= b and (d_start is None or d_start <= b):
            rows[(y, h)] = {"kind": "진단", "why": d_note + late(due_d)}
            done = min(max(due_d, a), b)  # 같은 반기에 기한이 온 정밀점검은 진단이 대신 — 점검 주기도 진단 완료부터(비고 8 단서)
            due_d, d_start = add_years(done, dy), None
            due_p = add_years(done, py)
            d_note = f"앞 회차 정밀안전진단 {ym(done)} · {g}등급 {dy}년 → {ym(due_d)}"
            p_note = f"앞 회차 정밀안전진단 {ym(done)} · {g}등급 {info.field} {py}년 → {ym(due_p)}"
            continue
        if due_p is not None and due_p <= b:
            if one and due_d is not None and 0 <= (due_d - due_p).days <= 184:
                rows[(y, h)] = {"kind": "정기", "why": f"정밀점검 기한 {ym(due_p)} — 정밀안전진단({ym(due_d)}) 완료 6개월 전 이내라 생략 가능(비고 10)"}
                continue
            rows[(y, h)] = {"kind": "정밀", "why": p_note + late(due_p)}
            done = min(max(due_p, a), b)
            due_p = add_years(done, py)
            p_note = f"앞 회차 정밀안전점검 {ym(done)} · {g}등급 {info.field} {py}년 → {ym(due_p)}"
    nxt = [x for x in (f"다음 정밀안전점검 {ym(due_p)}" if due_p else "", f"다음 정밀안전진단 {ym(due_d)}" if one and due_d else "") if x]
    out["next"] = " · ".join(nxt) or "전회차 정밀점검 시기를 넣으면 계산"
    if info.field == "토목" and info.completion and info.class_no == 2 and not info.last_diagnosis and g in "CDE" and \
            (datetime.date.today() - info.completion).days >= 30 * 365:
        out["warn"].append("준공 30년 지난 2종 토목 C·D·E등급 — 정밀안전진단 대상일 수 있음(별표 3 비고 6의3)")
    return out


def merge(plans: list[dict], halves: list[tuple[int, str]], names: list[str]) -> dict:
    """여러 건물(계약이 맡는 건물)의 계획 → 계약 회차 줄마다 가장 무거운 점검(진단 > 정밀 > 정기)과 그 이유(건물 이름)."""
    out = {}
    for y, h in halves:
        best, why = "정기", []
        for p, nm in zip(plans, names):
            r = p["rounds"].get((y, h)) or {"kind": "정기", "why": ""}
            if ORDER[r["kind"]] > ORDER[best]:
                best = r["kind"]
            if r["kind"] != "정기" or r["why"]:
                why.append(f"{nm}: {WORD[r['kind']]} — {r['why']}" if r["why"] else f"{nm}: {WORD[r['kind']]}")
        out[f"{y}-{h}"] = {"kind": best, "why": why}
    return out


# ---------- DB에서 재료 모으기 ----------

def _period_end(text: str | None) -> datetime.date | None:
    """"2025.04.09~2025.05.07" → 2025-05-07(끝 날, 없으면 앞 날)."""
    ds = re.findall(r"(\d{4})\s*[.\-/년]\s*(\d{1,2})(?:\s*[.\-/월]\s*(\d{1,2}))?", text or "")
    if not ds:
        return None
    y, m, d = ds[-1]
    try:
        return datetime.date(int(y), int(m), int(d or 1))
    except ValueError:
        return None


def gather(db, f, planned: list[tuple[datetime.date, str, str]] | None = None) -> Info:
    """시설물(건물) 하나 → Info. 우리 회차·전회차 보고서 이력·시설물 칸(사람이 넣은 값)·planned(이미 계약된 정밀·진단 회차 [(그 반기 끝, 정밀|진단, 글)])를 합침."""
    from core.models_web import SitokReport

    info = Info(id=f.id, name=f.name, field=field_of(f.kind), completion=f.completion_date,
                precision_first=bool(f.precision_first), diagnosis_first=bool(f.diagnosis_first))
    info.class_no = class_of(f.class_no, f.template, f.legal)
    info.class_src = "입력" if (f.class_no or "").strip() else ("법정 외" if f.legal is False else "보고서 틀")
    reps = sorted(db.query(SitokReport).filter(SitokReport.facility_id == f.id).all(), key=lambda r: (r.year, seasons.order(r.half)), reverse=True)
    # 등급 — 사람이 넣은 값 > 최근 보고서 결과 > 전회차 보고서 이력 > 기본 B·C
    grade, src = letter(f.safety_grade), "입력" if letter(f.safety_grade) else ""
    for r in reps:
        if grade:
            break
        ai = r.ai if isinstance(r.ai, dict) else {}
        g = letter(((ai.get("final") or ai.get("draft") or {}) if isinstance(ai.get("final") or ai.get("draft"), dict) else {}).get("grade"))
        if g:
            grade, src = g, f"{r.year} {r.half} 보고서"
    hist = []
    for r in reps:
        p = (r.survey or {}).get("prev") if isinstance(r.survey, dict) else None
        if isinstance(p, dict) and p.get("history"):
            hist = [h for h in p["history"] if isinstance(h, dict)]
            break
    if not grade:
        for h in hist:  # 위·최근부터
            if letter(h.get("grade")):
                grade, src = letter(h.get("grade")), "전회차 보고서 이력"
                break
    info.grade, info.grade_src = (grade, src) if grade else ("B", "기본(B·C로 봄)")
    # 전회차 정밀점검·진단 — 가장 늦은 것
    cands_p, cands_d = [], []
    if f.last_precision:
        cands_p.append((f.last_precision, "입력"))
    if f.last_diagnosis:
        cands_d.append((f.last_diagnosis, "입력"))
    today = datetime.date.today()
    for r in reps:
        made = r.status == "done" or (isinstance(r.submit, dict) and r.submit.get("report"))
        if r.kind in ("정밀", "진단") and made:
            d = r.period_end or r.report_date or (r.made_at.date() if r.made_at else None) or half_bounds(r.year, r.half)[1]
            if d <= today:
                (cands_d if r.kind == "진단" else cands_p).append((d, f"우리 회차 {r.year} {r.half}"))
    for h in hist:
        k = re.sub(r"\s", "", h.get("kind") or "")
        d = _period_end(h.get("period"))
        if d and "진단" in k:
            cands_d.append((d, "전회차 보고서 이력"))
        elif d and "정밀" in k:
            cands_p.append((d, "전회차 보고서 이력"))
    for d, k, label in planned or []:
        (cands_d if k == "진단" else cands_p).append((d, label))
    if cands_p:
        info.last_precision, info.lp_src = max(cands_p)
    if cands_d:
        info.last_diagnosis, info.ld_src = max(cands_d)
    return info
