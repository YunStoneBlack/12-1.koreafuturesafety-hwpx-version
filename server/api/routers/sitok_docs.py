"""서류 자동화 · 시특법 계약(2026-10-12 사용자, alembic 0040 sitok_doc_contract) — 산안법처럼 보고서 쪽과 따로, 현장(시설물) 연결.
화면 sitok-docs.html(js/sitok-docs.js). 민간 계약서 만들기는 server/sitok/civil.py, 관급 착수계·완료계는 2단계.

- `GET    /sitok/docs/contracts` — 목록. `GET .../blank?sector=` 새 계약 기본값(저장 안 함). `POST .../contracts` 만들기. `GET|PUT|DELETE .../{id}`.
- `POST   /sitok/docs/contracts/{id}/upload/{kind}` — kind: ledger(시설물관리대장 → 시설물명·위치·제원·관리주체) · bizreg(사업자등록증 → 관리주체·대표자·번호·주소)
  · existing(이미 만든·날인한 민간 계약서 → 계약 칸 전부 + 날인본으로 보관) · signed(날인본만 보관). 읽은 값은 빈 칸만(existing은 전부).
- `POST   /sitok/docs/contracts/{id}/make` — 민간 계약서 한글·PDF. `GET .../{id}/file/{name}` — 계약서.hwpx·계약서.pdf·날인본.pdf 등.
- `GET    /sitok/docs/contracts/{id}/candidates`, `POST .../{id}/link` {facility_id|null} — 현장(시설물) 연결.
- `POST   /sitok/docs/contracts/{id}/to-facility` — 연결한 시설물에 보고서 쪽 계약으로 넣기(날인본/만든 PDF를 계약서로, 다시 누르면 고침).
  10/14 형 2차 ②: 연결된 시설물이 없으면 올린 관리대장(없으면 계약 칸의 시설물명·위치·관리주체)으로 **시설물 카드를 만들고** 이번 반기 회차까지 만듦("계약서가 없는 경우" 등록 경로).
- `GET    /sitok/docs/template`, `POST /sitok/docs/template` — 민간 계약서 양식 받기·고친 양식 올리기(자리표시 검사).
- 관급(2단계, server/sitok/gov_docs.py): 올리기 g2b(나라장터 계약서 — 글자 규칙, 못 읽은 칸만 AI → 읽은 칸 덮어씀)·report_cover(결과보고서 표지),
  `GET .../{id}/gov` 착수계·완료계 창, `POST .../{id}/gov/{start|done}` 엑셀 + 합본 PDF(붙임 산출내역서·완수내역서), `GET .../{id}/gov/{kind}.{xlsx|pdf}`,
  `POST|GET|DELETE .../{id}/gov/{kind}/attach/{칸}[/{파일}]` 붙임 파일. 기술자 = 시특법 보고서 설정과 같은 명단(사용자 10/12).
"""
from __future__ import annotations

import datetime
import re
import secrets
import shutil
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core import config
from core.db import DATA_DIR
from core.models_web import SitokContract, SitokDocContract, SitokFacility, SitokGroup, SitokReport, TechPerson, User
from server.api import storage
from server.api.deps import get_current_user, get_db
from server.api.routers import contract_library as lib
from server.api.security import verify_password
from server.contract_docs import attachments, build
from server.sitok import civil, daega, gov_docs

router = APIRouter(prefix="/sitok/docs", tags=["sitok"])
ROOT = DATA_DIR / "_시특법_계약"
SECTORS = ("민간", "관급")
TEXT = ("sector", "doc_no", "client", "client_rep", "client_biz_no", "client_address", "facility_name", "location", "spec", "title", "contract_no",
        "guarantee", "delay_rate", "client_manager", "client_phone", "client_email", "site_manager", "site_phone", "site_email", "memo")
DATES = ("contract_date", "start_date", "end_date")
FILES = {"계약서.hwpx": "application/octet-stream", "계약서.pdf": "application/pdf", "날인본.pdf": "application/pdf",
         "시설물관리대장.pdf": "application/pdf", "사업자등록증.pdf": "application/pdf", "결과보고서_표지.pdf": "application/pdf",
         "대가내역서.pdf": "application/pdf", "대가내역서.xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}  # 대가내역서(10/15 — FMS e-보고서)
GOV = {"start": "착수계", "done": "완료계"}  # 관급 서류 — 계약 폴더 착수계.xlsx·착수계.pdf …
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# 관급 기술자 서류: 착수계 장 종류(build.PERSON_DOCS 이름) ← SubmitDoc 종류 — 교육수료증은 정밀안전진단(견본), 자격증·경력증명서는 산안법과 같은 그림
GOV_PERSON_DOCS = [("license", "license", "자격증"), ("edu", "sitok_edu", "정밀안전진단 교육 수료증"), ("career", "career", "경력증명서"),
                   ("sign", "sitok_sign", "서명·도장")]


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


def _require(db: Session, user: User, cid: int) -> SitokDocContract:
    c = db.get(SitokDocContract, cid)
    if c is None or c.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "계약을 찾을 수 없습니다.")
    return c


def _files(c: SitokDocContract) -> dict:
    base = folder(c)
    return {n: (base / n).exists() for n in FILES} | {"날인본.pdf": bool(c.contract_pdf and Path(c.contract_pdf).exists())}


def _group_names(db: Session, f) -> list[str]:
    if f is None or not f.group_id:
        return []
    return [x.name for x in db.query(SitokFacility).filter(SitokFacility.group_id == f.group_id).order_by(SitokFacility.group_order, SitokFacility.id)]


HALF_TAGS = ("상반기", "하반기", "상·하반기", "해당없음")  # 시설물 카드 안 계약의 반기 표시(10/15 민재형 문서번호 일치화)


def half_auto(c: SitokDocContract, f: SitokFacility | None) -> str:
    """반기 표시 자동 — 주기 없는 내진성능평가(시설물 뱃지 내진·계약건명 "내진") = 해당없음, 끝 없는 계약 = 상·하반기,
    민간 회차 줄의 반기들, 없으면 용역 기간(시작·끝이 같은 해 같은 반기면 그 반기, 아니면 상·하반기). 날짜도 없으면 빈칸."""
    if "내진" in (c.title or ""):  # 주기 없는 내진성능평가(뱃지는 10/15 밤 뺌 — 따로 관리)
        return "해당없음"
    if c.open_ended:
        return "상·하반기"
    # 관급은 용역 기간만(10/15 사용자 "용역기간을 읽어 선택" — 회차 줄은 민간만 씀, 관급 창에 남던 기본 회차 줄 때문에 다 하반기로 나왔음)
    halves = {r.get("half") for r in (c.rounds or []) if r.get("half") in ("상반기", "하반기")} if c.sector == "민간" else set()
    if not halves and c.start_date:
        end = c.end_date or c.start_date
        h = lambda d: "상반기" if d.month <= 6 else "하반기"  # noqa: E731
        halves = {h(c.start_date)} if (c.start_date.year, h(c.start_date)) == (end.year, h(end)) else {"상반기", "하반기"}
    return "상·하반기" if len(halves) > 1 else next(iter(halves), "")


def covered_ids(c: SitokDocContract) -> list[int]:
    """이 계약이 덮는 시설물 id(시설물 여럿 카드 — 0052). 예전 계약은 [facility_id]."""
    return [int(x) for x in (c.facility_ids or ([c.facility_id] if c.facility_id else []))]


def card_no(db: Session, c: SitokDocContract) -> str:
    """서류 번호(10/15 민재형) — 계약이 시설물 하나만 맡으면 그 시설물 번호(관급-9-1 — 발주처가 나눈 계약),
    여럿을 맡으면 카드 번호(관급-9 — 계약 하나에 보고서 9-1·9-2). 카드에 안 넣었으면 ""."""
    from server.api.routers.sitok import base_no

    fs = [x for x in (db.get(SitokFacility, i) for i in covered_ids(c)) if x is not None]
    if not fs:
        return ""
    return (fs[0].mgmt_no or "") if len(fs) == 1 else base_no(fs[0].mgmt_no)


