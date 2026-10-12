"""서류 자동화 · 시특법 관급 착수계·완료계(sitok_doc_contract 칸 더하기) — 2026-10-12.

고른 현장대리인·참여기술자(tech_person — 시특법 보고서 설정과 같은 명단), 착수계·완료계 만든 때.

Revision ID: 0041
Revises: 0040
Create Date: 2026-10-12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0041"
down_revision: Union[str, None] = "0040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_doc_contract", sa.Column("agent_id", sa.Integer(), sa.ForeignKey("tech_person.id", ondelete="SET NULL"), nullable=True))
    op.add_column("sitok_doc_contract", sa.Column("participant_ids", sa.JSON(), nullable=True))
    op.add_column("sitok_doc_contract", sa.Column("start_made_at", sa.DateTime(), nullable=True))
    op.add_column("sitok_doc_contract", sa.Column("done_made_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    for c in ("done_made_at", "start_made_at", "participant_ids", "agent_id"):
        op.drop_column("sitok_doc_contract", c)
