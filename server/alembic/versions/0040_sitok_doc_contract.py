"""서류 자동화 · 시특법 계약(sitok_doc_contract) — 2026-10-12.

사용자: 산안법처럼 보고서 쪽과 따로 + 현장 연결(민간·관급). 민간 = 계약서를 우리가 작성(회차 줄 · 정기/정밀, 끝 없는 계약), 관급 = 착수계·완료계(2단계).
계약 담당·현장 담당 이름·연락처·이메일.

Revision ID: 0040
Revises: 0039
Create Date: 2026-10-12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0040"
down_revision: Union[str, None] = "0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    t = lambda name: sa.Column(name, sa.Text(), nullable=False, server_default="")  # noqa: E731
    op.create_table(
        "sitok_doc_contract",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id"), nullable=False, index=True),
        sa.Column("facility_id", sa.Integer(), sa.ForeignKey("sitok_facility.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("sector", sa.Text(), nullable=False, server_default="민간"),
        t("doc_no"), t("client"), t("client_rep"), t("client_biz_no"), t("client_address"), t("facility_name"), t("location"), t("spec"),
        t("title"), t("contract_no"),
        sa.Column("amount", sa.BigInteger(), nullable=True),
        sa.Column("rounds", sa.JSON(), nullable=True),
        sa.Column("open_ended", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("unit", sa.JSON(), nullable=True),
        sa.Column("guarantee", sa.Text(), nullable=False, server_default="-"),
        sa.Column("delay_rate", sa.Text(), nullable=False, server_default="-"),
        sa.Column("contract_date", sa.Date(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        t("client_manager"), t("client_phone"), t("client_email"), t("site_manager"), t("site_phone"), t("site_email"),
        t("contract_pdf"),
        sa.Column("made_at", sa.DateTime(), nullable=True),
        sa.Column("report_contract_id", sa.Integer(), nullable=True),
        t("memo"), t("created_by"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        t("updated_by"),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("sitok_doc_contract")
