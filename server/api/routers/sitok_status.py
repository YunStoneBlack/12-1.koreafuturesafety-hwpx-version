"""보고서 자동화 · 시특법 — 제출 현황(2026-10-15 민재형 문서번호 일치화 문서 "보고서 제출현황 관리").

산안법은 15일마다 보고서가 나가 달마다 봤지만 시특법은 상·하반기로 봄. 한 줄 = 그 반기 시설물 카드 하나(묶인 동은 한 줄),
칸 = 보고서(만듦) · 발주처 이메일 제출 · FMS 처리(자동 제출 기록 sitok_report.fms 또는 직접 처리함 · 해당없음) · 보고서 합본 출력 · 보고서 택배.
그 반기를 덮는 계약이 있는데 회차를 아직 안 만든 시설물도 "회차 없음"으로, 장기·지속은 계약이 없어도 줄로(계약 칸 "미계약", 10/19) 보여 줌. 표시는 sitok_report.submit(0048) — 묶인 동은 같이.

- `GET /sitok/status/reports?year=&half=` — 줄 목록
- `POST /sitok/status/reports/{report_id}/mark` {item: field|report|mail|fms|print|parcel, action: done|na|clear, date?} — 표시(na = FMS 해당없음만)
  field = 현장점검일, report = 보고서를 그룹웨어 밖에서 작성 완료(10/16 민재형 — 그룹웨어 쓰기 전·토목 등 밖에서 쓴 보고서). 현장점검 = 현장 조사 [✓ 조사 완료](sitok_steps.py)와 같은 기록(동마다 완료도 같이), 방문 달력 그 반기 칸을 채움(10/18 — 전엔 뺐음), 앞날 = 예정(일정을 그날로, 10/19), 밖에서 완료 = 일정 그대로(10/19 — 달력이 색으로).
- `POST /sitok/status/facilities/{facility_id}/mark` {year, half, item, action, date?} — 회차가 아직 없는 줄(현장점검·밖에서 완료만) — 회차를 만들어 표시
- `GET /sitok/status/docs?year=&half=` — 서류 자동화 제출 현황(관급 착수계·완수계, 민간 계약서, 계산서 발행일)
- `POST /sitok/status/docs/{cid}/mark` {item: start|done|invoice, action: done|clear, date?, key?} — 직접 제출함·계산서 발행일
"""
from __future__ import annotations

import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokContract, SitokDocContract, SitokFacility, SitokGroup, SitokReport, SitokVisit, User
from server.api.deps import get_current_user, get_db
from server.sitok import seasons, steps
from server.sitok.visit_plan import fill_quietly, tell_apart, visit_span

router = APIRouter(prefix="/sitok/status", tags=["sitok-status"])
ITEMS = ("field", "report", "mail", "fms", "print", "parcel")
VISIT_ITEMS = ("field", "report")  # 표시하면 자동 일정을 안 잡음(이미 다녀옴·밖에서 끝남) — 달력 칸은 visits_after_mark
HALVES = ("상반기", "하반기")


def current_half(today: datetime.date | None = None) -> tuple[int, str]:
    t = today or datetime.date.today()
    return t.year, "상반기" if t.month <= 6 else "하반기"


def report_state(r: SitokReport | None) -> dict:
    """보고서 칸 — none(회차 없음) / writing(작성 중) / running(만드는 중) / failed / done(합본 PDF 있음)."""
    if r is None:
        return {"state": "none", "at": ""}
    if r.status == "running":
        return {"state": "running", "at": ""}
    if r.status == "failed":
        return {"state": "failed", "at": ""}
    if r.status == "done" and r.out_pdf and Path(r.out_pdf).exists():
        return {"state": "done", "at": r.made_at.strftime("%m/%d") if r.made_at else ""}
    mk = (r.submit or {}).get("report")
    if mk:  # 그룹웨어 밖에서 작성 완료(10/16)
        return {"state": "done", "at": (mk.get("at") or "")[5:10].replace("-", "/"), "outside": True, "at_iso": mk.get("at") or ""}
    return {"state": "writing", "at": ""}


