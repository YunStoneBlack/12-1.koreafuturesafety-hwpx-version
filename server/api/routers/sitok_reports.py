"""시특법 보고서 회차(2026-10-10 4단계) — 시설물 화면(sitok-facility.html)의 "점검 보고서" 칸.

- `GET  /sitok/facilities/{id}/reports` — 회차 목록 + 새 회차 기본값.
- `POST /sitok/facilities/{id}/reports` — 새 회차(틀 = 직전 회차 결과 한글이 있으면 자동으로).
- `PATCH/DELETE /sitok/reports/{id}` — 고치기·지우기.
- `POST /sitok/reports/{id}/source` — 지난 보고서 한글(hwp·hwpx) 올리기 = 틀(처음 하는 시설물). hwp는 작업 프로그램이 hwpx로 바꿈.
- `POST /sitok/reports/{id}/build` — 만들기 시작(백그라운드: 값 바꾸기 → 한글 PDF(100쪽 넘으면 몇 분) → 관리대장·계약서 합본). 화면은 GET으로 진행을 봄.
- `GET  /sitok/reports/{id}` · `/sitok/reports/{id}/file/{pdf|hwpx}`.
값 바꾸기 규칙: server/sitok/report_build.py. 점검기간·용역기간 기본값: 인수인계 10/10(민간·관급).
"""

from __future__ import annotations

import datetime
import threading
import traceback
from pathlib import Path

import pymupdf
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.db import SessionLocal
from core.models_web import SitokContract, SitokFacility, SitokReport, SubmitDoc, TechPerson, User
from server.api.deps import get_current_user, get_db
from server.api.routers.contract_library import doc_status
from server.api.routers.sitok import _facility_dir, _require_facility
from server.contract_docs import hwp_queue
from server.sitok import report_build as rb

router = APIRouter(prefix="/sitok", tags=["sitok"])
HALVES = ("상반기", "하반기")
PDF_WAIT = 1200  # 한글 PDF 대기(초) — 135쪽 보고서 + 앞에 산안법 보고서 작업이 있을 수도


class ReportIn(BaseModel):
    contract_id: int | None = None
    year: int | None = None
    half: str | None = None
    period_start: datetime.date | None = None
    period_end: datetime.date | None = None
    report_date: datetime.date | None = None
    chief_id: int | None = None
    participant_ids: list[int] | None = None


def _iso(d):
    return d.isoformat() if d else ""


def _report_dir(f: SitokFacility, r: SitokReport) -> Path:
    return _facility_dir(f) / f"{r.year}_{r.half}"


def _out(r: SitokReport) -> dict:
    return {"id": r.id, "contract_id": r.contract_id, "year": r.year, "half": r.half,
            "period_start": _iso(r.period_start), "period_end": _iso(r.period_end), "report_date": _iso(r.report_date),
            "chief_id": r.chief_id, "participant_ids": r.participant_ids or [],
            "has_source": bool(r.source_hwpx and Path(r.source_hwpx).exists()), "source_note": r.source_note,
            "status": r.status, "message": r.message, "made_at": r.made_at.strftime("%Y-%m-%d %H:%M") if r.made_at else "",
            "has_pdf": bool(r.out_pdf and Path(r.out_pdf).exists()), "has_hwpx": bool(r.out_hwpx and Path(r.out_hwpx).exists())}


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
    done = [x for x in rows if _order(x) < _order(r) and x.out_hwpx and Path(x.out_hwpx).exists()]
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
    c = _latest_contract(db, f.id)
    persons = db.query(TechPerson).filter(TechPerson.company_id == user.company_id, TechPerson.active.is_(True)).order_by(TechPerson.name).all()
    return {
        "reports": [_out(r) for r in rows],
        "defaults": {"year": today.year, "half": half, "contract_id": c.id if c else None,
                     **{k: _iso(v) for k, v in period_defaults(c, today.year, half).items()}},
        "persons": [{"id": p.id, "name": p.name, "position": p.position, "sitok_grade": p.sitok_grade} for p in persons],
    }


