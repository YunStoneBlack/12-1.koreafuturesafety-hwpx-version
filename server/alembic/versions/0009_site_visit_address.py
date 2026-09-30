"""현장 지도 방문 주소(site_contact.visit_address) — [📍 지도] 버튼용, 비어 있으면 현장 주소.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-30
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("site_contact", sa.Column("visit_address", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("site_contact", "visit_address")
