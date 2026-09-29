from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from core import config
from core.db import BASE_DIR
from core.models_db import Staff
from core.models_web import ReportEdit, ReportJob, User
from core.staff_load import MAX_SITES_PER_STAFF_PER_DAY, is_full, other_site_names
from server.api import repo
from server.api.report_defaults import apply_new_report_defaults, record_site_hazard_checks
from server.api.deps import get_current_user, get_db
from server.schemas.report import JobOut, ReportIn, ReportOut, SignoffStatus

router = APIRouter(tags=["reports"])


@router.get("/sites/{site_id}/reports", response_model=list[ReportOut])
def list_reports(site_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    reports = repo.list_reports_for_site(db, user.company_id, site_id)
    ids = [r.id for r in reports]
    if not ids:
        return []
    outdated = pdf_outdated_map(db, reports)
    out = []
    for r in reports:
        item = ReportOut.model_validate(r)
        item.pdf_outdated = outdated[r.id]
        out.append(item)
    return out


def pdf_outdated_map(db: Session, reports) -> dict[int, bool]:
    """{보고서 id: PDF가 수정 전 버전인가} — 마지막으로 성공한 PDF 렌더 작업이 시작된 뒤에 고쳤으면 True
    (렌더 도중 고친 것도 빠졌을 수 있어 시작 시각 기준). 수정 시각은 server/api/edit_tracking.py가 기록."""
    ids = [r.id for r in reports]
    edited = dict(db.query(ReportEdit.report_id, ReportEdit.edited_at).filter(ReportEdit.report_id.in_(ids)))
    rendered = dict(
        db.query(ReportJob.report_id, func.max(ReportJob.started_at))
        .filter(ReportJob.report_id.in_(ids), ReportJob.status == "done")
        .group_by(ReportJob.report_id)
    )
    result = {}
    for r in reports:
        e, started = edited.get(r.id), rendered.get(r.id)
        result[r.id] = bool(r.status == "final" and e and (started is None or e > started))
    return result


@router.get("/reports/{report_id}/pdf-status")
def pdf_status(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """보고서 화면 "미리보기"용 — 최신 PDF가 있으면 바로 띄우고, 없거나 수정 전 버전이면 새로 만든다."""
    report = repo.get_report(db, user.company_id, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    has_pdf = bool(report.pdf_path) and Path(report.pdf_path).exists()
    return {"has_pdf": has_pdf, "outdated": pdf_outdated_map(db, [report])[report.id]}


@router.post("/sites/{site_id}/reports", response_model=ReportOut)
def create_report(
    site_id: int, body: ReportIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    fields = body.model_dump(exclude_unset=True)
    report = repo.create_report(db, user.company_id, site_id, **fields)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "현장을 찾을 수 없습니다.")
    # 이전 회차·현장 기본값 승계(데스크톱 새 보고서와 동일, server/api/report_defaults.py)
    apply_new_report_defaults(db, report, explicit=set(fields))
    return report


@router.get("/reports/{report_id}", response_model=ReportOut)
def get_report(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report = repo.get_report(db, user.company_id, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    return report


@router.patch("/reports/{report_id}", response_model=ReportOut)
def update_report(
    report_id: int, body: ReportIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """섹션을 하나씩 채워나갈 때마다(1번 결재·통보 정보부터) 이 엔드포인트로 저장한다.

    `exclude_unset=True`가 핵심 — JSON 바디에 실제로 들어있던 필드만 갱신하고, 프론트가
    안 보낸 필드는 건드리지 않는다. 이게 없으면 예를 들어 "2번 섹션 저장" 버튼이 2번
    필드만 보내는 순간 1번(통보방법·서명 성명 등)이 ReportIn의 기본값(""/False)으로
    전부 리셋되어버린다 — 섹션별로 나눠 저장하는 이 화면 구조에서는 반드시 필요하다."""
    fields = body.model_dump(exclude_unset=True)
    if fields.get("visit_no") is None:
        fields.pop("visit_no", None)  # 회차는 비울 수 없음(NOT NULL)
    elif fields["visit_no"] < 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "회차는 1 이상이어야 합니다.")
    current = repo.get_report(db, user.company_id, report_id)
    if current is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    check_staff_limit(db, current, fields)
    report = repo.update_report(db, user.company_id, report_id, **fields)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    if "hazard_factor_checks" in fields:
        record_site_hazard_checks(db, report)  # 다음 회차 기본값(데스크톱 저장 로직과 동일)
    # 담당요원은 보고서 ↔ 현장 연동(2026-09-29 사용자 요청) — 보고서에서 정하면 현장 담당요원도 같은 사람으로
    # (현장 목록 "담당"과 다음 회차 자동 배정이 따라온다). 반대 방향은 sites.update_site.
    if "assigned_staff_id" in fields and report.site and report.site.assigned_staff_id != report.assigned_staff_id:
        report.site.assigned_staff_id = report.assigned_staff_id
        db.commit()
        db.refresh(report)
    return report


def check_staff_limit(db: Session, report, fields: dict) -> None:
    """담당요원 하루 4현장 한도(core/staff_load.py, 데스크톱 report_wizard_staff_limit.py와 같은 규칙).
    요원이나 지도일을 **바꿀 때만** 검사한다 — 예전 데이터가 이미 4곳을 넘어도 열고 저장할 수 있어야 해서
    (데스크톱도 저장된 보고서를 다시 열 땐 검사 안 함)."""
    if "assigned_staff_id" not in fields and "guidance_date" not in fields:
        return
    staff_id = fields.get("assigned_staff_id", report.assigned_staff_id)
    date = fields.get("guidance_date", report.guidance_date)
    if not staff_id or not date or (staff_id, date) == (report.assigned_staff_id, report.guidance_date):
        return
    names = other_site_names(db, staff_id, date, report.site_id)
    if is_full(names):
        staff = db.get(Staff, staff_id)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{staff.name if staff else '이'} 담당요원은 {date:%Y-%m-%d}에 이미 {MAX_SITES_PER_STAFF_PER_DAY}개 현장"
            f"({', '.join(names)})을 맡고 있어 더 맡을 수 없습니다. 다른 담당요원을 고르거나 지도일을 바꿔 주세요.",
        )


class StaffLoadItem(BaseModel):
    staff_id: int
    count: int
    full: bool
    sites: list[str]


class StaffLoadOut(BaseModel):
    max: int
    items: list[StaffLoadItem]


@router.get("/reports/{report_id}/staff-load", response_model=StaffLoadOut)
def get_staff_load(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """이 보고서 지도일 기준 요원별 "이미 맡은 다른 현장 수" — 드롭다운에 "2/4", "4/4 마감" 표시용."""
    report = repo.get_report(db, user.company_id, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    items = []
    for staff in repo.list_staff(db, user.company_id):
        names = other_site_names(db, staff.id, report.guidance_date, report.site_id)
        items.append(StaffLoadItem(staff_id=staff.id, count=len(names), full=is_full(names), sites=names))
    return StaffLoadOut(max=MAX_SITES_PER_STAFF_PER_DAY, items=items)


@router.get("/reports/{report_id}/signoff-status", response_model=SignoffStatus)
def get_signoff_status(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """섹션 1의 담당요원/결재란(이사·대표이사) 서명 등록 여부 — 실제 등록은 담당요원 관리·
    설정 화면에서 한다(아직 웹판에 없음, 데스크톱 기준값을 그대로 봄), 여기선 상태만."""
    report = repo.get_report(db, user.company_id, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")

    staff_signed = False
    if report.assigned_staff_id:
        staff = repo.get_staff(db, user.company_id, report.assigned_staff_id)
        staff_signed = bool(staff and staff.signature_path)

    director_path, _ = config.get_company_signature("director", user.company_id)
    ceo_path, _ = config.get_company_signature("ceo", user.company_id)
    return SignoffStatus(staff_signed=staff_signed, director_signed=bool(director_path), ceo_signed=bool(ceo_path))


@router.post("/reports/{report_id}/notify-signature", response_model=ReportOut)
async def save_notify_signature(
    report_id: int, file: UploadFile, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """현장책임자 서명 저장 — 브라우저 캔버스에서 그린 PNG를 그대로 받아서 저장한다.
    desktop/widgets/signature_pad.py의 `move_or_reference`와 같은 최종 경로 규칙
    (`data/signatures/report_{id}_notify.png`)을 그대로 따른다."""
    report = repo.get_report(db, user.company_id, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")

    sig_dir = BASE_DIR / "data" / "signatures"
    sig_dir.mkdir(parents=True, exist_ok=True)
    final_path = sig_dir / f"report_{report_id}_notify.png"
    final_path.write_bytes(await file.read())

    return repo.update_report(
        db, user.company_id, report_id, notify_signature_path=str(final_path), notify_signature_source="drawn"
    )


@router.get("/reports/{report_id}/notify-signature-image")
def get_notify_signature_image(
    report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    report = repo.get_report(db, user.company_id, report_id)
    if report is None or not report.notify_signature_path or not Path(report.notify_signature_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "저장된 서명이 없습니다.")
    return FileResponse(report.notify_signature_path, media_type="image/png")


@router.delete("/reports/{report_id}/notify-signature", response_model=ReportOut)
def clear_notify_signature(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report = repo.get_report(db, user.company_id, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    return repo.update_report(db, user.company_id, report_id, notify_signature_path="", notify_signature_source="")


@router.post("/reports/{report_id}/render", response_model=JobOut)
def render_report(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """PDF 생성 작업을 큐에 등록만 하고 즉시 응답한다 — 실제 렌더링(실측 8~15초, 한글 COM
    자동화)은 이 요청과 완전히 분리된 별도 워커 프로세스(server/worker/render_worker.py)가
    처리한다. 프론트엔드는 응답으로 받은 job id를 GET /jobs/{id}로 폴링한다."""
    job = repo.create_render_job(db, user.company_id, report_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    return job
