"""보고서 메일(2026-10-25 사용자·민재형 "시특법에 메일 기능 + 산안법에도 예약") — mail_job.

시특법 [📧 보고서 보내기](합본이 커서 내려받기 링크 — 받는 사람은 로그인 없이 /report/share/{token}) + 산안법 고객사 전송 예약.
run_at = 예약 시각(비면 바로 보낸 기록), 작업 프로그램(server/worker/mail_worker.py)이 시각이 지난 것을 보냄.

Revision ID: 0065
Revises: 0064
Create Date: 2026-10-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0065"
down_revision: Union[str, None] = "0064"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mail_job",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False, server_default="sitok"),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("to_addr", sa.Text(), nullable=False, server_default=""),
        sa.Column("cc_addr", sa.Text(), nullable=False, server_default=""),
        sa.Column("subject", sa.Text(), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("run_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("tries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("downloads", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_download_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_mail_job_company_id", "mail_job", ["company_id"])
    op.create_index("ix_mail_job_report", "mail_job", ["kind", "report_id"])
    op.create_index("ix_mail_job_token", "mail_job", ["token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_mail_job_token", table_name="mail_job")
    op.drop_index("ix_mail_job_report", table_name="mail_job")
    op.drop_index("ix_mail_job_company_id", table_name="mail_job")
    op.drop_table("mail_job")
