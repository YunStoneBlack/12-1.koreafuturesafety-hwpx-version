"""서류 자동화 · 시특법 계약(2026-10-12 사용자, alembic 0040 sitok_doc_contract) — 산안법처럼 보고서 쪽과 따로, 현장(시설물) 연결.
화면 sitok-docs.html(js/sitok-docs.js). 민간 계약서 만들기는 server/sitok/civil.py, 관급 착수계·완료계는 2단계.

- `GET    /sitok/docs/contracts` — 목록. `GET .../blank?sector=` 새 계약 기본값(저장 안 함). `POST .../contracts` 만들기. `GET|PUT|DELETE .../{id}`.
- `POST   /sitok/docs/contracts/{id}/upload/{kind}` — kind: ledger(시설물관리대장 → 시설물명·위치·제원·관리주체) · bizreg(사업자등록증 → 관리주체·대표자·번호·주소)
  · existing(이미 만든·날인한 민간 계약서 → 계약 칸 전부 + 날인본으로 보관) · signed(날인본만 보관). 읽은 값은 빈 칸만(existing은 전부).
- `POST   /sitok/docs/contracts/{id}/make` — 민간 계약서 한글·PDF. `GET .../{id}/file/{name}` — 계약서.hwpx·계약서.pdf·날인본.pdf 등.
- `GET    /sitok/docs/contracts/{id}/candidates`, `POST .../{id}/link` {facility_id|null} — 현장(시설물) 연결.
- `POST   /sitok/docs/contracts/{id}/to-facility` — 연결한 시설물에 보고서 쪽 계약으로 넣기(날인본/만든 PDF를 계약서로, 다시 누르면 고침).
- `GET    /sitok/docs/template`, `POST /sitok/docs/template` — 민간 계약서 양식 받기·고친 양식 올리기(자리표시 검사).
"""
from __future__ import annotations

import datetime
import re
import shutil
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core import config
from core.db import DATA_DIR
from core.models_web import SitokContract, SitokDocContract, SitokFacility, User
from server.api import storage
from server.api.deps import get_current_user, get_db
from server.api.security import verify_password
from server.sitok import civil

router = APIRouter(prefix="/sitok/docs", tags=["sitok"])
ROOT = DATA_DIR / "_시특법_계약"
SECTORS = ("민간", "관급")
TEXT = ("sector", "doc_no", "client", "client_rep", "client_biz_no", "client_address", "facility_name", "location", "spec", "title", "contract_no",
        "guarantee", "delay_rate", "client_manager", "client_phone", "client_email", "site_manager", "site_phone", "site_email", "memo")
DATES = ("contract_date", "start_date", "end_date")
FILES = {"계약서.hwpx": "application/octet-stream", "계약서.pdf": "application/pdf", "날인본.pdf": "application/pdf",
         "시설물관리대장.pdf": "application/pdf", "사업자등록증.pdf": "application/pdf"}


def folder(c: SitokDocContract) -> Path:
    """계약 폴더 "007_시설물명" — 이름이 바뀌면 예전 폴더를 옮김."""
    prefix = f"{c.id:03d}_"
    want = ROOT / (prefix + (storage._clean((c.facility_name or c.client or c.title or "계약")[:40]) or "계약"))
    if want.exists():
        return want
    old = next((p for p in ROOT.glob(f"{prefix}*") if p.is_dir()), None) if ROOT.exists() else None
    if old is not None:
        try:
            old.rename(want)
        except OSError:
            return old
    return want


def _iso(v):
    return v.isoformat() if isinstance(v, (datetime.date, datetime.datetime)) else v


def _date(v) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(str(v)[:10]) if v else None
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"날짜가 맞지 않습니다: {v}") from err


def _rounds(v) -> list[dict]:
    out = []
    for r in v or []:
        try:
            y = int(r.get("year"))
        except (TypeError, ValueError):
            continue
        if r.get("half") not in civil.HALVES:
            continue
        amt = int(str(r.get("amount") or 0).replace(",", "") or 0)
        out.append({"year": y, "half": r["half"], "kind": r.get("kind") if r.get("kind") in civil.KINDS else "정기", "amount": amt})
    return sorted(out, key=lambda r: (r["year"], civil.HALVES.index(r["half"])))


