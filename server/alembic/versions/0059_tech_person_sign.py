"""기술자 서명 그림(2026-10-21 민재형 "설정에 기술자 서명파일 등록해서 연동") — tech_person.sign_path(StoredPath). 시특법 설정 기술자 칸에서 올리고
옹벽 보고서 참여기술자 명단 "서명" 칸에 들어감(server/sitok/wall_build.fill_front).

Revision ID: 0059
Revises: 0058
Create Date: 2026-10-21
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0059"
down_revision: Union[str, None] = "0058"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tech_person", sa.Column("sign_path", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("tech_person", "sign_path")
