"""시특법 시설물·점검 용역 계약(2026-10-10 2단계) — 보고서 자동화 · 시특법 화면(sitok.html 목록, sitok-facility.html 등록·고치기).

- `GET    /sitok/facilities` — 목록(시설물 + 가장 최근 계약).
- `POST   /sitok/read` — PDF 하나 올리기(kind = ledger 관리대장 | contract 계약서) → AI로 읽은 칸 + 임시 표(token). 읽기에 실패해도 token은 준다(손으로 채움).
- `POST   /sitok/facilities` — 시설물 + 첫 계약 저장(ledger_token·contract_token이 있으면 PDF를 시설물 폴더로 옮김).
- `GET/PATCH/DELETE /sitok/facilities/{id}` — 보기·고치기·지우기(지우기는 현장 삭제와 같은 회사 삭제 비밀번호).
- `POST   /sitok/facilities/{id}/contracts`, `PATCH/DELETE /sitok/contracts/{id}` — 계약 더하기(다음 해 등)·고치기·지우기.
- `GET    /sitok/files/ledger/{facility_id}`, `/sitok/files/contract/{contract_id}` — 올린 PDF 보기.
값의 뜻·기본값(민간 = 독자수행 100%·수의계약·건축, 템플릿 2종/3종일반/3종학교)은 core/models_web.py SitokFacility·SitokContract 설명.
"""

from __future__ import annotations

import datetime
import secrets
import shutil
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core import config
from core.db import DATA_DIR
from core.models_web import SitokContract, SitokFacility, User
from server.api import storage
from server.api.deps import get_current_user, get_db
from server.api.security import verify_password
from server.sitok import reader

router = APIRouter(prefix="/sitok", tags=["sitok"])
ROOT = DATA_DIR / "_시특법"
UPLOAD_DIR = storage.SYSTEM_DIR / "시특법_올림"  # 등록 전 임시(하루 지나면 지움)
TEMPLATES = ("2종", "3종일반", "3종학교")
SECTORS = ("민간", "관급")
HALVES = ("상반기", "하반기", "연간")
JOINT_TYPES = ("독자수행", "공동이행", "분담이행")  # 점검진단실적 제출 사이트와 같은 선택지
BID_METHODS = ("일반경쟁", "제한경쟁", "지명경쟁", "수의계약", "기타")
FIELDS = ("교량 및 터널", "건축", "항만", "수리시설")
FAC_FIELDS = ("fms_no", "name", "template", "kind", "use_type", "main_use", "address", "owner_name", "owner_type", "owner_phone",
              "completion_date", "structure", "floors_above", "floors_below", "floors_roof", "max_height", "total_area", "building_area", "memo")
CON_FIELDS = ("sector", "title", "contract_no", "contract_date", "start_date", "end_date", "halves", "first_half_end", "second_half_start",
              "amount", "rep_name", "joint_type", "joint_pct", "bid_method", "field")
DATES = {"completion_date", "contract_date", "start_date", "end_date", "first_half_end", "second_half_start"}


class FacilityIn(BaseModel):
    fms_no: str | None = None
    name: str | None = None
    template: str | None = None
    kind: str | None = None
    use_type: str | None = None
    main_use: str | None = None
    address: str | None = None
    owner_name: str | None = None
    owner_type: str | None = None
    owner_phone: str | None = None
    completion_date: datetime.date | None = None
    structure: str | None = None
    floors_above: int | None = None
    floors_below: int | None = None
    floors_roof: int | None = None
    max_height: float | None = None
    total_area: float | None = None
    building_area: float | None = None
    memo: str | None = None


class ContractIn(BaseModel):
    sector: str | None = None
    title: str | None = None
    contract_no: str | None = None
    contract_date: datetime.date | None = None
    start_date: datetime.date | None = None
    end_date: datetime.date | None = None
    halves: str | None = None
    first_half_end: datetime.date | None = None
    second_half_start: datetime.date | None = None
    amount: int | None = None
    rep_name: str | None = None
    joint_type: str | None = None
    joint_pct: int | None = None
    bid_method: str | None = None
    field: str | None = None
    contract_token: str | None = None


class CreateIn(BaseModel):
    facility: FacilityIn
    contract: ContractIn | None = None
    ledger_token: str | None = None
    ledger_extra: dict | None = None  # 관리대장에서 읽은 나머지 값(시설물분류 등)


# ---------- 파일 ----------

def _facility_dir(f: SitokFacility) -> Path:
    return ROOT / f"{storage._clean(f.name)[:30] or '시설물'}_{f.id}"


def _token_path(token: str | None) -> Path | None:
    if not token or not token.isalnum():
        return None
    p = UPLOAD_DIR / f"{token}.pdf"
    return p if p.exists() else None


def _clean_uploads() -> None:
    if not UPLOAD_DIR.exists():
        return
    old = datetime.datetime.now().timestamp() - 86400
    for p in UPLOAD_DIR.glob("*.pdf"):
        if p.stat().st_mtime < old:
            p.unlink(missing_ok=True)


