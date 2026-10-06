"""K2B 제출 화면을 구역별 여러 장으로(2026-10-07 사용자 — 상세내용·불량사업장/대형사고·사진·문제점까지 들어갔는지 확인).

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-07
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("k2b_submission", sa.Column("screenshots", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("k2b_submission", "screenshots")
