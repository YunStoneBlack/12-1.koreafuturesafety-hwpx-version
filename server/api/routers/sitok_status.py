"""보고서 자동화 · 시특법 — 제출 현황(2026-10-15 민재형 문서번호 일치화 문서 "보고서 제출현황 관리").

산안법은 15일마다 보고서가 나가 달마다 봤지만 시특법은 상·하반기로 봄. 한 줄 = 그 반기 시설물 카드 하나(묶인 동은 한 줄),
칸 = 보고서(만듦) · 발주처 이메일 제출 · FMS 처리(자동 제출 기록 sitok_report.fms 또는 직접 처리함 · 해당없음) · 보고서 합본 출력 · 보고서 택배.
그 반기를 덮는 계약이 있는데 회차를 아직 안 만든 시설물도 "회차 없음"으로 보여 줌. 표시는 sitok_report.submit(0048) — 묶인 동은 같이.

- `GET /sitok/status/reports?year=&half=` — 줄 목록
- `POST /sitok/status/reports/{report_id}/mark` {item: mail|fms|print|parcel, action: done|na|clear, date?} — 표시(na = FMS 해당없음만)
- `GET /sitok/status/docs?year=&half=` — 서류 자동화 제출 현황(관급 착수계·완수계, 민간 계약서, 계산서 발행일)
- `POST /sitok/status/docs/{cid}/mark` {item: start|done|invoice, action: done|clear, date?, key?} — 직접 제출함·계산서 발행일
"""
from __future__ import annotations

import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokDocContract, SitokFacility, SitokGroup, SitokReport, User
from server.api.deps import get_current_user, get_db

router = APIRouter(prefix="/sitok/status", tags=["sitok-status"])
ITEMS = ("mail", "fms", "print", "parcel")
HALVES = ("상반기", "하반기")


def current_half(today: datetime.date | None = None) -> tuple[int, str]:
    t = today or datetime.date.today()
    return t.year, "상반기" if t.month <= 6 else "하반기"


def report_state(r: SitokReport | None) -> dict:
    """보고서 칸 — none(회차 없음) / writing(작성 중) / running(만드는 중) / failed / done(합본 PDF 있음)."""
    if r is None:
        return {"state": "none", "at": ""}
    if r.status == "running":
        return {"state": "running", "at": ""}
    if r.status == "failed":
        return {"state": "failed", "at": ""}
    if r.status == "done" and r.out_pdf and Path(r.out_pdf).exists():
        return {"state": "done", "at": r.made_at.strftime("%m/%d") if r.made_at else ""}
    return {"state": "writing", "at": ""}


def fms_state(r: SitokReport | None) -> dict:
    """FMS 칸 — 자동 제출 기록(실적 = 끝, 계약만 = 반쯤) + 직접 표시(처리함·해당없음). done = 끝난 것으로 셈."""
    st = (r.fms or {}) if r is not None else {}
    mark = ((r.submit or {}).get("fms") if r is not None else None) or None
    res, con = st.get("result") or {}, st.get("contract") or {}
    auto = "done" if res.get("status") == "done" else "contract" if con.get("status") == "done" else ""
    at = (res.get("at") if auto == "done" else con.get("at") if auto else "") or ""
    return {"auto": auto, "auto_at": at[5:10].replace("-", "/") if at else "", "mark": mark,
            "done": auto == "done" or bool(mark)}


class MarkIn(BaseModel):
    item: str
    action: str = "done"  # done | na(FMS 해당없음) | clear
    date: str | None = None


def _unit_reports(db: Session, r: SitokReport) -> list[SitokReport]:
    """묶인 동이면 같은 반기 회차 전부(표시를 같이), 아니면 그 회차 하나."""
    f = db.get(SitokFacility, r.facility_id)
    if f is None or not f.group_id:
        return [r]
    ids = [m.id for m in db.query(SitokFacility).filter(SitokFacility.group_id == f.group_id)]
    return db.query(SitokReport).filter(SitokReport.facility_id.in_(ids), SitokReport.year == r.year, SitokReport.half == r.half).all() or [r]