def fms_state(r: SitokReport | None) -> dict:
    """FMS 칸 — 자동 제출 기록(실적 = 끝, 계약만 = 반쯤) + 직접 표시(처리함·해당없음). done = 끝난 것으로 셈."""
    st = (r.fms or {}) if r is not None else {}
    mark = ((r.submit or {}).get("fms") if r is not None else None) or None
    res, con = st.get("result") or {}, st.get("contract") or {}
    auto = "done" if res.get("status") == "done" else "contract" if con.get("status") == "done" else ""
    at = (res.get("at") if auto == "done" else con.get("at") if auto else "") or ""
    return {"auto": auto, "auto_at": at[5:10].replace("-", "/") if at else "", "mark": mark,
            "done": auto == "done" or bool(mark)}


def _day(text: str | None, default: datetime.date | None) -> datetime.date | None:
    """표시 창 날짜("2026-10-19") — 비면 default, 틀리면 400."""
    try:
        return datetime.date.fromisoformat(text) if text else default
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "날짜가 맞지 않습니다.") from err


def _no_start(c, year: int, half: str, halves: str = "") -> bool:
    """시작일이 빈 계약(관급-24 "2026년 … 연간", 끝 12/31) — 끝나는 해가 이 해이고 끝이 이 반기 시작 이후면 덮는 것으로(반기 지정 계약은 그 반기만)."""
    from server.api.routers.sitok import half_range

    if c.start_date is not None or c.end_date is None:
        return False
    if halves in HALVES and halves != seasons.bucket(half):
        return False
    return c.end_date.year == year and c.end_date >= half_range(year, half)[0]


def _began(c) -> datetime.date | None:
    """계약 시작 — 시작일 없는 계약(관급 일부·민간-15)은 끝나는 날이 든 반기 첫날."""
    from server.api.routers.sitok import half_range

    if c.start_date is not None or c.end_date is None:
        return c.start_date
    return half_range(*current_half(c.end_date))[0]


def _contracts(db: Session, company_id: int, year: int, half: str, units: dict) -> tuple[list[set], dict]:
    """계약 칸 재료(10/19 형) — (이 반기 계약 중 계약서가 있는 것(민간 만듦·날인본, 관급 나라장터 계약서)이 맡는 건물 묶음들,
    묶음 단위 → 첫 계약 시작(그 전 반기엔 "미계약" 줄을 안 만듦 — 아직 거래 전))."""
    from server.api.routers.sitok_compose import _overlaps
    from server.api.routers.sitok_docs import covered_ids

    docs = db.query(SitokDocContract).filter(SitokDocContract.company_id == company_id).all()
    signed = [set(covered_ids(c)) for c in docs
              if (c.contract_pdf or c.made_at) and (_overlaps(c, year, half) or (not c.rounds and _no_start(c, year, half)))]
    began: dict = {}  # 시설물 → 첫 계약 시작
    for c in db.query(SitokContract).filter(SitokContract.company_id == company_id):
        if (d := _began(c)) is not None:
            began[c.facility_id] = min(began.get(c.facility_id, d), d)
    for c in docs:
        if (d := _began(c)) is not None:
            for fid in covered_ids(c):
                began[fid] = min(began.get(fid, d), d)
    return signed, {key: min((began[m.id] for m in members if m.id in began), default=None) for key, members in units.items()}


class MarkIn(BaseModel):
    item: str
    action: str = "done"  # done | na(FMS 해당없음) | clear
    date: str | None = None


def _unit_reports(db: Session, r: SitokReport) -> list[SitokReport]:
    """묶인 동이면 같은 반기 회차 전부(표시를 같이), 아니면 그 회차 하나."""
    f = db.get(SitokFacility, r.facility_id)
    if f is None or not f.group_id:
        return [r]
    ids = [m.id for m in db.query(SitokFacility).filter(SitokFacility.group_id == f.group_id)]
    return db.query(SitokReport).filter(SitokReport.facility_id.in_(ids), SitokReport.year == r.year, SitokReport.half == r.half).all() or [r]


