from __future__ import annotations

import datetime
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from core import config
from core.contract_analyzer import extract_site_info
from core.db import BASE_DIR
from core.models_db import Finding, PreviousFinding, Report, Site, SiteProcessDefault, Staff
from core.models_web import ReportJob, User
from server.api import repo
from server.api.deps import get_current_user, get_db
from server.api.geocode import map_addresses
from server.api.routers.report_manage import prepared_hwpx_path, preview_dir
from server.api.site_pace_out import last_visit_nos, pace_dict
from server.api.routers.reports import check_staff_limit
from server.api.security import verify_password
from server.schemas.site import SiteIn, SiteListItem, SiteOut

router = APIRouter(prefix="/sites", tags=["sites"])


@router.get("", response_model=list[SiteListItem])
def list_sites(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """현장 목록 + 현장별 보고서 요약(작성 수·최근 회차·최근 지도일)과 담당요원 이름 — 목록 화면에서 바로 보이게."""
    sites = repo.list_sites(db, user.company_id)
    ids = [s.id for s in sites]
    stats = {
        site_id: (count, last_no, last_date)
        for site_id, count, last_no, last_date in db.query(
            Report.site_id, func.count(Report.id), func.max(Report.visit_no), func.max(Report.guidance_date)
        ).filter(Report.site_id.in_(ids)).group_by(Report.site_id)
    } if ids else {}
    staff_ids = {s.assigned_staff_id for s in sites if s.assigned_staff_id}
    staff_names = dict(db.query(Staff.id, Staff.name).filter(Staff.id.in_(staff_ids))) if staff_ids else {}
    map_addr = map_addresses(db, sites)
    out = []
    for site in sites:
        count, last_no, last_date = stats.get(site.id, (0, None, None))
        item = SiteListItem.model_validate(site)
        item.report_count = count
        item.last_visit_no = last_no
        item.last_guidance_date = last_date
        item.staff_name = staff_names.get(site.assigned_staff_id, "")
        item.map_address = map_addr[site.id]
        item.pace = pace_dict(site, last_no)
        out.append(item)
    return out


@router.post("/extract-from-contract", response_model=SiteIn)
async def extract_from_contract(file: UploadFile, user: User = Depends(get_current_user)):
    """계약서·공문 PDF를 업로드하면 Claude로 '신규현장추가' 폼 필드를 추출해 돌려준다
    (desktop/views/site_form_view.py의 계약서 자동인식과 동일한 기능·같은 프롬프트,
    core/contract_analyzer.py를 그대로 재사용). 여기서 DB에 아무것도 저장하지 않는다 —
    프론트가 반환된 값으로 폼을 미리 채워주고, 사용자가 확인/수정한 뒤 POST /sites로
    실제 저장을 따로 요청한다.

    실측 약 20초 걸리는 순수 API 호출(한글 COM처럼 단일 인스턴스 제약이 없음)이라 큐 없이
    이 요청 안에서 바로 처리한다 — FastAPI가 동기 함수를 스레드풀에서 돌려주므로 다른
    요청을 막지 않는다."""
    if not config.has_api_key(user.company_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Claude API 키가 설정되어 있지 않습니다. 설정 화면에서 먼저 등록하세요.",
        )
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "PDF 파일만 업로드할 수 있습니다.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / "contract.pdf"
        tmp_path.write_bytes(await file.read())
        try:
            data = extract_site_info(tmp_path, company_id=user.company_id)
        except Exception as e:  # noqa: BLE001 -- Claude/파싱 오류를 그대로 사용자에게 보여줌
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"계약서 분석에 실패했습니다: {e}") from e

    return data


