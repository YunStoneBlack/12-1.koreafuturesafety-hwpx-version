"""내진성능평가 건(2026-10-21 사용자 "시특법 대상 시설물에 하는 과업이 아니야, 완전히 별도의 용역 — 별도 템플릿과 입력할 서류들을 세팅").

건 하나 = 숨김 건물(sitok_facility.seismic_only, 0062 — 시특법 목록·서류·제출 현황·달력에 안 나옴) + 성능평가 회차 하나(반기 칸·종류 "성능평가").
현장 조사(결함)·구조 일람표·철근탐사·보고서 만들기는 회차 화면들을 그대로 씀. 화면 seismic.html(목록·만들기)·seismic-project.html(건 화면).

- `GET    /seismic/projects` — 목록
- `POST   /seismic/projects` (contract·ledger PDF, name) — 계약서·건축물대장을 읽어 만들기(server/sitok/seismic_docs)
- `GET    /seismic/projects/{rid}` — 건 화면 값(용역·건물·층별·변동·서류 칸·지반·기술자·진행)
- `PATCH  /seismic/projects/{rid}` {contract, building, floors, changes, chief_id, participant_ids}
- `POST   /seismic/projects/{rid}/docs/{key}` · `DELETE …/docs/{key}[?item=]` · `GET …/docs/{key}/file[?item=]` — 서류 칸
- `PATCH  /seismic/projects/{rid}/ground` {bh, slot, file | depth·vs·cls·apply_depth} — 지반조사 확인 화면에서 바꾸기
- `GET    /seismic/projects/{rid}/ground/img/{name}` — 지반조사보고서에서 뽑은 그림
- `DELETE /seismic/projects/{rid}` {password}
서류 값은 회차 survey["seismic_contract"]·["seismic_docs"], 건물 값은 시설물 칸 + ledger["register"]. 외주 한글은 예전 자리 survey["seismic_files"]["body"](보고서 만들기가 읽음).
"""
from __future__ import annotations

import datetime
import re
import shutil
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokFacility, SitokReport, TechPerson, User
from server.api.deps import get_current_user, get_db
from server.sitok import seasons
from server.sitok import seismic_docs as SD

router = APIRouter(prefix="/seismic", tags=["seismic"])

# 서류 칸 — (키, 이름, 받는 확장자, 채우는 곳). schedule·struct는 여러 장(시설물 도면 칸 그대로 — 철근탐사 일람표 읽기가 씀)
DOCS = [
    ("contract", "용역계약서", (".pdf",), "용역명·발주처·금액·용역기간 → 표지·제출문·결과표"),
    ("register", "건축물대장", (".pdf",), "건물명·주소·구조·층수·면적·사용승인일 → 1.1·1.2·결과표"),
    ("task", "과업지시서", (".hwp", ".hwpx", ".pdf"), "부록 1 · 조사 수량 규칙(표 3-1)"),
    ("plan", "과업수행계획서", (".hwp", ".hwpx", ".pdf"), "부록 2"),
    ("schedule", "구조 일람표", (".pdf", ".png", ".jpg", ".jpeg"), "철근탐사 설계값(📏 부재 목록)"),
    ("struct", "구조도면", (".pdf", ".png", ".jpg", ".jpeg"), "부록 9"),
    ("floorplan", "층별 평면도", (".pdf", ".png", ".jpg", ".jpeg"), "1.2 건물규모 평면도 — 도면에 적힌 제목(○○평면도)으로 이름·층 차례, 틀리면 아래 칸에서 고치기"),
    ("core", "압축강도 시험성적서", (".pdf", ".png", ".jpg", ".jpeg"), "2.2.3 콘크리트 압축강도 · 부록 5"),
    ("ground", "지반조사보고서", (".pdf",), "2.5 지반 및 기초(값·위치도·사진·결과 표) · 부록 3"),
    ("vendor", "외주 결과물 한글", (".hwp", ".hwpx"), "결과표 나~마·확인서·체크리스트·3~7장"),
    ("measure", "장비·측정 위치도", (".pdf", ".png", ".jpg", ".jpeg"), "부록 5 측정 및 시험성과표 끝(층별 조사 위치)"),
    ("masonry_map", "조적벽 조사 위치도", (".pdf", ".png", ".jpg", ".jpeg"), "부록 5 끝 — 장비·측정 위치도 다음(10/22)"),
    ("midas", "마이다스 데이터 — 1. 안전성 검토", (".pdf",), "부록 7 '안전성 검토' 간지 뒤"),  # 키는 예전 한 칸 그대로(10/22 둘로 — 올린 파일 안 옮김)
    ("midas_linear", "마이다스 데이터 — 2. 선형해석", (".pdf",), "부록 7 '선형 해석' 간지 뒤"),
    ("estimate", "보강공사 내역서", (".pdf", ".xlsx", ".xls"), "부록 8"),
]
DOC = {k: (label, exts, fills) for k, label, exts, fills in DOCS}
MULTI = ("schedule", "struct", "floorplan")  # 시설물 도면 칸(drawings) — 여러 장
CONTRACT_KEYS = ("title", "client", "amount", "contract_no", "contract_date", "start_date", "end_date", "days", "method", "joint", "manager", "phone")
DATE_KEYS = ("contract_date", "start_date", "end_date", "permit_date", "approval_date", "build_start")


def _iso(v) -> str:
    return v.isoformat() if isinstance(v, (datetime.date, datetime.datetime)) else (v or "")


def _d(v) -> datetime.date | None:
    if isinstance(v, datetime.date):
        return v
    try:
        return datetime.date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _jsonable(d: dict) -> dict:
    return {k: (_iso(v) if isinstance(v, (datetime.date, datetime.datetime)) else v) for k, v in d.items()}


def _dirs(f: SitokFacility, r: SitokReport) -> tuple[Path, Path]:
    from server.api.routers.sitok import _facility_dir
    from server.api.routers.sitok_reports import _report_dir

    return _facility_dir(f), _report_dir(f, r)


def _require(db: Session, user: User, rid: int) -> tuple[SitokFacility, SitokReport]:
    r = db.get(SitokReport, rid)
    f = db.get(SitokFacility, r.facility_id) if r is not None else None
    if r is None or f is None or f.company_id != user.company_id or not f.seismic_only:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "내진성능평가 건을 찾을 수 없습니다.")
    return f, r


def _sv(r: SitokReport) -> dict:
    return dict(r.survey or {})


def _put(r: SitokReport, **kw) -> None:
    r.survey = {**(r.survey or {}), **kw}


