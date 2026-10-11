"""시특법 회차 면담·변경사항(sitok_report.survey) — 2026-10-11.

{"repairs": [{period, kind, method, where, note}] — 1.2.7 보수·보강 이력에 더할 줄(면담),
 "changes": {"구분": {before, after, where, note}} — 1.2.8 변경사항이 있는 항목만(나머지는 "변경사항없음")}

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-11
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_report", sa.Column("survey", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sitok_report", "survey")