def summary(db: Session, c: SitokDocContract) -> dict:
    f = db.get(SitokFacility, c.facility_id) if c.facility_id else None
    k = civil.kinds_of(c.rounds, c.unit, c.open_ended)
    auto = half_auto(c, f)
    return {"id": c.id, **{x: getattr(c, x) for x in TEXT}, **{x: _iso(getattr(c, x)) for x in DATES},
            "amount": c.amount, "rounds": c.rounds or [], "open_ended": c.open_ended, "unit": c.unit,
            "kind": k, "kind_word": civil.kind_word(k), "total": civil.total(c.rounds) if not c.open_ended else None,
            "auto_title": civil.default_title(c), "auto_doc_no": civil.default_doc_no(c.contract_date),
            "facility": {"id": f.id, "name": f.name, "mgmt_no": f.mgmt_no} if f else None, "report_contract_id": c.report_contract_id,
            "half_tag": c.half_tag or "", "half_auto": auto, "half": c.half_tag or auto,
            "facility_ids": covered_ids(c), "amounts": c.amounts or {}, "card_no": card_no(db, c),
            "targets": [{"id": t.id, "mgmt_no": t.mgmt_no, "name": t.name} for t in (db.get(SitokFacility, x) for x in covered_ids(c)) if t is not None],
            # 동별 금액(10/15): 회차 줄에 나오는 동 이름, 연결한 시설물이 묶음이면 묶음 동 이름(동별 금액을 처음 켤 때 기본값)
            "buildings": civil.buildings(c.rounds), "group_names": _group_names(db, f),
            "files": _files(c), "made_at": c.made_at.strftime("%Y-%m-%d %H:%M") if c.made_at else "",
            "gov": {k: _gov_made(c, k) for k in GOV},
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
    half_tag: str | None = None  # 시설물 카드 반기 표시 — "" = 자동(half_auto)
    facility_id: int | None = None  # 시설물 카드 안 [+ 계약]으로 만들 때 그 카드(10/15)
    facility_ids: list[int] | None = None  # 이 계약이 덮는 시설물(시설물 여럿 카드 — 보고서 따로, 0052)
    amounts: dict | None = None  # 시설물별 금액 {시설물 id: 원}


def _apply(c: SitokDocContract, body: ContractIn, user: User, db: Session | None = None) -> None:
    data = body.model_dump(exclude_unset=True)
    if "sector" in data and data["sector"] not in SECTORS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "계약 구분은 민간·관급 중 하나입니다.")
    if "half_tag" in data:
        if data["half_tag"] and data["half_tag"] not in HALF_TAGS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "반기 표시는 상반기·하반기·상·하반기·해당없음 중 하나입니다.")
        c.half_tag = data["half_tag"] or ""
    if data.get("facility_id") and db is not None:
        f = db.get(SitokFacility, data["facility_id"])
        if f is None or f.company_id != c.company_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "시설물을 찾을 수 없습니다.")
        c.facility_id = f.id
    if data.get("facility_ids") is not None and db is not None:
        ids = [int(x) for x in data["facility_ids"] if x]
        fs = [db.get(SitokFacility, x) for x in ids]
        if not ids or any(f is None or f.company_id != c.company_id for f in fs):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "이 계약의 시설물을 하나 이상 고르세요.")
        c.facility_ids, c.facility_id = ids, ids[0]
    if "amounts" in data and data["amounts"] is not None:
        c.amounts = {str(k): int(str(v).replace(",", "")) for k, v in data["amounts"].items() if str(v).replace(",", "").strip().isdigit()} or None
    for k in TEXT:
        if k in data and data[k] is not None:
            setattr(c, k, str(data[k]).strip())
    for k in DATES:
        if k in data:
            setattr(c, k, _date(data[k]))
    if "rounds" in data:
        c.rounds = civil.normalize_rounds(data["rounds"])
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
    _apply(c, body or ContractIn(), user, db)
    db.add(c)
    db.commit()
    if c.facility_id:  # 시설물 카드 안 [+ 계약] — 방문 달력에 반기마다 점검 날(10/15)
        from server.sitok.visit_plan import fill_quietly
        fill_quietly(db, user.company_id, user.display_name or "", [c.facility_id])
    return summary(db, c)


# ---------- 시설물 카드(10/15 민재형 문서번호 일치화 — 서류 자동화도 시설물 기준, 번호 민간-N·관급-N은 보고서 자동화와 같음) ----------

def card_out(f: SitokFacility, members: list[SitokFacility], viewed: str = "") -> dict:
    return {"id": f.id, "mgmt_no": f.mgmt_no, "name": f.name, "sector": f.sector or "민간", "badge_field": f.badge_field or "", "badge_kind": f.badge_kind or "",
            "contract_type": f.contract_type, "address": f.address, "owner_name": f.owner_name, "template": f.template,
            "contact_name": f.contact_name, "contact_phone": f.contact_phone or f.owner_phone,
            "group_id": f.group_id, "members": [{"id": m.id, "name": m.name} for m in members], "viewed_at": viewed,
            "created_at": f.created_at.isoformat(timespec="seconds") if f.created_at else ""}