def _take(token: str | None, dest: Path) -> str:
    """임시로 올린 PDF를 시설물 폴더로 옮기고 저장할 경로(문자열)를 준다. 없으면 ""."""
    src = _token_path(token)
    if src is None:
        return ""
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), dest)
    return str(dest)


# ---------- 값 다듬기 ----------

def _iso(v):
    return v.isoformat() if isinstance(v, (datetime.date, datetime.datetime)) else v


def _check(field: str, value, allowed) -> None:
    if value is not None and value not in allowed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{field}은(는) {'·'.join(allowed)} 중 하나입니다.")


def _apply_facility(row: SitokFacility, body: FacilityIn) -> None:
    data = body.model_dump(exclude_unset=True)
    _check("보고서 틀", data.get("template"), TEMPLATES)
    for k, v in data.items():
        setattr(row, k, v.strip() if isinstance(v, str) else v)


def _apply_contract(row: SitokContract, body: ContractIn) -> None:
    data = body.model_dump(exclude_unset=True, exclude={"contract_token"})
    _check("계약 구분", data.get("sector"), SECTORS)
    _check("반기", data.get("halves"), HALVES)
    _check("공동수급", data.get("joint_type"), JOINT_TYPES)
    _check("입찰방식", data.get("bid_method"), BID_METHODS)
    _check("수행분야", data.get("field"), FIELDS)
    for k, v in data.items():
        setattr(row, k, v.strip() if isinstance(v, str) else v)


def _contract_out(c: SitokContract) -> dict:
    return {"id": c.id, **{k: _iso(getattr(c, k)) for k in CON_FIELDS}, "has_pdf": bool(c.contract_pdf and Path(c.contract_pdf).exists()),
            "created_at": c.created_at.strftime("%Y-%m-%d") if c.created_at else ""}


def _facility_out(db: Session, f: SitokFacility, with_contracts: bool = True) -> dict:
    contracts = (db.query(SitokContract).filter(SitokContract.facility_id == f.id)
                 .order_by(SitokContract.start_date.desc().nullslast(), SitokContract.id.desc()).all())
    out = {"id": f.id, **{k: _iso(getattr(f, k)) for k in FAC_FIELDS}, "ledger": f.ledger or {},
           "has_ledger_pdf": bool(f.ledger_pdf and Path(f.ledger_pdf).exists()),
           "latest": _contract_out(contracts[0]) if contracts else None, "contract_count": len(contracts)}
    if with_contracts:
        out["contracts"] = [_contract_out(c) for c in contracts]
    return out


def _require_facility(db: Session, user: User, facility_id: int) -> SitokFacility:
    f = db.get(SitokFacility, facility_id)
    if f is None or f.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "시설물을 찾을 수 없습니다.")
    return f


def _require_contract(db: Session, user: User, contract_id: int) -> SitokContract:
    c = db.get(SitokContract, contract_id)
    if c is None or c.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "계약을 찾을 수 없습니다.")
    return c


def guess_template(grade: str, use_type: str, main_use: str) -> str:
    """관리대장 종별·용도로 보고서 틀 추정 — 3종이면서 학교(교육연구시설)면 3종학교(치장벽돌 점검·내진보강 점검표 추가)."""
    if grade != "3":
        return "2종"
    return "3종학교" if "학교" in main_use or "교육연구" in use_type else "3종일반"


# ---------- API ----------

@router.get("/options")
def options(user: User = Depends(get_current_user)):
    """화면 고르기 칸의 선택지(제출 사이트와 같은 이름)."""
    return {"templates": TEMPLATES, "sectors": SECTORS, "halves": HALVES, "joint_types": JOINT_TYPES, "bid_methods": BID_METHODS, "fields": FIELDS}


