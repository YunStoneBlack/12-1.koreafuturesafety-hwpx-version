"""서류 자동화 · 시특법 — 정밀안전점검·정밀안전진단 도래주기(2026-10-20 민재형, 시행령 별표 3). 계산은 server/sitok/cycle.py.

계약 창(js/sitok-docs.js 📅 도래주기 칸)이 회차 줄마다 실시할 점검(정기·정밀·진단)을 고르고, 전회차 기록이 없으면 사람이 넣음
(3종 = 안 물음, 2종 = 전회차 정밀안전점검, 1종 = + 정밀안전진단 — 넣은 값은 시설물에 저장해 다음 계약 때 다시 안 물음).

- `GET /sitok/docs/cycle?ids=1,2&halves=2027-상반기,2027-하반기` — 건물마다(묶음은 동마다) 재료·계획 + 회차 줄마다 합친 점검
- `POST /sitok/docs/cycle/facility/{fid}` {class_no?, safety_grade?, last_precision?("2024-09"), last_diagnosis?, precision_first?, diagnosis_first?, completion_date?}
"""
from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokFacility, User
from server.api.deps import get_current_user, get_db
from server.sitok import cycle as C
from server.sitok import seasons

router = APIRouter(prefix="/sitok/docs/cycle", tags=["sitok-cycle"])


def _buildings(db: Session, user: User, ids: list[int]) -> list[SitokFacility]:
    """계약이 맡는 시설물 → 건물(묶음이면 동 전부, 묶음 순서), 겹치지 않게."""
    from server.api.routers.sitok_groups import members

    out, seen = [], set()
    for i in ids:
        f = db.get(SitokFacility, i)
        if f is None or f.company_id != user.company_id:
            continue
        for m in (members(db, f.group_id) if f.group_id else [f]):
            if m.id not in seen:
                seen.add(m.id)
                out.append(m)
    return out


def _halves(text: str) -> list[tuple[int, str]]:
    out = []
    for x in (text or "").split(","):
        y, _, h = x.strip().partition("-")
        if y.isdigit() and h in seasons.ALL:
            out.append((int(y), h))
    return out


def _ym(d: datetime.date | None) -> str:
    return f"{d:%Y-%m}" if d else ""


def _planned(db: Session, user: User, f: SitokFacility, before: datetime.date | None) -> list:
    """이미 계약된 정밀·진단 회차(서류 계약 회차 줄, 새 계약 첫 반기 전) — [(그 반기 끝, 정밀|진단, "계약 회차 2027 상반기")]. 묶음 동은 대표 동 계약도."""
    from server.api.routers.sitok_docs import contract_index
    from server.api.routers.sitok_groups import members

    if before is None:
        return []
    ids = {f.id} | ({m.id for m in members(db, f.group_id)} if f.group_id else set())
    out = []
    for c, cov in contract_index(db, user.company_id):
        if not cov & ids:
            continue
        for r in c.rounds or []:
            if r.get("kind") in ("정밀", "진단") and str(r.get("year") or "").isdigit() and r.get("half") in seasons.ALL:
                end = C.half_bounds(int(r["year"]), r["half"])[1]
                if end < before:
                    out.append((end, r["kind"], f"계약 회차 {r['year']} {r['half']}"))
    return out


@router.get("")
def get_cycle(ids: str, halves: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    hs = _halves(halves)
    first = min((C.half_bounds(y, h)[0] for y, h in hs), default=None)  # 새 계약 첫 반기 시작 — 그 전 계약 회차의 정밀·진단을 전회차로
    rows, plans, names = [], [], []
    for f in _buildings(db, user, [int(x) for x in ids.split(",") if x.strip().isdigit()]):
        info = C.gather(db, f, _planned(db, user, f, first))
        p = C.plan(info, hs)
        plans.append(p)
        names.append(f.name)
        rows.append({
            "id": f.id, "name": f.name, "class_no": info.class_no, "class_src": info.class_src, "field": info.field, "kind": f.kind or "",
            "grade": info.grade, "grade_src": info.grade_src, "completion": f.completion_date.isoformat() if f.completion_date else "",
            "last_precision": _ym(info.last_precision), "lp_src": info.lp_src, "precision_first": info.precision_first,
            "last_diagnosis": _ym(info.last_diagnosis), "ld_src": info.ld_src, "diagnosis_first": info.diagnosis_first,
            "needs": C.needs(info), "next": p["next"], "warn": p["warn"],
            "plan": {f"{y}-{h}": v for (y, h), v in p["rounds"].items()},
        })
    return {"rows": rows, "rounds": C.merge(plans, hs, names)}


class CycleIn(BaseModel):
    class_no: str | None = None  # "1종" / "2종" / "3종" / ""(보고서 틀로)
    safety_grade: str | None = None  # A~E / ""(최근 보고서)
    last_precision: str | None = None  # "2024-09"(달까지 — 주기는 완료한 달의 마지막 날부터) / ""
    last_diagnosis: str | None = None
    precision_first: bool | None = None  # 아직 정밀안전점검을 한 적 없음 — 준공일로 최초 시기
    diagnosis_first: bool | None = None
    completion_date: datetime.date | None = None


def _month(text: str | None) -> datetime.date | None:
    """"2024-09" / "2024-09-15" / "2024.09" → 그달 마지막 날, 빈 값 None, 모양이 틀리면 400."""
    t = (text or "").strip().replace(".", "-")
    if not t:
        return None
    try:
        y, m = (int(x) for x in t.split("-")[:2])
        return C.month_end(datetime.date(y, m, 1))
    except (ValueError, TypeError) as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "날짜는 2024-09처럼 넣어 주세요.") from err


@router.post("/facility/{fid}")
def save_cycle(fid: int, body: CycleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = db.get(SitokFacility, fid)
    if f is None or f.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "시설물을 찾을 수 없습니다.")
    data = body.model_dump(exclude_unset=True)
    if "class_no" in data:
        v = (data["class_no"] or "").strip()
        if v and v not in ("1종", "2종", "3종"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "종별은 1종·2종·3종 중 하나입니다.")
        f.class_no = v
    if "safety_grade" in data:
        v = C.letter(data["safety_grade"]) if (data["safety_grade"] or "").strip() else ""
        f.safety_grade = v
    for k, first in (("last_precision", "precision_first"), ("last_diagnosis", "diagnosis_first")):
        if k in data:
            d = _month(data[k])
            setattr(f, k, d)
            if d:
                setattr(f, first, False)  # 날짜를 넣으면 "처음"은 풂
        if first in data and data[first] is not None:
            setattr(f, first, bool(data[first]))
            if data[first]:
                setattr(f, k, None)  # "처음"이면 넣었던 날짜는 지움
    if "completion_date" in data and data["completion_date"]:
        f.completion_date = data["completion_date"]
    db.commit()
    return {"ok": True}
