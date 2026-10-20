"""산안법 서류 자동화 ↔ 보고서 자동화 연동(2026-10-20 형 문서 "산안법 서류자동화 – 보고서 자동화 연동") —
contract_site = 용역 계약 하나에 현장 여럿(시특법처럼, 현장 하나는 계약 하나 — site_id가 키). 전엔 service_contract.site_id(현장 하나)뿐이었고
연결된 계약이 0건이라, 같은 관리번호(계약 "26-3" ↔ 현장 "26-3"·"26-3-1"…)끼리 지금 자동으로 이음. service_contract.changes = 계약변경 기록
(공기연장 등 — [{no, at, by, before, after, files}], server/api/routers/contracts.py). service_contract.site_id는 남겨 두지만 안 씀.

Revision ID: 0057
Revises: 0056
Create Date: 2026-10-20
"""
from __future__ import annotations

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0057"
down_revision: Union[str, None] = "0056"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NUM = re.compile(r"^(\d{2}|\d{4})-0*(\d+)$")


def _short(no: str | None) -> str:  # server/api/site_label.short_mgmt와 같은 규칙
    m = (no or "").strip()
    f = _NUM.match(m)
    return f"{f.group(1)[-2:]}-{f.group(2)}" if f else m


def upgrade() -> None:
    op.create_table(
        "contract_site",
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("site.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("service_contract.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.add_column("service_contract", sa.Column("changes", sa.JSON(), nullable=True))
    bind = op.get_bind()
    linked: set[int] = set()
    for cid, sid in bind.execute(sa.text("SELECT id, site_id FROM service_contract WHERE site_id IS NOT NULL")):
        bind.execute(sa.text("INSERT INTO contract_site (site_id, contract_id, created_at) VALUES (:s, :c, now())"), {"s": sid, "c": cid})
        linked.add(sid)
    contracts = list(bind.execute(sa.text("SELECT id, company_id, management_no FROM service_contract")))
    sites = list(bind.execute(sa.text("SELECT id, company_id, management_no FROM site WHERE company_id IS NOT NULL")))
    for cid, company, no in contracts:
        c = _short(no)
        same = [x for x in contracts if x[1] == company and _short(x[2]) == c]
        if not c or len(same) > 1:  # 번호가 겹치는 계약이 둘이면 사람이
            continue
        for sid, scompany, sno in sites:
            s = _short(sno)
            if scompany == company and sid not in linked and (s == c or re.fullmatch(re.escape(c) + r"-\d+", s)):
                bind.execute(sa.text("INSERT INTO contract_site (site_id, contract_id, created_at) VALUES (:s, :c, now())"), {"s": sid, "c": cid})
                linked.add(sid)


def downgrade() -> None:
    op.drop_column("service_contract", "changes")
    op.drop_table("contract_site")
