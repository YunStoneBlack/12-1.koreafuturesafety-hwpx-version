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
from core.models_web import SitokContract, SitokEquipment, SitokFacility, SitokReport, SubmitDoc, TechPerson, User
from core.stored_path import to_full
from server.api.deps import get_current_user, get_db
from server.api.routers.contract_library import doc_status
from server.api.routers.sitok import _contract_out, _facility_dir, _require_facility, contract_for, kind_known, register_path, renew_info


def _iso(d) -> str:
    return d.isoformat() if d else ""  # sitok._iso는 빈 날짜를 None으로 — 회차 화면은 "" (date 칸 value)
from server.contract_docs import hwp_queue
from server.sitok import master, report_build as rb

router = APIRouter(prefix="/sitok", tags=["sitok"])
HALVES = ("상반기", "하반기")
KINDS = ("정기", "정밀")  # 회차 종류(안전점검) — 계약서 그 반기 줄에서 자동, 틀리면 직접(민재형 10/13)
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


def _out(r: SitokReport) -> dict:
    return {"id": r.id, "contract_id": r.contract_id, "year": r.year, "half": r.half, "kind": r.kind or "정기",
            "period_start": _iso(r.period_start), "period_end": _iso(r.period_end), "report_date": _iso(r.report_date),
            "chief_id": r.chief_id, "participant_ids": r.participant_ids or [],
            "has_source": _prior(r) is not None, "source_note": r.source_note,
            "status": r.status, "message": r.message, "made_at": r.made_at.strftime("%Y-%m-%d %H:%M") if r.made_at else "",
            "has_pdf": bool(r.out_pdf and Path(r.out_pdf).exists()), "has_hwpx": bool(r.out_hwpx and Path(r.out_hwpx).exists()),
            "has_appendix": bool((r.survey or {}).get("appendix_hwpx") and Path((r.survey or {}).get("appendix_hwpx", "")).exists()),  # 정밀 부록 한글(10/13)
            # 이미 낸 보고서를 등록한 회차(만들기 없음) = 등록한 한글 "(낸 보고서).hwpx"(_register_one). 예전 조건 "만듦 + 전회차 없음"은 10/12 회사 원본으로
            # 바꾼 뒤 처음 맡는 시설물 첫 회차를 한 번 만들면 여기 걸려 현장 조사·면담 버튼이 사라졌음(동안교회 — 사용자 10/12)
            "past": r.status == "done" and Path(r.out_hwpx or "").name.endswith("(낸 보고서).hwpx"),
            "has_ai": bool(r.ai), "base": bool((r.survey or {}).get("base")), "has_survey": bool((r.survey or {}).get("repairs") or (r.survey or {}).get("changes")),
            "has_detail": bool((r.survey or {}).get("detail")), "amount_k": r.amount_k or "",
            # 회차 목록 진행 표시(10/14 형 피드백 ⑦ — 3층 구조): 현장 조사 = 결함 줄이나 전경사진이 있음, 재료시험 = 표본층 고름, 상태평가 = 저장한 입력
            "has_field": _has_field(r), "has_tests": bool(((r.tests or {}).get("sample") or {}).get("floors")), "has_rating": bool(r.rating)}


def _has_field(r: SitokReport) -> bool:
    from sqlalchemy.orm import object_session

    from core.models_web import SitokDefect

    db = object_session(r)
    if db is not None and db.query(SitokDefect.id).filter(SitokDefect.report_id == r.id).first() is not None:
        return True
    return bool(r.overview or (r.survey or {}).get("precision"))


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
    return (r.year, HALVES.index(r.half) if r.half in HALVES else 0)


def _previous(db: Session, r: SitokReport) -> SitokReport | None:
    """이 회차보다 앞선 회차 중 만든 한글이 있는 가장 최근 것."""
    rows = db.query(SitokReport).filter(SitokReport.facility_id == r.facility_id, SitokReport.id != r.id).all()
    done = [x for x in rows if _order(x) < _order(r) and _data_hwpx(x) and Path(_data_hwpx(x)).exists()]
    return max(done, key=_order) if done else None