@router.get("/facilities")
def list_cards(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """시설물 카드 — 시설물 하나(묶인 동은 대표 동 하나) + 계약은 /contracts의 facility(묶음 동 아무나)로 카드에 넣음(화면)."""
    from core.models_web import SitokView

    from server.api.routers.sitok import NO_RE, base_no

    rows = db.query(SitokFacility).filter(SitokFacility.company_id == user.company_id).order_by(SitokFacility.group_order, SitokFacility.id).all()
    seen = {k: v.isoformat(timespec="seconds") for k, v in db.query(SitokView.facility_id, SitokView.viewed_at).filter(SitokView.user_id == user.id)}
    groups: dict[int, list[SitokFacility]] = {}
    for f in rows:
        if f.group_id:
            groups.setdefault(f.group_id, []).append(f)
    units, done = [], set()  # 시설물(보고서 하나) = 시설물 하나 또는 묶인 동
    for f in rows:
        if f.group_id and f.group_id in done:
            continue
        members = groups.get(f.group_id, [f]) if f.group_id else [f]
        done.add(f.group_id)
        name = members[0].name
        if len(members) > 1:
            g = db.get(SitokGroup, f.group_id)
            name = (g.name if g else "") or name
        units.append((members, name))
    cards: dict[str, list] = {}
    for members, name in units:  # 같은 앞 번호(관급-6-1·6-2) = 카드 하나
        key = base_no(members[0].mgmt_no) or f"#{members[0].id}"
        cards.setdefault(key, []).append((members, name))
    sub = lambda u: int((NO_RE.match(u[0][0].mgmt_no or "") or [None] * 4)[3] or 0)  # noqa: E731
    out = []
    for key, us in cards.items():
        us.sort(key=sub)
        allm = [m for members, _ in us for m in members]
        lead, lead_name = us[0][0][0], us[0][1]
        card = card_out(lead, allm, max((seen.get(m.id, "") for m in allm), default=""))
        card["mgmt_no"] = key if len(us) > 1 and not key.startswith("#") else lead.mgmt_no
        card["units"] = [{"id": members[0].id, "mgmt_no": members[0].mgmt_no, "name": name, "members": [{"id": m.id, "name": m.name} for m in members]}
                         for members, name in us]
        if len(us[0][0]) > 1:
            card["group_name"] = lead_name
        out.append(card)
    return {"facilities": out}


class AddFacilityIn(BaseModel):
    name: str
    address: str | None = None
    owner_name: str | None = None  # 관리주체 — 시설물마다 다를 수 있음(남양주도시공사 계약 → 청소년수련관·어린이집, FMS 계정도 따로)
    ledger_token: str | None = None  # 창에 올린 시설물관리대장(/facilities/{id}/add/read) → 새 시설물 폴더로
    fields: dict | None = None  # 관리대장에서 읽은 시설물 칸(FMS 시설물번호·용도·준공일 …)
    ledger_extra: dict | None = None
    contract_ids: list[int] | None = None  # 같은 계약 — 이 시설물도 맡는 카드 안 계약(서류 관급-9 · 보고서 9-1·9-2). 비면 계약 따로(서류 9-1·9-2)


@router.post("/facilities/{fid}/add/read")
def add_read(fid: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """[+ 시설물 추가] 창의 시설물관리대장(PDF·한글·사진, 10/15 민재형 "관리대장은 추가해서") — 읽은 칸을 돌려주고 파일은 임시(추가할 때 새 시설물 폴더로)."""
    from server.api.routers.sitok import UPLOAD_DIR, _clean_uploads, _iso, guess_template
    from server.sitok import reader

    f = db.get(SitokFacility, fid)
    if f is None or f.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "시설물을 찾을 수 없습니다.")
    pdf = _pdf(file)
    _clean_uploads()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(12)
    path = UPLOAD_DIR / f"{token}.pdf"
    path.write_bytes(pdf)
    try:
        parsed = reader.read_ledger(path, user.company_id)
    except Exception as err:  # noqa: BLE001 — 못 읽어도 파일은 붙이고 손으로
        return {"token": token, "fields": {}, "error": f"자동으로 읽지 못했습니다 — 직접 입력해 주세요. ({str(err).splitlines()[0][:160] if str(err) else type(err).__name__})"}
    fields = {k: _iso(v) for k, v in parsed.items()}
    fields["template"] = guess_template(fields.get("grade", ""), fields.get("use_type", ""), fields.get("main_use", ""))
    return {"token": token, "fields": fields, "error": ""}


@router.post("/facilities/{fid}/add")
def add_facility(fid: int, body: AddFacilityIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """[+ 시설물 추가 — 보고서 따로](10/15 밤 민재형): 같은 카드에 보고서가 따로 나오는 시설물 — 관급-6 → 6-1, 새 것 6-2(다음 6-3).
    동 추가(묶음 — 한 보고서)와 다름. 새 시설물은 카드의 주소·관리주체·구분·뱃지·계약 구분을 물려받음(관리대장을 올렸으면 그 칸·관리주체).
    contract_ids = 같은 계약(그 계약이 이 시설물도 맡음 — 보고서 쪽 계약·이번 반기 회차까지), 비면 계약 따로(나중에 올리는 계약이 맡음)."""
    from server.api.routers.sitok import NO_RE, FacilityIn, _apply_facility, _facility_dir, _take, base_no, card_facilities

    f = db.get(SitokFacility, fid)
    if f is None or f.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "시설물을 찾을 수 없습니다.")
    if not body.name.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "시설물 이름을 넣어 주세요(예: 일동중학교 옹벽).")
    base = base_no(f.mgmt_no)
    if not NO_RE.match(base or ""):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "이 카드는 번호(관급-6 같은)가 없어 시설물을 나눌 수 없습니다 — 먼저 번호를 넣으세요.")
    card = card_facilities(db, f)
    subs = []
    for x in card:
        m = NO_RE.match(x.mgmt_no or "")
        if m and m[3] is None:
            x.mgmt_no = f"{base}-1"  # 첫 시설물 → 6-1(묶인 동 같이)
            subs.append(1)
        elif m:
            subs.append(int(m[3]))
    own = (body.owner_name or "").strip()
    same_owner = not own or own == f.owner_name
    new = SitokFacility(company_id=user.company_id, created_by=user.display_name or "", name=body.name.strip(), address=(body.address or f.address or "").strip(),
                        owner_name=own or f.owner_name, owner_type=f.owner_type if same_owner else "", owner_phone=f.owner_phone if same_owner else "",
                        sector=f.sector, badge_field=f.badge_field,
                        badge_kind=f.badge_kind, badge_manual=f.badge_manual, contract_type=f.contract_type, template=f.template, kind=f.kind,
                        contact_name=f.contact_name, contact_phone=f.contact_phone, legal=True if body.ledger_token else f.legal, ledger=body.ledger_extra or None)
    if body.fields:  # 관리대장에서 읽은 칸 — 이름·주소·관리주체는 창에서 고친 값, 구분·뱃지·번호·계약 구분은 카드 것
        keep = {"name", "address", "owner_name", "sector", "badge_field", "badge_kind", "contract_type", "mgmt_no", "legal"}
        for k, v in body.fields.items():
            if k in FacilityIn.model_fields and k not in keep and v not in (None, ""):
                try:
                    _apply_facility(new, FacilityIn(**{k: v}))
                except (ValueError, HTTPException):  # 못 읽은 모양의 칸은 건너뜀(시설물 화면에서)
                    pass
    new.mgmt_no = f"{base}-{max(subs, default=1) + 1}"
    db.add(new)
    db.flush()
    if body.ledger_token:
        new.ledger_pdf = _take(body.ledger_token, _facility_dir(new) / "시설물관리대장.pdf") or new.ledger_pdf
    ids_in_card = {x.id for x in card}
    joined = []
    for cid in dict.fromkeys(body.contract_ids or []):
        c = db.get(SitokDocContract, cid)
        if c is None or c.company_id != user.company_id or not (set(covered_ids(c)) & ids_in_card):
            continue
        ids = covered_ids(c)
        c.facility_ids = ids + [new.id]
        c.facility_id = ids[0]
        joined.append(c)
    db.commit()
    report_id = None
    for c in joined:  # 이미 보고서 쪽에 넣은 계약이면 새 시설물 것도(금액은 계약 창에서 시설물별로 나눔)
        if c.report_contract_id or c.report_contracts:
            try:
                report_id = to_facility(c.id, user, db).get("report_id") or report_id
            except HTTPException:
                db.rollback()
    return {"ok": True, "id": new.id, "mgmt_no": new.mgmt_no, "joined": [c.id for c in joined], "report_id": report_id}


class CardIn(BaseModel):
    sector: str = "민간"
    name: str = ""
    address: str = ""
    owner_name: str = ""
    badge_field: str = "건축"
    badge_kind: str = ""
    contract_type: str | None = None
    mgmt_no: str | None = None


@router.post("/facilities")
def create_card(body: CardIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """새 시설물 카드 — 보고서 자동화 시설물 목록에도 같은 번호로 바로 생김(같은 시설물 표). 관리대장·계약은 나중에."""
    from server.api.routers.sitok import FacilityIn, _apply_facility, default_badges, default_type, next_mgmt_no

    if not body.name.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "시설물명을 넣어 주세요.")
    if body.sector not in SECTORS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "민간·관급 중 하나를 고르세요.")
    f = SitokFacility(company_id=user.company_id, created_by=user.display_name or "")
    _apply_facility(f, FacilityIn(name=body.name, address=body.address, owner_name=body.owner_name, sector=body.sector,
                                  badge_field=body.badge_field or "건축", badge_kind=body.badge_kind if body.sector == "관급" else "",
                                  contract_type=body.contract_type or default_type(body.sector)))
    f.mgmt_no = (body.mgmt_no or "").strip() or next_mgmt_no(db, user.company_id, body.sector)
    default_badges(f)
    from server.api.routers.sitok import guess_badges
    g_field, g_kind = guess_badges([body.name, body.owner_name])
    f.badge_manual = f.badge_field != g_field or (f.sector == "관급" and f.badge_kind != g_kind)  # 이름으로 짐작한 것과 다르게 골랐으면 사람이 고른 것
    db.add(f)
    db.commit()
    return card_out(f, [f])


