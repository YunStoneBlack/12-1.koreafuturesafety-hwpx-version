"""용역 계약의 발주처 사업 담당자(사업부서) 이름·연락처·이메일(2026-10-06 형) — 착수계·완수계 E-mail 기본 받는 사람.
0020의 client_* 는 계약 담당자(계약부서).

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-06
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLS = ("biz_manager", "biz_phone", "biz_email")


def upgrade() -> None:
    for c in COLS:
        op.add_column("service_contract", sa.Column(c, sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    for c in COLS:
        op.drop_column("service_contract", c)
