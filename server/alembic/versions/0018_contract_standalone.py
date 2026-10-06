"""용역 계약을 현장 없이도(2026-10-06 형: 착수계가 현장 등록보다 먼저) — service_contract에 번호(id) 기본키, site_id는 나중에 연결하는 칸
(현장 하나에 계약 하나, 현장이 지워지면 연결만 끊김). 빈 행(창만 열어 보고 아무것도 안 넣은 것)은 지운다.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-06
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DELETE FROM service_contract WHERE coalesce(title, '') = '' AND coalesce(client, '') = '' "
               "AND start_made_at IS NULL AND done_made_at IS NULL")
    op.add_column("service_contract", sa.Column("id", sa.Integer(), sa.Identity(), nullable=False))
    op.add_column("service_contract", sa.Column("created_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE service_contract SET created_at = coalesce(updated_at, now())")
    op.drop_constraint("service_contract_pkey", "service_contract", type_="primary")
    op.create_primary_key("service_contract_pkey", "service_contract", ["id"])
    op.alter_column("service_contract", "site_id", nullable=True)
    op.drop_constraint("service_contract_site_id_fkey", "service_contract", type_="foreignkey")
    op.create_foreign_key("service_contract_site_id_fkey", "service_contract", "site", ["site_id"], ["id"], ondelete="SET NULL")
    op.create_unique_constraint("uq_service_contract_site", "service_contract", ["site_id"])
    op.create_index("ix_service_contract_company_id", "service_contract", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_service_contract_company_id", "service_contract")
    op.drop_constraint("uq_service_contract_site", "service_contract", type_="unique")
    op.drop_constraint("service_contract_site_id_fkey", "service_contract", type_="foreignkey")
    op.execute("DELETE FROM service_contract WHERE site_id IS NULL")
    op.create_foreign_key("service_contract_site_id_fkey", "service_contract", "site", ["site_id"], ["id"], ondelete="CASCADE")
    op.drop_constraint("service_contract_pkey", "service_contract", type_="primary")
    op.create_primary_key("service_contract_pkey", "service_contract", ["site_id"])
    op.drop_column("service_contract", "created_at")
    op.drop_column("service_contract", "id")