class NumberIn(BaseModel):
    n: int
    merge: bool = False  # 다른 카드가 쓰는 번호면 그 카드에 시설물로 넣기(같은 발주처가 나눈 계약 — 관급-9-1·9-2, 10/15 민재형)


@router.post("/facilities/{fid}/number")
def set_number(fid: int, body: NumberIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """카드 번호 바꾸기(10/15 민재형 "번호를 임의로 바꿀 수 있게") — 앞 글자는 구분(관급·민간), 숫자만. 겹치면 409, 묶인 동 같이. 다음 자동 번호는 가장 큰 번호 + 1."""
    f = db.get(SitokFacility, fid)
    if f is None or f.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "시설물을 찾을 수 없습니다.")
    if body.n < 1 or body.n > 99999:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "번호는 1 이상 숫자로 넣어 주세요.")
    from server.api.routers.sitok import NO_RE, base_no, card_facilities

    no = f"{f.sector or '민간'}-{body.n}"
    card = card_facilities(db, f)
    ids = {x.id for x in card}
    other = [x for x in db.query(SitokFacility).filter(SitokFacility.company_id == f.company_id) if x.id not in ids and base_no(x.mgmt_no) == no]
    if other and not body.merge:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{no}은(는) {other[0].name}이(가) 쓰고 있습니다.")
    if other:  # 합치기 — 그 카드가 번호 하나면 9 → 9-1, 이 카드 시설물은 9-2·9-3 …(묶인 동 같이, 원래 순서대로). 계약·보고서는 그대로 따라감
        sub = lambda x: int((NO_RE.match(x.mgmt_no or "") or [None] * 4)[3] or 0)  # noqa: E731
        subs = []
        for x in other:
            if sub(x) == 0:
                x.mgmt_no = f"{no}-1"
                subs.append(1)
            else:
                subs.append(sub(x))
        nxt = max(subs, default=1) + 1
        renum = {}
        for x in sorted(card, key=lambda x: (sub(x), x.group_order or 0, x.id)):
            if x.mgmt_no not in renum:
                renum[x.mgmt_no] = f"{no}-{nxt}"
                nxt += 1
        for x in card:
            x.mgmt_no = renum[x.mgmt_no]
        db.commit()
        return {"ok": True, "mgmt_no": no, "merged": sorted(set(renum.values()))}
    for x in card:  # 시설물 여럿 카드면 뒤 번호(-1·-2)는 그대로
        m = NO_RE.match(x.mgmt_no or "")
        x.mgmt_no = f"{no}-{int(m[3])}" if m and m[3] else no
    db.commit()
    return {"ok": True, "mgmt_no": no}


