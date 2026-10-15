"""시특법 FMS 제출(2026-10-15 — 시특법 7단계) — 제출 작업 표 + 시설물 관리주체 FMS 계정 + 회차 FMS 상태.

- fms_submission: 회차 화면 [FMS …] → queued, 작업 프로그램(server/worker/fms_worker.py)이 running → done | failed.
  stage = practice(채워 보기만, 저장 안 함) | contract(점검진단계약 등록 → 승인요청 → 관리주체 승인) | result(실적보고 + e-보고서 → 승인요청 → 관리주체 승인).
  report_ids = 같이 내는 회차들(묶음 동), project_no = FMS 계약 번호(E02210…), result = 단계별 결과·FMS에서 읽은 값(대표자 등), shots = 화면.
- sitok_facility.fms_owner_id·fms_owner_pw: 관리주체 FMS 계정(형 10/15 "시설물 카드에 입력") — 비밀번호는 암호화(K2B와 같은 열쇠).
  계정이 없으면 승인요청까지만(관리주체가 직접 승인).
- sitok_report.fms: 이 회차 FMS 상태 {project_no, contract: {at, by, status}, result: {…}}.
- 회사 FMS 계정은 app_setting(fms_id·fms_pw) — 표 변경 없음.

Revision ID: 0046
Revises: 0045
Create Date: 2026-10-15
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0046"
down_revision: Union[str, None] = "0045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fms_submission",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id"), nullable=False, index=True),
        sa.Column("report_ids", sa.JSON(), nullable=True),
        sa.Column("stage", sa.Text(), nullable=False, server_default="practice"),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("project_no", sa.Text(), nullable=False, server_default=""),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("log", sa.Text(), nullable=False, server_default=""),
        sa.Column("shots", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.add_column("sitok_facility", sa.Column("fms_owner_id", sa.Text(), nullable=False, server_default=""))
    op.add_column("sitok_facility", sa.Column("fms_owner_pw", sa.Text(), nullable=False, server_default=""))
    op.add_column("sitok_report", sa.Column("fms", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sitok_report", "fms")
    op.drop_column("sitok_facility", "fms_owner_pw")
    op.drop_column("sitok_facility", "fms_owner_id")
    op.drop_table("fms_submission")