def _require(db: Session, user: User, cid: int) -> SitokDocContract:
    c = db.get(SitokDocContract, cid)
    if c is None or c.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "계약을 찾을 수 없습니다.")
    return c


def _files(c: SitokDocContract) -> dict:
    base = folder(c)
    return {n: (base / n).exists() for n in FILES} | {"날인본.pdf": bool(c.contract_pdf and Path(c.contract_pdf).exists())}


def summary(db: Session, c: SitokDocContract) -> dict:
    f = db.get(SitokFacility, c.facility_id) if c.facility_id else None
    k = civil.kinds_of(c.rounds, c.unit, c.open_ended)
    return {"id": c.id, **{x: getattr(c, x) for x in TEXT}, **{x: _iso(getattr(c, x)) for x in DATES},
            "amount": c.amount, "rounds": c.rounds or [], "open_ended": c.open_ended, "unit": c.unit,
            "kind": k, "kind_word": civil.kind_word(k), "total": civil.total(c.rounds) if not c.open_ended else None,
            "auto_title": civil.default_title(c), "auto_doc_no": civil.default_doc_no(c.contract_date),
            "facility": {"id": f.id, "name": f.name} if f else None, "report_contract_id": c.report_contract_id,
            "files": _files(c), "made_at": c.made_at.strftime("%Y-%m-%d %H:%M") if c.made_at else "",
            "updated": f"{c.updated_at:%Y-%m-%d %H:%M} {c.updated_by}" if c.updated_at else ""}


class ContractIn(BaseModel):
    sector: str | None = None
    doc_no: str | None = None
    client: str | None = None
    client_rep: str | None = None
    client_biz_no: str | None = None
    client_address: str | None = None
    facility_name: str | None = None
    location: str | None = None
    spec: str | None = None
    title: str | None = None
    contract_no: str | None = None
    guarantee: str | None = None
    delay_rate: str | None = None
    client_manager: str | None = None
    client_phone: str | None = None
    client_email: str | None = None
    site_manager: str | None = None
    site_phone: str | None = None
    site_email: str | None = None
    memo: str | None = None
    contract_date: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    amount: int | None = None
    rounds: list[dict] | None = None
    open_ended: bool | None = None
    unit: dict | None = None


def _apply(c: SitokDocContract, body: ContractIn, user: User) -> None:
    data = body.model_dump(exclude_unset=True)
    if "sector" in data and data["sector"] not in SECTORS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "계약 구분은 민간·관급 중 하나입니다.")
    for k in TEXT:
        if k in data and data[k] is not None:
            setattr(c, k, str(data[k]).strip())
    for k in DATES:
        if k in data:
            setattr(c, k, _date(data[k]))
    if "rounds" in data:
        c.rounds = _rounds(data["rounds"])
    if "open_ended" in data:
        c.open_ended = bool(data["open_ended"])
    if "unit" in data:
        u = data["unit"] or {}
        c.unit = {"kind": u.get("kind") if u.get("kind") in civil.KINDS else "정기", "amount": int(str(u.get("amount") or 0).replace(",", "") or 0)} if u else None
    if "amount" in data:
        c.amount = data["amount"]
    if c.sector == "민간":  # 민간 금액 = 회차 합(끝 없는 계약은 비움)
        c.amount = None if c.open_ended else (civil.total(c.rounds) or None)
        if c.open_ended:
            c.end_date = None
    c.updated_at, c.updated_by = datetime.datetime.now(), user.display_name or ""


@router.get("/contracts")
def list_contracts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(SitokDocContract).filter(SitokDocContract.company_id == user.company_id).order_by(SitokDocContract.id.desc()).all()
    return {"contracts": [summary(db, c) for c in rows]}


