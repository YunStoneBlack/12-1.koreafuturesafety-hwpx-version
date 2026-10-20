"""보고서 자동화 · 시특법 — 방문 달력(2026-10-15 민재형 문서번호 일치화 문서 "보고서 달력관리"). 계산은 server/sitok/visit_plan.py.

- `GET /sitok/calendar?start=&end=` — 그 사이 점검 날(시설물 카드·반기·종류·지역·상태) + 날마다 건물 수 + 일정 없는 반기 수
- `POST /sitok/calendar/visits` {facility_id, plan_date, plan_end?, kind?} — 사람이 날 넣기(📌, 같은 반기에 더 넣기도)
- `PATCH /sitok/calendar/visits/{id}` {plan_date?, plan_end?, memo?} — 날 바꾸기(끌어 옮기기 → 📌). 시작만 바꾸면 기간 그대로 옮김.
  일정은 범위(시작~끝, 10/19 민재형 "일정을 범위 설정 가능하도록, 디폴트 10.30~10.30") — 끝이 비면 하루, 하루 건물 수는 날마다 나눠 셈(visit_plan.day_share).
- `DELETE /sitok/calendar/visits/{id}`
- `PATCH /sitok/calendar/visits/{id}/site-contact` {manager?, phone} — 카드의 현장 담당 연락처 = 서류 자동화 계약 정보 "현장 담당"을 바로 고침
  (10/20 민재형 "달력 전화번호는 현장 담당 번호로, 없으면 등록 버튼, 달력에서 고치면 계약 정보도 같이" — 시설물 칸 관리주체·담당자 전화는 안 씀)
- `GET /sitok/calendar/missing` — 일정 없는 반기 목록(계약기간 안인데 날이 없음)
- `POST /sitok/calendar/fill` {dry_run, facility_ids?} — 자동으로 잡기(미리보기 → 잡기). 이미 있는 날은 안 건드림.
"""
from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.models_web import SitokDocContract, SitokFacility, SitokReport, SitokVisit, User
from server.api.deps import get_current_user, get_db
from server.api.routers.sitok_docs import contract_index, site_contract, site_phone
from server.sitok import visit_plan as V

router = APIRouter(prefix="/sitok/calendar", tags=["sitok-calendar"])


def _unit_map(db: Session, company_id: int) -> dict[int, V.Unit]:
    out = {}
    for u in V.units(db, company_id, with_ended=True):
        for m in u.members:
            out[m.id] = u
    return out


def _unit_out(u: V.Unit) -> dict:
    f = u.lead
    return {"id": f.id, "mgmt_no": f.mgmt_no, "name": u.name, "sector": f.sector or "민간", "badge_field": f.badge_field or "",
            "badge_kind": f.badge_kind or "", "region": u.region, "address": f.address, "buildings": u.buildings,
            "contract_type": f.contract_type, "members": [{"id": m.id, "name": m.name} for m in u.members]}


def _state(db: Session, v: SitokVisit, u: V.Unit, today: datetime.date) -> tuple[str, int | None]:
    """done = 보고서 만듦(밖에서 완료 포함, 진하게) · field = 현장점검 완료(채운 칸 — 10/18 형 "산안법 달력처럼") · missed = 지난 날 · planned = 빈 칸."""
    reps = db.query(SitokReport).filter(SitokReport.facility_id.in_(u.ids), SitokReport.year == v.year, SitokReport.half == v.half).order_by(SitokReport.id).all()
    rid = reps[0].id if reps else None
    if any(x.status == "done" or (x.submit or {}).get("report") for x in reps):
        return "done", rid
    if any((x.submit or {}).get("field") for x in reps):
        return "field", rid
    return ("missed" if V.visit_span(v)[1] < today else "planned"), rid


def _site_out(c: SitokDocContract | None) -> dict | None:
    if c is None:
        return None
    return {"cid": c.id, "manager": c.site_manager or "", "phone": c.site_phone or "", "title": c.title or ""}