@router.get("/facilities")
def list_facilities(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(SitokFacility).filter(SitokFacility.company_id == user.company_id).order_by(SitokFacility.id.desc()).all()
    return [_facility_out(db, f, with_contracts=False) for f in rows]


@router.post("/read")
def read_pdf(kind: str = Form(...), file: UploadFile = File(...), user: User = Depends(get_current_user)):
    if kind not in ("ledger", "contract"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "kind는 ledger 또는 contract입니다.")
    data = file.file.read()
    if not data.startswith(b"%PDF"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "PDF 파일을 올려 주세요.")
    _clean_uploads()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(12)
    path = UPLOAD_DIR / f"{token}.pdf"
    path.write_bytes(data)
    try:
        parsed = reader.read_ledger(path, user.company_id) if kind == "ledger" else reader.read_contract(path, user.company_id)
    except Exception as err:  # noqa: BLE001 — 읽기 실패해도 파일은 붙이고 손으로 채우게
        return {"token": token, "fields": {}, "error": f"자동으로 읽지 못했습니다 — 직접 입력해 주세요. ({str(err).splitlines()[0][:160]})"}
    fields = {k: _iso(v) for k, v in parsed.items()}
    if kind == "ledger":
        fields["template"] = guess_template(fields.get("grade", ""), fields.get("use_type", ""), fields.get("main_use", ""))
    return {"token": token, "fields": fields, "error": ""}


@router.post("/facilities")
def create_facility(body: CreateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not (body.facility.name or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "시설물명을 넣어 주세요.")
    f = SitokFacility(company_id=user.company_id, created_by=user.display_name or "", ledger=body.ledger_extra or None)
    _apply_facility(f, body.facility)
    db.add(f)
    db.flush()
    f.ledger_pdf = _take(body.ledger_token, _facility_dir(f) / "시설물관리대장.pdf")
    if body.contract is not None:
        _add_contract(db, user, f, body.contract)
    db.commit()
    return _facility_out(db, f)


def _add_contract(db: Session, user: User, f: SitokFacility, body: ContractIn) -> SitokContract:
    c = SitokContract(company_id=user.company_id, facility_id=f.id, created_by=user.display_name or "")
    _apply_contract(c, body)
    db.add(c)
    db.flush()
    c.contract_pdf = _take(body.contract_token, _facility_dir(f) / f"계약서_{c.id}.pdf")
    return c


@router.get("/facilities/{facility_id}")
def get_facility(facility_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _facility_out(db, _require_facility(db, user, facility_id))


@router.patch("/facilities/{facility_id}")
def update_facility(facility_id: int, body: FacilityIn, ledger_token: str | None = None,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = _require_facility(db, user, facility_id)
    old_dir = _facility_dir(f)
    _apply_facility(f, body)
    if _facility_dir(f) != old_dir and old_dir.exists():  # 이름이 바뀌면 폴더도
        old_dir.rename(_facility_dir(f))
        f.ledger_pdf = str(_facility_dir(f) / Path(f.ledger_pdf).name) if f.ledger_pdf else ""
        for c in db.query(SitokContract).filter(SitokContract.facility_id == f.id):
            c.contract_pdf = str(_facility_dir(f) / Path(c.contract_pdf).name) if c.contract_pdf else ""
    if ledger_token:
        f.ledger_pdf = _take(ledger_token, _facility_dir(f) / "시설물관리대장.pdf") or f.ledger_pdf
    db.commit()
    return _facility_out(db, f)


@router.delete("/facilities/{facility_id}")
def delete_facility(facility_id: int, password: str = Body("", embed=True), user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """시설물 지우기(계약·올린 PDF까지, 되돌릴 수 없음) — 현장 삭제와 같은 회사 공용 삭제 비밀번호."""
    password_hash = config.get_site_delete_password_hash(user.company_id)
    if not password_hash:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "삭제 비밀번호가 아직 없습니다. '설정' 탭에서 먼저 정하세요.")
    if not verify_password(password, password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "삭제 비밀번호가 맞지 않습니다.")
    f = _require_facility(db, user, facility_id)
    folder = _facility_dir(f)
    db.query(SitokContract).filter(SitokContract.facility_id == f.id).delete()
    db.delete(f)
    db.commit()
    shutil.rmtree(folder, ignore_errors=True)
    return {"ok": True}


@router.post("/facilities/{facility_id}/contracts")
def add_contract(facility_id: int, body: ContractIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = _require_facility(db, user, facility_id)
    _add_contract(db, user, f, body)
    db.commit()
    return _facility_out(db, f)


@router.patch("/contracts/{contract_id}")
def update_contract(contract_id: int, body: ContractIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _require_contract(db, user, contract_id)
    _apply_contract(c, body)
    if body.contract_token:
        f = db.get(SitokFacility, c.facility_id)
        c.contract_pdf = _take(body.contract_token, _facility_dir(f) / f"계약서_{c.id}.pdf") or c.contract_pdf
    db.commit()
    return _facility_out(db, db.get(SitokFacility, c.facility_id))


@router.delete("/contracts/{contract_id}")
def delete_contract(contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _require_contract(db, user, contract_id)
    if c.contract_pdf:
        Path(c.contract_pdf).unlink(missing_ok=True)
    fid = c.facility_id
    db.delete(c)
    db.commit()
    return _facility_out(db, db.get(SitokFacility, fid))


@router.get("/files/ledger/{facility_id}")
def ledger_file(facility_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = _require_facility(db, user, facility_id)
    if not f.ledger_pdf or not Path(f.ledger_pdf).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "올린 관리대장이 없습니다.")
    return FileResponse(f.ledger_pdf, media_type="application/pdf", filename=f"{f.name}_시설물관리대장.pdf", content_disposition_type="inline")


@router.get("/files/contract/{contract_id}")
def contract_file(contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _require_contract(db, user, contract_id)
    if not c.contract_pdf or not Path(c.contract_pdf).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "올린 계약서가 없습니다.")
    return FileResponse(c.contract_pdf, media_type="application/pdf", filename=f"계약서_{c.id}.pdf", content_disposition_type="inline")
