"""보고서 메일 보내기(2026-10-25 사용자·민재형 "시특법에 메일 기능 + 산안법에도 예약", 방식 = 내려받기 링크 "1번이지 당연히").

- 시특법(kind=sitok): 합본 PDF가 커서(양주덕산초 96MB — 네이버 첨부 한도 약 10MB) 첨부하지 않고 내려받기 링크를 보냄.
  링크 = PUBLIC_BASE_URL/share/{token}(로그인 없이 — 그룹웨어 nginx `/report/share/`만 로그인 확인을 건너뜀, server/api/routers/share.py),
  기한 SHARE_DAYS일. 링크는 보낼 때가 아니라 열 때의 합본을 줌(보낸 뒤 고쳐 다시 만들면 새 것). 보내면 제출 현황 "전송"을 표시(묶인 동 같이).
- 산안법(kind=sanan): 고객사 전송 예약 — 보낼 때 PDF를 다시 확인(수정 전 버전·만드는 중이면 안 보냄)하고 첨부, report_mail 기록도 남김.
- 바로 보내기는 API가 deliver()를 바로 부르고, 예약은 작업 프로그램(server/worker/mail_worker.py)이 시각이 지나면 부름.
  메일 서버 연결 실패 같은 것은 예약이면 30분 뒤 한 번 더(MAX_TRIES), PDF 문제(Skip)는 다시 안 함.
"""
from __future__ import annotations

import datetime
import secrets
from pathlib import Path

from sqlalchemy.orm import Session

from core.models_web import MailJob, ReportMail, SitokReport
from server import settings as app_settings
from server.api import mailer

SHARE_DAYS = 30
RETRY_MINUTES = 30
MAX_TRIES = 2  # 처음 + 한 번 더


class Skip(Exception):
    """다시 해도 안 되는 실패(회차 없음·PDF 없음·수정 전 버전 등) — 한 번 더 안 함."""


def share_url(token: str) -> str:
    return f"{app_settings.PUBLIC_BASE_URL}/share/{token}"


def size_text(n: int) -> str:
    return f"{n / 1024 / 1024:.1f}MB" if n >= 1024 * 1024 else f"{max(1, round(n / 1024))}KB"


def split_addrs(value: str) -> list[str]:
    return [a.strip() for a in (value or "").split(",") if a.strip()]


# ---------- 시특법 ----------
def sitok_pdf(r: SitokReport) -> Path | None:
    p = Path(r.out_pdf) if r.out_pdf else None
    return p if p is not None and p.exists() else None


def sitok_problem(r: SitokReport) -> str:
    """지금 보낼 수 없는 이유(없으면 "")."""
    if r.status == "running":
        return "보고서를 만드는 중입니다 — 다 만든 뒤 보내세요."
    if sitok_pdf(r) is None:
        return "아직 합본 PDF가 없습니다 — 보고서를 만든 뒤 보내세요."
    return ""


def sitok_title(r: SitokReport) -> str:
    """합본 파일 이름 "2026년 하반기 정기안전점검 보고서_양주덕산초등학교" → "양주덕산초등학교 2026년 하반기 정기안전점검 보고서"."""
    p = sitok_pdf(r) or (Path(r.out_pdf) if r.out_pdf else None)
    stem = p.stem.removesuffix("_합본") if p is not None else f"{r.year}년 {r.half} {r.kind or '정기'}안전점검 보고서"
    head, _, tail = stem.partition("_")
    return f"{tail} {head}" if tail else stem


def sitok_subject(r: SitokReport) -> str:
    return f"[{app_settings.MAIL_FROM_NAME}] {sitok_title(r)}"


def sitok_body(title: str, url: str, size: int, expires: datetime.datetime, note: str) -> str:
    lines = [
        f"안녕하세요. {app_settings.MAIL_FROM_NAME}입니다.",
        "",
        f"{title}를 보내드립니다.",
        f"보고서 PDF({size_text(size)})는 용량이 커서 메일에 첨부하지 않고, 아래 링크에서 내려받으실 수 있게 했습니다.",
        "",
        "▶ 보고서 내려받기",
        url,
        "",
        f"링크는 {expires.year}년 {expires.month}월 {expires.day}일까지 열립니다. 그 뒤에 필요하시면 이 메일로 회신해 주세요.",
    ]
    if note.strip():
        lines += ["", note.strip()]
    lines += ["", f"{app_settings.MAIL_FROM_NAME} 드림"]
    return "\n".join(lines)


