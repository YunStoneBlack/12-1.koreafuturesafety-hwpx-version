"""산안법 서류 자동화 일부 수정(2026-10-15 사용자 "산안법 일부수정안"): 계약 목록 최근 열람순 + 제출 현황 계산서 발행일.

- contract_view: 사람마다 계약(착수계 창)을 마지막으로 연 때 — 계약 목록 "최근 열람순"(현장 목록 site_view와 같은 방식).
- service_contract.invoice_date: 계산서 발행일(제출 현황 칸, 달력으로 넣음).

Revision ID: 0050
Revises: 0049
Create Date: 2026-10-15
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0050"
down_revision: Union[str, None] = "0049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contract_view",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("service_contract.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("viewed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.add_column("service_contract", sa.Column("invoice_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("service_contract", "invoice_date")
    op.drop_table("contract_view")
