"""견적 → 계약으로 넘기기·수주 통계(2026-10-29 통합 견적 3단계, 사용자 "시작").

수주한 견적을 이미 있는 화면의 계약·건으로 — 견적의 발주처·대상·금액을 옮겨 담고 견적.link에 이어 둠(다시 누르면 그 계약을 엶):
- 재해예방 기술지도 → 서류 자동화 › 산안법 용역 계약(ServiceContract — 용역명 = 공사명, 계약금액 = 합계(VAT 포함), 공사기간 → 착수·완수일)
- 시설물 정기·정밀안전점검 → 서류 자동화 › 시특법 민간 계약(SitokDocContract — 회차 줄 = 견적 줄의 회당 금액(VAT 포함) × 횟수, 견적일 반기부터,
  시설물이 여럿이면 동별 금액). 그 창에서 [📝 계약서 만들기] → [🏢 시설물 카드 만들어 넣기]로 이어짐
- 건축물관리점검 → 보고서 자동화 › 건축물관리점검 건(BlcmJob — 이름·주소·관리자·점검금액·연면적·주용도)
나머지(사전·사후조사·공사안전보건대장·이행점검·건설현장 안전점검)는 넘길 계약 화면이 아직 없어 수주 표시·통계만.
통계 = 견적일자 해마다 용역별·견적담당별 — 수주율 = 수주 ÷ 보낸 견적(보냄 + 수주 + 실패), 작성중은 견적 수에만."""
from __future__ import annotations

import datetime
import re

from server.estimate import calc as C

TARGETS = {"tech_guide": "sanan", "sitok_regular": "sitok", "sitok_precision": "sitok", "blcm": "blcm"}
TARGET_LABEL = {"sanan": "서류 자동화 › 산안법 용역 계약", "sitok": "서류 자동화 › 시특법 민간 계약", "blcm": "보고서 자동화 › 건축물관리점검 건"}
_DATE = re.compile(r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})")


def parse_period(text: str | None) -> tuple[datetime.date | None, datetime.date | None]:
    """공사기간 글 "2027.01.01.~2027.02.28" · "2027-01-01 ~ 2027-02-28" · "2027년 1월 1일 ~ …" → (시작, 끝). 못 읽으면 None."""
    out = []
    for y, m, d in _DATE.findall(text or ""):
        try:
            out.append(datetime.date(int(y), int(m), int(d)))
        except ValueError:
            pass
    return (out[0] if out else None), (out[1] if len(out) > 1 else None)


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", "").replace("㎡", "").replace("m²", "").strip())
    except (TypeError, ValueError):
        return None


def rounds_from(kind: str, rows: list[dict], outs: list[dict], issued: datetime.date | None, vat: float = 0.1) -> list[dict]:
    """시특법 회차 줄 — 시설물(줄 이름)마다 회당 견적 금액 × 횟수를 차례로 펼쳐 회차 k = 시설물들의 k번째 합(VAT 포함, 원 단위 반올림).
    같은 이름 줄이 둘이면(상·하반기를 따로 적은 견적) 한 시설물로 이어 붙임. 연도·반기 = 견적일 반기부터 반기마다(계약 창에서 고침)."""
    word = "정밀" if kind == "sitok_precision" else "정기"
    per: dict[str, list[int]] = {}
    for r, o in zip(rows, outs):
        name = (r.get("name") or "").strip() or "시설물"
        per.setdefault(name, []).extend([int(o.get("unit") or 0)] * max(1, int(round(o.get("times") or 1))))
    day = issued or datetime.date.today()
    year, half = day.year, ("상반기" if day.month <= 6 else "하반기")
    out = []
    for k in range(max((len(v) for v in per.values()), default=0)):
        parts = [{"name": n, "amount": int(round(v[k] * (1 + vat)))} for n, v in per.items() if k < len(v)]
        item = {"year": year, "half": half, "kind": word, "amount": sum(p["amount"] for p in parts)}
        if len(parts) >= 2:
            item["parts"] = parts
        out.append(item)
        year, half = (year, "하반기") if half == "상반기" else (year + 1, "상반기")
    return out


def _spec(p: dict) -> str:
    area = (p.get("area") or "").strip()
    if area and not re.search(r"(㎡|m²|m2)$", area):
        area += "㎡"
    return ", ".join(x for x in (f"연면적 {area}" if area else "", (p.get("floors") or "").strip()) if x)


