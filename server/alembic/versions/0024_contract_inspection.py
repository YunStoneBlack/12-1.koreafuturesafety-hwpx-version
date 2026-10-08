"""완수계 "검사 및 납품조서" 표 값(2026-10-08 형·사용자) — 계약·준공 횟수·공급가액·부가세·계. 완수내역서 PDF에서 읽고 화면에서 고침.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-08
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("service_contract", sa.Column("inspection", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("service_contract", "inspection")