def grade_of(use: str) -> str:
    """내진등급(1.3) — 학교(교육연구시설)는 특등급(학교시설 내진성능평가 매뉴얼), 그 밖은 사람이 고침(기본 1등급)."""
    return "특등급" if re.search(r"교육|학교", use or "") else "1등급"


# ---------- 값 넣기 ----------
def _apply_contract(f: SitokFacility, r: SitokReport, c: dict) -> None:
    old = (_sv(r).get("seismic_contract") or {})
    new = {**old, **{k: c[k] for k in CONTRACT_KEYS if k in c}}
    if new.get("amount") not in (None, ""):
        try:
            new["amount"] = int(str(new["amount"]).replace(",", ""))
        except ValueError:
            new["amount"] = None
    _put(r, seismic_contract=_jsonable(new))
    r.period_start, r.period_end = _d(new.get("start_date")) or r.period_start, _d(new.get("end_date")) or r.period_end
    if new.get("amount"):
        r.amount_k = f"{new['amount'] / 1000:,.1f}"
    if new.get("client"):
        f.owner_name = new["client"]


BUILDING_COLS = {"name": "name", "address": "address", "structure": "structure", "use": "main_use", "below": "floors_below", "above": "floors_above",
                 "height": "max_height", "total_area": "total_area", "building_area": "building_area"}


def _apply_building(f: SitokFacility, b: dict) -> None:
    for k, col in BUILDING_COLS.items():
        if k in b and b[k] not in (None, ""):
            v = b[k]
            if col in ("floors_below", "floors_above"):
                v = int(float(v))
            elif col in ("max_height", "total_area", "building_area"):
                v = float(str(v).replace(",", ""))
            elif isinstance(v, str):
                v = v.strip()
            setattr(f, col, v)
    if "use" in b and b["use"]:
        f.use_type = b["use"]
    if "approval_date" in b:
        f.completion_date = _d(b["approval_date"])
    reg = dict((f.ledger or {}).get("register") or {})
    for k in ("lot_address", "site_area", "roof", "permit_date", "build_start", "approval_date", "seismic_design", "grade", "floors", "changes", "length_x", "length_y",
              "survey_units", "drawings"):
        if k in b:
            reg[k] = b[k]
    f.ledger = {**(f.ledger or {}), "register": _jsonable(reg)}


def _register_to_building(reg: dict) -> dict:
    """read_register 결과 → 건물 칸 값(착공일은 build_start)."""
    b = {k: reg.get(k) for k in ("name", "address", "lot_address", "structure", "use", "below", "above", "height", "roof", "total_area",
                                  "building_area", "site_area", "permit_date", "approval_date", "seismic_design") if reg.get(k) not in (None, "")}
    if reg.get("start_date"):
        b["build_start"] = reg["start_date"]
    b["floors"] = [_jsonable(x) for x in reg.get("floors") or []]
    b["changes"] = [_jsonable(x) for x in reg.get("changes") or []]
    b["grade"] = grade_of(reg.get("use") or "")
    return {k: (_iso(v) if isinstance(v, datetime.date) else v) for k, v in b.items()}


# ---------- 화면 값 ----------
def _doc_out(f: SitokFacility, r: SitokReport, fdir: Path, rdir: Path) -> list[dict]:
    from server.sitok import drawings as D

    docs = _sv(r).get("seismic_docs") or {}
    out = []
    for key, label, exts, fills in DOCS:
        if key in MULTI:
            items = [{"id": it["id"], "name": it.get("name") or Path(it["file"]).name, "at": it.get("at", "")} for it in D.items(f, key, fdir)]
        elif key == "vendor":
            body = (_sv(r).get("seismic_files") or {}).get("body")
            items = [{"id": "", "name": Path(str(body)).name, "at": (docs.get("vendor") or {}).get("at", "")}] if body else []
        else:
            d = docs.get(key) or {}
            items = [{"id": "", "name": d.get("name") or "", "at": d.get("at", "")}] if d.get("rel") and (rdir / d["rel"]).exists() else []
        out.append({"key": key, "label": label, "exts": list(exts), "fills": fills, "multi": key in MULTI, "items": items,
                    "note": (docs.get(key) or {}).get("note", "")})
    return out


def _project_out(db: Session, f: SitokFacility, r: SitokReport) -> dict:
    from server.api.routers.sitok_reports import _out as report_out

    fdir, rdir = _dirs(f, r)
    sv = _sv(r)
    reg = (f.ledger or {}).get("register") or {}
    building = {"name": f.name, "address": f.address or "", "structure": f.structure or "", "use": f.main_use or f.use_type or "",
                "below": f.floors_below or 0, "above": f.floors_above or 0, "height": f.max_height, "total_area": f.total_area,
                "building_area": f.building_area, "approval_date": _iso(f.completion_date) or reg.get("approval_date", ""),
                **{k: reg.get(k, "") for k in ("lot_address", "site_area", "roof", "permit_date", "build_start", "seismic_design", "grade", "length_x", "length_y")}}
    building["grade"] = building["grade"] or grade_of(building["use"])
    units = SD.survey_units(f)
    building["survey_units"] = units
    item_units = SD.item_units(f)  # 항목별 조사단위(안 고친 항목 = 전체, 10/26)
    building["drawings"] = reg.get("drawings") or ""  # 비우면 자동(drawings_auto)
    persons = db.query(TechPerson).filter(TechPerson.company_id == f.company_id, TechPerson.active.is_(True)).order_by(TechPerson.name).all()
    ground = (sv.get("seismic_docs") or {}).get("ground", {}).get("parsed")
    return {"id": r.id, "facility_id": f.id, "contract": sv.get("seismic_contract") or {}, "building": building,
            "floors": reg.get("floors") or [], "changes": reg.get("changes") or [], "docs": _doc_out(f, r, fdir, rdir),
            "ground": ground, "ground_slots": [[k, label] for k, label, _ in SD.GROUND_SLOTS],
            "ground_sentence": SD.ground_sentence((ground or {}).get("holes") or []),
            "units": units, "item_units": item_units, "unit_own": sorted(k for k, v in item_units.items() if v != units),
            "drawings_auto": SD.has_drawings(f), "min_counts": SD.min_counts(item_units, building["grade"], SD.has_drawings(f)),
            "field_counts": {**{k: len(_field(r)[k]) for k in ("members", "cores", "masonry", "photos")},
                             "texts": sum(1 for v in (_field(r).get("texts") or {}).values() if str(v or "").strip()) + (1 if str(_field(r).get("summary") or "").strip() else 0),
                             "texts_total": len(_field(r).get("texts") or {}) + 1},  # 보고서 AI 작성 — 쓴 글 칸 수(10/27)
            "persons": [{"id": p.id, "name": p.name, "grade": p.grade or "", "position": p.position or ""} for p in persons],
            "floorplans": _floorplans_out(f), "report": report_out(r)}


