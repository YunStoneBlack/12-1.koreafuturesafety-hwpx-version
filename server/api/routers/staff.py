"""담당요원 관리 — 데스크톱 '담당요원 관리' 화면(`desktop/views/staff_view.py`)과 같은 기능:
추가/수정/활성·비활성/삭제 + 요원별 서명 등록(그리기 또는 이미지). 전부 로그인한 회사 안에서만.

- `GET /staff`는 보고서 담당요원 드롭다운용(활성 요원만, 예전과 동일), 관리 화면은 `GET /staff/all`.
- 삭제 시 이 요원이 배정된 현장/보고서는 담당요원이 빈 값이 된다(데스크톱 안내 문구와 같은 동작).
  PostgreSQL은 외래키를 실제로 검사해서 먼저 연결을 끊어야 한다(데스크톱 SQLite는 검사 안 함).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_db import Report, Site, Staff
from core.models_web import StaffContact, User
from server.api import repo
from server.api.deps import get_current_user, get_db
from server.api.mailer import valid_email
from server.api.signature_files import normalize_source, save_signature_upload
from server.schemas.staff import StaffOut

router = APIRouter(prefix="/staff", tags=["staff"])


class StaffIn(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None  # 지도 기한 알림 메일 받는 곳(staff_contact — Staff는 데스크톱과 같이 쓰는 모델이라 따로)
    active: bool | None = None


class StaffAdminOut(StaffOut):
    active: bool
    has_signature: bool
    email: str = ""


def _admin_out(staff: Staff, email: str = "") -> StaffAdminOut:
    return StaffAdminOut(
        id=staff.id, name=staff.name, phone=staff.phone, active=staff.active, has_signature=bool(staff.signature_path),
        email=email,
    )


def _email_of(db: Session, staff_id: int) -> str:
    row = db.get(StaffContact, staff_id)
    return row.email if row else ""


def _set_email(db: Session, staff_id: int, email: str | None) -> None:
    email = (email or "").strip()
    if email and not valid_email(email):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "메일 주소를 확인하세요.")
    row = db.get(StaffContact, staff_id)
    if row is None:
        db.add(StaffContact(staff_id=staff_id, email=email))
    else:
        row.email = email


def _require_staff(db: Session, user: User, staff_id: int) -> Staff:
    staff = repo.get_staff(db, user.company_id, staff_id)
    if staff is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "담당요원을 찾을 수 없습니다.")
    return staff


@router.get("", response_model=list[StaffOut])
def list_staff(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return repo.list_staff(db, user.company_id)


@router.get("/all", response_model=list[StaffAdminOut])
def list_all_staff(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Staff).filter(Staff.company_id == user.company_id).order_by(Staff.active.desc(), Staff.id).all()
    emails = dict(db.query(StaffContact.staff_id, StaffContact.email).filter(StaffContact.staff_id.in_([s.id for s in rows]))) if rows else {}
    return [_admin_out(s, emails.get(s.id, "")) for s in rows]


@router.post("", response_model=StaffAdminOut)
def add_staff(body: StaffIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "담당요원 이름을 입력하세요.")
    staff = Staff(company_id=user.company_id, name=name, phone=(body.phone or "").strip())
    db.add(staff)
    db.flush()
    if body.email:
        _set_email(db, staff.id, body.email)
    db.commit()
    db.refresh(staff)
    return _admin_out(staff, _email_of(db, staff.id))


@router.patch("/{staff_id}", response_model=StaffAdminOut)
def update_staff(staff_id: int, body: StaffIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    staff = _require_staff(db, user, staff_id)
    fields = body.model_dump(exclude_unset=True)
    if "name" in fields:
        if not (fields["name"] or "").strip():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "담당요원 이름을 입력하세요.")
        staff.name = fields["name"].strip()
    if "phone" in fields:
        staff.phone = (fields["phone"] or "").strip()
    if fields.get("active") is not None:
        staff.active = fields["active"]
    if "email" in fields:
        _set_email(db, staff.id, fields["email"])
    db.commit()
    return _admin_out(staff, _email_of(db, staff.id))


@router.delete("/{staff_id}")
def delete_staff(staff_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    staff = _require_staff(db, user, staff_id)
    db.query(Site).filter(Site.assigned_staff_id == staff.id).update({Site.assigned_staff_id: None})
    db.query(Report).filter(Report.assigned_staff_id == staff.id).update({Report.assigned_staff_id: None})
    if staff.signature_path:
        Path(staff.signature_path).unlink(missing_ok=True)
    db.delete(staff)
    db.commit()
    return {"ok": True}


@router.post("/{staff_id}/signature", response_model=StaffAdminOut)
async def upload_staff_signature(
    staff_id: int,
    file: UploadFile,
    source: str = Form("drawn"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    staff = _require_staff(db, user, staff_id)
    dest = await save_signature_upload(file, f"staff_{staff.id}.png")
    staff.signature_path, staff.signature_source = str(dest), normalize_source(source)
    db.commit()
    return _admin_out(staff)


@router.delete("/{staff_id}/signature", response_model=StaffAdminOut)
def delete_staff_signature(staff_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    staff = _require_staff(db, user, staff_id)
    if staff.signature_path:
        Path(staff.signature_path).unlink(missing_ok=True)
    staff.signature_path, staff.signature_source = "", ""
    db.commit()
    return _admin_out(staff)


@router.get("/{staff_id}/signature")
def get_staff_signature(staff_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    staff = _require_staff(db, user, staff_id)
    if not staff.signature_path or not Path(staff.signature_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "등록된 서명이 없습니다.")
    return FileResponse(staff.signature_path, media_type="image/png")
