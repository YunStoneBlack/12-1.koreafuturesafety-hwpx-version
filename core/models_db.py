"""SQLAlchemy ORM 스키마.

이번 단계(Sub-phase 1)에서 실제로 화면에서 쓰는 건 Staff/Site 뿐이지만,
보고서 작성 마법사(Sub-phase 2~3)에서 바로 이어 쓸 수 있도록 전체 스키마를
한 번에 정의해둔다.
"""

from __future__ import annotations

import datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base


class Staff(Base):
    """담당요원."""

    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    phone: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(default=True)

    # Sub-phase 8: 담당요원 서명 — 요원별 1회 등록, 모든 보고서에 재사용.
    signature_path: Mapped[str] = mapped_column(Text, default="")
    signature_source: Mapped[str] = mapped_column(Text, default="")  # "drawn" | "uploaded"


class Site(Base):
    """현장. '신규현장추가' 화면 필드와 1:1 매핑."""

    __tablename__ = "site"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 현장
    name: Mapped[str] = mapped_column(Text)
    address: Mapped[str] = mapped_column(Text, default="")
    period_start: Mapped[datetime.date | None] = mapped_column(Date, default=None)
    period_end: Mapped[datetime.date | None] = mapped_column(Date, default=None)
    amount: Mapped[int | None] = mapped_column(default=None)
    site_mgmt_no: Mapped[str] = mapped_column(Text, default="")
    biz_start_no: Mapped[str] = mapped_column(Text, default="")
    manager_name: Mapped[str] = mapped_column(Text, default="")
    manager_phone: Mapped[str] = mapped_column(Text, default="")
    manager_email: Mapped[str] = mapped_column(Text, default="")

    # 본사(시공사)
    hq_company: Mapped[str] = mapped_column(Text, default="")
    corp_reg_no: Mapped[str] = mapped_column(Text, default="")
    biz_reg_no: Mapped[str] = mapped_column(Text, default="")
    license_no: Mapped[str] = mapped_column(Text, default="")
    hq_phone: Mapped[str] = mapped_column(Text, default="")
    hq_address: Mapped[str] = mapped_column(Text, default="")

    # 기타
    total_guidance_count: Mapped[int | None] = mapped_column(default=None)
    assigned_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), default=None)
    status: Mapped[str] = mapped_column(Text, default="진행중")  # 진행중 / 완료 / 보류

    # 12대 기인물 체크 상태(factor_no 리스트)와 진행공정 기본값은 회차 생성 시 그대로 승계된다.
    hazard_factor_checks: Mapped[list] = mapped_column(JSON, default=list)

    # Sub-phase 8: 관리번호 — 현장 단위로 고정, 1회차 저장 시 채워지고 이후 회차는 그대로 재사용.
    management_no: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)

    assigned_staff: Mapped[Staff | None] = relationship()
    reports: Mapped[list["Report"]] = relationship(back_populates="site", order_by="Report.visit_no")
    process_defaults: Mapped[list["SiteProcessDefault"]] = relationship(
        back_populates="site", order_by="SiteProcessDefault.slot"
    )


class SiteProcessDefault(Base):
    """진행공정(9번 섹션) 기본값 — 현장에 저장되어 다음 회차에 자동 승계."""

    __tablename__ = "site_process_default"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("site.id"))
    slot: Mapped[int] = mapped_column()  # 1~4
    process_name: Mapped[str] = mapped_column(Text, default="")
    hazard_text: Mapped[str] = mapped_column(Text, default="")
    prevention_text: Mapped[str] = mapped_column(Text, default="")
    risk_level: Mapped[str] = mapped_column(Text, default="")  # 상/중/하

    site: Mapped[Site] = relationship(back_populates="process_defaults")


