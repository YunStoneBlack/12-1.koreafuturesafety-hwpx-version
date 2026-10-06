"""용역 계약의 발주처 계약 담당자 이름·연락처·이메일(2026-10-06 사용자). 계약서에 적혀 있으면 읽어서 채움, 손으로 고칠 수 있음.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-06
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLS = ("client_manager", "client_phone", "client_email")


def upgrade() -> None:
    for c in COLS:
        op.add_column("service_contract", sa.Column(c, sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    for c in COLS:
        op.drop_column("service_contract", c)
