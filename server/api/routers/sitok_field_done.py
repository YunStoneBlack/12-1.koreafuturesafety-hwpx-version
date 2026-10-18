"""시특법 현장 조사 [✓ 조사 완료](2026-10-18 민재형 "조사완료 버튼 만들고") — 현장 조사 화면 맨 아래 버튼. 회차 화면 "현장 조사 ✓"는 이 버튼으로만.

전엔 결함 줄이나 전경사진이 하나라도 있으면 ✓ — 전회차 결함을 가져오기만 해도 끝난 것처럼 보였음(양주덕산초 교사동(본관) 125개 가져옴·확인 0).
누를 때마다 빠진 항목을 탭마다 예외 없이 보여 줌(형 "해당이 있는데 안 한 건지 없어서 안 한 건지는 경고를 듣고 점검자가 판단") — 화면이 [이어서 점검하기]·[현장점검 완료]를
몇 번이든 묻고, 경고가 남아 있어도 [현장점검 완료]면 완료. 완료 = sitok_report.survey["field_done"] {at, by}(동마다).
묶음의 동이 다 완료되면 제출 현황 [현장점검](submit.field)에 날짜 → 방문 달력 그 반기 칸을 채움(sitok_status.visit_done — 형 "달력에서 빼면 현장점검 이력 파악이 안 됨").

- `GET  /sitok/reports/{id}/field-check` — {done, missing: [{tab, text}], unit: {total, done}}
- `POST /sitok/reports/{id}/field-done` {done: bool} — 완료 / 완료 취소
"""
from __future__ import annotations

import datetime
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokDefect, SitokFacility, SitokReport, User
from server.api.deps import get_current_user, get_db
from server.api.routers.sitok_defects import floor_key
from server.api.routers.sitok_parts import _out as parts_out
from server.api.routers.sitok_reports import _report_dir, _require
from server.api.routers.sitok_status import _unit_reports, visits_after_mark
from server.sitok import parts as P, precision as PR

router = APIRouter(prefix="/sitok", tags=["sitok"])


def missing(db: Session, r: SitokReport) -> list[dict]:
    """빠진 점검 항목 — 탭(화면 탭 data-tab)마다 한 줄씩. 해당없음인지 안 한 건지는 점검자가 판단(그래서 다 보여 줌)."""
    out: list[dict] = []
    add = lambda tab, text: out.append({"tab": tab, "text": text})  # noqa: E731
    rows = db.query(SitokDefect.floor, SitokDefect.check, SitokDefect.photo).filter(SitokDefect.report_id == r.id).all()
    if not rows:
        add("defects", "결함이 하나도 없습니다 — 전회차 결함을 가져오지 않았거나 신규 결함을 넣지 않았습니다")
    else:
        left = Counter(fl for fl, c, _ in rows if not c)
        if left:
            add("defects", f"현장 확인 안 한 결함 {sum(left.values())}개 — " + " · ".join(f"{fl} {n}" for fl, n in sorted(left.items(), key=lambda x: floor_key(x[0]))))
        nophoto = sum(1 for _, _, ph in rows if not (ph and Path(ph).exists()))
        if nophoto:
            add("defects", f"이번 사진이 없는 결함 {nophoto}개")
    if not r.overview:
        add("overview", "전경사진 0장 — 안 찍으면 지난 회차 사진이 그대로 들어갑니다")
    po = parts_out(db, r)
    pub = [p["name"] for p in po["public"] if not p["has"] and not p["none"]]
    if pub:
        add("public", f"사진도 [해당없음]도 아닌 항목 — {' · '.join(pub)}")
    if any(not all(o["slots"]) for o in po["other"]):
        add("other", " · ".join(f"{o['name']} {sum(o['slots'])}/{len(o['slots'])}장" for o in po["other"]) + " — 빈 칸은 보고서에 \"-\"")
    if (r.kind or "정기") == "정밀":
        p = PR.norm((r.survey or {}).get("precision"))
        base = _report_dir(db.get(SitokFacility, r.facility_id), r)
        has = lambda f: bool(f and (base / f).exists())  # noqa: E731
        docs = [n for _, k, n in PR.DOC_ITEMS if not (p["docs"].get(k) or {}).get("status")]
        if docs:
            add("docs", f"보관 여부를 안 고른 자료 {len(docs)}개 — {' · '.join(docs[:3])}{' 외' if len(docs) > 3 else ''}")
        if not p["seismic"]["status"]:
            add("docs", "내진설계 적용 여부를 안 골랐습니다")
        n = sum(1 for ph in p["load"]["photos"] if has(ph["file"]))
        if n < PR.LOAD_SLOTS:
            add("load", f"사용하중 현황사진 {n}/{PR.LOAD_SLOTS}장")
        groups = [(f"{cap} {title}", sum(1 for f in p["survey"][k] if has(f)), len(titles)) for k, cap, title, titles in PR.SURVEY_PICS]
        empty = [f"{name} {n}/{total}" for name, n, total in groups if n < total]
        if empty:
            add("survey", f"조사 전경 사진 {sum(n for _, n, _ in groups)}/{sum(t for _, _, t in groups)}장 — {' · '.join(empty)}")
        grades = P.norm(r.parts).get("grades") or {}
        g_pub = [p_["name"] for p_ in po["public"] if not p_["none"] and not grades.get(p_["key"])]
        if g_pub:
            add("public", f"상태평가 등급을 안 고른 항목 — {' · '.join(g_pub)}")
        g_oth = [n for k, n in P.OTHER if not grades.get(k)]
        if g_oth:
            add("other", f"등급을 안 고른 항목 — {' · '.join(g_oth)}")
    return out


def _state(db: Session, r: SitokReport) -> dict:
    reps = _unit_reports(db, r)
    return {"done": (r.survey or {}).get("field_done"), "unit": {"total": len(reps), "done": sum(1 for x in reps if (x.survey or {}).get("field_done"))},
            "field": (r.submit or {}).get("field")}


@router.get("/reports/{report_id}/field-check")
def field_check(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    return {**_state(db, r), "missing": missing(db, r)}


class DoneIn(BaseModel):
    done: bool = True


@router.post("/reports/{report_id}/field-done")
def field_done(report_id: int, body: DoneIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    by = user.display_name or ""
    reps = _unit_reports(db, r)
    sv = dict(r.survey or {})
    if body.done:
        sv["field_done"] = {"at": datetime.date.today().isoformat(), "by": by}
        r.survey = sv
        dones = [(x.survey or {}).get("field_done") for x in reps]
        if all(dones) and not any((x.submit or {}).get("field") for x in reps):  # 묶음의 동이 다 끝남 → 제출 현황 [현장점검]·방문 달력
            day = max(d["at"] for d in dones)
            for x in reps:
                x.submit = {**(x.submit or {}), "field": {"at": day, "by": by}}
            db.commit()
            visits_after_mark(db, user, reps, True, "field", datetime.date.fromisoformat(day))
    else:
        sv.pop("field_done", None)
        r.survey = sv
        if any((x.submit or {}).get("field") for x in reps):  # 한 동이라도 다시 열면 묶음 [현장점검]도 풂(달력 칸은 그 자리에 빈 칸으로)
            for x in reps:
                sub = dict(x.submit or {})
                sub.pop("field", None)
                x.submit = sub
            db.commit()
            visits_after_mark(db, user, reps, False, "field")
    db.commit()
    return _state(db, r)