class Report(Base):
    """회차별 보고서."""

    __tablename__ = "report"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("site.id"))
    visit_no: Mapped[int] = mapped_column()  # 회차 (현장 내 자동 증가)
    assigned_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), default=None)
    guidance_date: Mapped[datetime.date | None] = mapped_column(Date, default=None)
    prev_guidance_date: Mapped[datetime.date | None] = mapped_column(Date, default=None)
    progress_rate: Mapped[int | None] = mapped_column(default=None)
    notification_method: Mapped[str] = mapped_column(Text, default="")  # 직접전달/등기우편/전자우편/모바일/기타
    prev_guidance_implemented: Mapped[bool | None] = mapped_column(default=None)
    special_note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(Text, default="draft")  # draft / final

    pdf_path: Mapped[str] = mapped_column(Text, default="")
    docx_path: Mapped[str] = mapped_column(Text, default="")
    hwpx_path: Mapped[str] = mapped_column(Text, default="")  # 예전 DOCX→HWPX 변환 파이프라인용(미사용)
    hwp_path: Mapped[str] = mapped_column(Text, default="")  # Sub-phase 8: 신규 템플릿 기반 .hwp 산출물

    # Sub-phase 8: 통보방법 성명/서명 — 회차마다 통보 대상자가 다를 수 있어 Report에 둔다.
    notify_signee_name: Mapped[str] = mapped_column(Text, default="")
    notify_signature_path: Mapped[str] = mapped_column(Text, default="")
    notify_signature_source: Mapped[str] = mapped_column(Text, default="")  # "drawn" | "uploaded"

    # 표3 "기타 특이사항" 행 — 공사기간 편중/사진촬영 불가/기타(자유 텍스트)/재해발생현황(유·무 + 내용)
    misc_overwork: Mapped[bool] = mapped_column(default=False)
    misc_no_photo: Mapped[bool] = mapped_column(default=False)
    misc_other: Mapped[bool] = mapped_column(default=False)
    misc_other_text: Mapped[str] = mapped_column(Text, default="")
    accident_status: Mapped[str] = mapped_column(Text, default="")  # "" | "유" | "무"
    accident_content: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now
    )

    site: Mapped[Site] = relationship(back_populates="reports")
    assigned_staff: Mapped[Staff | None] = relationship()
    overview_photos: Mapped[list["OverviewPhoto"]] = relationship(
        back_populates="report", order_by="OverviewPhoto.slot", cascade="all, delete-orphan"
    )
    safety_education: Mapped["SafetyEducation | None"] = relationship(
        back_populates="report", uselist=False, cascade="all, delete-orphan"
    )
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="report", order_by="Finding.slot", cascade="all, delete-orphan"
    )
    previous_findings: Mapped[list["PreviousFinding"]] = relationship(
        back_populates="report", order_by="PreviousFinding.slot", cascade="all, delete-orphan"
    )
    measurements: Mapped[list["Measurement"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )
    provided_materials: Mapped[list["ProvidedMaterial"]] = relationship(
        back_populates="report", order_by="ProvidedMaterial.slot", cascade="all, delete-orphan"
    )
    process_entries: Mapped[list["ProcessHazardEntry"]] = relationship(
        back_populates="report", order_by="ProcessHazardEntry.slot", cascade="all, delete-orphan"
    )
    current_process_photos: Mapped[list["CurrentProcessPhoto"]] = relationship(
        back_populates="report", order_by="CurrentProcessPhoto.slot", cascade="all, delete-orphan"
    )
    current_process_entries: Mapped[list["CurrentProcessEntry"]] = relationship(
        back_populates="report", order_by="CurrentProcessEntry.slot", cascade="all, delete-orphan"
    )
    hazard_factor_checks: Mapped[list] = mapped_column(JSON, default=list)

    # Sub-phase 7 (실제 표준 서식 9섹션 개편)에서 추가된 필드.
    major_hazard_work_checks: Mapped[list] = mapped_column(JSON, default=list)  # 4번 섹션, 체크된 인덱스 목록
    # 아래 3개는 core.constants의 MACHINERY_EQUIPMENT_ITEMS/HAND_TOOL_ITEMS/HAZMAT_ITEMS와
    # 같은 순서로 병렬 저장되는 [{"checked": bool, "note": str}, ...] — 항목마다 새 테이블을
    # 만들기엔 과해서 hazard_factor_checks와 같은 JSON 방식을 그대로 따른다.
    machinery_checks: Mapped[list] = mapped_column(JSON, default=list)
    hand_tool_checks: Mapped[list] = mapped_column(JSON, default=list)
    hazmat_checks: Mapped[list] = mapped_column(JSON, default=list)
    current_process_name: Mapped[str] = mapped_column(Text, default="")  # 6번 섹션 상단 공정명

    # "해당사항없음"은 화면상 항목 단위가 아니라 섹션 단위 토글이라 Report에 둔다.
    overview_na: Mapped[bool] = mapped_column(default=False)
    findings_na: Mapped[bool] = mapped_column(default=False)
    previous_findings_na: Mapped[bool] = mapped_column(default=False)
    measurements_na: Mapped[bool] = mapped_column(default=False)
    materials_na: Mapped[bool] = mapped_column(default=False)
    hazard_factors_na: Mapped[bool] = mapped_column(default=False)
    process_na: Mapped[bool] = mapped_column(default=False)
    major_hazard_na: Mapped[bool] = mapped_column(default=False)
    equipment_checks_na: Mapped[bool] = mapped_column(default=False)
    current_process_na: Mapped[bool] = mapped_column(default=False)


class OverviewPhoto(Base):
    """1. 전경사진."""

    __tablename__ = "overview_photo"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("report.id"))
    slot: Mapped[int] = mapped_column()  # 1~2
    photo_path: Mapped[str] = mapped_column(Text, default="")

    report: Mapped[Report] = relationship(back_populates="overview_photos")


