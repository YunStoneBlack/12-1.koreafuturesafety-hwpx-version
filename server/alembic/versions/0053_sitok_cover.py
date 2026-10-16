"""계약이 맡는 건물 정하기(2026-10-16 민재형 개편) — 건명·내역서 이름 → 전 계약 → 현장 전체(⚠ 확인), "전체"면 나중에 생기는 건물까지.

- sitok_doc_contract.cover: 맡는 건물을 정한 방식 — ""(사람이 고름·예전 계약, 안 바꿈) / "auto"(건명·내역서 이름이나 같은 모양 전 계약으로 — 건물이 늘면 다시 봄) /
  "check"(못 정해 현장 전체 또는 남은 건물 — 건물이 둘 이상이면 ⚠ 맡는 건물 확인, 건물이 늘면 다시 봄) / "all"(사람이 현장 전체로 확인 — 늘어난 건물까지).
- sitok_doc_contract.est_parts: 관급 내역서(산출내역서·과업내용서)에서 읽은 건물·사업장별 [{name, amount}] — 맡는 건물·건물별 금액에 씀.

Revision ID: 0053
Revises: 0052
Create Date: 2026-10-16
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0053"
down_revision: Union[str, None] = "0052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_doc_contract", sa.Column("cover", sa.Text(), nullable=False, server_default=""))
    op.add_column("sitok_doc_contract", sa.Column("est_parts", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sitok_doc_contract", "est_parts")
    op.drop_column("sitok_doc_contract", "cover")