@router.get("/next-management-no")
def next_management_no(year: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """관리번호 "자동생성" — "{연도}-{7자리 일련번호}"로 이 회사 현장 중 그 연도의 가장 큰 번호 + 1
    (데스크톱 `_auto_generate_management_no`와 같은 규칙, 웹판은 회사별로 센다). 저장은 안 한다."""
    prefix = f"{year or datetime.date.today().year}-"
    max_seq = 0
    for (management_no,) in db.query(Site.management_no).filter(Site.company_id == user.company_id):
        suffix = (management_no or "")[len(prefix):] if (management_no or "").startswith(prefix) else ""
        if suffix.isdigit():
            max_seq = max(max_seq, int(suffix))
    return {"management_no": f"{prefix}{max_seq + 1:07d}"}


@router.post("", response_model=SiteOut)
def create_site(body: SiteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return repo.create_site(db, user.company_id, **body.model_dump())


@router.get("/{site_id}", response_model=SiteOut)
def get_site(site_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    site = repo.get_site(db, user.company_id, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "현장을 찾을 수 없습니다.")
    out = SiteOut.model_validate(site)
    out.pace = pace_dict(site, last_visit_nos(db, [site.id]).get(site.id))
    return out


@router.patch("/{site_id}", response_model=SiteOut)
def update_site(
    site_id: int, body: SiteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    # 담당요원은 현장 ↔ 보고서 연동(2026-09-29 사용자 요청) — 현장에서 바꾸면 이 현장의 **아직 PDF를 안 만든 보고서**
    # (status != final)도 같은 사람으로. 이미 PDF를 만든(제출한) 과거 회차는 그대로 둔다(표지·서명이 바뀌면 안 되므로).
    # 하루 4현장 한도(reports.check_staff_limit)에 하나라도 걸리면 아무것도 안 바꾸고 400. 반대 방향은 reports.update_report.
    existing = repo.get_site(db, user.company_id, site_id)
    if existing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "현장을 찾을 수 없습니다.")
    new_staff = body.assigned_staff_id
    drafts = []
    if new_staff != existing.assigned_staff_id:
        drafts = [r for r in existing.reports if r.status != "final" and r.assigned_staff_id != new_staff]
        for r in drafts:
            check_staff_limit(db, r, {"assigned_staff_id": new_staff})
    site = repo.update_site(db, user.company_id, site_id, **body.model_dump())
    if drafts:
        for r in drafts:
            r.assigned_staff_id = new_staff
        db.commit()
        db.refresh(site)
    return site


@router.delete("/{site_id}")
def delete_site(
    site_id: int,
    password: str = Body("", embed=True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """현장 삭제 — 이 현장의 보고서 전부(사진·PDF·서명 파일 포함)와 공정 기본값까지 함께 지운다(되돌릴 수 없음).
    데스크톱 `dashboard_view._delete_site`와 같은 범위. PostgreSQL은 외래키를 실제로 검사하므로
    보고서 삭제(`report_manage.delete_report`)처럼 이월 연결(이전지적사항 → 지적사항)과 PDF 렌더 작업 기록을 먼저 정리한다.
    같은 현장 보고서끼리만 이월되므로 사진 폴더(data/photos/report_{id})는 통째로 지워도 다른 현장에 영향 없다."""
    # 회사 공용 삭제 비밀번호(설정 화면에서 정함)를 알아야 지울 수 있다 — 아직 안 정했으면 삭제 자체를 막는다
    password_hash = config.get_site_delete_password_hash(user.company_id)
    if not password_hash:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "삭제 비밀번호가 아직 없습니다. '설정' 탭에서 먼저 정하세요.")
    if not verify_password(password, password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "삭제 비밀번호가 맞지 않습니다.")
    site = repo.get_site(db, user.company_id, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "현장을 찾을 수 없습니다.")
    deleted_reports = delete_site_cascade(db, site)
    return {"ok": True, "deleted_reports": deleted_reports}


def delete_site_cascade(db: Session, site: Site) -> int:
    """현장 하나를 보고서·공정 기본값·파일까지 통째로 지운다(비밀번호 확인은 호출하는 쪽 몫). 지운 보고서 수를 돌려준다.
    PostgreSQL 외래키 때문에 이월 연결과 PDF 렌더 작업 기록을 먼저 정리하고, 파일은 DB 삭제가 확정된 뒤에 지운다."""
    site_id = site.id
    reports = db.query(Report).filter(Report.site_id == site_id).all()
    report_ids = [r.id for r in reports]
    files = [p for r in reports for p in (r.pdf_path, r.notify_signature_path) if p]
    if report_ids:
        finding_ids = [f.id for f in db.query(Finding.id).filter(Finding.report_id.in_(report_ids))]
        if finding_ids:
            db.query(PreviousFinding).filter(PreviousFinding.source_finding_id.in_(finding_ids)).update(
                {PreviousFinding.source_finding_id: None}, synchronize_session=False
            )
        db.query(ReportJob).filter(ReportJob.report_id.in_(report_ids)).delete(synchronize_session=False)
    for report in reports:
        db.delete(report)
    db.query(SiteProcessDefault).filter(SiteProcessDefault.site_id == site_id).delete(synchronize_session=False)
    db.delete(site)
    db.commit()
    for path in files:
        Path(path).unlink(missing_ok=True)
        if path.lower().endswith(".pdf"):
            shutil.rmtree(preview_dir(path), ignore_errors=True)  # 폰 미리보기 쪽 이미지
    for report_id in report_ids:
        shutil.rmtree(BASE_DIR / "data" / "photos" / f"report_{report_id}", ignore_errors=True)
        prepared_hwpx_path(report_id).unlink(missing_ok=True)  # 한글 받기용으로 준비해 둔 파일
    return len(report_ids)
