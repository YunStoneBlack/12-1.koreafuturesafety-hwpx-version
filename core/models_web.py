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

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base
from core.stored_path import StoredPath


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
    status: Mapped[str] = mapped_column(Text, default="queued")  # queued|rendering|done|failed|canceled(대기 중 취소, jobs.py)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)
    started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=None)
    finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=None)


class ReportEdit(Base):
    """웹판 전용 — 보고서 내용을 마지막으로 고친 시각. 현장 화면 보고서 목록에서 "PDF가 수정 전 버전"인지 판단하는 데 쓴다
    (마지막 PDF 렌더 작업 시작 시각보다 늦게 고쳤으면 수정 전 버전). 저장 요청이 성공할 때마다 server/api/edit_tracking.py가 갱신.
    Report는 데스크톱(SQLite)과 같이 쓰는 모델이라 칸을 늘리지 않고 따로 둔다. 보고서가 지워지면 DB가 같이 지운다(ON DELETE CASCADE)."""

    __tablename__ = "report_edit"

    report_id: Mapped[int] = mapped_column(ForeignKey("report.id", ondelete="CASCADE"), primary_key=True)
    edited_at: Mapped[datetime.datetime] = mapped_column(DateTime)


class ReportMail(Base):
    """웹판 전용 — 고객사에 보고서 PDF를 메일로 보낸 기록(현장 화면 "📧 고객사 전송", server/api/routers/report_mail.py).
    누가·언제·누구에게 보냈는지 남겨 목록에 "전송됨"을 보여 주고, 다시 보낼 때 "이미 보낸 보고서"라고 알린다.
    보고서가 지워지면 DB가 같이 지운다(ON DELETE CASCADE)."""

    __tablename__ = "report_mail"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("report.id", ondelete="CASCADE"), index=True)
    sent_at: Mapped[datetime.datetime] = mapped_column(DateTime)
    to_addr: Mapped[str] = mapped_column(Text)
    cc_addr: Mapped[str] = mapped_column(Text, default="")
    sent_by: Mapped[str] = mapped_column(Text, default="")  # 보낸 직원 이름(그룹웨어 표시 이름)


class ReportSubmitMark(Base):
    """웹판 전용 — "직접 제출함" 표시(제출 현황 화면). 고객사 전송(ReportMail) 말고 직접 메일·출력물·카톡 등으로 낸 보고서를
    제출 완료로 치기 위해 사람이 누른 기록. 되돌리기 = 행 삭제. 보고서가 지워지면 같이 지워진다(CASCADE).
    제출 완료 판정은 server/api/submission.py 한 곳에서만 한다(사용자가 나중에 기준을 바꿀 예정 — 2026-09-29)."""

    __tablename__ = "report_submit_mark"

    report_id: Mapped[int] = mapped_column(ForeignKey("report.id", ondelete="CASCADE"), primary_key=True)
    marked_at: Mapped[datetime.datetime] = mapped_column(DateTime)
    marked_by: Mapped[str] = mapped_column(Text, default="")


class StaffContact(Base):
    """웹판 전용 — 담당요원 메일(지도 기한 알림 메일 받는 곳). Staff는 데스크톱(SQLite)과 같이 쓰는 모델이라 칸을 늘리지 않고
    따로 둔다(ReportEdit과 같은 이유). 요원이 지워지면 같이 지워진다(CASCADE)."""

    __tablename__ = "staff_contact"

    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id", ondelete="CASCADE"), primary_key=True)
    email: Mapped[str] = mapped_column(Text, default="")


