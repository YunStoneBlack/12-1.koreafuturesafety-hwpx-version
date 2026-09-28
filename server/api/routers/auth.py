from __future__ import annotations

import datetime
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from core.models_web import User, UserSession
from server.api.deps import get_current_user, get_db
from server.api.security import verify_password
from server.schemas.auth import LoginRequest, UserOut
from server.settings import SESSION_COOKIE_NAME, SESSION_COOKIE_SECURE, SESSION_TTL_HOURS, WEB_BASE_PATH

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email, User.active.is_(True)).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "이메일 또는 비밀번호가 올바르지 않습니다.")

    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.datetime.now() + datetime.timedelta(hours=SESSION_TTL_HOURS)
    db.add(UserSession(id=session_id, user_id=user.id, expires_at=expires_at))
    db.commit()

    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite="lax",
        max_age=SESSION_TTL_HOURS * 3600,
        path=WEB_BASE_PATH or "/",  # 그룹웨어 쪽 경로로는 이 쿠키를 보내지 않음
    )
    return user


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        db.query(UserSession).filter(UserSession.id == session_id).delete()
        db.commit()
    response.delete_cookie(SESSION_COOKIE_NAME, path=WEB_BASE_PATH or "/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
