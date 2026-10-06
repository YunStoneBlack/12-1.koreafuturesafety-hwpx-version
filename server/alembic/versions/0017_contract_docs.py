"""착수계·완수계 서류(2026-10-06) — 현장 용역 계약(service_contract), 기술자 명단(tech_person), 붙는 서류 그림(submit_doc).

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-06
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tech_person",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id"), nullable=False, index=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("address", sa.Text(), nullable=False, server_default=""),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("position", sa.Text(), nullable=False, server_default=""),
        sa.Column("join_date", sa.Date(), nullable=True),
        sa.Column("qualification", sa.Text(), nullable=False, server_default=""),
        sa.Column("grade", sa.Text(), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "service_contract",
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("site.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id"), nullable=False),
        sa.Column("client", sa.Text(), nullable=False, server_default=""),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("contract_no", sa.Text(), nullable=False, server_default=""),
        sa.Column("amount", sa.BigInteger(), nullable=True),
        sa.Column("contract_date", sa.Date(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("settle_amount", sa.BigInteger(), nullable=True),
        sa.Column("actual_end_date", sa.Date(), nullable=True),
        sa.Column("contract_pdf", sa.Text(), nullable=False, server_default=""),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("tech_person.id", ondelete="SET NULL"), nullable=True),
        sa.Column("participant_ids", sa.JSON(), nullable=True),
        sa.Column("start_made_at", sa.DateTime(), nullable=True),
        sa.Column("done_made_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=False, server_default=""),
    )
    op.create_table(
        "submit_doc",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id"), nullable=False, index=True),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("tech_person.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("file", sa.Text(), nullable=False, server_default=""),
        sa.Column("issued_on", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("submit_doc")
    op.drop_table("service_contract")
    op.drop_table("tech_person")
