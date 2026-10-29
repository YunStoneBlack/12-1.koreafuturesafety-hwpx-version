"""통합 견적 계산(2026-10-29) — 회사 견적서 엑셀 9개(용역 8가지)의 수식을 그대로 옮김. 견적 = 머리(발주처·공사/시설·담당) + 줄(rows).

줄 계산 방식(type) — 계산 방식 셋(엔지니어링 대가 / 구간 단가 × 횟수 / 항목 × 횟수 × 단가):
- sitok: 시특법식 내역서(정기·정밀안전점검, 신축 사전·사후조사) — 직접인건비 = 인·일 × 노임(고급기술자), 직접경비 = 여비·차량·현지보조인부·
  위험수당(외업 인·일 × 노임 × %)·기계기구손료(직접인건비 × %)·보고서·추가조사비, 제경비 = 직접인건비 × 1.1, 기술료 = (직접인건비 + 제경비) × 0.2
- blcm: 건축물관리점검지침 7장 — 연면적 구간 사이 직선 보간으로 점검책임자(기술사)·점검자(초급) 인원, 사용승인 20년 이상이면 구조안전 책임자 +1,
  줄마다 INT, 제경비 110%·기술료 20%·직접경비 10만원 일괄, 소계 × 조정비(경과년수 × 용도)
- eng: 엔지니어링 일반(공사안전보건대장) — 업무마다 등급 × 인원 × 일수, 직접경비 = 직접인건비 × 10%(비상주), 제경비·기술료, 보고서 제작
- visit: 회당(재해예방 기술지도·이행점검) — 공사금액 구간 인건비 × 인원 × 일수 + 직접경비 + 제경비 + 기술료 + 보고서 → 회당 산출, 횟수 = 공사기간 ÷ 15일
- item: 항목 × 횟수 × 단가(건설현장 안전점검 — 안전관리계획서 검토·정기안전점검 n회 등)
산출 금액 = 만원 미만 절사(엑셀은 용역마다 10만·만·천·백원으로 제각각 — 최종 금액은 견적 금액 칸에서 정하므로 산출은 만원으로 통일).
견적 금액(회당, VAT 별도)을 비우면 산출 금액 그대로, 적으면 네고율 = 1 − 견적 ÷ 산출. 공급가 = 회당 × 횟수, 부가세 10%."""
from __future__ import annotations

import copy
import datetime
import math

GRADES = ("기술사", "특급기술자", "고급기술자", "중급기술자", "초급기술자", "고급숙련기술자", "중급숙련기술자", "초급숙련기술자")
# 엔지니어링 노임단가(건설부문, 원/일) — 2026 = 한국엔지니어링협회 「2025년도 엔지니어링업체 임금실태조사 보고서」(2025.12.02 공표, 2026.1.1 적용) 건설부문 표
# (회사 견적서 엑셀의 기술사·고급·초급 값과 같음), 2019 = 회사 견적서 엑셀에 있던 표. 매년 공표 때 기준표에서 연도를 더함.
LABOR_DEFAULT = {
    "2026": {"기술사": 467217, "특급기술자": 373353, "고급기술자": 310884, "중급기술자": 295138, "초급기술자": 235459,
             "고급숙련기술자": 281075, "중급숙련기술자": 250087, "초급숙련기술자": 218142},
    "2019": {"기술사": 432440, "특급기술자": 335638, "고급기술자": 282545, "중급기술자": 261571, "초급기술자": 205686,
             "고급숙련기술자": 204010, "중급숙련기술자": 174996, "초급숙련기술자": 157750},
}
# 회당 인건비(기술지도·이행점검 수수료내역) — 공사금액 구간(원, 미만)
VISIT_BANDS_DEFAULT = [
    {"under": 300_000_000, "label": "3억 미만", "grade": "중급기술자(건설)", "rate": 45000},
    {"under": 2_000_000_000, "label": "3억 이상 20억 미만", "grade": "중급기술자(건설)", "rate": 65000},
    {"under": 4_000_000_000, "label": "20억 이상 40억 미만", "grade": "고급기술자(건설)", "rate": 75000},
    {"under": None, "label": "40억 이상", "grade": "특급기술자(건설)", "rate": 150000},
]
# 현지보조인부 = 대한건설협회 시중노임단가 보통인부(2026.9.1 적용 172,698원 — 「2026년 하반기 적용 건설업 임금실태조사 보고서」, 회사 엑셀은 옛 133,417원)
RATES_DEFAULT = {"labor": LABOR_DEFAULT, "labor_year": "2026", "visit_bands": VISIT_BANDS_DEFAULT, "visit_days": 15,
                 "overhead": 1.1, "tech": 0.2, "helper_rate": 172698, "vat": 0.1}