class DeadlineAlert(Base):
    """웹판 전용 — 지도 기한 알림을 보낸 기록(2026-10-01 알림 기능 없앰, 테이블·지난 기록만 남음). 현장·기한·단계(d3/dday/over)·경로(mail, 나중에 sms)마다
    한 번만 보내려고 남긴다 — 같은 (현장, 기한, 단계, 경로)는 두 번 안 보냄. 현장이 지워지면 같이 지워진다(CASCADE)."""

    __tablename__ = "deadline_alert"
    __table_args__ = (UniqueConstraint("site_id", "deadline", "kind", "channel", name="uq_deadline_alert"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("site.id", ondelete="CASCADE"), index=True)
    deadline: Mapped[datetime.date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(Text)  # d3(임박 — 설정 일수 전) | dday | over(초과 첫날)
    channel: Mapped[str] = mapped_column(Text, default="mail")
    sent_at: Mapped[datetime.datetime] = mapped_column(DateTime)
    recipients: Mapped[str] = mapped_column(Text, default="")



class StaffGroupwareLink(Base):
    """웹판 전용 — 담당요원과 그룹웨어 직원정보(employee)를 잇는 줄(2026-09-30). 담당요원 탭이 그룹웨어 `/report-shell/employees`를
    받아 보내면(server/api/routers/staff_groupware.py) 이름·연락처·메일을 그룹웨어 값으로 맞추고, 로그인 아이디(username)로
    "지금 로그인한 사람 = 어느 담당요원"을 알아본다(방문 달력 "나만"). 요원이 지워지면 같이 지워진다(CASCADE)."""

    __tablename__ = "staff_gw_link"
    __table_args__ = (UniqueConstraint("company_id", "gw_employee_id", name="uq_staff_gw_link_employee"),)

    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id", ondelete="CASCADE"), primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"))
    gw_employee_id: Mapped[int] = mapped_column()
    gw_username: Mapped[str] = mapped_column(Text, default="")
    department: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[str] = mapped_column(Text, default="")
    synced_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)


class StaffK2bAccount(Base):
    """웹판 전용 — 담당요원의 K2B 계정(2026-10-01, alembic 0014). 요원 한 명에 하나. K2B는 로그인한 계정 이름이 "점검자"로 고정되므로
    그 회차 담당요원 본인 계정으로 제출한다. 비밀번호는 Fernet 암호문(server/api/k2b_secret.py, 열쇠 = .env.server K2B_SECRET_KEY) —
    화면에 다시 보여 주지 않는다. check_* = [로그인 확인] 결과(ok/mismatch/fail, K2B에서 찾은 이름, 안내, 시각). 요원이 지워지면 같이 지워진다."""

    __tablename__ = "staff_k2b_account"

    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id", ondelete="CASCADE"), primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"))
    k2b_id: Mapped[str] = mapped_column(Text, default="")
    password_enc: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=None)
    updated_by: Mapped[str] = mapped_column(Text, default="")
    check_status: Mapped[str] = mapped_column(Text, default="")
    check_name: Mapped[str] = mapped_column(Text, default="")
    check_message: Mapped[str] = mapped_column(Text, default="")
    checked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=None)


class K2bSubmission(Base):
    """웹판 전용 — K2B 제출 기록·대기열(2026-10-01, alembic 0015). 현장 화면 보고서 줄 [K2B 제출] → queued, 이 PC 작업 프로그램
    (server/worker/k2b_worker.py)이 running → done(K2B에 저장됨, round_no = K2B가 매긴 새 차수) | failed(message·화면).
    options = 창에서 고른 K2B 전용 항목(현재 작업공종·비계·불량사업장·대형사고 위험작업). screenshot = 저장 뒤(또는 실패 때) K2B 화면."""

    __tablename__ = "k2b_submission"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("report.id", ondelete="CASCADE"), index=True)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id", ondelete="SET NULL"), default=None)
    status: Mapped[str] = mapped_column(Text, default="queued")
    options: Mapped[dict | None] = mapped_column(JSON, default=None)
    round_no: Mapped[int | None] = mapped_column(default=None)
    message: Mapped[str] = mapped_column(Text, default="")
    screenshot: Mapped[str] = mapped_column(StoredPath, default="")
    log: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=datetime.datetime.now)
    started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=None)
    finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=None)


class VisitPlan(Base):
    """웹판 전용 — 방문 달력의 "방문 예정"(2026-09-30). 날짜·현장·요원·메모. 그 현장·그 날짜 보고서가 생기면 달력에선 "다녀온 방문"으로
    바뀌어 보이고(행은 그대로 둠), 날짜가 지났는데 보고서가 없으면 "지난 예정"(server/api/routers/calendar.py). 현장이 지워지면 같이
    지워지고, 요원이 지워지면 요원만 빈 값이 된다."""

    __tablename__ = "visit_plan"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("site.id", ondelete="CASCADE"), index=True)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id", ondelete="SET NULL"), default=None)  # 실제 출장자
    # 보고서 담당자(2026-10-02, alembic 0016) — 출장은 다른 사람이 가도 보고서에 이름이 들어갈 사람(한 사람 하루 4곳, server/api/report_staff.py)
    report_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id", ondelete="SET NULL"), default=None)
    plan_date: Mapped[datetime.date] = mapped_column(Date, index=True)
    memo: Mapped[str] = mapped_column(Text, default="")
    # auto = 자동 배치가 넣음(다시 배치하면 바뀜), manual = 사람이 넣거나 옮김(📌 고정 — 자동 배치가 안 건드리고 기준점으로 씀). alembic 0010
    source: Mapped[str] = mapped_column(Text, default="manual", server_default="manual")
    created_by: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)


