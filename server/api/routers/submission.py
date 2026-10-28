"""제출 현황(탭 "제출 현황", status.html) + "직접 제출함"·"K2B 직접 제출함" 표시.

- GET  /submission/overview?year=&month=&staff_id= — 그달(지도일 기준, 지도일이 없으면 만든 날) 보고서와 상태, 숫자 칸,
  그해 월별 제출/미제출, 요원별 현황, 현장별 그달 추진 현황(progress — 줄마다 지역 시·군), 전체 회차 부족 현장(shortage — 10/28). 상태 판정은 server/api/submission.py.
  (2026-10-01 "마지막 지도일 + 15일" 지도 기한·임박/초과·맨 위 배너는 없앰 — 실제 규칙이 아니었음. 진행은 진행 막대로 본다.)
- POST/DELETE /reports/{id}/submit-mark — "직접 제출함" 표시/되돌리기(PDF를 만든 보고서만). 보고서 수정이 아니므로 edit_tracking에서 제외.
- POST/DELETE /reports/{id}/k2b-mark — "K2B 직접 제출함" 표시/되돌리기(2026-10-10, K2B 사이트에 직접 넣은 보고서). 같은 조건·같은 이유로 제외.
"""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.models_db import Report, Site, Staff
from core.models_web import ReportK2bMark, ReportSubmitMark, User, VisitPlan
from server.api import repo
from server.api.deps import get_current_user, get_db
from server.api.submission import STATES, report_states
from server.api.site_label import site_label

router = APIRouter(tags=["submission"])


def _effective_date(report) -> datetime.date:
    return report.guidance_date or report.created_at.date()


def _company_reports(db: Session, company_id: int, staff_id: int | None):
    q = db.query(Report).join(Site, Site.id == Report.site_id).filter(Site.company_id == company_id)
    if staff_id:
        q = q.filter(Report.assigned_staff_id == staff_id)
    return q.all()


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
            "id": r.id, "site_id": r.site_id, "site_name": site_label(site) if site else "", "hq_company": site.hq_company if site else "",
            "visit_no": r.visit_no, "date": _effective_date(r).isoformat(), "has_guidance_date": r.guidance_date is not None,
            "staff_id": r.assigned_staff_id, "staff_name": staff_names.get(r.assigned_staff_id, ""),
            **states[r.id],
        })

    # 지도일 최근 순 → 같은 날이면 현장 이름 순 → 회차 큰 순(같은 현장끼리 모이게)
    rows.sort(key=lambda x: (-datetime.date.fromisoformat(x["date"]).toordinal(), x["site_name"], -x["visit_no"]))

    count = {s: sum(1 for x in rows if x["state"] == s) for s in STATES}
    cards = {
        "total": len(rows), **count,
        "submitted_mail": sum(1 for x in rows if x["state"] == "submitted" and x["submitted_via"] == "mail"),
        "submitted_manual": sum(1 for x in rows if x["state"] == "submitted" and x["submitted_via"] == "manual"),
        "k2b_done": sum(1 for x in rows if x["k2b_via"]),
    }

    # 요원별 그달 — 제출/전체
    by_staff: dict = {}

    def staff_entry(sid, name):
        return by_staff.setdefault(sid or 0, {"id": sid, "name": name or "미지정", "total": 0, "submitted": 0})

    for x in rows:
        e = staff_entry(x["staff_id"], x["staff_name"])
        e["total"] += 1
        e["submitted"] += x["state"] == "submitted"
    return {
        "year": year, "month": month,
        "cards": cards, "months": months, "staff": sorted(by_staff.values(), key=lambda e: (e["id"] is None, e["name"])),
        "reports": rows, "progress": _site_progress(db, user.company_id, year, month, staff_id, rows, sites),
        **dict(zip(("shortage", "ending"), _site_shortage(db, user.company_id, staff_id))),
    }


def _site_progress(db: Session, company_id: int, year: int, month: int, staff_id: int | None, rows: list[dict], sites: dict) -> list[dict]:
    """현장별 그달 추진 현황(10/27 사용자) — 배정 = 방문 달력 그달 예정 수와 그달 보고서 수 중 큰 쪽(달력을 안 쓴 현장은 보고서 수,
    예정보다 더 다녀왔으면 보고서 수), 보고서 = 그달 지도일 보고서 수, 제출 = 그중 제출 완료. 요원을 고르면 그 사람 예정(보고서 담당, 없으면 출장자)·보고서만.
    덜 끝난 현장이 위로(보고서/배정 작은 순)."""
    import calendar
    import collections

    from server.api.routers.calendar import short_region

    first = datetime.date(year, month, 1)
    last = datetime.date(year, month, calendar.monthrange(year, month)[1])
    plans = db.query(VisitPlan).filter(VisitPlan.company_id == company_id, VisitPlan.plan_date >= first, VisitPlan.plan_date <= last).all()
    planned = collections.Counter(p.site_id for p in plans if not staff_id or (p.report_staff_id or p.staff_id) == staff_id)
    done: dict = {}
    for x in rows:
        e = done.setdefault(x["site_id"], [0, 0])
        e[0] += 1
        e[1] += x["state"] == "submitted"
    ids = set(planned) | set(done)
    missing = ids - set(sites)
    if missing:
        sites = {**sites, **{s.id: s for s in db.query(Site).filter(Site.id.in_(missing))}}
    out = []
    for sid in ids:
        site = sites.get(sid)
        if site is None:
            continue
        reports, submitted = done.get(sid, (0, 0))
        out.append({"site_id": sid, "site_name": site_label(site), "region": short_region(site.address), "planned": planned.get(sid, 0),
                    "assigned": max(planned.get(sid, 0), reports), "reports": reports, "submitted": submitted})
    out.sort(key=lambda e: (e["reports"] / e["assigned"] if e["assigned"] else 1, e["submitted"] / e["assigned"] if e["assigned"] else 1, e["site_name"]))
    return out


