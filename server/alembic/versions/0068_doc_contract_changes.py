"""서류 자동화 계약의 계약변경 기록(2026-10-29 민재형 "내진성능평가는 단발성이라 [+ 관급 계약] 대신, 실정보고·설계변경이 자주 생기니 계약사항 변경") — sitok_doc_contract.changes.

[{no, at, by, reason, change_date, before: {칸: 값}, after: {칸: 값}, files: [이름]}] — 차수(no)는 기록 수가 아니라 마지막 차수 + 1(산안법 service_contract.changes와 같은 모양),
변경 계약서는 계약 폴더 "계약변경/N차/". 바꾸는 칸 = 착수일·완수일·계약금액(server/api/routers/sitok_docs.py CHANGE_KEYS).

Revision ID: 0068
Revises: 0067
Create Date: 2026-10-29
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0068"
down_revision: Union[str, None] = "0067"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_doc_contract", sa.Column("changes", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sitok_doc_contract", "changes")
