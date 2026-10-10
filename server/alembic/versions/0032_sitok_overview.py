"""시특법 회차 전경사진(sitok_report.overview) — 2026-10-11.

[{id, file(회차 폴더 기준 상대 경로), title, ai(AI가 붙인 제목 — 점검자 확인 전)}] 순서 그대로 보고서 10쪽(첫 장)·11쪽(6장씩)에.

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-11
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_report", sa.Column("overview", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sitok_report", "overview")
