"""FastAPI 의존성 — DB 세션과 "로그인한 사용자"를 해결한다.

인증(get_current_user)이 곧 그 사용자의 company_id를 해결하는 지점이기도 하다 — 이렇게
합쳐둔 이유: company_id를 모르는 상태로 데이터에 접근하는 라우트 자체가 존재할 수 없게
만들기 위함이다(라우터는 항상 이 함수가 준 user.company_id를 들고 server/api/repo.py를
거쳐서만 조회한다)."""

from __future__ import annotations

import datetime
import hmac
import secrets
from urllib.parse import unquote

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from core.db import SessionLocal
from core.models_web import User, UserSession
from server.settings import GROUPWARE_COMPANY_ID, GROUPWARE_RELAY_SECRET, SESSION_COOKIE_NAME


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _groupware_user(request: Request, db: Session) -> User:
    """그룹웨어 모드 — nginx가 그룹웨어 로그인을 확인하고 붙여준 헤더로 사용자를 알아본다.
    비밀값이 맞지 않으면(= nginx를 안 거친 요청) 사용자 헤더를 믿지 않는다. 처음 온 직원은 자동 등록(비밀번호 로그인 불가)."""
    secret = request.headers.get("X-Relay-Secret", "")
    username = unquote(request.headers.get("X-Gw-User", "")).strip()
    if not secret or not hmac.compare_digest(secret, GROUPWARE_RELAY_SECRET) or not username:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "그룹웨어에 로그인한 뒤 '보고서 자동화' 메뉴로 들어와 주세요.")
    display_name = unquote(request.headers.get("X-Gw-Name", "")).strip() or username
    key = f"gw:{username}"  # email 칸(고유)을 그룹웨어 아이디 보관용으로 쓴다
    user = db.query(User).filter(User.email == key).first()
    if user is None:
        user = User(
            company_id=GROUPWARE_COMPANY_ID,
            email=key,
            password_hash="!" + secrets.token_hex(16),  # bcrypt 형식이 아니라 비밀번호 로그인은 절대 성공 못 함
            display_name=display_name,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif user.display_name != display_name:
        user.display_name = display_name  # 그룹웨어에서 이름이 바뀌면 따라간다
        db.commit()
    if not user.active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "보고서 자동화 사용이 중지된 계정입니다.")
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    if GROUPWARE_RELAY_SECRET:
        return _groupware_user(request, db)

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


def is_groupware_admin(request: Request) -> bool:
    """그룹웨어 관리자인지(2026-10-01 — K2B 계정은 본인 또는 관리자만 입력). nginx가 그룹웨어 로그인 확인 뒤 붙이는 X-Gw-Role
    ("ADMIN"/"USER", 그룹웨어 ReportController)을 쓰고, 비밀값이 맞을 때만 믿는다. 그룹웨어 없이 자체 로그인 모드면 역할 구분이 없어 True."""
    if not GROUPWARE_RELAY_SECRET:
        return True
    secret = request.headers.get("X-Relay-Secret", "")
    if not secret or not hmac.compare_digest(secret, GROUPWARE_RELAY_SECRET):
        return False
    return unquote(request.headers.get("X-Gw-Role", "")).strip().upper() == "ADMIN"
