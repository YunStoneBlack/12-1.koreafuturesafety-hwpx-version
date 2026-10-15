"""시특법 시설물 뱃지 자동(2026-10-15 민재형 "계약서 보고 뱃지 자동선택") — 사람이 🏷 뱃지로 바꾼 카드는 자동이 덮어쓰지 않게.

sitok_facility.badge_manual: 사람이 분야·관급 종류를 직접 바꾸면 True(계약서를 읽을 때마다 자동으로 다시 정하는 것을 멈춤).

Revision ID: 0051
Revises: 0050
Create Date: 2026-10-15
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0051"
down_revision: Union[str, None] = "0050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_facility", sa.Column("badge_manual", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("sitok_facility", "badge_manual")