def period_defaults(c: SitokContract | None, year: int, half: str) -> dict:
    """관급: 상반기 = 착수일 ~ 상반기 완료일, 하반기 = 하반기 시작일 ~ 완수일(반기 하나 계약이면 착수 ~ 완수). 민간: 직접(현장 간 날 ~ 낸 날)."""
    if c is None or c.sector != "관급":
        return {"period_start": None, "period_end": None}
    if c.halves == "연간":
        return ({"period_start": c.start_date, "period_end": c.first_half_end} if half == "상반기"
                else {"period_start": c.second_half_start, "period_end": c.end_date})
    return {"period_start": c.start_date, "period_end": c.end_date}


def task_end(c: SitokContract | None, year: int, half: str) -> datetime.date:
    """과업지시서 "용역기간은 ○까지" — 민간 = 반기 말일(6/30·12/31), 관급 = 계약(1년 계약 상반기면 상반기 완료일)."""
    if c is not None and c.sector == "관급":
        d = c.first_half_end if c.halves == "연간" and half == "상반기" else c.end_date
        if d:
            return d
    return datetime.date(year, 6, 30) if half == "상반기" else datetime.date(year, 12, 31)


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
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "반기는 상반기·하반기입니다.")
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
    if not body.year or body.half not in HALVES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "연도와 반기를 고르세요.")
    if db.query(SitokReport).filter(SitokReport.facility_id == f.id, SitokReport.year == body.year, SitokReport.half == body.half).first():
        raise HTTPException(status.HTTP_409_CONFLICT, f"{body.year}년 {body.half} 보고서가 이미 있습니다.")
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
    if f.group_id:  # 묶인 동도 같은 반기 회차(사용자 10/12 — 한 번 묶이면 계속)
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


def _new_values(db: Session, r: SitokReport, old: rb.Values, prior: rb.Values | None) -> tuple[rb.Values, list[str]]:
    """이 회차의 새 값 + 경고(빈 칸·수료증 유효기간). old = 회사 원본(광숭초) 값 — 바뀌어야 할 것. 값은 시설물(관리대장)·계약 → 없으면 전회차 보고서."""
    f = db.get(SitokFacility, r.facility_id)
    c = db.get(SitokContract, r.contract_id) if r.contract_id else None
    warn: list[str] = []
    p = prior or rb.Values()
    new = rb.Values(**{k: getattr(old, k) for k in vars(old)})
    new.name, new.year, new.half = f.name or p.name or "-", r.year, r.half
    if p.title:  # 용역명은 전회차 보고서 모양(발주처마다 다름) — 연도·반기·이름만 이번으로
        t = p.title
        for o, n in ((p.name, new.name), (f"{p.year}년도", f"{r.year}년도"), (f"{p.year}년", f"{r.year}년"), (p.half, r.half)):
            if o:
                t = t.replace(o, n)
        new.title = t
    else:
        new.title = f"{r.year}년도 {r.half} {r.kind or '정기'}점검[{new.name}]"
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
    if c is not None:
        new.rep = c.rep_name or new.rep
        if c.amount:
            per_half = c.amount / 2 if c.sector == "관급" and c.halves == "연간" else c.amount
            new.amount_k = f"{round(per_half / 1000):,}"
    else:
        warn.append("계약을 고르지 않아 대표자·점검금액은 전회차 보고서 값입니다" if prior else "계약을 고르지 않아 대표자·점검금액이 비었습니다")
    if (r.amount_k or "").strip():  # 이 동 점검금액(같은 계약서를 여러 동이 같이 쓸 때 — 회차에서 넣음)
        new.amount_k = r.amount_k.strip()
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
    return ex


def _merge(pdf: Path, ledgers: list[str], contracts: list[str]) -> list[str]:
    """부록 간지 뒤에 관리대장(동마다 차례로)·계약서(계약서마다) PDF를 끼운다(간지 쪽을 글자로 찾음). 끼운 것 이름들."""
    doc = pymupdf.open(pdf)
    done = []
    plan = [("시설물관리대장", ledgers, ("부록.1", "관리대장")), ("계약서", contracts, ("부록", "계 약 서"))]
    for label, srcs, keys in reversed(plan):  # 뒤쪽부터 끼워야 앞쪽 쪽 번호가 안 밀림
        srcs = [s for s in srcs if s and Path(s).exists()]
        if not srcs:
            continue
        page = next((i for i in range(len(doc) - 1, -1, -1)
                     if all(k in doc[i].get_text() for k in keys) and len(doc[i].get_text().strip()) < 80), None)
        if page is None:
            continue
        at = page + 1
        for src in srcs:
            with pymupdf.open(src) as add:
                first = 0  # 올린 PDF가 지난 보고서에서 잘라낸 것이면 첫 장이 같은 간지 — 빼고 끼움(10/10 평택 견본)
                while first < len(add) - 1 and all(k in add[first].get_text() for k in keys) and len(add[first].get_text().strip()) < 80:
                    first += 1
                doc.insert_pdf(add, from_page=first, start_at=at)
                at += len(add) - first
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
    old.grade = pv.grade if pv else ""  # 1.x 안전등급 변경시 사유 — 전회차 등급과 비교
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


