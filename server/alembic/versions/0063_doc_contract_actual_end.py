"""시특법 서류 계약 실제 준공일(2026-10-22 사용자 "시특법 완수계도 실제 준공일 칸 만들고 문서번호 끝번호랑 발송일 실제준공일로, 없으면 원래 준공일")
— sitok_doc_contract.actual_end_date(비면 end_date). 산안법 contract.actual_end_date(0017)와 같은 뜻.

Revision ID: 0063
Revises: 0062
Create Date: 2026-10-22
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0063"
down_revision: Union[str, None] = "0062"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_doc_contract", sa.Column("actual_end_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("sitok_doc_contract", "actual_end_date")