# 건축물관리점검지침 7장(회사 산출근거 시트) — 연면적(㎡) 구간: 정기 책임자·점검자 / 긴급 책임자·점검자(인·일)
BLCM_AREA = (3000, 5000, 10000, 30000, 100000)
BLCM_PERSONS = {"regular": ((1, 1, 1, 2, 2), (0, 1, 2, 3, 4)), "urgent": ((0.5, 0.5, 0.5, 1, 1), (0, 0.5, 1, 1.5, 2))}
BLCM_AGE = ((5, 1.0), (10, 1.05), (15, 1.1), (25, 1.15), (35, 1.2), (55, 1.25))  # 넘으면 1.3
BLCM_AGE_OVER = 1.3
BLCM_USE = {"1종근린생활시설": 1.0, "자동차관련시설": 1.0, "2종근린생활시설": 1.1, "업무시설": 1.1, "공동주택": 1.1, "장례식장": 1.1, "교육연구시설": 1.1,
            "노유자시설": 1.2, "위락시설": 1.2, "관광휴게시설": 1.2, "판매시설": 1.2,
            "운수시설": 1.3, "의료시설": 1.3, "도서관": 1.3, "운동시설": 1.3, "숙박시설": 1.3, "문화및집회시설": 1.4}

# 용역 8가지 — 표지 "과업내용"·기본 줄·견적 조건(회사 견적서 엑셀 그대로)
KINDS = {
    "sitok_regular": {"label": "시설물 정기안전점검", "task": "시설물 안전점검", "subject": "시설명", "row": "sitok", "check": "정기안전점검",
                      "conditions": ["기존자료(도면 및 시설물관리대장) 제공 조건임", "전회차 자료 및 보고서 제공조건임", "현장조사 시 협조"]},
    "sitok_precision": {"label": "시설물 정밀안전점검", "task": "시설물 정밀안전점검", "subject": "시설명", "row": "sitok", "check": "정밀안전점검", "machine_pct": 0.05,
                        "conditions": ["기존자료(도면 및 시설물관리대장) 제공 조건임", "전회차 자료 및 보고서 제공조건임", "현장조사 시 협조"]},
    "survey": {"label": "신축공사 사전·사후조사", "task": "신축공사 관련 사전·사후조사", "subject": "용역명", "row": "sitok", "check": "사전조사",
               "conditions": ["기존자료(도면 등) 제공 조건임", "현장조사 시 협조"]},
    "blcm": {"label": "건축물관리점검", "task": "건축물관리점검 용역", "subject": "시설명", "row": "blcm", "check": "정기점검",
             "conditions": ["관련자료 요청 시 협조", "현장조사시 협조"]},
    "health_ledger": {"label": "공사안전보건대장", "task": "공사안전보건대장 용역", "subject": "공사명", "row": "eng", "check": "작성비용",
                      "conditions": ["관련자료 요청 시 협조", "보고서 최종 승인 후 대금 지급"]},
    "impl_check": {"label": "공사안전보건대장 이행점검", "task": "공사안전보건대장 이행점검", "subject": "공사명", "row": "visit", "check": "이행점검",
                   "conditions": ["관련자료 요청 시 협조", "회차별 보고서 최종 승인 후 대금 지급"]},
    "tech_guide": {"label": "재해예방 기술지도", "task": "『건설』 재해예방 기술지도", "subject": "공사명", "row": "visit", "check": "기술지도",
                   "conditions": ["계약 체결 후 공사기간, 공사금액 변경 발생 시 기술지도 횟수 및 금액 변경", "산업안전보건법 시행령 [별표18]에 따라 공사 시작 후 15일마다 1회"]},
    "site_safety": {"label": "건설현장 안전점검", "task": "건설현장 정기안전점검 용역", "subject": "공사명", "row": "item", "check": "정기안전점검",
                    "conditions": ["관련자료 요청 시 협조", "회차별 보고서 최종 승인 후 대금 지급"]},
}
ROW_TYPES = ("sitok", "blcm", "eng", "visit", "item")
ROW_LABEL = {"sitok": "시설물 내역(시특법식)", "blcm": "건축물관리점검(지침 7장)", "eng": "엔지니어링(업무·등급별)", "visit": "회당 금액 × 횟수", "item": "항목 × 횟수 × 단가"}


