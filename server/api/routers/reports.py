from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.models_web import User
from server.api import repo
from server.api.deps import get_current_user, get_db
from server.schemas.report import JobOut, ReportIn, ReportOut

router = APIRouter(tags=["reports"])


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


@router.post("/reports/{report_id}/render", response_model=JobOut)
def render_report(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """PDF 생성 작업을 큐에 등록만 하고 즉시 응답한다 — 실제 렌더링(실측 8~15초, 한글 COM
    자동화)은 이 요청과 완전히 분리된 별도 워커 프로세스(server/worker/render_worker.py)가
    처리한다. 프론트엔드는 응답으로 받은 job id를 GET /jobs/{id}로 폴링한다."""
    job = repo.create_render_job(db, user.company_id, report_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    return job
