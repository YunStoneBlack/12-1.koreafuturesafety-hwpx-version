"""담당요원 K2B 계정(staff_k2b_account, 2026-10-01) — 요원 한 명에 K2B 계정 하나. 비밀번호는 암호화(Fernet, 열쇠 = .env.server K2B_SECRET_KEY).
K2B는 로그인한 계정 이름이 "점검자"로 고정 입력되므로, 그 회차 담당요원 본인 계정으로 제출해야 한다. [로그인 확인] 결과(check_*)도 함께.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-01
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "staff_k2b_account",
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id"), nullable=False),
        sa.Column("k2b_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("password_enc", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=False, server_default=""),
        sa.Column("check_status", sa.Text(), nullable=False, server_default=""),
        sa.Column("check_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("check_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("checked_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("staff_k2b_account")