def rates_with(saved: dict | None, today: datetime.date | None = None) -> dict:
    """설정에 저장된 기준표 + 처음 값(빈 칸은 처음 값). 자동 갱신(rate_watch)이 미리 찾아 둔 다음 값은 적용일(1월 1일·9월 1일)부터."""
    out = copy.deepcopy(RATES_DEFAULT)
    s = saved or {}
    for k, v in s.items():
        if k == "labor" and isinstance(v, dict):
            for y, t in v.items():
                out["labor"].setdefault(str(y), {g: None for g in GRADES})
                out["labor"][str(y)].update({g: (int(x) if x not in (None, "") else None) for g, x in (t or {}).items() if g in GRADES})
        elif v not in (None, ""):
            out[k] = v
    today = today or datetime.date.today()
    for key, field, val in (("labor_next", "labor_year", "year"), ("helper_next", "helper_rate", "value")):
        nx = s.get(key) or {}
        try:
            if nx and today >= datetime.date.fromisoformat(nx["from"]) and (field != "labor_year" or nx[val] in out["labor"]):
                out[field] = nx[val]
        except (KeyError, ValueError, TypeError):
            pass
    return out


def labor_rate(rates: dict, grade: str, year: str | None = None) -> int | None:
    t = rates["labor"].get(str(year or rates.get("labor_year") or "2026")) or {}
    return t.get(grade)


def floor_to(x: float, digits: int = 4) -> int:
    """엑셀 ROUNDDOWN(x, -digits)."""
    step = 10 ** digits
    return int(math.floor((x or 0) / step + 1e-9) * step)


def _n(v, default=0.0) -> float:
    try:
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


# ---------- 줄 기본값 ----------
def default_row(kind: str, row_type: str | None = None, rates: dict | None = None, name: str = "") -> dict:
    k = KINDS.get(kind) or KINDS["site_safety"]
    t = row_type or k["row"]
    base = {"type": t, "name": name, "check": k["check"], "times": 1, "price": None}
    if t == "sitok":
        base.update({"grade": "고급기술자", "mandays": 4, "field_mandays": 2, "travel": {"days": 1, "persons": 2, "price": 50000},
                     "car": {"days": 1, "count": 1, "price": 40000}, "helper": {"days": 0, "persons": 1, "price": None},
                     "danger_pct": 0, "machine_pct": k.get("machine_pct", 0), "report": {"count": 3, "price": 20000}, "extra": 0})
    elif t == "blcm":
        base.update({"area": None, "built_year": None, "use": "업무시설", "mode": "regular", "structure": "auto", "expense": 100000})
    elif t == "eng":
        base.update({"tasks": [{"name": "현장조사/자료수집", "lines": []},
                               {"name": "공사 안전보건대장 점검/확인(공사중 이행확인)", "lines": []},
                               {"name": "분석/평가, 안전보건대장(기본·설계·시공) 작성", "lines": [{"grade": "고급기술자", "persons": 1, "days": 2}]}],
                     "expense_pct": 0.1, "report": 77000})
    elif t == "visit":
        base.update({"persons": 1, "days": 1, "band": "auto", "expense": 60000, "report": 30000, "period_days": None, "times": None})
    elif t == "item":
        base.update({"unit": 0, "note": ""})
    return base


def default_rows(kind: str, rates: dict | None = None) -> list[dict]:
    k = KINDS.get(kind) or KINDS["site_safety"]
    if kind == "health_ledger":
        return [{**default_row(kind, "eng", rates, "공사안전보건대장"), "check": "작성비용"}]
    if kind == "site_safety":
        return [{**default_row(kind, "item", rates, "안전관리계획서 검토"), "check": "", "unit": 1000000},
                {**default_row(kind, "item", rates, "정기안전점검"), "check": "", "times": 2, "unit": 2000000, "note": "높이 5미터 이상 거푸집 동바리"}]
    return [default_row(kind, k["row"], rates, "")]