@router.post("/facilities/{facility_id}/reports")
def create_report(facility_id: int, body: ReportIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = _require_facility(db, user, facility_id)
    if not body.year or body.half not in HALVES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "연도와 반기를 고르세요.")
    if db.query(SitokReport).filter(SitokReport.facility_id == f.id, SitokReport.year == body.year, SitokReport.half == body.half).first():
        raise HTTPException(status.HTTP_409_CONFLICT, f"{body.year}년 {body.half} 보고서가 이미 있습니다.")
    r = SitokReport(company_id=user.company_id, facility_id=f.id, created_by=user.display_name or "", **body.model_dump(exclude_unset=True))
    c = db.get(SitokContract, r.contract_id) if r.contract_id else None
    if r.period_start is None and r.period_end is None:
        for k, v in period_defaults(c, r.year, r.half).items():
            setattr(r, k, v)
    db.add(r)
    db.flush()
    prev = _previous(db, r)
    if prev is not None:
        r.source_hwpx, r.source_note = prev.out_hwpx, f"직전 회차({prev.year}년 {prev.half}) 보고서"
    db.commit()
    return _out(r)


@router.patch("/reports/{report_id}")
def update_report(report_id: int, body: ReportIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(r, k, v)
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


@router.post("/reports/{report_id}/source")
def upload_source(report_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """지난 보고서 한글 → 틀. hwp는 작업 프로그램이 hwpx로 바꾼다(17MB 보고서 20~40초). 결과표를 못 읽으면 거절."""
    r = _require(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
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
    dest = _report_dir(f, r) / "틀_지난보고서.hwpx"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    try:
        old = rb.read_old(dest)
    except Exception as err:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
    r.source_hwpx, r.source_note = str(dest), f"올린 파일: {name} ({old.year}년 {old.half} · {old.name})"
    db.commit()
    return _out(r)


def _new_values(db: Session, r: SitokReport, old: rb.Values) -> tuple[rb.Values, list[str]]:
    """이 회차의 새 값 + 경고(빈 칸·수료증 유효기간)."""
    f = db.get(SitokFacility, r.facility_id)
    c = db.get(SitokContract, r.contract_id) if r.contract_id else None
    warn: list[str] = []
    new = rb.Values(**{k: getattr(old, k) for k in vars(old)})
    new.name, new.year, new.half = f.name or old.name, r.year, r.half
    t = old.title
    for o, n in ((old.name, new.name), (f"{old.year}년도", f"{r.year}년도"), (f"{old.year}년", f"{r.year}년"), (old.half, r.half)):
        if o:
            t = t.replace(o, n)
    new.title = t
    new.owner = f.owner_name or old.owner
    new.address = f.address or old.address
    new.completion = f.completion_date or old.completion
    if old.scale and f.structure and f.total_area:
        floors = f"지상 {f.floors_above}층" if f.floors_above else ""
        if f.floors_below:
            floors += f", 지하 {f.floors_below}층"
        new.scale = f"형식 : {f.structure}, 연면적 : {f.total_area:,.1f} m², {floors}".rstrip(", ")
    if c is not None:
        new.rep = c.rep_name or old.rep
        if c.amount:
            per_half = c.amount / 2 if c.sector == "관급" and c.halves == "연간" else c.amount
            new.amount_k = f"{round(per_half / 1000):,}"
    else:
        warn.append("계약을 고르지 않아 대표자·점검금액은 지난 보고서 그대로입니다")
    new.period_start, new.period_end = r.period_start or old.period_start, r.period_end or old.period_end
    if not (r.period_start and r.period_end):
        warn.append("점검기간이 비어 지난 보고서 기간 그대로입니다 — 회차에서 정하세요")
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


def _merge(pdf: Path, f: SitokFacility, c: SitokContract | None) -> list[str]:
    """부록 간지 뒤에 관리대장·계약서 PDF를 끼운다(간지 쪽을 글자로 찾음). 끼운 것 이름들."""
    doc = pymupdf.open(pdf)
    done = []
    plan = [("시설물관리대장", f.ledger_pdf, ("부록.1", "관리대장")), ("계약서", c.contract_pdf if c else "", ("부록", "계 약 서"))]
    for label, src, keys in reversed(plan):  # 뒤쪽부터 끼워야 앞쪽 쪽 번호가 안 밀림
        if not src or not Path(src).exists():
            continue
        page = next((i for i in range(len(doc) - 1, -1, -1)
                     if all(k in doc[i].get_text() for k in keys) and len(doc[i].get_text().strip()) < 80), None)
        if page is None:
            continue
        with pymupdf.open(src) as add:
            first = 0  # 올린 PDF가 지난 보고서에서 잘라낸 것이면 첫 장이 같은 간지 — 빼고 끼움(10/10 평택 견본)
            while first < len(add) - 1 and all(k in add[first].get_text() for k in keys) and len(add[first].get_text().strip()) < 80:
                first += 1
            doc.insert_pdf(add, from_page=first, start_at=page + 1)
        done.append(label)
    tmp = pdf.with_suffix(".merge.pdf")
    doc.save(tmp, garbage=3, deflate=True)
    doc.close()
    tmp.replace(pdf)
    return list(reversed(done))


def _run_build(report_id: int) -> None:
    with SessionLocal() as db:
        r = db.get(SitokReport, report_id)
        try:
            f = db.get(SitokFacility, r.facility_id)
            c = db.get(SitokContract, r.contract_id) if r.contract_id else None
            src = Path(r.source_hwpx)
            old = rb.read_old(src)
            new, warn = _new_values(db, r, old)
            folder = _report_dir(f, r)
            base = f"{r.year}년 {r.half} 정기안전점검 보고서_{f.name}"
            hwpx = folder / f"{base}.hwpx"
            changed = rb.build(src, old, new, hwpx)
            r.out_hwpx = str(hwpx)
            r.message = f"한글 만듦({changed}곳 바꿈) — PDF로 바꾸는 중(100쪽 넘으면 몇 분)…"
            db.commit()
            pdf = folder / f"{base}.pdf"
            pdf.write_bytes(hwp_queue.convert_via_worker(hwpx.read_bytes(), ".hwpx", wait=PDF_WAIT))
            merged = _merge(pdf, f, c)
            r.out_pdf, r.status, r.made_at = str(pdf), "done", datetime.datetime.now()
            pages = pymupdf.open(pdf).page_count
            r.message = " · ".join([f"{pages}쪽, {changed}곳 바꿈" + (f", {'·'.join(merged)} 합본" if merged else "")] + [f"⚠ {w}" for w in warn])
        except Exception as err:  # noqa: BLE001 — 이유를 남김
            r.status, r.message = "failed", (str(err).splitlines()[0][:300] if str(err) else type(err).__name__)
            traceback.print_exc()
        db.commit()


@router.post("/reports/{report_id}/build")
def start_build(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    if r.status == "running":
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 만드는 중입니다.")
    if not r.source_hwpx or not Path(r.source_hwpx).exists():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "틀이 없습니다 — 지난 보고서 한글 파일을 먼저 올리세요.")
    r.status, r.message = "running", "만드는 중…"
    db.commit()
    threading.Thread(target=_run_build, args=(r.id,), daemon=True).start()
    return _out(r)


@router.get("/reports/{report_id}")
def get_report(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(_require(db, user, report_id))


@router.get("/reports/{report_id}/file/{kind}")
def report_file(report_id: int, kind: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    path = r.out_pdf if kind == "pdf" else r.out_hwpx if kind == "hwpx" else ""
    if not path or not Path(path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일이 없습니다.")
    return FileResponse(path, media_type="application/pdf" if kind == "pdf" else "application/octet-stream",
                        filename=Path(path).name, content_disposition_type="inline" if kind == "pdf" else "attachment")
