"""시특법 보고서 회차(2026-10-10 4단계) — sitok_report.

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sitok_report",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id"), nullable=False, index=True),
        sa.Column("facility_id", sa.Integer(), sa.ForeignKey("sitok_facility.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("sitok_contract.id", ondelete="SET NULL"), nullable=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("half", sa.Text(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True), sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column("chief_id", sa.Integer(), sa.ForeignKey("tech_person.id", ondelete="SET NULL"), nullable=True),
        sa.Column("participant_ids", sa.JSON(), nullable=True),
        sa.Column("source_hwpx", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("out_hwpx", sa.Text(), nullable=False, server_default=""),
        sa.Column("out_pdf", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.Text(), nullable=False, server_default=""),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("made_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sitok_report")
