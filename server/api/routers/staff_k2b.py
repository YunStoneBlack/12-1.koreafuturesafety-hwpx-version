"""담당요원 K2B 계정(2026-10-01) — 담당요원 탭에서 요원마다 K2B 아이디·비밀번호 등록, [로그인 확인].

K2B는 로그인한 계정 이름이 보고서 "점검자"로 고정되므로 그 회차 담당요원 본인 계정으로 제출한다(그룹웨어 계정 = 담당요원 = K2B 계정 주인).
- 입력·수정·삭제·로그인 확인은 **본인**(그룹웨어 로그인 아이디로 이어진 요원) 또는 **그룹웨어 관리자**만(사용자 결정 (나)).
- 비밀번호는 암호화(server/api/k2b_secret.py)해서 DB에 — 화면으로 다시 내보내지 않는다(등록 여부만).

- `GET /staff-k2b` — 요원마다 K2B 아이디·등록 여부·확인 결과·고칠 수 있는지.
- `PUT /staff-k2b/{staff_id} {k2b_id, password}` — 저장(비밀번호 비우면 예전 것 유지). 바꾸면 확인 결과는 지움.
- `DELETE /staff-k2b/{staff_id}` — 계정 지우기.
- `POST /staff-k2b/{staff_id}/check` — 이 PC에서 K2B 로그인만 해 보고 결과 저장(20~40초).
- `GET /staff-k2b/{staff_id}/check-shot` — 마지막 확인 때 찍은 K2B 화면.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_db import Staff
from core.models_web import StaffK2bAccount, User
from server.api import k2b_login, k2b_secret, repo
from server.api.deps import get_current_user, get_db, is_groupware_admin
from server.api.routers.staff_groupware import my_staff_id

router = APIRouter(prefix="/staff-k2b", tags=["staff"])


def _out(staff: Staff, acc: StaffK2bAccount | None, can_edit: bool) -> dict:
    return {
        "staff_id": staff.id, "name": staff.name, "can_edit": can_edit,
        "k2b_id": acc.k2b_id if acc else "", "has_password": bool(acc and acc.password_enc),
        "updated_at": acc.updated_at.isoformat() if acc and acc.updated_at else None,
        "check_status": acc.check_status if acc else "", "check_name": acc.check_name if acc else "",
        "check_message": acc.check_message if acc else "",
        "checked_at": acc.checked_at.isoformat() if acc and acc.checked_at else None,
    }


def _editable(request: Request, db: Session, user: User, staff_id: int) -> bool:
    return is_groupware_admin(request) or my_staff_id(db, user) == staff_id


def _staff_or_404(db: Session, user: User, staff_id: int) -> Staff:
    staff = repo.get_staff(db, user.company_id, staff_id)
    if staff is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "담당요원을 찾을 수 없습니다.")
    return staff


def _require_edit(request: Request, db: Session, user: User, staff_id: int) -> None:
    if not _editable(request, db, user, staff_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "K2B 계정은 본인 또는 그룹웨어 관리자만 바꿀 수 있습니다.")


@router.get("")
def list_accounts(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    admin = is_groupware_admin(request)
    me = my_staff_id(db, user)
    accounts = {a.staff_id: a for a in db.query(StaffK2bAccount).filter(StaffK2bAccount.company_id == user.company_id)}
    staff = db.query(Staff).filter(Staff.company_id == user.company_id).order_by(Staff.name).all()
    return {"is_admin": admin, "me_staff_id": me,
            "staff": [_out(s, accounts.get(s.id), admin or me == s.id) for s in staff]}


class AccountIn(BaseModel):
    k2b_id: str
    password: str = ""


@router.put("/{staff_id}")
def save_account(staff_id: int, body: AccountIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    staff = _staff_or_404(db, user, staff_id)
    _require_edit(request, db, user, staff_id)
    k2b_id = body.k2b_id.strip()
    if not k2b_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "K2B 아이디를 입력하세요.")
    acc = db.get(StaffK2bAccount, staff_id)
    if acc is None:
        if not body.password:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "K2B 비밀번호를 입력하세요.")
        acc = StaffK2bAccount(staff_id=staff_id, company_id=user.company_id)
        db.add(acc)
    try:
        if body.password:
            acc.password_enc = k2b_secret.encrypt(body.password)
    except k2b_secret.K2bSecretError as err:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(err)) from err
    if body.password or acc.k2b_id != k2b_id:  # 아이디·비밀번호가 바뀌면 지난 확인 결과는 더 이상 맞지 않음
        acc.check_status = acc.check_name = acc.check_message = ""
        acc.checked_at = None
    acc.k2b_id = k2b_id
    acc.updated_at = k2b_login.now()
    acc.updated_by = user.display_name or ""
    db.commit()
    return _out(staff, acc, True)


@router.delete("/{staff_id}")
def delete_account(staff_id: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _staff_or_404(db, user, staff_id)
    _require_edit(request, db, user, staff_id)
    acc = db.get(StaffK2bAccount, staff_id)
    if acc is not None:
        db.delete(acc)
        db.commit()
    (k2b_login.SHOT_DIR / f"login_staff_{staff_id}.png").unlink(missing_ok=True)
    return {"ok": True}


@router.post("/{staff_id}/check")
def check_account(staff_id: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """K2B에 로그인만 해 본다(동기 — 20~40초, FastAPI가 스레드에서 돌려 다른 요청은 안 막힘)."""
    staff = _staff_or_404(db, user, staff_id)
    _require_edit(request, db, user, staff_id)
    acc = db.get(StaffK2bAccount, staff_id)
    if acc is None or not acc.k2b_id or not acc.password_enc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "먼저 K2B 아이디·비밀번호를 저장하세요.")
    try:
        password = k2b_secret.decrypt(acc.password_enc)
    except k2b_secret.K2bSecretError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
    try:
        result = k2b_login.check_login(staff_id, acc.k2b_id, password, staff.name)
    except Exception as err:  # noqa: BLE001 — 크롬을 못 띄움 등, 이유를 그대로 보여 준다
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"K2B 로그인 확인을 하지 못했습니다: {str(err).splitlines()[0][:200]}") from err
    acc.check_status, acc.check_name, acc.check_message = result.status, result.name, result.message
    acc.checked_at = k2b_login.now()
    db.commit()
    return _out(staff, acc, True)


@router.get("/{staff_id}/check-shot")
def check_shot(staff_id: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _staff_or_404(db, user, staff_id)
    _require_edit(request, db, user, staff_id)  # 로그인 뒤 화면이라 본인·관리자만
    shot = Path(k2b_login.SHOT_DIR / f"login_staff_{staff_id}.png")
    if not shot.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "아직 확인한 화면이 없습니다.")
    return FileResponse(shot, media_type="image/png", headers={"Cache-Control": "no-store"})
