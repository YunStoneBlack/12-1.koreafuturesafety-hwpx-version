"""4. 이전지적사항 (최대 4건).

**이번 1차 포팅 범위 밖(의도적으로 미룸)**: 데스크톱(`desktop/views/report_wizard_load.py::
_reconcile_previous_findings`)은 마법사를 열 때마다 "직전 회차(같은 현장의 바로 전 보고서)의
8번 지적사항"을 자동으로 읽어와 이 4칸에 이월시키고, 원본이 수정되면 실시간으로 반영한다.
이 자동 이월은 8번 지적사항(Finding, 아직 웹판에 없음)이 있어야 의미가 있어서, 8번을
만들 때 같이 넣는다. 지금은 **수동 입력**(제목/내용/사진/조치결과)만 지원 — `source_finding_id`는
항상 NULL로 남겨두므로(모델이 이미 nullable로 설계돼 있음) 나중에 자동 이월을 추가해도
지금 만든 수동 입력 데이터와 충돌하지 않는다. "이행 후 위험성"(likelihood/severity) 계산도
같은 이유로 같이 미룬다."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from core.db import BASE_DIR
from core.models_db import PreviousFinding
from core.models_web import User
from server.api import repo
from server.api.deps import get_current_user, get_db
from server.schemas.previous_finding import PreviousFindingIn, PreviousFindingOut

router = APIRouter(prefix="/reports/{report_id}/previous-findings", tags=["previous-findings"])

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


def _to_out(slot: int, row: PreviousFinding | None) -> PreviousFindingOut:
    if row is None:
        return PreviousFindingOut(slot=slot)
    return PreviousFindingOut(
        slot=slot,
        title=row.title,
        content=row.content,
        result_status=row.result_status,
        has_photo=bool(row.photo_path),
        has_completion_photo=bool(row.completion_photo_path),
    )


@router.get("", response_model=list[PreviousFindingOut])
def list_previous_findings(
    report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _require_report(db, user.company_id, report_id)
    return [_to_out(slot, repo.get_slot_row(db, PreviousFinding, report_id, slot)) for slot in _SLOT_RANGE]


@router.patch("/{slot}", response_model=PreviousFindingOut)
def update_previous_finding(
    report_id: int,
    slot: int,
    body: PreviousFindingIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_report(db, user.company_id, report_id)
    _require_slot(slot)
    row = repo.upsert_slot_row(db, PreviousFinding, report_id, slot, **body.model_dump())
    return _to_out(slot, row)


async def _save_photo(db: Session, report_id: int, slot: int, field: str, slug: str, file: UploadFile) -> None:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "이미지 파일만 업로드할 수 있습니다.")
    photo_dir = BASE_DIR / "data" / "photos" / f"report_{report_id}"
    photo_dir.mkdir(parents=True, exist_ok=True)
    dest = photo_dir / f"{slug}{suffix}"
    dest.write_bytes(await file.read())
    repo.upsert_slot_row(db, PreviousFinding, report_id, slot, **{field: str(dest)})


def _clear_photo(db: Session, report_id: int, slot: int, field: str) -> None:
    row = repo.get_slot_row(db, PreviousFinding, report_id, slot)
    if row is not None and getattr(row, field):
        Path(getattr(row, field)).unlink(missing_ok=True)
        setattr(row, field, "")
        db.commit()


def _serve_photo(db: Session, report_id: int, slot: int, field: str):
    row = repo.get_slot_row(db, PreviousFinding, report_id, slot)
    path = getattr(row, field, "") if row else ""
    if not path or not Path(path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return FileResponse(path)


@router.post("/{slot}/photo", response_model=PreviousFindingOut)
async def upload_photo(
    report_id: int, slot: int, file: UploadFile, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _require_report(db, user.company_id, report_id)
    _require_slot(slot)
    await _save_photo(db, report_id, slot, "photo_path", f"previous_{slot}", file)
    return _to_out(slot, repo.get_slot_row(db, PreviousFinding, report_id, slot))


@router.delete("/{slot}/photo", response_model=PreviousFindingOut)
def delete_photo(report_id: int, slot: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_report(db, user.company_id, report_id)
    _require_slot(slot)
    _clear_photo(db, report_id, slot, "photo_path")
    return _to_out(slot, repo.get_slot_row(db, PreviousFinding, report_id, slot))


@router.get("/{slot}/photo")
def get_photo(report_id: int, slot: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_report(db, user.company_id, report_id)
    return _serve_photo(db, report_id, slot, "photo_path")


@router.post("/{slot}/completion-photo", response_model=PreviousFindingOut)
async def upload_completion_photo(
    report_id: int, slot: int, file: UploadFile, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _require_report(db, user.company_id, report_id)
    _require_slot(slot)
    await _save_photo(db, report_id, slot, "completion_photo_path", f"previous_{slot}_completion", file)
    return _to_out(slot, repo.get_slot_row(db, PreviousFinding, report_id, slot))


@router.delete("/{slot}/completion-photo", response_model=PreviousFindingOut)
def delete_completion_photo(
    report_id: int, slot: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _require_report(db, user.company_id, report_id)
    _require_slot(slot)
    _clear_photo(db, report_id, slot, "completion_photo_path")
    return _to_out(slot, repo.get_slot_row(db, PreviousFinding, report_id, slot))


@router.get("/{slot}/completion-photo")
def get_completion_photo(
    report_id: int, slot: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _require_report(db, user.company_id, report_id)
    return _serve_photo(db, report_id, slot, "completion_photo_path")