class SafetyEducation(Base):
    """2. 안전교육."""

    __tablename__ = "safety_education"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("report.id"), unique=True)
    photo_path: Mapped[str] = mapped_column(Text, default="")
    attendee_count: Mapped[int | None] = mapped_column(default=None)
    na_flag: Mapped[bool] = mapped_column(default=False)

    # Sub-phase 8 (표15 TBM 항목 대응)
    location: Mapped[str] = mapped_column(Text, default="")  # 교육장소
    content: Mapped[str] = mapped_column(Text, default="")  # 교육내용
    material: Mapped[str] = mapped_column(Text, default="")  # 교육자료

    report: Mapped[Report] = relationship(back_populates="safety_education")


class Finding(Base):
    """3. 지적사항 (최대 4건)."""

    __tablename__ = "finding"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("report.id"))
    slot: Mapped[int] = mapped_column()  # 1~4
    photo_path: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")  # 사용자가 적는 간단 설명(AI 입력용)
    title: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    law_citation: Mapped[str] = mapped_column(Text, default="")
    likelihood: Mapped[int | None] = mapped_column(default=None)  # 가능성 1~3
    severity: Mapped[int | None] = mapped_column(default=None)  # 중대성 1~3
    action_status: Mapped[str] = mapped_column(Text, default="추후확인")  # "추후확인" | "즉시이행"

    report: Mapped[Report] = relationship(back_populates="findings")

    @property
    def risk_score(self) -> int | None:
        if self.likelihood is None or self.severity is None:
            return None
        return self.likelihood * self.severity


class PreviousFinding(Base):
    """5. 이전지적사항 (최대 4건) — 직전 회차 지적사항 이월/후속조치 확인."""

    __tablename__ = "previous_finding"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("report.id"))
    slot: Mapped[int] = mapped_column()  # 1~4
    photo_path: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    action_result: Mapped[str] = mapped_column(Text, default="조치완료")
    result_status: Mapped[str] = mapped_column(Text, default="")  # ""(미선택)|"확인불가"|"보완필요"|"이행완료"
    # "이행완료" 체크 시 업로드하는 조치 완료 증빙 사진 — 원본 지적사항 사진(photo_path/
    # display_fields())과 별개다.
    completion_photo_path: Mapped[str] = mapped_column(Text, default="")
    risk_level: Mapped[str] = mapped_column(Text, default="")  # 상/중/하 (Sub-phase 8, 표4 대응)
    # 직전 회차 지적사항에서 이월된 경우 그 원본 Finding을 가리킨다 — 원본이 나중에 수정되면
    # display_fields()가 그 최신 내용을 실시간으로 반영한다. 수기로 추가했거나(+ 버튼) 원본이
    # 삭제된 경우 None이며, 이때는 title/content/photo_path에 저장된 값을 그대로 쓴다.
    source_finding_id: Mapped[int | None] = mapped_column(ForeignKey("finding.id"), default=None)

    report: Mapped[Report] = relationship(back_populates="previous_findings")
    source_finding: Mapped["Finding | None"] = relationship(foreign_keys=[source_finding_id])

    def display_fields(self) -> tuple[str, str, str]:
        """(제목, 내용, 사진경로) — 이월 원본이 살아있으면 그 최신 값을, 아니면 저장된
        스냅샷을 반환한다. 조치결과/확인여부/위험성은 이 보고서에서 직접 기록하는 후속조치
        정보라 원본과 무관하게 항상 `self`에 저장된 값을 그대로 쓴다(호출부에서 별도 처리)."""
        if self.source_finding_id and self.source_finding:
            f = self.source_finding
            return f.title, f.content, f.photo_path
        return self.title, self.content, self.photo_path


class Measurement(Base):
    """6. 계측자료."""

    __tablename__ = "measurement"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("report.id"))
    instrument_type: Mapped[str] = mapped_column(Text)  # 소음측정기/산소농도측정기/... (7종)
    photo_path: Mapped[str] = mapped_column(Text, default="")
    value: Mapped[str] = mapped_column(Text, default="")

    report: Mapped[Report] = relationship(back_populates="measurements")


class ProvidedMaterial(Base):
    """7. 제공자료 (최대 2건, 라이브러리 선택 또는 직접 업로드)."""

    __tablename__ = "provided_material"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("report.id"))
    slot: Mapped[int] = mapped_column()  # 1~2
    material_id: Mapped[int | None] = mapped_column(ForeignKey("material_library.id"), default=None)
    custom_photo_path: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(Text, default="")

    report: Mapped[Report] = relationship(back_populates="provided_materials")
    material: Mapped["MaterialLibrary | None"] = relationship()


