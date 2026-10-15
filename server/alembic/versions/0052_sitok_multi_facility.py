"""계약 하나 ↔ 시설물 여럿(보고서 따로) — 2026-10-15 민재형 "관급-6 계약 카드, 시설물 카드 관급-6-1·6-2 / 발주처가 나눈 계약 관급-10-1·10-2".

동 추가(묶음 — 한 보고서)와는 다름: 시설물마다 보고서·회차·FMS가 따로. 시설물 번호 "관급-6-1"·"관급-6-2"(같은 카드 = 같은 앞 번호 관급-6).
- sitok_doc_contract.facility_ids: 이 계약이 덮는 시설물(각 시설물의 대표 동 id) — 비면 [facility_id](예전 계약 그대로).
- sitok_doc_contract.amounts: 시설물별 금액 {시설물 id: 원} — 계약 하나에 시설물이 여럿일 때(합 = 계약금액).
- sitok_doc_contract.report_contracts: 시설물별 보고서 쪽 계약 {시설물 id: sitok_contract id}(report_contract_id는 첫 시설물 것).

Revision ID: 0052
Revises: 0051
Create Date: 2026-10-15
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0052"
down_revision: Union[str, None] = "0051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_doc_contract", sa.Column("facility_ids", sa.JSON(), nullable=True))
    op.add_column("sitok_doc_contract", sa.Column("amounts", sa.JSON(), nullable=True))
    op.add_column("sitok_doc_contract", sa.Column("report_contracts", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sitok_doc_contract", "report_contracts")
    op.drop_column("sitok_doc_contract", "amounts")
    op.drop_column("sitok_doc_contract", "facility_ids")
