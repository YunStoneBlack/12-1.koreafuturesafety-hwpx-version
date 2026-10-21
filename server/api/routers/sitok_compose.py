"""시특법 보고서 구성(2026-10-16 민재형) — 시설물 카드 안 건물(관리대장으로 등록한 시설물)을 보고서 상자에 넣어 보고서를 몇 권 낼지 정함.

형 흐름: 현장 하나 = 카드 하나(계약이 몇 개든) → 건물을 몇 개든 등록 → [보고서 구성]에서 상자를 만들고 건물을 끌어다 넣음 →
계약이 이 반기에 둘 이상일 때만 상자마다 연결할 계약을 고름(하나면 자동).
- 상자 하나에 건물 여럿 = 동 묶음(SitokGroup — 보고서 한 권, 현장 조사·면담·현황은 동마다, 시설물편 제N장), 건물 하나 = 그 건물만.
- 번호: 건물은 모두 카드 번호(관급-6) — 뒷번호 없음(10/19 민재형), 상자 순서는 book_order(1·2…, 상자 하나면 0). 계약 번호 9-1·9-2는 서류 자동화(sitok_docs.card_no).
- 저장하면 지금 구조(묶음·번호)를 바꿈 — 보고서 만들기·제출 현황·방문 달력·서류 카드가 그대로 따라감. 회차·현장 데이터는 건물마다라 상자를 옮겨도 안 사라짐.
- 계약: 이 반기와 기간이 겹치는 서류 자동화 계약마다 맡는 상자(대표 동)를 다시 정하고(cover "" — 사람이 정함) 보고서 쪽 계약·이 반기 회차 계약 칸까지.
  다른 반기 계약은 안 건드림. 추천 배치 = 계약 건명·내역서에 나오는 건물 이름으로(관급-9 "본관, 교직원 식당" → 그 계약 상자).

- `GET  /sitok/facilities/{id}/compose?year=&half=` — 건물·지금 상자·이 반기 계약·추천
- `POST /sitok/facilities/{id}/compose` {year, half, books: [{ids, name, contract_id}]}
"""
from __future__ import annotations

import datetime
import os

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokContract, SitokDocContract, SitokFacility, SitokGroup, SitokReport, User
from server.api.deps import get_current_user, get_db
from server.api.routers.sitok import NO_RE, _require_facility, base_no, card_facilities
from server.api.routers.sitok_groups import members
from server.sitok import seasons

router = APIRouter(prefix="/sitok", tags=["sitok"])


def default_name(names: list[str]) -> str:
    """묶음 이름 기본값 = 건물 이름들의 같은 앞부분("분당영덕여자고등학교 본관동"·"… 교직원식당" → "분당영덕여자고등학교"), 짧으면 첫 건물 이름."""
    pre = os.path.commonprefix(names).strip()
    return pre if len(pre) >= 2 else (names[0] if names else "")


def _books_now(db: Session, f: SitokFacility) -> list[list[SitokFacility]]:
    """지금 상자 — 보고서 하나 = 묶음(대표 동 + 동들) 또는 건물 하나, 번호 순서."""
    seen, out = set(), []
    for x in sorted(card_facilities(db, f), key=lambda x: (x.book_order or 0, x.group_order or 0, x.id)):
        if x.id in seen:
            continue
        ms = members(db, x.group_id) if x.group_id else [x]
        seen |= {m.id for m in ms}
        out.append(ms)
    return out


def _overlaps(c: SitokDocContract, year: int, half: str) -> bool:
    """이 계약이 이 반기를 덮나 — 민간은 회차 줄(또는 끝 없는 계약), 관급·그 밖은 용역 기간."""
    if seasons.is_seismic_title(c.title) != seasons.is_seismic(half):  # 내진성능평가 계약은 성능평가 회차에만(10/21 — 정기 보고서 구성·제출 현황에 안 섞임)
        return False
    hb = seasons.bucket(half)
    if c.rounds:
        return any(int(r.get("year") or 0) == year and seasons.bucket(r.get("half") or "") == hb for r in c.rounds)
    a, b = (datetime.date(year, 1, 1), datetime.date(year, 6, 30)) if hb == "상반기" else (datetime.date(year, 7, 1), datetime.date(year, 12, 31))
    if c.start_date is None:
        return False
    end = c.end_date or (b if c.open_ended else c.start_date)
    return c.start_date <= b and end >= a


def _overlap_days(c: SitokDocContract, year: int, half: str) -> int:
    """이 반기와 겹치는 날 수(상자 계약 기본값 고르기) — 민간 회차 줄 계약은 반기 전체로 봄.
    10/21 관급-30: 상반기 계약(4/13~7/11)이 하반기와 11일 겹쳐 하반기 상자 기본값이 상반기 계약(시작이 이른 것)이 됐던 것."""
    if not _overlaps(c, year, half):
        return 0
    hb = seasons.bucket(half)
    a, b = (datetime.date(year, 1, 1), datetime.date(year, 6, 30)) if hb == "상반기" else (datetime.date(year, 7, 1), datetime.date(year, 12, 31))
    if c.rounds or c.start_date is None:
        return (b - a).days + 1
    end = c.end_date or (b if c.open_ended else c.start_date)
    return (min(b, end) - max(a, c.start_date)).days + 1


