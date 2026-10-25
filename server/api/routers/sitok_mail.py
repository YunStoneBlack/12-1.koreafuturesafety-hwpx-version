"""시특법 회차 화면 [📧 보고서 보내기](2026-10-25 민재형 "시특법에 메일 기능", 방식 = 내려받기 링크 — 사용자 "1번이지 당연히").

합본 PDF가 커서(96MB) 첨부하지 않고 기한 있는 내려받기 링크를 메일로(server/api/mail_jobs.py). 바로 보내기 또는 날짜·시각 예약
(작업 프로그램 server/worker/mail_worker.py). 보내면 제출 현황 "전송" 표시(묶인 동 같이). 받는 사람 기본 = 이 시설물(묶음)에 지난번 보낸
주소, 처음이면 서류 자동화 계약의 현장 담당·발주처 담당 메일.

- `GET  /sitok/reports/{rid}/mail` — 창 정보 + 보낸·예약 기록
- `POST /sitok/reports/{rid}/mail` {to: [...], subject?, note?, run_at?} — 보내기(run_at 있으면 예약)
- `DELETE /mail-jobs/{jid}` — 예약 취소(시특법·산안법 같이)
- `POST /mail-jobs/{jid}/revoke` — 보낸 링크 끊기(잘못 보냈을 때 — 기한을 지금으로)
"""
from __future__ import annotations

import datetime
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import MailJob, SitokDocContract, SitokFacility, SitokReport, User
from server import settings as app_settings
from server.api import mail_jobs, mailer
from server.api.deps import get_current_user, get_db

router = APIRouter(tags=["sitok-mail"])
MAX_RECIPIENTS = 10


def _require(db: Session, user: User, rid: int) -> SitokReport:
    r = db.get(SitokReport, rid)
    if r is None or r.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "회차를 찾을 수 없습니다.")
    return r


def _unit_ids(db: Session, r: SitokReport) -> set[int]:
    """이 회차 시설물(묶음이면 묶인 동 전부) id."""
    f = db.get(SitokFacility, r.facility_id)
    if f is None or not f.group_id:
        return {r.facility_id}
    return {m.id for m in db.query(SitokFacility).filter(SitokFacility.group_id == f.group_id)}


def _emails(value: str) -> list[str]:
    return [a for a in re.split(r"[,;\s]+", value or "") if mailer.valid_email(a)]


def _roles(db: Session, company_id: int, ids: set[int]) -> list[dict]:
    """서류 자동화 계약(현장 연결)의 현장 담당·발주처 담당 — 가장 최근 계약."""
    for d in db.query(SitokDocContract).filter(SitokDocContract.company_id == company_id).order_by(SitokDocContract.id.desc()):
        if set(d.facility_ids or ([d.facility_id] if d.facility_id else [])) & ids:
            return [x for x in (
                {"key": "site", "label": "현장 담당", "name": d.site_manager or "", "emails": _emails(d.site_email)},
                {"key": "client", "label": "발주처 담당", "name": d.client_manager or d.client or "", "emails": _emails(d.client_email)},
            ) if x["emails"] or x["name"]]
    return []


def _jobs_q(db: Session, report_ids: list[int]):
    return db.query(MailJob).filter(MailJob.kind == "sitok", MailJob.report_id.in_(report_ids))


def _last_to(db: Session, ids: set[int]) -> list[str]:
    """이 시설물(묶음)에 지난번(어느 회차든) 보낸 받는 사람."""
    rids = [x for (x,) in db.query(SitokReport.id).filter(SitokReport.facility_id.in_(ids))]
    last = _jobs_q(db, rids).filter(MailJob.status == "done").order_by(MailJob.sent_at.desc()).first() if rids else None
    return mail_jobs.split_addrs(last.to_addr) if last else []


