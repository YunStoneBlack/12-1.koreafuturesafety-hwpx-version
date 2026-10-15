"""시특법 제출 현황(2026-10-15 민재형 문서번호 일치화 문서 — 보고서 제출현황·서류 제출현황, 상·하반기로).

- sitok_report.submit: 회차 보고서 제출 표시 {mail: {at, by}(발주처 이메일 제출), fms: {at, by} | {na: true, by}(FMS 처리 — 직접 처리함·해당없음,
  FMS 자동 제출 기록은 sitok_report.fms), print: {at, by}(보고서 합본 출력), parcel: {at, by}(보고서 택배)}. 묶인 동은 같이 표시.
- sitok_doc_contract.marks: 서류 제출 표시 {start: {at, by}(착수계 직접 제출함 — 프로그램 쓰기 전 낸 것 등), done: {at, by}(완료계),
  invoice: {"2026-하반기": "2026-12-20", …}(계산서 발행일 — 민간은 반기마다, 관급은 계약 하나 "all")}.

Revision ID: 0048
Revises: 0047
Create Date: 2026-10-15
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0048"
down_revision: Union[str, None] = "0047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_report", sa.Column("submit", sa.JSON(), nullable=True))
    op.add_column("sitok_doc_contract", sa.Column("marks", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sitok_doc_contract", "marks")
    op.drop_column("sitok_report", "submit")
