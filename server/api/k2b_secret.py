"""K2B 비밀번호 잠그기·풀기(2026-10-01) — Fernet(대칭 암호). 열쇠는 `.env.server`의 K2B_SECRET_KEY(DB와 따로 둔다 — DB 백업만으로는 못 풂).

열쇠를 잃으면 저장된 비밀번호를 풀 수 없다(요원이 다시 입력하면 됨). 형 회사 PC로 옮길 때 DB와 .env.server를 같이 옮길 것(README_DEPLOY 8번).
새 열쇠 만들기: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken


class K2bSecretError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = os.environ.get("K2B_SECRET_KEY", "").strip()
    if not key:
        raise K2bSecretError("K2B 비밀번호 열쇠(K2B_SECRET_KEY)가 서버 설정에 없습니다. 관리자에게 알려 주세요.")
    try:
        return Fernet(key.encode())
    except ValueError as err:
        raise K2bSecretError("K2B 비밀번호 열쇠(K2B_SECRET_KEY) 형식이 잘못됐습니다.") from err


def encrypt(password: str) -> str:
    return _fernet().encrypt(password.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as err:
        raise K2bSecretError("저장된 K2B 비밀번호를 풀 수 없습니다(서버 열쇠가 바뀜). 비밀번호를 다시 입력해 주세요.") from err
