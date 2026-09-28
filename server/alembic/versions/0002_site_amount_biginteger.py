"""Sub-phase 33 (버그 수정): site.amount를 INTEGER(32비트, 21억 한도) -> BIGINT로.

실제 계약서(34억 원)로 현장 등록을 시험하다가 `psycopg.errors.NumericValueOutOfRange`로
발견했다 -- SQLite는 이 폭 제한을 안 지켜서 데스크톱 exe에서는 한 번도 안 걸렸던 버그.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-28
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("site", "amount", type_=sa.BigInteger())


def downgrade() -> None:
    op.alter_column("site", "amount", type_=sa.Integer())
