"""11. 제공자료 (최대 2건) — 라이브러리에서 선택 또는 직접 업로드 (support.py에서 분리, Sub-phase 40).

데스크톱(`report_wizard_view.py`의 자료 선택/추천)과 같은 규칙:
- 슬롯마다 라이브러리 자료(`material_id`) 또는 직접 올린 이미지(`custom_photo_path`) 중 하나. 렌더러
  (`report_builder_hwpx_images.py`)는 직접 올린 이미지를 우선하므로, 라이브러리 자료를 고르면 직접 올린
  이미지를 지우고, 이미지를 올리면 라이브러리 선택을 해제해 화면과 보고서가 어긋나지 않게 한다.
- "추천"은 이 보고서 8번 지적사항 키워드로 자료 제목/태그를 매칭(`core/material_recommender.py`, AI 아님).
- 선택이 바뀔 때마다 10-1 TBM "교육내용"을 고른 자료 제목(쉼표 나열)으로 맞춘다(데스크톱
  `_sync_education_content_from_materials`와 같은 동작 — 그 뒤에 직접 고쳐 쓰는 건 자유).
- 라이브러리는 회사 구분 없는 공용 참조 데이터(`material_library`, 서버 시작 시 시딩 — core/db.py).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.material_recommender import recommend_materials
from core.models_db import Finding, MaterialLibrary, ProvidedMaterial, SafetyEducation
from core.models_web import User
from core.thumbnail_generator import resolve_material_path
from server.api import repo, storage
from server.api.deps import get_current_user, get_db
from server.api.photo_thumbs import photo_response
from server.schemas.support import MaterialIn, MaterialOut

router = APIRouter(tags=["materials"])

_ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_MATERIAL_SLOTS = range(1, 3)


class LibraryItemOut(BaseModel):
    id: int
    title: str


class MaterialsChangedOut(BaseModel):
    """선택 변경 응답 — 화면이 10-1 교육내용 칸도 같이 갱신할 수 있게 바뀐 값을 돌려준다."""

    items: list[MaterialOut]
    education_content: str


def _require_report(db: Session, company_id: int, report_id: int):
    report = repo.get_report(db, company_id, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    return report


def _require_slot(slot: int) -> None:
    if slot not in _MATERIAL_SLOTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "slot은 1~2여야 합니다.")


def _to_out(slot: int, row: ProvidedMaterial | None) -> MaterialOut:
    if row is None:
        return MaterialOut(slot=slot)
    return MaterialOut(
        slot=slot,
        title=row.title,
        material_id=row.material_id,
        has_photo=bool(row.custom_photo_path or row.material_id),
    )


def _all_out(db: Session, report_id: int) -> list[MaterialOut]:
    return [_to_out(slot, repo.get_slot_row(db, ProvidedMaterial, report_id, slot)) for slot in _MATERIAL_SLOTS]


def _sync_education_content(db: Session, report_id: int) -> str:
    rows = (
        db.query(ProvidedMaterial)
        .filter(ProvidedMaterial.report_id == report_id)
        .order_by(ProvidedMaterial.slot)
        .all()
    )
    content = ", ".join(r.title for r in rows if r.title.strip())
    edu = db.query(SafetyEducation).filter(SafetyEducation.report_id == report_id).first()
    if edu is None:
        edu = SafetyEducation(report_id=report_id)
        db.add(edu)
    edu.content = content
    db.commit()
    return content


def _changed(db: Session, report_id: int) -> MaterialsChangedOut:
    content = _sync_education_content(db, report_id)
    return MaterialsChangedOut(items=_all_out(db, report_id), education_content=content)


def _drop_custom_file(row: ProvidedMaterial) -> None:
    if row.custom_photo_path:
        Path(row.custom_photo_path).unlink(missing_ok=True)
        row.custom_photo_path = ""


# ---------- 공용 라이브러리 ----------


@router.get("/material-library", response_model=list[LibraryItemOut])
def list_library(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [LibraryItemOut(id=m.id, title=m.title) for m in db.query(MaterialLibrary).order_by(MaterialLibrary.id)]


@router.get("/material-library/{material_id}/thumbnail")
def library_thumbnail(material_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(MaterialLibrary, material_id)
    path = (resolve_material_path(item.thumbnail_path) or resolve_material_path(item.file_path)) if item else None
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "자료 이미지가 없습니다.")
    return FileResponse(path)


@router.get("/material-library/{material_id}/file")
def library_file(material_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """크게 보기(원본)."""
    item = db.get(MaterialLibrary, material_id)
    path = resolve_material_path(item.file_path) if item else None
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "자료 파일이 없습니다.")
    return FileResponse(path)


# ---------- 보고서의 제공자료 슬롯 ----------


@router.get("/reports/{report_id}/materials", response_model=list[MaterialOut])
def list_materials(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_report(db, user.company_id, report_id)
    return _all_out(db, report_id)


@router.patch("/reports/{report_id}/materials/{slot}", response_model=MaterialsChangedOut)
def update_material(
    report_id: int, slot: int, body: MaterialIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """보낸 필드만 갱신. `material_id`를 보내면 라이브러리 자료로 지정(제목도 자료 제목으로, 직접 올린
    이미지는 삭제), `title`만 보내면 제목만 수정."""
    _require_report(db, user.company_id, report_id)
    _require_slot(slot)
    fields = body.model_dump(exclude_unset=True)
    row = repo.get_slot_row(db, ProvidedMaterial, report_id, slot)
    if row is None:
        row = ProvidedMaterial(report_id=report_id, slot=slot)
        db.add(row)
    if "material_id" in fields and fields["material_id"] is not None:
        item = db.get(MaterialLibrary, fields["material_id"])
        if item is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "없는 자료입니다.")
        row.material_id = item.id
        row.title = item.title
        _drop_custom_file(row)
    if "title" in fields:
        row.title = fields["title"]
    db.commit()
    return _changed(db, report_id)


@router.delete("/reports/{report_id}/materials/{slot}", response_model=MaterialsChangedOut)
def clear_material(report_id: int, slot: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """슬롯 비우기(라이브러리 선택·직접 올린 이미지·제목 전부)."""
    _require_report(db, user.company_id, report_id)
    _require_slot(slot)
    row = repo.get_slot_row(db, ProvidedMaterial, report_id, slot)
    if row is not None:
        _drop_custom_file(row)
        db.delete(row)
        db.commit()
    return _changed(db, report_id)


@router.post("/reports/{report_id}/materials/recommend", response_model=MaterialsChangedOut)
def recommend(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """8번 지적사항 키워드로 자료 2개를 골라 슬롯 1·2에 바로 채운다(데스크톱 "추천"과 같이 기존 선택을
    바꾼다). 관련 자료가 없으면 아무것도 안 바꾸고 빈 결과(화면에서 안내)."""
    _require_report(db, user.company_id, report_id)
    findings = [
        {"title": f.title, "content": f.content}
        for f in db.query(Finding).filter(Finding.report_id == report_id).all()
        if (f.title or "").strip() or (f.content or "").strip()
    ]
    if not findings:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "8번 지적사항을 먼저 입력해야 관련 자료를 추천할 수 있습니다.")
    picked = recommend_materials(findings, db.query(MaterialLibrary).all(), limit=len(_MATERIAL_SLOTS))
    if not picked:
        return MaterialsChangedOut(items=[], education_content="")
    for slot in _MATERIAL_SLOTS:
        row = repo.get_slot_row(db, ProvidedMaterial, report_id, slot)
        if slot <= len(picked):
            if row is None:
                row = ProvidedMaterial(report_id=report_id, slot=slot)
                db.add(row)
            _drop_custom_file(row)
            row.material_id, row.title = picked[slot - 1].id, picked[slot - 1].title
        elif row is not None:
            _drop_custom_file(row)
            db.delete(row)
    db.commit()
    return _changed(db, report_id)


@router.post("/reports/{report_id}/materials/{slot}/photo", response_model=MaterialsChangedOut)
async def upload_material_photo(
    report_id: int, slot: int, file: UploadFile, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    report = _require_report(db, user.company_id, report_id)
    _require_slot(slot)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "이미지 파일만 업로드할 수 있습니다.")
    row = repo.get_slot_row(db, ProvidedMaterial, report_id, slot)
    if row is None:
        row = ProvidedMaterial(report_id=report_id, slot=slot)
        db.add(row)
    dest = storage.photo_path(db, report, f"제공자료{slot}", suffix, own=row.custom_photo_path or "")
    _drop_custom_file(row)  # 예전 파일 먼저 지우고(같은 이름일 수 있음) 새로 쓴다
    dest.write_bytes(await file.read())
    row.custom_photo_path = str(dest)
    row.material_id = None
    db.commit()
    return _changed(db, report_id)


@router.delete("/reports/{report_id}/materials/{slot}/photo", response_model=MaterialsChangedOut)
def delete_material_photo(
    report_id: int, slot: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _require_report(db, user.company_id, report_id)
    row = repo.get_slot_row(db, ProvidedMaterial, report_id, slot)
    if row is not None and row.custom_photo_path:
        _drop_custom_file(row)
        db.commit()
    return _changed(db, report_id)


@router.get("/reports/{report_id}/materials/{slot}/photo")
def get_material_photo(
    request: Request, report_id: int, slot: int, thumb: bool = False,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """썸네일 — 직접 올린 이미지가 있으면 그것, 아니면 라이브러리 자료 썸네일."""
    _require_report(db, user.company_id, report_id)
    row = repo.get_slot_row(db, ProvidedMaterial, report_id, slot)
    path: Path | None = None
    if row is not None and row.custom_photo_path and Path(row.custom_photo_path).exists():
        path = Path(row.custom_photo_path)
    elif row is not None and row.material is not None:
        path = resolve_material_path(row.material.thumbnail_path) or resolve_material_path(row.material.file_path)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "자료가 없습니다.")
    return photo_response(request, path, thumb)