def _replace_back_page(doc, keys: tuple, add_bytes: bytes | None, label: str, done: list) -> None:
    """부록 "2-1. … 측정데이터 [후면첨부]"처럼 빈 틀만 있는 쪽 → 그 쪽의 제목(틀 위)·꼬리(틀 아래)는 그대로 두고 틀 자리에 붙는 자료 첫 쪽을 줄여 넣음,
    자료 나머지 쪽은 뒤에 그대로(형 10/15 "수기 작업 때 편의상 그런 것 — 프로그램이니 이렇게 넣고 합본 가능?"). 틀 쪽을 못 찾으면 예전처럼 간지 뒤에 끼움."""
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
        pg = new.new_page(width=W, height=H)
        top, bottom = pymupdf.Rect(0, 0, W, box.y0 - 1), pymupdf.Rect(0, box.y1 + 1, W, H)
        pg.show_pdf_page(top, doc, page, clip=top)
        if bottom.height > 2:
            pg.show_pdf_page(bottom, doc, page, clip=bottom)
        a0 = add[0]
        parts = [pymupdf.Rect(b_[:4]) for b_ in a0.get_text("blocks")] + [d["rect"] for d in a0.get_drawings()] + [r_ for info in a0.get_images(full=True) for r_ in a0.get_image_rects(info[0])]
        parts = [r_ for r_ in parts if r_.is_valid and not r_.is_empty or r_.width > 0 or r_.height > 0]
        clip = pymupdf.Rect(min(r_.x0 for r_ in parts), min(r_.y0 for r_ in parts), max(r_.x1 for r_ in parts), max(r_.y1 for r_ in parts)) if parts else a0.rect
        clip = (clip + (-6, -6, 6, 6)) & a0.rect  # 자료 쪽 여백은 빼고 내용만 크게
        target = pymupdf.Rect(box.x0, box.y0, box.x1, box.y0 + min(box.height, box.width * clip.height / max(clip.width, 1)))  # 위에 붙여
        pg.show_pdf_page(target, add, 0, clip=clip)
        if len(add) > 1:
            new.insert_pdf(add, from_page=1)
        doc.insert_pdf(new, start_at=page + 1)
    doc.delete_page(page)
    done.append(label)


def _precision_appendix_pdf(db: Session, r: SitokReport, f: SitokFacility, pdf: Path) -> list[str]:
    """부록 PDF에 끼우기(간지 글자로 쪽 찾기, 뒤 간지부터): 7-5 계약서 · 5 상태평가 결과자료(③ PDF) · 3-1 탄산화 사진현황(10/14) · 2-1 강도 측정데이터(슈미트 xlsx → PDF) · 2 외관조사 사진첩 · 1 관리대장."""
    from server.api.routers.sitok_defects import _defects_for_cost, album_floors
    from server.api.routers.sitok_rating import _compute as rating_view
    from server.api.routers.sitok_tests import _view as tests_view
    from server.contract_docs.attachments import to_pdf_bytes
    from server.sitok import album_make, condition

    doc = pymupdf.open(pdf)
    done: list[str] = []
    c = db.get(SitokContract, r.contract_id) if r.contract_id else None
    if c is not None and c.contract_pdf and Path(c.contract_pdf).exists():
        _insert_after_page(doc, ("7-5", "계약서"), Path(c.contract_pdf).read_bytes(), "계약서", done)
    rv = rating_view(db, r)
    if rv["result"] is not None:
        tv = tests_view(db, r)
        from core.models_web import Company
        co = db.get(Company, r.company_id)
        when = r.period_start or r.report_date or datetime.date.today()
        bi = {"name": f.name, "address": f.address, "owner": f.owner_name, "completion": f"{f.completion_date.year}년 {f.completion_date.month}월" if f.completion_date else "",
              "use": f.main_use or f.use_type, "structure": f.structure, "land_area": "", "building_area": f"{f.building_area:,.1f} ㎡" if f.building_area else "",
              "total_area": f"{f.total_area:,.1f} ㎡" if f.total_area else "", "above": f.floors_above or 0, "below": f.floors_below or 0, "company": co.name if co else "", "phone": "",
              "when": when.isoformat()}
        agg = condition.aggregate(_defects_for_cost(db, r.id), tv, rv["counts"], above=f.floors_above or 0, below=f.floors_below or 0, tilt_note=tv["tilt"]["note"], settlement_note=tv["settlement"]["note"])
        out = _report_dir(f, r) / "상태평가" / "상태평가결과.pdf"
        condition.make_pdf(out, agg, rv["result"], bi, tv, rv["prev_grade"] or rv["prev_auto"])
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
            _replace_back_page(doc, ("2-1", "측정데이터"), to_pdf_bytes(xlsx.read_bytes(), xlsx.name), "강도 측정데이터", done)
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
    return done