def _out(db: Session, user: User, r: SitokReport) -> dict:
    from server.api.routers.sitok_status import _unit_reports

    ids = _unit_ids(db, r)
    pdf = mail_jobs.sitok_pdf(r)
    unit = [x.id for x in _unit_reports(db, r)]
    return {
        "configured": mailer.is_configured(),
        "from_addr": app_settings.MAIL_SMTP_USER, "cc": app_settings.MAIL_CC,
        "title": mail_jobs.sitok_title(r), "subject": mail_jobs.sitok_subject(r),
        "filename": pdf.name if pdf else "", "size_bytes": pdf.stat().st_size if pdf else 0,
        "problem": mail_jobs.sitok_problem(r), "share_days": mail_jobs.SHARE_DAYS,
        "roles": _roles(db, user.company_id, ids), "last_recipients": _last_to(db, ids),
        "max_recipients": MAX_RECIPIENTS,
        "jobs": [mail_jobs.job_out(j) for j in _jobs_q(db, unit).order_by(MailJob.id.desc()).limit(30)],
    }


@router.get("/sitok/reports/{rid}/mail")
def mail_info(rid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(db, user, _require(db, user, rid))


class SendIn(BaseModel):
    to: list[str]
    subject: str = ""
    note: str = ""
    run_at: str | None = None


def clean_to(values: list[str]) -> list[str]:
    to: list[str] = []
    for a in values:
        a = (a or "").strip()
        if not a:
            continue
        if not mailer.valid_email(a):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"받는 사람 메일 주소를 확인하세요: {a}")
        if a.lower() not in (x.lower() for x in to):
            to.append(a)
    if not to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "받는 사람을 한 곳 이상 넣으세요.")
    if len(to) > MAX_RECIPIENTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"받는 사람은 {MAX_RECIPIENTS}곳까지 넣을 수 있습니다.")
    return to


def run_at_of(value: str | None) -> datetime.datetime | None:
    try:
        return mail_jobs.parse_run_at(value)
    except ValueError as e:
        msg = str(e)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, msg if "예약" in msg else "예약 날짜·시각이 맞지 않습니다.") from e


@router.post("/sitok/reports/{rid}/mail")
def send(rid: int, body: SendIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, rid)
    if not mailer.is_configured():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "메일 보내기 설정이 아직 안 됐습니다(회사 네이버 메일 연결 필요).")
    to = clean_to(body.to)
    run_at = run_at_of(body.run_at)
    if run_at is None:
        problem = mail_jobs.sitok_problem(r)
        if problem:
            raise HTTPException(status.HTTP_409_CONFLICT, problem)
    elif mail_jobs.sitok_pdf(r) is None and r.status != "running":
        raise HTTPException(status.HTTP_409_CONFLICT, "아직 합본 PDF가 없습니다 — 보고서를 만든 뒤 예약하세요.")
    job = MailJob(company_id=user.company_id, kind="sitok", report_id=r.id, to_addr=", ".join(to), cc_addr=mailer.cc_for(to),
                  subject=(body.subject or "").strip()[:200] or mail_jobs.sitok_subject(r), note=(body.note or "")[:2000],
                  run_at=run_at, status="queued" if run_at else "sending", created_by=user.display_name or "")
    db.add(job)
    db.commit()
    if run_at is None:
        mail_jobs.deliver(db, job)
        if job.status != "done":
            # 400 — 5xx면 앞단 nginx가 자기 오류 화면으로 바꿈
            raise HTTPException(status.HTTP_400_BAD_REQUEST, job.message or "보내지 못했습니다.")
    return {"job": mail_jobs.job_out(job), **_out(db, user, r)}


def _require_job(db: Session, user: User, jid: int) -> MailJob:
    j = db.get(MailJob, jid)
    if j is None or j.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "메일 기록이 없습니다.")
    return j


@router.delete("/mail-jobs/{jid}")
def cancel(jid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = _require_job(db, user, jid)
    if j.status != "queued":
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 보냈거나 끝난 메일은 취소할 수 없습니다.")
    j.status, j.message = "cancelled", f"예약 취소 — {user.display_name or ''}"
    db.commit()
    return mail_jobs.job_out(j)


@router.post("/mail-jobs/{jid}/revoke")
def revoke(jid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = _require_job(db, user, jid)
    if not j.token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "내려받기 링크가 없는 메일입니다.")
    now = datetime.datetime.now()
    if not j.expires_at or j.expires_at > now:
        j.expires_at = now
        j.message = (j.message + " · " if j.message else "") + f"링크 끊음 — {user.display_name or ''}"
        db.commit()
    return mail_jobs.job_out(j)