@router.get("/reports")
def list_rows(year: int | None = None, half: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from server.api.routers.sitok import contract_for, covers, half_range

    y0, h0 = current_half()
    year, half = year or y0, half if half in HALVES else h0
    facs = db.query(SitokFacility).filter(SitokFacility.company_id == user.company_id, SitokFacility.survey_only.is_(False)).order_by(SitokFacility.group_order, SitokFacility.id).all()
    reps_by: dict[int, dict[str, SitokReport]] = {}  # 시설물 → {시기: 회차} — 연 3회(해빙기·우기·동절기)는 반기 칸 안에서 시기마다(10/16)
    for x in db.query(SitokReport).filter(SitokReport.company_id == user.company_id, SitokReport.year == year,
                                          SitokReport.half.in_(seasons.in_bucket(half))).order_by(SitokReport.id):
        reps_by.setdefault(x.facility_id, {}).setdefault(x.half, x)
    docs = {}
    for d in db.query(SitokDocContract).filter(SitokDocContract.company_id == user.company_id, SitokDocContract.facility_id.isnot(None)).order_by(SitokDocContract.id):
        docs[d.facility_id] = d
    visits: dict = {}  # (시설물, 시기) → 방문 달력 일정(시작, 끝) — 현장점검 칸에 날짜(10/19 민재형 "현장점검 날짜 표기")
    for v in db.query(SitokVisit).filter(SitokVisit.company_id == user.company_id, SitokVisit.year == year,
                                         SitokVisit.half.in_(seasons.in_bucket(half))).order_by(SitokVisit.plan_date, SitokVisit.id):
        visits.setdefault((v.facility_id, v.half), visit_span(v))
    units: dict = {}
    for f in facs:
        units.setdefault(("g", f.group_id) if f.group_id else ("f", f.id), []).append(f)
    signed, first_start = _contracts(db, user.company_id, year, half, units)
    h_end = half_range(year, half)[1]
    rows = []
    names = {}
    for key, members in units.items():
        g = db.get(SitokGroup, key[1]) if key[0] == "g" and len(members) > 1 else None
        names[key] = (g.name if g else "") or members[0].name
    # 같은 현장에 이름이 같은 묶음이 여럿이면 건물 이름을 붙임(10/19 뒷번호 없앰)
    names = dict(zip(names, tell_apart([(units[k][0], units[k], nm) for k, nm in names.items()])))
    for key, members in units.items():
        lead = members[0]
        name = names[key]
        doc = next((docs[m.id] for m in members if m.id in docs), None)
        for hh in sorted({h for m in members for h in reps_by.get(m.id, {})}, key=seasons.order) or [half]:  # 연 3회면 시기마다 한 줄
            mr = [reps_by[m.id][hh] for m in members if hh in reps_by.get(m.id, {})]
            r = mr[0] if mr else None
            # 이 반기 회차가 없으면: 종료는 빼고, 1회성·입찰은 이 반기 계약이 있을 때만, 장기·지속은 계약이 없어도 줄로(계약 칸 "미계약" —
            # 10/19 형 "시설물 목록 95개소인데 제출 현황 91개소" → 하반기 계약을 아직 안 받은 장기 4곳이 빠졌던 것)
            if r is None and (lead.contract_type == "종료" or (contract_for(db, lead, year, half) is None
                                                             and (lead.contract_type != "장기" or first_start.get(key) is None or first_start[key] > h_end))):
                continue  # 이 반기 계약도 회차도 없음
            sub = (r.submit or {}) if r is not None else {}
            states = [report_state(x) for x in mr] or [report_state(None)]
            rep = next((s for s in states if s["state"] != "done"), states[0])  # 묶음은 한 동이라도 안 끝나면 안 끝남
            vis = next((visits[(m.id, hh)] for m in members if (m.id, hh) in visits), None)  # 이 시기 방문 일정(대표 동에 잡힘)
            ids = {m.id for m in members}
            rc = db.get(SitokContract, r.contract_id) if r is not None and r.contract_id else None
            # 계약서 있으면 완료, 없으면 미계약 — 이 반기를 맡는 계약만(10/19 형 "해당 반기에 계약서 없으면 미계약": 상반기에 끝난 계약이 하반기 회차에 붙어 있던 것)
            has_con = any(ids & c for c in signed) or bool(rc and rc.contract_pdf and (covers(rc, year, half) or _no_start(rc, year, half, rc.halves)))
            rows.append({
                "facility": {"id": lead.id, "mgmt_no": lead.mgmt_no, "name": name, "sector": lead.sector or "민간", "badge_field": lead.badge_field or "",
                             "badge_kind": lead.badge_kind or "", "contract_type": lead.contract_type, "members": [{"id": m.id, "name": m.name} for m in members]},
                "report_id": r.id if r is not None else None, "report_ids": [x.id for x in mr], "kind": r.kind if r is not None else "",
                "season": hh if seasons.is_season(hh) else "",
                "visit": {"start": vis[0].isoformat(), "end": vis[1].isoformat()} if vis else None,
                "contract": has_con,
                "report": rep, "field": sub.get("field"), "mail": sub.get("mail"), "fms": fms_state(r), "print": sub.get("print"), "parcel": sub.get("parcel"),
                "email": (doc.site_email or doc.client_email) if doc is not None else "",
            })
    return {"year": year, "half": half, "rows": rows}


@router.post("/reports/{report_id}/mark")
def mark(report_id: int, body: MarkIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = db.get(SitokReport, report_id)
    if r is None or r.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "회차를 찾을 수 없습니다.")
    if body.item not in ITEMS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "표시할 칸이 아닙니다.")
    if body.action not in ("done", "na", "clear") or (body.action == "na" and body.item != "fms"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "해당없음은 FMS 칸만 됩니다.")
    day = _day(body.date, datetime.date.today())
    reps = _unit_reports(db, r)
    if body.item == "field" and body.action == "done" and day > datetime.date.today():  # 앞날 = 예정(10/19 민재형 "날짜가 미래면 당연히 안함, 지난 거 넣은 건 완료")
        for x in reps:
            x.submit = {k: v for k, v in (x.submit or {}).items() if k != "field"}
            steps.put(x, "field", None)
        db.commit()
        schedule_visit(db, user, [x.facility_id for x in reps], r.year, r.half, r.kind or "정기", day)
        return {"ok": True, "item": body.item, "value": None, "planned": day.isoformat()}
    value = None if body.action == "clear" else {"na": True, "by": user.display_name or ""} if body.action == "na" else {"at": day.isoformat(), "by": user.display_name or ""}
    for x in reps:
        sub = dict(x.submit or {})
        if value is None:
            sub.pop(body.item, None)
        else:
            sub[body.item] = value
        x.submit = sub
        if body.item == "field":  # 현장 조사 화면 [✓ 조사 완료](sitok_steps.py)와 같은 일 — 동마다 완료도 같이(10/18)
            steps.put(x, "field", None if value is None else (steps.get(x, "field") or value))
    db.commit()
    if body.item in VISIT_ITEMS:
        visits_after_mark(db, user, reps, value is not None, body.item, day)
    return {"ok": True, "item": body.item, "value": value}


