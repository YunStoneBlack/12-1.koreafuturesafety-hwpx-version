"""Sub-phase 33: 웹판 최초 스키마.

이 리비전이 Postgres DB에 처음 적용될 때는 테이블이 하나도 없는 새 DB이므로, 기존
20여 개 테이블(현장/보고서/사진/지적사항 등, 데스크톱 exe와 완전히 동일)을 여기 일일이
다시 옮겨적는 대신 `Base.metadata.create_all()`을 그대로 호출해서 core/models_db.py의
SQLAlchemy 모델 정의를 단일 진실 소스로 삼는다 — 여기에는 이번에 새로 추가된
company/user/user_session/report_job 테이블과, staff/site/app_setting에 새로 붙은
company_id 컬럼도 전부 포함되어 있다(모델 정의 자체가 이미 최신 상태이기 때문).

이후 스키마 변경부터는 이 방식이 아니라 진짜 alembic revision(개별 op.add_column 등)으로
관리한다 — 이번 리비전은 "지금부터 alembic으로 관리를 시작한다"는 기준점이다.

Revision ID: 0001
Revises:
Create Date: 2026-09-28
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from core import models_db  # noqa: F401 -- 전체 모델을 메타데이터에 등록하기 위한 임포트
    from core import models_web  # noqa: F401
    from core.db import Base

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    from core import models_db  # noqa: F401
    from core import models_web  # noqa: F401
    from core.db import Base

    Base.metadata.drop_all(bind=op.get_bind())
