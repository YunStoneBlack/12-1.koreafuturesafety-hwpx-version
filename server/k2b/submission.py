"""웹판 DB(보고서 한 회차) → K2B 제출 값(2026-10-01). 14번 `core/db_reader.py`(데스크톱 SQLite를 읽던 것)의 규칙을 그대로 옮김.

- 보고서에서 자동: 현장명(관리번호 라벨 없는 원래 이름 — K2B 검색용), 지도일, 공정률, 현장책임자·연락처, 특이사항, 통보방법,
  사진(3번 전경 → K2B "현장전경" / 3번 점검 → "현장점검"(사용자 2026-10-02: 점검 사진만 — 이전지적·지적·TBM·계측 사진은 안 올림) /
  4번 이전지적사항 이행완료 증빙 → "현장개선"), 보고서 파일 = PDF(K2B는 PDF만 받음, CONFIRMED).
- 사용자 2026-10-02: 지도건수 = 8번 지적사항 개수, 교육인원 = 10번 TBM 참석 인원, 배포자료건수 = 11번 제공자료 개수(값이 없으면 비워 둠),
  문제점 및 개선 요청사항 = 8번 지적사항 한 줄에 한 건("제목 / 내용" 한 줄), 이전 기술지도 이행여부 = 4번 결과로 미리 고름(prev_guidance_auto).
- [K2B 제출] 창에서 사람이 고르는 것(ManualFields): 현재 작업공종(7종), 이행여부, 경영책임자·발주자 통보일, 비계 사용·종류, 불량사업장 통보(+내용·첨부), 대형사고 위험작업.
  경영책임자(본사)·발주자 통보일도 창에서 고름(사용자 2026-10-02, 기본은 비움).
- 점검자는 K2B가 로그인 계정 이름으로 고정 → 그 회차 담당요원의 K2B 계정으로 로그인(server/api/routers/staff_k2b.py).
"""
from __future__ import annotations

import re

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from core.models_db import (
    Finding, InspectionPhoto, OverviewPhoto, PreviousFinding, ProvidedMaterial, Report, SafetyEducation, Site,
)
from server.api.carryover import is_active


@dataclass
class MajorHazardWork:
    """대형사고 위험작업 한 행(업무영역은 K2B가 자동으로 채움)."""

    occurrence_type: str  # 전체/붕괴/도괴/낙하/질식
    hazard_work: str  # selectors.MAJOR_HAZARD_WORK_OPTIONS 중 하나
    start_date: str  # YYYY-MM-DD
    end_date: str


@dataclass
class ManualFields:
    current_process: str = ""  # selectors.CURRENT_PROCESS_OPTIONS 중 하나, "" = 선택 안 함
    scaffold_usage: str = ""  # "사용" | "미사용" | "" = 선택 안 함
    scaffold_types: list[str] = field(default_factory=list)
    bad_site_notify: bool = False
    bad_site_content: str = ""
    bad_site_files: list[str] = field(default_factory=list)
    major_hazard_works: list[MajorHazardWork] = field(default_factory=list)
    # 이전 기술지도 이행여부 — 창에서 고름(이행/불이행/해당없음). K2B는 "해당없음"을 1차수에서만 받음(2026-10-01 실측: 6차수에선 잠겨
    # "이전 기술지도 통보여부를 선택해 주세요."로 저장 막힘) — 그래서 보고서 값이 없을 때 자동으로 해당없음을 넣지 않고 사람이 고른다.
    prev_guidance: str = ""
    # 경영책임자(건설업체 본사) 통보일 — 분기 하나(1~4) + 날짜(둘 다 있거나 둘 다 없음, 40억 이상 공사만), 건설공사 발주자 통보일 — 날짜.
    # 기본은 비움, 요원이 창에서 고름(사용자 2026-10-02 — 10/1의 "넣지 않는다"를 바꿈).
    ceo_notice_quarter: int | None = None
    ceo_notice_date: str = ""  # YYYY-MM-DD
    owner_notice_date: str = ""


@dataclass
class K2BSubmission:
    site_name: str
    visit_no: int
    guidance_date: str | None
    staff_id: int | None
    staff_name: str
    site_manager_name: str = ""
    site_manager_phone: str = ""
    progress_rate: int | None = None
    special_note: str = ""
    notification_method: str = ""
    prev_guidance_auto: str = ""  # 4번 결과로 미리 고른 이행여부("" = 사람이 골라야 함) — prev_guidance_auto()
    prev_guidance_reason: str = ""
    guidance_count: int | None = None  # None = K2B 칸 비워 둠
    education_count: int | None = None
    material_count: int | None = None
    problem_texts: list[str] = field(default_factory=list)  # 문제점 및 개선 요청사항(한 줄 = 한 건)
    overview_photo_paths: list[str] = field(default_factory=list)
    inspection_photo_paths: list[str] = field(default_factory=list)
    improvement_photo_paths: list[str] = field(default_factory=list)
    report_pdf_path: str = ""
    manual: ManualFields = field(default_factory=ManualFields)
    # K2B에서 현장 고를 때 같이 비교(2026-10-08 — site_match.py): 주소·공사금액·공사 기간(YYYYMMDD)·사업장관리번호·개시번호(숫자만)
    site_address: str = ""
    site_amount: int | None = None
    site_start: str = ""
    site_end: str = ""
    site_mgmt_no: str = ""
    site_start_no: str = ""

    def site_key(self):
        from server.k2b.site_match import SiteKey
        return SiteKey(self.site_name, self.site_address, self.site_amount, self.site_start, self.site_end,
                       self.site_mgmt_no, self.site_start_no)


