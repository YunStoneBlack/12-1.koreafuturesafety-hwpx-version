"""시특법 설정(2026-10-10 3단계, sitok-settings.html) — 보고서 앞부분·부록에 자동으로 들어가는 회사·기술자 서류와 사용 장비.

- `GET    /sitok/settings` — 전부(회사 서류·기술자·장비).
- `POST|DELETE /sitok/settings/company/{kind}` — 회사 서류 그림(안전진단전문기관 등록증, 유효기간 칸).
- `PATCH  /sitok/settings/persons/{id}` — 기술자 시특법 칸(분야·결과표 기술등급). 기술자 추가·이름·직위·등급은 서류 자동화와 같은
  `/contract-docs/persons`(같은 사람을 산안법 착수계와 같이 씀).
- `POST|DELETE /sitok/settings/persons/{id}/docs/{kind}` — 기술자 시특법 서류(정밀안전진단 교육 수료증·책임기술자 자격, 유효기간 칸).
- `POST /sitok/settings/equipment`, `PATCH|DELETE /sitok/settings/equipment/{id}`, `POST .../{id}/photo`, `GET .../photo/{n}` — 사용 장비(1.6 표).
서류 그림·유효기간 저장은 서류 자동화(contract_library)와 같은 표(SubmitDoc)·같은 함수 — 종류 이름만 시특법 것(SITOK_*).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokEquipment, TechPerson, User
from core.stored_path import to_full, to_stored
from server.api import storage
from server.api.deps import get_current_user, get_db
from server.api.routers import contract_library as lib
from server.api.routers.sitok import ROOT
from server.contract_docs import files

router = APIRouter(prefix="/sitok/settings", tags=["sitok"])
# 서류 종류 — SubmitDoc.kind(서류 자동화의 build.COMPANY_DOCS·PERSON_DOCS와 이름이 겹치지 않게 sitok_ 붙임)
SITOK_COMPANY_DOCS = [("sitok_reg", "안전진단전문기관 등록증")]
SITOK_PERSON_DOCS = [("sitok_edu", "정밀안전진단 교육 수료증"), ("sitok_license", "책임기술자 자격")]
COMPANY_LABELS = dict(SITOK_COMPANY_DOCS)
PERSON_LABELS = dict(SITOK_PERSON_DOCS)
EQUIP_DIR = ROOT / "장비"


def _person_out(db: Session, p: TechPerson) -> dict:
    docs = lib.person_docs(db, p.id)
    return {"id": p.id, "name": p.name, "position": p.position, "grade": p.grade, "qualification": p.qualification, "active": p.active,
            "sitok_field": p.sitok_field, "sitok_grade": p.sitok_grade,
            "docs": [lib.doc_out(docs.get(k), k, label) for k, label in SITOK_PERSON_DOCS]}


def _equip_out(e: SitokEquipment) -> dict:
    return {"id": e.id, "grp": e.grp, "name": e.name, "model": e.model, "purpose": e.purpose, "active": e.active, "sort": e.sort,
            "photos": len(e.photos or []), "ts": abs(hash(tuple(e.photos or []))) % 100000}


def equipment(db: Session, company_id: int) -> list[SitokEquipment]:
    return db.query(SitokEquipment).filter(SitokEquipment.company_id == company_id).order_by(SitokEquipment.sort, SitokEquipment.id).all()


@router.get("")
def get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    docs = lib.company_docs(db, user.company_id)
    return {
        "company_docs": [lib.doc_out(docs.get(k), k, label) for k, label in SITOK_COMPANY_DOCS],
        "persons": [_person_out(db, p) for p in lib.persons(db, user.company_id)],
        "equipment": [_equip_out(e) for e in equipment(db, user.company_id)],
    }


@router.post("/company/{kind}")
def upload_company_doc(kind: str, file: UploadFile = File(...), issued_on: str = Form(""), valid_until: str = Form(""),
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if kind not in COMPANY_LABELS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 서류 종류입니다.")
    return lib._upload_dated(db, user, file, kind, COMPANY_LABELS[kind], files.company_doc_path(COMPANY_LABELS[kind]),
                             lib.company_docs(db, user.company_id).get(kind), None, issued_on, valid_until)


@router.delete("/company/{kind}")
def delete_company_doc(kind: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if kind not in COMPANY_LABELS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 서류 종류입니다.")
    lib._drop_doc(db, lib.company_docs(db, user.company_id).get(kind))
    return {"ok": True}


class PersonSitokIn(BaseModel):
    sitok_field: str | None = None
    sitok_grade: str | None = None


@router.patch("/persons/{person_id}")
def update_person(person_id: int, body: PersonSitokIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = lib._require_person(db, user, person_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, (v or "").strip())
    db.commit()
    return _person_out(db, p)


@router.post("/persons/{person_id}/docs/{kind}")
def upload_person_doc(person_id: int, kind: str, file: UploadFile = File(...), issued_on: str = Form(""), valid_until: str = Form(""),
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = lib._require_person(db, user, person_id)
    if kind not in PERSON_LABELS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 서류 종류입니다.")
    lib._upload_dated(db, user, file, kind, PERSON_LABELS[kind], files.person_doc_path(p.id, p.name, PERSON_LABELS[kind]),
                      lib.person_docs(db, p.id).get(kind), p.id, issued_on, valid_until)
    return _person_out(db, p)


@router.delete("/persons/{person_id}/docs/{kind}")
def delete_person_doc(person_id: int, kind: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = lib._require_person(db, user, person_id)
    if kind not in PERSON_LABELS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 서류 종류입니다.")
    lib._drop_doc(db, lib.person_docs(db, p.id).get(kind))
    return _person_out(db, p)


class EquipIn(BaseModel):
    grp: str | None = None
    name: str | None = None
    model: str | None = None
    purpose: str | None = None
    sort: int | None = None
    active: bool | None = None


def _require_equip(db: Session, user: User, equip_id: int) -> SitokEquipment:
    e = db.get(SitokEquipment, equip_id)
    if e is None or e.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "장비를 찾을 수 없습니다.")
    return e


@router.post("/equipment")
def add_equipment(body: EquipIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    last = max((e.sort for e in equipment(db, user.company_id)), default=0)
    e = SitokEquipment(company_id=user.company_id, sort=last + 1)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(e, k, v.strip() if isinstance(v, str) else v)
    db.add(e)
    db.commit()
    return _equip_out(e)


@router.patch("/equipment/{equip_id}")
def update_equipment(equip_id: int, body: EquipIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    e = _require_equip(db, user, equip_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(e, k, v.strip() if isinstance(v, str) else v)
    db.commit()
    return _equip_out(e)


@router.delete("/equipment/{equip_id}")
def delete_equipment(equip_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    e = _require_equip(db, user, equip_id)
    for p in e.photos or []:
        Path(to_full(p)).unlink(missing_ok=True)
    db.delete(e)
    db.commit()
    return {"ok": True}


@router.post("/equipment/{equip_id}/photo")
def upload_equipment_photo(equip_id: int, file: UploadFile = File(...), replace: bool = Form(True),
                           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """장비 사진 — replace면 있던 사진을 지우고 이 한 장으로, 아니면 덧붙임(표 칸엔 1~2장)."""
    e = _require_equip(db, user, equip_id)
    jpeg = files.to_jpeg(file.file.read(), file.filename or "")
    old = list(e.photos or [])
    if replace:
        for p in old:
            Path(to_full(p)).unlink(missing_ok=True)
        old = []
    dest = EQUIP_DIR / f"{storage._clean(e.name)[:20] or '장비'}_{e.id}_{len(old) + 1}.jpg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(jpeg)
    e.photos = old + [to_stored(str(dest))]
    db.commit()
    return _equip_out(e)


@router.get("/equipment/{equip_id}/photo/{n}")
def equipment_photo(equip_id: int, n: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    e = _require_equip(db, user, equip_id)
    photos = e.photos or []
    if not 0 <= n < len(photos) or not Path(to_full(photos[n])).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return FileResponse(to_full(photos[n]), media_type="image/jpeg")
