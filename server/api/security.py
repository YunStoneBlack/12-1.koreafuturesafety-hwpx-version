"""비밀번호 해싱 — `bcrypt` 패키지를 직접 쓴다.

원래 passlib[bcrypt]로 만들었는데, passlib 1.7.4(마지막 릴리즈, 이후 관리가 끊김)가
최신 bcrypt 패키지(4.1+/5.x)의 내부 API 변경을 못 따라가서 `password_hash()` 호출 시
`AttributeError: module 'bcrypt' has no attribute '__about__'`로 깨지는 걸 실제로 겪었다
(2026-09-28, 이 PC에서 재현). passlib를 아예 걷어내고 bcrypt를 직접 쓰는 쪽이 낡은
호환 레이어에 계속 발목 잡히는 것보다 안전하다."""

from __future__ import annotations

import bcrypt

_ENCODING = "utf-8"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(_ENCODING), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(_ENCODING), hashed.encode("ascii"))
    except ValueError:
        # 저장된 해시가 깨져있거나 형식이 다른 경우 — 검증 실패로 처리(예외로 500 내지 않음).
        return False
