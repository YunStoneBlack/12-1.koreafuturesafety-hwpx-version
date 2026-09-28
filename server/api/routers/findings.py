"""8. 지적사항 (최대 4건).

**이번 1차 포팅 범위 밖(의도적으로 미룸)**: 데스크톱은 사진을 Claude Vision에 보내 제목/
내용/법령 인용/위험성을 자동 채우는 "AI추천" 버튼이 있다(`description` 필드가 그 입력).
지금은 전부 수동 입력만 지원 — `description`은 안 씀(AI 붙일 때 추가)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from core.db import BASE_DIR
from core.models_db import Finding
from core.models_web import User
from server.api import repo
from server.api.deps import get_current_user, get_db
from server.schemas.finding import FindingIn, FindingOut

router = APIRouter(prefix="/reports/{report_id}/findings", tags=["findings"])

_ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_SLOT_RANGE = range(1, 5)


def _require_report(db: Session, company_id: int, report_id: int):
    report = repo.get_report(db, company_id, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    return report


def _require_slot(slot: int) -> None:
    if slot not in _SLOT_RANGE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "slot은 1~4여야 합니다.")


def _to_out(slot: int, row: Finding | None) -> FindingOut:
    if row is None:
        return FindingOut(slot=slot)
    return FindingOut(
        slot=slot,
        title=row.title,
        content=row.content,
        law_citation=row.law_citation,
        likelihood=row.likelihood,
        severity=row.severity,
        action_status=row.action_status,
        has_photo=bool(row.photo_path),
    )


@router.get("", response_model=list[FindingOut])
def list_findings(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_report(db, user.company_id, report_id)
    return [_to_out(slot, repo.get_slot_row(db, Finding, report_id, slot)) for slot in _SLOT_RANGE]


@router.patch("/{slot}", response_model=FindingOut)
def update_finding(
    report_id: int,
    slot: int,
    body: FindingIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_report(db, user.company_id, report_id)
    _require_slot(slot)
    row = repo.upsert_slot_row(db, Finding, report_id, slot, **body.model_dump())
    return _to_out(slot, row)


@router.post("/{slot}/photo", response_model=FindingOut)
async def upload_photo(
    report_id: int, slot: int, file: UploadFile, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _require_report(db, user.company_id, report_id)
    _require_slot(slot)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "이미지 파일만 업로드할 수 있습니다.")
    photo_dir = BASE_DIR / "data" / "photos" / f"report_{report_id}"
    photo_dir.mkdir(parents=True, exist_ok=True)
    dest = photo_dir / f"finding_{slot}{suffix}"
    dest.write_bytes(await file.read())
    repo.upsert_slot_row(db, Finding, report_id, slot, photo_path=str(dest))
    return _to_out(slot, repo.get_slot_row(db, Finding, report_id, slot))


@router.delete("/{slot}/photo", response_model=FindingOut)
def delete_photo(report_id: int, slot: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_report(db, user.company_id, report_id)
    _require_slot(slot)
    row = repo.get_slot_row(db, Finding, report_id, slot)
    if row is not None and row.photo_path:
        Path(row.photo_path).unlink(missing_ok=True)
        row.photo_path = ""
        db.commit()
    return _to_out(slot, repo.get_slot_row(db, Finding, report_id, slot))


@router.get("/{slot}/photo")
def get_photo(report_id: int, slot: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_report(db, user.company_id, report_id)
    row = repo.get_slot_row(db, Finding, report_id, slot)
    if row is None or not row.photo_path or not Path(row.photo_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return FileResponse(row.photo_path)
