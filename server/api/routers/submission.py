"""제출 현황(탭 "제출 현황", status.html) + 지도 기한(맨 위 배너) + "직접 제출함" 표시.

- GET  /submission/overview?year=&month=&staff_id= — 그달(지도일 기준, 지도일이 없으면 만든 날) 보고서와 상태, 숫자 칸,
  그해 월별 제출/미제출, 요원별 현황, 임박·초과 현장. 상태 판정은 server/api/submission.py, 기한은 server/api/deadlines.py.
- GET  /submission/deadlines — 임박·초과 현장만(모든 탭 맨 위 배너용, 가벼움).
- POST/DELETE /reports/{id}/submit-mark — "직접 제출함" 표시/되돌리기(PDF를 만든 보고서만). 보고서 수정이 아니므로 edit_tracking에서 제외.
"""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core import config
from core.models_db import Report, Site, Staff
from core.models_web import ReportSubmitMark, User
from server.api import repo
from server.api.deadlines import site_deadlines
from server.api.deps import get_current_user, get_db
from server.api.submission import report_states

router = APIRouter(tags=["submission"])


def _effective_date(report) -> datetime.date:
    return report.guidance_date or report.created_at.date()


def _company_reports(db: Session, company_id: int, staff_id: int | None):
    q = db.query(Report).join(Site, Site.id == Report.site_id).filter(Site.company_id == company_id)
    if staff_id:
        q = q.filter(Report.assigned_staff_id == staff_id)
    return q.all()


@router.get("/submission/deadlines")
def deadlines(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = [d for d in site_deadlines(db, user.company_id) if d.stage != "ok"]
    return {
        "imminent_days": config.get_deadline_imminent_days(user.company_id),
        "imminent": sum(d.stage == "imminent" for d in items),
        "over": sum(d.stage == "over" for d in items),
        "items": [d.to_dict() for d in items],
    }


@router.get("/submission/overview")
def overview(
    year: int, month: int, staff_id: int | None = None,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    if not 1 <= month <= 12:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "월을 확인하세요.")
    reports = [r for r in _company_reports(db, user.company_id, staff_id) if _effective_date(r).year == year]
    states = report_states(db, reports)

    # 그해 월별 — 제출 완료 / 미제출(나머지 전부)
    months = [{"month": m, "submitted": 0, "pending": 0} for m in range(1, 13)]
    for r in reports:
        key = "submitted" if states[r.id]["state"] == "submitted" else "pending"
        months[_effective_date(r).month - 1][key] += 1

    in_month = [r for r in reports if _effective_date(r).month == month]
    sites = {s.id: s for s in db.query(Site).filter(Site.id.in_({r.site_id for r in in_month}))} if in_month else {}
    staff_names = dict(db.query(Staff.id, Staff.name).filter(Staff.company_id == user.company_id))
    rows = []
    for r in in_month:
        site = sites.get(r.site_id)
        rows.append({
            "id": r.id, "site_id": r.site_id, "site_name": site.name if site else "", "hq_company": site.hq_company if site else "",
            "visit_no": r.visit_no, "date": _effective_date(r).isoformat(), "has_guidance_date": r.guidance_date is not None,
            "staff_id": r.assigned_staff_id, "staff_name": staff_names.get(r.assigned_staff_id, ""),
            **states[r.id],
        })

    # 지도일 최근 순 → 같은 날이면 현장 이름 순 → 회차 큰 순(같은 현장끼리 모이게)
    rows.sort(key=lambda x: (-datetime.date.fromisoformat(x["date"]).toordinal(), x["site_name"], -x["visit_no"]))

    dl = [d for d in site_deadlines(db, user.company_id) if d.stage != "ok" and (not staff_id or d.staff_id == staff_id)]
    count = {s: sum(1 for x in rows if x["state"] == s) for s in ("writing", "outdated", "pdf_ready", "submitted")}
    cards = {
        "total": len(rows), **count,
        "submitted_mail": sum(1 for x in rows if x["state"] == "submitted" and x["submitted_via"] == "mail"),
        "submitted_manual": sum(1 for x in rows if x["state"] == "submitted" and x["submitted_via"] == "manual"),
        "imminent": sum(d.stage == "imminent" for d in dl), "over": sum(d.stage == "over" for d in dl),
    }

    # 요원별 그달 — 제출/전체, 임박·초과 현장 수
    by_staff: dict = {}

    def staff_entry(sid, name):
        return by_staff.setdefault(sid or 0, {"id": sid, "name": name or "미지정", "total": 0, "submitted": 0, "imminent": 0, "over": 0})

    for x in rows:
        e = staff_entry(x["staff_id"], x["staff_name"])
        e["total"] += 1
        e["submitted"] += x["state"] == "submitted"
    for d in dl:
        staff_entry(d.staff_id, d.staff_name)[d.stage] += 1
    return {
        "year": year, "month": month, "imminent_days": config.get_deadline_imminent_days(user.company_id),
        "cards": cards, "months": months, "staff": sorted(by_staff.values(), key=lambda e: (e["id"] is None, e["name"])),
        "deadlines": [d.to_dict() for d in dl], "reports": rows,
    }


def _require_report(db: Session, user: User, report_id: int):
    report = repo.get_report(db, user.company_id, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    return report


@router.post("/reports/{report_id}/submit-mark")
def mark_submitted(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report = _require_report(db, user, report_id)
    if report.status != "final":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "PDF를 만든 보고서만 제출 완료로 표시할 수 있습니다.")
    mark = db.get(ReportSubmitMark, report_id) or ReportSubmitMark(report_id=report_id)
    mark.marked_at = datetime.datetime.now()
    mark.marked_by = user.display_name or ""
    db.add(mark)
    db.commit()
    return {"ok": True}


@router.delete("/reports/{report_id}/submit-mark")
def unmark_submitted(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_report(db, user, report_id)
    db.query(ReportSubmitMark).filter(ReportSubmitMark.report_id == report_id).delete()
    db.commit()
    return {"ok": True}
