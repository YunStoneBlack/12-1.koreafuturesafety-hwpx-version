"""시특법 시설물 도면(2026-10-12 사용자, alembic 0039) — 시설물 현황 창에서(회차 번호로 부르지만 저장은 시설물: 다음 회차에도 그대로, 바뀌면 여기서).
내용·보고서에 넣기는 server/sitok/drawings.py.

- `GET    /sitok/reports/{id}/drawings` — {attach: [...], struct: [...]} (이름·올린 날·쪽 수).
- `POST   /sitok/reports/{id}/drawings` — form kind(attach|struct) + file(PDF·그림, 여러 번).
- `DELETE /sitok/reports/{id}/drawings/{kind}/{did}`, `POST .../{kind}/{did}/move` {step: -1|1}, `GET .../{kind}/{did}/file`.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokFacility, SitokReport, User
from server.api.deps import get_current_user, get_db
from server.api.routers.sitok import _facility_dir
from server.api.routers.sitok_reports import _require
from server.sitok import drawings as D

router = APIRouter(prefix="/sitok", tags=["sitok"])


def _fac(db: Session, user: User, report_id: int) -> tuple[SitokFacility, Path]:
    r: SitokReport = _require(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    return f, _facility_dir(f)


def _kind(kind: str) -> str:
    if kind not in D.KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "도면 종류가 맞지 않습니다.")
    return kind


def _out(f: SitokFacility, base: Path) -> dict:
    return {k: [{"id": it["id"], "name": it["name"], "at": it.get("at", ""), "pages": D.pages_of(it["path"]), "pdf": it["path"].suffix.lower() == ".pdf"}
                for it in D.items(f, k, base)] for k in D.KINDS}


@router.get("/reports/{report_id}/drawings")
def get_drawings(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f, base = _fac(db, user, report_id)
    return _out(f, base)


@router.post("/reports/{report_id}/drawings")
def add_drawing(report_id: int, kind: str = Form(...), file: UploadFile = File(...), user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    f, base = _fac(db, user, report_id)
    try:
        D.add(f, _kind(kind), base, file.file.read(), file.filename or "도면")
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
    db.commit()
    return _out(f, base)


@router.delete("/reports/{report_id}/drawings/{kind}/{did}")
def delete_drawing(report_id: int, kind: str, did: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f, base = _fac(db, user, report_id)
    D.remove(f, _kind(kind), base, did)
    db.commit()
    return _out(f, base)


class MoveIn(BaseModel):
    step: int


@router.post("/reports/{report_id}/drawings/{kind}/{did}/move")
def move_drawing(report_id: int, kind: str, did: str, body: MoveIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f, base = _fac(db, user, report_id)
    D.move(f, _kind(kind), did, 1 if body.step > 0 else -1)
    db.commit()
    return _out(f, base)


@router.get("/reports/{report_id}/drawings/{kind}/{did}/file")
def drawing_file(report_id: int, kind: str, did: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f, base = _fac(db, user, report_id)
    it = next((x for x in D.items(f, _kind(kind), base) if x["id"] == did), None)
    if it is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "도면이 없습니다.")
    p = it["path"]
    return FileResponse(p, media_type="application/pdf" if p.suffix.lower() == ".pdf" else "image/jpeg", content_disposition_type="inline",
                        filename=it["name"])
