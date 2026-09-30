"""사진 돌리기(↻ 오른쪽 90도, 2026-09-30 사용자 요청) — 폰 화면 회전 잠금 상태로 옆으로 들고 찍으면 방향 정보(EXIF) 없이 누운 사진이
저장돼 썸네일·보고서에 그대로 누워 들어간다. 저장된 **원본 파일 자체를** 돌려 다시 저장하므로 썸네일(photo_thumbs)·보고서용 축소본
(report_builder_hwpx_jpeg)은 파일 수정 시각이 바뀐 걸 보고 새로 만든다. 주소는 각 사진 칸 주소 끝에 `/rotate`
(`POST /api/reports/{id}/...`라 edit_tracking이 보고서 "수정됨"으로 기록 → PDF 수정 전 버전).

사진 칸: 전경·점검(3번), 지적사항(8번), 이전지적 사진·이행완료 증빙(4번 — 이월된 사진은 지난 회차 8번 파일이라 여기선 못 돌림),
교육(10-1), 계측(10-2), 제공자료 직접 올린 이미지(11번 — 라이브러리 자료는 공용 파일이라 못 돌림).
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from core.models_db import (
    Finding, InspectionPhoto, Measurement, OverviewPhoto, PreviousFinding, ProvidedMaterial, SafetyEducation,
)
from core.models_web import User
from server.api import repo
from server.api.deps import get_current_user, get_db

router = APIRouter(prefix="/reports/{report_id}", tags=["photos"])


def rotate_file(path: str) -> None:
    """원본을 방향 정보대로 세운 뒤 오른쪽으로 90도 돌려 같은 파일에 다시 저장(방향 정보는 빼고 — 이미 반영했으므로)."""
    src = Path(path or "")
    if not path or not src.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "돌릴 사진이 없습니다.")
    try:
        with Image.open(src) as img:
            fmt = (img.format or "JPEG").upper()
            icc = img.info.get("icc_profile")
            out = ImageOps.exif_transpose(img).rotate(-90, expand=True)
            tmp = src.with_name(src.name + f".{os.getpid()}.rot.tmp")
            if fmt in ("JPEG", "MPO"):
                if out.mode not in ("RGB", "L"):
                    out = out.convert("RGB")
                out.save(tmp, "JPEG", quality=95, subsampling=0, icc_profile=icc)
            else:
                out.save(tmp, fmt)
        os.replace(tmp, src)
    except HTTPException:
        raise
    except Exception as e:  # 깨진 파일 등
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"사진을 돌리지 못했습니다: {e}") from e


def _require_report(db: Session, user: User, report_id: int) -> None:
    if repo.get_report(db, user.company_id, report_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")


def _done() -> dict:
    return {"ok": True}


@router.post("/overview-photos/{slot}/rotate")
def rotate_overview(report_id: int, slot: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_report(db, user, report_id)
    row = repo.get_photo_slot(db, OverviewPhoto, report_id, slot)
    rotate_file(row.photo_path if row else "")
    return _done()


@router.post("/inspection-photos/{slot}/rotate")
def rotate_inspection(report_id: int, slot: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_report(db, user, report_id)
    row = repo.get_photo_slot(db, InspectionPhoto, report_id, slot)
    rotate_file(row.photo_path if row else "")
    return _done()


@router.post("/findings/{slot}/photo/rotate")
def rotate_finding(report_id: int, slot: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_report(db, user, report_id)
    row = repo.get_slot_row(db, Finding, report_id, slot)
    rotate_file(row.photo_path if row else "")
    return _done()


@router.post("/previous-findings/{slot}/photo/rotate")
def rotate_previous(report_id: int, slot: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_report(db, user, report_id)
    row = repo.get_slot_row(db, PreviousFinding, report_id, slot)
    if row is not None and row.source_finding_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "이월된 사진은 지난 회차 8번 지적사항에서 돌리세요.")
    rotate_file(row.photo_path if row else "")
    return _done()


@router.post("/previous-findings/{slot}/completion-photo/rotate")
def rotate_completion(report_id: int, slot: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_report(db, user, report_id)
    row = repo.get_slot_row(db, PreviousFinding, report_id, slot)
    rotate_file(row.completion_photo_path if row else "")
    return _done()


@router.post("/tbm/photo/rotate")
def rotate_tbm(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_report(db, user, report_id)
    row = db.query(SafetyEducation).filter(SafetyEducation.report_id == report_id).first()
    rotate_file(row.photo_path if row else "")
    return _done()


@router.post("/measurements/{instrument_type}/photo/rotate")
def rotate_measurement(report_id: int, instrument_type: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_report(db, user, report_id)
    row = (
        db.query(Measurement)
        .filter(Measurement.report_id == report_id, Measurement.instrument_type == instrument_type)
        .first()
    )
    rotate_file(row.photo_path if row else "")
    return _done()


@router.post("/materials/{slot}/photo/rotate")
def rotate_material(report_id: int, slot: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_report(db, user, report_id)
    row = repo.get_slot_row(db, ProvidedMaterial, report_id, slot)
    if row is None or not row.custom_photo_path:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "라이브러리 자료는 돌릴 수 없습니다(직접 올린 이미지만).")
    rotate_file(row.custom_photo_path)
    return _done()