def visits_after_mark(db: Session, user: User, reps: list[SitokReport], done: bool, item: str = "field", day: datetime.date | None = None) -> None:
    """현장점검 표시 = 그 반기 방문 칸을 그날로 채움(visit_done — 10/18 형 "달력에서 빼면 이력 파악이 안 됨"),
    밖에서 완료 표시 = 방문 일정은 그대로(달력이 진하게 채움 — 10/19 형 "방문 달력에 모두 그대로 남아 있게, 완료된 건 색 채우기"),
    둘 다 지우면 다시 자동으로 잡음."""
    if done and item == "field":
        visit_done(db, user, reps, day or datetime.date.today())
    elif not done and not any((x.submit or {}).get(k) for x in reps for k in VISIT_ITEMS):  # 밖에서 완료는 일정을 안 건드림(10/19 형)
        fill_quietly(db, user.company_id, user.display_name or "", [x.facility_id for x in reps])


def _place_visit(db: Session, user: User, ids: list[int], year: int, half: str, kind: str, day: datetime.date, keep_length: bool) -> None:
    """그 반기 방문 일정을 day에 둠 — 그날이 든 일정(여러 날 일정이면 그 범위 안)은 그대로, 없으면 가장 가까운 일정을 옮기고(📌 manual,
    keep_length면 기간째, 아니면 하루로), 아예 없으면 그날 새로(대표 동). 다른 일정은 지우지 않음(10/19 형 "방문 달력에 모두 그대로 남아 있게")."""
    vs = db.query(SitokVisit).filter(SitokVisit.facility_id.in_(ids), SitokVisit.year == year, SitokVisit.half == half).all()
    if any(visit_span(v)[0] <= day <= visit_span(v)[1] for v in vs):
        return
    if vs:
        v = min(vs, key=lambda v: (abs((v.plan_date - day).days), v.id))
        a, b = visit_span(v)
        v.plan_date, v.plan_end, v.source = day, (day + (b - a)) if keep_length and b > a else None, "manual"
    else:
        lead = db.query(SitokFacility).filter(SitokFacility.id.in_(ids)).order_by(SitokFacility.group_order, SitokFacility.id).first()
        db.add(SitokVisit(company_id=user.company_id, facility_id=lead.id if lead else ids[0], year=year, half=half, kind=kind,
                          plan_date=day, source="manual", created_by=user.display_name or ""))
    db.commit()