@router.get("/reports")
def list_rows(year: int | None = None, half: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from server.api.routers.sitok import contract_for

    y0, h0 = current_half()
    year, half = year or y0, half if half in HALVES else h0
    facs = db.query(SitokFacility).filter(SitokFacility.company_id == user.company_id).order_by(SitokFacility.group_order, SitokFacility.id).all()
    reps = {r.facility_id: r for r in db.query(SitokReport).filter(SitokReport.company_id == user.company_id, SitokReport.year == year,
                                                                   SitokReport.half == half).order_by(SitokReport.id)}
    docs = {}
    for d in db.query(SitokDocContract).filter(SitokDocContract.company_id == user.company_id, SitokDocContract.facility_id.isnot(None)).order_by(SitokDocContract.id):
        docs[d.facility_id] = d
    units: dict = {}
    for f in facs:
        units.setdefault(("g", f.group_id) if f.group_id else ("f", f.id), []).append(f)
    rows = []
    for key, members in units.items():
        lead = members[0]
        mr = [reps[m.id] for m in members if m.id in reps]
        r = next((reps[m.id] for m in members if m.id in reps), None)
        if r is None:
            if lead.contract_type == "종료" or contract_for(db, lead, year, half) is None:
                continue  # 이 반기 계약도 회차도 없음
        name = lead.name
        if key[0] == "g" and len(members) > 1:
            g = db.get(SitokGroup, key[1])
            name = (g.name if g else "") or lead.name
        doc = next((docs[m.id] for m in members if m.id in docs), None)
        sub = (r.submit or {}) if r is not None else {}
        states = [report_state(x) for x in mr] or [report_state(None)]
        rep = next((s for s in states if s["state"] != "done"), states[0])  # 묶음은 한 동이라도 안 끝나면 안 끝남
        rows.append({
            "facility": {"id": lead.id, "mgmt_no": lead.mgmt_no, "name": name, "sector": lead.sector or "민간", "badge_field": lead.badge_field or "",
                         "badge_kind": lead.badge_kind or "", "contract_type": lead.contract_type, "members": [{"id": m.id, "name": m.name} for m in members]},
            "report_id": r.id if r is not None else None, "report_ids": [x.id for x in mr], "kind": r.kind if r is not None else "",
            "report": rep, "mail": sub.get("mail"), "fms": fms_state(r), "print": sub.get("print"), "parcel": sub.get("parcel"),
            "email": (doc.site_email or doc.client_email) if doc is not None else "",
        })
    return {"year": year, "half": half, "rows": rows}


@router.post("/reports/{report_id}/mark")
def mark(report_id: int, body: MarkIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = db.get(SitokReport, report_id)
    if r is None or r.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "회차를 찾을 수 없습니다.")
    if body.item not in ITEMS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "표시할 칸이 아닙니다.")
    if body.action not in ("done", "na", "clear") or (body.action == "na" and body.item != "fms"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "해당없음은 FMS 칸만 됩니다.")
    try:
        day = datetime.date.fromisoformat(body.date) if body.date else datetime.date.today()
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "날짜가 맞지 않습니다.") from err
    value = None if body.action == "clear" else {"na": True, "by": user.display_name or ""} if body.action == "na" else {"at": day.isoformat(), "by": user.display_name or ""}
    for x in _unit_reports(db, r):
        sub = dict(x.submit or {})
        if value is None:
            sub.pop(body.item, None)
        else:
            sub[body.item] = value
        x.submit = sub
    db.commit()
    return {"ok": True, "item": body.item, "value": value}


# ---------- 서류 제출 현황(서류 자동화 · 시특법 — 10/15 민재형 문서 "서류 제출현황 관리") ----------
# 상·하반기로, 한 줄 = 그 반기에 걸친 계약(관급 = 용역 기간이 반기와 겹침, 민간 = 그 반기 회차 줄·끝 없는 계약).
# 칸: 관급 착수계·완수계(첨부 넣고 [만들기]로 PDF까지 = 제출로 봄, 프로그램 쓰기 전 낸 것은 "직접 제출함"), 민간 계약서(만듦·날인본),
# 계산서 발행일(민간 = 반기마다 "2026-하반기", 관급 = 계약 하나 "all"). 표시는 sitok_doc_contract.marks(0048).

