"""착수계·완수계 제출 기록(2026-10-06 사용자) — E-mail(바로 보냄)·직접 제출·우편 제출, 여러 방식 함께 가능. 기록이 있으면 제출(예전 "합본 PDF를 만들면 제출" 대신).

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-06
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contract_submit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id"), nullable=False, index=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("service_contract.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("submitted_on", sa.Date(), nullable=False),
        sa.Column("to_addr", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("contract_submit")