def schedule_visit(db: Session, user: User, ids: list[int], year: int, half: str, kind: str, day: datetime.date) -> None:
    """현장점검일을 앞날로 넣음 = 예정 — 그 반기 방문 일정을 그날로(기간째 옮김). 완료 표시는 안 함(10/19 민재형)."""
    _place_visit(db, user, ids, year, half, kind, day, keep_length=True)


def visit_done(db: Session, user: User, reps: list[SitokReport], day: datetime.date) -> None:
    """현장점검 완료 → 그 반기 방문 칸을 완료한 날에 둠(달력이 채운 칸으로 그림, 옮기면 하루 일정)."""
    r = reps[0]
    _place_visit(db, user, [x.facility_id for x in reps], r.year, r.half, r.kind or "정기", day, keep_length=False)


class FacMarkIn(MarkIn):
    year: int
    half: str


@router.post("/facilities/{facility_id}/mark")
def mark_facility(facility_id: int, body: FacMarkIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """회차가 아직 없는 줄 — 현장점검일·밖에서 작성 완료만(10/16): 그 반기(연 3회면 시기) 회차를 만들어(묶인 동 같이) 표시."""
    from server.api.routers.sitok import contract_for, kind_known
    from server.api.routers.sitok_onboard import _default_people
    from server.api.routers.sitok_reports import _group_reports, _new_report
    from server.sitok.visit_plan import kind_of_title

    f = db.get(SitokFacility, facility_id)
    if f is None or f.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "시설물을 찾을 수 없습니다.")
    if body.item not in VISIT_ITEMS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "회차가 없는 줄은 현장점검·밖에서 작성 완료만 표시할 수 있습니다 — 회차를 먼저 만드세요.")
    if body.half not in seasons.ALL:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "반기가 맞지 않습니다.")
    r = db.query(SitokReport).filter(SitokReport.facility_id == f.id, SitokReport.year == body.year, SitokReport.half == body.half).first()
    day = _day(body.date, None)
    if r is None and body.item == "field" and body.action == "done" and day and day > datetime.date.today():  # 앞날 = 예정 — 회차는 안 만들고 일정만
        from server.api.routers.sitok_groups import members

        ids = [m.id for m in (members(db, f.group_id) if f.group_id else [f])]
        c = contract_for(db, f, body.year, seasons.bucket(body.half))
        schedule_visit(db, user, ids, body.year, body.half, kind_known(db, c, body.year, body.half) or (kind_of_title(c.title) if c is not None else "정기"), day)
        return {"ok": True, "item": body.item, "value": None, "planned": day.isoformat()}
    if r is None:
        c = contract_for(db, f, body.year, seasons.bucket(body.half))
        chief, parts = _default_people(db, user.company_id)
        kind = kind_known(db, c, body.year, body.half) or (kind_of_title(c.title) if c is not None else "정기")
        r = _new_report(db, user.display_name or "", f, body.year, body.half, contract_id=c.id if c else None, chief_id=chief, participant_ids=parts, kind=kind)
        if f.group_id:
            _group_reports(db, r, user.display_name or "")
        db.commit()
    return mark(r.id, MarkIn(item=body.item, action=body.action, date=body.date), user, db)


# ---------- 서류 제출 현황(서류 자동화 · 시특법 — 10/15 민재형 문서 "서류 제출현황 관리") ----------
# 상·하반기로, 한 줄 = 그 반기에 걸친 계약(관급 = 용역 기간이 반기와 겹침, 민간 = 그 반기 회차 줄·끝 없는 계약).
# 칸: 관급 착수계·완수계(첨부 넣고 [만들기]로 PDF까지 = 제출로 봄, 프로그램 쓰기 전 낸 것은 "직접 제출함"), 민간 계약서(만듦·날인본),
# 계산서 발행일(민간 = 반기마다 "2026-하반기", 관급 = 계약 하나 "all"). 표시는 sitok_doc_contract.marks(0048).

