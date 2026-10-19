"""시설물(건물) 번호에 뒷번호를 안 붙임(2026-10-19 민재형 "시설물은 관급-9에 총 5개를 등재, 보고서는 2·3개로 나눔 — 시설물 관급-9-1 이런 번호 안 생기게").

- sitok_facility.book_order: 카드 안 보고서(상자) 순서 1, 2, …(보고서 구성 상자 순서 — 전엔 뒷번호 "관급-9-2"의 2가 이 순서였음). 0 = 상자 하나뿐/예전.
- 있던 "관급-9-2" 같은 번호 → mgmt_no "관급-9", book_order 2.
계약 번호(9-1·9-2)는 서류 자동화 계약 쪽에서(sitok_docs.card_no — 같은 카드에서 기간이 겹치는 계약이 여럿이면 시작일 순 -1·-2).

Revision ID: 0054
Revises: 0053
Create Date: 2026-10-19
"""
from __future__ import annotations

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0054"
down_revision: Union[str, None] = "0053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SUB = re.compile(r"^(관급|민간)-0*(\d+)-0*(\d+)$")


def upgrade() -> None:
    op.add_column("sitok_facility", sa.Column("book_order", sa.Integer(), nullable=False, server_default="0"))
    bind = op.get_bind()
    for fid, no in bind.execute(sa.text("SELECT id, mgmt_no FROM sitok_facility WHERE mgmt_no IS NOT NULL")).fetchall():
        m = SUB.match((no or "").strip())
        if m:
            bind.execute(sa.text("UPDATE sitok_facility SET mgmt_no = :no, book_order = :k WHERE id = :id"),
                         {"no": f"{m[1]}-{int(m[2])}", "k": int(m[3]), "id": fid})


def downgrade() -> None:
    bind = op.get_bind()
    for fid, no, k in bind.execute(sa.text("SELECT id, mgmt_no, book_order FROM sitok_facility WHERE book_order > 0")).fetchall():
        bind.execute(sa.text("UPDATE sitok_facility SET mgmt_no = :no WHERE id = :id"), {"no": f"{no}-{k}", "id": fid})
    op.drop_column("sitok_facility", "book_order")