class ProcessHazardEntry(Base):
    """9. 진행공정 유해·위험요인 파악 및 대책 (최대 4공정, 회차 데이터)."""

    __tablename__ = "process_hazard_entry"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("report.id"))
    slot: Mapped[int] = mapped_column()  # 1~4
    process_name: Mapped[str] = mapped_column(Text, default="")
    hazard_text: Mapped[str] = mapped_column(Text, default="")
    prevention_text: Mapped[str] = mapped_column(Text, default="")
    risk_level: Mapped[str] = mapped_column(Text, default="")  # 상/중/하

    report: Mapped[Report] = relationship(back_populates="process_entries")


class CurrentProcessPhoto(Base):
    """6. 현재 진행중인 공정 유해위험요인 파악 — 현장 사진 (최대 2장). OverviewPhoto와 동일한 모양."""

    __tablename__ = "current_process_photo"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("report.id"))
    slot: Mapped[int] = mapped_column()  # 1~2
    photo_path: Mapped[str] = mapped_column(Text, default="")

    report: Mapped[Report] = relationship(back_populates="current_process_photos")


class CurrentProcessEntry(Base):
    """6. 현재 진행중인 공정 유해위험요인 파악 (최대 4행).

    실제 문서(표12)가 8번 섹션(표15, `ProcessHazardEntry`)과 완전히 같은 표 구조(진행공정/
    유해·위험요인/예방대책/위험성)로 통일되면서 이 모델도 같은 모양으로 바뀌었다 —
    `process_name`/`prevention_text`를 새로 추가했다. `measure_text`("현재안전보건조치")·
    `evaluation`("평가")은 옛 구조(항목당 유해위험요인만 여러 줄, 평가 열 있음)에서 쓰던
    컬럼으로, 새 코드는 더 이상 채우지 않지만 과거 데이터 호환을 위해 컬럼 자체는 지우지
    않는다(이 프로젝트의 다른 컬럼들과 같은 원칙 — `core/db.py` 마이그레이션은 컬럼을
    삭제하지 않고 추가만 한다)."""

    __tablename__ = "current_process_entry"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("report.id"))
    slot: Mapped[int] = mapped_column()  # 1~4
    process_name: Mapped[str] = mapped_column(Text, default="")
    hazard_text: Mapped[str] = mapped_column(Text, default="")
    prevention_text: Mapped[str] = mapped_column(Text, default="")
    risk_level: Mapped[str] = mapped_column(Text, default="")  # 상/중/하
    measure_text: Mapped[str] = mapped_column(Text, default="")  # (옛 구조) 현재안전보건조치 — 더 이상 안 씀
    evaluation: Mapped[str] = mapped_column(Text, default="")  # (옛 구조) 양호/미흡 — 더 이상 안 씀

    report: Mapped[Report] = relationship(back_populates="current_process_entries")


class LawArticleCache(Base):
    """법령 검색 결과 로컬 캐시 (국가법령정보센터 Open API 응답)."""

    __tablename__ = "law_article_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    law_name: Mapped[str] = mapped_column(Text)
    article_no: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    fetched_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)


class ProcessCatalog(Base):
    """공정 카탈로그 (진행공정 선택 모달의 검색 대상). 초기엔 공정명만 시딩되고
    유해위험요인/예방대책/위험등급은 검수 전까지 비어있을 수 있다(reviewed=False)."""

    __tablename__ = "process_catalog"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(Text)  # 예: 경량철골·지붕개량공사
    construction_type: Mapped[str] = mapped_column(Text, default="")
    process_name: Mapped[str] = mapped_column(Text)
    hazard_text: Mapped[str] = mapped_column(Text, default="")
    prevention_text: Mapped[str] = mapped_column(Text, default="")
    default_risk_level: Mapped[str] = mapped_column(Text, default="")
    reviewed: Mapped[bool] = mapped_column(default=False)
    sort_order: Mapped[int] = mapped_column(default=0)  # 실제 사이트 "전체" 목록의 원래 순서


class MaterialLibrary(Base):
    """제공자료 라이브러리."""

    __tablename__ = "material_library"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    thumbnail_path: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(Text, default="")  # 쉼표 구분


class MeasurementStandard(Base):
    """계측장비별 고정 측정기준값."""

    __tablename__ = "measurement_standard"

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_type: Mapped[str] = mapped_column(Text, unique=True)
    standard_criteria: Mapped[str] = mapped_column(Text, default="")


class AppSetting(Base):
    """사용자별 로컬 설정 (Claude API 키, AI 기능 on/off 등). 배포 시 각자 PC에서 직접 입력한다."""

    __tablename__ = "app_setting"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(Text, unique=True)
    value: Mapped[str] = mapped_column(Text, default="")
