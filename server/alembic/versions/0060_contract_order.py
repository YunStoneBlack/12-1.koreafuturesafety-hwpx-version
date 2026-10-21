"""발주처 과업지시서(2026-10-21 민재형) — sitok_contract.order_pdf(StoredPath)·deliver(JSON: 납품 항목 책자·USB·비고·출처).
시설물 화면 계약 카드에서 올리고, 옹벽 보고서는 우리 과업지시서 대신 그 PDF를 부록3에 끼우며 과업수행계획서 5. 납품 항목을 채움.

Revision ID: 0060
Revises: 0059
Create Date: 2026-10-21
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0060"
down_revision: Union[str, None] = "0059"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_contract", sa.Column("order_pdf", sa.Text(), nullable=False, server_default=""))
    op.add_column("sitok_contract", sa.Column("deliver", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sitok_contract", "deliver")
    op.drop_column("sitok_contract", "order_pdf")
