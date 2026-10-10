"""시특법 정기안전점검(2026-10-10) — 시설물(sitok_facility)·점검 용역 계약(sitok_contract). 설계: 바탕화면 "시특법 견본\인수인계.md".

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _text(name: str, default: str = ""):
    return sa.Column(name, sa.Text(), nullable=False, server_default=default)


def upgrade() -> None:
    op.create_table(
        "sitok_facility",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id"), nullable=False, index=True),
        _text("fms_no"), _text("name"), _text("template", "2종"), _text("kind", "건축물"), _text("use_type"), _text("main_use"),
        _text("address"), _text("owner_name"), _text("owner_type"), _text("owner_phone"),
        sa.Column("completion_date", sa.Date(), nullable=True),
        _text("structure"),
        sa.Column("floors_above", sa.Integer(), nullable=True), sa.Column("floors_below", sa.Integer(), nullable=True),
        sa.Column("floors_roof", sa.Integer(), nullable=True), sa.Column("max_height", sa.Float(), nullable=True),
        sa.Column("total_area", sa.Float(), nullable=True), sa.Column("building_area", sa.Float(), nullable=True),
        sa.Column("ledger", sa.JSON(), nullable=True),
        _text("ledger_pdf"), _text("memo"), _text("created_by"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "sitok_contract",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id"), nullable=False, index=True),
        sa.Column("facility_id", sa.Integer(), sa.ForeignKey("sitok_facility.id", ondelete="CASCADE"), nullable=False, index=True),
        _text("sector", "민간"), _text("title"), _text("contract_no"),
        sa.Column("contract_date", sa.Date(), nullable=True), sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True), _text("halves", "연간"),
        sa.Column("first_half_end", sa.Date(), nullable=True), sa.Column("second_half_start", sa.Date(), nullable=True),
        sa.Column("amount", sa.BigInteger(), nullable=True), _text("rep_name"), _text("joint_type", "독자수행"),
        sa.Column("joint_pct", sa.Integer(), nullable=False, server_default="100"),
        _text("bid_method", "수의계약"), _text("field", "건축"), _text("contract_pdf"), _text("created_by"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sitok_contract")
    op.drop_table("sitok_facility")