@router.get("/contracts/{cid}")
def get_contract(cid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return summary(db, _require(db, user, cid))


@router.put("/contracts/{cid}")
def put_contract(cid: int, body: ContractIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _require(db, user, cid)
    _apply(c, body, user, db)
    db.commit()
    return auto_card(db, user, c) or summary(db, c)


# ---------- 저장하면 시설물 카드에(10/15 민재형 "계약서 넣고 버튼을 눌러야 카드가 생기는데 — 저장 누르면 생기게") ----------

def _norm(s: str | None) -> str:
    return re.sub(r"[\s()（）·,._\-]", "", s or "")


SCHOOL_RE = re.compile(r"([가-힣A-Za-z0-9]+(?:초등학교|중학교|고등학교|유치원|학교))")


def school_names(*texts: str | None) -> set[str]:
    """학교 이름("초성초등학교") — 띄어쓰기로 나뉜 말에서, 앞에 붙은 "…교육청"은 뗌."""
    out = set()
    for x in texts:
        for m in SCHOOL_RE.findall(x or ""):
            m = re.sub(r"^.*(교육지원청|교육청)", "", m)
            if len(m) > 2:
                out.add(m)
    return out


def _card_units(db: Session, f: SitokFacility) -> list[SitokFacility]:
    """카드의 시설물(보고서 하나씩 — 관급-9-1·9-2), 묶인 동은 대표 동 하나(목록·계약 체크칸과 같은 id)."""
    from server.api.routers.sitok import NO_RE, card_facilities

    seen, out = set(), []
    for x in sorted(card_facilities(db, f), key=lambda x: (x.group_order or 0, x.id)):
        if x.group_id:
            if x.group_id in seen:
                continue
            seen.add(x.group_id)
        out.append(x)
    return sorted(out, key=lambda x: int((NO_RE.match(x.mgmt_no or "") or [None] * 4)[3] or 0))


def _overlaps(a: SitokDocContract, b: SitokDocContract) -> bool:
    if not a.start_date or not b.start_date:
        return False
    return a.start_date <= (b.end_date or b.start_date) and b.start_date <= (a.end_date or a.start_date)


def _pattern(t: str | None) -> str:
    """계약건명 모양 — 연도·반기·숫자·띄어쓰기를 뺌("2026년 남양주어린이집 정기안전점검" → "남양주어린이집정기안전점검")."""
    return re.sub(r"상·하반기|상반기|하반기|\d+|년|[\s()（）·,._\-\[\]]", "", t or "")


def _pick_units(db: Session, c: SitokDocContract, lead: SitokFacility) -> list[SitokFacility]:
    """관급 계약이 맡을 카드 시설물(10/15 민재형 — 계약 하나에 보고서 9-1·9-2 / 발주처가 계약을 나눔 서류 9-1↔보고서 9-1·9-2↔9-2).
    이 계약 기간에 다른 계약이 이미 맡은 시설물은 빼고(내진성능평가 계약은 따로) → 계약건명에 이름이 있는 시설물 →
    전에 같은 건명 모양 계약이 맡던 시설물 → 남은 시설물 전부. 다 맡겨져 있으면 [](같은 발주처가 나눈 새 계약 — 새 카드)."""
    units = _card_units(db, lead)
    if "내진" in (c.title or ""):
        return units
    ids = {u.id for u in units}
    taken, prev = set(), None
    for o in db.query(SitokDocContract).filter(SitokDocContract.company_id == c.company_id, SitokDocContract.id != c.id):
        cov = set(covered_ids(o)) & ids
        if not cov or "내진" in (o.title or ""):
            continue
        if _overlaps(c, o):
            taken |= cov
        elif o.start_date and c.start_date and o.start_date < c.start_date and _pattern(o.title) and _pattern(o.title) == _pattern(c.title) \
                and (prev is None or o.start_date > prev[0]):
            prev = (o.start_date, cov)
    free = [u for u in units if u.id not in taken]
    if len(free) <= 1 or len(units) == 1:
        return free
    title = _norm(c.title)
    named = [u for u in free if len(_norm(u.name)) >= 4 and _norm(u.name) in title]
    if named:
        return named
    if prev and [u for u in free if u.id in prev[1]]:
        return [u for u in free if u.id in prev[1]]
    return free


def match_card(db: Session, c: SitokDocContract, why: dict | None = None) -> list[SitokFacility] | None | bool:
    """같은 시설물 카드 — 시설물명·발주처가 카드 이름·관리주체와 (띄어쓰기 빼고) 같거나, 학교 이름("초성초등학교")이 같거나,
    계약건명에 시설물 이름이 그대로 있으면(관급 — "2026년 남양주어린이집 정기안전점검", 10/15 밤).
    없으면 None, 둘 이상이면 False(못 정함 — 사람이 고름), 계약서에 학교가 둘 이상 적혀 있어도 False.
    관급은 카드 안에서 맡을 시설물을 고름(_pick_units) — 이 기간 계약이 다 있으면 None + why["full"] = 그 카드 번호(새 카드, 번호를 같게 바꾸면 합침)."""
    keys = {_norm(x) for x in (c.facility_name, c.client) if _norm(x)}
    schools = school_names(c.facility_name, c.client)
    if len(schools) > 1:
        return False
    title = _norm(c.title) if c.sector == "관급" else ""
    hits = {}
    for f in db.query(SitokFacility).filter(SitokFacility.company_id == c.company_id, SitokFacility.sector == c.sector):
        names = {_norm(f.name), _norm(f.owner_name)} - {""}
        fs = school_names(f.name, f.owner_name)
        if keys & names or (schools and schools & fs) or (title and len(_norm(f.name)) >= 4 and _norm(f.name) in title):
            lead = f
            if f.group_id:
                lead = db.query(SitokFacility).filter(SitokFacility.group_id == f.group_id).order_by(SitokFacility.group_order, SitokFacility.id).first() or f
            hits[lead.id] = lead
    if not hits:
        return None
    from server.api.routers.sitok import base_no
    bases = {base_no(h.mgmt_no) for h in hits.values()}
    if len(hits) > 1 and not (len(bases) == 1 and next(iter(bases))):  # 다른 카드 여럿 — 못 정함
        return False
    lead = next(iter(hits.values()))
    if c.sector == "관급":
        units = _pick_units(db, c, lead)
        if not units and why is not None:
            why["full"] = base_no(lead.mgmt_no) or lead.mgmt_no
        return units or None
    if len(hits) > 1:  # 민간 — 같은 카드(관급-6-1·6-2 — 앞 번호 같음)면 맞은 시설물 전부(계약 창에서 체크로 줄임)
        return sorted(hits.values(), key=lambda h: h.mgmt_no or "")
    return [lead]


def auto_card(db: Session, user: User, c: SitokDocContract) -> dict | None:
    """계약서 PDF가 있으면 저장할 때 카드에 넣고 보고서 쪽 계약까지(to_facility) — 카드가 없으면 같은 시설물 카드를 찾아 넣고, 없으면 새 카드.
    같은 계약번호 계약이 이미 있으면(중복) 안 함. 넣을 수 없으면 None(그냥 저장)."""
    has_pdf = (c.contract_pdf and Path(c.contract_pdf).exists()) or (folder(c) / "계약서.pdf").exists()
    if not has_pdf or duplicate_of(db, c) is not None or not (c.facility_name or c.client or c.title):
        return None
    joined, why = None, {}
    if c.facility_id is None:
        f = match_card(db, c, why)
        if f is False:  # 같은 시설물로 보이는 카드가 여럿·학교가 둘 — 새 카드를 만들지 않고 사람이 [카드 고르기]
            return None
        if f is not None:  # [시설물들] — 시설물 여럿 카드면 전부(보고서 따로)
            c.facility_id = f[0].id
            c.facility_ids = [x.id for x in f] if len(f) > 1 else None
            joined = f[0]
            db.flush()
    elif c.report_contract_id:
        rcmap = {str(k): v for k, v in (c.report_contracts or {str(c.facility_id): c.report_contract_id}).items()}
        ids, multi = covered_ids(c), len(covered_ids(c)) > 1
        same = set(rcmap) <= {str(x) for x in ids}  # 체크를 뺀 시설물이 있으면 다시 넣음(그 시설물 보고서 쪽 계약 지움 — to_facility)
        for fid in ids:
            rc = db.get(SitokContract, rcmap.get(str(fid))) if rcmap.get(str(fid)) else None
            want_amount = (c.amounts or {}).get(str(fid)) if multi else (c.amount if c.sector == "관급" else None)
            if rc is None or rc.facility_id != fid or (rc.start_date, rc.end_date, rc.contract_no) != (c.start_date, c.end_date, c.contract_no) \
                    or (want_amount is not None and rc.amount != want_amount):
                same = False
                break
        if same:
            return None  # 이미 넣었고 바뀐 것 없음
    try:
        out = to_facility(c.id, user, db)
    except HTTPException:
        db.rollback()
        return None
    from server.api.routers.sitok import auto_badges

    f = db.get(SitokFacility, c.facility_id)
    if f is not None:
        auto_badges(db, f)
        db.commit()
    no = f.mgmt_no if f is not None else ""
    msg = (f"✓ 새 시설물 카드 {no} {out['facility_name']}를 만들어 넣었습니다(보고서 자동화에도 생김)" if out.get("created_facility")
           else f"✓ 같은 시설물 카드 {card_no(db, c)} {out['facility_name']}에 넣었습니다" if joined is not None
           else f"✓ {card_no(db, c)} {out['facility_name']} 카드의 보고서 쪽 계약으로 넣었습니다")
    if out.get("created_facility") and why.get("full"):  # 같은 발주처 카드가 이 기간 계약이 이미 있음 — 나눈 계약이면 번호로 합치기
        n = why["full"].split("-", 1)[-1]
        msg += f" — 같은 발주처 카드 {why['full']}는 이 기간 계약이 이미 있어 새 카드로 했습니다. 발주처가 계약을 나눈 거면 번호표를 눌러 {n}(으)로 바꾸면 {why['full']} 카드의 시설물(보고서 따로)로 들어갑니다"
    elif joined is not None and f is not None and len(_card_units(db, f)) > 1:
        msg += f" — 이 계약의 시설물 {' · '.join(x.mgmt_no for x in (db.get(SitokFacility, i) for i in covered_ids(c)) if x)}(다르면 계약 정보의 \"이 계약의 시설물\"에서 고르세요)"
    return summary(db, c) | {"auto_card": msg, "report_id": out.get("report_id")}


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
    if kind not in ("ledger", "bizreg", "existing", "signed", "g2b", "report_cover"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "올릴 서류 종류가 맞지 않습니다.")
    return _store(db, c, kind, _pdf(file), user)


def _store(db: Session, c: SitokDocContract, kind: str, pdf: bytes, user: User) -> dict:
    """PDF로 바꾼 서류를 계약 폴더에 두고 읽어서 칸 채우기(관리대장·사업자등록증은 빈 칸만, 기존 계약서는 전부)."""
    from server.sitok import reader

    base = folder(c)
    base.mkdir(parents=True, exist_ok=True)
    target = {"ledger": "시설물관리대장.pdf", "bizreg": "사업자등록증.pdf", "existing": "날인본.pdf", "signed": "날인본.pdf", "g2b": "날인본.pdf",
              "report_cover": "결과보고서_표지.pdf"}[kind]
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
        elif kind == "g2b":
            c.sector = "관급"
            got, error = _read_g2b(base / target, user.company_id)
            filled = _fill(c, got, True)
    except Exception as err:  # noqa: BLE001 — 파일은 붙이고 손으로 채우게
        error = f"자동으로 읽지 못했습니다 — 직접 넣어 주세요. ({str(err).splitlines()[0][:150]})"
    c.updated_at, c.updated_by = datetime.datetime.now(), user.display_name or ""
    folder(c)  # 이름이 바뀌었으면 폴더도
    if c.contract_pdf and not Path(c.contract_pdf).exists():
        c.contract_pdf = str(folder(c) / "날인본.pdf")
    full = False
    lead = db.get(SitokFacility, c.facility_id) if c.facility_id else None
    if kind in ("g2b", "existing") and lead is not None and not c.report_contracts and not c.report_contract_id and len(_card_units(db, lead)) > 1:
        # 시설물 여럿 카드 안 [+ 계약](10/15 밤) — 기간을 읽었으니 맡을 시설물을 고름: 이 기간 다른 계약이 맡은 시설물은 빼고(나눈 계약이면 9-2만)
        picked = _pick_units(db, c, lead) if c.sector == "관급" else []
        if picked:
            c.facility_id, c.facility_ids = picked[0].id, ([u.id for u in picked] if len(picked) > 1 else None)
        elif c.sector == "관급":
            full = True
            error = (error + " ") if error else ""
            error += "이 기간 계약이 카드의 시설물마다 이미 있습니다 — 다른 시설물 계약이면 카드의 [+ 시설물 추가]로 시설물을 먼저 만들고 \"이 계약의 시설물\"에서 고르세요."
    db.commit()
    dup = duplicate_of(db, c)
    auto = auto_card(db, user, c) if kind in ("g2b", "existing", "signed") and not full else None  # 계약서를 올리면 바로 카드에(10/15 — 저장 = 카드)
    if auto is None and c.facility_id and kind in ("g2b", "existing"):  # 카드 안 계약 — 기간이 생기면 방문 달력 일정(10/15)
        from server.sitok.visit_plan import fill_quietly
        fill_quietly(db, user.company_id, user.display_name or "", [c.facility_id])
    return (auto or summary(db, c)) | {"filled": filled, "error": error, "duplicate_of": dup}


def duplicate_of(db: Session, c: SitokDocContract) -> dict | None:
    """같은 계약번호(나라장터)의 다른 계약 — 창을 닫고 다시 올려 계약이 둘 생기는 것 막기(10/15 민재형 "연동이 안 됨"). 카드에 든 것을 먼저."""
    no = (c.contract_no or "").strip()
    if not no:
        return None
    rows = db.query(SitokDocContract).filter(SitokDocContract.company_id == c.company_id, SitokDocContract.id != c.id,
                                             SitokDocContract.contract_no == no).order_by(SitokDocContract.facility_id.is_(None), SitokDocContract.id).all()
    if not rows:
        return None
    d = rows[0]
    f = db.get(SitokFacility, d.facility_id) if d.facility_id else None
    return {"id": d.id, "title": d.title or d.client, "facility": {"id": f.id, "mgmt_no": f.mgmt_no, "name": f.name} if f else None}


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


@router.post("/contracts/{cid}/daega")
def make_daega(cid: int, body: ContractIn | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """대가내역서 엑셀·PDF(server/sitok/daega.py — 형 양식, 계약 회차 줄·동별 금액으로). FMS e-보고서 "계약서 및 대가내역서"에도 씀."""
    c = _require(db, user, cid)
    if body is not None:
        _apply(c, body, user)
        db.commit()
    if not c.open_ended and not c.rounds and not c.amount:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "계약 회차(연도·반기·정기/정밀·금액)나 계약금액을 먼저 넣어 주세요.")
    base = folder(c)
    try:
        daega.build_pdf(c, base / "대가내역서.xlsx", base / "대가내역서.pdf")
    except (RuntimeError, ValueError) as err:  # LibreOffice 없음·변환 실패 — 엑셀은 남음
        return summary(db, c) | {"warning": f"엑셀은 만들었지만 PDF로 바꾸지 못했습니다: {str(err)[:150]}"}
    return summary(db, c) | {"warning": ""}


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
    """연결한 시설물에 보고서 쪽 계약(SitokContract)으로 — 계약서 PDF는 날인본(없으면 만든 계약서 PDF). 이미 넣었으면 그 계약을 고침.
    연결된 시설물이 없으면(10/14 "계약서가 없는 경우" 등록) 관리대장으로 시설물 카드를 만들어 연결하고, 이번 반기 회차까지 만든다."""
    from server.api.routers.sitok import _facility_dir

    c = _require(db, user, cid)
    src = Path(c.contract_pdf) if c.contract_pdf and Path(c.contract_pdf).exists() else folder(c) / "계약서.pdf"
    if not src.exists():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "넣을 계약서가 없습니다 — 날인본을 올리거나 계약서를 만드세요.")
    f = db.get(SitokFacility, c.facility_id) if c.facility_id else None
    created = None
    if f is None:
        f = _new_facility_from(db, user, c)
        c.facility_id = f.id
        c.facility_ids = None
        created = f.id
    targets = [t for t in (db.get(SitokFacility, x) for x in covered_ids(c)) if t is not None] or [f]  # 계약 하나에 시설물 여럿(0052) — 시설물마다 보고서 쪽 계약
    rcmap = {str(k): v for k, v in (c.report_contracts or {}).items()}
    if c.report_contract_id and not rcmap:
        rcmap[str(c.facility_id)] = c.report_contract_id
    halves = {r["half"] for r in c.rounds or []}
    per_half = (c.unit or {}).get("amount") if c.open_ended else next((r["amount"] for r in c.rounds or [] if r.get("amount")), None)
    multi = len(targets) > 1
    amounts = {str(k): v for k, v in (c.amounts or {}).items()}
    from server.api.routers.sitok import attach_contract

    report_id = None
    for t in targets:
        rc = db.get(SitokContract, rcmap[str(t.id)]) if rcmap.get(str(t.id)) else None
        if rc is None or rc.facility_id != t.id:
            rc = SitokContract(company_id=user.company_id, facility_id=t.id, created_by=user.display_name or "")
            db.add(rc)
            db.flush()
        rc.sector, rc.title, rc.contract_no = c.sector, c.title or civil.default_title(c), c.contract_no
        rc.contract_date, rc.start_date, rc.end_date = c.contract_date, c.start_date, c.end_date
        rc.halves = "연간" if c.sector == "관급" or c.open_ended or len(halves) != 1 else next(iter(halves))
        base_amount = c.amount if c.sector == "관급" else per_half  # 보고서 쪽 민간 금액 = 반기 한 번 금액(회차마다 다르면 회차 카드 "이 동 점검금액")
        rc.amount = amounts.get(str(t.id)) if multi and amounts.get(str(t.id)) else (None if multi else base_amount)  # 여럿이면 시설물별 금액(없으면 비움)
        rc.rep_name = re.sub(r"^대표자\s*", "", c.client_rep or "")
        rc.rounds = ((c.rounds or []) + ([{"open_ended": True, **c.unit}] if c.open_ended and c.unit else [])) if c.sector == "민간" else None  # 회차 종류(정기/정밀) 자동 선택에 씀(0043) — 관급은 기간·계약건명으로
        dest = _facility_dir(t) / f"계약서_{rc.id}.pdf"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        rc.contract_pdf = str(dest)
        rcmap[str(t.id)] = rc.id
        db.flush()
        attach_contract(db, rc)  # 계약 없이 만든 회차 중 이 계약이 덮는 것에 붙임(10/13)
        if (created is not None and t.id == created) or (not t.group_id and db.query(SitokReport.id).filter(SitokReport.facility_id == t.id).first() is None):
            # 새 시설물(또는 회차가 하나도 없는 시설물 — [+ 시설물 추가]로 만든 관급-9-2 등)이면 이번 반기(계약이 덮으면) 회차까지
            report_id = _first_report(db, user, t, rc) or report_id
    keep = {str(t.id) for t in targets}
    for k in [k for k in rcmap if k not in keep]:  # 계약 창에서 체크를 뺀 시설물 — 그 시설물에 넣었던 보고서 쪽 계약을 지움(회차는 남고 계약 칸만 비움)
        old = db.get(SitokContract, rcmap.pop(k))
        if old is not None and str(old.facility_id) == k:
            db.query(SitokReport).filter(SitokReport.contract_id == old.id).update({SitokReport.contract_id: None})
            db.delete(old)
    c.report_contracts = rcmap
    c.report_contract_id = rcmap.get(str(c.facility_id)) or next(iter(rcmap.values()), None)
    db.commit()
    from server.sitok.visit_plan import fill_quietly
    fill_quietly(db, user.company_id, user.display_name or "", [t.id for t in targets])  # 방문 달력 반기마다 점검 날(10/15)
    return summary(db, c) | {"report_contract": c.report_contract_id, "facility_name": " · ".join(t.name for t in targets) if multi else f.name,
                             "created_facility": created, "report_id": report_id}


def _new_facility_from(db: Session, user: User, c: SitokDocContract) -> SitokFacility:
    """서류 자동화 계약 → 시설물 카드: 올린 관리대장(AI로 다시 읽어 칸 전부)이 있으면 그것, 없으면 계약 칸의 시설물명·위치·관리주체만. 번호표·계약 구분은 새 등록과 같음."""
    from server.api.routers.sitok import FacilityIn, _apply_facility, _facility_dir, default_badges, default_type, next_mgmt_no
    from server.sitok import reader

    ledger = folder(c) / "시설물관리대장.pdf"
    fields: dict = {"name": (c.facility_name or c.client or c.title or "").strip(), "address": c.location or "", "owner_name": c.client or ""}
    extra = None
    if ledger.exists():
        try:
            d = reader.read_ledger(ledger, user.company_id)
            extra = d.pop("ledger", None)
            d.pop("owner_rep", None)
            grade = d.pop("grade", "")
            fields.update({k: v for k, v in d.items() if v not in (None, "") and k in FacilityIn.model_fields})
            if grade and "template" in FacilityIn.model_fields and not fields.get("template"):
                fields["template"] = "3종일반" if grade == "3" else "2종"
        except Exception:  # noqa: BLE001 — 못 읽으면 계약 칸 값으로
            pass
    if not fields["name"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "시설물명이 없습니다 — 관리대장을 올리거나 시설물 칸을 적어 주세요.")
    f = SitokFacility(company_id=user.company_id, created_by=user.display_name or "", ledger=extra or None)
    _apply_facility(f, FacilityIn(**fields))
    db.add(f)
    db.flush()
    if ledger.exists():
        dest = _facility_dir(f) / "시설물관리대장.pdf"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ledger, dest)
        f.ledger_pdf = str(dest)
    bizreg = folder(c) / "사업자등록증.pdf"
    if bizreg.exists():
        dest = _facility_dir(f) / "사업자등록증.pdf"
        shutil.copyfile(bizreg, dest)
    f.sector = c.sector or "민간"
    f.mgmt_no = next_mgmt_no(db, user.company_id, f.sector)
    default_badges(f)
    from server.api.routers.sitok import guess_badges
    f.badge_field, kind = guess_badges([c.client, c.facility_name, c.title, c.spec, f.name, f.use_type, f.main_use])
    f.badge_kind = kind if f.sector == "관급" else ""
    f.contract_type = default_type(c.sector)
    return f


