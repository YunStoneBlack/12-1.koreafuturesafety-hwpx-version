"""4. 이전지적사항 (최대 4건).

목록 조회(GET) 때마다 `server/api/carryover.py`가 직전 회차 8번 지적사항을 자동 이월한다
(데스크톱 `_reconcile_previous_findings`와 같은 규칙, 자세한 건 그 모듈 docstring). 이월 항목은
제목/내용/사진/이행 전 위험성이 원본을 따르므로 여기서 수정·업로드를 막고, 조치결과와 이행완료
증빙사진만 받는다. 수기 항목(빈 칸에 직접 입력)은 전부 입력 가능."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from core.db import BASE_DIR
from core.models_db import PreviousFinding
from core.models_web import User
from server.api import repo
from server.api.carryover import owns_file, reconcile_previous_findings, sync_implemented_flag
from server.api.deps import get_current_user, get_db
from server.api.photo_thumbs import photo_response
from server.schemas.previous_finding import PreviousFindingIn, PreviousFindingList, PreviousFindingOut

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
    title, content, photo_path = row.display_fields()
    before_likelihood, before_severity = row.source_risk()
    after_likelihood, after_severity = row.resolve_after_risk()
    return PreviousFindingOut(
        slot=slot,
        title=title,
        content=content,
        result_status=row.result_status,
        has_photo=bool(photo_path),
        has_completion_photo=bool(row.completion_photo_path),
        carried=bool(row.source_finding_id),
        before_likelihood=before_likelihood,
        before_severity=before_severity,
        after_likelihood=after_likelihood,
        after_severity=after_severity,
    )


def _sync_flag(db: Session, report) -> None:
    rows = db.query(PreviousFinding).filter(PreviousFinding.report_id == report.id).all()
    sync_implemented_flag(report, rows)


def _reject_if_carried(row: PreviousFinding | None) -> None:
    if row is not None and row.source_finding_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "직전 회차에서 이월된 지적사항의 사진은 그 회차 8번(지적사항)에서 수정하세요.",
        )


@router.get("", response_model=PreviousFindingList)
def list_previous_findings(
    report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    report = _require_report(db, user.company_id, report_id)
    prev_report = reconcile_previous_findings(db, report)
    items = [_to_out(slot, repo.get_slot_row(db, PreviousFinding, report_id, slot)) for slot in _SLOT_RANGE]
    return PreviousFindingList(
        prev_visit_no=prev_report.visit_no if prev_report else None,
        carried_count=sum(1 for item in items if item.carried),
        items=items,
    )


@router.patch("/{slot}", response_model=PreviousFindingOut)
def update_previous_finding(
    report_id: int,
    slot: int,
    body: PreviousFindingIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = _require_report(db, user.company_id, report_id)
    _require_slot(slot)
    fields = body.model_dump(exclude_unset=True)
    row = repo.get_slot_row(db, PreviousFinding, report_id, slot)
    if row is None:
        row = PreviousFinding(report_id=report_id, slot=slot)
        db.add(row)
    if row.source_finding_id:
        # 원본을 따르는 값 — 보내와도 무시(화면에서도 잠겨 있음)
        for key in ("title", "content", "manual_likelihood", "manual_severity"):
            fields.pop(key, None)
    before = (row.manual_likelihood, row.manual_severity)
    for key, value in fields.items():
        setattr(row, key, value)
    if (row.manual_likelihood, row.manual_severity) != before:
        row.after_likelihood = row.after_severity = None  # 이행 전이 바뀌면 이행 후 다시 뽑기
    row.resolve_after_risk()
    db.flush()
    _sync_flag(db, report)
    db.commit()
    return _to_out(slot, row)


async def _save_photo(db: Session, report_id: int, slot: int, field: str, slug: str, file: UploadFile) -> None:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "이미지 파일만 업로드할 수 있습니다.")
    row = repo.get_slot_row(db, PreviousFinding, report_id, slot)
    if field == "photo_path":
        _reject_if_carried(row)
    photo_dir = BASE_DIR / "data" / "photos" / f"report_{report_id}"
    photo_dir.mkdir(parents=True, exist_ok=True)
    # 파일명에 난수를 붙인다 — 이월 때문에 항목의 슬롯 번호가 바뀔 수 있어서, 슬롯 번호만으로
    # 이름을 지으면 다른 항목이 같은 파일을 덮어쓸 수 있다.
    dest = photo_dir / f"{slug}_{uuid.uuid4().hex[:8]}{suffix}"
    dest.write_bytes(await file.read())
    old = getattr(row, field, "") if row else ""
    if row is not None and owns_file(row, old):
        Path(old).unlink(missing_ok=True)
    repo.upsert_slot_row(db, PreviousFinding, report_id, slot, **{field: str(dest)})


def _clear_photo(db: Session, report_id: int, slot: int, field: str) -> None:
    row = repo.get_slot_row(db, PreviousFinding, report_id, slot)
    if field == "photo_path":
        _reject_if_carried(row)
    if row is not None and getattr(row, field):
        Path(getattr(row, field)).unlink(missing_ok=True)
        setattr(row, field, "")
        db.commit()


def _serve_photo(request: Request, db: Session, report_id: int, slot: int, field: str, thumb: bool):
    row = repo.get_slot_row(db, PreviousFinding, report_id, slot)
    path = ""
    if row is not None:
        path = row.display_fields()[2] if field == "photo_path" else getattr(row, field)
    if not path or not Path(path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return photo_response(request, path, thumb)


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
def get_photo(
    request: Request, report_id: int, slot: int, thumb: bool = False,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    _require_report(db, user.company_id, report_id)
    return _serve_photo(request, db, report_id, slot, "photo_path", thumb)


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
    request: Request, report_id: int, slot: int, thumb: bool = False,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    _require_report(db, user.company_id, report_id)
    return _serve_photo(request, db, report_id, slot, "completion_photo_path", thumb)