def _floorplans_out(f: SitokFacility) -> list[dict]:
    """1.2 평면도 쪽마다 이름(읽은 것·고친 것) — 보고서 차례대로(10/27 이름 고치기 칸)."""
    from server.sitok import seismic_fill as SF

    try:
        return [{k: x[k] for k in ("item", "page", "file", "auto", "name", "cap")} for x in SF.plan_pages(f)]
    except Exception:  # noqa: BLE001 — 깨진 PDF여도 건 화면은 열리게
        return []


def _list_out(db: Session, f: SitokFacility, r: SitokReport) -> dict:
    from server.api.routers.sitok_reports import _out as report_out

    sv = _sv(r)
    c = sv.get("seismic_contract") or {}
    docs = sv.get("seismic_docs") or {}
    have = sum(1 for k in DOC if (docs.get(k) or {}).get("rel")) + (1 if (sv.get("seismic_files") or {}).get("body") else 0) \
        + sum(1 for k in MULTI if (f.drawings or {}).get(k))
    return {"id": r.id, "facility_id": f.id, "name": f.name, "address": f.address or "", "title": c.get("title") or "", "client": c.get("client") or "",
            "start_date": c.get("start_date") or _iso(r.period_start), "end_date": c.get("end_date") or _iso(r.period_end),
            "docs": have, "docs_total": len(DOCS), **{k: v for k, v in report_out(r).items() if k in ("status", "made_at", "has_pdf", "field", "seismic")}}


@router.get("/projects")
def list_projects(facility: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = (db.query(SitokReport, SitokFacility).join(SitokFacility, SitokFacility.id == SitokReport.facility_id)
         .filter(SitokFacility.company_id == user.company_id, SitokFacility.seismic_only.is_(True), SitokReport.half == seasons.SEISMIC))
    if facility:
        q = q.filter(SitokFacility.id == facility)
    rows = q.order_by(SitokReport.id.desc()).all()
    return {"projects": [_list_out(db, f, r) for r, f in rows]}


def _save_upload(data: bytes, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


@router.post("/projects")
def create_project(contract: UploadFile | None = File(None), ledger: UploadFile | None = File(None), name: str = Form(""),
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """용역계약서·건축물대장 PDF(둘 다 또는 하나)를 읽어 건 만들기 — 못 읽은 칸은 건 화면에서 직접."""
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="seis_"))
    try:
        cdata = contract.file.read() if contract is not None and contract.filename else b""
        rdata = ledger.file.read() if ledger is not None and ledger.filename else b""
        for data, label in ((cdata, "용역계약서"), (rdata, "건축물대장")):
            if data and not data.startswith(b"%PDF"):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{label}는 PDF로 올려 주세요.")
        c, reg = {}, {}
        if cdata:
            (tmp / "c.pdf").write_bytes(cdata)
            c = SD.read_contract(tmp / "c.pdf")
        if rdata:
            (tmp / "r.pdf").write_bytes(rdata)
            reg = SD.read_register(tmp / "r.pdf")
        title = (c.get("title") or "").strip()
        nm = (name or "").strip() or (reg.get("name") or "").strip() or re.sub(r"\s*내진성능평가\s*용역\s*$", "", title).strip()
        if not nm:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "건물 이름을 넣거나 용역계약서·건축물대장을 올려 주세요.")
        f = SitokFacility(company_id=user.company_id, name=nm, kind="건축물", seismic_only=True, legal=False, template="2종",
                          contract_type="1회성", sector="관급", created_by=user.display_name or "", ledger={})
        db.add(f)
        db.flush()
        start = c.get("start_date") or datetime.date.today()
        r = SitokReport(company_id=user.company_id, facility_id=f.id, year=start.year, half=seasons.SEISMIC, kind="성능평가",
                        period_start=c.get("start_date"), period_end=c.get("end_date"), source_note="내진성능평가", survey={})
        db.add(r)
        db.flush()
        if cdata:
            _apply_contract(f, r, {k: c.get(k) for k in CONTRACT_KEYS})
        if rdata:
            _apply_building(f, _register_to_building(reg))  # 이름 = 대장 명칭(사람이 이름을 넣었으면 그것)
        if name.strip():
            f.name = name.strip()
        fdir, rdir = _dirs(f, r)  # 이름이 정해진 뒤에 폴더
        docs = {}
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        if cdata:
            _save_upload(cdata, rdir / "서류" / "용역계약서.pdf")
            docs["contract"] = {"rel": "서류/용역계약서.pdf", "name": contract.filename, "at": now, "by": user.display_name or ""}
        if rdata:
            _save_upload(rdata, rdir / "서류" / "건축물대장.pdf")
            note = "" if reg.get("text_ok") else "글자가 없는 PDF(스캔)라 칸을 못 읽었습니다 — 직접 넣어 주세요"
            docs["register"] = {"rel": "서류/건축물대장.pdf", "name": ledger.filename, "at": now, "by": user.display_name or "", "note": note}
        _put(r, seismic_docs=docs)
        db.commit()
        return _project_out(db, f, r)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@router.get("/projects/{rid}")