def _first_report(db: Session, user: User, f: SitokFacility, rc: SitokContract) -> int | None:
    """새 시설물의 첫 회차 — 오늘 반기를 이 계약이 덮으면 그 회차(종류는 계약 회차 줄에서, 모르면 정기)."""
    from server.api.routers.sitok import kind_known
    from server.api.routers.sitok_onboard import _default_people
    from server.api.routers.sitok_reports import _new_report

    today = datetime.date.today()
    half = "상반기" if today.month <= 6 else "하반기"
    if rc.start_date and rc.end_date and not (rc.start_date <= today <= rc.end_date):
        return None
    if db.query(SitokReport).filter(SitokReport.facility_id == f.id, SitokReport.year == today.year, SitokReport.half == half).first():
        return None
    chief, parts = _default_people(db, user.company_id)
    r = _new_report(db, user.display_name or "", f, today.year, half, contract_id=rc.id, chief_id=chief, participant_ids=parts,
                    kind=kind_known(db, rc, today.year, half) or "정기")
    return r.id


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


# ---------- 관급 착수계·완료계(2단계, server/sitok/gov_docs.py) ----------

def _read_g2b(pdf: Path, company_id: int) -> tuple[dict, str]:
    """나라장터 계약서 → 계약 칸(글자 규칙, 못 읽은 중요한 칸만 AI — 산안법과 같음, 용역 종류만 바꾼 물음). 사업 담당(수요기관) = 현장 담당."""
    from server.contract_docs import contract_ai, contract_pdf

    try:
        text = contract_pdf.read_text(pdf)
        got = contract_pdf.parse_text(text)
        # 발주처 기관명이 줄이 나뉘어 꼬리만 읽힌 경우("광" / "숭초등학교" — 광숭초 계약서) → 수요기관 기관명(같은 이름이 온전히 한 줄)
        m = re.search(r"<수요기관>\s*기\s*관\s*명\s*:?\s*([^\n]+)", text)
        whole = m[1].strip() if m else ""
        if got.get("client") and whole != got["client"] and whole.endswith(got["client"]):
            got["client"] = whole
    except Exception:  # noqa: BLE001 — 글자 없는 스캔 등 → 전부 AI
        got = {k: None for k in contract_ai.KEY_FIELDS + ("contract_date",)}
    error = ""
    if contract_ai.needs_ai(got):
        try:
            prompt = contract_ai.PROMPT.replace("건설재해예방 기술지도 용역", "시설물 정기안전점검 용역")
            for k, v in contract_ai.read_with_ai(pdf, company_id, prompt).items():
                if v and not got.get(k):
                    got[k] = v
        except Exception as err:  # noqa: BLE001
            error = f"못 읽은 칸이 있습니다 — 직접 넣어 주세요. ({str(err).splitlines()[0][:150] if str(err) else type(err).__name__})"
    for a, b in (("biz_manager", "site_manager"), ("biz_phone", "site_phone"), ("biz_email", "site_email")):
        got[b] = got.pop(a, None)
    keys = ("client", "title", "contract_no", "amount", "contract_date", "start_date", "end_date", "client_manager", "client_phone", "client_email",
            "site_manager", "site_phone", "site_email")
    return {k: got.get(k) for k in keys}, error


