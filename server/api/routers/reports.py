from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from core import config
from core.db import BASE_DIR
from core.models_web import User
from server.api import repo
from server.api.deps import get_current_user, get_db
from server.schemas.report import JobOut, ReportIn, ReportOut, SignoffStatus

router = APIRouter(tags=["reports"])


@router.get("/sites/{site_id}/reports", response_model=list[ReportOut])
def list_reports(site_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return repo.list_reports_for_site(db, user.company_id, site_id)


@router.post("/sites/{site_id}/reports", response_model=ReportOut)
def create_report(
    site_id: int, body: ReportIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    report = repo.create_report(db, user.company_id, site_id, **body.model_dump())
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "현장을 찾을 수 없습니다.")
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
    """섹션을 하나씩 채워나갈 때마다(1번 결재·통보 정보부터) 이 엔드포인트로 저장한다 —
    데스크톱 마법사가 매 섹션 변경 시 `_save(navigate=False)`로 전체를 다시 저장하는 것과
    같은 방식으로, 프론트도 섹션 저장 버튼마다 이 PATCH를 호출하면 된다."""
    report = repo.update_report(db, user.company_id, report_id, **body.model_dump())
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    return report


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