def get_project(rid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f, r = _require(db, user, rid)
    return _project_out(db, f, r)


class ProjectIn(BaseModel):
    contract: dict | None = None
    building: dict | None = None
    floors: list[dict] | None = None
    changes: list[dict] | None = None
    chief_id: int | None = None
    participant_ids: list[int] | None = None


def _rename(db: Session, f: SitokFacility, r: SitokReport, old_dir: Path) -> None:
    """이름을 고쳐 시설물 폴더 이름이 바뀌면 폴더를 옮기고 저장된 전체 경로(결함 사진·외주 한글·만든 보고서)도 새 폴더로."""
    from server.api.routers.sitok import _facility_dir, move_defect_photos

    new_dir = _facility_dir(f)
    if new_dir == old_dir or not old_dir.exists():
        return
    old_dir.rename(new_dir)
    move_defect_photos(db, f.id, old_dir, new_dir)
    o, n = str(old_dir), str(new_dir)
    sv = _sv(r)
    files = dict(sv.get("seismic_files") or {})
    for k, v in list(files.items()):
        if isinstance(v, str) and v.startswith(o):
            files[k] = n + v[len(o):]
    _put(r, seismic_files=files)
    for col in ("out_hwpx", "out_pdf"):
        v = getattr(r, col) or ""
        if v.startswith(o):
            setattr(r, col, n + v[len(o):])


@router.patch("/projects/{rid}")
def update_project(rid: int, body: ProjectIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f, r = _require(db, user, rid)
    fdir, _ = _dirs(f, r)
    if body.contract is not None:
        _apply_contract(f, r, body.contract)
    b = dict(body.building or {})
    if body.floors is not None:
        b["floors"] = body.floors
    if body.changes is not None:
        b["changes"] = body.changes
    if b:
        if "name" in b and not str(b["name"] or "").strip():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "건물 이름은 비울 수 없습니다.")
        before = SD.sample_floors(f, "rebar")
        _apply_building(f, b)
        _rename(db, f, r, fdir)
        _resync_rebar(r, f, before)
    if body.chief_id is not None:
        r.chief_id = body.chief_id or None
    if body.participant_ids is not None:
        r.participant_ids = [int(x) for x in body.participant_ids if x]
    db.commit()
    return _project_out(db, f, r)


def _resync_rebar(r: SitokReport, f: SitokFacility, before: list[int]) -> None:
    """조사단위가 바뀌어 철근배근 표본 층이 달라지면 철근탐사 카드도 — 새 층 4종 × 3칸, 빠진 층은 손 안 댄 카드만 지움(10/26).
    부재 단면·조적은 칸 수 계획이 표본 층을 따라감(member_plan·masonry_plan)."""
    from server.sitok import rebar_survey as RV

    cur = RV.normalize(_sv(r).get("rebar"))
    if not cur["seeded"]:
        return  # 철근탐사 화면을 처음 열 때 지금 단위로 깔림
    rows = RV.resync_floors(cur["rows"], before, SD.sample_floors(f, "rebar"))
    if rows is not None:
        r.survey = {**(r.survey or {}), "rebar": {**cur, "rows": rows}}


class UnitsIn(BaseModel):
    all: int | None = None  # 전체 조사단위(건물 정보 "조사단위 수"와 같은 값)
    item: str | None = None  # member·rebar·core·masonry — 그 항목만
    n: int | None = None  # 그 항목 단위(비우거나 0이면 전체를 따름)


@router.post("/projects/{rid}/units")
def set_units(rid: int, body: UnitsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """조사단위 — 전체(all) 또는 항목 하나(item, n)(10/26 민재형 "개별적으로 가능하게 하고 전체단위수도 — 발주처 요구로 지하 포함 6 등").
    항목 값이 전체와 같아지면 따로 둔 값을 지움. 철근탐사 카드는 표본 층을 따라 늘고 줆(쓴 카드는 안 지움)."""
    f, r = _require(db, user, rid)
    before = SD.sample_floors(f, "rebar")
    reg = dict((f.ledger or {}).get("register") or {})
    own = {k: v for k, v in (reg.get("unit_items") or {}).items() if k in SD.UNIT_ITEMS} if isinstance(reg.get("unit_items"), dict) else {}
    if body.all is not None:
        if not 1 <= body.all <= 40:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "조사단위는 1~40입니다.")
        reg["survey_units"] = body.all
    if body.item is not None:
        if body.item not in SD.UNIT_ITEMS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "없는 조사 항목입니다.")
        if body.n and not 1 <= body.n <= 40:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "조사단위는 1~40입니다.")
        own[body.item] = body.n or None
    f.ledger = {**(f.ledger or {}), "register": _jsonable(reg)}  # 전체를 먼저 바꾼 뒤 항목 값 정리
    total = SD.survey_units(f)
    reg["unit_items"] = {k: int(v) for k, v in own.items() if v and int(v) != total}
    f.ledger = {**(f.ledger or {}), "register": _jsonable(reg)}
    _resync_rebar(r, f, before)
    db.commit()
    return _project_out(db, f, r)


