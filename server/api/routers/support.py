"""10. 사업장 지원 사항 (TBM 활성화 지도 및 교육 / 계측자료) / 11. 제공자료.

**이번 1차 포팅 범위 밖(의도적으로 미룸)**: 11번 제공자료는 데스크톱에서 "라이브러리에서
선택"(`MaterialLibrary`, AI 추천 포함) 또는 "직접 업로드" 둘 다 되는데, 이 웹판 DB엔 아직
라이브러리 시딩이 안 되어 있어(`core/db.py::_seed_reference_data`가 데스크톱 `init_db()`
경로에서만 호출됨 — 웹판은 다른 부트스트랩을 씀) 지금은 **직접 업로드만** 지원한다."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from core.constants import MEASUREMENT_INSTRUMENTS
from core.db import BASE_DIR
from core.models_db import Measurement, ProvidedMaterial, Report, SafetyEducation
from core.models_web import User
from server.api import repo
from server.api.deps import get_current_user, get_db
from server.schemas.support import MaterialIn, MaterialOut, MeasurementIn, MeasurementOut, TbmIn, TbmOut

router = APIRouter(prefix="/reports/{report_id}", tags=["support"])

_ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_MATERIAL_SLOTS = range(1, 3)


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
def get_tbm_photo(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_report(db, user.company_id, report_id)
    row = db.query(SafetyEducation).filter(SafetyEducation.report_id == report_id).first()
    if row is None or not row.photo_path or not Path(row.photo_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return FileResponse(row.photo_path)


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
    report_id: int, instrument_type: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _require_report(db, user.company_id, report_id)
    row = (
        db.query(Measurement)
        .filter(Measurement.report_id == report_id, Measurement.instrument_type == instrument_type)
        .first()
    )
    if row is None or not row.photo_path or not Path(row.photo_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return FileResponse(row.photo_path)


# ---------- 11. 제공자료 (직접 업로드만 — 라이브러리 선택은 다음 단계) ----------


@router.get("/materials", response_model=list[MaterialOut])
def list_materials(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_report(db, user.company_id, report_id)
    rows = {m.slot: m for m in db.query(ProvidedMaterial).filter(ProvidedMaterial.report_id == report_id).all()}
    return [
        MaterialOut(slot=slot, title=(rows[slot].title if slot in rows else ""),
                    has_photo=bool(rows[slot].custom_photo_path) if slot in rows else False)
        for slot in _MATERIAL_SLOTS
    ]


@router.patch("/materials/{slot}", response_model=MaterialOut)
def update_material(
    report_id: int, slot: int, body: MaterialIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _require_report(db, user.company_id, report_id)
    if slot not in _MATERIAL_SLOTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "slot은 1~2여야 합니다.")
    row = repo.upsert_slot_row(db, ProvidedMaterial, report_id, slot, title=body.title)
    return MaterialOut(slot=slot, title=row.title, has_photo=bool(row.custom_photo_path))


@router.post("/materials/{slot}/photo", response_model=MaterialOut)
async def upload_material_photo(
    report_id: int, slot: int, file: UploadFile, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _require_report(db, user.company_id, report_id)
    if slot not in _MATERIAL_SLOTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "slot은 1~2여야 합니다.")
    path = await _save_photo(file, report_id, f"material_{slot}")
    row = repo.upsert_slot_row(db, ProvidedMaterial, report_id, slot, custom_photo_path=path)
    return MaterialOut(slot=slot, title=row.title, has_photo=True)


@router.get("/materials/{slot}/photo")
def get_material_photo(report_id: int, slot: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_report(db, user.company_id, report_id)
    row = repo.get_slot_row(db, ProvidedMaterial, report_id, slot)
    if row is None or not row.custom_photo_path or not Path(row.custom_photo_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "자료가 없습니다.")
    return FileResponse(row.custom_photo_path)
