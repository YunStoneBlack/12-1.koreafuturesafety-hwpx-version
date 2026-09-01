"""'이전 보고서 업로드'에서 AI가 추출한 dict(core.report_extractor.extract_report_info의
반환값)를 DB에 반영하는 매칭·중복방지·저장 로직.

core/models_db.py에는 site_mgmt_no/biz_reg_no/(site_id, visit_no)에 대한 유니크 제약이
전혀 없어서(직접 확인함), 이 모듈이 매칭·중복 검사를 직접 책임진다:
- 현장 매칭: 사업장관리번호(site_mgmt_no)로 먼저 찾고, 없으면 현장명으로 폴백한다
  (실제 사이트 설명 문구 "번호를 못 읽은 보고서는 현장명으로 이어붙입니다"와 동일한 규칙).
- 회차 중복: 매칭/생성된 현장에 같은 visit_no의 Report가 이미 있으면 새로 만들지 않는다.
"""

from __future__ import annotations

from datetime import date

from core.db import SessionLocal
from core.models_db import (
    Finding,
    Measurement,
    MaterialLibrary,
    PreviousFinding,
    ProcessHazardEntry,
    ProvidedMaterial,
    Report,
    SafetyEducation,
    Site,
)


def find_matching_site(site_data: dict, session) -> Site | None:
    site_mgmt_no = (site_data.get("site_mgmt_no") or "").strip()
    if site_mgmt_no:
        match = session.query(Site).filter(Site.site_mgmt_no == site_mgmt_no).first()
        if match:
            return match
    name = (site_data.get("name") or "").strip()
    if name:
        return session.query(Site).filter(Site.name == name).first()
    return None


def find_duplicate_report(site_id: int, visit_no: int | None, session) -> Report | None:
    if visit_no is None:
        return None
    return (
        session.query(Report)
        .filter(Report.site_id == site_id, Report.visit_no == visit_no)
        .first()
    )


def preview_match(extracted: dict) -> dict:
    """등록 전 검토용 — DB에 아무것도 쓰지 않고 매칭/중복 상태만 미리 확인한다.

    반환: {"site_name", "is_new_site", "duplicate_report_id"(있으면 int, 없으면 None)}
    """
    site_data = extracted["site"]
    report_data = extracted["report"]
    with SessionLocal() as session:
        site = find_matching_site(site_data, session)
        duplicate_id = None
        if site is not None:
            duplicate = find_duplicate_report(site.id, report_data.get("visit_no"), session)
            duplicate_id = duplicate.id if duplicate else None
        return {
            "site_name": site.name if site else (site_data.get("name") or "(이름 없음)"),
            "is_new_site": site is None,
            "duplicate_report_id": duplicate_id,
        }


def _parse_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def commit_extracted(extracted: dict) -> dict:
    """추출된 데이터를 DB에 반영한다.

    반환: {"site_id", "report_id", "is_new_site", "skipped"}. 이미 같은 현장·회차 보고서가
    있으면 아무것도 새로 만들지 않고 skipped=True로 기존 report_id를 돌려준다 — 여러 파일을
    연달아 등록하는 도중에도 항상 다시 확인한다(등록 직전 미리보기 이후 상태가 바뀌었을 수 있음).
    """
    with SessionLocal() as session:
        site_data = extracted["site"]
        report_data = extracted["report"]

        site = find_matching_site(site_data, session)
        is_new_site = site is None
        if site is None:
            site = Site(
                name=site_data.get("name") or "(이름 없음)",
                address=site_data.get("address") or "",
                period_start=_parse_date(site_data.get("period_start")),
                period_end=_parse_date(site_data.get("period_end")),
                amount=site_data.get("amount"),
                site_mgmt_no=site_data.get("site_mgmt_no") or "",
                biz_start_no=site_data.get("biz_start_no") or "",
                manager_name=site_data.get("manager_name") or "",
                manager_phone=site_data.get("manager_phone") or "",
                manager_email=site_data.get("manager_email") or "",
                hq_company=site_data.get("hq_company") or "",
                corp_reg_no=site_data.get("corp_reg_no") or "",
                biz_reg_no=site_data.get("biz_reg_no") or "",
                license_no=site_data.get("license_no") or "",
                hq_phone=site_data.get("hq_phone") or "",
                hq_address=site_data.get("hq_address") or "",
                total_guidance_count=site_data.get("total_guidance_count"),
            )
            session.add(site)
            session.flush()

        visit_no = report_data.get("visit_no")
        duplicate = find_duplicate_report(site.id, visit_no, session)
        if duplicate:
            session.commit()
            return {
                "site_id": site.id,
                "report_id": duplicate.id,
                "is_new_site": is_new_site,
                "skipped": True,
            }

        report = Report(
            site_id=site.id,
            visit_no=visit_no or 1,
            guidance_date=_parse_date(report_data.get("guidance_date")),
            progress_rate=report_data.get("progress_rate"),
            notification_method=report_data.get("notification_method") or "",
            prev_guidance_implemented=report_data.get("prev_guidance_implemented"),
            special_note=report_data.get("special_note") or "",
            hazard_factor_checks=report_data.get("hazard_factor_checks") or [],
        )
        session.add(report)
        session.flush()

        attendee_count = report_data.get("attendee_count")
        if attendee_count is not None:
            session.add(SafetyEducation(report_id=report.id, attendee_count=attendee_count))

        for idx, f in enumerate(extracted.get("findings") or [], start=1):
            if idx > 4:
                break
            session.add(
                Finding(
                    report_id=report.id,
                    slot=idx,
                    title=f.get("title") or "",
                    content=f.get("content") or "",
                    law_citation=f.get("law_citation") or "",
                    likelihood=f.get("likelihood"),
                    severity=f.get("severity"),
                )
            )

        for idx, p in enumerate(extracted.get("previous_findings") or [], start=1):
            if idx > 4:
                break
            session.add(
                PreviousFinding(
                    report_id=report.id,
                    slot=idx,
                    title=p.get("title") or "",
                    content=p.get("content") or "",
                    action_result=p.get("action_result") or "조치완료",
                )
            )

        for m in extracted.get("measurements") or []:
            instrument_type = m.get("instrument_type") or ""
            if not instrument_type:
                continue
            session.add(
                Measurement(report_id=report.id, instrument_type=instrument_type, value=m.get("value") or "")
            )

        for idx, mat in enumerate(extracted.get("provided_materials") or [], start=1):
            if idx > 2:
                break
            title = mat.get("title") or ""
            if not title:
                continue
            library_match = session.query(MaterialLibrary).filter(MaterialLibrary.title == title).first()
            session.add(
                ProvidedMaterial(
                    report_id=report.id,
                    slot=idx,
                    material_id=library_match.id if library_match else None,
                    title=title,
                )
            )

        for idx, proc in enumerate(extracted.get("process_entries") or [], start=1):
            if idx > 4:
                break
            session.add(
                ProcessHazardEntry(
                    report_id=report.id,
                    slot=idx,
                    process_name=proc.get("process_name") or "",
                    hazard_text=proc.get("hazard_text") or "",
                    prevention_text=proc.get("prevention_text") or "",
                    risk_level=proc.get("risk_level") or "",
                )
            )

        session.commit()
        return {
            "site_id": site.id,
            "report_id": report.id,
            "is_new_site": is_new_site,
            "skipped": False,
        }
