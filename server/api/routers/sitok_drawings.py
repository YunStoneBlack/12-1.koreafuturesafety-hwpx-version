"""시특법 시설물 도면(2026-10-12 사용자, alembic 0039) — 저장은 시설물(다음 회차에도 그대로, 바뀌면 시설물 정보·서류 칸에서).
내용·보고서에 넣기는 server/sitok/drawings.py. 종류 attach(첨부 도면)·struct(구조일반사항)·schedule(구조 일람표, 10/14).

- `GET    …/drawings` — {attach: [...], struct: [...], schedule: [...]} (이름·올린 날·쪽 수).
- `POST   …/drawings` — form kind + file(PDF·그림, 여러 번).
- `DELETE …/drawings/{kind}/{did}`, `POST …/drawings/{kind}/{did}/move` {step: -1|1}, `GET …/drawings/{kind}/{did}/file`.
"…" = `/sitok/reports/{id}`(회차 번호로 — 현황 창·재료시험) 또는 `/sitok/facilities/{fid}`(10/14 시설물 정보·서류 칸, 3층 구조). 두 경로가 같은 함수(_get·_add·_delete·_move·_file)를 씀.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokFacility, SitokReport, User
from server.api.deps import get_current_user, get_db
from server.api.routers.sitok import _facility_dir, _require_facility
from server.api.routers.sitok_reports import _require
from server.sitok import drawings as D

router = APIRouter(prefix="/sitok", tags=["sitok"])


class MoveIn(BaseModel):
    step: int


def _by_report(db: Session, user: User, report_id: int) -> tuple[SitokFacility, Path]:
    r: SitokReport = _require(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    return f, _facility_dir(f)


def _by_facility(db: Session, user: User, facility_id: int) -> tuple[SitokFacility, Path]:
    f = _require_facility(db, user, facility_id)
    return f, _facility_dir(f)


def _kind(kind: str) -> str:
    if kind not in D.KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "도면 종류가 맞지 않습니다.")
    return kind


def _out(f: SitokFacility, base: Path) -> dict:
    return {k: [{"id": it["id"], "name": it["name"], "at": it.get("at", ""), "pages": D.pages_of(it["path"]), "pdf": it["path"].suffix.lower() == ".pdf"}
                for it in D.items(f, k, base)] for k in D.KINDS}


# ---- 공통 동작 ----

def _get(f: SitokFacility, base: Path) -> dict:
    return _out(f, base)


def _add(db: Session, f: SitokFacility, base: Path, kind: str, file: UploadFile) -> dict:
    try:
        D.add(f, _kind(kind), base, file.file.read(), file.filename or "도면")
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
    db.commit()
    return _out(f, base)


def _delete(db: Session, f: SitokFacility, base: Path, kind: str, did: str) -> dict:
    D.remove(f, _kind(kind), base, did)
    db.commit()
    return _out(f, base)


def _move(db: Session, f: SitokFacility, base: Path, kind: str, did: str, step: int) -> dict:
    D.move(f, _kind(kind), did, 1 if step > 0 else -1)
    db.commit()
    return _out(f, base)


def _file(f: SitokFacility, base: Path, kind: str, did: str) -> FileResponse:
    it = next((x for x in D.items(f, _kind(kind), base) if x["id"] == did), None)
    if it is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "도면이 없습니다.")
    p = it["path"]
    return FileResponse(p, media_type="application/pdf" if p.suffix.lower() == ".pdf" else "image/jpeg", content_disposition_type="inline",
                        filename=it["name"])


# ---- 회차 id 경로 ----

@router.get("/reports/{report_id}/drawings")
def get_drawings(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _get(*_by_report(db, user, report_id))


@router.post("/reports/{report_id}/drawings")
def add_drawing(report_id: int, kind: str = Form(...), file: UploadFile = File(...), user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    return _add(db, *_by_report(db, user, report_id), kind, file)


@router.delete("/reports/{report_id}/drawings/{kind}/{did}")
def delete_drawing(report_id: int, kind: str, did: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _delete(db, *_by_report(db, user, report_id), kind, did)


@router.post("/reports/{report_id}/drawings/{kind}/{did}/move")
def move_drawing(report_id: int, kind: str, did: str, body: MoveIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _move(db, *_by_report(db, user, report_id), kind, did, body.step)


@router.get("/reports/{report_id}/drawings/{kind}/{did}/file")
def drawing_file(report_id: int, kind: str, did: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _file(*_by_report(db, user, report_id), kind, did)


# ---- 시설물 id 경로(10/14) ----

@router.get("/facilities/{facility_id}/drawings")
def get_drawings_f(facility_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _get(*_by_facility(db, user, facility_id))


@router.post("/facilities/{facility_id}/drawings")
def add_drawing_f(facility_id: int, kind: str = Form(...), file: UploadFile = File(...), user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    return _add(db, *_by_facility(db, user, facility_id), kind, file)


@router.delete("/facilities/{facility_id}/drawings/{kind}/{did}")
def delete_drawing_f(facility_id: int, kind: str, did: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _delete(db, *_by_facility(db, user, facility_id), kind, did)


@router.post("/facilities/{facility_id}/drawings/{kind}/{did}/move")
def move_drawing_f(facility_id: int, kind: str, did: str, body: MoveIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _move(db, *_by_facility(db, user, facility_id), kind, did, body.step)


@router.get("/facilities/{facility_id}/drawings/{kind}/{did}/file")
def drawing_file_f(facility_id: int, kind: str, did: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _file(*_by_facility(db, user, facility_id), kind, did)