def _doc_key(c: SitokDocContract, year: int, half: str, is_now: bool) -> str | None:
    """이 반기에 보일 계약이면 계산서 칸 열쇠, 아니면 None. 날짜가 없는 계약은 지금 반기에만."""
    from server.api.routers.sitok import half_range

    a, b = half_range(year, half)
    if c.sector == "관급":
        if c.start_date is None:
            return "all" if is_now else None
        return "all" if c.start_date <= b and (c.end_date or c.start_date) >= a else None
    key = f"{year}-{half}"
    rounds = c.rounds or []
    if any(r.get("year") == year and r.get("half") == half for r in rounds):
        return key
    if c.open_ended:
        return key if c.start_date is not None and c.start_date <= b else (key if c.start_date is None and is_now else None)
    if not rounds:
        if c.start_date is None:
            return key if is_now else None
        return key if c.start_date <= b and (c.end_date or c.start_date) >= a else None
    return None


@router.get("/docs")
def doc_rows(year: int | None = None, half: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from server.api.routers.sitok_docs import card_no, covered_ids, folder, half_auto, signed_pdf
    from server.sitok import civil

    y0, h0 = current_half()
    year, half = year or y0, half if half in HALVES else h0
    rows = []
    for c in db.query(SitokDocContract).filter(SitokDocContract.company_id == user.company_id).order_by(SitokDocContract.id):
        key = _doc_key(c, year, half, (year, half) == (y0, h0))
        if key is None:
            continue
        f = db.get(SitokFacility, c.facility_id) if c.facility_id else None
        mk = c.marks or {}
        made = lambda at: at.strftime("%Y-%m-%d") if at else ""  # noqa: E731
        signed = signed_pdf(c) is not None
        rows.append({
            "contract": {"id": c.id, "sector": c.sector, "title": c.title or civil.default_title(c), "half": c.half_tag or half_auto(c, f),
                         "period": f"{c.start_date or ''} ~ {'계약 해지 시까지' if c.open_ended else (c.end_date or '')}" if c.start_date else "",
                         "client": c.client},
            # 번호 = 서류 번호(계약이 시설물 여럿 = 관급-9, 하나 = 관급-9-1 — 10/15 민재형)
            "facility": {"id": f.id, "mgmt_no": card_no(db, c) or f.mgmt_no, "name": " · ".join(x.name for x in (db.get(SitokFacility, i) for i in covered_ids(c)) if x) or f.name,
                         "sector": f.sector or "민간", "badge_field": f.badge_field or "", "badge_kind": f.badge_kind or ""} if f is not None else None,
            "start": {"made": made(c.start_made_at) if c.sector == "관급" else made(c.made_at), "signed": signed if c.sector == "민간" else False,
                      "pdf": (folder(c) / "착수계.pdf").exists() if c.sector == "관급" else False, "mark": mk.get("start")},
            "done": {"made": made(c.done_made_at), "mark": mk.get("done")} if c.sector == "관급" else None,
            "invoice": {"key": key, "date": (mk.get("invoice") or {}).get(key) or ""},
        })
    return {"year": year, "half": half, "rows": rows}


class DocMarkIn(BaseModel):
    item: str  # start | done | invoice
    action: str = "done"  # done | clear
    date: str | None = None
    key: str | None = None  # 계산서 칸 열쇠("2026-하반기" / "all")


@router.post("/docs/{cid}/mark")
def doc_mark(cid: int, body: DocMarkIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.get(SitokDocContract, cid)
    if c is None or c.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "계약을 찾을 수 없습니다.")
    if body.item not in ("start", "done", "invoice") or body.action not in ("done", "clear"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "표시할 칸이 아닙니다.")
    try:
        day = datetime.date.fromisoformat(body.date) if body.date else datetime.date.today()
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "날짜가 맞지 않습니다.") from err
    mk = dict(c.marks or {})
    if body.item == "invoice":
        key = body.key or ("all" if c.sector == "관급" else "")
        if not key:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "계산서 반기가 없습니다.")
        inv = dict(mk.get("invoice") or {})
        if body.action == "clear":
            inv.pop(key, None)
        else:
            inv[key] = day.isoformat()
        mk["invoice"] = inv
    elif body.action == "clear":
        mk.pop(body.item, None)
    else:
        mk[body.item] = {"at": day.isoformat(), "by": user.display_name or ""}
    c.marks = mk
    db.commit()
    return {"ok": True, "marks": mk}