class SiteContact(Base):
    """웹판 전용 — 현장의 발주처·감리단(이름·기관명 + 메일, 메일은 ", "로 여러 개)과 지도 방문 주소(2026-09-30). 고객사 전송 창에서 현장책임자와 함께
    체크 항목으로 나온다. 표지에 안 들어가므로 바꿔도 PDF는 그대로. retired_emails: 현장책임자·발주처·감리단에서 빠진 옛 주소 —
    "지난번 받는 사람" 자동 채움에서 뺀다(주소가 바뀌었는데 옛 주소가 계속 채워지지 않게). 현장이 지워지면 같이 지워진다(CASCADE)."""

    __tablename__ = "site_contact"

    site_id: Mapped[int] = mapped_column(ForeignKey("site.id", ondelete="CASCADE"), primary_key=True)
    owner_name: Mapped[str] = mapped_column(Text, default="")
    owner_email: Mapped[str] = mapped_column(Text, default="")
    supervisor_name: Mapped[str] = mapped_column(Text, default="")
    supervisor_email: Mapped[str] = mapped_column(Text, default="")
    retired_emails: Mapped[str] = mapped_column(Text, default="")
    # 지도 방문 주소(2026-09-30) — 군부대처럼 서류상 주소와 실제로 찾아가는 주소가 다를 때만 채움. 비어 있으면 현장 주소.
    # [📍 지도] 버튼이 이 주소를 네이버 지도로 연다. 보고서(PDF)엔 안 나감.
    visit_address: Mapped[str] = mapped_column(Text, default="")
    # 첫 지도 회차(2026-10-01, alembic 0013) — 이 시스템 전에 다녀온 회차가 있으면(30회 중 1~7회) 8. 보고서가 없을 때 "다녀온 횟수" = 이 값 - 1,
    # 첫 보고서 회차 = 이 값(server/api/site_pace_out.done_counts, repo.create_report). 보고서가 생기면 최근 보고서 회차가 우선(둘 중 큰 것).
    first_visit_no: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class SiteGeo(Base):
    """웹판 전용 — 현장 좌표(카카오 로컬 API, 2026-10-01, alembic 0011). 자동 배치·일정 변경의 거리 기준 묶기(server/api/geocode.py).
    address = 좌표를 찾을 때 쓴 주소(지도 방문 주소, 없으면 현장 주소 — 바뀌면 다시 찾음), precise = 시·군 중심보다 구체적으로 찾았는지."""

    __tablename__ = "site_geo"

    site_id: Mapped[int] = mapped_column(ForeignKey("site.id", ondelete="CASCADE"), primary_key=True)
    address: Mapped[str] = mapped_column(Text, default="")
    lat: Mapped[float | None] = mapped_column(Float, default=None)
    lng: Mapped[float | None] = mapped_column(Float, default=None)
    precise: Mapped[bool] = mapped_column(Boolean, default=False)
    found: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=None)


class SiteDistance(Base):
    """웹판 전용 — 현장 사이 도로 거리(카카오모빌리티 길찾기, 2026-10-01, alembic 0012). site_a < site_b.
    coords = 물었을 때 두 좌표("lat,lng|lat,lng") — 좌표가 바뀌면 다시 묻는다. road_km가 비면 길찾기 실패(직선거리로 대신)."""

    __tablename__ = "site_distance"

    site_a: Mapped[int] = mapped_column(ForeignKey("site.id", ondelete="CASCADE"), primary_key=True)
    site_b: Mapped[int] = mapped_column(ForeignKey("site.id", ondelete="CASCADE"), primary_key=True)
    coords: Mapped[str] = mapped_column(Text, default="")
    road_km: Mapped[float | None] = mapped_column(Float, default=None)
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=None)


