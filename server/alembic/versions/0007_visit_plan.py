"""방문 달력 — 방문 예정(visit_plan): 날짜·현장·요원·메모.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-30
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "visit_plan",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id"), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("site.id", ondelete="CASCADE"), nullable=False),
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id", ondelete="SET NULL"), nullable=True),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("memo", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_visit_plan_company_id", "visit_plan", ["company_id"])
    op.create_index("ix_visit_plan_site_id", "visit_plan", ["site_id"])
    op.create_index("ix_visit_plan_plan_date", "visit_plan", ["plan_date"])


def downgrade() -> None:
    op.drop_index("ix_visit_plan_plan_date", table_name="visit_plan")
    op.drop_index("ix_visit_plan_site_id", table_name="visit_plan")
    op.drop_index("ix_visit_plan_company_id", table_name="visit_plan")
    op.drop_table("visit_plan")
