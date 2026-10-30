"""시특법 결함 동(구역) 칸 sitok_defect.zone(2026-10-30 사용자 "시설물은 1개인데 연결된 동으로 동이 여러 개 — 동마다 결함현황표, 전회차 가져오기가 제대로 안 됨").

시설물 1개 안 동(통계청·선거관리위원회·통계교육원·지하층 …)마다 층별 결함 — 번호·사진·사진첩은 동+층마다. 동 차례는 시설물 ledger["zones"].
빈 글 = 동 없음(지금까지와 같음).

Revision ID: 0071
Revises: 0070
Create Date: 2026-10-30
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0071"
down_revision: Union[str, None] = "0070"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_defect", sa.Column("zone", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("sitok_defect", "zone")
