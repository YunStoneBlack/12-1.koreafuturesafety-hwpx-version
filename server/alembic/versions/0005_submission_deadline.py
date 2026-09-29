"""Sub-phase 65: 제출 현황·지도 기한 알림 — report_submit_mark(직접 제출함), staff_contact(요원 메일), deadline_alert(알림 보낸 기록).

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-29
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_submit_mark",
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("report.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("marked_at", sa.DateTime(), nullable=False),
        sa.Column("marked_by", sa.Text(), nullable=False),
    )
    op.create_table(
        "staff_contact",
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False),
    )
    op.create_table(
        "deadline_alert",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("site.id", ondelete="CASCADE"), nullable=False),
        sa.Column("deadline", sa.Date(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.Column("recipients", sa.Text(), nullable=False),
        sa.UniqueConstraint("site_id", "deadline", "kind", "channel", name="uq_deadline_alert"),
    )
    op.create_index("ix_deadline_alert_site_id", "deadline_alert", ["site_id"])


def downgrade() -> None:
    op.drop_index("ix_deadline_alert_site_id", table_name="deadline_alert")
    op.drop_table("deadline_alert")
    op.drop_table("staff_contact")
    op.drop_table("report_submit_mark")
