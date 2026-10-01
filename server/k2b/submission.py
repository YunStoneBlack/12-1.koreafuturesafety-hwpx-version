"""웹판 DB(보고서 한 회차) → K2B 제출 값(2026-10-01). 14번 `core/db_reader.py`(데스크톱 SQLite를 읽던 것)의 규칙을 그대로 옮김.

- 보고서에서 자동: 현장명(관리번호 라벨 없는 원래 이름 — K2B 검색용), 지도일, 공정률, 현장책임자·연락처, 특이사항, 통보방법, 이전 지도 이행여부,
  사진(전경 → K2B "현장전경" / 점검·이전지적·지적·TBM·계측 → "현장점검"(K2B엔 지적사항 칸이 따로 없음, 14번 CONFIRMED) /
  이전지적 조치완료 → "현장개선"), 보고서 파일 = PDF(K2B는 PDF만 받음, CONFIRMED).
- [K2B 제출] 창에서 사람이 고르는 것(ManualFields): 현재 작업공종(7종), 비계 사용·종류, 불량사업장 통보(+내용·첨부), 대형사고 위험작업.
  지도건수·경영책임자/발주자 통보일은 넣지 않는다(사용자 2026-10-01).
- 점검자는 K2B가 로그인 계정 이름으로 고정 → 그 회차 담당요원의 K2B 계정으로 로그인(server/api/routers/staff_k2b.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from core.models_db import (
    Finding, InspectionPhoto, Measurement, OverviewPhoto, PreviousFinding, Report, SafetyEducation, Site,
)


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
    prev_guidance_implemented: bool | None = None
    overview_photo_paths: list[str] = field(default_factory=list)
    inspection_photo_paths: list[str] = field(default_factory=list)
    improvement_photo_paths: list[str] = field(default_factory=list)
    report_pdf_path: str = ""
    manual: ManualFields = field(default_factory=ManualFields)


def _paths(rows, attr: str = "photo_path") -> list[str]:
    return [getattr(r, attr) for r in rows if getattr(r, attr) and Path(getattr(r, attr)).exists()]


def build_submission(db: Session, report: Report, manual: ManualFields | None = None) -> K2BSubmission:
    site: Site = report.site
    rid = report.id
    staff = report.assigned_staff
    by_slot = lambda model: db.query(model).filter(model.report_id == rid).order_by(model.slot).all()  # noqa: E731
    inspection = _paths(by_slot(InspectionPhoto))
    inspection += _paths(by_slot(PreviousFinding))
    inspection += _paths(by_slot(Finding))
    inspection += _paths(db.query(SafetyEducation).filter(SafetyEducation.report_id == rid).all())
    inspection += _paths(db.query(Measurement).filter(Measurement.report_id == rid).order_by(Measurement.id).all())
    return K2BSubmission(
        site_name=site.name,
        visit_no=report.visit_no,
        guidance_date=report.guidance_date.isoformat() if report.guidance_date else None,
        staff_id=report.assigned_staff_id,
        staff_name=staff.name if staff else "",
        site_manager_name=site.manager_name or "",
        site_manager_phone=site.manager_phone or "",
        progress_rate=report.progress_rate,
        special_note=report.special_note or "",
        notification_method=report.notification_method or "",
        prev_guidance_implemented=report.prev_guidance_implemented,
        overview_photo_paths=_paths(by_slot(OverviewPhoto)),
        inspection_photo_paths=inspection,
        improvement_photo_paths=_paths(by_slot(PreviousFinding), "completion_photo_path"),
        report_pdf_path=report.pdf_path if report.pdf_path and Path(report.pdf_path).exists() else "",
        manual=manual or ManualFields(),
    )