def _convert_pushing(hwpx: Path, pdf: Path, precision: bool = False) -> None:
    """본문 한글 → PDF(정기·정밀 공용, 사용자 10/14 "정기도 같이"). 쪽 검사에서 "제목 'X'만 쪽 끝에 있음"이 나오면 그 제목 문단을 새 쪽에서 시작하게 고치고(pagecheck.push_headings) PDF를 한 번 더
    — 형 10/14 "2~3줄 애매하게 넘어가면 줄간격 늘려서 아예 넘겨버려"(결과표 '다.'부터는 precision_build._split_result_table)."""
    from server.sitok import pagecheck

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
    if pushed:
        pdf.write_bytes(hwp_queue.convert_via_worker(hwpx.read_bytes(), ".hwpx", wait=PDF_WAIT))


def _convert_appendix(appx: Path, apdf: Path) -> None:
    """정밀 부록 한글 → PDF — 마지막 구역(과업수행계획서·사전검토보고서)은 빈 자리 메우기 후 한 번 더(표 한 줄만 다음 쪽 등, 10/15)."""
    from server.sitok import pagecheck

    apdf.write_bytes(hwp_queue.convert_via_worker(appx.read_bytes(), ".hwpx", wait=PDF_WAIT))
    try:
        if pagecheck.fill_gaps(appx, apdf, sections_from=-1):
            apdf.write_bytes(hwp_queue.convert_via_worker(appx.read_bytes(), ".hwpx", wait=PDF_WAIT))
    except Exception:  # noqa: BLE001 — 못 하면 그대로
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
        r.message = " · ".join([f"합본 {pages}쪽(본문 {body_pages}), {changed + changed2}곳 바꿈" + (f", 부록에 {'·'.join(merged)} 끼움" if merged else "")] + [f"⚠ {w}" for w in warn])
    except Exception as err:  # noqa: BLE001
        _fail([r], err)
    db.commit()