def _gov_made(c: SitokDocContract, kind: str) -> dict:
    at = c.start_made_at if kind == "start" else c.done_made_at
    base = folder(c) if c.id else None
    return {"at": at.strftime("%Y-%m-%d %H:%M") if at else "", "pdf": bool(base and (base / f"{GOV[kind]}.pdf").exists()),
            "xlsx": bool(base and (base / f"{GOV[kind]}.xlsx").exists())}


def _values(c: SitokDocContract) -> build.Contract:
    return build.Contract(client=c.client, title=c.title, contract_no=c.contract_no, amount=c.amount, contract_date=c.contract_date,
                          start_date=c.start_date, end_date=c.end_date)


def _person_docs(db: Session, p: TechPerson) -> dict:
    d = lib.person_docs(db, p.id)
    return {k: d.get(src) for k, src, _ in GOV_PERSON_DOCS}


def _person_state(db: Session, p: TechPerson) -> dict:
    d = _person_docs(db, p)
    return {"id": p.id, "name": p.name, "qualification": p.qualification, "grade": gov_docs.grade_text(p.sitok_grade, p.grade),
            "missing": [label for k, _, label in GOV_PERSON_DOCS if not lib.doc_status(d[k])],
            "expired": [label for k, _, label in GOV_PERSON_DOCS if lib.doc_status(d[k]) == "expired"]}


def _person(db: Session, p: TechPerson) -> gov_docs.Person:
    d = _person_docs(db, p)
    return gov_docs.Person(name=p.name, address=p.address, birth_date=p.birth_date, position=p.position, join_date=p.join_date,
                           qualification=p.qualification, grade=gov_docs.grade_text(p.sitok_grade, p.grade),
                           docs={k: d[k].file for k in ("license", "edu", "career") if d[k] is not None and d[k].file},
                           sign=d["sign"].file if d["sign"] is not None and d["sign"].file else "")


