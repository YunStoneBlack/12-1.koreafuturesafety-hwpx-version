"""시특법 보고서 회차(2026-10-10 4단계) — 시설물 화면(sitok-facility.html)의 "점검 보고서" 칸.

- `GET  /sitok/facilities/{id}/reports` — 회차 목록 + 새 회차 기본값.
- `POST /sitok/facilities/{id}/reports` — 새 회차(틀 = 직전 회차 결과 한글이 있으면 자동으로).
- `PATCH/DELETE /sitok/reports/{id}` — 고치기·지우기.
- `POST /sitok/reports/{id}/source` — 지난 보고서 한글(hwp·hwpx) 올리기 = 전회차 보고서(데이터용). hwp는 작업 프로그램이 hwpx로 바꿈.
- `POST /sitok/facilities/{id}/reports/past` — 이미 낸 보고서 한글 등록 = 그 회차(연도·반기·기간은 결과표에서)를 "만듦"으로 → 다음 회차의 전회차 보고서.
10/12 판 다시 잡기: 보고서는 늘 회사 원본 템플릿(server/sitok/master.py)으로 만들고, 전회차 보고서(source_hwpx — 직전 회차·이미 낸 것·올린 것)에서는
1.2.6·1.2.7 이력, 시설물 현황 값, 지난 평가, (AI 초안이 없을 때) 결과표·1.3·종합결론 글 같은 데이터만 가져온다(_base_extras).
- `POST /sitok/reports/{id}/build` — 만들기 시작(백그라운드: 값 바꾸기 → 한글 PDF(100쪽 넘으면 몇 분) → 관리대장·계약서 합본). 화면은 GET으로 진행을 봄.
- `GET  /sitok/reports/{id}` · `/sitok/reports/{id}/file/{pdf|hwpx}`.
- `POST /sitok/reports/{id}/ai/draft` — AI 초안 새로(현장 조사 결함 + 지난 회차 문장 참고, 30~90초), `GET|PUT /sitok/reports/{id}/ai` — 점검자가 고친 값.
  만들 때 이 값이 결과표·1.3 외관조사 서술·결과의 분석·종합결론·안전등급에 들어감(server/sitok/report_build.py _ai_front·_ai_body).
값 바꾸기 규칙: server/sitok/report_build.py. 점검기간·용역기간 기본값: 인수인계 10/10(민간·관급).
"""

from __future__ import annotations

import datetime
import re
import threading
import traceback
from pathlib import Path

import pymupdf
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.db import SessionLocal
from core.models_web import SitokContract, SitokEquipment, SitokFacility, SitokReport, SitokVisit, SubmitDoc, TechPerson, User
from core.stored_path import to_full
from server.api.deps import get_current_user, get_db
from server.api.routers.contract_library import doc_status
from server.api.routers.sitok import _contract_out, _facility_dir, _require_facility, contract_for, kind_known, register_path, renew_info


def _iso(d) -> str:
    return d.isoformat() if d else ""  # sitok._iso는 빈 날짜를 None으로 — 회차 화면은 "" (date 칸 value)
from server.contract_docs import hwp_queue
from server.sitok import cycle
from server.sitok.cycle import class_label
from server.sitok import civil, master, report_build as rb
from server.sitok import prev_pdf, seasons, steps

router = APIRouter(prefix="/sitok", tags=["sitok"])

HALVES = seasons.ALL + (seasons.SEISMIC,)  # 상반기·하반기 + 연 3회 해빙기·우기·동절기(10/16 — D·E등급) + 내진성능평가(10/21)
KINDS = ("정기", "정밀", "성능평가")  # 회차 종류 — 정기·정밀은 계약서 그 반기 줄에서 자동, 틀리면 직접(민재형 10/13). 성능평가 = 반기 칸도 "성능평가"(10/21)
PDF_WAIT = 1200  # 한글 PDF 대기(초) — 135쪽 보고서 + 앞에 산안법 보고서 작업이 있을 수도


class ReportIn(BaseModel):
    contract_id: int | None = None
    year: int | None = None
    half: str | None = None
    kind: str | None = None  # 정기 / 정밀 — 안 보내면 계약서 회차 줄에서
    period_start: datetime.date | None = None
    period_end: datetime.date | None = None
    report_date: datetime.date | None = None
    chief_id: int | None = None
    participant_ids: list[int] | None = None
    amount_k: str | None = None  # 이 동 점검금액(천원) — 같은 계약서를 여러 동이 같이 쓸 때


SHARED = ("period_start", "period_end", "report_date", "chief_id", "participant_ids")  # 묶인 동끼리 같은 값(회차 고치면 같이)


def _report_dir(f: SitokFacility, r: SitokReport) -> Path:
    return _facility_dir(f) / f"{r.year}_{r.half}"


def _done_msg(head: str, label: str, by_dong: dict[str, list[str]], warn: list[str]) -> str:
    """만들기 끝 안내 — 한 줄에 하나(사용자 10/15 "알림 1개당 줄바꿈"): 요약 / 끼운 자료(동마다 같으면 한 번) / ⚠ 알림마다. 화면(sitok-round.js)이 줄로 나눠 보여 줌."""
    lists = [v for v in by_dong.values() if v]
    if not lists:
        attached = ""
    elif len(lists) == len(by_dong) and all(v == lists[0] for v in lists):
        attached = f"{label}: {'·'.join(lists[0])}" + (" (동마다)" if len(by_dong) > 1 else "")
    else:
        attached = f"{label}: " + " / ".join(f"{n} {'·'.join(v)}" for n, v in by_dong.items() if v)
    return "\n".join([head] + ([attached] if attached else []) + [f"⚠ {w}" for w in warn])


def rating_result_pdf(db: Session, r: SitokReport, f: SitokFacility, rv: dict, tv: dict) -> Path:
    """상태평가 결과 자료 PDF(SafetyMan 모양, 전경사진 첫 장) — 상태평가 화면 [PDF]·부록 5.·본문 그림(5.1.3·7.3)이 같이 씀."""
    from server.api.routers.sitok_defects import _defects_for_cost
    from server.api.routers.sitok_overview import photos as overview_photos
    from server.sitok import condition

    def area(v):
        return f"{v:.1f} ㎡" if v else ""  # SafetyMan: 쉼표 없이 "2037.3 ㎡"

    def pct(v):
        return f"{v:.2f}%" if v else ""

    when = r.period_start or r.report_date or datetime.date.today()
    led = f.ledger or {}
    bi = {"name": f.name, "address": f.address, "owner": f.owner_name, "completion": f"{f.completion_date.year}년 {f.completion_date.month}월" if f.completion_date else "",
          "use": f.main_use or f.use_type, "structure": f.structure, "land_area": area(led.get("land_area")), "building_area": area(f.building_area),
          "total_area": area(f.total_area), "coverage": pct(led.get("coverage_ratio")), "far": pct(led.get("floor_area_ratio")),
          "above": f.floors_above or 0, "below": f.floors_below or 0, "kind_label": f"{r.kind or '정기'}점검",
          "when": when.isoformat()}  # 평가기관·연락처는 양식(SafetyMan 설정) 그대로
    agg = condition.aggregate(_defects_for_cost(db, r.id), tv, rv["counts"], above=f.floors_above or 0, below=f.floors_below or 0, joints=rv.get("joints"),
                              tilt_note=tv["tilt"]["note"], settlement_note=tv["settlement"]["note"])
    ph = overview_photos(db, r)
    dest = _report_dir(f, r) / "상태평가" / "상태평가결과.pdf"
    return condition.make_pdf(dest, agg, rv["result"], bi, tv, rv["prev_grade"] or rv["prev_auto"], photo=Path(ph[0][0]) if ph else None, joints=rv.get("joints"))


def _out(r: SitokReport) -> dict:
    return {"id": r.id, "contract_id": r.contract_id, "year": r.year, "half": r.half, "kind": r.kind or "정기",
            "period_start": _iso(r.period_start), "period_end": _iso(r.period_end), "report_date": _iso(r.report_date),
            "chief_id": r.chief_id, "participant_ids": r.participant_ids or [],
            "has_source": _prior(r) is not None, "source_note": r.source_note,
            "status": r.status, "message": r.message, "made_at": r.made_at.strftime("%Y-%m-%d %H:%M") if r.made_at else "",
            "has_pdf": bool(r.out_pdf and Path(r.out_pdf).exists()), "has_hwpx": bool(r.out_hwpx and Path(r.out_hwpx).exists()),
            "has_appendix": bool((r.survey or {}).get("appendix_hwpx") and Path((r.survey or {}).get("appendix_hwpx", "")).exists()),  # 정밀 부록 한글(10/13)
            "has_cover": bool((r.survey or {}).get("cover_pdf") and Path((r.survey or {}).get("cover_pdf", "")).exists()),  # 표지 + 책등(제본용, 10/19)
            # 이미 낸 보고서를 등록한 회차(만들기 없음) = 등록한 한글 "(낸 보고서).hwpx"(_register_one). 예전 조건 "만듦 + 전회차 없음"은 10/12 회사 원본으로
            # 바꾼 뒤 처음 맡는 시설물 첫 회차를 한 번 만들면 여기 걸려 현장 조사·면담 버튼이 사라졌음(동안교회 — 사용자 10/12)
            "past": r.status == "done" and Path(r.out_hwpx or "").name.endswith("(낸 보고서).hwpx"),
            "base": bool((r.survey or {}).get("base")), "amount_k": r.amount_k or "",
            "maps": len([x for x in ((r.survey or {}).get("appearance_maps") or []) if isinstance(x, dict)]),  # 부록 외관망도 파일 수(10/23, sitok_maps)
            # 회차 칸 진행 표시(10/14 형 피드백 ⑦ — 3층 구조): ✓ = 칸마다 [✓ 조사 완료]·[✓ 작성 완료]를 누름(10/18 민재형, sitok_steps.py —
            # 전엔 결함 줄·저장한 값이 하나라도 있으면 ✓), steps = {칸: {at, by}}, field = 현장 조사 진행(결함 확인 수·전경 장수)
            **{f"has_{k}": bool(steps.get(r, k)) for k in steps.STEPS}, "steps": (r.survey or {}).get("steps") or {}, "field": _field_progress(r),
            "wall": _is_wall(r), "ai_left": steps.left(r, "ai", _is_wall(r)),  # AI 초안 칸 잠금(10/18 형 요청1 — 앞 칸을 다 완료해야), 옹벽은 현황 칸 없음(10/21)
            "seismic": _seismic_progress(r)}  # 내진성능평가 회차 칸 아래 글(철근탐사 줄 수·일람표 확인 필요, 10/21) — 아니면 None


def _seismic_progress(r: SitokReport) -> dict | None:
    if not seasons.is_seismic(r.half):
        return None
    from sqlalchemy.orm import object_session

    from server.sitok import rebar_schedule as RS

    db = object_session(r)
    f = db.get(SitokFacility, r.facility_id) if db is not None else None
    sv = RS.view(((f.ledger or {}) if f else {}).get("rebar_schedule"))
    files = {k: Path(str(v)).name for k, v in ((r.survey or {}).get("seismic_files") or {}).items() if v}
    from server.sitok import rebar_survey as RV

    done = sum(1 for x in RV.normalize((r.survey or {}).get("rebar"))["rows"] if RV.has_result(x))  # 미리 만든 빈 칸은 안 셈(10/22)
    return {"rebar": done, "schedule": len(sv["items"]), "schedule_need": sv["need"], "files": files,
            "only": bool(getattr(f, "seismic_only", False))}  # 내진성능평가 전용 건(0062) — 회차 화면 대신 건 화면(seismic-project.html)


def _is_wall(r: SitokReport) -> bool:
    """회차의 시설물이 옹벽인지(server/sitok/kinds.is_wall) — 회차 화면 단계·만들기 분기."""
    from sqlalchemy.orm import object_session

    from server.sitok import kinds as _kinds

    db = object_session(r)
    f = db.get(SitokFacility, r.facility_id) if db is not None else None
    return bool(f) and _kinds.is_wall(f)


def _field_progress(r: SitokReport) -> dict:
    """현장 조사 진행(10/18 형) — 회차 화면 카드의 "결함 12/125 확인 · 전경 3장"과 완료 표시(survey.steps.field {at, by}, sitok_steps.py)."""
    from sqlalchemy.orm import object_session

    from core.models_web import SitokDefect

    db = object_session(r)
    checks = [c for (c,) in db.query(SitokDefect.check).filter(SitokDefect.report_id == r.id)] if db is not None else []
    return {"done": steps.get(r, "field"), "defects": len(checks), "checked": sum(1 for c in checks if c), "overview": len(r.overview or [])}


def _data_hwpx(x: SitokReport) -> str:
    """다음 회차가 데이터를 가져갈 한글 — 묶음으로 만든 회차는 합치기 전 이 동만의 한글(survey.single_hwpx), 아니면 만든 한글."""
    single = (x.survey or {}).get("single_hwpx")
    return single if single and Path(single).exists() else x.out_hwpx


def _require(db: Session, user: User, report_id: int) -> SitokReport:
    r = db.get(SitokReport, report_id)
    if r is None or r.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    return r


def _order(r: SitokReport) -> tuple:
    return (r.year, seasons.order(r.half))


def _previous(db: Session, r: SitokReport) -> SitokReport | None:
    """이 회차보다 앞선 회차 중 만든 한글이 있는 가장 최근 것."""
    rows = db.query(SitokReport).filter(SitokReport.facility_id == r.facility_id, SitokReport.id != r.id).all()
    rows = [x for x in rows if seasons.is_seismic(x.half) == seasons.is_seismic(r.half)]  # 성능평가 ↔ 정기·정밀은 서로 전회차가 아님(10/21)
    done = [x for x in rows if _order(x) < _order(r) and _data_hwpx(x) and Path(_data_hwpx(x)).exists()]
    return max(done, key=_order) if done else None


def period_defaults(c: SitokContract | None, year: int, half: str) -> dict:
    """관급: 상반기 = 착수일 ~ 상반기 완료일, 하반기 = 하반기 시작일 ~ 완수일(반기 하나 계약이면 착수 ~ 완수). 민간: 직접(현장 간 날 ~ 낸 날)."""
    if c is None or c.sector != "관급":
        return {"period_start": None, "period_end": None}
    if c.halves == "연간" and half in seasons.HALVES:
        return ({"period_start": c.start_date, "period_end": c.first_half_end} if half == "상반기"
                else {"period_start": c.second_half_start, "period_end": c.end_date})
    return {"period_start": c.start_date, "period_end": c.end_date}


def task_end(c: SitokContract | None, year: int, half: str) -> datetime.date:
    """과업지시서 "용역기간은 ○까지" — 민간 = 반기 말일(6/30·12/31), 관급 = 계약(1년 계약 상반기면 상반기 완료일)."""
    if c is not None and c.sector == "관급":
        d = c.first_half_end if c.halves == "연간" and half == "상반기" else c.end_date
        if d:
            return d
    return seasons.date_range(year, half)[1]  # 반기 말일(6/30·12/31), 연 3회는 그 시기 말일(3/31·6/30·12/31)


def _latest_contract(db: Session, facility_id: int) -> SitokContract | None:
    return (db.query(SitokContract).filter(SitokContract.facility_id == facility_id)
            .order_by(SitokContract.start_date.desc().nullslast(), SitokContract.id.desc()).first())


@router.get("/facilities/{facility_id}/reports")
def list_reports(facility_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = _require_facility(db, user, facility_id)
    rows = sorted(db.query(SitokReport).filter(SitokReport.facility_id == f.id).all(), key=_order, reverse=True)
    today = datetime.date.today()
    half = "상반기" if today.month <= 6 else "하반기"
    c = contract_for(db, f, today.year, half)  # 그 반기를 덮는 계약(10/13 — 예전엔 가장 최근 계약)
    persons = db.query(TechPerson).filter(TechPerson.company_id == user.company_id, TechPerson.active.is_(True)).order_by(TechPerson.name).all()
    from server.api.routers.sitok_groups import group_out
    return {
        "reports": [_out(r) for r in rows],
        "defaults": {"year": today.year, "half": half, "contract_id": c.id if c else None,
                     **{k: _iso(v) for k, v in period_defaults(c, today.year, half).items()}},
        "persons": [{"id": p.id, "name": p.name, "position": p.position, "sitok_grade": p.sitok_grade} for p in persons],
        "group": group_out(db, f),  # 한 보고서로 묶인 동(10/12)
        "group_contracts": _group_contracts(db, f),  # 묶인 동이면 묶음 전체 동의 계약에서 고름(한 계약서에 여러 동)
        "renew": renew_info(db, f),  # 장기·지속 계약 끝나기 전 알림(10/13)
    }


@router.get("/facilities/{facility_id}/contract-for")
def get_contract_for(facility_id: int, year: int, half: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """회차 만들기 전 — 그 반기를 덮는 계약(없으면 null + 마지막 계약: 화면이 "새 계약서를 올리세요")."""
    f = _require_facility(db, user, facility_id)
    if half not in HALVES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "시기는 상반기·하반기(연 3회면 해빙기·우기·동절기)입니다.")
    c = contract_for(db, f, year, half)
    last = _latest_contract(db, f.id)
    return {"contract": _contract_out(c) if c else None, "latest": _contract_out(last) if last else None,
            "kind": kind_known(db, c, year, half)}  # 그 반기 회차 종류(정기/정밀) — 계약서 회차 줄·계약건명에서, 모르면 null(0043, 10/14)


def _group_contracts(db: Session, f: SitokFacility) -> list[dict]:
    from server.api.routers.sitok import _contract_out
    from server.api.routers.sitok_groups import members

    out = []
    for m in members(db, f.group_id):
        for c in db.query(SitokContract).filter(SitokContract.facility_id == m.id).order_by(SitokContract.start_date.desc().nullslast()):
            out.append({**_contract_out(c), "facility": m.name})
    return out


def _new_report(db: Session, by: str, f: SitokFacility, year: int, half: str, **values) -> SitokReport:
    r = SitokReport(company_id=f.company_id, facility_id=f.id, year=year, half=half, created_by=by, **values)
    c = db.get(SitokContract, r.contract_id) if r.contract_id else None
    if r.period_start is None and r.period_end is None:
        for k, v in period_defaults(c, r.year, r.half).items():
            setattr(r, k, v)
    db.add(r)
    db.flush()
    prev = _previous(db, r)
    if prev is not None:
        r.source_hwpx, r.source_note = _data_hwpx(prev), f"직전 회차({prev.year}년 {prev.half}) 보고서"
    return r


def _group_reports(db: Session, r: SitokReport, by: str = "") -> list[tuple[SitokFacility, SitokReport]]:
    """묶음 동마다 같은 반기 회차 [(동, 회차)] 묶음 순서 — 없는 동은 만듦(점검기간·기술자는 r 것, 계약은 그 동 최근 계약)."""
    from server.api.routers.sitok_groups import members

    f = db.get(SitokFacility, r.facility_id)
    out = []
    for m in members(db, f.group_id) or [f]:
        x = r if m.id == f.id else db.query(SitokReport).filter(SitokReport.facility_id == m.id, SitokReport.year == r.year,
                                                                  SitokReport.half == r.half).first()
        if x is None:
            c = contract_for(db, m, r.year, r.half)  # 그 반기를 덮는 계약(그 동 → 묶음), 없으면 대표 동 회차의 것
            x = _new_report(db, by, m, r.year, r.half, contract_id=c.id if c else r.contract_id, kind=r.kind, **{k: getattr(r, k) for k in SHARED})
        out.append((m, x))
    return out


@router.post("/facilities/{facility_id}/reports")
def create_report(facility_id: int, body: ReportIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = _require_facility(db, user, facility_id)
    if body.kind == "성능평가" or seasons.is_seismic(body.half):  # 내진성능평가 — 반기 칸·종류 둘 다 "성능평가"(같은 해 정기 회차와 따로)
        if not f.seismic_only:  # 별개 용역(10/22) — 시특법 시설물에는 안 만듦
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "내진성능평가는 왼쪽 메뉴 보고서 자동화 › 내진성능평가에서 용역계약서·건축물대장으로 만드세요.")
        body.half, body.kind = seasons.SEISMIC, "성능평가"
    if not body.year or body.half not in HALVES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "연도와 반기를 고르세요.")
    if db.query(SitokReport).filter(SitokReport.facility_id == f.id, SitokReport.year == body.year, SitokReport.half == body.half).first():
        raise HTTPException(status.HTTP_409_CONFLICT, f"{body.year}년 {'내진성능평가' if seasons.is_seismic(body.half) else body.half} 회차가 이미 있습니다.")
    vals = body.model_dump(exclude_unset=True, exclude={"year", "half"})
    if "contract_id" not in vals:  # 안 보내면 그 반기를 덮는 계약(10/13), null을 보내면 "계약 없이"
        c = contract_for(db, f, body.year, body.half)
        vals["contract_id"] = c.id if c else None
    if vals.get("kind") not in KINDS:  # 종류를 안 고르면 계약서 그 반기 줄·계약건명에서(정기/정밀), 모르면 428 → 화면이 정기/정밀을 물음(10/14 형 피드백)
        k = kind_known(db, db.get(SitokContract, vals["contract_id"]) if vals["contract_id"] else None, body.year, body.half)
        if k is None:
            raise HTTPException(status.HTTP_428_PRECONDITION_REQUIRED, "계약서에서 회차 종류(정기/정밀)를 못 읽었습니다 — 종류를 골라 주세요.")
        vals["kind"] = k
    r = _new_report(db, user.display_name or "", f, body.year, body.half, **vals)
    if f.group_id and not seasons.is_seismic(body.half):  # 묶인 동도 같은 반기 회차(사용자 10/12 — 한 번 묶이면 계속), 내진성능평가는 건물마다 따로(10/21)
        _group_reports(db, r, user.display_name or "")
    db.commit()
    return _out(r)


