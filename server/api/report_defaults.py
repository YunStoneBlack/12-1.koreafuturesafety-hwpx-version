"""새 보고서 기본값·이전 회차 승계 — 데스크톱 `desktop/views/report_wizard_view.py`(새 보고서 열 때)와
`_reset_report_fields`가 채우는 값을 웹판 보고서 생성(`POST /sites/{id}/reports`) 직후 DB에 그대로 넣는다.
예전 웹판은 이걸 하나도 안 해서, 새 보고서가 전부 빈칸(교육장소·교육자료·통보방법 등)으로 PDF에
나갔다(Sub-phase 40에서 발견).

- 이전 회차(같은 현장 마지막 보고서) 승계: 현장책임자 성명(없으면 현장 관리자명)·서명(파일 복사)·
  통보방법(없으면 "전자우편")·공정률, 이전 지도일 = 직전 회차 지도일
- 담당요원: 그날 예정의 보고서 담당자 → 직전 회차 보고서 담당 → 현장 담당(그날 4곳이면 순서대로 여유 있는 사람, 2026-10-02)
- 현장 단위 승계: 6번 12대 기인물 체크, 9번 향후 진행공정 "공정명만"
  (유해요인은 매 회차 새로 작성하는 값이라 승계 안 함 — 데스크톱 Sub-phase 20 원칙)
- 고정 기본값: 지도일 오늘, 재해발생 "무", 10-1 교육장소 "현장 내"·교육자료 "안전보건공단 배포자료",
  10-2 조도계/가스농도측정기 측정치 문구 + 판정 "양호" + 조치 "이상 없음 확인"
전부 입력칸의 초기값일 뿐 사용자가 그대로 고칠 수 있다.

반대 방향(보고서 저장 → 현장에 기록)은 `record_site_defaults_*` — 데스크톱 저장 로직
(`report_wizard_save.py`)처럼 6번 체크와 9번 공정명을 현장에 남겨 다음 회차가 이어받게 한다.
"""

from __future__ import annotations

import datetime
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from core.models_db import Measurement, ProcessHazardEntry, Report, SafetyEducation, Site, SiteProcessDefault
from core.models_web import VisitPlan
from core.staff_load import other_site_names
from server.api import storage
from server.api.report_staff import pick, staff_order

DEFAULT_NOTIFICATION_METHOD = "전자우편"
DEFAULT_EDUCATION_LOCATION = "현장 내"
DEFAULT_EDUCATION_MATERIAL = "안전보건공단 배포자료"
DEFAULT_MEASUREMENT_VALUES = {"조도계": "기준치 이내", "가스농도측정기": "적정 범위 내"}
DEFAULT_MEASUREMENT_VERDICT = "양호"
DEFAULT_MEASUREMENT_ACTION = "이상 없음 확인"


def _copy_signature(src: str, db: Session, report: Report) -> str:
    """이전 회차 서명을 이 보고서 전용 경로(회차 폴더, storage 규칙)로 복사한다(같은 파일을 공유하면 한쪽에서 지울 때 다른
    회차 서명까지 사라지므로)."""
    if not src or not Path(src).exists():
        return ""
    dest = storage.notify_signature_path(db, report)
    try:
        shutil.copyfile(src, dest)
    except OSError:
        return ""
    return str(dest)


def apply_new_report_defaults(db: Session, report: Report, explicit: set[str]) -> None:
    """방금 만든 보고서에 기본값을 채운다. `explicit`는 생성 요청에 직접 들어온 필드 — 그건 덮어쓰지 않는다."""
    site = db.get(Site, report.site_id)
    last = (
        db.query(Report)
        .filter(Report.site_id == report.site_id, Report.id != report.id, Report.visit_no < report.visit_no)
        .order_by(Report.visit_no.desc())
        .first()
    )

    def setdefault(field: str, value) -> None:
        if field not in explicit and value not in (None, ""):
            setattr(report, field, value)

    setdefault("notify_signee_name", (last.notify_signee_name if last else "") or (site.manager_name if site else ""))
    setdefault("notification_method", (last.notification_method if last else "") or DEFAULT_NOTIFICATION_METHOD)
    setdefault("progress_rate", last.progress_rate if last else None)
    setdefault("prev_guidance_date", last.guidance_date if last else None)
    setdefault("guidance_date", datetime.date.today())
    setdefault("accident_status", "무")
    # 보고서 담당요원(2026-10-02, server/api/report_staff.py): 그날 이 현장 방문 예정에 정해 둔 보고서 담당자 → 없으면 직전 회차 보고서 담당
    # → 1회차면 현장 담당(계약 당시). 그 사람이 그 지도일에 이미 보고서 4곳이면 보고서 담당 순서에서 여유 있는 사람(모두 차면 비움).
    date = report.guidance_date or datetime.date.today()
    planned = db.query(VisitPlan.report_staff_id).filter(VisitPlan.site_id == report.site_id, VisitPlan.plan_date == date,
                                                         VisitPlan.report_staff_id.isnot(None)).order_by(VisitPlan.id).first()
    preferred = (planned[0] if planned else None) or (last.assigned_staff_id if last else None) or (site.assigned_staff_id if site else None)
    if site and "assigned_staff_id" not in explicit:
        load = {sid: set(other_site_names(db, sid, date, report.site_id)) for sid in staff_order(db, site.company_id)}
        preferred = pick(preferred, load, staff_order(db, site.company_id), report.site_id)
    setdefault("assigned_staff_id", preferred)
    if "hazard_factor_checks" not in explicit and site and site.hazard_factor_checks:
        report.hazard_factor_checks = list(site.hazard_factor_checks)
    if last and last.notify_signature_path and "notify_signature_path" not in explicit:
        copied = _copy_signature(last.notify_signature_path, db, report)
        if copied:
            report.notify_signature_path = copied
            report.notify_signature_source = last.notify_signature_source

    db.add(
        SafetyEducation(
            report_id=report.id, location=DEFAULT_EDUCATION_LOCATION, material=DEFAULT_EDUCATION_MATERIAL
        )
    )
    for instrument, value in DEFAULT_MEASUREMENT_VALUES.items():
        db.add(
            Measurement(
                report_id=report.id,
                instrument_type=instrument,
                value=value,
                manual_verdict=DEFAULT_MEASUREMENT_VERDICT,
                manual_action=DEFAULT_MEASUREMENT_ACTION,
            )
        )
    if site:
        for default in sorted(site.process_defaults, key=lambda d: d.slot):
            if default.process_name.strip():
                db.add(ProcessHazardEntry(report_id=report.id, slot=default.slot, process_name=default.process_name))
    db.commit()
    db.refresh(report)


def record_site_hazard_checks(db: Session, report: Report) -> None:
    """6번 저장 시 — 12대 기인물 체크를 현장에도 기록(다음 회차 기본값)."""
    site = db.get(Site, report.site_id)
    if site is not None:
        site.hazard_factor_checks = list(report.hazard_factor_checks or [])
        db.commit()


def record_site_process_name(db: Session, report: Report, slot: int, process_name: str) -> None:
    """9번 저장 시 — 그 슬롯의 공정명을 현장에도 기록(비우면 현장 기본값에서도 지움)."""
    row = db.query(SiteProcessDefault).filter_by(site_id=report.site_id, slot=slot).first()
    name = process_name.strip()
    if not name:
        if row is not None:
            db.delete(row)
    elif row is None:
        db.add(SiteProcessDefault(site_id=report.site_id, slot=slot, process_name=name))
    else:
        row.process_name = name
    db.commit()
