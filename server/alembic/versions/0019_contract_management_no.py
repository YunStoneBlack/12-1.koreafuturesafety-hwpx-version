"""용역 계약 관리번호(2026-10-06 사용자: 보고서 자동화 현장처럼 "26-3)_용역명" — 자동생성·수정 가능, 현장 번호와 따로 셈).

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-06
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("service_contract", sa.Column("management_no", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("service_contract", "management_no")