@router.patch("/reports/{report_id}")
def update_report(report_id: int, body: ReportIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    data = body.model_dump(exclude_unset=True)
    if "amount_k" in data:
        data["amount_k"] = (data["amount_k"] or "").strip()
    if "kind" in data and data["kind"] not in KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "회차 종류는 정기·정밀입니다.")
    if "kind" in data and (data["kind"] == "성능평가") != seasons.is_seismic(r.half):  # 반기 칸과 짝 — 성능평가 ↔ 정기·정밀은 새 회차로
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "내진성능평가 회차와 정기·정밀 회차는 서로 바꿀 수 없습니다 — 새 회차를 만드세요.")
    for k, v in data.items():
        setattr(r, k, v)
    shared = {k: v for k, v in data.items() if k in SHARED}
    if shared and db.get(SitokFacility, r.facility_id).group_id:  # 점검기간·제출일·기술자는 묶인 동도 같이
        for _, x in _group_reports(db, r, user.display_name or ""):
            for k, v in shared.items():
                setattr(x, k, v)
    db.commit()
    return _out(r)


@router.delete("/reports/{report_id}")
def delete_report(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    if r.status == "running":
        raise HTTPException(status.HTTP_409_CONFLICT, "만드는 중에는 지울 수 없습니다.")
    for p in (r.out_hwpx, r.out_pdf):
        if p:
            Path(p).unlink(missing_ok=True)
    db.delete(r)
    db.commit()
    return {"ok": True}


def _read_hwp_upload(file: UploadFile, dest: Path) -> tuple[str, rb.Values]:
    """올린 지난 보고서 한글 → dest(hwpx)에 저장하고 결과표 값. hwp는 작업 프로그램이 hwpx로 바꾼다(17MB 6초·190MB 12초).
    결과표를 못 읽으면 400(파일은 지움)."""
    name = file.filename or "지난보고서"
    ext = Path(name).suffix.lower()
    if ext not in (".hwp", ".hwpx"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "지난 보고서 한글 파일(.hwp·.hwpx)을 올려 주세요.")
    data = file.file.read()
    if ext == ".hwp":
        try:
            data = hwp_queue.convert_via_worker(data, ".hwp", to="hwpx", wait=170)
        except RuntimeError as err:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(err)) from err
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    try:
        return name, rb.read_old(dest)
    except Exception as err:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err


def _is_precision(hwpx: Path) -> bool:
    """정밀안전점검 보고서인지 — 결과표 용역명에 "정밀"."""
    try:
        return "정밀" in (rb.read_old(hwpx).title or "")
    except Exception:  # noqa: BLE001
        return False


def _chapter_count(hwpx: Path) -> int:
    """보고서 시설물편 장 수(여러 동 묶음 보고서면 2 이상)."""
    import zipfile

    from lxml import etree

    from server.sitok import merge

    with zipfile.ZipFile(hwpx) as z:
        secs = rb._sections(z)
        return len(merge._chapters(etree.fromstring(z.read(secs[2])))) if len(secs) > 2 else 1


def _register_one(db: Session, user: User, f: SitokFacility, src: Path, name: str) -> SitokReport:
    """한 동 지난 보고서 한글(src) → 그 회차(없으면 만듦)를 "만듦"으로."""
    old = rb.read_old(src)
    if not old.year or old.half not in HALVES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "보고서의 연도·반기를 결과표 용역명에서 찾지 못했습니다.")
    r = db.query(SitokReport).filter(SitokReport.facility_id == f.id, SitokReport.year == old.year, SitokReport.half == old.half).first()
    if r is None:
        c = contract_for(db, f, old.year, old.half)
        r = SitokReport(company_id=user.company_id, facility_id=f.id, year=old.year, half=old.half, contract_id=c.id if c else None,
                        created_by=user.display_name or "")
        db.add(r)
    elif r.status == "running":
        raise HTTPException(status.HTTP_409_CONFLICT, "그 회차를 만드는 중입니다.")
    r.period_start, r.period_end = old.period_start, old.period_end
    if old.report_month:
        r.report_date = datetime.date(old.report_month[0], old.report_month[1], 1)
    kind = "정밀" if "정밀" in (old.title or "") else "정기"  # 용역명에 "정밀"이면 정밀 회차(10/14 숭의 2026 상반기 정밀 등록)
    r.kind = kind
    if old.grade or old.findings:  # 결과표 안전등급·점검 주요결과 → 다음 회차 점검이력·전차 검토가 씀
        r.ai = {**(r.ai or {}), "grade": old.grade or (r.ai or {}).get("grade", ""), "findings": old.findings or (r.ai or {}).get("findings", [])}
    dest = _report_dir(f, r) / f"{old.year}년 {old.half} {kind}안전점검 보고서_{f.name}(낸 보고서).hwpx"
    dest.parent.mkdir(parents=True, exist_ok=True)
    src.replace(dest)
    r.out_hwpx, r.out_pdf, r.status, r.made_at = str(dest), "", "done", datetime.datetime.now()
    r.source_note = r.source_note or "이미 낸 보고서"
    r.message = f"이미 낸 보고서 등록({name}) — 다음 회차가 이력·시설물 현황 등 데이터를 여기서 가져옵니다"
    later = [x for x in db.query(SitokReport).filter(SitokReport.facility_id == f.id, SitokReport.id != r.id).all() if _order(x) > _order(r) and x.status != "running"]
    if later:  # 바로 다음 회차가 "직전 회차" 보고서를 전회차로 쓰고 있었으면(지운 시험 회차 등) 이제 이 보고서로(10/14 숭의 42·43)
        nxt = min(later, key=_order)
        if not nxt.source_hwpx or (nxt.source_note or "").startswith("직전 회차") or not Path(nxt.source_hwpx).exists():
            nxt.source_hwpx, nxt.source_note = str(dest), f"직전 회차({old.year}년 {old.half} {kind}) 보고서"
    return r


