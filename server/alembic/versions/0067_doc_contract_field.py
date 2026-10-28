"""서류 자동화 계약의 분야(2026-10-28 사용자 "서류 자동화 시특법이랑 동일하게 내진성능평가 서류 자동화 만들기") — sitok_doc_contract.field.

"시특법"(기본·예전 계약 전부) | "내진"(내진성능평가 용역 — 서류 자동화 › 내진성능평가 화면, 현장 연결 = 내진성능평가 건의 숨김 건물). 화면은 같은 코드를 쓰고
요청 머리 X-Docs-Field로 어느 쪽 목록인지 가림(server/api/routers/sitok_docs.py doc_field).

Revision ID: 0067
Revises: 0066
Create Date: 2026-10-28
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0067"
down_revision: Union[str, None] = "0066"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_doc_contract", sa.Column("field", sa.Text(), nullable=False, server_default="시특법"))


def downgrade() -> None:
    op.drop_column("sitok_doc_contract", "field")
