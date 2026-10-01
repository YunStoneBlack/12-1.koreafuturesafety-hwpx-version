"""K2B 제출 기록·대기열(k2b_submission, 2026-10-01) — 현장 화면 보고서 줄 [K2B 제출]. 이 PC 작업 프로그램(server/worker/k2b_worker.py)이 queued를 꺼내 실행.
status: queued → running → done(저장됨) | failed(이유·화면). options = 창에서 고른 K2B 전용 항목(JSON). round_no = K2B가 매긴 새 차수.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-01
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "k2b_submission",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id"), nullable=False, index=True),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("report.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("round_no", sa.Integer(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("screenshot", sa.Text(), nullable=False, server_default=""),
        sa.Column("log", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("k2b_submission")