def _run_precision_group_build(db: Session, r: SitokReport) -> None:
    """정밀 묶음(10/14 형 2차 답 — 정기 묶음처럼): 동마다 본문 한글(이 동만)을 만들어 한 권으로 합치고(server/sitok/precision_merge.merge_body) PDF·도면·쪽 검사,
    동마다 부록 한글·PDF(관리대장·사진첩·측정데이터·탄산화 사진현황·결과자료·계약서 끼움)를 만든 뒤 간지 구간마다 이어 붙여(merge_appendix_pdfs) 합본 PDF."""
    from core.models_web import SitokGroup
    from server.sitok import drawings as D
    from server.sitok import precision_build, precision_merge

    pairs: list = []
    try:
        pairs = _group_reports(db, r)
        for _, x in pairs:
            x.status, x.message, x.kind = "running", "묶음 정밀 보고서 만드는 중…", "정밀"
        db.commit()
        _group_amounts(pairs)
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
        gtitle = parts[0]["title"].replace(lead.name, gname) if lead.name in parts[0]["title"] else parts[0]["title"]
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
        apdfs, merged_all, changed2 = [], [], 0
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
            merged_all += [f"{m.name} {s}" for s in _precision_appendix_pdf(db, x, m, apdf)]
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
        msg = " · ".join([f"{len(pairs)}동 묶음 합본 {pages}쪽(본문 {body_pages}), {total + changed2}곳 바꿈" + (f", 부록에 {'·'.join(merged_all)} 끼움" if merged_all else "")] + [f"⚠ {w}" for w in warn])
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
        if (r.kind or "정기") == "정밀":
            return _run_precision_group_build(db, r) if f.group_id else _run_precision_build(db, r)
        if f.group_id:
            return _run_group_build(db, r)
        try:
            c = db.get(SitokContract, r.contract_id) if r.contract_id else None
            folder = _report_dir(f, r)
            base = f"{r.year}년 {r.half} {r.kind or '정기'}안전점검 보고서_{f.name}"
            hwpx = folder / f"{base}.hwpx"
            warn, changed, _ = _build_hwpx(db, r, hwpx)
            r.out_hwpx = str(hwpx)
            r.message = f"한글 만듦({changed}곳 바꿈) — PDF로 바꾸는 중(100쪽 넘으면 몇 분)…"
            db.commit()
            pdf = folder / f"{base}.pdf"
            _convert_pushing(hwpx, pdf)  # 한글 → PDF(+ 결과표 넘침·제목만 쪽 끝이면 고치고 한 번 더, 10/14)
            drawn = _insert_drawings(pdf, [(1, f)])  # 1.2.9 뒤 첨부 도면(10/12)
            warn = _page_check(pdf, hwpx, drawn) + warn  # 관리대장·계약서 합치기 전(본문 쪽 번호 = 최종), 도면 쪽은 빼고
            merged = _merge(pdf, [f.ledger_pdf], [c.contract_pdf] if c else [])
            if _insert_albums(db, [r], [f.name], pdf):
                merged.append("외관조사 사진첩")
            from server.api.routers.sitok_defects import missing_photo_note
            if missing_photo_note(db, r.id):  # 이번 회차 사진 없는 결함 — 사진첩 칸은 비움(사용자 10/14)
                warn.append(missing_photo_note(db, r.id))
            r.out_pdf, r.status, r.made_at = str(pdf), "done", datetime.datetime.now()
            pages = pymupdf.open(pdf).page_count
            r.message = " · ".join([f"{pages}쪽, {changed}곳 바꿈" + (f", {'·'.join(merged)} 합본" if merged else "")] + [f"⚠ {w}" for w in warn])
        except Exception as err:  # noqa: BLE001 — 이유를 남김
            _fail([r], err)
        db.commit()


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


def _group_amounts(pairs: list[tuple[SitokFacility, SitokReport]]) -> None:
    """같은 계약서를 여러 동이 같이 쓰면 동별 점검금액(회차 amount_k)이 있어야 — 없으면 이상한 것이라 물어봄(사용자 10/12)."""
    shared: dict[int, list] = {}
    for m, x in pairs:
        if x.contract_id:
            shared.setdefault(x.contract_id, []).append((m, x))
    missing = [m.name for lst in shared.values() if len(lst) > 1 for m, x in lst if not (x.amount_k or "").strip()]
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
        _group_amounts(pairs)
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
        gtitle = parts[0]["title"].replace(lead.name, gname) if lead.name in parts[0]["title"] else parts[0]["title"]
        folder = _report_dir(lead, lead_r)
        base = f"{r.year}년 {r.half} {r.kind or '정기'}안전점검 보고서_{gname}"
        hwpx = folder / f"{base}.hwpx"
        warn += merge.merge(parts, hwpx, gname, gtitle)
        for _, y in pairs:
            y.out_hwpx, y.message = str(hwpx), f"{len(pairs)}동 한글 합침 — PDF로 바꾸는 중(몇 분)…"
        db.commit()
        pdf = folder / f"{base}.pdf"
        _convert_pushing(hwpx, pdf)  # 한글 → PDF(+ 결과표 넘침·제목만 쪽 끝이면 고치고 한 번 더, 10/14)
        drawn = _insert_drawings(pdf, [(k, m) for k, (m, _) in enumerate(pairs, 1)])  # 동마다 N.2.9 뒤 첨부 도면(10/12)
        warn = _page_check(pdf, hwpx, drawn) + warn  # 관리대장·계약서 합치기 전(본문 쪽 번호 = 최종), 도면 쪽은 빼고
        contracts = []
        for _, y in pairs:
            c = db.get(SitokContract, y.contract_id) if y.contract_id else None
            if c is not None and c.contract_pdf and c.contract_pdf not in contracts:
                contracts.append(c.contract_pdf)
        merged = _merge(pdf, [m.ledger_pdf for m, _ in pairs], contracts)
        if _insert_albums(db, [y for _, y in pairs], [m.name for m, _ in pairs], pdf):
            merged.append("외관조사 사진첩")
        from server.api.routers.sitok_defects import missing_photo_note
        warn += [f"{m.name}: {missing_photo_note(db, y.id)}" for m, y in pairs if missing_photo_note(db, y.id)]
        pages = pymupdf.open(pdf).page_count
        msg = " · ".join([f"{len(pairs)}동 묶음 {pages}쪽, {total}곳 바꿈" + (f", {'·'.join(merged)} 합본" if merged else "")] + [f"⚠ {w}" for w in warn])
        now = datetime.datetime.now()
        for _, y in pairs:
            y.out_pdf, y.status, y.made_at, y.message = str(pdf), "done", now, msg
    except Exception as err:  # noqa: BLE001
        _fail([y for _, y in pairs] or [r], err)
    db.commit()


