from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from core.models_web import User
from server.api import repo
from server.api.deps import get_current_user, get_db
from server.schemas.report import JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """프론트엔드가 1.5초 간격 정도로 폴링하는 용도. status가 queued|rendering|done|failed."""
    job = repo.get_job(db, user.company_id, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "작업을 찾을 수 없습니다.")
    return job


@router.get("/{job_id}/download")
def download_job_pdf(job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = repo.get_job(db, user.company_id, job_id)
    if job is None or job.status != "done":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "아직 준비되지 않았습니다.")
    report = repo.get_report(db, user.company_id, job.report_id)
    if report is None or not report.pdf_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일을 찾을 수 없습니다.")
    return FileResponse(report.pdf_path, media_type="application/pdf", filename=f"report_{report.id}.pdf")