ENDING_DAYS = 60  # ⏰ 계약 끝 임박 — 우리 계약기간 끝까지 이 날 수 안(10/28 사용자 4번)
ENDING_BUSY = 8.0  # 남은 기간 월 필요 횟수가 이만큼 넘으면(주 2회 넘게) 벅참


def _site_shortage(db: Session, company_id: int, staff_id: int | None) -> tuple[list[dict], list[dict]]:
    """전체 회차가 부족한 현장(10/28 사용자 "전체 회차가 많이 부족한 현장 보여주기") — 진행 중 현장마다 현장 목록 진행 막대와 같은 계산
    (server/api/site_pace_out.pace_dict — 우리 계약기간 경과율 × 총 횟수 = 지금쯤 했어야 할 회차, 다녀온 횟수 = done_counts)에서 모자란 곳만, 많이 모자란 순.
    요원을 고르면 그 현장 담당 요원 것만. 다음 예정·오늘 이후 예정 수(남은 횟수보다 적으면 방문 달력 [채워 넣기] 대상)·최근 지도일을 같이.
    둘째 = ⏰ 계약 끝 임박(10/28 사용자 4번) — 우리 계약기간 끝까지 ENDING_DAYS일 안(지났으면 포함)인데 남은 회차가 있고,
    오늘 이후 예정이 남은 회차보다 적거나 · 남은 기간 월 ENDING_BUSY회 넘게 필요하거나 · 계약기간이 이미 지난 현장(끝이 가까운 순). 부족이 아니어도 들어감."""
    from sqlalchemy import func

    from server.api import contract_sites
    from server.api.routers.calendar import short_region
    from server.api.site_pace_out import done_counts, pace_dict
    from server.api.site_status import is_active

    today = datetime.date.today()
    sites = [s for s in db.query(Site).filter(Site.company_id == company_id).all() if is_active(s) and (not staff_id or s.assigned_staff_id == staff_id)]
    if not sites:
        return [], []
    ids = [s.id for s in sites]
    done = done_counts(db, ids)
    periods = contract_sites.our_periods(db, sites)
    future: dict = {}
    for sid, d in db.query(VisitPlan.site_id, VisitPlan.plan_date).filter(VisitPlan.company_id == company_id, VisitPlan.site_id.in_(ids), VisitPlan.plan_date >= today):
        future.setdefault(sid, []).append(d)
    last = dict(db.query(Report.site_id, func.max(Report.guidance_date)).filter(Report.site_id.in_(ids)).group_by(Report.site_id))
    out, ending = [], []
    for s in sites:
        p = pace_dict(s, done.get(s.id), today, periods[s.id])
        fut = sorted(future.get(s.id) or [])
        left = max((p["total"] or 0) - p["performed"], 0)
        end = periods[s.id][1]
        days = (end - today).days if end else None
        if p["total"] and left and days is not None and days <= ENDING_DAYS:
            need = p.get("monthly_needed")
            why = [w for w, hit in (("over", days < 0), ("plan", len(fut) < left), ("busy", need is not None and need > ENDING_BUSY)) if hit]
            if why:
                ending.append({"site_id": s.id, "site_name": site_label(s), "region": short_region(s.address), "period_end": end.isoformat(), "days_left": days,
                               "left": left, "upcoming": len(fut), "monthly_needed": round(need, 1) if need is not None else None,
                               "performed": p["performed"], "total": p["total"], "diff": p["diff"] if p["status"] == "shortage" else 0, "why": why})
        if p["status"] != "shortage":
            continue
        out.append({"site_id": s.id, "site_name": site_label(s), "region": short_region(s.address), "performed": p["performed"], "total": p["total"],
                    "diff": p["diff"], "ideal": p["performed"] + p["diff"], "left": left,
                    "monthly_needed": round(p["monthly_needed"], 1) if p.get("monthly_needed") is not None else None,
                    "elapsed_months": p["elapsed_months"], "total_months": p["total_months"], "period_end": p["period_end"], "period_over": p["period_over"],
                    "upcoming": len(fut), "next_plan": fut[0].isoformat() if fut else None, "last_visit": last[s.id].isoformat() if last.get(s.id) else None})
    out.sort(key=lambda e: (-e["diff"], -(e["left"] - e["upcoming"]), e["site_name"]))
    ending.sort(key=lambda e: (e["days_left"], -(e["left"] - e["upcoming"]), e["site_name"]))
    return out, ending


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


@router.post("/reports/{report_id}/k2b-mark")
def mark_k2b(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report = _require_report(db, user, report_id)
    if report.status != "final":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "PDF를 만든 보고서만 K2B 제출로 표시할 수 있습니다.")
    mark = db.get(ReportK2bMark, report_id) or ReportK2bMark(report_id=report_id)
    mark.marked_at = datetime.datetime.now()
    mark.marked_by = user.display_name or ""
    db.add(mark)
    db.commit()
    return {"ok": True}


@router.delete("/reports/{report_id}/k2b-mark")
def unmark_k2b(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_report(db, user, report_id)
    db.query(ReportK2bMark).filter(ReportK2bMark.report_id == report_id).delete()
    db.commit()
    return {"ok": True}