def mark_sent(db: Session, r: SitokReport, job: MailJob) -> None:
    """제출 현황 "전송"(sitok_report.submit["mail"]) — 묶인 동 같이. 이미 표시(직접·먼저 보낸 것)가 있으면 그대로."""
    from server.api.routers.sitok_status import _unit_reports

    for x in _unit_reports(db, r):
        sub = dict(x.submit or {})
        if not sub.get("mail"):
            sub["mail"] = {"at": datetime.date.today().isoformat(), "by": job.created_by or "", "job": job.id}
            x.submit = sub


def _send_sitok(db: Session, job: MailJob) -> list[str]:
    r = db.get(SitokReport, job.report_id)
    if r is None or r.company_id != job.company_id:
        raise Skip("회차가 지워졌습니다.")
    problem = sitok_problem(r)
    if problem:
        raise Skip(problem)
    pdf = sitok_pdf(r)
    now = datetime.datetime.now()
    if not job.token:
        job.token = secrets.token_urlsafe(24)
    job.expires_at = now + datetime.timedelta(days=SHARE_DAYS)
    db.commit()  # 메일이 닿자마자 눌러도 링크가 열리게 먼저 저장
    body = sitok_body(sitok_title(r), share_url(job.token), pdf.stat().st_size, job.expires_at, job.note or "")
    refused = mailer.send_mail(split_addrs(job.to_addr), job.cc_addr, job.subject or sitok_subject(r), body)
    mark_sent(db, r, job)
    return refused


# ---------- 산안법(고객사 전송 예약) ----------
def _send_sanan(db: Session, job: MailJob) -> list[str]:
    from server.api import repo
    from server.api.routers.report_mail import _pdf_problem
    from server.api.routers.report_manage import download_name

    report = repo.get_report(db, job.company_id, job.report_id)
    if report is None:
        raise Skip("보고서가 지워졌습니다.")
    problem = _pdf_problem(db, report)
    if problem:
        raise Skip(problem)
    site_name = report.site.name if report.site else ""
    refused = mailer.send_pdf(
        split_addrs(job.to_addr), job.cc_addr,
        job.subject or mailer.mail_subject(site_name, report.visit_no), mailer.mail_body(site_name, report.visit_no),
        Path(report.pdf_path), download_name(report, ".pdf"),
    )
    db.add(ReportMail(report_id=report.id, sent_at=datetime.datetime.now(), to_addr=job.to_addr, cc_addr=job.cc_addr,
                      sent_by=job.created_by or ""))
    return refused


def deliver(db: Session, job: MailJob) -> None:
    """메일 한 통 보내고 결과를 job에 적어 commit — status done | failed | queued(예약이 메일 서버 문제로 실패 → 30분 뒤 한 번 더)."""
    job.tries = (job.tries or 0) + 1
    now = datetime.datetime.now()
    try:
        if job.kind == "sitok":
            refused = _send_sitok(db, job)
        elif job.kind == "sanan":
            refused = _send_sanan(db, job)
        else:
            raise Skip("알 수 없는 메일입니다.")
    except Skip as e:
        job.status, job.message = "failed", str(e)
    except mailer.MailError as e:
        if job.run_at is not None and job.tries < MAX_TRIES:
            nxt = now + datetime.timedelta(minutes=RETRY_MINUTES)
            job.status, job.run_at, job.message = "queued", nxt, f"{e} — {nxt:%H:%M}에 한 번 더 보냅니다."
        else:
            job.status, job.message = "failed", str(e)
    else:
        job.status, job.sent_at = "done", datetime.datetime.now()
        job.message = f"메일 서버가 받지 않은 주소: {', '.join(refused)}" if refused else ""
    db.commit()


def job_out(j: MailJob) -> dict:
    now = datetime.datetime.now()
    fmt = lambda d: d.strftime("%Y-%m-%d %H:%M") if d else ""  # noqa: E731
    return {
        "id": j.id, "kind": j.kind, "status": j.status, "to": j.to_addr, "cc": j.cc_addr, "subject": j.subject, "note": j.note,
        "run_at": fmt(j.run_at), "sent_at": fmt(j.sent_at), "created_at": fmt(j.created_at), "created_by": j.created_by,
        "message": j.message, "tries": j.tries or 0,
        "url": share_url(j.token) if j.token and j.status == "done" else "",
        "expires_at": fmt(j.expires_at), "expired": bool(j.expires_at and j.expires_at <= now),
        "downloads": j.downloads or 0, "last_download_at": fmt(j.last_download_at),
    }


def parse_run_at(value: str | None) -> datetime.datetime | None:
    """예약 시각 "2026-11-20T09:00" — 비면 None(바로). 지난 시각이면 ValueError."""
    if not value:
        return None
    at = datetime.datetime.fromisoformat(value)
    if at <= datetime.datetime.now():
        raise ValueError("예약 시각이 이미 지났습니다 — 앞으로의 날짜·시각을 고르거나 [지금 보내기]를 쓰세요.")
    return at