@router.post("/projects/{rid}/docs/{key}")
def upload_doc(rid: int, key: str, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from server.sitok import drawings as D

    if key not in DOC:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 서류 칸입니다.")
    label, exts, _ = DOC[key]
    f, r = _require(db, user, rid)
    name = file.filename or f"{label}{exts[0]}"
    ext = Path(name).suffix.lower()
    if ext not in exts:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{label}은(는) {'·'.join(exts)} 파일로 올려 주세요.")
    data = file.file.read()
    if ext == ".pdf" and not data.startswith(b"%PDF"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "PDF 파일이 아닙니다.")
    fdir, rdir = _dirs(f, r)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    meta = {"name": name, "at": now, "by": user.display_name or ""}
    msg = ""
    if key in MULTI:
        try:
            D.add(f, key, fdir, data, name)
        except ValueError as err:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
    elif key == "vendor":
        from server.api.routers.sitok_seismic import _vendor_kind

        dest = rdir / "외주" / f"{Path(name).stem[:60]}{ext}"
        _save_upload(data, dest)
        files = dict(_sv(r).get("seismic_files") or {})
        files["body"] = str(dest)
        _put(r, seismic_files=files)
        msg = _vendor_kind(dest)
    else:
        rel = f"서류/{label}{ext}"
        for old in (rdir / "서류").glob(f"{label}.*") if (rdir / "서류").exists() else []:
            old.unlink(missing_ok=True)
        _save_upload(data, rdir / rel)
        meta["rel"] = rel
        if key == "contract":
            c = SD.read_contract(rdir / rel)
            _apply_contract(f, r, {k: v for k, v in c.items() if v not in (None, "")})
            msg = "계약서에서 용역 정보를 다시 읽었습니다"
        elif key == "register":
            reg = SD.read_register(rdir / rel)
            if reg.get("text_ok"):
                _apply_building(f, _register_to_building(reg))
                _rename(db, f, r, fdir)
                fdir, rdir = _dirs(f, r)
                msg = "건축물대장에서 건물 정보를 다시 읽었습니다"
            else:
                meta["note"] = msg = "글자가 없는 PDF(스캔)라 칸을 못 읽었습니다 — 직접 넣어 주세요"
        elif key == "ground":
            out_dir = rdir / "지반"
            shutil.rmtree(out_dir, ignore_errors=True)
            parsed = SD.read_ground(rdir / rel, out_dir)
            meta["parsed"] = parsed
            meta["note"] = " · ".join(parsed["warn"])
            msg = f"시추공 {len(parsed['holes'])}개 — " + ("모두 찾았습니다" if not parsed["warn"] else f"확인할 것 {len(parsed['warn'])}개")
    docs = dict(_sv(r).get("seismic_docs") or {})
    docs[key] = meta
    _put(r, seismic_docs=docs)
    db.commit()
    return _project_out(db, f, r) | {"msg": msg}


@router.delete("/projects/{rid}/docs/{key}")
def delete_doc(rid: int, key: str, item: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from server.sitok import drawings as D

    if key not in DOC:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 서류 칸입니다.")
    f, r = _require(db, user, rid)
    fdir, rdir = _dirs(f, r)
    if key in MULTI:
        D.remove(f, key, fdir, item)
    elif key == "vendor":
        files = dict(_sv(r).get("seismic_files") or {})
        files.pop("body", None)
        _put(r, seismic_files=files)
    else:
        docs = dict(_sv(r).get("seismic_docs") or {})
        d = docs.pop(key, None) or {}
        if d.get("rel"):
            (rdir / d["rel"]).unlink(missing_ok=True)
        if key == "ground":
            shutil.rmtree(rdir / "지반", ignore_errors=True)
        _put(r, seismic_docs=docs)
    db.commit()
    return _project_out(db, f, r)


@router.get("/projects/{rid}/docs/{key}/file")
def doc_file(rid: int, key: str, item: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from core.stored_path import to_full
    from server.sitok import drawings as D

    if key not in DOC:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 서류 칸입니다.")
    f, r = _require(db, user, rid)
    fdir, rdir = _dirs(f, r)
    p = None
    if key in MULTI:
        p = next((it["path"] for it in D.items(f, key, fdir) if it["id"] == item), None)
    elif key == "vendor":
        body = (_sv(r).get("seismic_files") or {}).get("body")
        p = Path(to_full(body)) if body else None
    else:
        d = (_sv(r).get("seismic_docs") or {}).get(key) or {}
        p = rdir / d["rel"] if d.get("rel") else None
    if p is None or not Path(p).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일이 없습니다.")
    name = f"{f.name}_{DOC[key][0]}{Path(p).suffix}"
    return FileResponse(p, filename=None, headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(name)}"})


class FloorplanIn(BaseModel):
    item: str
    page: int = 1
    name: str = ""  # "" = 자동(읽은 이름)으로


@router.patch("/projects/{rid}/floorplans")
def rename_floorplan(rid: int, body: FloorplanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """1.2 평면도 이름 고치기(10/27 사용자 "네이밍이 다르면 고칠 수 있게") — 도면 칸 항목 titles{쪽: 이름}, 보고서는 고친 이름·그 층 차례로."""
    from server.sitok import seismic_fill as SF

    f, r = _require(db, user, rid)
    d = dict(f.drawings or {})
    lst = [dict(it) for it in d.get("floorplan") or []]
    it = next((x for x in lst if x["id"] == body.item), None)
    if it is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "평면도 파일이 없습니다.")
    titles = dict(it.get("titles") or {})
    name = SF.plan_name(body.name)[:40]
    if name:
        titles[str(body.page)] = name
    else:
        titles.pop(str(body.page), None)
    it["titles"] = titles
    d["floorplan"] = lst
    f.drawings = d
    db.commit()
    return _project_out(db, f, r)


@router.get("/projects/{rid}/floorplans/{item}/{page}/thumb")
def floorplan_thumb(rid: int, item: str, page: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from server.sitok import drawings as D
    from server.sitok import seismic_fill as SF

    f, r = _require(db, user, rid)
    fdir, _ = _dirs(f, r)
    p = next((x["path"] for x in D.items(f, "floorplan", fdir) if x["id"] == item), None)
    if p is None or page < 1 or page > D.pages_of(Path(p)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "평면도 쪽이 없습니다.")
    return Response(SF.plan_thumb(Path(p), page), media_type="image/png", headers={"Cache-Control": "private, max-age=600"})


class GroundIn(BaseModel):
    bh: str
    slot: str | None = None  # 사진 칸 — file = 후보 그림 이름("" = 비우기)
    file: str | None = None
    depth: str | None = None
    vs: float | None = None
    cls: str | None = None
    apply_depth: float | None = None


@router.patch("/projects/{rid}/ground")
def update_ground(rid: int, body: GroundIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f, r = _require(db, user, rid)
    docs = dict(_sv(r).get("seismic_docs") or {})
    g = dict(docs.get("ground") or {})
    parsed = dict(g.get("parsed") or {})
    holes = [dict(h) for h in parsed.get("holes") or []]
    h = next((x for x in holes if x["bh"] == body.bh), None)
    if h is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "그 시추공이 없습니다.")
    if body.slot is not None:
        if body.slot not in {k for k, _, _ in SD.GROUND_SLOTS}:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "없는 사진 칸입니다.")
        names = {x["file"] for hh in holes for x in hh.get("extra") or []}
        photos = dict(h.get("photos") or {})
        if body.file:
            if body.file not in names:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "지반조사보고서에서 뽑은 사진만 고를 수 있습니다.")
            photos[body.slot] = body.file
        else:
            photos.pop(body.slot, None)
        h["photos"] = photos
    for k in ("depth", "vs", "cls", "apply_depth"):
        v = getattr(body, k)
        if v is not None:
            h[k] = v
    parsed["holes"] = holes
    g["parsed"] = parsed
    docs["ground"] = g
    _put(r, seismic_docs=docs)
    db.commit()
    return _project_out(db, f, r)


@router.get("/projects/{rid}/ground/img/{name}")
def ground_img(rid: int, name: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f, r = _require(db, user, rid)
    if not re.fullmatch(r"[\w\-.]+\.png", name):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "그림 이름이 이상합니다.")
    p = _dirs(f, r)[1] / "지반" / name
    if not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "그림이 없습니다.")
    return FileResponse(p, media_type="image/png")


@router.delete("/projects/{rid}")
def delete_project(rid: int, password: str = Body("", embed=True), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from server.api.routers.sitok import _check_delete_password, _delete_facility

    f, _ = _require(db, user, rid)
    _check_delete_password(user, password)
    _delete_facility(db, f)
    db.commit()
    return {"ok": True}


# ---------- 현장조사 입력(2단계 — 부재 단면·코어·조적조·현장 사진·분석 글, server/sitok/seismic_field) ----------
def _field(r: SitokReport) -> dict:
    from server.sitok import seismic_field as SF

    return SF.normalize(_sv(r).get("seismic_field"))


def _field_out(db: Session, f: SitokFacility, r: SitokReport) -> dict:
    from server.sitok import rebar_schedule as RS
    from server.sitok import seismic_field as SF

    fd = _field(r)
    sch = RS.view((f.ledger or {}).get("rebar_schedule"))
    below, above = f.floors_below or 0, f.floors_above or 0
    floors = [-b for b in range(below, 0, -1)] + list(range(1, above + 1)) or [1]
    grade = ((f.ledger or {}).get("register") or {}).get("grade") or grade_of(f.main_use or f.use_type or "")
    _, rdir = _dirs(f, r)
    core_doc = (_sv(r).get("seismic_docs") or {}).get("core") or {}
    return {"id": r.id, "facility_id": f.id, "name": f.name, "members": fd["members"], "cores": fd["cores"], "masonry": fd["masonry"],
            "texts": fd["texts"], "text_labels": [[k, label] for k, label, _ in SF.TEXTS], "core_note": fd["core_note"], "core_design": fd["core_design"],
            "summary": fd["summary"],
            "photos": {k: {"at": v.get("at", ""), "name": v.get("name", "")} for k, v in fd["photos"].items()},
            "photo_slots": [[k, label, where] for k, label, where in SF.PHOTO_SLOTS], "core_stats": SF.core_stats(fd["cores"]),
            "has_core_report": bool(core_doc.get("rel") and (rdir / core_doc["rel"]).exists()),
            "floors": [{"n": n, "label": SF.floor_label(n)} for n in floors], "units": SD.survey_units(f), "item_units": SD.item_units(f),
            "sample_floors": SD.sample_floors(f, "member"), "masonry_floors": SD.sample_floors(f, "masonry"),  # 항목별 조사단위 층(10/26)
            "member_kinds": list(SD.MEMBER_KINDS), "member_plan": SD.member_plan(f, fd["member_plan"]), "member_order": fd["member_order"],
            "member_plan_default": SD.member_plan(f), "drawings": SD.has_drawings(f),
            "masonry_types": fd["masonry_types"], "masonry_plan": SD.masonry_plan(f, fd["masonry_plan"]), "masonry_plan_default": SD.masonry_plan(f),
            "min_counts": SD.min_counts(SD.item_units(f), grade, SD.has_drawings(f)), "rebar": _rebar_done(r),
            "schedule": [{"id": x["id"], "kind": x["kind"], "marks": x["marks"], "floors": x["floors"],
                          "size": x.get("size") or (f"THK={x['thickness']}" if x.get("thickness") else ""),  # 벽체 = 두께(견본 "THK=200")
                          "range": RS.floor_range(x["floors"])} for x in sch["items"] if x["kind"] in SF.MEMBER_KINDS]}  # 층 범위 — 그 층 칸만(철근탐사처럼, 10/22)


def _rebar_done(r: SitokReport) -> int:
    """철근탐사 결과 있는 줄 수(미리 만든 빈 칸은 안 셈, 10/22)."""
    from server.sitok import rebar_survey as RV

    return sum(1 for x in RV.normalize(_sv(r).get("rebar"))["rows"] if RV.has_result(x))


@router.get("/projects/{rid}/field")
def get_field(rid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f, r = _require(db, user, rid)
    return _field_out(db, f, r)


@router.patch("/projects/{rid}/field")
def save_field(rid: int, body: dict = Body(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """{members?, cores?, masonry?, texts?, core_note?} — 보낸 것만 바꿈. 부재 단면은 일람표 칸(item_id)을 고르면 도면치수·부호를 채움(사람이 쓴 값은 그대로)."""
    from server.sitok import rebar_schedule as RS
    from server.sitok import seismic_field as SF

    f, r = _require(db, user, rid)
    cur = _field(r)
    for k in ("members", "cores", "masonry", "texts", "core_note", "core_design", "summary", "member_plan", "member_order", "masonry_types", "masonry_plan"):
        if k in body:
            cur[k] = body[k]
    cur = SF.apply_types(SF.normalize(cur))  # 조적 칸은 목록 값으로(10/22)
    items = {x["id"]: x for x in RS.view((f.ledger or {}).get("rebar_schedule"))["items"]}
    for m in cur["members"]:
        it = items.get(m["item_id"])
        if it is not None:
            m["kind"] = it["kind"] if it["kind"] in SF.MEMBER_KINDS else m["kind"]
            m["mark"] = m["mark"] or (it["marks"][0] if it["marks"] else "")
            m["design"] = m["design"] or SF.size_text(it.get("size") or (f"THK={it['thickness']}" if it.get("thickness") else ""))
            if m["match"] == "일치":
                m["measured"] = m["design"]
    _put(r, seismic_field={**(_sv(r).get("seismic_field") or {}), **cur})
    db.commit()
    return _field_out(db, f, r)


@router.post("/projects/{rid}/field/photo/{slot}")
def upload_field_photo(rid: int, slot: str, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from server.contract_docs import files
    from server.sitok import seismic_field as SF

    if slot not in SF.PHOTO:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 사진 칸입니다.")
    f, r = _require(db, user, rid)
    _, rdir = _dirs(f, r)
    dest = rdir / "현장사진" / f"{slot}.jpg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        files.save_jpeg(file.file.read(), file.filename or f"{slot}.jpg", dest)
    except Exception as err:  # noqa: BLE001 — 그림이 아니면
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "사진(jpg·png 등)을 올려 주세요.") from err
    sf = dict(_sv(r).get("seismic_field") or {})
    photos = dict(sf.get("photos") or {})
    photos[slot] = {"rel": f"현장사진/{slot}.jpg", "name": file.filename or "", "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    sf["photos"] = photos
    _put(r, seismic_field=sf)
    db.commit()
    return _field_out(db, f, r)


@router.delete("/projects/{rid}/field/photo/{slot}")
def delete_field_photo(rid: int, slot: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f, r = _require(db, user, rid)
    _, rdir = _dirs(f, r)
    sf = dict(_sv(r).get("seismic_field") or {})
    photos = dict(sf.get("photos") or {})
    p = photos.pop(slot, None)
    if p and p.get("rel"):
        (rdir / p["rel"]).unlink(missing_ok=True)
    sf["photos"] = photos
    _put(r, seismic_field=sf)
    db.commit()
    return _field_out(db, f, r)


@router.get("/projects/{rid}/field/photo/{slot}")
def field_photo(rid: int, slot: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f, r = _require(db, user, rid)
    p = (_field(r)["photos"].get(slot) or {}).get("rel")
    path = _dirs(f, r)[1] / p if p else None
    if path is None or not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return FileResponse(path, media_type="image/jpeg")


@router.post("/projects/{rid}/field/cores/read")
def read_cores(rid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """서류 칸 압축강도 시험성적서 → 코어 줄(AI, 약 20원 — 화면 [🤖 성적서에서 읽기]). 읽은 줄로 바꿈(사람이 확인·고침)."""
    from server.sitok import seismic_field as SF

    f, r = _require(db, user, rid)
    _, rdir = _dirs(f, r)
    doc = (_sv(r).get("seismic_docs") or {}).get("core") or {}
    if not doc.get("rel") or not (rdir / doc["rel"]).exists():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "먼저 건 화면 서류 칸에 압축강도 시험성적서를 올려 주세요.")
    try:
        got = SF.read_core_report(user.company_id, rdir / doc["rel"])
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"성적서를 읽지 못했습니다(직접 넣어 주세요): {str(err).splitlines()[0][:120]}") from err
    if not got["rows"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "성적서에서 코어 강도 줄을 못 찾았습니다 — 직접 넣어 주세요.")
    sf = dict(_sv(r).get("seismic_field") or {})
    sf["cores"] = got["rows"]
    sf["core_note"] = " · ".join(x for x in (got["lab"], f"접수번호 {got['test_no']}" if got["test_no"] else "", f"발급 {got['issued']}" if got["issued"] else "") if x)
    _put(r, seismic_field=sf)
    db.commit()
    return _field_out(db, f, r) | {"read": len(got["rows"])}


# ---------- 요약문 책임기술자 종합의견(10/22 민재형 "둘 다 가능하게") ----------
def _summary_base(db: Session, f: SitokFacility, r: SitokReport) -> tuple[str, dict]:
    """견본 문장 채우기 글 + AI에 줄 자료."""
    from core.stored_path import to_full
    from server.sitok import seismic_build as SB
    from server.sitok import seismic_field as SF
    from server.sitok import seismic_fill as SFL
    from server.sitok import seismic_vendor as SV
    from server.sitok.wall_build import Hwpx

    d = SB.gather(db, r, f)
    field = _field(r)
    reg = (f.ledger or {}).get("register") or {}
    body = (_sv(r).get("seismic_files") or {}).get("body")
    vendor_text = ""
    if body and Path(to_full(body)).exists():
        try:
            vendor_text = " ".join(SV._text(Hwpx(SV.vendor_hwpx(Path(to_full(body)))).root).split())
        except Exception:  # noqa: BLE001 — 외주 글 없이
            vendor_text = ""
    text = SFL.summary_text(d, field, f, reg, vendor_text)
    facts = {"건물": d["name"], "사용승인": d["completion"].isoformat() if d.get("completion") else "", "내진등급": reg.get("grade") or "",
             "중량물": field["texts"]["heavy"], "균열": field["texts"]["crack"], "누수": field["texts"]["leak"], "철근노출": field["texts"]["rebar"],
             "노후화": field["texts"]["aging"], "코어": SF.core_stats(field["cores"]), "외주결과": SFL.vendor_results(vendor_text),
             "결함": [x[3] for x in SFL.defect_rows(db, r.id)][:40]}
    return text, facts


@router.post("/projects/{rid}/field/summary/{mode}")
def make_summary(rid: int, mode: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """mode = template(견본 문장에 값만, 무료) | ai(이번 건 자료로 AI가 다시 씀, 약 30원). 만든 글을 저장하고 돌려줌(화면에서 고쳐 저장)."""
    import json

    if mode not in ("template", "ai"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "template 또는 ai")
    f, r = _require(db, user, rid)
    text, facts = _summary_base(db, f, r)
    if mode == "ai":
        from server.sitok import vision

        prompt = ("아래는 학교시설 내진성능평가 보고서 '책임기술자 종합의견' 초안과 이번 건 자료입니다. 초안의 문단 구성과 말투(…하였다, …판단됨)를 따라 "
                  "이번 건 자료에 맞게 다듬어 주세요. 자료에 없는 수치·부재 이름은 지어내지 말고, 결함이 있으면 주된 결함 종류와 의견을 한 문장 넣으세요. "
                  "문단마다 줄을 바꾸고, 머리말 없이 글만 주세요.\n\n[초안]\n" + text + "\n\n[자료]\n" + json.dumps(facts, ensure_ascii=False, default=str))
        try:
            got = vision.ask(user.company_id, [], prompt, max_tokens=3000, effort="low", writing=True).strip()
        except Exception as err:  # noqa: BLE001
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI 초안을 못 만들었습니다: {str(err).splitlines()[0][:120]}") from err
        text = got or text
    sf = dict(_sv(r).get("seismic_field") or {})
    sf["summary"] = text
    _put(r, seismic_field=sf)
    db.commit()
    return _field_out(db, f, r) | {"made": mode}


EQ_STYLE = """[견본 말투 예 — 내용은 이번 건 자료로만]
부재치수 조사 결과: 본 건물은 철근콘크리트 구조이며, 설계도면을 보유하고 있는 상태로, 확인된 도면과 실제 측정한 치수를 비교하였으며, 부재규격 현장조사 결과는 설계도서와 대부분 일치하나 지상5층 B1부재가 구조도면과 실측 수치와 상이하여 현장 실측 데이터를 내진성능 평가에 반영하였다.
철근배근 조사 결과: 본 건물은 철근콘크리트 구조이며, 설계도서 및 구조도면을 보유하고 있어, 실제 철근배근 상태를 조사하여 구조도면과 비교하여 일치 여부를 확인하였음.
강재 접합부 조사 / 강재 부식 조사: 본 건물은 철근콘크리트 구조로, 강재는 적용되지 않아 조사대상에서 제외하였다.
콘크리트 강도 조사: 구조체의 코어채취에 의한 콘크리트 압축강도 조사결과, 15.7~17.3MPa(평균 16.6MPa)로 조사되었으며 … / 내진성능평가에는 현장조사 설계기준강도 값인 15.8MPa를 적용하였음.
중량물: 지붕층 실외기 및 환기설비 이외에는 특기할만한 하중의 증가는 없는 것으로 조사되어 대체적으로 양호한 것으로 조사되었다.
마감재: 마감재 조사 결과, 외부 치장벽돌, 외단열시스템 마감, 커튼월 등이 조사됨.
조적 허리벽 및 채움벽: 허리벽 · 채움벽 조사 결과, 채움벽과 허리벽은 구조체와 밀실하게 연결되었으며, 마감 모르타르, 상단부 사춤상태 등은 양호한 것으로 조사됨."""


def _eq_facts(db: Session, f: SitokFacility, r: SitokReport) -> dict:
    """요약 장비조사·비구조 AI에 줄 이번 건 자료(입력한 것만)."""
    from collections import Counter

    from server.sitok import rebar_survey as RV
    from server.sitok import seismic_field as SF
    from server.sitok import seismic_fill as SFL

    field = _field(r)
    rebar = RV.report_rows(RV.normalize(_sv(r).get("rebar"))["rows"])
    dec = SFL.core_decided(field["cores"])
    return {"구조": f.structure or "", "도면": "보유" if SD.has_drawings(f) else "미보유",
            "부재단면": {"조사 개소": len(field["members"]), "도면과 상이": SFL.member_diffs(field["members"]) if field["members"] else []},
            "철근배근": {"조사 개소": len(rebar), "도면과 상이": [f"{x['floor']}층 {x.get('mark') or x['kind']}" for x in rebar if RV.mismatch(x)]},
            "코어": {**SF.core_stats(field["cores"]), "결정 설계기준강도": dec[2] if dec else None, "도면 설계기준강도": field.get("core_design")},
            "조적": {"조사 개소": len(field["masonry"]), "구분": dict(Counter(x["kind"] for x in field["masonry"])),
                   "적용 상태": dict(Counter(x["applied"] for x in field["masonry"])), "경계면": dict(Counter(x["boundary"] for x in field["masonry"])),
                   "노출": dict(Counter(x["expose"] for x in field["masonry"]))},
            "결함(외관조사)": [{"위치": x[1], "부재": x[2], "결함": x[3], "크기·개수": x[4]} for x in SFL.defect_rows(db, r.id)][:60],
            "현장 사진 칸": sorted(field["photos"])}


@router.post("/projects/{rid}/field/texts/ai")
def ai_eq_texts(rid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """요약 (1) 현장 시험 및 분석 — 장비조사·비구조 조사 결과 칸을 이번 건 입력값으로 AI가 씀(약 30원, 10/22 형 "AI 작성 기능 추가"). 자료 없는 칸은 빈칸."""
    import json

    from server.sitok import seismic_field as SF
    from server.sitok import vision

    f, r = _require(db, user, rid)
    keys = [k for k, _l, _d in SF.TEXTS]
    labels = {k: label for k, label, _ in SF.TEXTS}
    prompt = ("아래는 학교시설 내진성능평가 보고서의 조사결과 글 칸(각 글은 본문 조사결과와 요약 표에 같이 들어감)과 이번 건 현장조사 입력 자료입니다. "
              "칸마다 보고서 말투(…조사되었다, …반영하였다)로 글머리 문장 1~3개를 써 주세요(여러 개면 줄을 바꿈). 자료에 없는 수치·부재·위치는 지어내지 말고, "
              "그 칸의 자료가 없으면 빈 문자열로 두세요(예: 부재 단면 조사 개소 0이면 부재규격 빈칸, 결함 목록이 비면 외관조사 칸은 빈칸). "
              "강재 칸(강재 접합부·부식·외관조사 강재)은 구조가 철근콘크리트조면 '본 건물은 철근콘크리트 구조로, 강재는 적용되지 않아 조사대상에서 제외하였다.'로 쓰세요.\n"
              f"JSON만: {json.dumps({k: '' for k in keys}, ensure_ascii=False)}\n칸 이름: {json.dumps(labels, ensure_ascii=False)}\n\n{EQ_STYLE}\n\n[이번 건 자료]\n"
              + json.dumps(_eq_facts(db, f, r), ensure_ascii=False, default=str))
    try:
        got = vision.ask_json(user.company_id, [], prompt, max_tokens=3000, effort="low", writing=True) or {}
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI 초안을 못 만들었습니다: {str(err).splitlines()[0][:120]}") from err
    if not isinstance(got, dict):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "AI 답을 읽지 못했습니다 — 다시 눌러 주세요.")
    sf = dict(_sv(r).get("seismic_field") or {})
    texts = dict(sf.get("texts") or {})
    for k in keys:
        texts[k] = str(got.get(k) or "").strip()[:600]
    sf["texts"] = texts
    _put(r, seismic_field=sf)
    db.commit()
    return _field_out(db, f, r) | {"made": "ai", "filled": sum(1 for k in keys if texts[k])}


# ---------- 과업수행계획서 자동(10/22) · 스캔 건축물대장 AI 읽기(10/22) ----------
@router.post("/projects/{rid}/docs/plan/auto")
def auto_plan(rid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """견본 과업수행계획서에 용역명·기간·건물·위치도·일정·기술자를 채워 서류 칸 "과업수행계획서"로 둠(내려받아 고치고 다시 올려도 됨)."""
    from server.sitok import seismic_plan

    f, r = _require(db, user, rid)
    _, rdir = _dirs(f, r)
    for old in (rdir / "서류").glob("과업수행계획서.*") if (rdir / "서류").exists() else []:
        old.unlink(missing_ok=True)
    try:
        seismic_plan.build_plan(db, r, f, rdir / "서류" / "과업수행계획서.hwpx")
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
    docs = dict(_sv(r).get("seismic_docs") or {})
    docs["plan"] = {"rel": "서류/과업수행계획서.hwpx", "name": f"{f.name}_과업수행계획서(자동).hwpx", "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "by": user.display_name or "", "note": "자동으로 만들었습니다 — 받아서 고치고 다시 올려도 됩니다"}
    _put(r, seismic_docs=docs)
    db.commit()
    return _project_out(db, f, r) | {"msg": "과업수행계획서를 자동으로 만들었습니다"}


@router.post("/projects/{rid}/docs/register/ai")
def register_ai(rid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """올린 건축물대장을 AI로 읽어 건물 정보에 넣음(글자 없는 스캔본용, 약 30원)."""
    f, r = _require(db, user, rid)
    fdir, rdir = _dirs(f, r)
    d = (_sv(r).get("seismic_docs") or {}).get("register") or {}
    if not d.get("rel") or not (rdir / d["rel"]).exists():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "먼저 건축물대장을 올려 주세요.")
    try:
        reg = SD.read_register_ai(rdir / d["rel"], user.company_id)
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"건축물대장을 못 읽었습니다: {str(err).splitlines()[0][:120]}") from err
    _apply_building(f, _register_to_building(reg))
    _rename(db, f, r, fdir)
    docs = dict(_sv(r).get("seismic_docs") or {})
    docs["register"] = {**d, "note": "AI로 읽었습니다 — 건물 정보에서 확인해 주세요"}
    _put(r, seismic_docs=docs)
    db.commit()
    return _project_out(db, f, r) | {"msg": "AI로 읽었습니다 — 건물 정보에서 확인해 주세요"}