def _paths(rows, attr: str = "photo_path") -> list[str]:
    return [getattr(r, attr) for r in rows if getattr(r, attr) and Path(getattr(r, attr)).exists()]


def prev_guidance_auto(report: Report, rows: list[PreviousFinding]) -> tuple[str, str]:
    """K2B "이전 기술지도 이행여부"를 4번 이전지적사항 결과로 미리 고른다(사용자 2026-10-02). (값, 창에 보일 이유).
    1회차 → 해당없음(K2B는 1차수에서만 받음) / 이전지적 없음·해당없음 → 이행 / 결과 안 고른 줄 있음 → ""(사람이 먼저 고르게) /
    하나라도 확인불가·보완필요 → 불이행 / 전부 이행완료 → 이행."""
    if report.visit_no == 1:
        return "해당없음", "1회차라 해당없음"
    active = [] if report.previous_findings_na else [pf for pf in rows if is_active(pf)]
    if not active:
        return "이행", "4번 이전지적사항이 없어 이행"
    blank = sum(1 for pf in active if not pf.result_status)
    if blank:
        return "", f"4번 이전지적사항 결과를 안 고른 줄이 {blank}개 — 보고서에서 먼저 고르세요"
    bad = [pf.result_status for pf in active if pf.result_status != "이행완료"]
    if bad:
        counts = " · ".join(f"{k} {bad.count(k)}건" for k in ("확인불가", "보완필요") if k in bad)
        return "불이행", f"4번에 {counts} → 불이행"
    return "이행", f"4번 {len(active)}건 모두 이행완료 → 이행"


def _problem_text(f: Finding) -> str:
    """문제점 및 개선 요청사항 한 칸 — "제목 / 내용" 한 줄(사용자 2026-10-02: K2B 칸은 첫 줄만 보여 줄바꿈 방식은 제목만 보였음).
    제목·내용 안의 줄바꿈은 띄어쓰기로 잇는다."""
    parts = (" ".join((f.title or "").split()), " ".join((f.content or "").split()))
    return " / ".join(x for x in parts if x)


def build_submission(db: Session, report: Report, manual: ManualFields | None = None) -> K2BSubmission:
    site: Site = report.site
    rid = report.id
    staff = report.assigned_staff
    by_slot = lambda model: db.query(model).filter(model.report_id == rid).order_by(model.slot).all()  # noqa: E731
    previous = by_slot(PreviousFinding)
    prev_value, prev_reason = prev_guidance_auto(report, previous)
    findings = [] if report.findings_na else [f for f in by_slot(Finding) if _problem_text(f)]
    tbm = db.query(SafetyEducation).filter(SafetyEducation.report_id == rid).first()
    materials = [] if report.materials_na else [m for m in by_slot(ProvidedMaterial)
                                                  if m.material_id or m.custom_photo_path or (m.title or "").strip()]
    return K2BSubmission(
        site_name=site.name,
        site_address=site.address or "",
        site_amount=site.amount,
        site_start=site.period_start.strftime("%Y%m%d") if site.period_start else "",
        site_end=site.period_end.strftime("%Y%m%d") if site.period_end else "",
        site_mgmt_no=re.sub(r"\D", "", site.site_mgmt_no or ""),
        site_start_no=re.sub(r"\D", "", site.biz_start_no or ""),
        visit_no=report.visit_no,
        guidance_date=report.guidance_date.isoformat() if report.guidance_date else None,
        staff_id=report.assigned_staff_id,
        staff_name=staff.name if staff else "",
        site_manager_name=site.manager_name or "",
        site_manager_phone=site.manager_phone or "",
        progress_rate=report.progress_rate,
        special_note=report.special_note or "",
        notification_method=report.notification_method or "",
        prev_guidance_auto=prev_value,
        prev_guidance_reason=prev_reason,
        guidance_count=len(findings) or None,
        education_count=(tbm.attendee_count or None) if tbm else None,
        material_count=len(materials) or None,
        problem_texts=[_problem_text(f) for f in findings],
        overview_photo_paths=_paths(by_slot(OverviewPhoto)),
        inspection_photo_paths=_paths(by_slot(InspectionPhoto)),
        improvement_photo_paths=_paths(previous, "completion_photo_path"),
        report_pdf_path=report.pdf_path if report.pdf_path and Path(report.pdf_path).exists() else "",
        manual=manual or ManualFields(),
    )
