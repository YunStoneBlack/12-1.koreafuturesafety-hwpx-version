"""AI 작성 보조 — 데스크톱 마법사의 "✨ AI로 작성"/"AI추천" 버튼과 같은 `core/vision_analyzer.py`
함수를 그대로 호출한다(프롬프트·후처리 무수정 → 데스크톱과 같은 결과).

- 결과는 **DB에 저장하지 않고 돌려주기만** 한다 — 화면이 받은 값을 입력칸에 채우고, 사용자가 확인·수정한 뒤
  기존 "저장" 버튼으로 저장한다(계약서 자동인식 `POST /sites/extract-from-contract`와 같은 방식).
- 사진은 분석용으로만 받고 보관하지 않는다(임시파일 → 분석 → 삭제). 폰 원본 사진은 Claude API 이미지 한도(5MB)를
  넘을 수 있어, 보고서용과 같은 축소(긴 변 1400px + 회전 표시 반영, `prepare_photo_for_report`)를 거쳐 보낸다.
- Claude 호출은 20초 안팎 걸리지만 한글 COM 같은 단일 인스턴스 제약이 없어 job 큐 없이 요청 안에서 처리한다
  (동기 `def` 엔드포인트라 FastAPI가 스레드풀에서 돌려 다른 요청을 막지 않는다).
- API 키는 로그인한 사용자 회사의 키(`company_id`)를 쓰고, 없으면 `.env`의 기본 키로 fallback(core/config.py).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core import config
from core.models_db import Finding, Measurement, SafetyEducation
from core.models_web import User
from core.report_builder_hwpx_jpeg import prepare_photo_for_report
from core.vision_analyzer import analyze_finding, analyze_process_hazards, count_people, read_measurement_value
from server.api import repo
from server.api.deps import get_current_user, get_db

router = APIRouter(prefix="/reports/{report_id}/ai", tags=["ai"])

_ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


class ProcessHazardItemOut(BaseModel):
    hazard: str
    prevention: str
    risk_level: str


class ProcessHazardsOut(BaseModel):
    items: list[ProcessHazardItemOut]


class PeopleCountOut(BaseModel):
    count: int | None  # None = 사진에서 못 셈(지어내지 않음 — vision_analyzer 원칙)


class MeasurementReadOut(BaseModel):
    value: str | None  # None = 못 읽음


class FindingSuggestionOut(BaseModel):
    title: str
    content: str
    law_citation: str
    likelihood: int | None
    severity: int | None


def _require_ready(db: Session, user: User, report_id: int) -> None:
    if repo.get_report(db, user.company_id, report_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    if not config.has_api_key(user.company_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "'설정' 화면에서 Claude API 키를 먼저 등록하세요.")


def _save_temp_photo(file: UploadFile | None, workdir: Path) -> Path | None:
    if file is None or not file.filename:
        return None
    suffix = Path(file.filename).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "이미지 파일만 분석할 수 있습니다.")
    path = workdir / f"upload{suffix}"
    path.write_bytes(file.file.read())
    return prepare_photo_for_report(path)


def _ai_failed(err: Exception) -> HTTPException:
    return HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI 분석에 실패했습니다: {err}")


@router.post("/process-hazards", response_model=ProcessHazardsOut)
def ai_process_hazards(
    report_id: int,
    process_name: str = Form(""),
    file: UploadFile | None = File(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """7번/9번 공용 — 공정 사진·공정명 중 하나 이상으로 유해요인/예방대책/위험성 항목(최대 5개)을 만든다.
    사진 촬영이 금지된 현장을 위해 공정명만 있어도 된다(데스크톱 `_ProcessSlot._run_ai`와 같은 규칙)."""
    _require_ready(db, user, report_id)
    process_name = process_name.strip()
    with tempfile.TemporaryDirectory() as workdir:
        photo = _save_temp_photo(file, Path(workdir))
        if photo is None and not process_name:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "공정 사진 또는 공정 이름 중 하나 이상을 입력해주세요.")
        try:
            items = analyze_process_hazards(photo, process_name, company_id=user.company_id)
        except Exception as err:  # noqa: BLE001 - API/파싱 오류를 사용자에게 그대로 안내
            raise _ai_failed(err) from err
    return ProcessHazardsOut(items=items)


@router.post("/finding/{slot}", response_model=FindingSuggestionOut)
def ai_finding(
    report_id: int,
    slot: int,
    description: str = Form(""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """8번 "✨ AI추천" — 이 슬롯에 이미 올린 지적사항 사진 + 간단 설명으로 제목(30자)/내용(110자)/관련법령/
    가능성·중대성을 추천한다. 사진이 필수인 건 데스크톱과 같다(`_FindingSlot._run_ai`). 설명은 다음에 다시
    누를 때를 위해 슬롯에 저장해 둔다(추천 결과 자체는 저장하지 않음)."""
    _require_ready(db, user, report_id)
    row = repo.get_slot_row(db, Finding, report_id, slot)
    if row is None or not row.photo_path or not Path(row.photo_path).exists():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "먼저 지적사항 사진을 올려주세요.")
    row.description = description.strip()
    db.commit()
    try:
        result = analyze_finding(
            prepare_photo_for_report(Path(row.photo_path)), row.description, company_id=user.company_id
        )
    except Exception as err:  # noqa: BLE001
        raise _ai_failed(err) from err
    return FindingSuggestionOut(**result)


def _stored_photo(path: str | None, missing_message: str) -> Path:
    if not path or not Path(path).exists():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, missing_message)
    return prepare_photo_for_report(Path(path))


@router.post("/tbm-people", response_model=PeopleCountOut)
def ai_tbm_people(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """10-1 "✨ AI로 인원 세기" — 저장된 TBM(안전교육) 사진의 인원수(데스크톱 `_run_count_people`)."""
    _require_ready(db, user, report_id)
    row = db.query(SafetyEducation).filter(SafetyEducation.report_id == report_id).first()
    photo = _stored_photo(row.photo_path if row else None, "먼저 TBM 사진을 올려주세요.")
    try:
        return PeopleCountOut(count=count_people(photo, company_id=user.company_id))
    except Exception as err:  # noqa: BLE001
        raise _ai_failed(err) from err


@router.post("/measurement/{instrument_type}", response_model=MeasurementReadOut)
def ai_measurement(
    report_id: int, instrument_type: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """10-2 "✨ AI로 읽기" — 저장된 계측장비 사진에서 측정값을 읽는다(가스측정기는 4종 값을 읽어
    정상범위 판정, 데스크톱 `_MeasurementRow._run_read`와 같은 함수)."""
    _require_ready(db, user, report_id)
    row = (
        db.query(Measurement)
        .filter(Measurement.report_id == report_id, Measurement.instrument_type == instrument_type)
        .first()
    )
    photo = _stored_photo(row.photo_path if row else None, "먼저 계측장비 사진을 올려주세요.")
    try:
        return MeasurementReadOut(value=read_measurement_value(photo, instrument_type, company_id=user.company_id))
    except Exception as err:  # noqa: BLE001
        raise _ai_failed(err) from err
