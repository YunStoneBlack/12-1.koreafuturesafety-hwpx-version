"""현장 발주처·감리단 연락처(site_contact) — 고객사 전송 받는 사람 체크 항목.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-30
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "site_contact",
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("site.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("owner_name", sa.Text(), nullable=False),
        sa.Column("owner_email", sa.Text(), nullable=False),
        sa.Column("supervisor_name", sa.Text(), nullable=False),
        sa.Column("supervisor_email", sa.Text(), nullable=False),
        sa.Column("retired_emails", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("site_contact")
