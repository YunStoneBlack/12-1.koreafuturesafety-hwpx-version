"""DB의 파일 경로 칸 형식(2026-10-01) — 저장소(DATA_DIR) 안의 파일은 **저장소 기준 상대경로**로 저장하고, 꺼낼 때 다시 전체 경로로 돌려준다.

저장소를 다른 곳(형 회사 PC 등)으로 옮길 때 `.env.server`의 DATA_DIR 한 줄만 바꾸면 되게 하려는 것 — DB에 `C:\\Users\\...` 같은
전체 경로가 박혀 있으면 옮기는 순간 사진·PDF 연결이 다 끊긴다. 코드(라우터·한글 렌더러)는 지금처럼 전체 경로 문자열을 다루므로 손댈 필요가 없다.
- 넣을 때: 저장소 안의 전체 경로 → "26-1)_현장/05회차/사진/….jpg"(슬래시). 저장소 밖(예전 임시 폴더 등)·빈 값은 그대로.
- 꺼낼 때: 상대경로 → DATA_DIR / 상대경로(지금 PC 기준 전체 경로). 예전에 저장된 전체 경로는 그대로(옛 파일도 계속 열림).
"""
from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from core.db import DATA_DIR


def _norm(p: str) -> str:
    return os.path.normcase(os.path.abspath(p))


def to_stored(value: str) -> str:
    """전체 경로 → 저장소 기준 상대경로(저장소 밖이면 그대로)."""
    if not value or not os.path.isabs(value):
        return value
    root = _norm(str(DATA_DIR))
    full = _norm(value)
    if full == root or not full.startswith(root + os.sep):
        return value
    return Path(os.path.relpath(os.path.abspath(value), os.path.abspath(str(DATA_DIR)))).as_posix()


def to_full(value: str) -> str:
    """상대경로 → 지금 저장소 기준 전체 경로(이미 전체 경로면 그대로)."""
    if not value or os.path.isabs(value) or PureWindowsPath(value).drive:
        return value
    return str(DATA_DIR / Path(value))


class StoredPath(TypeDecorator):
    """파일 경로 칸 — 위 설명대로 넣고 꺼낼 때 바꿔 준다. DB 칸 자체는 그대로 Text(마이그레이션 없음)."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return to_stored(value) if isinstance(value, str) else value

    def process_result_value(self, value, dialect):
        return to_full(value) if isinstance(value, str) else value
