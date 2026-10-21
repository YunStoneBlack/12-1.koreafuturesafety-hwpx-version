"""시특법 동 묶음(2026-10-12 판 다시 잡기 ② — 한 계약에 여러 동을 한 보고서로, 견본 숭의교회 본관 + B동).

동마다 시설물·회차는 따로(현장 조사·전경·현황·면담·AI 초안은 동별), 보고서를 만들 때 한 권으로 합침(sitok_reports._run_group_build,
server/sitok/merge.py). 한 번 묶이면 다음 회차도 계속 묶임(사용자 10/12).

- `GET  /sitok/facilities/{id}/group` — 묶음(이름·동 순서) + 더 묶을 수 있는 시설물.
- `POST /sitok/facilities/{id}/group` — {facility_id}: 이 시설물 묶음에 동 더하기(묶음이 없으면 새로, 이름 = 이 시설물 이름).
- `PATCH /sitok/groups/{id}` — {name}. `POST /sitok/groups/{id}/order` — {facility_ids}: 순서(첫 동 = 대표·시설물편 제1장).
- `DELETE /sitok/groups/{id}/members/{facility_id}` — 묶음에서 빼기(한 동만 남으면 묶음 없앰).
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokFacility, SitokGroup, User
from server.api.deps import get_current_user, get_db
from server.api.routers.sitok import _require_facility

router = APIRouter(prefix="/sitok", tags=["sitok"])


def members(db: Session, group_id: int | None) -> list[SitokFacility]:
    if not group_id:
        return []
    return db.query(SitokFacility).filter(SitokFacility.group_id == group_id).order_by(SitokFacility.group_order, SitokFacility.id).all()


def group_out(db: Session, f: SitokFacility) -> dict | None:
    if not f.group_id:
        return None
    g = db.get(SitokGroup, f.group_id)
    ms = members(db, f.group_id)
    from server.sitok import kinds as _kinds

    return {"id": g.id, "name": g.name, "members": [{"id": m.id, "name": m.name, "template": m.template, "kind": _kinds.civil_kind(m) or "건물"} for m in ms],
            "lead": bool(ms) and ms[0].id == f.id, "index": next((i for i, m in enumerate(ms, 1) if m.id == f.id), 0)}


def _require_group(db: Session, user: User, group_id: int) -> SitokGroup:
    g = db.get(SitokGroup, group_id)
    if g is None or g.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "묶음을 찾을 수 없습니다.")
    return g


def _renumber(db: Session, group_id: int) -> None:
    for i, m in enumerate(members(db, group_id)):
        m.group_order = i


@router.get("/facilities/{facility_id}/group")
def get_group(facility_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = _require_facility(db, user, facility_id)
    free = (db.query(SitokFacility).filter(SitokFacility.company_id == user.company_id, SitokFacility.group_id.is_(None), SitokFacility.id != f.id, SitokFacility.survey_only.is_(False))
            .order_by(SitokFacility.name).all())
    return {"group": group_out(db, f), "candidates": [{"id": x.id, "name": x.name, "owner": x.owner_name, "address": x.address} for x in free]}


class AddIn(BaseModel):
    facility_id: int  # 더할 동


@router.post("/facilities/{facility_id}/group")
def add_member(facility_id: int, body: AddIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = _require_facility(db, user, facility_id)
    other = _require_facility(db, user, body.facility_id)
    if other.id == f.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "같은 시설물입니다.")
    if other.group_id and other.group_id != f.group_id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{other.name}은(는) 이미 다른 묶음에 있습니다 — 거기서 먼저 빼세요.")
    if not f.group_id:
        g = SitokGroup(company_id=user.company_id, name=f.name)
        db.add(g)
        db.flush()
        f.group_id, f.group_order = g.id, 0
    other.group_id = f.group_id
    other.group_order = max((m.group_order for m in members(db, f.group_id)), default=0) + 1
    db.commit()
    return get_group(facility_id, user, db)


@router.patch("/groups/{group_id}")
def rename_group(group_id: int, name: str = Body(..., embed=True), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = _require_group(db, user, group_id)
    if not name.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "묶음 이름을 넣어 주세요.")
    g.name = name.strip()
    db.commit()
    return {"id": g.id, "name": g.name}


@router.post("/groups/{group_id}/order")
def reorder(group_id: int, facility_ids: list[int] = Body(..., embed=True), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_group(db, user, group_id)
    ms = {m.id: m for m in members(db, group_id)}
    if set(facility_ids) != set(ms):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "묶음의 동을 모두 넣어 주세요.")
    for i, fid in enumerate(facility_ids):
        ms[fid].group_order = i
    db.commit()
    return {"ok": True}


@router.delete("/groups/{group_id}/members/{facility_id}")
def remove_member(group_id: int, facility_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = _require_group(db, user, group_id)
    f = _require_facility(db, user, facility_id)
    if f.group_id != g.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "그 묶음의 동이 아닙니다.")
    f.group_id, f.group_order = None, 0
    db.flush()
    rest = members(db, g.id)
    if len(rest) <= 1:
        for m in rest:
            m.group_id, m.group_order = None, 0
        db.flush()
        db.delete(g)
    else:
        _renumber(db, g.id)
    db.commit()
    return {"ok": True}