def _cover_source(db: Session, c: SitokDocContract) -> tuple[Path | None, str]:
    """결과보고서 장 표지 — 올린 표지 > 연결한 시설물의 만든 보고서(보고서 쪽에 넣은 계약의 회차 먼저, 그다음 최근)."""
    up = folder(c) / "결과보고서_표지.pdf"
    if c.id and up.exists():
        return up, "올린 표지"
    if c.facility_id:
        reps = [r for r in db.query(SitokReport).filter(SitokReport.facility_id == c.facility_id).all() if r.out_pdf and Path(r.out_pdf).exists()]
        reps.sort(key=lambda r: (r.contract_id is not None and r.contract_id == c.report_contract_id, r.made_at or r.created_at), reverse=True)
        if reps:
            return Path(reps[0].out_pdf), f"{reps[0].year}년 {reps[0].half} 보고서 표지(연결한 시설물)"
    return None, ""


def _attach_list(c: SitokDocContract, kind: str) -> list[dict]:
    k = f"sitok_{kind}"
    return [{"slot": key, "label": label, "files": [attachments.file_info(f) for f in attachments.list_files(folder(c), k, key)]}
            for key, label, _ in attachments.SLOTS[k]]


@router.get("/contracts/{cid}/gov")
def gov_state(cid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """착수계·완료계 창 — 기본값(문서번호·인사말·담당), 기술자 명단(빠진 서류), 붙임, 결과보고서 표지."""
    c = _require(db, user, cid)
    v = _values(c)
    _, cover = _cover_source(db, c)
    return summary(db, c) | {
        "defaults": {"doc_no_start": build.default_doc_no(v, c.start_date), "doc_no_done": build.default_doc_no(v, c.end_date),
                     "greeting": gov_docs.greeting(c.client), "contact_name": config.get_doc_contact_name(user.company_id)},
        "agent_id": c.agent_id, "participant_ids": c.participant_ids or [],
        "persons": [_person_state(db, p) for p in lib.persons(db, user.company_id) if p.active],
        "attachments": {k: _attach_list(c, k) for k in GOV},
        "cover": cover,
    }


class GovIn(BaseModel):
    contract: ContractIn | None = None
    doc_no: str = ""
    greeting: str = ""
    contact: str = ""
    seal: bool = True
    agent_id: int | None = None
    participant_ids: list[int] = []


def _doc_warnings(db: Session, chosen: list[TechPerson]) -> list[str]:
    out = []
    for p in chosen:
        d = _person_docs(db, p)
        for k, _, lab in GOV_PERSON_DOCS:
            if lib.doc_status(d[k]) == "expired":
                out.append(f"⚠ {p.name} {lab} 유효기간 지남({d[k].valid_until}) — 새로 발급받아 설정 탭에서 바꾸세요.")
            elif lib.doc_status(d[k]) == "nodate":
                out.append(f"⚠ {p.name} {lab} 발급일을 모릅니다 — 유효기간을 확인할 수 없으니 설정 탭에서 발급일을 적으세요.")
    return out


@router.post("/contracts/{cid}/gov/{kind}")
def make_gov(cid: int, kind: Literal["start", "done"], body: GovIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """착수계·완료계 엑셀(양식 채움) → LibreOffice PDF → 붙임(산출내역서·완수내역서) 끼운 합본 PDF."""
    import openpyxl

    from server.contract_docs import to_pdf

    c = _require(db, user, cid)
    if body.contract is not None:
        _apply(c, body.contract, user)
    v = _values(c)
    if not v.client or not v.title:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "발주처·용역명을 먼저 채우세요(나라장터 계약서를 올리면 자동으로 채워집니다).")
    label = GOV[kind]
    base = folder(c)
    xlsx, pdf = base / f"{label}.xlsx", base / f"{label}.pdf"
    doc_no = body.doc_no.strip() or build.default_doc_no(v, c.start_date if kind == "start" else c.end_date)
    greet = body.greeting.strip() or gov_docs.greeting(c.client)
    contact = body.contact.strip() or config.get_doc_contact_name(user.company_id)
    warnings: list[str] = []
    try:
        if kind == "start":
            mine = {p.id: p for p in lib.persons(db, user.company_id)}
            if body.agent_id not in mine:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "현장대리인(책임기술자)을 고르세요.")
            part_ids = [i for i in dict.fromkeys(body.participant_ids) if i in mine and i != body.agent_id]
            chosen = [mine[body.agent_id]] + [mine[i] for i in part_ids]
            warnings += _doc_warnings(db, chosen)
            warnings += gov_docs.build_start(v, doc_no, greet, contact, body.seal, _person(db, chosen[0]), [_person(db, p) for p in chosen[1:]], xlsx)
            c.agent_id, c.participant_ids = body.agent_id, part_ids
        else:
            src, _ = _cover_source(db, c)
            warnings += gov_docs.build_done(v, doc_no, greet, contact, body.seal, gov_docs.cover_image(src) if src else None, xlsx)
    except (FileNotFoundError, ValueError) as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
    pdf_error = ""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            sheets = Path(tmp) / "sheets.pdf"
            to_pdf.office_to_pdf(xlsx, sheets)
            count = len(openpyxl.load_workbook(xlsx, read_only=True).sheetnames)
            warnings += attachments.merge(sheets, base, f"sitok_{kind}", count, pdf)
    except Exception as err:  # noqa: BLE001 — 엑셀은 받을 수 있게 두고 PDF만 실패 알림
        pdf.unlink(missing_ok=True)
        pdf_error = str(err)[:300]
    if kind == "start":
        c.start_made_at = datetime.datetime.now()
    else:
        c.done_made_at = datetime.datetime.now()
    db.commit()
    return {"warnings": warnings, "pdf_error": pdf_error, "gov": {k: _gov_made(c, k) for k in GOV}, "doc_no": doc_no}


@router.get("/contracts/{cid}/gov/{kind}.{ext}")
def gov_file(cid: int, kind: Literal["start", "done"], ext: Literal["xlsx", "pdf"], inline: bool = False,
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _require(db, user, cid)
    path = folder(c) / f"{GOV[kind]}.{ext}"
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"아직 만든 {GOV[kind]}가 없습니다.")
    name = re.sub(r'[\\/:*?"<>|]', "_", f"{c.title or c.client or '계약'}_{GOV[kind]}.{ext}")
    return FileResponse(path, media_type="application/pdf" if ext == "pdf" else XLSX, filename=name,
                        content_disposition_type="inline" if inline else "attachment", headers={"Cache-Control": "no-store"})


def _slot(kind: str, slot: str) -> str:
    k = f"sitok_{kind}"
    if slot not in {key for key, _, _ in attachments.SLOTS[k]}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 붙임 칸입니다.")
    return k


@router.post("/contracts/{cid}/gov/{kind}/attach/{slot}")
def gov_attach(cid: int, kind: Literal["start", "done"], slot: str, file: UploadFile = File(...), user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    """붙임 파일(산출내역서·완수내역서 — 견적서) 올리기 — 바로 PDF로 바꿔 둠(한글은 작업 PC 한글로)."""
    c = _require(db, user, cid)
    k = _slot(kind, slot)
    try:
        attachments.add_file(folder(c), k, slot, file.file.read(), file.filename or "")
    except (ValueError, RuntimeError) as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
    return _attach_list(c, kind)


@router.delete("/contracts/{cid}/gov/{kind}/attach/{slot}/{name}")
def gov_attach_delete(cid: int, kind: Literal["start", "done"], slot: str, name: str, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    c = _require(db, user, cid)
    attachments.remove_file(folder(c), _slot(kind, slot), slot, name)
    return _attach_list(c, kind)


@router.get("/contracts/{cid}/gov/{kind}/attach/{slot}/{name}")
def gov_attach_view(cid: int, kind: Literal["start", "done"], slot: str, name: str, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    c = _require(db, user, cid)
    path = attachments.slot_dir(folder(c), _slot(kind, slot), slot) / Path(name).name
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일이 없습니다.")
    return FileResponse(path, media_type="application/pdf", filename=path.name, content_disposition_type="inline")