@router.get("/contracts/blank")
def blank(sector: str = "민간", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = SitokDocContract(id=0, company_id=user.company_id, sector=sector if sector in SECTORS else "민간", rounds=[], open_ended=False,
                         guarantee="-", delay_rate="-")
    return summary(db, c) | {"files": {}}


@router.post("/contracts")
def create(body: ContractIn | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = SitokDocContract(company_id=user.company_id, created_by=user.display_name or "", rounds=[], guarantee="-", delay_rate="-")
    _apply(c, body or ContractIn(), user)
    db.add(c)
    db.commit()
    return summary(db, c)


@router.get("/contracts/{cid}")
def get_contract(cid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return summary(db, _require(db, user, cid))


@router.put("/contracts/{cid}")
def put_contract(cid: int, body: ContractIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _require(db, user, cid)
    _apply(c, body, user)
    db.commit()
    return summary(db, c)


@router.delete("/contracts/{cid}")
def delete_contract(cid: int, password: str = Body("", embed=True), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """지우기(올린·만든 파일까지, 되돌릴 수 없음) — 회사 공용 삭제 비밀번호. 보고서 쪽에 넣은 계약은 그대로."""
    h = config.get_site_delete_password_hash(user.company_id)
    if not h:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "삭제 비밀번호가 아직 없습니다. 설정에서 먼저 정하세요.")
    if not verify_password(password, h):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "삭제 비밀번호가 맞지 않습니다.")
    c = _require(db, user, cid)
    base = folder(c)
    db.delete(c)
    db.commit()
    shutil.rmtree(base, ignore_errors=True)
    return {"ok": True}


# ---------- 올리기·AI 읽기 ----------

def _fill(c: SitokDocContract, got: dict, override: bool) -> list[str]:
    """읽은 값 넣기 — override면 전부, 아니면 빈 칸만. 넣은 칸 이름들."""
    filled = []
    for k, v in got.items():
        if v in (None, "", [], {}):
            continue
        cur = getattr(c, k)
        if override or cur in (None, "", "-", [], {}) or (k == "open_ended" and not cur):
            setattr(c, k, v)
            filled.append(k)
    return filled


def _pdf(file: UploadFile) -> bytes:
    """올린 파일 → PDF(한글·사진·오피스도) — 못 바꾸면 400."""
    from server.contract_docs.attachments import to_pdf_bytes

    try:
        return to_pdf_bytes(file.file.read(), file.filename or "파일")
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err


@router.post("/contracts/from-existing")
def from_existing(file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """이미 만든(날인한) 민간 계약서로 새 계약 — 파일을 못 읽으면 아무것도 안 만듦. 같은 시설물·관리주체 계약이 있으면 알려 줌."""
    pdf = _pdf(file)
    c = SitokDocContract(company_id=user.company_id, created_by=user.display_name or "", sector="민간", rounds=[], guarantee="-", delay_rate="-")
    db.add(c)
    db.flush()
    out = _store(db, c, "existing", pdf, user)
    key = (c.facility_name or c.client or "").replace(" ", "")
    dup = next((o for o in db.query(SitokDocContract).filter(SitokDocContract.company_id == user.company_id, SitokDocContract.id != c.id)
                if key and key in {(o.facility_name or "").replace(" ", ""), (o.client or "").replace(" ", "")}), None)
    return out | {"duplicate_of": {"id": dup.id, "title": dup.title or civil.default_title(dup)} if dup else None}


@router.post("/contracts/{cid}/upload/{kind}")
def upload(cid: int, kind: str, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _require(db, user, cid)
    if kind not in ("ledger", "bizreg", "existing", "signed"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "올릴 서류 종류가 맞지 않습니다.")
    return _store(db, c, kind, _pdf(file), user)


def _store(db: Session, c: SitokDocContract, kind: str, pdf: bytes, user: User) -> dict:
    """PDF로 바꾼 서류를 계약 폴더에 두고 읽어서 칸 채우기(관리대장·사업자등록증은 빈 칸만, 기존 계약서는 전부)."""
    from server.sitok import reader

    base = folder(c)
    base.mkdir(parents=True, exist_ok=True)
    target = {"ledger": "시설물관리대장.pdf", "bizreg": "사업자등록증.pdf", "existing": "날인본.pdf", "signed": "날인본.pdf"}[kind]
    (base / target).write_bytes(pdf)
    if target == "날인본.pdf":
        c.contract_pdf = str(base / target)
    filled, error = [], ""
    try:
        if kind == "ledger":
            d = reader.read_ledger(base / target, user.company_id)
            got = {"facility_name": d.get("name"), "location": d.get("address"), "client": d.get("owner_name"),
                   "client_rep": d.get("owner_rep"), "spec": f"연면적 {d['total_area']:,.2f}m²" if d.get("total_area") else ""}
            filled = _fill(c, got, False)
        elif kind == "bizreg":
            filled = _fill(c, civil.read_bizreg(pdf, "사업자등록증.pdf", user.company_id), False)
        elif kind == "existing":
            got = civil.read_existing(pdf, "계약서.pdf", user.company_id)
            c.sector = "민간"
            filled = _fill(c, got, True)
            c.amount = None if c.open_ended else (civil.total(c.rounds) or None)
    except Exception as err:  # noqa: BLE001 — 파일은 붙이고 손으로 채우게
        error = f"자동으로 읽지 못했습니다 — 직접 넣어 주세요. ({str(err).splitlines()[0][:150]})"
    c.updated_at, c.updated_by = datetime.datetime.now(), user.display_name or ""
    folder(c)  # 이름이 바뀌었으면 폴더도
    if c.contract_pdf and not Path(c.contract_pdf).exists():
        c.contract_pdf = str(folder(c) / "날인본.pdf")
    db.commit()
    return summary(db, c) | {"filled": filled, "error": error}


# ---------- 민간 계약서 만들기 ----------

def _template() -> bytes:
    p = civil.template_path()
    if not p.exists():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "민간 계약서 양식이 없습니다 — 화면 아래 [양식]에서 올려 주세요.")
    return p.read_bytes()


@router.post("/contracts/{cid}/make")
def make(cid: int, body: ContractIn | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from server.contract_docs import hwp_queue

    c = _require(db, user, cid)
    if body is not None:
        _apply(c, body, user)
    if c.sector != "민간":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "관급은 나라장터 계약서를 받습니다 — 계약서 만들기는 민간만.")
    if not c.facility_name and not c.client:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "관리주체·시설물명을 넣어 주세요.")
    if not c.open_ended and not c.rounds:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "계약 회차(연도·반기·정기/정밀·금액)를 하나 이상 넣거나 [계약 해지 시까지]를 고르세요.")
    data = civil.build(_template(), civil.values(c))  # 문서번호·계약건명이 비면 자동 값(저장은 안 함 — 회차를 고치면 따라 바뀌게)
    base = folder(c)
    base.mkdir(parents=True, exist_ok=True)
    (base / "계약서.hwpx").write_bytes(data)
    warn = ""
    try:
        (base / "계약서.pdf").write_bytes(hwp_queue.convert_via_worker(data, ".hwpx", wait=180))
    except RuntimeError as err:
        (base / "계약서.pdf").unlink(missing_ok=True)
        warn = f"한글은 만들었지만 PDF로 바꾸지 못했습니다: {str(err)[:150]}"
    c.made_at = datetime.datetime.now()
    db.commit()
    return summary(db, c) | {"warning": warn}


@router.get("/contracts/{cid}/file/{name}")
def get_file(cid: int, name: str, inline: bool = True, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _require(db, user, cid)
    if name not in FILES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일이 없습니다.")
    p = Path(c.contract_pdf) if name == "날인본.pdf" and c.contract_pdf else folder(c) / name
    if not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일이 없습니다.")
    label = re.sub(r'[\\/:*?"<>|]', "_", f"{c.facility_name or c.client or '계약'}_{name}")
    return FileResponse(p, media_type=FILES[name], filename=label, content_disposition_type="inline" if inline and name.endswith(".pdf") else "attachment",
                        headers={"Cache-Control": "no-store"})


# ---------- 현장(시설물) 연결 ----------

@router.get("/contracts/{cid}/candidates")
def candidates(cid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from server.contract_docs.contract_status import similarity

    c = _require(db, user, cid)
    key = c.facility_name or c.client or c.title
    rows = db.query(SitokFacility).filter(SitokFacility.company_id == user.company_id).all()
    rows.sort(key=lambda f: -max(similarity(key, f.name), similarity(key, f.owner_name or "")))
    return {"facilities": [{"id": f.id, "name": f.name, "owner": f.owner_name, "address": f.address} for f in rows]}


class LinkIn(BaseModel):
    facility_id: int | None = None


@router.post("/contracts/{cid}/link")
def link(cid: int, body: LinkIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _require(db, user, cid)
    if body.facility_id is not None:
        f = db.get(SitokFacility, body.facility_id)
        if f is None or f.company_id != user.company_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "시설물을 찾을 수 없습니다.")
    c.facility_id = body.facility_id
    db.commit()
    return summary(db, c)


@router.post("/contracts/{cid}/to-facility")
def to_facility(cid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """연결한 시설물에 보고서 쪽 계약(SitokContract)으로 — 계약서 PDF는 날인본(없으면 만든 계약서 PDF). 이미 넣었으면 그 계약을 고침."""
    from server.api.routers.sitok import _facility_dir

    c = _require(db, user, cid)
    f = db.get(SitokFacility, c.facility_id) if c.facility_id else None
    if f is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "먼저 현장(시설물)을 연결하세요.")
    src = Path(c.contract_pdf) if c.contract_pdf and Path(c.contract_pdf).exists() else folder(c) / "계약서.pdf"
    if not src.exists():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "넣을 계약서가 없습니다 — 날인본을 올리거나 계약서를 만드세요.")
    rc = db.get(SitokContract, c.report_contract_id) if c.report_contract_id else None
    if rc is None or rc.facility_id != f.id:
        rc = SitokContract(company_id=user.company_id, facility_id=f.id, created_by=user.display_name or "")
        db.add(rc)
        db.flush()
    halves = {r["half"] for r in c.rounds or []}
    per_half = (c.unit or {}).get("amount") if c.open_ended else next((r["amount"] for r in c.rounds or [] if r.get("amount")), None)
    rc.sector, rc.title, rc.contract_no = c.sector, c.title or civil.default_title(c), c.contract_no
    rc.contract_date, rc.start_date, rc.end_date = c.contract_date, c.start_date, c.end_date
    rc.halves = "연간" if c.sector == "관급" or c.open_ended or len(halves) != 1 else next(iter(halves))
    rc.amount = c.amount if c.sector == "관급" else per_half  # 보고서 쪽 민간 금액 = 반기 한 번 금액(회차마다 다르면 회차 카드 "이 동 점검금액")
    rc.rep_name = re.sub(r"^대표자\s*", "", c.client_rep or "")
    dest = _facility_dir(f) / f"계약서_{rc.id}.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    rc.contract_pdf = str(dest)
    c.report_contract_id = rc.id
    db.commit()
    return summary(db, c) | {"report_contract": rc.id, "facility_name": f.name}


# ---------- 민간 계약서 양식 ----------

@router.get("/template")
def get_template(user: User = Depends(get_current_user)):
    p = civil.template_path()
    if not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "양식이 없습니다.")
    return FileResponse(p, media_type="application/octet-stream", filename=civil.TEMPLATE_NAME)


@router.post("/template")
def put_template(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    """고친 양식 올리기 — 한글(hwp면 hwpx로 바꿈). 꼭 있어야 할 자리표시({시설물명} 등)가 빠지면 안 받음, 지금 양식은 _지난양식/에 보관."""
    from server.contract_docs import hwp_queue

    data, name = file.file.read(), (file.filename or "").lower()
    if name.endswith(".hwp"):
        try:
            data = hwp_queue.convert_via_worker(data, ".hwp", to="hwpx", wait=180)
        except RuntimeError as err:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(err)) from err
    elif not name.endswith(".hwpx"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "한글 파일(.hwp·.hwpx)로 올려 주세요.")
    try:
        missing = civil.check(data)
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"한글 파일을 읽지 못했습니다: {err}") from err
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "양식에 꼭 있어야 할 자리가 없습니다: " + ", ".join("{" + m + "}" for m in missing))
    p = civil.template_path()
    if p.exists():
        old = p.parent / "_지난양식" / f"{p.stem}_{datetime.datetime.fromtimestamp(p.stat().st_mtime):%Y%m%d_%H%M%S}.hwpx"
        old.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, old)
    p.write_bytes(data)
    return {"ok": True, "updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