@router.post("/reports/{report_id}/build")
def start_build(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    if r.status == "running":
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 만드는 중입니다.")
    if (r.kind or "정기") == "정밀":  # 정밀(10/13 ⑤) — 본문 원본으로 본문 한글·PDF(부록은 다음)
        if not master.master_path("정밀본문").exists():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "정밀안전점검 본문 원본이 없습니다 — 시특법 설정에서 올리세요.")
    elif not master.master_path().exists():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "회사 원본 템플릿이 없습니다 — 시특법 설정에서 올리세요.")
    if not (r.period_start and r.period_end):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "점검기간(시작·끝)을 먼저 정하세요.")
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
    return {**_out(r), "facility_id": f.id, "facility_name": f.name}  # 회차 화면(sitok-round.html, 10/14)이 경로 표시에 씀


@router.get("/reports/{report_id}/file/{kind}")
def report_file(report_id: int, kind: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    sv = r.survey or {}
    path = (r.out_pdf if kind == "pdf" else r.out_hwpx if kind == "hwpx" else sv.get("appendix_hwpx", "") if kind == "appendix"
            else sv.get("appendix_pdf", "") if kind == "appendix_pdf" else sv.get("body_pdf", "") if kind == "body_pdf" else "")
    kind = "pdf" if kind.endswith("pdf") else kind
    if not path or not Path(path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일이 없습니다.")
    return FileResponse(path, media_type="application/pdf" if kind == "pdf" else "application/octet-stream",
                        filename=Path(path).name, content_disposition_type="inline" if kind == "pdf" else "attachment",
                        headers={"Cache-Control": "no-store"})  # 다시 만든 뒤 예전 PDF가 보이지 않게(10/12 동안교회)


def _ai_out(db: Session, r: SitokReport) -> dict:
    """AI 초안 + 단가표 공법 이름(창에서 보수공법 고르기용)."""
    from server.api.routers.sitok_settings import prices
    return {**(r.ai or {}), "prices": [p.method for p in prices(db, r.company_id)]}


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


@router.post("/reports/{report_id}/ai/draft")
def ai_draft_new(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """AI 초안 새로 — 결과는 draft에, 점검자가 고치기 전 final도 같은 값으로(화면에서 고쳐 저장하면 final만 바뀜)."""
    from core.models_web import SitokDefect
    from server.sitok import ai_draft

    r = _require(db, user, report_id)
    if (r.kind or "정기") == "정밀":
        return _precision_ai_draft(db, r, user)
    f = db.get(SitokFacility, r.facility_id)
    rows = db.query(SitokDefect).filter(SitokDefect.report_id == r.id).all()
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
        data = ai_draft.draft(facility, f"{r.year}년 {r.half} (점검기간 {_iso(r.period_start)}~{_iso(r.period_end)})", defects, old, user.company_id,
                              eval_items=items, fac_items=fac_items,
                              combos=method_combos(db, r.id), price_list=[(p.method, p.unit, p.price) for p in prices(db, r.company_id)],
                              parts_facts=facts)
        data["parts"] = P.rows(r.parts, judged)
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI 초안을 만들지 못했습니다: {str(err).splitlines()[0][:200]}") from err
    data["made_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    final = {k: v for k, v in data.items() if k not in ("stats",)}
    if final.get("items"):
        final["grade"] = rb.eval_score(final["items"])["grade"] or final.get("grade")
    r.ai = {"draft": data, "final": final}
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
    final = {k: body.get(k) for k in ("critical", "public", "findings", "repairs", "next_focus", "sections", "conclusion", "grade", "grade_reason",
                                      "items", "eval_opinion", "facility", "methods", "parts")}
    if final.get("items"):  # 3종: 등급은 18항목 점수로(점검자가 고른 등급보다 우선)
        final["grade"] = rb.eval_score(final["items"])["grade"] or final.get("grade")
    if final.get("grade") and final["grade"] not in ("A", "B", "C", "D", "E"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "안전등급은 A~E 중 하나입니다.")
    final["edited_by"], final["edited_at"] = user.display_name or "", datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    r.ai = {**(r.ai or {}), "final": final}
    db.commit()
    return _ai_out(db, r)


@router.get("/reports/{report_id}/survey")
def survey_get(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """면담·변경사항 창 — 1.2.7 지난 이력(전회차 보고서)·1.2.8 항목(회사 원본) + 이번에 넣은 값."""
    r = _require(db, user, report_id)
    prior = _prior(r)
    m = master.master_path()
    base = {"repairs_old": rb.read_survey(prior)["repairs_old"] if prior else [],
            "change_items": rb.read_survey(m)["change_items"] if m.exists() else []}
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


@router.put("/reports/{report_id}/survey")
def survey_save(report_id: int, body: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    keys = ("period", "kind", "method", "where", "note")
    repairs = [{k: str(x.get(k) or "").strip() for k in keys} for x in body.get("repairs") or []]
    changes = {str(k): {f: str((v or {}).get(f) or "").strip() for f in ("before", "after", "where", "note")}
               for k, v in (body.get("changes") or {}).items() if str((v or {}).get("after") or "").strip()}
    r.survey = {**(r.survey or {}), "repairs": [x for x in repairs if x["method"] or x["kind"]], "changes": changes}  # 시설물 현황(detail)은 그대로
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
    dflt = _detail_defaults(prior, f)
    saved = override or (r.survey or {}).get("detail") or {}
    for x in base["fields"]:
        x["prior"] = dflt["prior_fields"].get(x["key"], "-") if prior else ""
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

    r = _require(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    reg = _save_register(f, file)
    cur = _detail_out(db, r)
    facility = (f"{f.name} / 시설물번호 {f.fms_no} / {f.address} / 관리주체 {f.owner_name} / 준공 {_iso(f.completion_date)} / 구조 {f.structure} / "
                f"지상 {f.floors_above}층·지하 {f.floors_below}층·옥탑 {f.floors_roof} / 최고높이 {f.max_height} / 연면적 {f.total_area} / 건축면적 {f.building_area} / "
                f"주용도 {f.main_use}")
    pdfs = [Path(p) for p in (f.ledger_pdf, str(reg)) if p and Path(p).exists()]
    from server.sitok import drawings as D  # 구조일반사항·건축개요 도면(10/12) — 글자 + 쪽 그림
    struct = [it["path"] for it in D.items(f, "struct", _facility_dir(f))]
    if not pdfs and not struct:  # 법정 외(관리대장 없음)·군사보안(건축물대장 없음) 등
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "시설물관리대장·건축물대장·구조일반사항 도면이 없어 AI로 채울 수 없습니다 — 칸에 직접 넣으세요(없는 칸은 \"-\").")
    try:
        got = detail.fill_ai(cur, facility, pdfs, user.company_id, drawings=D.for_ai(struct) if struct else None)
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI가 채우지 못했습니다: {str(err).splitlines()[0][:150]}") from err
    keep = {c["key"]: c["selected"] for c in cur["checks"]}
    return {**_detail_out(db, r, {"fields": got["fields"], "checks": keep, "uses": got["uses"] if got["uses"] else None,
                                   "uses_total": got["uses_total"]}), "ai": True}


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


def _detail_defaults(prior: Path | None, f: SitokFacility | None = None) -> dict:
    """시설물 현황 기본값 = 칸은 회사 원본, 값은 시설물 칸(관리대장·직접 입력) → 전회차 보고서 → "-" — 원본(다른 시설물) 값이 남지 않게.
    prior_fields = 전회차 보고서 값만(창에서 다르면 둘 다 보여 줌)."""
    from server.sitok import detail

    base = detail.read(master.master_path())
    src = detail.read(prior) if prior else None
    pv = {x["key"]: x["value"] for x in (src or {}).get("fields", [])}
    pn = {_norm_key(k): v for k, v in pv.items()}
    prior_fields = {x["key"]: (pv.get(x["key"]) or pn.get(_norm_key(x["key"])) or "-") for x in base["fields"]}
    fv = _facility_detail(f)
    fields = {k: fv.get(_norm_key(k)) or v for k, v in prior_fields.items()}
    pc = {c["key"]: c["selected"] for c in (src or {}).get("checks", [])}
    checks = {c["key"]: pc[c["key"]] for c in base["checks"] if c["key"] in pc}
    total = (src or {}).get("uses_total") or (f"{f.total_area:,.2f}㎡" if f is not None and f.total_area else "")  # 없으면 시설물 칸 연면적
    return {"fields": fields, "prior_fields": prior_fields, "checks": checks, "uses": (src or {}).get("uses") or [], "uses_total": total}


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
    mp = locmap.map_for(f.address, f.name, _facility_dir(f))
    if mp is None:
        warn.append("주소로 위치도 지도를 만들지 못해 빈 그림으로 넣었습니다")
    if not ex.overview and prior is not None:  # 이번에 전경사진을 안 찍었으면 전회차 보고서 사진(표지·10쪽·11쪽)
        ex.overview = rb.read_overview(prior, _report_dir(f, r) / "전회차_전경")
        if ex.overview:
            warn.append(f"전경사진을 안 찍어 전회차 보고서 사진 {len(ex.overview)}장을 넣었습니다")
    ov = ex.overview
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
    result = {"시설물구분": f.kind or "건축물", "종류": f.use_type or f.main_use or "-",
              "종별": f"{(f.template or '2')[:1]}종" if f.legal else "해당없음"}  # 법정 외(자체 점검) = 해당없음(사용자 10/12)
    if c is not None:
        result.update({"공동수급": f"{c.joint_type} {c.joint_pct}%".strip(), "계약방법": c.bid_method})
    ex.base = {"map": str(mp) if mp else "", "cover": ov[0][0] if ov else "", "has_overview": bool(ov), "name": f.name,
               "short": f.name.split()[-1] if " " in f.name else f.name, "year": f"{f.completion_date.year}년" if f.completion_date else "-",
               "floors": floors or "-", "area": f"{f.total_area:,.2f}㎡" if f.total_area else "-", "structure": f.structure or "-",
               "grade": (f.template or "2")[:1], "use": f.use_type or f.main_use or "시설물",
               "history": history, "repairs": repairs, "result": result, "school": f.template == "3종학교", "legal": f.legal,
               "target": {"owner": f.owner_name or (pv.owner if pv else "") or "-", "name": f.name, "use": f.use_type or f.main_use or "-",
                          "year": str(f.completion_date.year) if f.completion_date else "-", "area": f"{f.total_area:,.2f}" if f.total_area else "-",
                          "floors": (f"-{f.floors_below}/{f.floors_above}" if f.floors_below else str(f.floors_above or "-")),
                          "structure": "철콘" if "철근콘크리트" in (f.structure or "") else (f.structure or "-"), "grade": (pv.grade if pv else "") or "-"}}
    ex.history = False
    if not ov:
        warn.append("전경사진이 없어 표지·전경 칸이 빈 그림입니다(현장 조사 → 🏢 전경사진)")
    if not (r.survey or {}).get("detail"):  # 시설물 현황을 저장 안 했으면 전회차 보고서 값(없으면 "-")
        ex.survey = {**(ex.survey or {}), "detail": _detail_defaults(prior, f)}
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