def _contracts(db: Session, ids: set[int], year: int, half: str) -> list[SitokDocContract]:
    from server.api.routers.sitok_docs import covered_ids

    return [c for c in db.query(SitokDocContract).filter(SitokDocContract.company_id == db.get(SitokFacility, next(iter(ids))).company_id)
            .order_by(SitokDocContract.start_date, SitokDocContract.id) if set(covered_ids(c)) & ids and _overlaps(c, year, half)]


def _con_out(db: Session, c: SitokDocContract) -> dict:
    from server.api.routers.sitok_docs import card_no
    from server.sitok import civil

    period = f"{c.start_date:%Y.%m.%d}~{'해지 시까지' if c.open_ended else (f'{c.end_date:%Y.%m.%d}' if c.end_date else '')}" if c.start_date else ""
    return {"id": c.id, "no": card_no(db, c), "title": c.title or civil.default_title(c), "period": period, "amount": c.amount}  # no = 계약 번호(관급-9-1, 10/19)


@router.get("/facilities/{facility_id}/compose")
def get_compose(facility_id: int, year: int | None = None, half: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from server.api.routers.sitok_docs import _named_units, covered_ids
    from server.api.routers.sitok_status import current_half

    f = _require_facility(db, user, facility_id)
    y0, h0 = current_half()
    year, half = year or y0, half if half in ("상반기", "하반기") else h0
    books = _books_now(db, f)
    blds = [x for b in books for x in b]
    ids = {x.id for x in blds}
    cons = _contracts(db, ids, year, half)
    reps = {r.facility_id: r for r in db.query(SitokReport).filter(SitokReport.facility_id.in_(ids), SitokReport.year == year,
                                                                   SitokReport.half.in_(seasons.in_bucket(half)))}

    def con_of(book: list[SitokFacility]) -> int | None:  # 이 상자 건물을 맡는 계약 중 반기와 가장 많이 겹치는 것(같으면 늦게 시작한 것)
        mine = [c for c in cons if set(covered_ids(c)) & {x.id for x in book}]
        return max(mine, key=lambda c: (_overlap_days(c, year, half), c.start_date or datetime.date.min, c.id)).id if mine else None

    suggest = None
    if len(cons) >= 2:  # 추천 — 계약마다 건명·내역서에 나오는 건물, 겹치지 않고 다 들어가면
        picks = [(c, [u.id for u in _named_units(c, blds)]) for c in cons]
        used = [i for _, p in picks for i in p]
        if all(p for _, p in picks) and len(used) == len(set(used)):
            rest = [x.id for x in blds if x.id not in used]
            suggest = [{"ids": p, "name": "", "contract_id": c.id} for c, p in picks] + [{"ids": [i], "name": "", "contract_id": None} for i in rest]
    gname = lambda b: (db.get(SitokGroup, b[0].group_id).name if b[0].group_id and db.get(SitokGroup, b[0].group_id) else "")  # noqa: E731
    return {
        "card": {"no": base_no(f.mgmt_no), "name": books[0][0].name if books else f.name},
        "year": year, "half": half,
        "buildings": [{"id": x.id, "name": x.name, "fms_no": x.fms_no or "", "mgmt_no": x.mgmt_no,
                       "round": ({"id": reps[x.id].id, "kind": reps[x.id].kind, "data": bool(reps[x.id].survey or reps[x.id].ai)} if x.id in reps else None)}
                      for x in blds],
        "books": [{"ids": [x.id for x in b], "name": gname(b), "contract_id": con_of(b)} for b in books],
        "contracts": [_con_out(db, c) for c in cons], "suggest": suggest,
    }


class BookIn(BaseModel):
    ids: list[int]
    name: str = ""
    contract_id: int | None = None


class ComposeIn(BaseModel):
    year: int
    half: str
    books: list[BookIn]


@router.post("/facilities/{facility_id}/compose")
def save_compose(facility_id: int, body: ComposeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from fastapi import HTTPException as _H

    from server.api.routers.sitok_docs import covered_ids, to_facility
    from server.api.routers.sitok_reports import _group_reports
    from server.sitok.visit_plan import fill_quietly

    f = _require_facility(db, user, facility_id)
    if body.half not in ("상반기", "하반기"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "반기가 맞지 않습니다.")
    card = {x.id: x for x in card_facilities(db, f)}
    books = [b for b in body.books if b.ids]
    flat = [i for b in books for i in b.ids]
    if sorted(flat) != sorted(card) or len(flat) != len(set(flat)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "건물마다 보고서 하나에만 넣어 주세요(빠진 건물·두 번 넣은 건물이 있습니다).")
    base = base_no(f.mgmt_no)
    if not NO_RE.match(base or ""):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "카드 번호(관급-6 같은)가 없어 보고서를 나눌 수 없습니다 — 먼저 번호를 넣으세요.")
    old_groups = {x.group_id for x in card.values() if x.group_id}
    used_groups: set[int] = set()
    leads = []
    for k, b in enumerate(books, 1):
        fs = [card[i] for i in b.ids]
        if len(fs) > 1:  # 동 묶음 — 첫 건물의 묶음을 그대로 쓰고(다른 상자가 안 썼으면), 없으면 새로
            gid = next((x.group_id for x in fs if x.group_id and x.group_id not in used_groups), None)
            g = db.get(SitokGroup, gid) if gid else None
            if g is None:
                g = SitokGroup(company_id=user.company_id, name="")
                db.add(g)
                db.flush()
            g.name = (b.name or "").strip() or default_name([x.name for x in fs])
            used_groups.add(g.id)
            for i, x in enumerate(fs):
                x.group_id, x.group_order = g.id, i
        else:
            fs[0].group_id, fs[0].group_order = None, 0
        for x in fs:
            x.mgmt_no, x.book_order = base, (k if len(books) > 1 else 0)
        leads.append(fs[0])
    for gid in old_groups - used_groups:  # 빈 묶음 지움
        g = db.get(SitokGroup, gid)
        if g is not None and not members(db, gid):
            db.delete(g)
    db.flush()
    # 계약 — 이 반기와 겹치는 계약마다 맡는 상자(대표 동)
    cons = _contracts(db, set(card), body.year, body.half)
    pick = {k: (cons[0].id if len(cons) == 1 else b.contract_id) for k, b in enumerate(books)}
    lead_of = {x.id: leads[k] for k, b in enumerate(books) for x in (card[i] for i in b.ids)}
    notes = []
    for c in cons:
        mine = [leads[k].id for k in range(len(books)) if pick[k] == c.id]
        if not mine and len(cons) > 1:  # 고른 상자가 없는 계약 — 지금 맡던 건물을 대표 동으로만 맞춤
            mine = list(dict.fromkeys(lead_of[i].id for i in covered_ids(c) if i in lead_of))
        if not mine:
            continue
        before = covered_ids(c)
        c.facility_id, c.facility_ids, c.cover = mine[0], (mine if len(mine) > 1 else None), ""
        c.amounts = {k2: v for k2, v in (c.amounts or {}).items() if int(k2) in mine} or None
        db.flush()
        if before != covered_ids(c) and (c.report_contracts or c.report_contract_id or c.contract_pdf):
            try:
                to_facility(c.id, user, db)
            except _H:
                db.rollback()
            if len(mine) > 1 and not c.amounts:
                notes.append(f"계약 \"{(c.title or '')[:30]}\"이(가) 보고서 {len(mine)}개를 맡습니다 — 서류 자동화 계약 정보에서 보고서별 금액을 나눠 넣으세요.")
    db.commit()
    # 이 반기 회차 — 상자(묶음)마다 동 회차를 맞추고 계약 칸을 그 상자 계약으로
    have_round = db.query(SitokReport.id).filter(SitokReport.facility_id.in_(list(card)), SitokReport.year == body.year,
                                                 SitokReport.half.in_(seasons.in_bucket(body.half))).first() is not None
    for k, lead in enumerate(leads):
        c = next((x for x in cons if x.id == pick[k]), None)
        rc_id = None
        if c is not None:
            db.refresh(c)
            rc_id = (c.report_contracts or {}).get(str(lead.id)) or (c.report_contract_id if c.facility_id == lead.id else None)
        ids = [x.id for x in (members(db, lead.group_id) if lead.group_id else [lead])]
        reps = db.query(SitokReport).filter(SitokReport.facility_id.in_(ids), SitokReport.year == body.year,
                                            SitokReport.half.in_(seasons.in_bucket(body.half))).all()
        if reps and lead.group_id:
            for r in {r.half: r for r in reps}.values():
                _group_reports(db, r, user.display_name or "")
            reps = db.query(SitokReport).filter(SitokReport.facility_id.in_(ids), SitokReport.year == body.year,
                                                SitokReport.half.in_(seasons.in_bucket(body.half))).all()
        if rc_id:
            for r in reps:
                r.contract_id = rc_id
        if not reps and rc_id and have_round:  # 계약이 이 반기를 덮는데 회차가 없는 보고서 — 다른 보고서에 이 반기 회차가 있으면 같이 만듦(제출 현황·달력에 나오게, 10/16 관급-10 옹벽)
            from server.api.routers.sitok import kind_known
            from server.api.routers.sitok_onboard import _default_people
            from server.api.routers.sitok_reports import _new_report

            rc = db.get(SitokContract, rc_id)
            chief, parts = _default_people(db, user.company_id)
            r = _new_report(db, user.display_name or "", lead, body.year, body.half, contract_id=rc_id, chief_id=chief, participant_ids=parts,
                            kind=kind_known(db, rc, body.year, body.half) or "정기")
            if lead.group_id:
                _group_reports(db, r, user.display_name or "")
            notes.append(f"보고서 {k + 1}({lead.name})에 {body.year}년 {body.half} 회차를 만들었습니다.")
    db.commit()
    fill_quietly(db, user.company_id, user.display_name or "", list(card))
    out = get_compose(facility_id, body.year, body.half, user, db)
    return out | {"notes": notes}