def sanan_fields(e, totals: dict) -> dict:
    """산안법 용역 계약 칸(contracts.ContractIn 이름) — 용역명 = 공사명(운영 계약 이름이 공사명 그대로), 담당 = 견적 참조(계약 담당)."""
    c, p = e.client or {}, e.project or {}
    start, end = parse_period(p.get("period"))
    out = {"client": (c.get("name") or "").strip(), "title": (p.get("name") or "").strip(), "amount": int(totals.get("total") or 0) or None,
           "client_manager": (c.get("ref") or "").strip(), "client_phone": (c.get("phone") or "").strip(), "client_email": (c.get("email") or "").strip()}
    if start:
        out["start_date"] = start.isoformat()
    if end:
        out["end_date"] = end.isoformat()
    return out


def sitok_fields(e, outs: list[dict], vat: float) -> dict:
    """시특법 민간 계약 칸(sitok_docs.ContractIn 이름) — 계약건명·문서번호는 비워 둠(계약 창이 회차로 자동 — 청천영진아파트 2026~2027년 정기안전점검)."""
    c, p = e.client or {}, e.project or {}
    return {"sector": "민간", "client": (c.get("name") or "").strip(), "client_rep": (c.get("rep") or "").strip(),
            "facility_name": (p.get("name") or "").strip(), "location": (p.get("address") or "").strip(), "spec": _spec(p),
            "client_manager": (c.get("ref") or "").strip(), "client_phone": (c.get("phone") or "").strip(), "client_email": (c.get("email") or "").strip(),
            "rounds": rounds_from(e.kind, e.rows or [], outs, e.issued_on, vat), "open_ended": False,
            "memo": f"견적 {e.no}에서 넘김({datetime.date.today():%Y-%m-%d})"}


def blcm_fields(e, totals: dict) -> dict:
    """건축물관리점검 건 칸 — 관리자 = 발주처(회사명)·대표자(성명), 점검금액 = 합계(부가세 포함), 개요 = 견적 줄의 연면적·주용도."""
    c, p = e.client or {}, e.project or {}
    row = next((r for r in e.rows or [] if r.get("type") == "blcm"), {})
    building = {k: v for k, v in (("total_area", _num(row.get("area"))), ("use", row.get("use") or "")) if v not in (None, "")}
    owner = {k: (c.get(s) or "").strip() for k, s in (("company", "name"), ("name", "rep"), ("phone", "phone"), ("email", "email")) if (c.get(s) or "").strip()}
    return {"name": ((p.get("name") or "").strip() or (c.get("name") or "").strip() or "이름 없는 건축물")[:80], "address": (p.get("address") or "").strip()[:200],
            "owner": owner, "contract": {"amount": int(totals.get("total") or 0) or ""}, "building": building,
            "memo": f"견적 {e.no}에서 넘김({datetime.date.today():%Y-%m-%d})"}


# ---------- 수주 통계 ----------
def _year(e) -> int:
    d = e.issued_on or (e.created_at.date() if e.created_at else datetime.date.today())
    return d.year


def _blank(label: str) -> dict:
    return {"label": label, "count": 0, "draft": 0, "sent": 0, "won": 0, "lost": 0, "quoted": 0, "won_total": 0, "rate": None}


def _add(b: dict, e) -> None:
    b["count"] += 1
    s = e.status if e.status in ("draft", "sent", "won", "lost") else "draft"
    b[s] += 1
    total = int((e.totals or {}).get("total") or 0)
    if s != "draft":
        b["quoted"] += total
    if s == "won":
        b["won_total"] += total


def _rate(b: dict) -> dict:
    sent = b["sent"] + b["won"] + b["lost"]
    b["rate"] = round(b["won"] / sent, 4) if sent else None
    return b


def stats(rows: list, year: int | None) -> dict:
    """견적일자 해(year=None이면 전체)의 용역별·견적담당별·달별 숫자."""
    years = sorted({_year(e) for e in rows}, reverse=True)
    pick = [e for e in rows if year is None or _year(e) == year]
    kinds = {k: _blank(v["label"]) for k, v in C.KINDS.items()}
    staff: dict[str, dict] = {}
    months = [{"m": m, "count": 0, "won": 0} for m in range(1, 13)]
    total = _blank("합계")
    for e in pick:
        _add(kinds.setdefault(e.kind, _blank(e.kind)), e)
        who = ((e.staff or {}).get("name") or "").strip() or "(담당 없음)"
        _add(staff.setdefault(who, _blank(who)), e)
        _add(total, e)
        d = e.issued_on or (e.created_at.date() if e.created_at else None)
        if d and year is not None:
            months[d.month - 1]["count"] += 1
            months[d.month - 1]["won"] += e.status == "won"
    return {"year": year, "years": years, "total": _rate(total),
            "kinds": [{"key": k, **_rate(b)} for k, b in kinds.items() if b["count"]],
            "staff": sorted((_rate(b) for b in staff.values()), key=lambda b: (-b["count"], b["label"])),
            "months": months if year is not None else []}
