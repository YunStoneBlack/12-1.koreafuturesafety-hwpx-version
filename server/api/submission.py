"""보고서 제출 상태 판정 — **"제출 완료" 기준은 여기 한 곳에서만 정한다.**

지금 기준(사용자 결정 2026-09-29, "일단 3번 — 나중에 방식을 바꿀 것"):
  제출 완료 = 고객사 전송(report_mail) 성공 **또는** "직접 제출함" 표시(report_submit_mark).
나중에 기준을 바꿀 땐 `report_state()`만 고치면 제출 현황 화면·숫자 칸·월별 막대·요원별 현황이 같이 바뀐다.

상태: writing(작성 중 — PDF 안 만듦) / outdated(PDF 수정 전 버전) / pdf_ready(PDF 완료·미제출) / submitted(제출 완료).
제출 뒤 보고서를 고쳤으면(마지막 수정 > 제출 시각) submitted 그대로 + modified_after=True("⚠ 제출 뒤 수정됨" — 다시 보낼지 판단).
"""

from __future__ import annotations

import datetime

from sqlalchemy.orm import Session

from core.models_web import ReportEdit, ReportMail, ReportSubmitMark
from server.api import repo
from server.api.routers.reports import pdf_outdated_map

STATES = ("writing", "outdated", "pdf_ready", "submitted")


def report_state(report, outdated: bool, last_mail: ReportMail | None, mark: ReportSubmitMark | None,
                 edited_at: datetime.datetime | None) -> dict:
    submitted_at = None
    via = ""
    by = ""
    to_count = 0
    if last_mail is not None:
        submitted_at, via, by = last_mail.sent_at, "mail", last_mail.sent_by
        to_count = len([a for a in last_mail.to_addr.split(",") if a.strip()])
    if mark is not None and (submitted_at is None or mark.marked_at > submitted_at):
        submitted_at, via, by, to_count = mark.marked_at, "manual", mark.marked_by, 0
    if submitted_at is not None:
        state = "submitted"
    elif report.status != "final":
        state = "writing"
    elif outdated:
        state = "outdated"
    else:
        state = "pdf_ready"
    return {
        "state": state,
        "submitted_via": via,  # mail | manual | ""
        "submitted_at": submitted_at.strftime("%Y-%m-%d %H:%M") if submitted_at else "",
        "submitted_by": by,
        "to_count": to_count,
        "modified_after": bool(submitted_at and edited_at and edited_at > submitted_at),
        "has_mark": mark is not None,
    }


def report_states(db: Session, reports) -> dict[int, dict]:
    """{보고서 id: report_state(...)} — 여러 보고서를 한 번에(질의 4번)."""
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
    return {r.id: report_state(r, outdated[r.id], last_mail.get(r.id), marks.get(r.id), edited.get(r.id)) for r in reports}
