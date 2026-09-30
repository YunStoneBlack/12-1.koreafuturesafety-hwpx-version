"""방문 예정 출처(visit_plan.source) — 자동 배치가 넣은 것(auto)과 사람이 넣거나 옮긴 것(manual, 📌 고정)을 가른다(2026-10-01).

자동 배치를 다시 하면 auto이면서 아직 안 간 예정만 지우고 다시 짠다. 기존 예정은 전부 사람이 넣은 것이라 manual.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-01
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("visit_plan", sa.Column("source", sa.Text(), nullable=False, server_default="manual"))


def downgrade() -> None:
    op.drop_column("visit_plan", "source")
