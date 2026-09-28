"""웹판(server/, Sub-phase 33~) 전용 SQLAlchemy 모델.

core/models_db.py(데스크톱 exe 시절부터 있던 전체 스키마)와 분리해둔 이유: models_db.py가
600줄을 넘어서기도 했고, 이 파일의 모델들은 데스크톱 exe 쪽에서는 아예 안 쓰이는(테이블은
만들어지지만 항상 비어있는) 순수 웹판 전용 개념이라 — 회사(테넌트), 로그인 계정, 로그인
세션, 비동기 PDF 생성 작업 큐. Staff/Site/Report 같은 기존 핵심 엔티티는 데스크톱과 계속
공유하므로 그대로 models_db.py에 남아있다.

`core/db.py::init_db()`와 `server/alembic/env.py`가 이 모듈도 같이 import해서 테이블
메타데이터에 등록한다 — 여기 새 모델을 추가하면 그 두 곳에서 자동으로 잡힌다."""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base


class Company(Base):
    """웹판의 고객사(테넌트) 단위. 데스크톱 exe는 고객사가 1곳뿐이라 이 테이블을 안 쓰고
    그냥 SQLite 파일 하나 = 그 회사 전부였는데, 웹판은 여러 회사가 같은 DB를 같이 쓰니
    Staff/Site에 company_id를 붙여서 회사별로 데이터를 분리한다. 그 아래 Report와 그
    자식 테이블들(사진/지적사항/공정 등)은 Site를 거쳐 간접적으로 격리된다
    (Report.site_id -> Site.company_id) — 지금 규모(회사당 5~50명)에서는 매 쿼리마다
    Site와 join하는 정도로 충분하고, 성능 문제가 실제로 확인되면 그때 company_id를
    Report에도 직접 붙이는 걸 검토한다."""

    __tablename__ = "company"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text, unique=True)  # 나중에 서브도메인으로도 씀
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)


class User(Base):
    """웹판 로그인 계정 — 고객사 직원 1명. Sub-phase 33 1차 범위에서는 역할(role) 구분 없이
    같은 회사 안에서는 전부 동등한 권한이다(형 회사 5명 전부 같은 데이터를 보고 고침)."""

    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"))
    email: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)

    company: Mapped[Company] = relationship()


class UserSession(Base):
    """웹판 로그인 세션. JWT 대신 이 테이블을 쓰는 이유: 5명짜리 파일럿에서는 "직원 한 명이
    퇴사해서 당장 접속을 끊어야 한다" 같은 상황을 세션 행 하나 지우는 것만으로 즉시 처리할
    수 있어야 한다(JWT는 만료 전까지 서버가 강제로 무효화할 방법이 없음). `id`(세션 토큰
    본체, 추측 불가능한 랜덤 문자열)를 서명된 쿠키에 담아 내려준다."""

    __tablename__ = "user_session"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime)

    user: Mapped[User] = relationship()


class ReportJob(Base):
    """웹판의 비동기 PDF 생성 작업 큐. 한글 COM 자동화는 실측 8~15초 걸리는 느린 작업이라
    웹 요청 안에서 바로 처리하면 안 되고, API 프로세스가 이 테이블에 "queued" 행을 하나
    넣고 즉시 응답한 뒤, 별도 워커 프로세스(server/worker/render_worker.py)가 이 테이블을
    폴링해서 실제 렌더링을 수행한다.

    실패해도 절대 다른 서식으로 조용히 대체하지 않고 error_message에 그대로 남긴다 —
    core/report_builder.py의 build_report()가 HwpNotAvailableError(한글 자체가 없을 때)만
    구분해서 처리하는 것과 같은 이유: 자동화가 일시적으로 실패한 걸 사용자가 못 알아채는
    사이에 부실한 서식으로 조용히 바뀌는 사고를 막기 위함이다."""

    __tablename__ = "report_job"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("report.id"))
    status: Mapped[str] = mapped_column(Text, default="queued")  # queued|rendering|done|failed
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)
    started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=None)
    finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=None)