# ---------- 계산 ----------
def _cost_tail(labor: float, exp: list[dict], r: dict, rates: dict) -> dict:
    """직접경비 합 · 제경비(직접인건비 × 율) · 기술료((직접인건비 + 제경비) × 율) · 합 · 산출(만원 미만 절사)."""
    expense = sum(x["amount"] for x in exp)
    oh_rate, tech_rate = _n(r.get("overhead"), rates["overhead"]), _n(r.get("tech"), rates["tech"])
    overhead = labor * oh_rate
    tech = (labor + overhead) * tech_rate
    total = labor + expense + overhead + tech
    return {"expenses": exp, "labor": labor, "expense": expense, "overhead": overhead, "overhead_rate": oh_rate,
            "tech": tech, "tech_rate": tech_rate, "sum": total, "calc": floor_to(total, 4)}


def calc_sitok(r: dict, rates: dict) -> dict:
    grade = r.get("grade") or "고급기술자"
    rate = labor_rate(rates, grade, r.get("year"))
    md = _n(r.get("mandays"))
    labor = md * (rate or 0)
    lines = [{"name": "직접인건비", "detail": f"{grade} {md:g}인·일 × {rate or 0:,}원", "amount": labor, "missing": rate is None}]
    exp = []
    tr = r.get("travel") or {}
    exp.append({"name": "여비 및 체제비", "detail": f"{_n(tr.get('days')):g}일 × {_n(tr.get('persons')):g}인 × {_n(tr.get('price')):,.0f}원",
                "amount": _n(tr.get("days")) * _n(tr.get("persons")) * _n(tr.get("price"))})
    car = r.get("car") or {}
    exp.append({"name": "차량운영비", "detail": f"{_n(car.get('days')):g}일 × {_n(car.get('count')):g}대 × {_n(car.get('price')):,.0f}원",
                "amount": _n(car.get("days")) * _n(car.get("count")) * _n(car.get("price"))})
    hp = r.get("helper") or {}
    hp_price = _n(hp.get("price"), rates.get("helper_rate") or 0)
    if _n(hp.get("days")) and _n(hp.get("persons")):
        exp.append({"name": "현지보조인부", "detail": f"{_n(hp.get('days')):g}일 × {_n(hp.get('persons')):g}인 × {hp_price:,.0f}원",
                    "amount": _n(hp.get("days")) * _n(hp.get("persons")) * hp_price})
    if _n(r.get("danger_pct")):
        exp.append({"name": "위험수당", "detail": f"외업 {_n(r.get('field_mandays')):g}인·일 × {rate or 0:,}원 × {_n(r.get('danger_pct')) * 100:g}%",
                    "amount": _n(r.get("field_mandays")) * (rate or 0) * _n(r.get("danger_pct"))})
    if _n(r.get("machine_pct")):
        exp.append({"name": "기계·기구손료", "detail": f"직접인건비 × {_n(r.get('machine_pct')) * 100:g}%", "amount": labor * _n(r.get("machine_pct"))})
    rp = r.get("report") or {}
    exp.append({"name": "보고서제작", "detail": f"{_n(rp.get('count')):g}부 × {_n(rp.get('price')):,.0f}원", "amount": _n(rp.get("count")) * _n(rp.get("price"))})
    if _n(r.get("extra")):
        exp.append({"name": "추가조사비", "detail": "", "amount": _n(r.get("extra"))})
    return {"lines": lines, **_cost_tail(labor, exp, r, rates)}


def blcm_persons(area: float, mode: str = "regular") -> tuple[float, float]:
    """연면적 → (점검책임자, 점검자) 인·일 — 구간 사이 직선 보간(엑셀 산출근거 D18·F18), 3천㎡ 미만 = 첫 값, 10만㎡ 이상 = 끝 값(엑셀은 FALSE)."""
    heads, staff = BLCM_PERSONS.get(mode) or BLCM_PERSONS["regular"]
    a = _n(area)

    def interp(vals):
        if a < BLCM_AREA[0]:
            return float(vals[0])
        for i in range(1, len(BLCM_AREA)):
            if a < BLCM_AREA[i]:
                x0, x1, y0, y1 = BLCM_AREA[i - 1], BLCM_AREA[i], vals[i - 1], vals[i]
                return y0 + (a - x0) * (y1 - y0) / (x1 - x0)
        return float(vals[-1])
    return interp(heads), interp(staff)


def blcm_age_factor(age: int) -> float:
    for lim, f in BLCM_AGE:
        if age <= lim:
            return f
    return BLCM_AGE_OVER


