"""시특법 시설물 도면(sitok_facility.drawings) — 2026-10-12.

사용자: 첨부용 도면(평·입·단면도 — 보고서 1.2.9 관련 설계도면 뒤에 붙음), 구조일반사항·건축개요 도면(건축물대장처럼 시설물 현황 AI가 읽음).
시설물에 한 번 올려 다음 회차에도 쓰고, 증축·인테리어 등으로 바뀌면 바꿈.

Revision ID: 0039
Revises: 0038
Create Date: 2026-10-12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0039"
down_revision: Union[str, None] = "0038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_facility", sa.Column("drawings", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sitok_facility", "drawings")
