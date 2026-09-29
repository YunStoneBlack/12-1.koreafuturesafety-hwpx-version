from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from core.models_web import ReportJob, User
from server.api import repo
from server.api.deps import get_current_user, get_db
from server.api.routers.report_manage import download_name
from server.schemas.report import JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """프론트엔드가 1.5초 간격 정도로 폴링하는 용도. status가 queued|rendering|done|failed|canceled."""
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
    return FileResponse(report.pdf_path, media_type="application/pdf", filename=download_name(report, ".pdf"))


@router.post("/{job_id}/cancel")
def cancel_job(job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """PDF 만들기 취소(보고서 화면 "PDF 생성"·미리보기의 [취소]/닫기).
    - 아직 순서를 기다리는 중(queued)이면 "canceled"로 바꿔 워커가 건너뛰게 한다 → {"canceled": true}.
      워커가 막 가져가는 순간과 겹치지 않게 "queued일 때만" 한 번의 UPDATE로 바꾼다.
    - 이미 한글로 만드는 중(rendering)이면 멈추지 않는다 — 한글 COM을 중간에 끊으면 다음 작업까지 망가질 수 있음.
      화면은 기다리기만 그만두고, PDF는 끝까지 만들어져 현장 화면에 "PDF 생성됨"으로 나온다 → {"canceled": false, "status": "rendering"}."""
    job = repo.get_job(db, user.company_id, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "작업을 찾을 수 없습니다.")
    changed = (
        db.query(ReportJob)
        .filter(ReportJob.id == job_id, ReportJob.status == "queued")
        .update({"status": "canceled", "finished_at": datetime.datetime.now()}, synchronize_session=False)
    )
    db.commit()
    if changed:
        return {"canceled": True, "status": "canceled"}
    db.refresh(job)
    return {"canceled": False, "status": job.status}