def calc_blcm(r: dict, rates: dict, today: datetime.date | None = None) -> dict:
    today = today or datetime.date.today()
    mode = "urgent" if r.get("mode") == "urgent" else "regular"
    heads, staff = blcm_persons(_n(r.get("area")), mode)
    year = int(_n(r.get("built_year"))) if r.get("built_year") else None
    age = (today.year - year) if year else 0
    sv = r.get("structure", "auto")
    structure = (age >= 20) if sv in ("auto", None, "") else (sv is True or sv == "yes")  # auto = 사용승인 20년 이상이면
    if structure and mode == "regular":
        heads += 1  # 구조안전 점검책임자(사용승인 20년 이상 첫 정기점검 — 구조강화점검)
    r_head, r_staff = labor_rate(rates, "기술사", r.get("year")), labor_rate(rates, "초급기술자", r.get("year"))
    a1, a2 = int((r_head or 0) * heads), int((r_staff or 0) * staff)
    lines = [{"name": "점검책임자", "detail": f"기술사 {heads:g}인 × {r_head or 0:,}원" + (" (구조안전 +1)" if structure and mode == "regular" else ""),
              "amount": a1, "missing": r_head is None},
             {"name": "점검자", "detail": f"초급기술자 {round(staff, 4):g}인 × {r_staff or 0:,}원", "amount": a2, "missing": r_staff is None}]
    labor = int(a1 + a2)
    oh_rate, tech_rate = _n(r.get("overhead"), rates["overhead"]), _n(r.get("tech"), rates["tech"])
    overhead = int(labor * oh_rate)
    tech = int((labor + overhead) * tech_rate)
    expense = _n(r.get("expense"), 100000)
    sub = labor + overhead + tech + expense
    age_f = blcm_age_factor(age) if year else 1.0
    use_f = BLCM_USE.get((r.get("use") or "").replace(" ", ""), 1.0)
    adj = round(age_f * use_f, 6)
    return {"lines": lines, "expenses": [{"name": "직접경비", "detail": "여비·차량·현장경비·위험수당 일괄(지침)", "amount": expense}],
            "labor": labor, "expense": expense, "overhead": overhead, "overhead_rate": oh_rate, "tech": tech, "tech_rate": tech_rate,
            "sum": sub, "adjust": adj, "adjust_detail": (f"경과년수 {age}년 {age_f:g} × 용도({r.get('use') or '-'}) {use_f:g}" if year else f"용도 {use_f:g}"),
            "persons": [round(heads, 4), round(staff, 4)], "age": age if year else None, "structure": structure,
            "calc": floor_to(sub * adj, 4)}


def calc_eng(r: dict, rates: dict) -> dict:
    lines, labor = [], 0.0
    for t in r.get("tasks") or []:
        for ln in t.get("lines") or []:
            rate = labor_rate(rates, ln.get("grade") or "", r.get("year"))
            amt = (rate or 0) * _n(ln.get("persons")) * _n(ln.get("days"))
            if not (_n(ln.get("persons")) and _n(ln.get("days"))):
                continue
            lines.append({"name": t.get("name") or "", "detail": f"{ln.get('grade')} {_n(ln.get('persons')):g}인 × {_n(ln.get('days')):g}일 × {rate or 0:,}원",
                          "amount": amt, "missing": rate is None})
            labor += amt
    pct = _n(r.get("expense_pct"), 0.1)
    exp = [{"name": "직접경비", "detail": f"직접인건비 × {pct * 100:g}%(비상주)", "amount": labor * pct}]
    if _n(r.get("report")):
        exp.append({"name": "보고서 제작", "detail": "", "amount": _n(r.get("report"))})
    return {"lines": lines, **_cost_tail(labor, exp, r, rates)}