@router.post("/facilities/{facility_id}/reports/past")
def register_past(facility_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """이미 낸 보고서 등록(10/10) — 그 회차가 없으면 만들고, 있으면 결과 한글만 이것으로. 상태 "만듦"(PDF는 없음) → 다음 회차가 이 데이터를 가져감.
    묶인 시설물이고 여러 동 보고서(시설물편 장 2개 이상)면 동마다 나눠(merge.split, 장 순서 = 묶음 순서) 동마다 등록(10/12)."""
    f = _require_facility(db, user, facility_id)
    tmp = _facility_dir(f) / "_올림_지난보고서.hwpx"
    name, _ = _read_hwp_upload(file, tmp)
    r = register_prior_file(db, user, f, tmp, name)
    db.commit()
    return _out(r)


def register_prior_file(db: Session, user: User, f: SitokFacility, tmp: Path, name: str) -> SitokReport:
    """지난 보고서 hwpx(tmp) 등록 — 묶인 시설물이고 여러 동 보고서면 동마다 나눠(장 순서 = 묶음 순서). f의 회차를 돌려줌(commit은 부른 쪽)."""
    from server.api.routers.sitok_groups import members
    from server.sitok import merge, precision_merge

    precise = _is_precision(tmp)
    n = precision_merge.part_count(tmp) if precise else _chapter_count(tmp)
    ms = members(db, f.group_id)
    if n >= 2 and len(ms) >= 2:
        mine = None
        for k, m in enumerate(ms[:n], 1):
            part = _facility_dir(m) / f"_올림_지난보고서_{k}.hwpx"
            part.parent.mkdir(parents=True, exist_ok=True)
            (precision_merge.split if precise else merge.split)(tmp, k, part)  # 정밀 묶음은 구역 2개·앞부분 묶음이 달라 따로(10/14)
            x = _register_one(db, user, m, part, f"{name} — {k}장")
            mine = x if m.id == f.id else mine
        tmp.unlink(missing_ok=True)
        if len(ms) != n:
            mine.message += f" · ⚠ 보고서는 {n}동, 묶음은 {len(ms)}동 — 장 순서대로 앞에서부터 맞췄습니다"
        return mine
    return _register_one(db, user, f, tmp, name)


@router.post("/reports/{report_id}/source")
def upload_source(report_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """지난 보고서 한글 → 이 회차의 전회차 보고서(데이터). 여러 동 보고서면 이 동 장만 남겨서(묶음 순서 = 장 순서)."""
    from server.api.routers.sitok_groups import group_out
    from server.sitok import merge

    r = _require(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    dest = _report_dir(f, r) / "틀_지난보고서.hwpx"
    name, old = _read_hwp_upload(file, dest)
    g = group_out(db, f)
    if g and _chapter_count(dest) >= 2:
        whole = dest.with_name("틀_지난보고서_묶음.hwpx")
        dest.replace(whole)
        merge.split(whole, g["index"], dest)
        old = rb.read_old(dest)
    r.source_hwpx, r.source_note = str(dest), f"올린 파일: {name} ({old.year}년 {old.half} · {old.name})"
    db.commit()
    return _out(r)


def _prior(r: SitokReport) -> Path | None:
    """전회차 보고서(데이터만 가져옴, 10/12) — 직전 회차가 만든 한글 / 이미 낸 보고서 / 올린 지난 보고서. 없으면 처음 맡는 시설물.
    10/11 "회사 기본 틀로 시작" 회차(survey.base)의 source_hwpx는 다른 시설물 보고서라 전회차가 아님."""
    if (r.survey or {}).get("base"):
        return None
    return Path(r.source_hwpx) if r.source_hwpx and Path(r.source_hwpx).exists() else None


def service_title(name: str, r: SitokReport) -> str:
    """용역명 = 표지 문구(10/19 민재형 "용역명도 표지문구랑 동일하게") — "○○에 대한 2026년 하반기 정기안전점검 보고서",
    ○○ = 시설물명(FMS) 또는 묶음·분권은 "1장 시설물명 등 N개소"(merge.cover_name)."""
    return f"{name}에 대한 {r.year}년 {r.half} {r.kind or '정기'}안전점검 보고서"


def _new_values(db: Session, r: SitokReport, old: rb.Values, prior: rb.Values | None) -> tuple[rb.Values, list[str]]:
    """이 회차의 새 값 + 경고(빈 칸·수료증 유효기간). old = 회사 원본(광숭초) 값 — 바뀌어야 할 것. 값은 시설물(관리대장)·계약 → 없으면 전회차 보고서."""
    f = db.get(SitokFacility, r.facility_id)
    c = db.get(SitokContract, r.contract_id) if r.contract_id else None
    warn: list[str] = []
    p = prior or rb.Values()
    new = rb.Values(**{k: getattr(old, k) for k in vars(old)})
    new.name, new.year, new.half = f.name or p.name or "-", r.year, r.half
    new.title = service_title(new.name, r)  # 용역명 = 표지 문구(10/19 민재형 — 전엔 전회차 용역명 모양에 연도·반기·이름만 바꿈)
    new.owner = f.owner_name or p.owner or "-"
    new.address = f.address or p.address or "-"
    new.completion = f.completion_date or p.completion
    if not new.completion:
        warn.append("준공일이 없어 결과표 준공일이 \"-\"입니다 — 알면 시설물 정보에 넣으세요")
    if f.structure and f.total_area:
        floors = f"지상 {f.floors_above}층" if f.floors_above else ""
        if f.floors_below:
            floors += f", 지하 {f.floors_below}층"
        new.scale = f"형식 : {f.structure}, 연면적 : {f.total_area:,.1f} m², {floors}".rstrip(", ")
    else:
        new.scale = p.scale or "-"
    new.rep, new.amount_k = p.rep or "-", p.amount_k or "-"
    holder = str((f.ledger or {}).get("holder") or "").strip()  # 결과표 대표자 = 관리대장 소유주(10/21 사용자 — 전엔 계약서 대표자)
    if c is not None:
        new.rep = c.rep_name or new.rep
        if c.amount:
            per_half = c.amount / 2 if c.sector == "관급" and c.halves == "연간" else c.amount
            new.amount_k = f"{round(per_half / 1000):,}"
        # 계약 회차 줄의 이번 반기 금액(동별 금액이면 이 동 것, 10/15) — 민간만(관급은 나라장터 금액을 반기로 나누는 위 방식 그대로)
        by_round = civil.amount_for(c.rounds, r.year, r.half, f.name) if c.sector == "민간" else None
        if by_round:
            new.amount_k = f"{round(by_round / 1000):,}"
    else:
        warn.append("계약을 고르지 않아 대표자·점검금액은 전회차 보고서 값입니다" if prior else "계약을 고르지 않아 대표자·점검금액이 비었습니다")
    if (r.amount_k or "").strip():  # 이 동 점검금액(같은 계약서를 여러 동이 같이 쓸 때 — 회차에서 넣음)
        new.amount_k = r.amount_k.strip()
    if holder:
        new.rep = holder
    else:
        warn.append("시설물 칸 소유주(관리대장 소유자)가 비어 결과표 대표자는 " + ("계약서 대표자" if c is not None and c.rep_name else "전회차 보고서") + " 값입니다")
    new.period_start, new.period_end = r.period_start, r.period_end
    rd = r.report_date or r.period_end or datetime.date.today()
    new.report_month = (rd.year, rd.month)
    new.task_end = task_end(c, r.year, r.half)
    ids = [x for x in [r.chief_id, *(r.participant_ids or [])] if x]
    people = [db.get(TechPerson, i) for i in ids]
    if people:
        new.persons = [(p.name, p.sitok_grade or g) for p, (_, g) in zip(people, old.persons + [("", "")] * len(people))]
        if len(people) != len(old.persons):
            warn.append(f"기술자 수가 지난 보고서({len(old.persons)}명)와 달라 앞의 {min(len(people), len(old.persons))}명만 바꿨습니다")
    on = r.period_end or datetime.date.today()
    for p in people:
        edu = db.query(SubmitDoc).filter(SubmitDoc.person_id == p.id, SubmitDoc.kind == "sitok_edu").first()
        st = doc_status(edu, on)
        if st == "expired":
            warn.append(f"{p.name} 정밀안전진단 교육 수료증 유효기간이 지났습니다({edu.valid_until})")
        elif st in ("", "nodate"):
            warn.append(f"{p.name} 정밀안전진단 교육 수료증이 없거나 수료일이 없습니다(시특법 설정)")
    return new, warn


def _blank_jpg() -> Path:
    """대표사진 남는 칸에 넣을 흰 그림(한 번 만들어 둠)."""
    from server.api import storage
    p = storage.SYSTEM_DIR / "시특법_흰그림.jpg"
    if not p.exists():
        from PIL import Image
        p.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (400, 300), "white").save(p, "JPEG")
    return p


def _extras(db: Session, r: SitokReport) -> rb.Extras:
    """설정 값 — 등록증·수료증(앞부분은 기술자 순서, 부록은 책임기술자)·책임기술자 자격, 사용 장비 표, 명단 직위."""
    ex = rb.Extras()
    reg = db.query(SubmitDoc).filter(SubmitDoc.company_id == r.company_id, SubmitDoc.person_id.is_(None), SubmitDoc.kind == "sitok_reg").first()
    if reg is not None:
        ex.images[("sitok_reg", None)] = reg.file
    ids = [x for x in [r.chief_id, *(r.participant_ids or [])] if x]
    for i, pid in enumerate(ids):
        p = db.get(TechPerson, pid)
        if p is None:
            continue
        ex.positions[p.name.replace(" ", "")] = p.position
        docs = {d.kind: d.file for d in db.query(SubmitDoc).filter(SubmitDoc.person_id == pid)}
        if docs.get("sitok_edu"):
            ex.images[("sitok_edu", i)] = docs["sitok_edu"]
            if i == 0:
                ex.images[("sitok_edu", "chief")] = docs["sitok_edu"]
        if i == 0 and docs.get("sitok_license"):
            ex.images[("sitok_license", "chief")] = docs["sitok_license"]
    ex.ai = (r.ai or {}).get("final") or None
    if ex.ai and ex.ai.get("items"):
        ex.ai = {**ex.ai, "grade": rb.eval_score(ex.ai["items"])["grade"] or ex.ai.get("grade")}
    f = db.get(SitokFacility, r.facility_id)
    ex.template = f.template
    eq = (db.query(SitokEquipment).filter(SitokEquipment.company_id == r.company_id, SitokEquipment.active.is_(True))
          .order_by(SitokEquipment.sort, SitokEquipment.id).all())
    ex.equipment = [(e.name, e.model, e.purpose, [to_full(x) for x in (e.photos or [])]) for e in eq]
    from server.api.routers.sitok_defects import cost_rows, priority_rows, summary_rows
    from server.api.routers.sitok_settings import prices
    ex.survey = r.survey or {}  # 비어 있어도 1.2.8은 "변경사항없음"으로 새로
    from server.api.routers.sitok_overview import photos as overview_photos
    ex.overview = overview_photos(db, r)  # 전경사진(없으면 지난 회차 그대로)
    from server.sitok import parts as P  # 1.3 6) 공중이용·7) 기타시설 표 = 현장 화면 탭 사진(10/12)
    ex.parts = P.build_input(r.parts, _report_dir(f, r))
    from server.sitok import drawings as D  # 첨부 도면이 없으면 1.2.9 "-후면첨부-" → "-"(10/12)
    ex.has_drawings = bool(D.items(f, "attach", _facility_dir(f)))
    if not P.recorded(r.parts):
        ex.notes.append("공중이용·기타시설 탭에 사진이 없어 6) 표는 모두 \"해당없음\", 7) 표는 \"-\"입니다(현장 조사 → 🚶 공중이용·🧱 기타시설)")
    ex.blank = str(_blank_jpg())
    from server.api.routers.sitok_defects import method_map
    methods = method_map((ex.ai or {}).get("methods"))  # AI 초안 보수공법(없으면 결함유형별 기본 공법)
    ex.summary = summary_rows(db, r.id, methods)  # 9쪽 요약표·우선순위·개략공사비·1.3 대표사진 = 현장 조사 결함으로
    if ex.summary:
        ex.priority = priority_rows(db, r.id, methods)
        ex.cost = cost_rows(db, r.id, prices(db, r.company_id), methods)
        from server.api.routers.sitok_defects import rep_photos
        ex.rep_photos = rep_photos(db, r.id)
    else:  # 결함이 없으면 원본 표(다른 시설물 것)가 남지 않게 "-" 한 줄
        ex.summary = [("-", "-", "-", ["특이사항 없음"], ["-"])]
        ex.priority = [("-", "-", "특이사항 없음", "-", "-", "-", "-")]
        ex.cost = ([("-", "-", "-", "-", "-", "-", "-")], 0)
        ex.notes.append("현장 조사 결함이 없어 요약표·우선순위·개략공사비가 \"특이사항 없음\"입니다")
    from server.sitok import good as G  # 상태양호 사진·강재 해당없음·학교 내진보강(10/19 형 B3·B5)
    g = G.norm(r.survey)
    ex.rep_photos = G.add_to_rep(ex.rep_photos, r.survey, _report_dir(f, r))
    if g["steel_na"] and ex.ai:
        ex.ai = {**ex.ai, "sections": {**(ex.ai.get("sections") or {}), "steel": G.STEEL_NA_TEXT}}
    if (f.template or "") == "3종학교":
        ex.seismic, ex.seismic_base = g["seismic"], str(_report_dir(f, r))
    return ex


def _ledger_range(src: str, key: tuple[str, str] | None, seen: set) -> tuple[int, int] | None:
    """관리대장 PDF에서 끼울 쪽 (처음, 끝) — 여러 건물을 모은 것("종합" 관리대장)이면 그 동 것만(시설물번호·이름으로), 못 맞추면 아직 안 넣은 건물들.
    10/23 형 "관리대장 3개만 들어가야 하는데 5개(서관·다목적 2번)" — 본관 카드에 3동 종합 10쪽, 서관·다목적은 나눈 3쪽이라 겹쳤음.
    seen = 이미 넣은 시설물번호(겹침 빼기). 넣을 게 없으면 None."""
    from server.sitok import reader

    starts = reader.ledger_starts(Path(src))
    with pymupdf.open(src) as add:
        n = len(add)
        if len(starts) < 2:
            no = re.findall(r"[A-Z]{2}\d{4}-\d{7}", "".join(add[starts[0] if starts else 0].get_text().split())[:300])
            if no and no[0] in seen:
                return None
            seen.update(no[:1])
            return 0, n - 1
        bounds = [0] + starts[1:] + [n]
        chunks = []
        for k in range(len(starts)):
            head = "".join(add[starts[k]].get_text().split())[:300]
            no = re.findall(r"[A-Z]{2}\d{4}-\d{7}", head)
            chunks.append((bounds[k], bounds[k + 1] - 1, no[0] if no else "", head))
    if key:
        fno, name = (key[0] or "").replace(" ", ""), (key[1] or "").replace(" ", "")
        mine = [c for c in chunks if (fno and c[2] == fno) or (not fno and name and name in c[3])]
        if mine:
            seen.add(mine[0][2])
            return mine[0][0], mine[0][1]
    keep = [c for c in chunks if not c[2] or c[2] not in seen]
    if not keep:
        return None
    seen.update(c[2] for c in keep if c[2])
    return keep[0][0], keep[-1][1]  # 이어진 쪽만 끼울 수 있어 처음~끝(사이 겹침은 드묾)


def _merge(pdf: Path, ledgers: list[str], contracts: list[str], keys: list | None = None, warn: list | None = None) -> list[str]:
    """부록 간지 뒤에 관리대장(동마다 차례로)·계약서(계약서마다) PDF를 끼운다(간지 쪽을 글자로 찾음). 끼운 것 이름들.
    keys = 관리대장마다 (시설물번호, 시설물명) — 종합 관리대장이면 그 동 것만(_ledger_range). 간지를 못 찾으면 warn에 안내(10/23 — 계약서가 말없이 빠졌음)."""
    doc = pymupdf.open(pdf)
    done = []
    plan = [("시설물관리대장", list(zip(ledgers, keys or [None] * len(ledgers))), ("부록.1", "관리대장")),
            ("계약서", [(c, None) for c in contracts], ("부록", "계 약 서"))]
    for label, srcs, keys_ in reversed(plan):  # 뒤쪽부터 끼워야 앞쪽 쪽 번호가 안 밀림
        srcs = [(s, k) for s, k in srcs if s and Path(s).exists()]
        if not srcs:
            continue
        page = next((i for i in range(len(doc) - 1, -1, -1)
                     if all(k in doc[i].get_text() for k in keys_) and len(doc[i].get_text().strip()) < 80), None)
        if page is None:
            if warn is not None:
                warn.append(f"부록 '{label}' 간지 쪽을 못 찾아 {label} PDF를 못 끼웠습니다 — 손으로 확인하세요")
            continue
        at = page + 1
        seen: set = set()
        for src, key in srcs:
            rng = _ledger_range(src, key, seen) if label == "시설물관리대장" else None
            if label == "시설물관리대장" and rng is None:
                continue
            with pymupdf.open(src) as add:
                first, last = rng or (0, len(add) - 1)
                # 올린 PDF가 지난 보고서에서 잘라낸 것이면 첫 장이 같은 간지 — 빼고 끼움(10/10 평택 견본)
                while first < last and all(k in add[first].get_text() for k in keys_) and len(add[first].get_text().strip()) < 80:
                    first += 1
                doc.insert_pdf(add, from_page=first, to_page=last, start_at=at)
                at += last - first + 1
        done.append(label)
    tmp = pdf.with_suffix(".merge.pdf")
    doc.save(tmp, garbage=3, deflate=True)
    doc.close()
    tmp.replace(pdf)
    return list(reversed(done))


def _divider_page(doc, like, text: str) -> None:
    """묶음 사진첩 앞 간지 "부록2-1. ○○"(견본 모양 — 가운데 큰 글씨) 한 쪽을 doc 끝에 — server/sitok/precision_merge._divider_page와 같은 것(10/14 한 곳으로)."""
    from server.sitok.precision_merge import _divider_page as make

    make(doc, like, text)


def _insert_albums(db: Session, reps: list[SitokReport], names: list[str], pdf: Path) -> bool:
    """현장 조사 결함이 있으면 외관조사 사진첩(결함현황표·사진표)을 만들어 부록2 간지 뒤에 끼움(10/11 5-2). 여러 동이면 동마다
    "부록2-N. 동 이름" 간지 + 그 동 사진첩(견본 숭의교회)."""
    from server.api.routers.sitok_defects import album_floors
    from server.sitok import album_make

    books = []
    for k, (r, name) in enumerate(zip(reps, names), 1):
        floors = album_floors(db, r.id)
        if floors:
            album = pdf.with_name(f"외관조사 사진첩_{k}.pdf" if len(reps) > 1 else "외관조사 사진첩.pdf")
            album_make.make(floors, album)
            books.append((k, name, album))
    if not books:
        return False
    doc = pymupdf.open(pdf)
    page = next((i for i in range(len(doc)) if "부록.2" in doc[i].get_text() and "사진첩" in doc[i].get_text()
                 and len(doc[i].get_text().strip()) < 60), None)
    if page is None:
        doc.close()
        return False
    add_all = pymupdf.open()
    for k, name, album in books:
        if len(reps) > 1:
            _divider_page(add_all, doc[page], f"부록2-{k}. {name}")
        with pymupdf.open(album) as add:
            add_all.insert_pdf(add)
    doc.insert_pdf(add_all, start_at=page + 1)
    add_all.close()
    tmp = pdf.with_suffix(".album.pdf")
    doc.save(tmp, garbage=3, deflate=True)
    doc.close()
    tmp.replace(pdf)
    return True


def _build_hwpx(db: Session, r: SitokReport, dest: Path) -> tuple[list[str], int, rb.Values]:
    """한 동 한글 만들기(회사 원본 → 종별 손질 → 이 회차 값·전회차 데이터) → (경고, 바꾼 곳 수, 새 값)."""
    f = db.get(SitokFacility, r.facility_id)
    c = db.get(SitokContract, r.contract_id) if r.contract_id else None
    folder = _report_dir(f, r)
    folder.mkdir(parents=True, exist_ok=True)
    src = folder / "틀_회사원본.hwpx"  # 회사 원본 → 이 시설물 종별(2종·3종 일반은 학교 전용 절 빼고 번호 다시)
    warn = master.prepare(master.master_path(), f.template, src, private=c is None or c.sector != "관급", legal=f.legal)
    prior = _prior(r)
    pv = rb.read_old(prior) if prior else None
    old = rb.read_old(src)
    old.grade = pv.grade if pv else _prev_grade(r)  # 1.x 안전등급 변경시 사유 — 전회차 등급과 비교(한글이 없으면 전회차 보고서 PDF, 10/18)
    new, w = _new_values(db, r, old, pv)
    warn += w
    extras = _extras(db, r)
    warn += _base_extras(db, r, f, extras, prior, pv)
    changed = rb.build(src, old, new, dest, extras)
    return warn + extras.notes, changed, new


def _fail(rows: list[SitokReport], err: Exception) -> None:
    for x in rows:
        x.status, x.message = "failed", (str(err).splitlines()[0][:300] if str(err) else type(err).__name__)
    traceback.print_exc()


def _insert_after_page(doc, keys: tuple, add_bytes: bytes | None, label: str, done: list) -> None:
    """keys 글자가 다 있는 짧은 쪽(간지) 뒤에 PDF를 끼움 — 뒤쪽부터 끼워야 앞 쪽 번호가 안 밀리므로 호출 순서는 뒤 간지 먼저."""
    if not add_bytes:
        return
    page = next((i for i in range(len(doc) - 1, -1, -1) if all(k in doc[i].get_text() for k in keys) and len(doc[i].get_text().strip()) < 120), None)
    if page is None:
        return
    with pymupdf.open(stream=add_bytes, filetype="pdf") as add:
        doc.insert_pdf(add, start_at=page + 1)
    done.append(label)


def _replace_back_page(doc, keys: tuple, add_bytes: bytes | None, label: str, done: list, wide: bool = False) -> None:
    """부록 "2-1. … 측정데이터 [후면첨부]"처럼 빈 틀만 있는 쪽 → 그 쪽의 제목(틀 위)·꼬리(틀 아래)는 그대로 두고 틀 자리에 붙는 자료 첫 쪽을 줄여 넣음,
    자료 나머지 쪽은 뒤에 그대로(형 10/15 "수기 작업 때 편의상 그런 것 — 프로그램이니 이렇게 넣고 합본 가능?"). 틀 쪽을 못 찾으면 예전처럼 간지 뒤에 끼움.
    wide = 자료 내용이 가로로 넓으면 그 쪽을 가로 쪽으로(제목은 왼쪽 위 그대로, 틀 대신 쪽 여백 안 가득 — 2-1 강도 성과표, 형 10/15 "가로로")."""
    if not add_bytes:
        return
    page = next((i for i in range(len(doc) - 1, -1, -1) if all(k in doc[i].get_text() for k in keys) and "후면첨부" in doc[i].get_text()
                 and len(doc[i].get_text().strip()) < 120), None)
    if page is None:
        _insert_after_page(doc, keys, add_bytes, label, done)
        return
    src = doc[page]
    W, H = src.rect.width, src.rect.height
    boxes = [d["rect"] for d in src.get_drawings() if d["rect"].height > H * 0.3 or d["rect"].width > W * 0.4]  # 틀 = 표 테두리 선들(세로·가로 선 따로)
    if not boxes or max(b.x1 for b in boxes) - min(b.x0 for b in boxes) < W * 0.4 or max(b.y1 for b in boxes) - min(b.y0 for b in boxes) < H * 0.3:
        _insert_after_page(doc, keys, add_bytes, label, done)
        return
    box = pymupdf.Rect(min(b.x0 for b in boxes), min(b.y0 for b in boxes), max(b.x1 for b in boxes), max(b.y1 for b in boxes))
    with pymupdf.open(stream=add_bytes, filetype="pdf") as add, pymupdf.open() as new:
        a0 = add[0]
        parts = [pymupdf.Rect(b_[:4]) for b_ in a0.get_text("blocks")] + [d["rect"] for d in a0.get_drawings()] + [r_ for info in a0.get_images(full=True) for r_ in a0.get_image_rects(info[0])]
        parts = [r_ for r_ in parts if r_.is_valid and not r_.is_empty or r_.width > 0 or r_.height > 0]
        clip = pymupdf.Rect(min(r_.x0 for r_ in parts), min(r_.y0 for r_ in parts), max(r_.x1 for r_ in parts), max(r_.y1 for r_ in parts)) if parts else a0.rect
        clip = (clip + (-6, -6, 6, 6)) & a0.rect  # 자료 쪽 여백은 빼고 내용만 크게
        top, bottom = pymupdf.Rect(0, 0, W, box.y0 - 1), pymupdf.Rect(0, box.y1 + 1, W, H)
        if wide and clip.width > clip.height * 1.15:  # 가로 쪽(H × W) — 제목 띠는 왼쪽 위 그대로, 꼬리(쪽 번호 등)는 아래 가운데
            LW, LH = H, W
            pg = new.new_page(width=LW, height=LH)
            pg.show_pdf_page(top, doc, page, clip=top)
            if bottom.height > 2:
                pg.show_pdf_page(pymupdf.Rect((LW - W) / 2, LH - bottom.height, (LW + W) / 2, LH), doc, page, clip=bottom)
            area = pymupdf.Rect(box.x0, box.y0, LW - (W - box.x1), LH - max(bottom.height, box.x0))
            k = min(area.width / max(clip.width, 1), area.height / max(clip.height, 1))
            target = pymupdf.Rect(area.x0, area.y0, area.x0 + clip.width * k, area.y0 + clip.height * k)
            target += ((area.width - target.width) / 2, 0, (area.width - target.width) / 2, 0)  # 가로 가운데
        else:
            pg = new.new_page(width=W, height=H)
            pg.show_pdf_page(top, doc, page, clip=top)
            if bottom.height > 2:
                pg.show_pdf_page(bottom, doc, page, clip=bottom)
            target = pymupdf.Rect(box.x0, box.y0, box.x1, box.y0 + min(box.height, box.width * clip.height / max(clip.width, 1)))  # 위에 붙여
        pg.show_pdf_page(target, add, 0, clip=clip)
        if len(add) > 1:
            new.insert_pdf(add, from_page=1)
        doc.insert_pdf(new, start_at=page + 1)
    doc.delete_page(page)
    done.append(label)


def _precision_appendix_pdf(db: Session, r: SitokReport, f: SitokFacility, pdf: Path) -> list[str]:
    """부록 PDF에 끼우기(간지 글자로 쪽 찾기, 뒤 간지부터): 7-5 계약서 · 5 상태평가 결과자료(③ PDF) · 3-1 탄산화 사진현황(10/14) · 2-1 강도 측정데이터(슈미트 xlsx → PDF) · 2 외관조사 사진첩 · 1 관리대장."""
    from server.api.routers.sitok_defects import album_floors
    from server.api.routers.sitok_rating import _compute as rating_view
    from server.api.routers.sitok_tests import _view as tests_view
    from server.contract_docs.attachments import to_pdf_bytes
    from server.sitok import album_make

    doc = pymupdf.open(pdf)
    done: list[str] = []
    c = db.get(SitokContract, r.contract_id) if r.contract_id else None
    if c is not None and c.contract_pdf and Path(c.contract_pdf).exists():
        _insert_after_page(doc, ("7-5", "계약서"), Path(c.contract_pdf).read_bytes(), "계약서", done)
    rv = rating_view(db, r)
    if rv["result"] is not None:
        out = rating_result_pdf(db, r, f, rv, tests_view(db, r))
        _insert_after_page(doc, ("5.", "상태평가 결과 자료"), out.read_bytes(), "상태평가 결과자료", done)
    try:  # 3-1 탄산화 사진현황(재료시험 탭 탄산화 줄 사진, 10/14)
        from server.api.routers.sitok_tests import carb_photo_pdf
        cp = carb_photo_pdf(db, r, f, _report_dir(f, r) / "재료시험" / "탄산화_사진현황.pdf")
        if cp is not None:
            _replace_back_page(doc, ("3-1", "측정데이터"), cp.read_bytes(), "탄산화 사진현황", done)
    except Exception:  # noqa: BLE001 — 사진 PDF가 안 되면 빼고 감
        traceback.print_exc()
    xlsx = _report_dir(f, r) / "재료시험" / "슈미트_시험성과표.xlsx"
    if xlsx.exists():
        try:
            _replace_back_page(doc, ("2-1", "측정데이터"), to_pdf_bytes(xlsx.read_bytes(), xlsx.name), "강도 측정데이터", done, wide=True)
        except Exception:  # noqa: BLE001 — 엑셀 변환이 안 되면 빼고 감
            pass
    floors = album_floors(db, r.id)
    if floors:
        album = pdf.with_name("외관조사 사진첩.pdf")
        album_make.make(floors, album)
        _insert_after_page(doc, ("2.", "외관조사 사진첩"), album.read_bytes(), "외관조사 사진첩", done)
    if f.ledger_pdf and Path(f.ledger_pdf).exists():
        _insert_after_page(doc, ("1.", "시설물관리대장"), Path(f.ledger_pdf).read_bytes(), "관리대장", done)
    tmp = pdf.with_suffix(".ins.pdf")
    doc.save(tmp, garbage=3, deflate=True)
    doc.close()
    tmp.replace(pdf)
    from server.api.routers.sitok_maps import insert_maps
    if insert_maps(db, [r], pdf):  # 부록 외관망도(10/23)
        done.append("외관망도")
    return done


def _convert_pushing(hwpx: Path, pdf: Path, precision: bool = False) -> None:
    """본문 한글 → PDF(정기·정밀 공용, 사용자 10/14 "정기도 같이"). 쪽 검사에서 "제목 'X'만 쪽 끝에 있음"이 나오면 그 제목 문단을 새 쪽에서 시작하게 고치고(pagecheck.push_headings) PDF를 한 번 더
    — 형 10/14 "2~3줄 애매하게 넘어가면 줄간격 늘려서 아예 넘겨버려"(결과표 '다.'부터는 precision_build._split_result_table)."""
    from server.sitok import layout_fix, pagecheck

    try:  # 머리말 용역명 한 줄로 — 칸 늘리기 → 자간 → 글자 1pt(10/19 형), 합본 용역명이 정해진 뒤라 여기서
        layout_fix.header_one_line(hwpx)
    except Exception:  # noqa: BLE001 — 못 하면 그대로
        traceback.print_exc()
    pdf.write_bytes(hwp_queue.convert_via_worker(hwpx.read_bytes(), ".hwpx", wait=PDF_WAIT))
    keep: set = set()  # 빈 자리 메우기가 일부러 넘긴 캡션·제목(다음 회에 다시 당기지 않게)
    for _ in range(2 if precision else 0):  # 정밀: 빈 쪽·쪽 아래 빈 자리에 다음 쪽 내용(사진 표는 줄여서)을 당김(형 10/15 "빈 공간에 표를 끼워 넣어 한 쪽에 쏙") — 고친 뒤 새로 생긴 것도 한 번 더
        try:
            filled = pagecheck.fill_gaps(hwpx, pdf, keep=keep)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            filled = []
        if not filled:
            break
        pdf.write_bytes(hwp_queue.convert_via_worker(hwpx.read_bytes(), ".hwpx", wait=PDF_WAIT))
    try:
        pushed = pagecheck.split_result_tables(hwpx, pdf) + pagecheck.push_headings(hwpx, pagecheck.scan(pdf, hwpx, limit=50))  # 결과표 넘침 → '다.'부터 새 쪽, 제목만 쪽 끝 → 새 쪽
    except Exception:  # noqa: BLE001 — 검사가 안 되면 그대로
        traceback.print_exc()
        pushed = []
    if not precision:
        try:  # 몇 줄만 넘어간 쪽 → 넘친 표를 그만큼 줄임(10/19 형 "고쳐도 매번 생길 수 있으니 방식으로")
            pushed += pagecheck.squeeze_overflow(hwpx, pdf)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
    try:  # 제목+표가 통째로 다음 쪽(또는 새 쪽 제목만 남고 표만) → 조금 모자라면 줄여 앞 쪽에, 많으면 나뉘게(10/19 형, 정밀도 10/23 사용자 "응")
        pushed += pagecheck.pull_tables(hwpx, pdf)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    if pushed:
        pdf.write_bytes(hwp_queue.convert_via_worker(hwpx.read_bytes(), ".hwpx", wait=PDF_WAIT))
        try:  # 고친 뒤 쪽 모양이 바뀌어 새로 생긴 "표 통째로 넘어감"도 한 번 더(10/23 형 사전검토 3.1 — 첫 PDF에선 다른 곳을 고쳤고 그 뒤 3.1이 새로 넘어갔음)
            if pagecheck.pull_tables(hwpx, pdf):
                pdf.write_bytes(hwp_queue.convert_via_worker(hwpx.read_bytes(), ".hwpx", wait=PDF_WAIT))
        except Exception:  # noqa: BLE001
            traceback.print_exc()
    try:  # 목차 쪽 번호 = 다 고친 PDF의 실제 쪽(10/19 형 — 원본 숫자·책갈피 그대로라 묶음 2·3장이 1장 쪽으로 나왔음), 바뀌면 한 번 더
        if pagecheck.fill_toc(hwpx, pdf):
            pdf.write_bytes(hwp_queue.convert_via_worker(hwpx.read_bytes(), ".hwpx", wait=PDF_WAIT))
    except Exception:  # noqa: BLE001 — 못 하면 그대로
        traceback.print_exc()


def _convert_appendix(appx: Path, apdf: Path) -> None:
    """정밀 부록 한글 → PDF — 마지막 구역(과업수행계획서·사전검토보고서)은 빈 자리 메우기 후 한 번 더(표 한 줄만 다음 쪽 등, 10/15), 표 통째로 넘어감도(10/23)."""
    from server.sitok import pagecheck

    apdf.write_bytes(hwp_queue.convert_via_worker(appx.read_bytes(), ".hwpx", wait=PDF_WAIT))
    try:
        if pagecheck.fill_gaps(appx, apdf, sections_from=-1):
            apdf.write_bytes(hwp_queue.convert_via_worker(appx.read_bytes(), ".hwpx", wait=PDF_WAIT))
    except Exception:  # noqa: BLE001 — 못 하면 그대로
        traceback.print_exc()
    try:  # 표 통째로 넘어감(10/23 — 정기 부록 "나. 과업내용"처럼, 정밀 부록은 따로 한 파일이라 여기서)
        if pagecheck.pull_tables(appx, apdf, sections_from=0):
            apdf.write_bytes(hwp_queue.convert_via_worker(appx.read_bytes(), ".hwpx", wait=PDF_WAIT))
    except Exception:  # noqa: BLE001
        traceback.print_exc()


def _run_precision_build(db: Session, r: SitokReport) -> None:
    """정밀안전점검(10/13 ⑤) — 본문 원본 → 본문 한글·PDF, 부록 원본 → 부록 한글·PDF(관리대장·사진첩·측정데이터·결과자료·계약서 끼움), 합본 PDF."""
    from server.sitok import precision_build

    f = db.get(SitokFacility, r.facility_id)
    try:
        folder = _report_dir(f, r)
        base = f"{r.year}년 {r.half} 정밀안전점검 보고서_{f.name}"
        hwpx = folder / f"{base}(본문).hwpx"
        warn, changed, _ = precision_build.build_body(db, r, hwpx)
        r.out_hwpx = str(hwpx)
        r.message = f"본문 한글 만듦({changed}곳 바꿈) — 본문 PDF로 바꾸는 중(몇 분)…"
        db.commit()
        pdf = folder / f"{base}(본문).pdf"
        _convert_pushing(hwpx, pdf, precision=True)  # 한글 → PDF(+ 제목만 쪽 끝이면 새 쪽으로 밀고 한 번 더, 형 10/14)
        from server.sitok import drawings as D
        paths = [it["path"] for it in D.items(f, "attach", _facility_dir(f))]  # 1.2 시설물 관련도면 [후면첨부] 뒤에 첨부 도면(정기 1.2.9와 같게)
        drawn = D.insert(pdf, [(1, paths)], finder=lambda pg, n: pg.search_for("시설물 관련도면") and pg.search_for("후면첨부")) if paths else []
        warn = _page_check(pdf, hwpx, drawn) + warn
        body_pages = pymupdf.open(pdf).page_count
        r.message = f"본문 {body_pages}쪽 — 부록 한글 만드는 중…"
        db.commit()
        appx = folder / f"{base}(부록).hwpx"
        w2, changed2 = precision_build.build_appendix(db, r, appx)
        warn += [x for x in w2 if x not in warn]
        r.survey = {**(r.survey or {}), "appendix_hwpx": str(appx)}
        r.message = f"본문 {body_pages}쪽 · 부록 한글 만듦({changed2}곳) — 부록 PDF로 바꾸는 중…"
        db.commit()
        apdf = folder / f"{base}(부록).pdf"
        _convert_appendix(appx, apdf)
        merged = _precision_appendix_pdf(db, r, f, apdf)
        full = folder / f"{base}_합본.pdf"
        with pymupdf.open(pdf) as a, pymupdf.open(apdf) as b, pymupdf.open() as out:
            out.insert_pdf(a)
            out.insert_pdf(b)
            out.save(full, garbage=3, deflate=True)
        pages = pymupdf.open(full).page_count
        r.survey = {**(r.survey or {}), "appendix_hwpx": str(appx), "appendix_pdf": str(apdf), "body_pdf": str(pdf)}
        r.out_pdf, r.status, r.made_at = str(full), "done", datetime.datetime.now()
        r.message = _done_msg(f"합본 {pages}쪽(본문 {body_pages}), {changed + changed2}곳 바꿈", "부록에 끼움", {f.name: merged}, warn)
    except Exception as err:  # noqa: BLE001
        _fail([r], err)
    db.commit()


def _run_precision_group_build(db: Session, r: SitokReport) -> None:
    """정밀 묶음(10/14 형 2차 답 — 정기 묶음처럼): 동마다 본문 한글(이 동만)을 만들어 한 권으로 합치고(server/sitok/precision_merge.merge_body) PDF·도면·쪽 검사,
    동마다 부록 한글·PDF(관리대장·사진첩·측정데이터·탄산화 사진현황·결과자료·계약서 끼움)를 만든 뒤 간지 구간마다 이어 붙여(merge_appendix_pdfs) 합본 PDF."""
    from core.models_web import SitokGroup
    from server.sitok import drawings as D
    from server.sitok import merge, precision_build, precision_merge

    pairs: list = []
    try:
        pairs = _group_reports(db, r)
        for _, x in pairs:
            x.status, x.message, x.kind = "running", "묶음 정밀 보고서 만드는 중…", "정밀"
        db.commit()
        _group_amounts(pairs, db)
        missing = [m.name for m, x in pairs if not (x.period_start and x.period_end)]
        if missing:
            raise ValueError("점검기간이 없는 동: " + ", ".join(missing))
        parts, warn, total = [], [], 0
        for k, (m, x) in enumerate(pairs, 1):
            single = _report_dir(m, x) / f"{x.year}년 {x.half} 정밀안전점검 보고서_{m.name}(본문·이 동만).hwpx"
            w, changed, new = precision_build.build_body(db, x, single)
            total += changed
            x.survey = {**(x.survey or {}), "single_hwpx": str(single)}
            parts.append({"hwpx": single, "name": m.name, "title": new.title})
            warn += [f"{m.name}: {s}" for s in w]
            for _, y in pairs:
                y.message = f"본문 한글 만드는 중 — {k}/{len(pairs)}동"
            db.commit()
        lead, lead_r = pairs[0]
        g = db.get(SitokGroup, lead.group_id)
        gname = (g.name if g else "") or lead.name
        gtitle = service_title(merge.cover_name(parts, gname), r)  # 묶음 용역명 = 표지 문구(10/19 형)
        folder = _report_dir(lead, lead_r)
        base = f"{r.year}년 {r.half} 정밀안전점검 보고서_{gname}"
        hwpx = folder / f"{base}(본문).hwpx"
        warn += precision_merge.merge_body(parts, hwpx, gname, gtitle)
        for _, y in pairs:
            y.out_hwpx, y.message = str(hwpx), f"{len(pairs)}동 본문 합침 — 본문 PDF로 바꾸는 중(몇 분)…"
        db.commit()
        pdf = folder / f"{base}(본문).pdf"
        _convert_pushing(hwpx, pdf, precision=True)  # 한글 → PDF(+ 제목만 쪽 끝이면 새 쪽으로 밀고 한 번 더, 형 10/14)
        chapters = [(k, [it["path"] for it in D.items(m, "attach", _facility_dir(m))]) for k, (m, _) in enumerate(pairs, 1)]
        with pymupdf.open(pdf) as doc:  # 동마다 "1.2 시설물 관련도면 [후면첨부]" 쪽 — k번째 것
            hits = [i for i, pg in enumerate(doc) if pg.search_for("시설물 관련도면") and pg.search_for("후면첨부")]
        drawn = D.insert(pdf, chapters, finder=lambda pg, n: n <= len(hits) and pg.number == hits[n - 1]) if any(p for _, p in chapters) else []
        warn = _page_check(pdf, hwpx, drawn) + warn
        body_pages = pymupdf.open(pdf).page_count
        apdfs, changed2 = [], 0
        merged_all: dict[str, list[str]] = {}  # 동 이름 → 부록에 끼운 자료
        for k, (m, x) in enumerate(pairs, 1):
            for _, y in pairs:
                y.message = f"본문 {body_pages}쪽 — 부록 만드는 중 {k}/{len(pairs)}동…"
            db.commit()
            appx = _report_dir(m, x) / f"{x.year}년 {x.half} 정밀안전점검 보고서_{m.name}(부록·이 동만).hwpx"  # 묶음 이름 = 대표 동 이름이면 합친 "(부록).pdf"와 겹쳐 이름을 달리
            w2, c2 = precision_build.build_appendix(db, x, appx)
            changed2 += c2
            warn += [f"{m.name}: {s}" for s in w2 if f"{m.name}: {s}" not in warn]
            apdf = appx.with_suffix(".pdf")
            _convert_appendix(appx, apdf)
            merged_all[m.name] = _precision_appendix_pdf(db, x, m, apdf)
            x.survey = {**(x.survey or {}), "appendix_hwpx": str(appx)}
            apdfs.append((m.name, apdf))
        apdf_all = folder / f"{base}(부록).pdf"
        warn += precision_merge.merge_appendix_pdfs(apdfs, apdf_all)
        full = folder / f"{base}_합본.pdf"
        with pymupdf.open(pdf) as a, pymupdf.open(apdf_all) as b, pymupdf.open() as out:
            out.insert_pdf(a)
            out.insert_pdf(b)
            out.save(full, garbage=3, deflate=True)
        pages = pymupdf.open(full).page_count
        msg = _done_msg(f"{len(pairs)}동 묶음 합본 {pages}쪽(본문 {body_pages}), {total + changed2}곳 바꿈", "부록에 끼움", merged_all, warn)
        now = datetime.datetime.now()
        for _, y in pairs:
            y.survey = {**(y.survey or {}), "appendix_pdf": str(apdf_all), "body_pdf": str(pdf)}
            y.out_pdf, y.status, y.made_at, y.message = str(full), "done", now, msg
    except Exception as err:  # noqa: BLE001
        _fail([y for _, y in pairs] or [r], err)
    db.commit()


def _run_build(report_id: int) -> None:
    with SessionLocal() as db:
        r = db.get(SitokReport, report_id)
        f = db.get(SitokFacility, r.facility_id)
        if seasons.is_seismic(r.half):
            return _run_seismic_build(db, r, f)  # 내진성능평가(10/21) — 우리 1~2장 원본 + 외주 3~7장 끼워 넣기
        if (r.kind or "정기") == "정밀":
            return _run_precision_group_build(db, r) if f.group_id else _run_precision_build(db, r)
        from server.sitok import kinds as _kinds
        if _kinds.is_wall(f) and (r.kind or "정기") == "정기":
            return _run_wall_build(db, r, f)  # 옹벽 정기(10/20 3단계 — 부분 파일 채워 PDF 합침, 묶음은 아직 한 곳씩)
        if f.group_id:
            return _run_group_build(db, r)
        try:
            c = db.get(SitokContract, r.contract_id) if r.contract_id else None
            folder = _report_dir(f, r)
            base = f"{r.year}년 {r.half} {r.kind or '정기'}안전점검 보고서_{f.name}"
            hwpx = folder / f"{base}.hwpx"
            warn, changed, new = _build_hwpx(db, r, hwpx)
            from server.sitok import summary_doc
            summary_doc.add_toc_line(hwpx)  # 목차 "▣ 요약문"(10/16)
            r.out_hwpx = str(hwpx)
            r.message = f"한글 만듦({changed}곳 바꿈) — PDF로 바꾸는 중(100쪽 넘으면 몇 분)…"
            db.commit()
            pdf = folder / f"{base}.pdf"
            _convert_pushing(hwpx, pdf)  # 한글 → PDF(+ 결과표 넘침·제목만 쪽 끝이면 고치고 한 번 더, 10/14)
            drawn = _insert_drawings(pdf, [(1, f)])  # 1.2.9 뒤 첨부 도면(10/12)
            warn = _page_check(pdf, hwpx, drawn) + warn  # 관리대장·계약서 합치기 전(본문 쪽 번호 = 최종), 도면 쪽은 빼고
            if _add_summary(db, [(f, r)], new.title, hwpx, pdf, warn):  # 정기 요약문 — 목차 앞(10/16 민재형 견본)
                pass
            merged = _merge(pdf, [f.ledger_pdf], [c.contract_pdf] if c else [], [(f.fms_no, f.name)], warn)
            if _insert_albums(db, [r], [f.name], pdf):
                merged.append("외관조사 사진첩")
            from server.api.routers.sitok_maps import insert_maps
            if insert_maps(db, [r], pdf):  # 부록 외관망도(10/23 — 올린 PDF·그림을 외관망도 간지 뒤에)
                merged.append("외관망도")
            from server.api.routers.sitok_defects import missing_photo_note
            if missing_photo_note(db, r.id):  # 이번 회차 사진 없는 결함 — 사진첩 칸은 비움(사용자 10/14)
                warn.append(missing_photo_note(db, r.id))
            if _split_cover(pdf, new.title, [r]):  # 표지 + 책등은 제본용 따로(10/19 형)
                merged.append("표지·책등은 따로(제본용)")
            r.out_pdf, r.status, r.made_at = str(pdf), "done", datetime.datetime.now()
            pages = pymupdf.open(pdf).page_count
            r.message = _done_msg(f"{pages}쪽, {changed}곳 바꿈", "합본", {f.name: merged}, warn)
        except Exception as err:  # noqa: BLE001 — 이유를 남김
            _fail([r], err)
        db.commit()


def _run_wall_build(db: Session, r: SitokReport, f: SitokFacility) -> None:
    """옹벽 한 곳 정기 보고서(server/sitok/wall_build) — 옹벽 원본 한 파일(형이 합친 것, 10/21)을 채워 한글 한 파일 + PDF(관리대장·사진첩·계약서 끼움)."""
    from server.sitok import wall_build

    pairs: list = []
    try:
        if f.group_id:  # 묶음 — 곳마다 회차(없으면 만듦), 한 권(10/21 4단계 — 건축물 묶음과 같은 규칙: 표지 "첫 곳 등 N개소", 같은 계약이면 곳별 점검금액 필요)
            pairs = _group_reports(db, r)
            for _, x in pairs:
                x.status, x.message = "running", "옹벽 묶음 보고서 만드는 중…"
            db.commit()
            _group_amounts(pairs, db)
            missing = [m.name for m, x in pairs if not (x.period_start and x.period_end)]
            if missing:
                raise ValueError("점검기간이 없는 곳: " + ", ".join(missing))
        else:
            pairs = [(f, r)]
        lead_f, lead_r = pairs[0]
        folder = _report_dir(lead_f, lead_r)

        def say(msg: str) -> None:
            for _, x in pairs:
                x.message = f"옹벽 보고서 — {msg}"
            db.commit()

        name = title = ""
        if len(pairs) > 1:
            name, title = wall_book_name(db, pairs, r)
        hwpx, pdf, warn, changed = wall_build.build_many(db, pairs, folder, say, name=name, title=title)
        from server.api.routers.sitok_maps import insert_maps
        maps = insert_maps(db, [x for _, x in pairs], pdf)  # 부록 외관망도(10/23) — 옹벽 틀엔 간지가 없어 "기타 부록 참고자료" 간지 뒤
        pages = pymupdf.open(pdf).page_count
        head = f"{len(pairs)}곳 묶음 {pages}쪽, {changed}곳 채움" if len(pairs) > 1 else f"{pages}쪽, {changed}곳 채움"
        msg = _done_msg(head, "합본", {"": ["외관망도"] if maps else []}, warn)
        now = datetime.datetime.now()
        for _, x in pairs:
            x.out_hwpx, x.out_pdf, x.status, x.made_at, x.message = str(hwpx), str(pdf), "done", now, msg
    except Exception as err:  # noqa: BLE001
        _fail([x for _, x in pairs] or [r], err)
    db.commit()


def _run_seismic_build(db: Session, r: SitokReport, f: SitokFacility) -> None:
    """내진성능평가 보고서(server/sitok/seismic_build — 1차: 이름·날짜·참여기술자·결과표 가·1.1·1.2·2.2.2 철근배근 + 외주 3~7장 끼워 넣기)."""
    from server.sitok import seismic_build

    try:
        def say(msg: str) -> None:
            r.message = f"내진성능평가 보고서 — {msg}"
            db.commit()

        hwpx, pdf, warn, changed = seismic_build.build(db, r, f, _report_dir(f, r), say)
        head = warn.pop(0) if warn and warn[0].endswith("쪽") else ""
        r.out_hwpx, r.out_pdf, r.status, r.made_at = str(hwpx), str(pdf), "done", datetime.datetime.now()
        r.message = _done_msg(f"{head}, {changed}곳 채움", "합본", {"": []}, warn)
    except Exception as err:  # noqa: BLE001
        _fail([r], err)
    db.commit()


def wall_book_name(db: Session, pairs: list, r: SitokReport) -> tuple[str, str]:
    """옹벽 묶음 책 표지 이름·용역명 — 이름은 건축물 규칙(merge.cover_name "첫 곳 등 N개소"), 용역명은 곳들이 같은 계약(용역명 있음)이면 그 계약 용역명,
    아니면 표지 문구(service_title)."""
    from core.models_web import SitokGroup
    from server.sitok import merge

    lead_f = pairs[0][0]
    g = db.get(SitokGroup, lead_f.group_id) if lead_f.group_id else None
    name = merge.cover_name([{"name": m.name} for m, _ in pairs], (g.name if g else "") or lead_f.name)
    cids = {x.contract_id for _, x in pairs}
    c = db.get(SitokContract, next(iter(cids))) if len(cids) == 1 and next(iter(cids)) else None
    title = (c.title if c and c.title else "").strip() or service_title(name, r)
    return name, title


def _split_cover(pdf: Path, title: str, reps: list[SitokReport]) -> Path | None:
    """합본에서 책등 쪽을 떼어 "표지 + 책등" PDF(제본소에 따로 — 10/19 형) → 회차 survey.cover_pdf, 회차 화면 [표지(제본용) PDF]."""
    from server.sitok import layout_fix

    try:
        dest = layout_fix.split_cover_pdf(pdf, title)
    except Exception:  # noqa: BLE001 — 못 떼면 합본 그대로
        traceback.print_exc()
        return None
    for x in reps:
        sv = {k: v for k, v in (x.survey or {}).items() if k != "cover_pdf"}
        if dest:
            sv["cover_pdf"] = str(dest)
        x.survey = sv
    return dest


# ---------- 정기 요약문(10/16 민재형 견본 — 안산대 2026 상반기, server/sitok/summary_doc.py) ----------

def _book_lead(db: Session, r: SitokReport) -> SitokReport | None:
    """보고서 한 권(묶음이면 대표 동)의 회차 — 요약문 결언은 여기에(r.ai["summary"])."""
    f = db.get(SitokFacility, r.facility_id)
    if f is None or not f.group_id:
        return r
    pairs = _group_reports(db, r)
    return pairs[0][1] if pairs else r


def _summary_rows(db: Session, pairs: list) -> list[dict]:
    """동마다 AI 초안(확정) 결론·주요결과·등급 — 결언 AI에 줌."""
    from server.sitok import ai_draft

    rows = []
    for m, x in pairs:
        fin = (x.ai or {}).get("final") or {}
        g = rb.eval_score(fin["items"])["grade"] if fin.get("items") else fin.get("grade", "")
        rows.append({"name": m.name, "grade": ai_draft.grade_label(g, m.template) if g else "-", "conclusion": fin.get("conclusion") or [],
                     "findings": fin.get("findings") or []})
    return rows


def _make_summary_conclusion(db: Session, r: SitokReport, company_id: int, by: str) -> list[str]:
    """요약문 결언 AI — 묶음 동마다 결론을 묶어 씀(동 AI 초안이 다 있어야), 대표 동 회차 ai["summary"]에 저장."""
    from server.sitok import ai_draft

    f = db.get(SitokFacility, r.facility_id)
    pairs = _group_reports(db, r) if f.group_id else [(f, r)]
    lead_f, lead = pairs[0]
    from core.models_web import SitokGroup
    g = db.get(SitokGroup, lead_f.group_id) if lead_f.group_id else None
    title = f"{r.year}년 {seasons.bucket(r.half)} {(g.name if g else '') or lead_f.name} 정기안전점검 용역"
    paras = ai_draft.summary_conclusion(title, r.year, seasons.bucket(r.half), _summary_rows(db, pairs), lead_f.template, company_id)
    lead.ai = {**(lead.ai or {}), "summary": {"conclusion": paras, "made_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "by": by}}
    db.commit()
    return paras


def _summary_input(db: Session, pairs: list, title: str, warn: list, book: bool = False) -> "object":
    """요약문 값 — 동마다 관리대장 칸(현황)·AI 초안(등급·점검 주요결과)·보수물량 표(적용공법·우선순위)·전회차 등급, 결언은 대표 동 ai.summary(없으면 기본 문장).
    book = 분권(10/19 형 — 묶음 결언 AI는 다른 동 얘기도 있어 기본 문장, AI 다시 안 부름)."""
    from server.api.routers.sitok_defects import method_map, priority_rows
    from server.sitok import ai_draft
    from server.sitok import summary_doc as S

    lead_f, lead = pairs[0]
    tpl = lead_f.template or "2종"
    blds = []
    for m, x in pairs:
        fin = (x.ai or {}).get("final") or {}
        g = rb.eval_score(fin["items"])["grade"] if fin.get("items") else fin.get("grade", "")
        prio = priority_rows(db, x.id, method_map(fin.get("methods")))
        methods = list(dict.fromkeys(p[3] for p in prio if p[3] and p[3] != "-")) or ["주의관찰"]
        nums = sorted({int(p[6]) for p in prio if str(p[6]).isdigit()}) or [4]
        prev = "-"
        prior = _prior(x)
        if prior is not None:
            try:
                pg = rb._letter(rb.read_old(prior).grade)
                prev = ai_draft.grade_label(pg, m.template) if pg else "-"
            except Exception:  # noqa: BLE001
                prev = "-"
        elif _prev_grade(x):  # 전회차 한글이 없으면 전회차 보고서 PDF에서 읽은 등급(10/19 — 요약문 3.4 전차등급이 "-"이던 것)
            prev = ai_draft.grade_label(_prev_grade(x), m.template)
        floors = " / ".join(s for s in (f"B{m.floors_below}F" if m.floors_below else "", f"{m.floors_above}F" if m.floors_above else "") if s)
        blds.append(S.Building(name=m.name, cls="미지정" if m.legal is False else class_label(m),
                               year=f"{m.completion_date.year}년" if m.completion_date else "-", floors=floors or "-",
                               area=f"{m.total_area:,.2f}㎡" if m.total_area else "-", structure=m.structure or "-", prev=prev,
                               grade=ai_draft.grade_label(g, m.template) if g else "-", findings=fin.get("findings") or [],
                               methods=", ".join(methods), prio=f"{nums[0]}순위" if nums[0] == nums[-1] else f"{nums[0]}~{nums[-1]}순위"))
        if not fin:
            warn.append(f"요약문: {m.name} AI 초안이 없어 등급·점검결과가 비었습니다")
    cls = "2종" if ai_draft.is_type2(tpl) else "3종"
    label = "미지정시설물" if lead_f.legal is False else ("제2종시설물" if cls == "2종" else "제3종시설물")
    period = (f"{lead.period_start:%Y년 %m월 %d일} ∼ {lead.period_end:%Y년 %m월 %d일}" if lead.period_start and lead.period_end else "")
    s = S.Summary(title=title, period=period, year=lead.year, half=seasons.bucket(lead.half), kind="정기", cls=cls, label=label,
                  category=lead_f.kind or "건축물", buildings=blds, diag=[b.name for b in blds if b.grade in S.BAD])  # 동마다 그 동 등급 체계(10/20)
    con = [] if book else ((lead.ai or {}).get("summary") or {}).get("conclusion") or []
    if not con and not book:
        warn.append("요약문 결언은 기본 문장입니다 — AI 초안 화면 [요약문 결언 AI로 쓰기]")
    s.conclusion = con or S.fallback_conclusion(s)
    return s


def _add_summary(db: Session, pairs: list, title: str, hwpx: Path, pdf: Path, warn: list, book: bool = False) -> int:
    """정기 요약문 한글·PDF를 만들어 보고서 PDF 목차 앞에(목차 "▣ 요약문" 줄은 PDF 전에 add_toc_line) → 끼운 쪽 수. 못 하면 경고만."""
    from server.sitok import summary_doc as S

    tpl = master.master_dir() / "정기안전점검_요약문_원본.hwpx"
    if not tpl.exists():
        warn.append("요약문 원본(정기안전점검_요약문_원본.hwpx)이 없어 요약문을 빼고 만들었습니다")
        return 0
    try:
        s = _summary_input(db, pairs, title, warn, book)
        out = hwpx.with_name(hwpx.stem + "_요약문.hwpx")
        S.build(s, tpl, out)
        spdf = out.with_suffix(".pdf")
        spdf.write_bytes(hwp_queue.convert_via_worker(out.read_bytes(), ".hwpx", wait=PDF_WAIT))
        try:  # 결언이 한두 줄 다음 쪽으로 넘치면 줄 간격을 줄여, 3.4 표(동 수만큼 김)가 통째로 넘어가면 줄이거나 나눠 한 번 더(10/19 형)
            from server.sitok import pagecheck
            if pagecheck.squeeze_overflow(out, spdf, sections_from=0) + pagecheck.pull_tables(out, spdf, sections_from=0):
                spdf.write_bytes(hwp_queue.convert_via_worker(out.read_bytes(), ".hwpx", wait=PDF_WAIT))
        except Exception:  # noqa: BLE001 — 못 고치면 그대로
            traceback.print_exc()
        n = S.insert_before_toc(pdf, spdf)
        if not n:
            warn.append("요약문: 보고서에서 목차 쪽을 못 찾아 끼우지 못했습니다(요약문 한글은 따로 있음)")
        return n
    except Exception as err:  # noqa: BLE001 — 요약문이 안 돼도 보고서는 그대로
        traceback.print_exc()
        warn.append(f"요약문을 넣지 못했습니다: {str(err).splitlines()[0][:120]}")
        return 0


def _insert_drawings(pdf: Path, chapters: list[tuple[int, SitokFacility]]) -> list[int]:
    """시설물편 N장(동)의 N.2.9 관련 설계도면 쪽 뒤에 그 시설물 첨부 도면(server/sitok/drawings.py) → 끼운 쪽 번호(0부터)."""
    from server.sitok import drawings as D

    plan = [(n, [it["path"] for it in D.items(m, "attach", _facility_dir(m))]) for n, m in chapters]
    return D.insert(pdf, plan) if any(paths for _, paths in plan) else []


def _page_check(pdf: Path, hwpx: Path, skip: list[int] | None = None) -> list[str]:
    """자동 쪽 검사(10/12 사용자 — server/sitok/pagecheck.py) → 경고 한 줄(없으면 []). 검사가 실패해도 보고서는 그대로."""
    from server.sitok import pagecheck

    try:
        found = pagecheck.scan(pdf, hwpx, skip=set(skip or []))
    except Exception:  # noqa: BLE001
        return []
    return [f"쪽 확인 — {' / '.join(found)}"] if found else []


def _group_amounts(pairs: list[tuple[SitokFacility, SitokReport]], db: Session | None = None) -> None:
    """같은 계약서를 여러 동이 같이 쓰면 동별 점검금액(회차 amount_k 또는 계약 회차 줄의 동별 금액, 10/15)이 있어야 — 없으면 이상한 것이라 물어봄(사용자 10/12)."""
    shared: dict[int, list] = {}
    for m, x in pairs:
        if x.contract_id:
            shared.setdefault(x.contract_id, []).append((m, x))

    def has(m, x) -> bool:
        if (x.amount_k or "").strip():
            return True
        c = db.get(SitokContract, x.contract_id) if db is not None else None
        return bool(c and (civil.round_of(c.rounds, x.year, x.half) or {}).get("parts") and civil.amount_for(c.rounds, x.year, x.half, m.name))

    missing = [m.name for lst in shared.values() if len(lst) > 1 for m, x in lst if not has(m, x)]
    if missing:
        raise ValueError("같은 계약서를 여러 동이 같이 써서 동별 점검금액을 알 수 없습니다 — 회차의 '이 동 점검금액(천원)'을 넣어 주세요: " + ", ".join(missing))


def _run_group_build(db: Session, r: SitokReport) -> None:
    """묶음 — 동마다 한글을 만들어(합치기 전 것은 survey.single_hwpx, 다음 회차가 이 동 데이터를 여기서) 한 권으로 합친 뒤 PDF·부록."""
    from core.models_web import SitokGroup
    from server.sitok import merge

    pairs: list = []
    try:
        pairs = _group_reports(db, r)
        for _, x in pairs:
            x.status, x.message = "running", "묶음 보고서 만드는 중…"
        db.commit()
        _group_amounts(pairs, db)
        missing = [m.name for m, x in pairs if not (x.period_start and x.period_end)]
        if missing:
            raise ValueError("점검기간이 없는 동: " + ", ".join(missing))
        parts, warn, total = [], [], 0
        for k, (m, x) in enumerate(pairs, 1):
            single = _report_dir(m, x) / f"{x.year}년 {x.half} {x.kind or '정기'}안전점검 보고서_{m.name}(이 동만).hwpx"
            w, changed, new = _build_hwpx(db, x, single)
            total += changed
            x.survey = {**(x.survey or {}), "single_hwpx": str(single)}
            floors = " / ".join(s for s in (f"B{m.floors_below}F" if m.floors_below else "", f"{m.floors_above}F" if m.floors_above else "") if s)
            parts.append({"hwpx": single, "name": m.name, "title": new.title, "area": m.total_area or 0,
                          "row": [str(k), m.name, f"{m.completion_date.year}년" if m.completion_date else "-", floors or "-",
                                  f"{m.total_area:,.2f}㎡" if m.total_area else "-", m.structure or "-"]})
            warn += [f"{m.name}: {s}" for s in w]
            for _, y in pairs:
                y.message = f"한글 만드는 중 — {k}/{len(pairs)}동"
            db.commit()
        lead, lead_r = pairs[0]
        g = db.get(SitokGroup, lead.group_id)
        gname = (g.name if g else "") or lead.name
        gtitle = service_title(merge.cover_name(parts, gname), r)  # 묶음 용역명 = 표지 문구(10/19 형)
        folder = _report_dir(lead, lead_r)
        base = f"{r.year}년 {r.half} {r.kind or '정기'}안전점검 보고서_{gname}"
        hwpx = folder / f"{base}.hwpx"
        warn += merge.merge(parts, hwpx, gname, gtitle)
        from server.sitok import summary_doc
        summary_doc.add_toc_line(hwpx)  # 목차 "▣ 요약문"(10/16)
        for _, y in pairs:
            y.out_hwpx, y.message = str(hwpx), f"{len(pairs)}동 한글 합침 — PDF로 바꾸는 중(몇 분)…"
        db.commit()
        pdf = folder / f"{base}.pdf"
        _convert_pushing(hwpx, pdf)  # 한글 → PDF(+ 결과표 넘침·제목만 쪽 끝이면 고치고 한 번 더, 10/14)
        drawn = _insert_drawings(pdf, [(k, m) for k, (m, _) in enumerate(pairs, 1)])  # 동마다 N.2.9 뒤 첨부 도면(10/12)
        warn = _page_check(pdf, hwpx, drawn) + warn  # 관리대장·계약서 합치기 전(본문 쪽 번호 = 최종), 도면 쪽은 빼고
        _add_summary(db, pairs, gtitle, hwpx, pdf, warn)  # 정기 요약문 — 동마다 한 줄씩, 목차 앞(10/16)
        contracts = []
        for _, y in pairs:
            c = db.get(SitokContract, y.contract_id) if y.contract_id else None
            if c is not None and c.contract_pdf and c.contract_pdf not in contracts:
                contracts.append(c.contract_pdf)
        merged = _merge(pdf, [m.ledger_pdf for m, _ in pairs], contracts, [(m.fms_no, m.name) for m, _ in pairs], warn)
        if _insert_albums(db, [y for _, y in pairs], [m.name for m, _ in pairs], pdf):
            merged.append("외관조사 사진첩")
        from server.api.routers.sitok_maps import insert_maps
        if insert_maps(db, [y for _, y in pairs], pdf, [m.name for m, _ in pairs]):  # 부록 외관망도(10/23) — 동 차례로, 동마다 간지
            merged.append("외관망도")
        from server.api.routers.sitok_defects import missing_photo_note
        warn += [f"{m.name}: {missing_photo_note(db, y.id)}" for m, y in pairs if missing_photo_note(db, y.id)]
        cover = _split_cover(pdf, gtitle, [y for _, y in pairs])  # 표지 + 책등은 제본용 따로(10/19 형)
        if cover:
            merged.append("표지·책등은 따로(제본용)")
        pages = pymupdf.open(pdf).page_count
        msg = _done_msg(f"{len(pairs)}동 묶음 {pages}쪽, {total}곳 바꿈", "합본", {"": merged}, warn)
        now = datetime.datetime.now()
        for _, y in pairs:
            y.out_pdf, y.status, y.made_at, y.message = str(pdf), "done", now, msg
    except Exception as err:  # noqa: BLE001
        _fail([y for _, y in pairs] or [r], err)
    db.commit()


def _field_day(db: Session, r: SitokReport) -> datetime.date | None:
    """현장 간 날 — 방문 달력 그 반기 일정(여러 날이면 끝 날) > 현장 조사 [✓ 조사 완료] 날."""
    h = seasons.bucket(r.half)
    vs = [v for v in db.query(SitokVisit).filter(SitokVisit.facility_id == r.facility_id, SitokVisit.year == r.year) if seasons.bucket(v.half) == h]
    if vs:
        return max(v.plan_end or v.plan_date for v in vs)
    at = (steps.get(r, "field") or {}).get("at")
    try:
        return datetime.date.fromisoformat(str(at)[:10]) if at else None
    except ValueError:
        return None


def _precision_due(db: Session, f: SitokFacility, year: int, half: str, skip: int | None = None) -> datetime.date | None:
    """정밀 도래일 — 사용승인일(준공일)의 그해 같은 날이 그 반기 안이면 그날(10/20 형 "6/30·12/30이 아니라 사용승인일로부터 4년째 되는 날부터 반복"),
    아니면 도래주기 계산(cycle.plan)의 기한(지났으면 반기 끝)."""
    a, b = cycle.half_bounds(year, half)
    c = f.completion_date
    if c:
        try:
            ann = c.replace(year=year)
        except ValueError:  # 2/29
            ann = datetime.date(year, 2, 28)
        if a <= ann <= b:
            return ann
    due = (cycle.plan(cycle.gather(db, f, skip=skip), [(year, half)])["rounds"].get((year, half)) or {}).get("due")  # 지금 회차는 빼고
    if not due:
        return None
    d = datetime.date.fromisoformat(due)
    return d if a <= d <= b else b


def period_default(db: Session, r: SitokReport) -> tuple[datetime.date | None, datetime.date | None, str]:
    """점검기간 기본값(10/20 형) → (시작, 끝, 규칙 글) — 못 정하면 (None, None, 이유). 계약 구분(없으면 시설물 카드) 민간/관급:
    정기 — 민간 = 현장 간 날 −30일 ~ 현장 간 날, 관급 = 착수일 ~ 완수일(1년 계약 = 상반기 착수일 ~ 6/30 · 하반기 7/1 ~ 완수일).
    정밀 — 민간 = 반기 시작 ~ 정밀 도래일, 관급 = 착수일 ~ 완수일(1년 계약은 비워 둠 — 직접)."""
    f = db.get(SitokFacility, r.facility_id)
    c = db.get(SitokContract, r.contract_id) if r.contract_id else None
    sector = (c.sector if c else f.sector) or "민간"
    precise = (r.kind or "정기") == "정밀"
    h = seasons.bucket(r.half)
    if sector == "관급":
        if not (c and c.start_date and c.end_date):
            return None, None, "관급 — 계약 착수일·완수일이 없어 못 정함(계약을 고르거나 직접 넣으세요)"
        if not (c.start_date <= datetime.date(r.year, 6, 30) and c.end_date >= datetime.date(r.year, 7, 1)):  # 반기 하나 계약
            return c.start_date, c.end_date, "관급 = 착수일 ~ 완수일"
        if precise:
            return None, None, "관급 1년 계약 정밀 — 직접 넣으세요"
        if h == "상반기":
            return c.start_date, c.first_half_end or datetime.date(r.year, 6, 30), "관급 1년 계약 상반기 = 착수일 ~ 6/30"
        return c.second_half_start or datetime.date(r.year, 7, 1), c.end_date, "관급 1년 계약 하반기 = 7/1 ~ 완수일"
    if precise:
        due = _precision_due(db, f, r.year, h, r.id)
        if due is None:
            return None, None, "민간 정밀 — 도래일을 몰라(준공일·전회차 정밀점검 시기) 직접 넣으세요"
        return cycle.half_bounds(r.year, h)[0], due, "민간 정밀 = 반기 시작 ~ 정밀 도래일"
    day = _field_day(db, r)
    if day is None:
        return None, None, "민간 정기 — 현장 간 날(방문 달력·현장 조사 완료)이 아직 없음"
    return day - datetime.timedelta(days=30), day, "민간 정기 = 현장 간 날 −30일 ~ 현장 간 날"


def _fill_period(db: Session, r: SitokReport) -> str:
    """빈 점검기간을 기본값으로(묶음이면 빈 동도 같이) — 못 채우면 이유 글, 채웠거나 이미 있으면 ""."""
    if r.period_start and r.period_end:
        return ""
    s, e, why = period_default(db, r)
    if not (s and e):
        return why
    r.period_start, r.period_end = r.period_start or s, r.period_end or e
    if db.get(SitokFacility, r.facility_id).group_id:
        for _, x in _group_reports(db, r):
            if not (x.period_start and x.period_end):
                x.period_start, x.period_end = r.period_start, r.period_end
    db.commit()
    return ""


def _template_block_safe(db: Session, r: SitokReport) -> str:
    """회차 화면 보기용 — 묶음 동 회차를 새로 만들지 않게(_group_reports는 없는 동 회차를 만듦) 동 시설물만 봄."""
    from server.api.routers.sitok_groups import members
    from server.sitok import kinds as _kinds

    f = db.get(SitokFacility, r.facility_id)
    out: list[str] = []
    for m in members(db, f.group_id) or [f]:
        why = _kinds.template_block(m, r.kind or "정기")
        if why and why not in out:
            out.append(why)
    return " ".join(out)


def _template_block(db: Session, r: SitokReport) -> str:
    """이 회차(묶음이면 동마다)의 보고서 틀이 없으면 안내 글 — 형 10/21 "보고서 틀이 없는 경우 준비 중입니다, 보고서 만들기 막기"."""
    from server.sitok import kinds as _kinds

    f = db.get(SitokFacility, r.facility_id)
    if f is None:
        return ""
    if f.group_id:
        return _template_block_safe(db, r)
    return _kinds.template_block(f, r.kind or "정기")


@router.post("/reports/{report_id}/build")
def start_build(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    if r.status == "running":
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 만드는 중입니다.")
    block = _template_block(db, r)
    if block:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, block)
    if (r.kind or "정기") == "성능평가":  # 내진성능평가(10/21) — 원본 확인은 _template_block이 함
        pass
    elif (r.kind or "정기") == "정밀":  # 정밀(10/13 ⑤) — 본문 원본으로 본문 한글·PDF(부록은 다음)
        if not master.master_path("정밀본문").exists():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "정밀안전점검 본문 원본이 없습니다 — 시특법 설정에서 올리세요.")
    elif not master.master_path().exists():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "회사 원본 템플릿이 없습니다 — 시특법 설정에서 올리세요.")
    why = _fill_period(db, r)  # 비었으면 기본값으로(10/20 형 규칙)
    if why:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"점검기간(시작·끝)을 먼저 정하세요 — 회차 화면 맨 아래 ⚙ 회차 정보에서. ({why})")
    left = _build_left(db, r)
    if left:  # 10/18 형 요청1 — 칸을 다 [완료]해야 보고서 합본(제출 현황 "보고서 완료"가 진짜 끝난 것이 되게)
        raise HTTPException(status.HTTP_409_CONFLICT, "보고서를 만들기 전에 먼저 완료할 칸: " + " / ".join(left))
    r.status, r.message = "running", "만드는 중…"
    db.commit()
    threading.Thread(target=_run_build, args=(r.id,), daemon=True).start()
    return _out(r)


@router.get("/reports/{report_id}")
def get_report(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from server.api.routers.sitok import mark_view

    r = _require(db, user, report_id)
    mark_view(db, user.id, r.facility_id)  # 시설물 목록 "최근 열람순"(10/13) — 현장 조사·보고서 화면도
    f = db.get(SitokFacility, r.facility_id)
    if f.group_id and r.status != "done":  # 아직 안 만든 회차만(이미 만든·낸 보고서 회차는 그대로)
        _group_reports(db, r, user.display_name or "")  # 묶음 동 회차가 빠졌으면 만듦 — 동마다 칸을 완료해야 묶음 보고서가 열려서(10/18)
        db.commit()
    auto = None
    if not (r.period_start and r.period_end) and r.status != "done":  # 비어 있으면 만들 때 넣을 기본값(10/20)
        s, e, why = period_default(db, r)
        auto = {"start": _iso(s), "end": _iso(e), "rule": why}
    return {**_out(r), "facility_id": f.id, "facility_name": f.name,  # 회차 화면(sitok-round.html, 10/14)이 경로 표시에 씀
            "group_rounds": _group_rounds(db, f, r), "build_left": _build_left(db, r), "auto_period": auto,
            "build_block": _template_block(db, r) if not f.group_id else _template_block_safe(db, r)}  # 틀 없음 → 만들기 막음(10/21)


def _build_left(db: Session, r: SitokReport) -> list[str]:
    """보고서 만들기 전에 아직 완료 안 된 칸(10/18 형 요청1) — 한 동이면 ["면담·변경사항 조사 · 시설물 현황"],
    묶음이면 동마다 "제2장 교사동(서관) — …"(그 반기 회차가 없는 동도)."""
    f = db.get(SitokFacility, r.facility_id)
    if not f.group_id or seasons.is_seismic(r.half):  # 내진성능평가는 건물마다 따로(묶음이어도 이 회차만, 10/21)
        miss = steps.left(r, "build", _is_wall(r))
        return [" · ".join(miss)] if miss else []
    from server.api.routers.sitok_groups import members

    out = []
    for i, m in enumerate(members(db, f.group_id) or [f], 1):
        x = r if m.id == f.id else db.query(SitokReport).filter(SitokReport.facility_id == m.id, SitokReport.year == r.year, SitokReport.half == r.half).first()
        miss = steps.left(x, "build", _is_wall(x)) if x is not None else ["이 반기 회차 없음"]
        if miss:
            out.append(f"제{i}장 {m.name} — {' · '.join(miss)}")
    return out


def _group_rounds(db: Session, f: SitokFacility, r: SitokReport) -> list[dict]:
    """묶인 동마다 같은 반기 회차와 진행 표시 — 회차 화면이 현장 점검·보고서 칸을 동마다 한 줄씩(사용자 10/15 "동별로 조사가 생겨야"). 묶음 아니면 []."""
    if not f.group_id:
        return []
    from server.api.routers.sitok_groups import members

    keys = ("kind", "past", "has_field", "has_tests", "has_rating", "has_survey", "has_detail", "has_ai")
    out = []
    for i, m in enumerate(members(db, f.group_id), 1):
        x = r if m.id == f.id else db.query(SitokReport).filter(SitokReport.facility_id == m.id, SitokReport.year == r.year, SitokReport.half == r.half).first()
        o = _out(x) if x is not None else {}
        out.append({"index": i, "facility_id": m.id, "name": m.name, "report_id": x.id if x is not None else None, "current": m.id == f.id,
                    **{k: o.get(k) for k in keys}})
    return out


@router.get("/reports/{report_id}/file/{kind}")
def report_file(report_id: int, kind: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    sv = r.survey or {}
    path = (r.out_pdf if kind == "pdf" else r.out_hwpx if kind == "hwpx" else sv.get("appendix_hwpx", "") if kind == "appendix"
            else sv.get("appendix_pdf", "") if kind == "appendix_pdf" else sv.get("body_pdf", "") if kind == "body_pdf"
            else sv.get("cover_pdf", "") if kind == "cover_pdf" else "")  # cover_pdf = 표지 + 책등(제본용, 10/19)
    kind = "pdf" if kind.endswith("pdf") else kind
    if not path or not Path(path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일이 없습니다.")
    return FileResponse(path, media_type="application/pdf" if kind == "pdf" else "application/octet-stream",
                        filename=Path(path).name, content_disposition_type="inline" if kind == "pdf" else "attachment",
                        headers={"Cache-Control": "no-store"})  # 다시 만든 뒤 예전 PDF가 보이지 않게(10/12 동안교회)


def _ai_out(db: Session, r: SitokReport) -> dict:
    """AI 초안 + 단가표 공법 이름(창에서 보수공법 고르기용)."""
    from server.api.routers.sitok_settings import prices
    from server.sitok import kinds as _kinds
    from server.sitok import wall_ai

    f = db.get(SitokFacility, r.facility_id)
    lead = _book_lead(db, r)
    wall = bool(f) and _kinds.is_wall(f)
    return {**(r.ai or {}), "prices": [p.method for p in prices(db, r.company_id)], "template": f.template if f else "",
            "wall": wall, "sections_list": wall_ai.section_list() if wall else None,
            "summary": ((lead.ai or {}).get("summary") if lead is not None else None) or {}, "book": len(_group_reports(db, r)) if f and f.group_id else 1}


def _precision_ai_out(db: Session, r: SitokReport) -> dict:
    """정밀 회차 AI 창(10/13 ⑤-2) — 22항목: 기본 글(precision_text) + 저장한 글(ai.final.precision)."""
    from server.sitok import precision_ai, precision_build

    base = precision_build.defaults(db, r)["texts"]
    saved = ((r.ai or {}).get("final") or {}).get("precision") or {}
    draft = ((r.ai or {}).get("draft") or {}).get("precision") or {}
    return {"precision": True, "made_at": ((r.ai or {}).get("draft") or {}).get("made_at", ""), "edited_at": ((r.ai or {}).get("final") or {}).get("edited_at", ""),
            "edited_by": ((r.ai or {}).get("final") or {}).get("edited_by", ""),
            "items": [{"key": k, "label": lab, "where": where, "default": base.get(k, ""), "ai": draft.get(k, ""), "text": saved.get(k) or base.get(k, "")}
                      for k, lab, where in precision_ai.ITEMS]}


def _precision_ai_draft(db: Session, r: SitokReport, user: User) -> dict:
    from server.sitok import precision_ai, precision_build

    d = precision_build.defaults(db, r)
    mat = precision_ai.material(db, r, d["tv"], d["rv"], d["pr"], d["defects"], d["facility"])
    try:
        texts = precision_ai.draft(user.company_id, mat, d["texts"])
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI 초안을 만들지 못했습니다: {str(err).splitlines()[0][:200]}") from err
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    r.ai = {**(r.ai or {}), "draft": {"precision": texts, "made_at": now}, "final": {**((r.ai or {}).get("final") or {}), "precision": texts}}
    db.commit()
    return _precision_ai_out(db, r)


class DraftIn(BaseModel):
    grade: str | None = None  # "up" 한 단계 올려(좋게) · "down" 한 단계 내려 — 등급 재산정 요청(10/19 형)


def _wall_ai_draft(db: Session, r: SitokReport, f: SitokFacility, rows: list, user: User, target: str) -> dict:
    """옹벽 AI 초안(server/sitok/wall_ai) — 결함이 없어도 됨(양호 보고서). 전회차 사진 설명·상태양호·공중이용 사실을 같이 줌."""
    from server.sitok import good as G
    from server.sitok import parts as P
    from server.sitok import wall_ai

    defects = [{k: getattr(d, k) for k in ("part", "member", "dtype", "floor", "seq", "count", "width", "length", "qty", "check", "mark", "progress", "cause", "cause_note")}
               for d in rows]
    prev = [f"{d.floor} — {(d.prev or {}).get('설명') or ''}".strip(" —") for d in rows if d.prev and (d.prev or {}).get("설명")]
    spec = (f.ledger or {}).get("wall") or {}
    facility = f"{f.name} — 옹벽 {f.class_no or spec.get('class_no') or 2}종 · {spec.get('form') or f.structure or ''} · 연장 {spec.get('length') or '-'}m · 높이 {spec.get('height') or '-'}m · 준공 {_iso(f.completion_date)}"
    facts = G.facts(r.survey, "wall")
    pub = []
    try:
        pp = P.norm(r.parts)["public"]
        pub = [name for k, name in P.PUBLIC if (pp.get(k) or {}).get("file") or (pp.get(k) or {}).get("prev")]
        none = [name for k, name in P.PUBLIC if (pp.get(k) or {}).get("none")]
        if pub or none:
            facts += f"\n[공중이 이용하는 부위 사진] 찍은 항목: {', '.join(pub) or '없음'} / 해당없음: {', '.join(none) or '없음'}"
    except Exception:  # noqa: BLE001
        pass
    target_word = wall_ai.word(target) if target else ""
    prev_grade = wall_ai.word(f.safety_grade or "")
    from server.sitok import wall_manual
    form = wall_manual.form_of(spec.get("form") or "", f.name, f.kind or "")
    eval_items = wall_manual.items_for(form) if (f.template or "").startswith("3종") else None  # 3종 18항목(5단계, 10/21)
    from server.api.routers.sitok_defects import method_combos
    from server.api.routers.sitok_settings import prices
    from server.sitok import wall_collect
    ps = wall_collect.prev_summary(db, r, f)  # 요약표 전회 칸(⑫): 전회차 회차 > 전회차 PDF > 없음
    try:
        data = wall_ai.draft(facility, f"{r.year}년 {r.half} (점검기간 {_iso(r.period_start)}~{_iso(r.period_end)})", defects, prev, facts, user.company_id,
                             target_word, prev_grade, ", ".join(pub), eval_items, form, prev_rows=ps["rows"], combos=method_combos(db, r.id),
                             price_list=[(p.method, p.unit, p.price) for p in prices(db, r.company_id)])
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI 초안을 만들지 못했습니다: {str(err).splitlines()[0][:200]}") from err
    wall_ai.apply_prev(data, ps)
    if target_word:
        data["requested_grade"] = wall_ai.letter(target_word)
    data["made_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    final = dict(data)
    keep = {k: v for k, v in (r.ai or {}).items() if k == "summary"}
    r.ai = {"draft": data, "final": final, **keep}
    db.commit()
    return _ai_out(db, r)


AI_JOBS: dict[int, dict] = {}  # 회차 → AI 초안 일 {state: running/done/failed, msg, started} — API가 다시 뜨면 비어 화면은 저장된 초안을 그림


@router.post("/reports/{report_id}/ai/draft")
def ai_draft_new(report_id: int, body: DraftIn | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """AI 초안 새로 — 결과는 draft에, 점검자가 고치기 전 final도 같은 값으로(화면에서 고쳐 저장하면 final만 바뀜).
    body.grade = up/down이면 지금 등급에서 한 단계 올리거나 내린 등급으로 다시 씀(정기만, 10/19 형).
    10/21: 뒤에서 돌림 — 3종은 사진 판단·본문·18항목·요약문 결언까지 AI 여러 번이라 3분을 넘겨 그룹웨어 nginx(180초)가 504로 끊었음(서버는 계속 써서 저장됨).
    바로 {job}을 돌려주고 화면은 GET /ai/draft/state를 물어 끝나면 GET /ai. 같은 회차가 쓰는 중이면 새로 시작하지 않음(여러 번 눌러 겹쳐 돌던 것)."""
    from server.sitok import ai_draft

    r = _require(db, user, report_id)
    job = AI_JOBS.get(r.id)
    if job and job.get("state") == "running":
        return {"job": job}
    target = ""
    if body is not None and body.grade in ("up", "down"):
        fin0 = (r.ai or {}).get("final") or {}
        cur = rb._letter(str(fin0.get("grade") or ""))
        order = "BCDE" if ai_draft.is_type2(db.get(SitokFacility, r.facility_id).template) and not fin0.get("items") else "ABCDE"
        if cur not in order:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "지금 등급이 없습니다 — 먼저 AI 초안을 만드세요.")
        i = order.index(cur) + (-1 if body.grade == "up" else 1)
        if not 0 <= i < len(order):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"이미 {'가장 좋은' if body.grade == 'up' else '가장 낮은'} 등급입니다.")
        target = order[i]
    miss = steps.left(r, "ai", _is_wall(r))
    if miss:  # 10/18 형 요청1 — 앞 칸을 다 [완료]해야 AI 초안(화면 칸도 잠김)
        raise HTTPException(status.HTTP_409_CONFLICT, f"AI 초안 전에 먼저 완료할 칸: {' · '.join(miss)}")
    AI_JOBS[r.id] = {"state": "running", "msg": f"AI가 {target} 등급에 맞게 다시 쓰는 중" if target else "AI가 초안을 쓰는 중",
                     "started": datetime.datetime.now().strftime("%H:%M:%S")}
    threading.Thread(target=_ai_draft_job, args=(r.id, user.id, target), daemon=True).start()
    return {"job": AI_JOBS[r.id]}


@router.get("/busy")
def busy(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """API 안에서 뒤에서 도는 일(10/21) — 재시작 전에 확인(server/scripts/safe_restart_api.py). 보고서 만들기(DB status)·분권·AI 초안·전회차 가져오기."""
    from server.api.routers.sitok_defects import IMPORTS
    from server.api.routers.sitok_rebar import JOBS as SCHEDULE_JOBS
    from server.api.routers.sitok_split import _RUNNING

    builds = [rid for (rid,) in db.query(SitokReport.id).filter(SitokReport.status == "running")]
    return {"builds": builds, "splits": sorted(_RUNNING), "ai": [k for k, v in AI_JOBS.items() if v.get("state") == "running"],
            "imports": [k for k, v in IMPORTS.items() if (v or {}).get("state") == "running"],
            "schedules": [k for k, v in SCHEDULE_JOBS.items() if (v or {}).get("state") == "running"]}  # 구조 일람표 읽기(10/21)


@router.get("/reports/{report_id}/ai/draft/state")
def ai_draft_state(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """AI 초안 일 상태 — {state: idle/running/done/failed, msg}."""
    r = _require(db, user, report_id)
    return AI_JOBS.get(r.id) or {"state": "idle", "msg": ""}


def _ai_draft_job(report_id: int, user_id: int, target: str) -> None:
    db = SessionLocal()
    try:
        r, user = db.get(SitokReport, report_id), db.get(User, user_id)
        _ai_draft_work(db, r, user, target)
        AI_JOBS[report_id] = {"state": "done", "msg": "다 썼습니다", "at": datetime.datetime.now().strftime("%H:%M:%S")}
    except HTTPException as err:
        AI_JOBS[report_id] = {"state": "failed", "msg": str(err.detail)}
    except Exception as err:  # noqa: BLE001 — 이유를 화면에
        traceback.print_exc()
        AI_JOBS[report_id] = {"state": "failed", "msg": f"AI 초안을 만들지 못했습니다: {str(err).splitlines()[0][:200]}"}
    finally:
        db.close()


def _ai_draft_work(db: Session, r: SitokReport, user: User, target: str) -> dict:
    """AI 초안 본 일(뒤에서) — 정밀·옹벽·건축물 정기."""
    from core.models_web import SitokDefect
    from server.sitok import ai_draft

    if (r.kind or "정기") == "정밀":
        return _precision_ai_draft(db, r, user)
    f = db.get(SitokFacility, r.facility_id)
    rows = db.query(SitokDefect).filter(SitokDefect.report_id == r.id).all()
    from server.sitok import kinds as _kinds
    if _kinds.is_wall(f):
        return _wall_ai_draft(db, r, f, rows, user, target)
    if not rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "현장 조사 결함이 없습니다 — [📱 현장 조사]에서 결함을 먼저 가져오거나 입력하세요.")
    defects = [{k: getattr(d, k) for k in ("part", "member", "dtype", "floor", "seq", "count", "width", "length", "qty", "check", "mark", "progress", "cause",
                                           "cause_note")}
               for d in rows]
    prior = _prior(r)
    old = rb.old_texts(prior) if prior else ""
    facility = f"{f.name} — {f.template} · {f.use_type or f.main_use} · {f.structure} · 지상 {f.floors_above or '-'}층/지하 {f.floors_below or 0}층 · 준공 {_iso(f.completion_date)}"
    try:  # 18항목·1.4 항목 이름은 회사 원본, "지난 평가"·"지난 있다/없다"는 전회차 보고서(없으면 비움)
        m = master.master_path()
        items = rb.read_eval_items(m) if f.template.startswith("3종") else []
        before = {it["no"]: it["rating"] for it in (rb.read_eval_items(prior) if items and prior else [])}
        items = [{**it, "rating": before.get(it["no"], "")} for it in items]
        had = {_norm_key(it["name"]): it["has"] for it in (rb.read_facility_items(prior) if prior else [])}
        fac_items = [{**it, "has": had.get(_norm_key(it["name"]), False)} for it in rb.read_facility_items(m)]
        from server.api.routers.sitok_defects import method_combos
        from server.api.routers.sitok_settings import prices
        # 공중이용·기타시설 탭 사진(10/12) — AI가 먼저 사진을 보고 조사항목·상태평가기준(a~e)으로 항목별 판단 → 본 초안에 사실로
        from server.sitok import parts as P
        judged: dict = {}
        facts = ""
        if P.recorded(r.parts):
            photos = P.photo_list(r.parts, _report_dir(f, r))
            if photos:
                mine = "\n".join(f"{d['floor']} {d['seq']}번 {d['member']} {d['dtype']} {d.get('cause') or ''}" for d in defects
                                 if ai_draft.category_of(d["part"], d["member"], d["dtype"]) in ("public", "other"))
                judged = P.evaluate(user.company_id, facility, photos, mine)
            facts = P.facts(r.parts, judged)
        from server.sitok import good as G
        facts = "\n".join(x for x in (facts, G.facts(r.survey)) if x)  # 상태양호 사진·강재 해당없음(10/19)
        data = ai_draft.draft(facility, f"{r.year}년 {r.half} (점검기간 {_iso(r.period_start)}~{_iso(r.period_end)})", defects, old, user.company_id,
                              eval_items=items, fac_items=fac_items,
                              combos=method_combos(db, r.id), price_list=[(p.method, p.unit, p.price) for p in prices(db, r.company_id)],
                              parts_facts=facts, template=f.template, target=target)
        data["parts"] = P.rows(r.parts, judged)
        if G.norm(r.survey)["steel_na"]:
            data["sections"]["steel"] = G.STEEL_NA_TEXT
        if target:
            data["requested_grade"] = target  # 점검자 요청 등급(창이 나온 등급과 견줘 보여 줌)
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI 초안을 만들지 못했습니다: {str(err).splitlines()[0][:200]}") from err
    data["made_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    final = {k: v for k, v in data.items() if k not in ("stats",)}
    if final.get("items"):
        final["grade"] = rb.eval_score(final["items"])["grade"] or final.get("grade")
    keep = {k: v for k, v in (r.ai or {}).items() if k == "summary"}
    r.ai = {"draft": data, "final": final, **keep}
    db.commit()
    try:  # 요약문 결언 — 이 보고서(묶음이면 동 전부) AI 초안이 다 있으면 동마다 결론을 묶어 바로(민재형 10/16 "AI 초안 작성에 넣어줘")
        pairs = _group_reports(db, r) if f.group_id else [(f, r)]
        if all(((x.ai or {}).get("final")) for _, x in pairs):
            _make_summary_conclusion(db, r, user.company_id, user.display_name or "")
    except Exception:  # noqa: BLE001 — 결언은 [요약문 결언 AI로 쓰기]로 다시
        traceback.print_exc()
    return _ai_out(db, r)


@router.post("/reports/{report_id}/ai/summary")
def ai_summary_new(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """요약문 3.6 결언 AI로 다시(동마다 확정 AI 초안의 결론·주요결과를 묶음)."""
    r = _require(db, user, report_id)
    try:
        _make_summary_conclusion(db, r, user.company_id, user.display_name or "")
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"요약문 결언을 쓰지 못했습니다: {str(err).splitlines()[0][:200]}") from err
    return _ai_out(db, r)


@router.put("/reports/{report_id}/ai/summary")
def ai_summary_save(report_id: int, body: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """요약문 결언 고친 글 — {conclusion: [문단]} → 대표 동 회차에."""
    r = _require(db, user, report_id)
    lead = _book_lead(db, r)
    paras = [str(x).strip() for x in (body.get("conclusion") or []) if str(x).strip()]
    lead.ai = {**(lead.ai or {}), "summary": {**((lead.ai or {}).get("summary") or {}), "conclusion": paras, "edited_by": user.display_name or "",
                                              "edited_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}}
    db.commit()
    return _ai_out(db, r)


@router.get("/reports/{report_id}/ai")
def ai_get(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    if (r.kind or "정기") == "정밀":
        return _precision_ai_out(db, r)
    return _ai_out(db, r) if r.ai else {}


@router.put("/reports/{report_id}/ai")
def ai_save(report_id: int, body: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """점검자가 고친 값(final) 저장 — 키는 ai_draft.draft 결과와 같음. 등급은 A~E만. 정밀 회차는 {precision: {키: 글}}."""
    r = _require(db, user, report_id)
    if (r.kind or "정기") == "정밀":
        from server.sitok import precision_ai

        texts = {k: str((body.get("precision") or {}).get(k) or "").strip() for k in precision_ai.KEYS}
        if texts.get("diag") not in ("필요", "불필요", ""):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "정밀안전진단 실시여부는 필요/불필요입니다.")
        final = {**((r.ai or {}).get("final") or {}), "precision": texts, "edited_by": user.display_name or "", "edited_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
        r.ai = {**(r.ai or {}), "final": final}
        db.commit()
        return _precision_ai_out(db, r)
    keys = ("critical", "public", "findings", "repairs", "next_focus", "sections", "conclusion", "grade", "grade_reason", "items", "eval_opinion", "facility", "methods", "parts")
    from server.sitok import kinds as _kinds
    wall = _kinds.is_wall(db.get(SitokFacility, r.facility_id))
    if wall:  # 옹벽(10/20): 실시결과 요약표 줄·종합의견도, 종합결론은 {survey, repair, urgent}; 10/21 1.5 유지관리방안·전회 칸 출처
        keys += ("summary_rows", "summary_opinion", "maint_plan", "summary_prev_src", "summary_prev_label", "summary_prev_grade")
    final = {k: body.get(k) for k in keys}
    if wall:
        final["wall"] = True
    if final.get("items"):  # 3종: 등급은 18항목 점수로(점검자가 고른 등급보다 우선) — 옹벽은 매뉴얼 단서(보강토 11번)까지(wall_manual.score)
        if wall:
            from server.sitok import wall_manual
            wf = db.get(SitokFacility, r.facility_id)
            form = wall_manual.form_of(((wf.ledger or {}).get("wall") or {}).get("form") or "", wf.name, wf.kind or "")
            final["grade"] = wall_manual.score(final["items"], form)["grade"] or final.get("grade")
        else:
            final["grade"] = rb.eval_score(final["items"])["grade"] or final.get("grade")
    from server.sitok import ai_draft as _AD

    tpl = db.get(SitokFacility, r.facility_id).template
    if final.get("grade"):  # 2종은 양호·보통·미흡·불량(속은 B~E) — 우수(A)는 양호로(10/16)
        final["grade"] = _AD.to_letter(str(final["grade"]), tpl)
    if final.get("grade") and final["grade"] not in ("A", "B", "C", "D", "E"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "안전등급은 A~E(2종은 양호·보통·미흡·불량) 중 하나입니다.")
    final["edited_by"], final["edited_at"] = user.display_name or "", datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    r.ai = {**(r.ai or {}), "final": final}
    db.commit()
    return _ai_out(db, r)


@router.get("/reports/{report_id}/survey")
def survey_get(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """면담·변경사항 창 — 1.2.7 지난 이력(전회차 보고서)·1.2.8 항목(회사 원본) + 이번에 넣은 값."""
    r = _require(db, user, report_id)
    prior = _prior(r)
    if _is_wall(r):  # 옹벽(10/21 형 "보고서랑 맞추기") — 1.3.1 자료수집·1.3.2 점검 이력·1.3.3 보수 이력·1.3.4 자료분석, 1.2.8 변경사항은 없음
        return _wall_survey_out(db, r, user)
    m = master.master_path()
    prev = (r.survey or {}).get("prev") or {}
    base = {"repairs_old": rb.read_survey(prior)["repairs_old"] if prior else prev.get("repairs") or [],
            "change_items": rb.read_survey(m)["change_items"] if m.exists() else [], "has_prior": prior is not None}
    return {**base, "repairs": (r.survey or {}).get("repairs") or [], "changes": (r.survey or {}).get("changes") or {},
            "period": f"{r.year}년 {r.half}", "has_register": _register(db.get(SitokFacility, r.facility_id)).exists()}


_register = register_path  # 건축물대장 PDF(시설물 폴더에 하나) — 10/14 server/api/routers/sitok.register_path로 옮김


@router.post("/facilities/{facility_id}/register")
def upload_register(facility_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """건축물대장 PDF 올리기 — 시설물 정보·서류 칸(10/14). 시설물 현황 [🤖 채우기]·면담 1.2.8 초안이 씀."""
    f = _require_facility(db, user, facility_id)
    _save_register(f, file)
    return {"ok": True, "has_register": True}


@router.get("/facilities/{facility_id}/register/file")
def register_file(facility_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = _require_facility(db, user, facility_id)
    p = register_path(f)
    if not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "건축물대장이 없습니다.")
    return FileResponse(p, media_type="application/pdf", content_disposition_type="inline", filename=f"{f.name} 건축물대장.pdf")


def _save_register(f: SitokFacility, file: UploadFile | None) -> Path:
    reg = _register(f)
    if file is not None and file.filename:
        data = file.file.read()
        if not data.startswith(b"%PDF"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "건축물대장은 PDF로 올려 주세요.")
        reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_bytes(data)
    return reg


@router.post("/reports/{report_id}/survey/changes/ai")
def survey_changes_ai(report_id: int, file: UploadFile | None = File(None), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """1.2.8 초안(저장 안 함) — 건축물대장 변동사항(준공 이후 전부)을 AI가 줄마다 읽고 항목별로(server/sitok/changes.py). 점검자가 창에서 확인하고 저장."""
    from server.sitok import changes

    r = _require(db, user, report_id)
    reg = _save_register(db.get(SitokFacility, r.facility_id), file)
    if not reg.exists():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "건축물대장 PDF를 올려 주세요(변동사항이 있는 \"을\" 쪽까지).")
    labels = [it["label"] for it in survey_get(report_id, user, db)["change_items"]]
    if not labels:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "틀에 1.2.8 변경사항 표가 없습니다.")
    try:
        events = changes.read_events(reg, user.company_id)
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"건축물대장 변동사항을 읽지 못했습니다: {str(err).splitlines()[0][:150]}") from err
    drafted, missing = changes.draft(events, labels)
    return {"changes": drafted, "events": events, "missing": missing}


def _wall_prev_report(db: Session, r: SitokReport) -> SitokReport | None:
    """같은 시설물의 직전 회차(그룹웨어에 있는 것) — 연도·반기 앞선 것 중 가장 최근."""
    from server.sitok import seasons as _s

    rows = db.query(SitokReport).filter(SitokReport.facility_id == r.facility_id, SitokReport.id != r.id).all()
    key = lambda x: (x.year, 0 if _s.bucket(x.half) == "상반기" else 1)  # noqa: E731
    before = [x for x in rows if key(x) < key(r)]
    return max(before, key=key) if before else None


def _wall_survey_out(db: Session, r: SitokReport, user: User) -> dict:
    """옹벽 면담 창 값(민재형 ⑩ 우선순위): 1.3.1 = 저장 > 전회차 PDF > 전회차 회차 > 기본값 / 1.3.2 = 저장 > 전회차 회차 이력 + 전회차 줄(자동 누적) > 관리대장 /
    1.3.3 = 저장 > 전회차 회차 / 1.3.4 = 저장(자료가 바뀌었으면 stale)."""
    from core.models_web import Company
    from server.api.routers.sitok_prev import prev_file
    from server.sitok import wall_ai, wall_collect

    f = db.get(SitokFacility, r.facility_id)
    spec = ((f.ledger or {}).get("wall") or {}) if f else {}
    sv = r.survey or {}
    prev = _wall_prev_report(db, r)
    psv = (prev.survey or {}) if prev is not None else {}
    comp = db.get(Company, user.company_id)
    company = getattr(comp, "name", "") or ""
    # 1.3.2 점검 이력
    src_h = "saved" if "history" in sv else ""
    history = sv.get("history")
    if history is None:
        if prev is not None and (psv.get("history") is not None or psv.get("fms_history")):
            fin = (prev.ai or {}).get("final") or {}
            history = wall_collect.chain_history(psv.get("history") or [], prev, company, wall_ai.word(fin.get("grade") or "") or (f.safety_grade or ""), fin.get("findings") or [])
            src_h = "prev"
        else:
            history = list(spec.get("history") or [])
            src_h = "ledger" if history else ""
    # 1.3.3 보수 이력
    repairs = sv.get("repairs")
    src_r = "saved" if repairs is not None else ""
    if repairs is None:
        repairs = list(psv.get("repairs") or []) if prev is not None else []
        src_r = "prev" if repairs else ""
    # 1.3.1 자료수집 현황
    base = wall_collect.defaults(spec, history, repairs)
    collect, src_c = None, ""
    if sv.get("collect"):
        collect, src_c = wall_collect.norm_collect(sv["collect"], base), "saved"
    else:
        pdf = prev_file(db, r)
        got = wall_collect.read_prior_pdf(pdf) if pdf.exists() else None
        if got:
            collect, src_c = wall_collect.norm_collect(got, base), "pdf"
        elif prev is not None and psv.get("collect"):
            collect, src_c = wall_collect.norm_collect(psv["collect"], base), "prev"
        else:
            collect, src_c = base, "default"
    # 1.3.4 자료분석
    analysis = sv.get("analysis") or (psv.get("analysis") if prev is not None else None) or {}
    h = wall_collect.analysis_hash(collect, history, repairs)
    return {"wall": True, "history": history, "history_src": src_h, "repairs": repairs, "repairs_src": src_r, "collect": collect, "collect_src": src_c,
            "collect_rows": wall_collect.ROWS, "analysis": {k: analysis.get(k, "") for k in ("build_result", "build_dir", "maint_result", "maint_dir", "hash")},
            "analysis_stale": bool(analysis) and analysis.get("hash") != h, "analysis_ai": bool(analysis.get("ai")), "prev_round": f"{prev.year}년 {prev.half}" if prev else "",
            "repairs_old": [], "change_items": [], "changes": {}, "has_prior": prev is not None, "has_register": False, "period": f"{r.year}년 {r.half}"}


@router.post("/reports/{report_id}/survey/history/fms")
def survey_history_fms(report_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """FMS 점검진단실적 엑셀 → 1.3.2 줄(전체분, 저장은 [저장]) — 옹벽."""
    from server.sitok import wall_collect

    r = _require(db, user, report_id)
    try:
        rows = wall_collect.fms_history(file.file.read())
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"엑셀을 읽지 못했습니다: {str(err)[:150]}") from err
    if not rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "엑셀에 점검 줄이 없습니다.")
    r.survey = {**(r.survey or {}), "fms_history": True}
    db.commit()
    return {"history": rows}


@router.post("/reports/{report_id}/survey/analysis/ai")
def survey_analysis_ai(report_id: int, body: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """1.3.4 자료분석 결과 AI 초안(저장은 [저장]) — 화면의 1.3.1~1.3.3 값으로."""
    from server.sitok import wall_collect

    r = _require(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    spec = ((f.ledger or {}).get("wall") or {}) if f else {}
    history = body.get("history") or []
    repairs = body.get("repairs") or []
    collect = wall_collect.norm_collect(body.get("collect"), wall_collect.defaults(spec, history, repairs))
    return {"analysis": wall_collect.analysis_ai(collect, history, repairs, user.company_id)}


@router.put("/reports/{report_id}/survey")
def survey_save(report_id: int, body: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    keys = ("period", "kind", "method", "where", "note")
    repairs = [{k: str(x.get(k) or "").strip() for k in keys} for x in body.get("repairs") or []]
    changes = {str(k): {f: str((v or {}).get(f) or "").strip() for f in ("before", "after", "where", "note")}
               for k, v in (body.get("changes") or {}).items() if str((v or {}).get("after") or "").strip()}
    extra = {}
    if _is_wall(r):  # 옹벽 1.3.1 자료수집·1.3.2 점검 이력 줄 [{period, kind, org, grade, result, note}]·1.3.4 자료분석(자료 해시와 같이)
        from server.sitok import wall_collect

        hk = ("period", "kind", "org", "grade", "result", "note")
        hist = [{k: str(x.get(k) or "").strip() for k in hk} for x in body.get("history") or []]
        extra["history"] = [x for x in hist if x["period"] or x["result"]]
        f = db.get(SitokFacility, r.facility_id)
        spec = ((f.ledger or {}).get("wall") or {}) if f else {}
        reps_w = [x for x in repairs if x["method"] or x["kind"] or x["where"]]
        extra["collect"] = wall_collect.norm_collect(body.get("collect"), wall_collect.defaults(spec, extra["history"], reps_w))
        an = body.get("analysis") or {}
        if any(str(an.get(k) or "").strip() for k in ("build_result", "build_dir", "maint_result", "maint_dir")):
            extra["analysis"] = {**{k: str(an.get(k) or "").strip() for k in ("build_result", "build_dir", "maint_result", "maint_dir")},
                                 "ai": bool(an.get("ai")), "hash": str(an.get("hash") or "") or wall_collect.analysis_hash(extra["collect"], extra["history"], reps_w)}  # hash = 글을 쓸 때의 자료(AI 응답·저장값) — 뒤에 자료가 바뀌면 stale
    r.survey = {**(r.survey or {}), "repairs": [x for x in repairs if x["method"] or x["kind"] or x["where"]], "changes": changes, **extra}  # 시설물 현황(detail)은 그대로
    db.commit()
    return survey_get(report_id, user, db)


# ---------- 시설물 현황(1.1 건축물 현황표·1.2.1~1.2.4 체크·구조·용도현황) — server/sitok/detail.py ----------

def _detail_out(db: Session, r: SitokReport, override: dict | None = None) -> dict:
    """칸은 회사 원본, 값 = 저장한 것(또는 AI 초안 override) → 없으면 전회차 보고서 값(없으면 "-"). 칸마다 prior = 전회차 보고서 값
    (관리대장·건축물대장 AI 값과 다르면 창이 둘 다 보여 주고 고르게 — 사용자 10/12, 기본은 관리대장)."""
    from server.sitok import detail

    if not master.master_path().exists():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "회사 원본 템플릿이 없습니다 — 시특법 설정에서 올리세요.")
    prior = _prior(r)
    base = detail.read(master.master_path())
    f = db.get(SitokFacility, r.facility_id)
    dflt = _detail_defaults(prior, f, (r.survey or {}).get("prev"))
    saved = override or (r.survey or {}).get("detail") or {}
    for x in base["fields"]:
        x["prior"] = dflt["prior_fields"].get(x["key"], "-") if prior or (r.survey or {}).get("prev") else ""
        x["value"] = (saved.get("fields") or {}).get(x["key"], dflt["fields"].get(x["key"], "-"))
    for c in base["checks"]:
        c["selected"] = (saved.get("checks") or {}).get(c["key"], dflt["checks"].get(c["key"]))
    base["uses"] = saved["uses"] if saved.get("uses") is not None else dflt["uses"]
    base["uses_total"] = saved.get("uses_total") or dflt["uses_total"]
    return {**base, "saved": bool((r.survey or {}).get("detail")), "has_ledger": bool(f.ledger_pdf and Path(f.ledger_pdf).exists()),
            "has_register": _register(f).exists(), "has_prior": prior is not None}


@router.get("/reports/{report_id}/detail")
def detail_get(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _detail_out(db, _require(db, user, report_id))


@router.post("/reports/{report_id}/detail/ai")
def detail_ai(report_id: int, file: UploadFile | None = File(None), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """AI 초안(저장 안 함) — 관리대장 PDF(시설물 등록 때 올린 것) + 건축물대장 PDF(여기서 올리면 시설물 폴더에 둠, 층별 용도·면적)."""
    from server.sitok import detail

    from server.api.routers.sitok_prev import ensure_prev, prev_file

    r = _require(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    reg = _save_register(f, file)
    use_prev = _prior(r) is None and prev_file(db, r).exists()  # 전회차 보고서 PDF(10/18 민재형) — 처음이면 AI로 한 번 읽어 저장 → 기본값·체크·용도현황에 들어감
    pv = ensure_prev(db, user, r) if use_prev else {}
    cur = _detail_out(db, r)
    facility = (f"{f.name} / 시설물번호 {f.fms_no} / {f.address} / 관리주체 {f.owner_name} / 준공 {_iso(f.completion_date)} / 구조 {f.structure} / "
                f"지상 {f.floors_above}층·지하 {f.floors_below}층·옥탑 {f.floors_roof} / 최고높이 {f.max_height} / 연면적 {f.total_area} / 건축면적 {f.building_area} / "
                f"주용도 {f.main_use}")
    pdfs = [Path(p) for p in (f.ledger_pdf, str(reg)) if p and Path(p).exists()]
    from server.sitok import drawings as D  # 구조일반사항·건축개요 도면(10/12) — 글자 + 쪽 그림
    struct = [it["path"] for it in D.items(f, "struct", _facility_dir(f))]
    if not pdfs and not struct:  # 법정 외(관리대장 없음)·군사보안(건축물대장 없음) 등
        if use_prev:
            return {**cur, "ai": True}  # 전회차 보고서 PDF 값만(기본값에 이미 들어감)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "시설물관리대장·건축물대장·구조일반사항 도면·전회차 보고서 PDF가 없어 AI로 채울 수 없습니다 — 칸에 직접 넣으세요(없는 칸은 \"-\").")
    try:
        got = detail.fill_ai(cur, facility, pdfs, user.company_id, drawings=D.for_ai(struct) if struct else None)
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI가 채우지 못했습니다: {str(err).splitlines()[0][:150]}") from err
    keep = {c["key"]: c["selected"] for c in cur["checks"]}
    pf = pv.get("fields") or {}
    fields = {k: (pf.get(k) or v) if (v or "-").strip() in ("", "-") else v for k, v in got["fields"].items()}  # 대장·도면에 없는 칸은 전회차 보고서 값
    return {**_detail_out(db, r, {"fields": fields, "checks": keep, "uses": got["uses"] or pv.get("uses") or None,
                                   "uses_total": got["uses_total"] or pv.get("uses_total") or ""}), "ai": True}


@router.put("/reports/{report_id}/detail")
def detail_save(report_id: int, body: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    d = {"fields": {str(k): str(v or "").strip() or "-" for k, v in (body.get("fields") or {}).items()},
         "checks": {str(k): (int(v) if v is not None and str(v).isdigit() else None) for k, v in (body.get("checks") or {}).items()},
         "uses": [[str(x or "").strip() for x in (row + ["", "", "", ""])[:4]] for row in body.get("uses") or [] if any(str(x or "").strip() for x in row)],
         "uses_total": str(body.get("uses_total") or "").strip()}
    r.survey = {**(r.survey or {}), "detail": d}
    db.commit()
    return _detail_out(db, r)


# ---------- 회사 원본으로 만들 때 전회차 보고서에서 가져오는 것(2026-10-12 판 다시 잡기 ③ — 지난 보고서는 데이터만) ----------

def _norm_key(k: str) -> str:
    """시설물 현황 칸 이름 맞추기 — 보고서마다 "건축면적(㎡)"·"건축면적"처럼 달라도 같은 칸."""
    return re.sub(r"\(.*?\)|㎡|\s", "", k or "")


def _facility_detail(f: SitokFacility | None) -> dict:
    """시설물 현황 칸 중 시설물 칸(관리대장에서 읽었거나 직접 넣은 것)으로 아는 값 — 칸 이름은 _norm_key로 맞춤.
    자료가 다르면 기본은 관리대장(사용자 10/12), 관리대장 없는 법정 외 자체 점검은 직접 넣은 시설물 칸(10/12)."""
    if f is None:
        return {}
    d = f.completion_date
    floors = ", ".join(x for x in (f"지하{f.floors_below}층" if f.floors_below else "", f"지상{f.floors_above}층" if f.floors_above else "") if x)
    vals = {"시설물명": f.name, "시설물번호": f.fms_no, "준공년월일": f"{d.year}년 {d.month:02d}월 {d.day:02d}일" if d else "",
            "위치": f.address, "관리주체": f.owner_name, "건축면적": f"{f.building_area:,.2f}㎡" if f.building_area else "",
            "연면적": f"{f.total_area:,.2f}㎡" if f.total_area else "", "층수": f"1개동({floors})" if floors else "",
            "주용도": f.use_type or f.main_use, "구조형식": f.structure, "최고높이": f"{f.max_height:g}m" if f.max_height else ""}
    return {k: str(v).strip() for k, v in vals.items() if v and str(v).strip()}


def _detail_defaults(prior: Path | None, f: SitokFacility | None = None, prev: dict | None = None) -> dict:
    """시설물 현황 기본값 = 칸은 회사 원본, 값은 시설물 칸(관리대장·직접 입력) → 전회차 보고서 → "-" — 원본(다른 시설물) 값이 남지 않게.
    prior_fields = 전회차 보고서 값만(창에서 다르면 둘 다 보여 줌). 전회차 한글이 없으면 전회차 보고서 PDF에서 읽은 값(prev — 10/18 민재형, server/sitok/prev_pdf.py)."""
    from server.sitok import detail

    base = detail.read(master.master_path())
    src = detail.read(prior) if prior else (prev_pdf.as_detail(prev) if prev else None)
    pv = {x["key"]: x["value"] for x in (src or {}).get("fields", [])}
    pn = {_norm_key(k): v for k, v in pv.items()}
    prior_fields = {x["key"]: (pv.get(x["key"]) or pn.get(_norm_key(x["key"])) or "-") for x in base["fields"]}
    fv = _facility_detail(f)
    fields = {k: fv.get(_norm_key(k)) or v for k, v in prior_fields.items()}
    pc = {c["key"]: c["selected"] for c in (src or {}).get("checks", [])}
    checks = {c["key"]: pc[c["key"]] for c in base["checks"] if c["key"] in pc}
    total = (src or {}).get("uses_total") or (f"{f.total_area:,.2f}㎡" if f is not None and f.total_area else "")  # 없으면 시설물 칸 연면적
    return {"fields": fields, "prior_fields": prior_fields, "checks": checks, "uses": (src or {}).get("uses") or [], "uses_total": total}


def _year_half(period: str | None) -> tuple[int, str]:
    """점검기간 글 "2026.03.02~2026.04.15" → (2026, "상반기") — 끝 날 기준, 못 읽으면 (0, "")."""
    m = re.findall(r"(20\d\d)[.\-/년\s]+(\d{1,2})", period or "")
    if not m:
        return 0, ""
    y, mo = m[-1]
    return int(y), "상반기" if int(mo) <= 6 else "하반기"


def _prev_grade(r: SitokReport) -> str:
    """전회차 보고서 PDF에서 읽은 안전등급 글자(A~E, 2종 낱말은 B~E로) — 없으면 ""."""
    g = (((r.survey or {}).get("prev") or {}).get("report") or {}).get("grade") or ""
    return rb._letter(g) or ""


def _ours(hwpx: Path) -> bool:
    """우리 회사 보고서인지(표지·제출문에 회사 이름) — 1.2.6 점검기관 칸."""
    import zipfile

    with zipfile.ZipFile(hwpx) as z:
        return "한국미래안전" in z.read(rb._sections(z)[0]).decode("utf-8", "ignore")


def _base_extras(db: Session, r: SitokReport, f: SitokFacility, ex: rb.Extras, prior: Path | None, pv: rb.Values | None) -> list[str]:
    """회사 원본의 시설물 고유 내용(표지·위치도·전경·일반현황·결과표 고정 칸·1.2.6·1.2.7·1.1/1.2·결과표 글·1.3·1.4)을 이 시설물 것으로 —
    전회차 보고서가 있으면 그 데이터, 없으면(처음 맡는 시설물) 비우거나 안내. 경고(채워야 할 것)를 돌려줌."""
    from server.sitok import locmap

    warn = []
    c = db.get(SitokContract, r.contract_id) if r.contract_id else None
    mp = locmap.facility_map(f, _facility_dir(f))  # 올린 그림 > 핀 > 주소(10/23 사용자 "다른 보고서 틀에도 시설별 위치도 기능 모두")
    if mp is None:
        warn.append("주소로 위치도 지도를 만들지 못해 빈 그림으로 넣었습니다")
    elif note := locmap.address_note(f, _facility_dir(f)):
        warn.append(note)
    if not ex.overview and prior is not None:  # 이번에 전경사진을 안 찍었으면 전회차 보고서 사진(표지·10쪽·11쪽)
        ex.overview = rb.read_overview(prior, _report_dir(f, r) / "전회차_전경")
        if ex.overview:
            warn.append(f"전경사진을 안 찍어 전회차 보고서 사진 {len(ex.overview)}장을 넣었습니다")
    ov = ex.overview
    own = r.overview or []
    if len(own) >= 2 and not any(p.get("main") for p in own):  # 10/23 형 — 첫 장(옥상전경)이 표지·위치도 아래로 나갔음
        warn.append(f"대표 전경사진을 안 골라 첫 장({own[0].get('title') or '제목 없음'})을 표지·위치도 아래에 넣었습니다 — 전경사진 탭 [★ 대표로]로 고르세요")
    floors = " / ".join(x for x in (f"B{f.floors_below}F" if f.floors_below else "", f"{f.floors_above}F" if f.floors_above else "") if x)
    history, repairs = [], []
    if prior is not None and pv is not None:  # 1.2.6 = 전회차 회차 + 그 보고서의 가장 최근 이력(견본들처럼 2개), 1.2.7 = 전회차 이력
        period = f"{pv.period_start:%Y.%m.%d}~{pv.period_end:%Y.%m.%d}" if pv.period_start and pv.period_end else "-"
        history.append({"kind": "정기안전점검", "period": period, "org": "(주)한국미래안전" if _ours(prior) else "-", "grade": pv.grade or "-",
                        "title": f"【 {pv.year}년 {pv.half} 정기안전점검 실시결과 】", "lines": pv.findings or ["-"]})
        older = [h for h in rb.read_history(prior) if rb._d(h["period"]) and rb._d(h["period"]) != pv.period_start]
        older.sort(key=lambda h: rb._d(h["period"]), reverse=True)  # 보고서마다 이력 순서가 달라(광숭초 오래된 순·숭의 최근 순) 날짜로
        history += older[:1]
        repairs = rb.read_survey(prior)["repairs_old"]
    elif (r.survey or {}).get("prev"):  # 전회차 보고서 PDF(10/18) — 결과표 = 1.2.6 첫 줄, 그 보고서의 1.2.6 이력 맨 위 하나, 1.2.7 이력
        pp = r.survey["prev"]
        rp = pp.get("report") or {}
        y, h = _year_half(rp.get("period"))
        history.append({"kind": "정기안전점검", "period": rp.get("period") or "-", "org": rp.get("org") or "-", "grade": rp.get("grade") or "-",
                        "title": f"【 {y}년 {h} 정기안전점검 실시결과 】" if y else "【 전회차 정기안전점검 실시결과 】", "lines": rp.get("findings") or ["-"]})
        start = rb._d(rp.get("period") or "")
        older = [dict(h) for h in pp.get("history") or [] if rb._d(h.get("period") or "") and rb._d(h["period"]) != start]
        older.sort(key=lambda h: rb._d(h["period"]), reverse=True)  # 표가 오래된 순인 보고서도 있어(덕산초 2026 상반기) 날짜로 — 전전회차 = 가장 최근(10/19 형)
        for h in older[:1]:
            t = (h.get("title") or "").strip().strip("【】 ")
            h["title"] = f"【 {t} 】" if t and t != "-" else h.get("title") or "-"
        history += older[:1]
        repairs = pp.get("repairs") or []
    result = {"시설물구분": f.kind or "건축물", "종류": f.use_type or f.main_use or "-",
              "종별": class_label(f) if f.legal else "해당없음"}  # 법정 외(자체 점검) = 해당없음(사용자 10/12), 1종은 시설물 종별 칸(10/20)
    if c is not None:
        result.update({"공동수급": f"{c.joint_type} {c.joint_pct}%".strip(), "계약방법": c.bid_method})
    ex.base = {"map": str(mp) if mp else "", "cover": ov[0][0] if ov else "", "has_overview": bool(ov), "name": f.name,
               "short": f.name.split()[-1] if " " in f.name else f.name, "year": f"{f.completion_date.year}년" if f.completion_date else "-",
               "floors": floors or "-", "area": f"{f.total_area:,.2f}㎡" if f.total_area else "-", "structure": f.structure or "-",
               "grade": class_label(f)[:1], "use": f.use_type or f.main_use or "시설물",
               "history": history, "repairs": repairs, "result": result, "school": f.template == "3종학교", "legal": f.legal,
               "target": {"owner": f.owner_name or (pv.owner if pv else "") or "-", "name": f.name, "use": f.use_type or f.main_use or "-",
                          "year": str(f.completion_date.year) if f.completion_date else "-", "area": f"{f.total_area:,.2f}" if f.total_area else "-",
                          "floors": (f"-{f.floors_below}/{f.floors_above}" if f.floors_below else str(f.floors_above or "-")),
                          "structure": "철콘" if "철근콘크리트" in (f.structure or "") else (f.structure or "-"), "grade": (pv.grade if pv else "") or _prev_grade(r) or "-"}}
    ex.history = False
    if not ov:
        warn.append("전경사진이 없어 표지·전경 칸이 빈 그림입니다(현장 조사 → 🏢 전경사진)")
    if not (r.survey or {}).get("detail"):  # 시설물 현황을 저장 안 했으면 전회차 보고서 값(없으면 "-")
        ex.survey = {**(ex.survey or {}), "detail": _detail_defaults(prior, f, (r.survey or {}).get("prev"))}
        warn.append("[🏢 시설물 현황]을 저장하지 않아 1.1·1.2 표는 시설물 칸" + (" + 전회차 보고서 값입니다" if prior else " 값 말고는 비었습니다(\"-\")"))
    if not ex.ai:
        if prior is not None:
            ai = rb.read_texts(prior)
            if (f.template or "").startswith("3종"):
                items = rb.read_eval_items(prior)
                if items:
                    ai["items"] = items
            fac = rb.read_facility_items(prior)
            if fac:
                ai["facility"] = fac
            ex.ai = ai
            warn.append("[🤖 AI 초안]을 안 만들어 결과표·1.3·1.4·종합결론은 전회차 보고서 글 그대로입니다")
        else:
            warn.append("[🤖 AI 초안]을 안 만들어 결과표·1.3·1.4·종합결론이 원본(다른 시설물) 글입니다 — 꼭 만드세요")
    if f.template == "3종학교":
        warn.append("1.7 치장벽돌 안전점검 표는 원본 값 그대로 — 손으로 확인하세요")
    return warn
