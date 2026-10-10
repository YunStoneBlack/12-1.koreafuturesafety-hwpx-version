"""시특법 결함(2026-10-10 5단계) — sitok_defect.

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    t = lambda n: sa.Column(n, sa.Text(), nullable=False, server_default="")  # noqa: E731
    op.create_table(
        "sitok_defect",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("sitok_report.id", ondelete="CASCADE"), nullable=False, index=True),
        t("floor"), sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
        t("part"), t("member"), t("dtype"), t("count"), t("width"), t("length"), t("qty"), t("area_ratio"), t("cause"), t("progress"),
        t("mark"), t("check"), t("photo"), sa.Column("prev", sa.JSON(), nullable=True), t("prev_photo"),
        sa.Column("starred", sa.Boolean(), nullable=False, server_default=sa.false()), t("note"), t("checked_by"),
        sa.Column("checked_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("sitok_defect")