def _visit_out(db: Session, v: SitokVisit, u: V.Unit, today: datetime.date, cons: list | None = None) -> dict:
    st, rid = _state(db, v, u, today)
    cons = cons if cons is not None else contract_index(db, v.company_id)
    return {"id": v.id, "date": v.plan_date.isoformat(), "end": V.visit_span(v)[1].isoformat(), "year": v.year, "half": v.half, "kind": v.kind, "pinned": v.source == "manual",
            "memo": v.memo, "state": st, "report_id": rid, "facility": _unit_out(u), "site": _site_out(site_contract(cons, set(u.ids), v.year, v.half)),
            "phone": site_phone(cons, set(u.ids), u.lead.owner_phone, v.year, v.half)}  # 현장 담당, 비면 관리주체 전화(10/20)


@router.get("")
def calendar(start: datetime.date, end: datetime.date, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if (end - start).days > 70:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "한 번에 70일까지 봅니다.")
    today = datetime.date.today()
    um = _unit_map(db, user.company_id)
    rows = db.query(SitokVisit).filter(SitokVisit.company_id == user.company_id, SitokVisit.plan_date < end,
                                       func.coalesce(SitokVisit.plan_end, SitokVisit.plan_date) >= start).order_by(SitokVisit.plan_date, SitokVisit.id).all()
    cons = contract_index(db, user.company_id)
    visits = [_visit_out(db, v, um[v.facility_id], today, cons) for v in rows if v.facility_id in um]
    load: dict[str, int] = {}
    for v in rows:
        if v.facility_id in um:
            for d, n in V.day_share(v, um[v.facility_id].buildings):  # 여러 날 일정은 날마다 나눠(10/19)
                load[d.isoformat()] = load.get(d.isoformat(), 0) + n
    miss = V.missing(db, user.company_id, today)
    return {"visits": visits, "day_load": load, "day_cap": V.DAY_CAP, "missing": len(miss), "missing_units": len({n.unit.lead.id for n in miss}),
            "facilities": [_unit_out(u) for u in {id(u): u for u in um.values()}.values()]}


class VisitIn(BaseModel):
    facility_id: int
    plan_date: datetime.date
    plan_end: datetime.date | None = None
    kind: str | None = None
    memo: str | None = None


@router.post("/visits")
def add_visit(body: VisitIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = db.get(SitokFacility, body.facility_id)
    if f is None or f.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "시설물을 찾을 수 없습니다.")
    um = _unit_map(db, user.company_id)
    u = um.get(f.id)
    y, h = V.slot_of(db, u, body.plan_date)  # 반기, 연 3회 시설물이면 그 날이 드는 해빙기·우기·동절기(10/16)
    kind = body.kind if body.kind in ("정기", "정밀") else None
    if kind is None:  # 그 반기 할 일(계약)의 종류, 없으면 그 반기 다른 날의 종류, 없으면 정기
        need = next((n for n in V.needs_for(db, u, min(datetime.date.today(), body.plan_date - V.DAY)) if n.key == (y, h)), None) if u else None
        old = db.query(SitokVisit).filter(SitokVisit.facility_id.in_(u.ids if u else [f.id]), SitokVisit.year == y, SitokVisit.half == h).first()
        kind = need.kind if need else old.kind if old else "정기"
    v = SitokVisit(company_id=user.company_id, facility_id=(u.lead.id if u else f.id), year=y, half=h, kind=kind, plan_date=body.plan_date,
                   plan_end=_end(body.plan_date, body.plan_end), source="manual", memo=(body.memo or "").strip(), created_by=user.display_name or "")
    db.add(v)
    db.commit()
    return _visit_out(db, v, u or V.Unit(f, [f], f.name, V.region_of(f.address)), datetime.date.today())


class VisitPatch(BaseModel):
    plan_date: datetime.date | None = None
    plan_end: datetime.date | None = None
    memo: str | None = None
    kind: str | None = None


