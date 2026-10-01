"""3. 전경사진 및 점검사진 — 전경(표4)/점검(표5) 각각 최대 4칸, 완전히 같은 모양이라
`_build_slot_router()` 하나로 두 카테고리(overview/inspection) 라우터를 둘 다 찍어낸다.

저장 경로는 server/api/storage.py 규칙(2026-10-01): `현장\05회차\사진\현장_05회차_전경사진1.jpg`."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from core.models_db import InspectionPhoto, OverviewPhoto, Report
from core.models_web import User
from server.api import repo, storage
from server.api.deps import get_current_user, get_db
from server.api.photo_thumbs import photo_response

_ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_SLOT_RANGE = range(1, 5)  # 1~4


def _build_slot_router(category: str, model_cls, label: str) -> APIRouter:
    router = APIRouter(prefix=f"/reports/{{report_id}}/{category}-photos", tags=["photos"])

    def _require_report(db: Session, company_id: int, report_id: int) -> Report:
        report = repo.get_report(db, company_id, report_id)
        if report is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
        return report

    def _require_slot(slot: int) -> None:
        if slot not in _SLOT_RANGE:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "slot은 1~4여야 합니다.")

    @router.get("")
    def list_slots(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
        _require_report(db, user.company_id, report_id)
        rows = db.query(model_cls).filter(model_cls.report_id == report_id).all()
        return [{"slot": r.slot} for r in rows if r.photo_path]

    @router.post("/{slot}")
    async def upload_slot(
        report_id: int,
        slot: int,
        file: UploadFile,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        report = _require_report(db, user.company_id, report_id)
        _require_slot(slot)
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in _ALLOWED_SUFFIXES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{label}은(는) 이미지 파일만 업로드할 수 있습니다.")

        dest = storage.photo_path(db, report, f"{label}{slot}", suffix)
        dest.write_bytes(await file.read())
        old = repo.get_photo_slot(db, model_cls, report_id, slot)
        storage.drop_old(old.photo_path if old else "", dest)

        repo.upsert_photo_slot(db, model_cls, report_id, slot, str(dest))
        return {"slot": slot, "ok": True}

    @router.delete("/{slot}")
    def delete_slot(
        report_id: int, slot: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
    ):
        _require_report(db, user.company_id, report_id)
        _require_slot(slot)
        row = repo.get_photo_slot(db, model_cls, report_id, slot)
        if row is not None and row.photo_path:
            Path(row.photo_path).unlink(missing_ok=True)
        repo.delete_photo_slot(db, model_cls, report_id, slot)
        return {"slot": slot, "ok": True}

    @router.get("/{slot}/image")
    def get_slot_image(
        request: Request, report_id: int, slot: int, thumb: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db)
    ):
        _require_report(db, user.company_id, report_id)
        row = repo.get_photo_slot(db, model_cls, report_id, slot)
        if row is None or not row.photo_path or not Path(row.photo_path).exists():
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label}이(가) 없습니다.")
        return photo_response(request, row.photo_path, thumb)

    return router


overview_router = _build_slot_router("overview", OverviewPhoto, "전경사진")
inspection_router = _build_slot_router("inspection", InspectionPhoto, "점검사진")
