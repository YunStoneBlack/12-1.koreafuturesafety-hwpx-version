"""시특법 설정(2026-10-10 3단계) — 기술자 시특법 칸(분야·결과표 기술등급), 사용 장비 표(sitok_equipment).

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tech_person", sa.Column("sitok_field", sa.Text(), nullable=False, server_default="건축"))
    op.add_column("tech_person", sa.Column("sitok_grade", sa.Text(), nullable=False, server_default=""))
    op.create_table(
        "sitok_equipment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id"), nullable=False, index=True),
        sa.Column("grp", sa.Text(), nullable=False, server_default=""),
        sa.Column("name", sa.Text(), nullable=False, server_default=""),
        sa.Column("model", sa.Text(), nullable=False, server_default=""),
        sa.Column("purpose", sa.Text(), nullable=False, server_default=""),
        sa.Column("photos", sa.JSON(), nullable=True),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_table("sitok_equipment")
    op.drop_column("tech_person", "sitok_grade")
    op.drop_column("tech_person", "sitok_field")
