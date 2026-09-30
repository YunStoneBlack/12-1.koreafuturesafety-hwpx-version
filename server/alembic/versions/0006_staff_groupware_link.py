"""담당요원 ↔ 그룹웨어 직원정보 연결(staff_gw_link) — 담당요원 탭이 그룹웨어 직원 목록을 받아 이어 붙이고, 방문 달력 "나만"이 쓴다.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-30
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "staff_gw_link",
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id"), nullable=False),
        sa.Column("gw_employee_id", sa.Integer(), nullable=False),
        sa.Column("gw_username", sa.Text(), nullable=False),
        sa.Column("department", sa.Text(), nullable=False),
        sa.Column("position", sa.Text(), nullable=False),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "gw_employee_id", name="uq_staff_gw_link_employee"),
    )


def downgrade() -> None:
    op.drop_table("staff_gw_link")
