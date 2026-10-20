"""현장 기술지도 계약기간(2026-10-20 사용자 "기술지도계약서에도 공사기간 말고 우리 계약기간이 명시되어 있어 — 그걸 따르면 됨,
자동 배치도 우리 계약기간으로") — site_contact.contract_start·contract_end = K2B 기술지도계약서 아래쪽 "계약기간 ○년 ○월 ○일부터 ○년 ○월 ○일까지".
우리 계약기간 = 이 칸 → 연결된 용역 계약 착수~완수 → 공사기간(server/api/contract_sites.our_periods). 공사기간(site.period_*)은 보고서 표1 그대로.

Revision ID: 0058
Revises: 0057
Create Date: 2026-10-20
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0058"
down_revision: Union[str, None] = "0057"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("site_contact", sa.Column("contract_start", sa.Date(), nullable=True))
    op.add_column("site_contact", sa.Column("contract_end", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("site_contact", "contract_end")
    op.drop_column("site_contact", "contract_start")
