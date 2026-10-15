"""시특법 문서번호 일치화(2026-10-15 민재형 문서 "시특법 서류자동화와 보고서 자동화 문서번호 일치화") — 시설물 번호 관급-N·민간-N + 뱃지.

- sitok_facility.sector: 민간 / 관급(시설물 카드 단위 — 드롭박스 폴더도 관급·민간으로만 나눠 번호). 지금까지는 계약에만 있었음.
- sitok_facility.badge_field: 건축 / 토목 / 건축·토목(민간·관급 공통), badge_kind: 학교 / 일반 / 내진(관급만) — 목록에서 뱃지별 개수·거르기.
- sitok_facility.mgmt_no: "26-4"(연도-순번) → "민간-3"·"관급-1"(구분별 순번, 연도 없음). 지금 번호 차례(연도·순번)대로 다시 매김, 묶인 동은 같은 번호.
- sitok_doc_contract.half_tag: 시설물 카드 안 계약의 반기 표시(상반기 / 하반기 / 상·하반기 / 해당없음) — 비우면 용역 기간·회차로 자동(내진성능평가 = 해당없음).

Revision ID: 0047
Revises: 0046
Create Date: 2026-10-15
"""
from __future__ import annotations

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0047"
down_revision: Union[str, None] = "0046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _old_key(no: str, fid: int) -> tuple:
    m = re.match(r"^(\d{2}|\d{4})-0*(\d+)$", (no or "").strip())
    return (0, int(m[1][-2:]), int(m[2]), fid) if m else (1, 0, 0, fid)


def upgrade() -> None:
    op.add_column("sitok_facility", sa.Column("sector", sa.Text(), nullable=False, server_default="민간"))
    op.add_column("sitok_facility", sa.Column("badge_field", sa.Text(), nullable=False, server_default="건축"))
    op.add_column("sitok_facility", sa.Column("badge_kind", sa.Text(), nullable=False, server_default=""))
    op.add_column("sitok_doc_contract", sa.Column("half_tag", sa.Text(), nullable=False, server_default=""))

    bind = op.get_bind()
    facs = bind.execute(sa.text("SELECT id, company_id, mgmt_no, group_id, template FROM sitok_facility")).fetchall()
    cons = bind.execute(sa.text("SELECT id, facility_id, sector, field FROM sitok_contract ORDER BY id")).fetchall()
    docs = bind.execute(sa.text("SELECT id, facility_id, sector FROM sitok_doc_contract WHERE facility_id IS NOT NULL ORDER BY id")).fetchall()
    con_of = {c.facility_id: c for c in cons}  # 마지막 계약
    doc_of = {d.facility_id: d for d in docs}
    lead_of: dict[int, int] = {}  # 묶음 → 계약 있는 동(대표)
    for f in facs:
        if f.group_id and f.id in con_of:
            lead_of.setdefault(f.group_id, f.id)
    info = {}
    for f in facs:
        c = con_of.get(f.id) or (con_of.get(lead_of.get(f.group_id)) if f.group_id else None)
        d = doc_of.get(f.id)
        sector = (c.sector if c else d.sector if d else "민간") or "민간"
        field = "건축" if not c or (c.field or "건축") == "건축" else "토목"
        kind = ("학교" if f.template == "3종학교" else "일반") if sector == "관급" else ""
        info[f.id] = (sector, field, kind)
    # 번호: 회사·구분마다 지금 번호 차례대로 1부터, 묶인 동은 같은 번호(묶음 첫 동 차례)
    by_company: dict[int, list] = {}
    for f in facs:
        by_company.setdefault(f.company_id, []).append(f)
    new_no: dict[int, str] = {}
    for rows in by_company.values():
        counters: dict[str, int] = {}
        group_no: dict[int, str] = {}
        for f in sorted(rows, key=lambda r: _old_key(r.mgmt_no, r.id)):
            sector = info[f.id][0]
            if f.group_id and f.group_id in group_no:
                new_no[f.id] = group_no[f.group_id]
                continue
            counters[sector] = counters.get(sector, 0) + 1
            new_no[f.id] = f"{sector}-{counters[sector]}"
            if f.group_id:
                group_no[f.group_id] = new_no[f.id]
    for f in facs:
        sector, field, kind = info[f.id]
        bind.execute(sa.text("UPDATE sitok_facility SET sector = :s, badge_field = :bf, badge_kind = :bk, mgmt_no = :no WHERE id = :id"),
                     {"s": sector, "bf": field, "bk": kind, "no": new_no[f.id], "id": f.id})


def downgrade() -> None:
    op.drop_column("sitok_doc_contract", "half_tag")
    op.drop_column("sitok_facility", "badge_kind")
    op.drop_column("sitok_facility", "badge_field")
    op.drop_column("sitok_facility", "sector")
