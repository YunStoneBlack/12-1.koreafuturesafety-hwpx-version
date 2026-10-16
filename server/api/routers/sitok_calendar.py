"""보고서 자동화 · 시특법 — 방문 달력(2026-10-15 민재형 문서번호 일치화 문서 "보고서 달력관리"). 계산은 server/sitok/visit_plan.py.

- `GET /sitok/calendar?start=&end=` — 그 사이 점검 날(시설물 카드·반기·종류·지역·상태) + 날마다 건물 수 + 일정 없는 반기 수
- `POST /sitok/calendar/visits` {facility_id, plan_date, kind?} — 사람이 날 넣기(📌, 같은 반기에 더 넣기도)
- `PATCH /sitok/calendar/visits/{id}` {plan_date?, memo?} — 날 바꾸기(끌어 옮기기 → 📌)
- `DELETE /sitok/calendar/visits/{id}`
- `GET /sitok/calendar/missing` — 일정 없는 반기 목록(계약기간 안인데 날이 없음)
- `POST /sitok/calendar/fill` {dry_run, facility_ids?} — 자동으로 잡기(미리보기 → 잡기). 이미 있는 날은 안 건드림.
"""
from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokFacility, SitokReport, SitokVisit, User
from server.api.deps import get_current_user, get_db
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
            "phone": f.contact_phone or f.owner_phone, "contract_type": f.contract_type, "members": [{"id": m.id, "name": m.name} for m in u.members]}


def _state(db: Session, v: SitokVisit, u: V.Unit, today: datetime.date) -> tuple[str, int | None]:
    r = db.query(SitokReport).filter(SitokReport.facility_id.in_(u.ids), SitokReport.year == v.year, SitokReport.half == v.half).order_by(SitokReport.id).first()
    if r is not None and r.status == "done":
        return "done", r.id
    return ("missed" if v.plan_date < today else "planned"), (r.id if r is not None else None)


def _visit_out(db: Session, v: SitokVisit, u: V.Unit, today: datetime.date) -> dict:
    st, rid = _state(db, v, u, today)
    return {"id": v.id, "date": v.plan_date.isoformat(), "year": v.year, "half": v.half, "kind": v.kind, "pinned": v.source == "manual",
            "memo": v.memo, "state": st, "report_id": rid, "facility": _unit_out(u)}


@router.get("")
def calendar(start: datetime.date, end: datetime.date, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if (end - start).days > 70:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "한 번에 70일까지 봅니다.")
    today = datetime.date.today()
    um = _unit_map(db, user.company_id)
    rows = db.query(SitokVisit).filter(SitokVisit.company_id == user.company_id, SitokVisit.plan_date >= start, SitokVisit.plan_date < end).order_by(SitokVisit.plan_date, SitokVisit.id).all()
    visits = [_visit_out(db, v, um[v.facility_id], today) for v in rows if v.facility_id in um]
    load: dict[str, int] = {}
    for x in visits:
        load[x["date"]] = load.get(x["date"], 0) + x["facility"]["buildings"]
    miss = V.missing(db, user.company_id, today)
    return {"visits": visits, "day_load": load, "day_cap": V.DAY_CAP, "missing": len(miss), "missing_units": len({n.unit.lead.id for n in miss}),
            "facilities": [_unit_out(u) for u in {id(u): u for u in um.values()}.values()]}


class VisitIn(BaseModel):
    facility_id: int
    plan_date: datetime.date
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
                   source="manual", memo=(body.memo or "").strip(), created_by=user.display_name or "")
    db.add(v)
    db.commit()
    return _visit_out(db, v, u or V.Unit(f, [f], f.name, V.region_of(f.address)), datetime.date.today())


class VisitPatch(BaseModel):
    plan_date: datetime.date | None = None
    memo: str | None = None
    kind: str | None = None


def _require(db: Session, user: User, vid: int) -> SitokVisit:
    v = db.get(SitokVisit, vid)
    if v is None or v.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "일정을 찾을 수 없습니다.")
    return v


@router.patch("/visits/{vid}")
def patch_visit(vid: int, body: VisitPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    v = _require(db, user, vid)
    if body.plan_date is not None and body.plan_date != v.plan_date:
        v.plan_date = body.plan_date
        v.year, v.half = V.slot_of(db, _unit_map(db, user.company_id).get(v.facility_id), body.plan_date)  # 다른 반기(연 3회면 시기)로 옮기면 그 점검이 됨
        v.source = "manual"  # 사람이 옮긴 날 = 📌(자동 배치가 안 건드림)
    if body.memo is not None:
        v.memo = body.memo.strip()
    if body.kind in ("정기", "정밀"):
        v.kind = body.kind
    db.commit()
    um = _unit_map(db, user.company_id)
    return _visit_out(db, v, um[v.facility_id], datetime.date.today())


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
