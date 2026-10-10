"""보고서 제출 상태 판정 — **"제출 완료" 기준은 여기 한 곳에서만 정한다.**

지금 기준(2026-10-10 사용자 "K2B까지 제출 완료 해야 제출완료로 해줘. 안돼있으면 표시해주고"):
  제출 완료 = [고객사 전송(report_mail) 성공 **또는** "직접 제출함" 표시(report_submit_mark)]
             **그리고** [K2B 제출 성공(k2b_submission done) **또는** "K2B 직접 제출함" 표시(report_k2b_mark)].
  (그 전 2026-09-29 기준은 앞 괄호만 — "일단 3번, 나중에 방식을 바꿀 것")
나중에 기준을 바꿀 땐 `report_state()`만 고치면 제출 현황 화면·숫자 칸·월별 막대·요원별 현황·방문 달력이 같이 바뀐다.

상태: writing(작성 중 — PDF 안 만듦) / outdated(PDF 수정 전 버전) / pdf_ready(PDF 완료·미전송) /
      k2b_missing(전송은 했는데 K2B가 안 됨) / submitted(제출 완료).
제출 뒤 보고서를 고쳤으면(마지막 수정 > 전송 시각) 상태 그대로 + modified_after=True("⚠ 제출 뒤 수정됨" — 다시 보낼지 판단).
"""

from __future__ import annotations

import datetime

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from core.models_web import K2bSubmission, ReportEdit, ReportK2bMark, ReportMail, ReportSubmitMark
from server.api import repo
from server.api.routers.reports import pdf_outdated_map

STATES = ("writing", "outdated", "pdf_ready", "k2b_missing", "submitted")


def report_state(report, outdated: bool, last_mail: ReportMail | None, mark: ReportSubmitMark | None,
                 edited_at: datetime.datetime | None, k2b_job: K2bSubmission | None = None,
                 k2b_mark: ReportK2bMark | None = None) -> dict:
    submitted_at = None
    via = ""
    by = ""
    to_count = 0
    if last_mail is not None:
        submitted_at, via, by = last_mail.sent_at, "mail", last_mail.sent_by
        to_count = len([a for a in last_mail.to_addr.split(",") if a.strip()])
    if mark is not None and (submitted_at is None or mark.marked_at > submitted_at):
        submitted_at, via, by, to_count = mark.marked_at, "manual", mark.marked_by, 0

    k2b_at = None
    k2b_via = ""
    k2b_by = ""
    k2b_round = None
    if k2b_job is not None:
        k2b_at, k2b_via, k2b_by, k2b_round = k2b_job.finished_at or k2b_job.created_at, "web", k2b_job.created_by, k2b_job.round_no
    if k2b_mark is not None and (k2b_at is None or k2b_mark.marked_at > k2b_at):
        k2b_at, k2b_via, k2b_by, k2b_round = k2b_mark.marked_at, "manual", k2b_mark.marked_by, None

    if submitted_at is not None:
        state = "submitted" if k2b_at is not None else "k2b_missing"
    elif report.status != "final":
        state = "writing"
    elif outdated:
        state = "outdated"
    else:
        state = "pdf_ready"
    return {
        "state": state,
        "submitted_via": via,  # mail | manual | "" — 고객사 쪽(전송)
        "submitted_at": submitted_at.strftime("%Y-%m-%d %H:%M") if submitted_at else "",
        "submitted_by": by,
        "to_count": to_count,
        "modified_after": bool(submitted_at and edited_at and edited_at > submitted_at),
        "has_mark": mark is not None,
        "k2b_via": k2b_via,  # web | manual | ""
        "k2b_at": k2b_at.strftime("%Y-%m-%d %H:%M") if k2b_at else "",
        "k2b_by": k2b_by,
        "k2b_round": k2b_round,
        "k2b_job_id": k2b_job.id if k2b_job is not None and k2b_via == "web" else None,
        "has_k2b_mark": k2b_mark is not None,
    }


_ready: set[str] = set()


def _table_ready(db: Session, name: str) -> bool:
    """alembic 0026을 아직 안 올린 DB에서도 화면이 죽지 않게(올리기 전엔 K2B 직접 제출 표시 없음으로 침). 있으면 기억해 둔다."""
    if name not in _ready and inspect(db.get_bind()).has_table(name):
        _ready.add(name)
    return name in _ready


def report_states(db: Session, reports) -> dict[int, dict]:
    """{보고서 id: report_state(...)} — 여러 보고서를 한 번에(질의 6번)."""
    ids = [r.id for r in reports]
    if not ids:
        return {}
    outdated = pdf_outdated_map(db, reports)
    last_mail: dict[int, ReportMail] = {}
    if repo.mail_table_ready(db):
        for m in db.query(ReportMail).filter(ReportMail.report_id.in_(ids)).order_by(ReportMail.sent_at):
            last_mail[m.report_id] = m
    marks = {m.report_id: m for m in db.query(ReportSubmitMark).filter(ReportSubmitMark.report_id.in_(ids))}
    edited = dict(db.query(ReportEdit.report_id, ReportEdit.edited_at).filter(ReportEdit.report_id.in_(ids)))
    k2b_jobs: dict[int, K2bSubmission] = {}  # 보고서마다 마지막 성공(K2B에 저장됨)
    for j in (db.query(K2bSubmission).filter(K2bSubmission.report_id.in_(ids), K2bSubmission.status == "done")
              .order_by(K2bSubmission.id)):
        k2b_jobs[j.report_id] = j
    k2b_marks = ({m.report_id: m for m in db.query(ReportK2bMark).filter(ReportK2bMark.report_id.in_(ids))}
                 if _table_ready(db, "report_k2b_mark") else {})
    return {r.id: report_state(r, outdated[r.id], last_mail.get(r.id), marks.get(r.id), edited.get(r.id),
                               k2b_jobs.get(r.id), k2b_marks.get(r.id)) for r in reports}
