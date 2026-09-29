"""보고서 이력 관리 — 데스크톱 현장상세 "보고서 이력"(`desktop/views/site_detail_view.py`)의 "↓ 한글", "🗑 삭제".

- 한글(.hwpx): COM 없이 순수 파이썬 엔진(`build_report_hwpx`, 데스크톱 "↓ 한글"과 같은 함수)이라 렌더 워커/큐
  없이 요청 안에서 바로 만든다(수 초). 누를 때마다 저장된 최신 내용으로 새로 만든다(데스크톱과 동일).
- 삭제: 자식 테이블은 ORM cascade로 같이 지워지지만, PostgreSQL은 외래키를 실제로 검사해서 두 가지를
  먼저 정리해야 한다(데스크톱 SQLite는 검사 안 해서 문제가 드러나지 않았음) —
  ① 다음 회차 4번 이전지적사항이 이 보고서의 8번 지적사항을 가리키는 연결(끊어도 이월 내용은 저장된
  사본(title/content/photo_path)으로 남는다 — PreviousFinding.display_fields 참고, 단 사진 파일은 이
  보고서 폴더에 있으므로 지우지 않고 남겨둔다), ② PDF 렌더 작업 기록(report_job).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from core.models_db import Finding, PreviousFinding
from core.models_web import ReportJob, User
from core.report_builder_hwpx import build_report_hwpx
from server.api import repo
from server.api.deps import get_current_user, get_db

router = APIRouter(prefix="/reports/{report_id}", tags=["report-manage"])


def download_name(report, suffix: str) -> str:
    site_name = (report.site.name if report.site else "") or "보고서"
    safe = "".join(ch for ch in site_name if ch not in '\\/:*?"<>|').strip() or "보고서"
    return f"{safe}_{report.visit_no}회차{suffix}"


@router.get("/hwpx")
def download_hwpx(
    report_id: int,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = repo.get_report(db, user.company_id, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    tmp_dir = tempfile.TemporaryDirectory()
    out = Path(tmp_dir.name) / "report.hwpx"
    try:
        build_report_hwpx(report_id, out)
    except Exception as err:  # noqa: BLE001
        tmp_dir.cleanup()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"한글 파일을 만들지 못했습니다: {err}") from err
    background.add_task(tmp_dir.cleanup)  # 응답을 다 보낸 뒤 임시 파일 정리
    return FileResponse(out, media_type="application/hwp+zip", filename=download_name(report, ".hwpx"))


@router.get("/pdf")
def download_pdf(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """마지막으로 만든 PDF 받기(현장 화면 보고서 목록의 "PDF 생성됨"을 누를 때). 새로 만들지 않고 저장된 파일을 그대로 준다."""
    report = repo.get_report(db, user.company_id, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    if not report.pdf_path or not Path(report.pdf_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "아직 만든 PDF가 없습니다. 보고서 화면에서 'PDF 생성'을 먼저 누르세요.")
    return FileResponse(report.pdf_path, media_type="application/pdf", filename=download_name(report, ".pdf"))


@router.delete("")
def delete_report(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report = repo.get_report(db, user.company_id, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    finding_ids = [f.id for f in db.query(Finding.id).filter(Finding.report_id == report_id)]
    if finding_ids:
        db.query(PreviousFinding).filter(
            PreviousFinding.source_finding_id.in_(finding_ids), PreviousFinding.report_id != report_id
        ).update({PreviousFinding.source_finding_id: None}, synchronize_session=False)
    db.query(ReportJob).filter(ReportJob.report_id == report_id).delete(synchronize_session=False)
    for path in (report.pdf_path, report.notify_signature_path):
        if path:
            Path(path).unlink(missing_ok=True)
    db.delete(report)
    db.commit()
    return {"ok": True}
