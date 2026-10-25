"""FMS 예약 등록(2026-10-25 사용자·민재형 "FMS 예약 등록") — fms_submission.run_at(비면 바로, 있으면 그 시각이 지나야 작업 프로그램이 집음).

Revision ID: 0064
Revises: 0063
Create Date: 2026-10-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0064"
down_revision: Union[str, None] = "0063"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("fms_submission", sa.Column("run_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("fms_submission", "run_at")