class ServiceContract(Base):
    """웹판 전용 — 현장의 용역 계약(발주처와 맺은 기술지도 용역, 2026-10-06, alembic 0017). 착수계·완수계 서류(server/contract_docs)에 들어가는 값.
    현장 정보의 공사금액·공사기간(시공사 공사)과는 다른 것 — 용역금액·용역 착수일·완수일. 계약서 PDF를 올리면 읽어서 채우고(사람이 고칠 수 있음),
    착수계 때 한 번 넣으면 완수계 때 다시 쓴다. 정산금액·실제준공일이 비면 계약금액·준공기한(사용자 10/6: 보통 그대로, 다를 때만 고침).
    agent_id·participant_ids = 지난번 착수계에서 고른 기술자(다음에 그대로 골라 둠). 현장이 지워지면 같이 지워진다."""

    __tablename__ = "service_contract"

    site_id: Mapped[int] = mapped_column(ForeignKey("site.id", ondelete="CASCADE"), primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"))
    client: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(Text, default="")
    contract_no: Mapped[str] = mapped_column(Text, default="")
    amount: Mapped[int | None] = mapped_column(BigInteger, default=None)
    contract_date: Mapped[datetime.date | None] = mapped_column(Date, default=None)
    start_date: Mapped[datetime.date | None] = mapped_column(Date, default=None)
    end_date: Mapped[datetime.date | None] = mapped_column(Date, default=None)
    settle_amount: Mapped[int | None] = mapped_column(BigInteger, default=None)
    actual_end_date: Mapped[datetime.date | None] = mapped_column(Date, default=None)
    contract_pdf: Mapped[str] = mapped_column(StoredPath, default="")
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("tech_person.id", ondelete="SET NULL"), default=None)
    participant_ids: Mapped[list | None] = mapped_column(JSON, default=None)
    start_made_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=None)
    done_made_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=None)
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=None)
    updated_by: Mapped[str] = mapped_column(Text, default="")


class TechPerson(Base):
    """웹판 전용 — 착수계 기술자 명단(2026-10-06, alembic 0017). 현장대리인(책임기술자 1명)·참여기술자(0~N명)로 고르는 사람.
    담당요원(staff)과 따로 둔 이유: 현장대리인이 담당요원이 아닐 수 있음(예: 권만중). 자격증·교육수료증·경력증명서 그림은 SubmitDoc(person_id)."""

    __tablename__ = "tech_person"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    name: Mapped[str] = mapped_column(Text)
    address: Mapped[str] = mapped_column(Text, default="")
    birth_date: Mapped[datetime.date | None] = mapped_column(Date, default=None)
    position: Mapped[str] = mapped_column(Text, default="")       # 직책(재직증명서)
    join_date: Mapped[datetime.date | None] = mapped_column(Date, default=None)
    qualification: Mapped[str] = mapped_column(Text, default="")  # 기술자격(여러 개면 줄바꿈)
    grade: Mapped[str] = mapped_column(Text, default="")          # 기술등급(특급·고급…)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=None)


class SubmitDoc(Base):
    """웹판 전용 — 착수계·완수계에 붙는 서류 그림(2026-10-06, alembic 0017). person_id가 비면 회사 서류(완납증명서 4·사업자등록증·통장),
    있으면 그 기술자의 서류(자격증·교육수료증·경력증명서). 종류(kind)는 server/contract_docs/build.py의 COMPANY_DOCS·PERSON_DOCS.
    valid_until = 유효기간 — 지나면 서류 만들 때 경고(사용자 10/6: 새로 발급받아 바꿔 올리게). 완납증명서는 비우면 발급일 + 30일.
    PDF로 올려도 첫 장을 그림으로 바꿔 둔다(file = 저장소 _서류 폴더의 JPG)."""

    __tablename__ = "submit_doc"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("tech_person.id", ondelete="CASCADE"), default=None, index=True)
    kind: Mapped[str] = mapped_column(Text)
    file: Mapped[str] = mapped_column(StoredPath, default="")
    issued_on: Mapped[datetime.date | None] = mapped_column(Date, default=None)
    valid_until: Mapped[datetime.date | None] = mapped_column(Date, default=None)
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=None)
    updated_by: Mapped[str] = mapped_column(Text, default="")
