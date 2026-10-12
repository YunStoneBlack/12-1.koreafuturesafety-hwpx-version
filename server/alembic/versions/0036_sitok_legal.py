"""시특법 법정 시설물 여부(sitok_facility.legal) — 2026-10-12.

법정(1·2·3종)이 아닌데 관리주체가 같은 양식으로 자체 점검을 받는 시설물(시설물관리대장 없음): 틀은 2종/3종일반 중 고르고 결과표 종별 "해당없음".

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_facility", sa.Column("legal", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("sitok_facility", "legal")
