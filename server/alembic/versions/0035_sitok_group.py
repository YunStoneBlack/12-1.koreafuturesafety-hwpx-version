"""시특법 동 묶음(sitok_group, sitok_facility.group_id·group_order) + 회차 동별 점검금액(sitok_report.amount_k) — 2026-10-12.

한 계약에 여러 동(숭의교회 본관 + B동)을 한 보고서로 — 동마다 회차는 따로, 만들 때 합침.

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: Union[str, None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sitok_group",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id"), nullable=False, index=True),
        sa.Column("name", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.add_column("sitok_facility", sa.Column("group_id", sa.Integer(), sa.ForeignKey("sitok_group.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_sitok_facility_group_id", "sitok_facility", ["group_id"])
    op.add_column("sitok_facility", sa.Column("group_order", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("sitok_report", sa.Column("amount_k", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("sitok_report", "amount_k")
    op.drop_column("sitok_facility", "group_order")
    op.drop_index("ix_sitok_facility_group_id", "sitok_facility")
    op.drop_column("sitok_facility", "group_id")
    op.drop_table("sitok_group")
