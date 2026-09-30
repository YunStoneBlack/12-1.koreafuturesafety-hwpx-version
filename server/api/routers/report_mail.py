"""고객사에 보고서 PDF 메일 보내기 — 현장 화면 보고서 목록의 "📧 고객사 전송"(Sub-phase 63).

- GET  /reports/{id}/mail — 창에 띄울 정보: 현장책임자 메일(기본 받는 사람), 참조·보내는 주소, 첨부 파일 이름·크기,
  PDF 상태(없음/수정 전 버전/만드는 중), 보낸 기록, 이 현장에서 지난번에 보낸 받는 사람들(다음 회차에 자동으로 채움).
- 보낸 기록 `to_addr`에는 받는 사람들을 ", "로 이어 저장한다(표 모양은 그대로).
- POST /reports/{id}/mail {to: [주소…]} — 받는 사람 여러 곳(감리 현장은 발주처·감리단 등)을 한 통으로(서로 보임, 사용자 결정 2026-09-29). 최신 PDF만 보낸다(수정 전 버전·만드는 중이면 409 "PDF를 다시 만든 뒤 보내세요").
  보낸 기록(ReportMail)을 남긴다. 이 요청은 보고서 수정이 아니므로 edit_tracking에서 제외(PDF가 "수정 전 버전"이 되지 않게).
"""

from __future__ import annotations

import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_db import Report
from core.models_web import ReportJob, ReportMail, User
from server import settings as app_settings
from server.api import mailer, repo
from server.api.repo import mail_table_ready
from server.api.deps import get_current_user, get_db
from server.api.routers.report_manage import download_name
from server.api.routers.site_contacts import contacts_of, retired_emails, split_emails
from server.api.routers.reports import pdf_outdated_map

router = APIRouter(prefix="/reports/{report_id}/mail", tags=["report-mail"])


MAX_RECIPIENTS = 10


class MailSendIn(BaseModel):
    to: list[str] | str  # str은 예전 화면(한 곳) 호환


def split_addrs(value: str) -> list[str]:
    return [a.strip() for a in (value or "").split(",") if a.strip()]


def _site_last_recipients(db: Session, site_id: int) -> list[str]:
    """이 현장 보고서 중 가장 최근에 보낸 메일의 받는 사람들 — 감리 현장은 매 회차 같은 발주처·감리단에 보내므로 다음 회차에 채워 둔다."""
    if not mail_table_ready(db):
        return []
    last = (
        db.query(ReportMail).join(Report, Report.id == ReportMail.report_id)
        .filter(Report.site_id == site_id).order_by(ReportMail.sent_at.desc()).first()
    )
    return split_addrs(last.to_addr) if last else []


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
    contacts = contacts_of(db, site) if site else {}
    retired = retired_emails(db, site.id) if site else {}
    last_raw = [a.lower() for a in _site_last_recipients(db, report.site_id)]
    role_emails = {
        "manager": [manager_email] if mailer.valid_email(manager_email) else [],
        "owner": split_emails(contacts.get("owner_email", "")),
        "supervisor": split_emails(contacts.get("supervisor_email", "")),
    }
    # 처음 체크 상태 — 지난번에 받은 곳(지금 주소로든, 바뀌기 전 옛 주소로든). 처음 보내면 등록된 곳 전부.
    role_checked = {
        role: bool(emails) and (
            not last_raw
            or any(a.lower() in last_raw for a in emails)
            or any(retired.get(a) == role for a in last_raw)
        )
        for role, emails in role_emails.items()
    }
    return {
        "site_id": report.site_id,
        "configured": mailer.is_configured() and mail_table_ready(db),
        "from_addr": app_settings.MAIL_SMTP_USER,
        "cc": app_settings.MAIL_CC,
        "manager_name": (site.manager_name or "") if site else "",
        "manager_email": manager_email if mailer.valid_email(manager_email) else "",
        # 발주처·감리단(site_contact) — 전송 창 체크 항목(없으면 빈 값)
        "owner_name": contacts.get("owner_name", ""),
        "owner_emails": split_emails(contacts.get("owner_email", "")),
        "supervisor_name": contacts.get("supervisor_name", ""),
        "supervisor_emails": split_emails(contacts.get("supervisor_email", "")),
        "subject": mailer.mail_subject(site.name if site else "", report.visit_no),
        "filename": download_name(report, ".pdf"),
        "size_bytes": Path(report.pdf_path).stat().st_size if has_pdf else 0,
        "problem": _pdf_problem(db, report),
        "history": _history(db, report_id),
        # 지난번 받는 사람 — 현장책임자·발주처·감리단에서 바뀌어 빠진 옛 주소는 빼고 채운다
        "last_recipients": [a for a in _site_last_recipients(db, report.site_id) if a.lower() not in retired],
        "role_checked": role_checked,
        "max_recipients": MAX_RECIPIENTS,
    }


@router.post("")
def send_mail(
    report_id: int, body: MailSendIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    report = _require_report(db, user, report_id)
    if not mailer.is_configured() or not mail_table_ready(db):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "메일 보내기 설정이 아직 안 됐습니다(회사 네이버 메일 연결 필요).")
    to_addrs: list[str] = []
    for addr in ([body.to] if isinstance(body.to, str) else body.to):
        addr = addr.strip()
        if not addr:
            continue
        if not mailer.valid_email(addr):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"받는 사람 메일 주소를 확인하세요: {addr}")
        if addr.lower() not in (a.lower() for a in to_addrs):  # 같은 주소 두 번은 하나로
            to_addrs.append(addr)
    if not to_addrs:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "받는 사람을 한 곳 이상 넣으세요.")
    if len(to_addrs) > MAX_RECIPIENTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"받는 사람은 {MAX_RECIPIENTS}곳까지 넣을 수 있습니다.")
    problem = _pdf_problem(db, report)
    if problem:
        raise HTTPException(status.HTTP_409_CONFLICT, problem)

    site_name = report.site.name if report.site else ""
    cc_addr = mailer.cc_for(to_addrs)
    try:
        refused = mailer.send_pdf(
            to_addrs, cc_addr,
            mailer.mail_subject(site_name, report.visit_no), mailer.mail_body(site_name, report.visit_no),
            Path(report.pdf_path), download_name(report, ".pdf"),
        )
    except mailer.MailError as e:
        # 400 — 5xx면 앞단 nginx가 자기 오류 화면으로 바꿔 안내 문구가 안 보일 수 있음
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e

    db.add(ReportMail(
        report_id=report.id, sent_at=datetime.datetime.now(), to_addr=", ".join(to_addrs), cc_addr=cc_addr,
        sent_by=user.display_name or "",
    ))
    db.commit()
    return {"ok": True, "to": to_addrs, "cc": cc_addr, "refused": refused, "history": _history(db, report_id)}