def _end(start: datetime.date, end: datetime.date | None) -> datetime.date | None:
    """끝 날 — 비거나 시작과 같으면 None(하루), 시작보다 앞이면 400."""
    if end is None or end == start:
        return None
    if end < start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "끝 날이 시작 날보다 앞입니다.")
    return end


def _require(db: Session, user: User, vid: int) -> SitokVisit:
    v = db.get(SitokVisit, vid)
    if v is None or v.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "일정을 찾을 수 없습니다.")
    return v


@router.patch("/visits/{vid}")
def patch_visit(vid: int, body: VisitPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    v = _require(db, user, vid)
    start, end = V.visit_span(v)
    if body.plan_date is not None and body.plan_date != v.plan_date:
        if body.plan_end is None and v.plan_end:  # 시작만 옮기면 기간 그대로(끌어 옮기기)
            v.plan_end = body.plan_date + (end - start)
        v.plan_date = body.plan_date
        v.year, v.half = V.slot_of(db, _unit_map(db, user.company_id).get(v.facility_id), body.plan_date)  # 다른 반기(연 3회면 시기)로 옮기면 그 점검이 됨
        v.source = "manual"  # 사람이 옮긴 날 = 📌(자동 배치가 안 건드림)
    if body.plan_end is not None:
        v.plan_end = _end(v.plan_date, body.plan_end)
        v.source = "manual"
    if body.memo is not None:
        v.memo = body.memo.strip()
    if body.kind in ("정기", "정밀"):
        v.kind = body.kind
    db.commit()
    um = _unit_map(db, user.company_id)
    return _visit_out(db, v, um[v.facility_id], datetime.date.today())


class SiteContactIn(BaseModel):
    phone: str
    manager: str | None = None


@router.patch("/visits/{vid}/site-contact")
def site_contact(vid: int, body: SiteContactIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """카드의 현장 담당 연락처 → 서류 자동화 계약 정보 "현장 담당"(SitokDocContract.site_manager·site_phone)을 바로 고침(10/20 민재형).
    계약 저장(put_contract)의 카드 정리 같은 일은 안 함 — 이 두 칸만."""
    v = _require(db, user, vid)
    um = _unit_map(db, user.company_id)
    f = db.get(SitokFacility, v.facility_id)
    u = um.get(v.facility_id) or V.Unit(f, [f], f.name, V.region_of(f.address))
    c = site_contract(contract_index(db, user.company_id), set(u.ids), v.year, v.half)
    if c is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "이 시설물의 계약이 서류 자동화에 없습니다 — 계약을 먼저 넣으면 현장 담당 연락처를 등록할 수 있습니다.")
    c.site_phone = body.phone.strip()
    if body.manager is not None:
        c.site_manager = body.manager.strip()
    c.updated_at, c.updated_by = datetime.datetime.now(), user.display_name or ""
    db.commit()
    return _site_out(c)


@router.delete("/visits/{vid}")
def delete_visit(vid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    v = _require(db, user, vid)
    db.delete(v)
    db.commit()
    return {"ok": True}


def _need_out(n: V.Need) -> dict:
    return {"facility": _unit_out(n.unit), "year": n.year, "half": n.half, "kind": n.kind, "start": n.start.isoformat(), "end": n.end.isoformat(), "why": n.why}


@router.get("/missing")
def get_missing(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"missing": [_need_out(n) for n in V.missing(db, user.company_id)]}


class FillIn(BaseModel):
    dry_run: bool = True
    facility_ids: list[int] | None = None


@router.post("/fill")
def fill(body: FillIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    planned = V.plan(db, user.company_id, V.missing(db, user.company_id, facility_ids=body.facility_ids))
    out = [{**_need_out(p["need"]), "date": p["date"].isoformat() if p["date"] else None, "note": p["note"]} for p in planned]
    if not body.dry_run:
        V.apply(db, user.company_id, planned, user.display_name or "")
        db.commit()
    return {"planned": out, "applied": not body.dry_run}
