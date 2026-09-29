"""10. 사업장 지원 사항 (TBM 활성화 지도 및 교육 / 계측자료).

11번 제공자료는 `materials.py`로 분리됨(Sub-phase 40 — 라이브러리 선택/추천 추가)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from core.constants import MEASUREMENT_INSTRUMENTS
from core.db import BASE_DIR
from core.models_db import Measurement, Report, SafetyEducation
from core.models_web import User
from server.api import repo
from server.api.deps import get_current_user, get_db
from server.api.photo_thumbs import photo_response
from server.schemas.support import MeasurementIn, MeasurementOut, TbmIn, TbmOut

router = APIRouter(prefix="/reports/{report_id}", tags=["support"])

_ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _require_report(db: Session, company_id: int, report_id: int) -> Report:
    report = repo.get_report(db, company_id, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    return report


async def _save_photo(file: UploadFile, report_id: int, slug: str) -> str:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "이미지 파일만 업로드할 수 있습니다.")
    photo_dir = BASE_DIR / "data" / "photos" / f"report_{report_id}"
    photo_dir.mkdir(parents=True, exist_ok=True)
    dest = photo_dir / f"{slug}{suffix}"
    dest.write_bytes(await file.read())
    return str(dest)


def _clear_file(db: Session, row, field: str) -> None:
    """사진 필드 비우기 + 파일 삭제. 예전엔 이 삭제 API 자체가 없어서 화면의 "삭제"가 405로 조용히
    실패하고(응답 확인을 안 했음) 사진이 그대로 보고서에 나갔다 — Sub-phase 40에서 발견."""
    path = getattr(row, field, "") if row is not None else ""
    if path:
        Path(path).unlink(missing_ok=True)
        setattr(row, field, "")
        db.commit()


# ---------- 10-1. TBM 교육 (SafetyEducation, 회차당 1건) ----------


@router.get("/tbm", response_model=TbmOut)
def get_tbm(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_report(db, user.company_id, report_id)
    row = db.query(SafetyEducation).filter(SafetyEducation.report_id == report_id).first()
    if row is None:
        return TbmOut()
    return TbmOut(
        attendee_count=row.attendee_count, location=row.location, content=row.content,
        material=row.material, has_photo=bool(row.photo_path),
    )


@router.patch("/tbm", response_model=TbmOut)
def update_tbm(
    report_id: int, body: TbmIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _require_report(db, user.company_id, report_id)
    row = db.query(SafetyEducation).filter(SafetyEducation.report_id == report_id).first()
    if row is None:
        row = SafetyEducation(report_id=report_id, **body.model_dump())
        db.add(row)
    else:
        for key, value in body.model_dump().items():
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return TbmOut(
        attendee_count=row.attendee_count, location=row.location, content=row.content,
        material=row.material, has_photo=bool(row.photo_path),
    )


@router.post("/tbm/photo", response_model=TbmOut)
async def upload_tbm_photo(
    report_id: int, file: UploadFile, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _require_report(db, user.company_id, report_id)
    path = await _save_photo(file, report_id, "education")
    row = db.query(SafetyEducation).filter(SafetyEducation.report_id == report_id).first()
    if row is None:
        row = SafetyEducation(report_id=report_id, photo_path=path)
        db.add(row)
    else:
        row.photo_path = path
    db.commit()
    db.refresh(row)
    return TbmOut(
        attendee_count=row.attendee_count, location=row.location, content=row.content,
        material=row.material, has_photo=True,
    )


@router.get("/tbm/photo")
def get_tbm_photo(
    request: Request, report_id: int, thumb: bool = False,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    _require_report(db, user.company_id, report_id)
    row = db.query(SafetyEducation).filter(SafetyEducation.report_id == report_id).first()
    if row is None or not row.photo_path or not Path(row.photo_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return photo_response(request, row.photo_path, thumb)


@router.delete("/tbm/photo", response_model=TbmOut)
def delete_tbm_photo(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_report(db, user.company_id, report_id)
    row = db.query(SafetyEducation).filter(SafetyEducation.report_id == report_id).first()
    _clear_file(db, row, "photo_path")
    if row is None:
        return TbmOut()
    return TbmOut(
        attendee_count=row.attendee_count, location=row.location, content=row.content,
        material=row.material, has_photo=False,
    )


# ---------- 10-2. 계측자료 (Measurement, instrument_type별 최대 1건씩) ----------

_INSTRUMENT_UNITS = dict(MEASUREMENT_INSTRUMENTS)


def _require_instrument(instrument_type: str) -> None:
    if instrument_type not in _INSTRUMENT_UNITS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "알 수 없는 계측장비입니다.")


@router.get("/measurements", response_model=list[MeasurementOut])
def list_measurements(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_report(db, user.company_id, report_id)
    rows = {m.instrument_type: m for m in db.query(Measurement).filter(Measurement.report_id == report_id).all()}
    out = []
    for name, unit in MEASUREMENT_INSTRUMENTS:
        row = rows.get(name)
        if row is None:
            out.append(MeasurementOut(instrument_type=name, unit=unit))
        else:
            out.append(MeasurementOut(
                instrument_type=name, unit=unit, value=row.value,
                manual_verdict=row.manual_verdict, manual_action=row.manual_action, has_photo=bool(row.photo_path),
            ))
    return out


@router.patch("/measurements/{instrument_type}", response_model=MeasurementOut)
def update_measurement(
    report_id: int, instrument_type: str, body: MeasurementIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    _require_report(db, user.company_id, report_id)
    _require_instrument(instrument_type)
    row = (
        db.query(Measurement)
        .filter(Measurement.report_id == report_id, Measurement.instrument_type == instrument_type)
        .first()
    )
    if row is None:
        row = Measurement(report_id=report_id, instrument_type=instrument_type, **body.model_dump())
        db.add(row)
    else:
        for key, value in body.model_dump().items():
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return MeasurementOut(
        instrument_type=instrument_type, unit=_INSTRUMENT_UNITS[instrument_type], value=row.value,
        manual_verdict=row.manual_verdict, manual_action=row.manual_action, has_photo=bool(row.photo_path),
    )


@router.post("/measurements/{instrument_type}/photo", response_model=MeasurementOut)
async def upload_measurement_photo(
    report_id: int, instrument_type: str, file: UploadFile,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    _require_report(db, user.company_id, report_id)
    _require_instrument(instrument_type)
    slug = f"measurement_{instrument_type}"
    path = await _save_photo(file, report_id, slug)
    row = (
        db.query(Measurement)
        .filter(Measurement.report_id == report_id, Measurement.instrument_type == instrument_type)
        .first()
    )
    if row is None:
        row = Measurement(report_id=report_id, instrument_type=instrument_type, photo_path=path)
        db.add(row)
    else:
        row.photo_path = path
    db.commit()
    db.refresh(row)
    return MeasurementOut(
        instrument_type=instrument_type, unit=_INSTRUMENT_UNITS[instrument_type], value=row.value,
        manual_verdict=row.manual_verdict, manual_action=row.manual_action, has_photo=True,
    )


@router.get("/measurements/{instrument_type}/photo")
def get_measurement_photo(
    request: Request, report_id: int, instrument_type: str, thumb: bool = False,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    _require_report(db, user.company_id, report_id)
    row = (
        db.query(Measurement)
        .filter(Measurement.report_id == report_id, Measurement.instrument_type == instrument_type)
        .first()
    )
    if row is None or not row.photo_path or not Path(row.photo_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return photo_response(request, row.photo_path, thumb)


@router.delete("/measurements/{instrument_type}/photo", response_model=MeasurementOut)
def delete_measurement_photo(
    report_id: int, instrument_type: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _require_report(db, user.company_id, report_id)
    _require_instrument(instrument_type)
    row = (
        db.query(Measurement)
        .filter(Measurement.report_id == report_id, Measurement.instrument_type == instrument_type)
        .first()
    )
    _clear_file(db, row, "photo_path")
    unit = _INSTRUMENT_UNITS[instrument_type]
    if row is None:
        return MeasurementOut(instrument_type=instrument_type, unit=unit)
    return MeasurementOut(
        instrument_type=instrument_type, unit=unit, value=row.value,
        manual_verdict=row.manual_verdict, manual_action=row.manual_action, has_photo=False,
    )