def visit_times(period_days, per: int = 15) -> int | None:
    d = _n(period_days)
    return max(1, int(d // per)) if d else None


def visit_band(rates: dict, amount) -> dict:
    a = _n(amount)
    bands = rates.get("visit_bands") or VISIT_BANDS_DEFAULT
    for b in bands:
        if b.get("under") in (None, "") or a < _n(b["under"]):
            return b
    return bands[-1]


def calc_visit(r: dict, rates: dict, project_amount=None) -> dict:
    bands = rates.get("visit_bands") or VISIT_BANDS_DEFAULT
    band = str(r.get("band", "auto"))
    b = visit_band(rates, project_amount) if band == "auto" or not band.isdigit() or int(band) >= len(bands) else bands[int(band)]
    persons, days = _n(r.get("persons"), 1), _n(r.get("days"), 1)
    labor = _n(b["rate"]) * persons * days
    lines = [{"name": "직접인건비", "detail": f"{b['grade']}({b['label']}) {_n(b['rate']):,.0f}원 × {persons:g}인 × {days:g}일", "amount": labor}]
    exp = [{"name": "직접경비", "detail": "출장비 등", "amount": _n(r.get("expense"), 60000)}]
    if _n(r.get("report")):
        exp.append({"name": "보고서 제작", "detail": "", "amount": _n(r.get("report"))})
    return {"lines": lines, **_cost_tail(labor, exp, r, rates), "band": b["label"],
            "times_auto": visit_times(r.get("period_days"), int(_n(rates.get("visit_days"), 15)))}


def calc_row(r: dict, rates: dict, project: dict | None = None, today: datetime.date | None = None) -> dict:
    """줄 하나 → {…계산, calc 산출(회당, VAT 별도), unit 견적(회당), times, supply, nego}."""
    t = r.get("type")
    if t == "sitok":
        out = calc_sitok(r, rates)
    elif t == "blcm":
        out = calc_blcm(r, rates, today)
    elif t == "eng":
        out = calc_eng(r, rates)
    elif t == "visit":
        out = calc_visit(r, rates, (project or {}).get("amount"))
    else:
        unit = _n(r.get("unit"))
        out = {"lines": [], "expenses": [], "sum": unit, "calc": int(unit)}
    times = r.get("times")
    if t == "visit" and times in (None, "", 0):
        times = out.get("times_auto") or 1
    times = _n(times, 1) or 1
    unit = int(_n(r.get("price"))) if r.get("price") not in (None, "") else out["calc"]
    out.update({"unit": unit, "times": times, "supply": int(round(unit * times)),
                "nego": round(1 - unit / out["calc"], 4) if out["calc"] else 0.0,
                "missing_rate": any(x.get("missing") for x in out.get("lines") or [])})
    return out


def totals(rows_out: list[dict], rates: dict) -> dict:
    supply = sum(int(x["supply"]) for x in rows_out)
    vat = int(round(supply * _n(rates.get("vat"), 0.1)))  # 반올림 — 합계 맞추기(4,600,000 → 공급가 4,181,818 + 418,182)가 딱 떨어지게
    return {"supply": supply, "vat": vat, "total": supply + vat, "calc": int(sum(x["calc"] * x["times"] for x in rows_out))}


def fit_total(rows: list[dict], rows_out: list[dict], target_total: int, rates: dict) -> list[dict]:
    """합계(VAT 포함)를 target으로 — 공급가 = target ÷ 1.1, 줄마다 산출 비율대로 나누고(천원 미만 절사) 남은 것은 첫 줄에."""
    vat = _n(rates.get("vat"), 0.1)
    want = int(round(target_total / (1 + vat)))
    base = sum(x["calc"] * x["times"] for x in rows_out) or 1
    new = [dict(r) for r in rows]
    acc = 0
    for r, o in zip(new, rows_out):
        share = want * (o["calc"] * o["times"]) / base
        unit = floor_to(share / (o["times"] or 1), 3)
        r["price"] = unit
        acc += unit * (o["times"] or 1)
    if new:
        t0 = rows_out[0]["times"] or 1
        new[0]["price"] = int(new[0]["price"] + (want - acc) / t0)
    return new


def korean_amount(n: int | None) -> str:
    """금액 한글(엑셀 NUMBERSTRING(x,1) — LibreOffice에 없음): 9100000 → "구백일십만"."""
    if n is None:
        return ""
    n = int(n)
    if n == 0:
        return "영"
    digits = "영일이삼사오육칠팔구"
    small = ["", "십", "백", "천"]
    big = ["", "만", "억", "조"]
    out, i = [], 0
    while n > 0:
        part, n = n % 10000, n // 10000
        if part:
            s = ""
            for j in range(3, -1, -1):
                d = (part // (10 ** j)) % 10
                if d:
                    s += digits[d] + small[j]
            out.append(s + big[i])
        i += 1
    return "".join(reversed(out))
