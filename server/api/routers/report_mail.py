"""고객사에 보고서 PDF 메일 보내기 — 현장 화면 보고서 목록의 "📧 고객사 전송"(Sub-phase 63).

- GET  /reports/{id}/mail — 창에 띄울 정보: 현장책임자 메일(기본 받는 사람), 참조·보내는 주소, 첨부 파일 이름·크기,
  PDF 상태(없음/수정 전 버전/만드는 중), 보낸 기록.
- POST /reports/{id}/mail {to} — 최신 PDF만 보낸다(수정 전 버전·만드는 중이면 409 "PDF를 다시 만든 뒤 보내세요").
  보낸 기록(ReportMail)을 남긴다. 이 요청은 보고서 수정이 아니므로 edit_tracking에서 제외(PDF가 "수정 전 버전"이 되지 않게).
"""

from __future__ import annotations

import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from core.models_web import ReportJob, ReportMail, User
from server import settings as app_settings
from server.api import mailer, repo
from server.api.deps import get_current_user, get_db
from server.api.routers.report_manage import download_name
from server.api.routers.reports import pdf_outdated_map

router = APIRouter(prefix="/reports/{report_id}/mail", tags=["report-mail"])


_table_ready = False


def mail_table_ready(db: Session) -> bool:
    """report_mail 표가 DB에 있나(alembic 0004 적용 전이면 False) — 새 코드가 먼저 돌아도 현장 화면 목록이 깨지지 않게.
    한 번 있으면 계속 있으므로 True는 기억해 둔다."""
    global _table_ready
    if not _table_ready:
        _table_ready = inspect(db.get_bind()).has_table("report_mail")
    return _table_ready


class MailSendIn(BaseModel):
    to: str


def _history(db: Session, report_id: int) -> list[dict]:
    if not mail_table_ready(db):
        return []
    rows = db.query(ReportMail).filter(ReportMail.report_id == report_id).order_by(ReportMail.sent_at.desc())
    return [
        {"sent_at": r.sent_at.strftime("%Y-%m-%d %H:%M"), "to": r.to_addr, "cc": r.cc_addr, "by": r.sent_by}
        for r in rows
    ]


def _pdf_problem(db: Session, report) -> str:
    """보낼 수 없는 이유(없으면 "")."""
    if not report.pdf_path or not Path(report.pdf_path).exists():
        return "아직 PDF를 만들지 않았습니다. 보고서 화면에서 PDF를 만든 뒤 보내세요."
    busy = (
        db.query(ReportJob.id)
        .filter(ReportJob.report_id == report.id, ReportJob.status.in_(("queued", "rendering")))
        .first()
    )
    if busy:
        return "PDF를 만드는 중입니다. 다 만들어진 뒤 보내세요."
    if pdf_outdated_map(db, [report])[report.id]:
        return "PDF를 만든 뒤 보고서 내용이 바뀌었습니다. 보고서 화면에서 PDF를 다시 만든 뒤 보내세요."
    return ""


def _require_report(db: Session, user: User, report_id: int):
    report = repo.get_report(db, user.company_id, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    return report


@router.get("")
def mail_info(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report = _require_report(db, user, report_id)
    site = report.site
    has_pdf = bool(report.pdf_path) and Path(report.pdf_path).exists()
    manager_email = (site.manager_email or "").strip() if site else ""
    return {
        "configured": mailer.is_configured() and mail_table_ready(db),
        "from_addr": app_settings.MAIL_SMTP_USER,
        "cc": app_settings.MAIL_CC,
        "manager_name": (site.manager_name or "") if site else "",
        "manager_email": manager_email if mailer.valid_email(manager_email) else "",
        "subject": mailer.mail_subject(site.name if site else "", report.visit_no),
        "filename": download_name(report, ".pdf"),
        "size_bytes": Path(report.pdf_path).stat().st_size if has_pdf else 0,
        "problem": _pdf_problem(db, report),
        "history": _history(db, report_id),
    }


@router.post("")
def send_mail(
    report_id: int, body: MailSendIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    report = _require_report(db, user, report_id)
    if not mailer.is_configured() or not mail_table_ready(db):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "메일 보내기 설정이 아직 안 됐습니다(회사 네이버 메일 연결 필요).")
    to_addr = body.to.strip()
    if not mailer.valid_email(to_addr):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "받는 사람 메일 주소를 확인하세요.")
    problem = _pdf_problem(db, report)
    if problem:
        raise HTTPException(status.HTTP_409_CONFLICT, problem)

    site_name = report.site.name if report.site else ""
    cc_addr = mailer.cc_for(to_addr)
    try:
        mailer.send_pdf(
            to_addr, cc_addr,
            mailer.mail_subject(site_name, report.visit_no), mailer.mail_body(site_name, report.visit_no),
            Path(report.pdf_path), download_name(report, ".pdf"),
        )
    except mailer.MailError as e:
        # 400 — 5xx면 앞단 nginx가 자기 오류 화면으로 바꿔 안내 문구가 안 보일 수 있음
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e

    db.add(ReportMail(
        report_id=report.id, sent_at=datetime.datetime.now(), to_addr=to_addr, cc_addr=cc_addr,
        sent_by=user.display_name or "",
    ))
    db.commit()
    return {"ok": True, "to": to_addr, "cc": cc_addr, "history": _history(db, report_id)}