def _doc_key(c: SitokDocContract, year: int, half: str, is_now: bool) -> str | None:
    """이 반기에 보일 계약이면 계산서 칸 열쇠, 아니면 None. 날짜가 없는 계약은 지금 반기에만."""
    from server.api.routers.sitok import half_range

    a, b = half_range(year, half)
    if c.sector == "관급":
        if c.start_date is None:
            return "all" if is_now else None
        return "all" if c.start_date <= b and (c.end_date or c.start_date) >= a else None
    key = f"{year}-{half}"
    rounds = c.rounds or []
    if any(r.get("year") == year and seasons.bucket(r.get("half")) == half for r in rounds):
        return key
    if c.open_ended:
        return key if c.start_date is not None and c.start_date <= b else (key if c.start_date is None and is_now else None)
    if not rounds:
        if c.start_date is None:
            return key if is_now else None
        return key if c.start_date <= b and (c.end_date or c.start_date) >= a else None
    return None


@router.get("/docs")
def doc_rows(year: int | None = None, half: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from server.api.routers.sitok_docs import card_no, covered_ids, folder, half_auto, signed_pdf
    from server.sitok import civil

    y0, h0 = current_half()
    year, half = year or y0, half if half in HALVES else h0
    rows = []
    for c in db.query(SitokDocContract).filter(SitokDocContract.company_id == user.company_id).order_by(SitokDocContract.id):
        key = _doc_key(c, year, half, (year, half) == (y0, h0))
        if key is None:
            continue
        f = db.get(SitokFacility, c.facility_id) if c.facility_id else None
        mk = c.marks or {}
        made = lambda at: at.strftime("%Y-%m-%d") if at else ""  # noqa: E731
        signed = signed_pdf(c) is not None
        rows.append({
            "contract": {"id": c.id, "sector": c.sector, "title": c.title or civil.default_title(c), "half": c.half_tag or half_auto(c, f),
                         "period": f"{c.start_date or ''} ~ {'계약 해지 시까지' if c.open_ended else (c.end_date or '')}" if c.start_date else "",
                         "client": c.client},
            # 번호 = 서류 번호(계약이 시설물 여럿 = 관급-9, 하나 = 관급-9-1 — 10/15 민재형)
            "facility": {"id": f.id, "mgmt_no": card_no(db, c) or f.mgmt_no, "name": " · ".join(x.name for x in (db.get(SitokFacility, i) for i in covered_ids(c)) if x) or f.name,
                         "sector": f.sector or "민간", "badge_field": f.badge_field or "", "badge_kind": f.badge_kind or ""} if f is not None else None,
            "start": {"made": made(c.start_made_at) if c.sector == "관급" else made(c.made_at), "signed": signed if c.sector == "민간" else False,
                      "pdf": (folder(c) / "착수계.pdf").exists() if c.sector == "관급" else False, "mark": mk.get("start")},
            "done": {"made": made(c.done_made_at), "mark": mk.get("done")} if c.sector == "관급" else None,
            "invoice": {"key": key, "date": (mk.get("invoice") or {}).get(key) or ""},
        })
    return {"year": year, "half": half, "rows": rows}


class DocMarkIn(BaseModel):
    item: str  # start | done | invoice
    action: str = "done"  # done | clear
    date: str | None = None
    key: str | None = None  # 계산서 칸 열쇠("2026-하반기" / "all")


@router.post("/docs/{cid}/mark")
def doc_mark(cid: int, body: DocMarkIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.get(SitokDocContract, cid)
    if c is None or c.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "계약을 찾을 수 없습니다.")
    if body.item not in ("start", "done", "invoice") or body.action not in ("done", "clear"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "표시할 칸이 아닙니다.")
    day = _day(body.date, datetime.date.today())
    mk = dict(c.marks or {})
    if body.item == "invoice":
        key = body.key or ("all" if c.sector == "관급" else "")
        if not key:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "계산서 반기가 없습니다.")
        inv = dict(mk.get("invoice") or {})
        if body.action == "clear":
            inv.pop(key, None)
        else:
            inv[key] = day.isoformat()
        mk["invoice"] = inv
    elif body.action == "clear":
        mk.pop(body.item, None)
    else:
        mk[body.item] = {"at": day.isoformat(), "by": user.display_name or ""}
    c.marks = mk
    db.commit()
    return {"ok": True, "marks": mk}
