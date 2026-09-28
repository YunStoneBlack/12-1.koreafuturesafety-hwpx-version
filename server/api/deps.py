"""FastAPI 의존성 — DB 세션과 "로그인한 사용자"를 해결한다.

인증(get_current_user)이 곧 그 사용자의 company_id를 해결하는 지점이기도 하다 — 이렇게
합쳐둔 이유: company_id를 모르는 상태로 데이터에 접근하는 라우트 자체가 존재할 수 없게
만들기 위함이다(라우터는 항상 이 함수가 준 user.company_id를 들고 server/api/repo.py를
거쳐서만 조회한다)."""

from __future__ import annotations

import datetime

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from core.db import SessionLocal
from core.models_web import User, UserSession
from server.settings import SESSION_COOKIE_NAME


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다.")

    session_row = db.get(UserSession, session_id)
    if session_row is None or session_row.expires_at < datetime.datetime.now():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "세션이 만료되었습니다. 다시 로그인해주세요.")

    user = db.get(User, session_row.user_id)
    if user is None or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "계정을 찾을 수 없습니다.")
    return user
