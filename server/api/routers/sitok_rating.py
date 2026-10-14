"""시특법 정밀안전점검 상태평가(2026-10-13 밤, ③ 단계) — 표본층별 부재 전체 개수 입력 → 결함현황표·재료시험과 합쳐 SafetyMan 갑지와 같은 결과.

- `GET /sitok/reports/{id}/rating` — 입력(counts·prev_grade·note, 비었으면 지난 정밀 회차 개수) + 결과(rating.evaluate) + 근거(층·부재·항목·결함) + 제외/미배정 결함.
- `PATCH /sitok/reports/{id}/rating` — 입력 저장 → 같은 보기.
- `GET /sitok/reports/{id}/rating/pdf` — 부록 "상태평가 결과 자료" PDF(건축물 평가결과 + 입력자료, server/sitok/condition.make_pdf) — 회차 폴더 상태평가/.
화면 sitok-rating.html(js/sitok-rating.js). 정밀 회차 카드 [📊 상태평가]."""
from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import Company, SitokFacility, SitokReport, User
from server.api.deps import get_current_user, get_db
from server.api.routers.sitok_defects import _defects_for_cost
from server.api.routers.sitok_reports import _order, _report_dir, _require
from server.api.routers.sitok_tests import _view as tests_view
from server.sitok import condition

router = APIRouter(prefix="/sitok", tags=["sitok-rating"])
GRADE_LETTERS = ("", "A", "B", "C", "D", "E")


class RatingIn(BaseModel):
    counts: dict | None = None
    prev_grade: str | None = None
    note: str | None = None


def _norm_counts(v) -> dict:
    out = {}
    for key, members in (v or {}).items():
        try:
            k = str(int(key))
        except (TypeError, ValueError):
            continue
        row = {}
        for m, n in (members or {}).items():
            if m in condition.MEMBERS or m in condition.STEEL_MEMBERS:
                try:
                    row[m] = max(0, int(float(str(n).replace(",", "")))) if str(n).strip() not in ("", "None") else 0
                except ValueError:
                    row[m] = 0
        out[k] = row
    return out


def _previous_precision(db: Session, r: SitokReport) -> SitokReport | None:
    rows = db.query(SitokReport).filter(SitokReport.facility_id == r.facility_id, SitokReport.id != r.id, SitokReport.kind == "정밀").all()
    before = [x for x in rows if _order(x) < _order(r)]
    return max(before, key=_order) if before else None


def _compute(db: Session, r: SitokReport) -> dict:
    f = db.get(SitokFacility, r.facility_id)
    tv = tests_view(db, r)
    raw = r.rating or {}
    counts = _norm_counts(raw.get("counts"))
    carried = False
    prev = _previous_precision(db, r)
    if not any(any(v.values()) for v in counts.values()) and prev is not None and (prev.rating or {}).get("counts"):
        counts, carried = _norm_counts(prev.rating["counts"]), True
    prev_grade = (raw.get("prev_grade") or "").strip().upper()
    prev_auto = ""
    if not prev_grade and prev is not None:
        try:
            pres = condition.evaluate(condition.aggregate(_defects_for_cost(db, prev.id), tests_view(db, prev), _norm_counts((prev.rating or {}).get("counts")),
                                                         above=f.floors_above or 0, below=f.floors_below or 0))
            prev_auto = pres["total"]["grade"] if pres and pres.get("total") else ""
        except Exception:  # noqa: BLE001 — 지난 회차가 덜 됐으면 그냥 빈칸
            prev_auto = ""
    agg = condition.aggregate(_defects_for_cost(db, r.id), tv, counts, above=f.floors_above or 0, below=f.floors_below or 0,
                              tilt_note=tv["tilt"]["note"], settlement_note=tv["settlement"]["note"])
    result = condition.evaluate(agg)
    steel = any(fl.get("material") == "철골" for fl in tv["sample"]["floors"])  # 철골조면 강재기둥·강재보 열(10/14)
    return {"report": tv["report"], "building": tv["building"], "sample_floors": tv["sample"]["floors"], "members": list(condition.MEMBERS) + (list(condition.STEEL_MEMBERS) if steel else []),
            "counts": counts, "carried": carried, "prev_grade": prev_grade, "prev_auto": prev_auto, "prev_report": {"id": prev.id, "year": prev.year, "half": prev.half} if prev else None,
            "note": raw.get("note") or "", "result": result, "floors": agg["floors"], "deform": agg["deform"], "excluded": agg["excluded"], "unassigned": agg["unassigned"],
            "labels": {"items": condition.ITEM_LABEL, "surface": condition.SURFACE_LABEL, "crack_rows": condition.CRACK_ROWS, "scaling_rows": condition.SCALING_ROWS,
                       "spalling_rows": condition.SPALLING_ROWS, "leak_rows": condition.LEAK_ROWS, "rebar_rows": condition.REBAR_ROWS}}


@router.get("/reports/{report_id}/rating")
def get_rating(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    return _compute(db, r)


@router.patch("/reports/{report_id}/rating")
def save_rating(report_id: int, body: RatingIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    cur = dict(r.rating or {})
    data = body.model_dump(exclude_unset=True)
    if "counts" in data:
        cur["counts"] = _norm_counts(data["counts"])
    if "prev_grade" in data:
        g = (data["prev_grade"] or "").strip().upper()
        if g not in GRADE_LETTERS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "전회차 등급은 A~E입니다.")
        cur["prev_grade"] = g
    if "note" in data:
        cur["note"] = (data["note"] or "").strip()
    r.rating = cur
    db.commit()
    return _compute(db, r)


@router.get("/reports/{report_id}/rating/pdf")
def rating_pdf(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    v = _compute(db, r)
    if v["result"] is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "평가할 부재가 없습니다 — 표본층을 고르고 부재 개수를 넣으세요.")
    tv = tests_view(db, r)
    co = db.get(Company, user.company_id)
    when = r.period_start or r.report_date or datetime.date.today()
    bi = {"name": f.name, "address": f.address, "owner": f.owner_name, "completion": f"{f.completion_date.year}년 {f.completion_date.month}월" if f.completion_date else "",
          "use": f.main_use or f.use_type, "structure": f.structure, "land_area": "", "building_area": f"{f.building_area:,.1f} ㎡" if f.building_area else "",
          "total_area": f"{f.total_area:,.1f} ㎡" if f.total_area else "", "above": f.floors_above or 0, "below": f.floors_below or 0,
          "company": co.name if co else "", "phone": getattr(co, "phone", "") or "", "when": when.isoformat()}
    agg = condition.aggregate(_defects_for_cost(db, r.id), tv, v["counts"], above=f.floors_above or 0, below=f.floors_below or 0,
                              tilt_note=tv["tilt"]["note"], settlement_note=tv["settlement"]["note"])
    dest = _report_dir(f, r) / "상태평가" / "상태평가결과.pdf"
    condition.make_pdf(dest, agg, v["result"], bi, tv, v["prev_grade"] or v["prev_auto"])
    return FileResponse(dest, media_type="application/pdf", filename=f"상태평가결과_{f.name}.pdf", content_disposition_type="inline")
