"""시특법 새 점검 대상 등록을 한 번에(2026-10-12 사용자) — 한 화면(sitok-new.html)에서 계약서·이전 회차 보고서·동마다 시설물관리대장·건축물대장을
올리고 [등록하고 시작]. 없는 서류는 비워도 됨: 이전 회차(처음 점검)·건축물대장(군사보안 등 — 그 칸은 "-"로 두고 직접 입력)·시설물관리대장
(법정 외 자체 점검 — 칸 직접 입력, 틀 2종/3종일반 고름, 결과표 종별 "해당없음").

- `POST /sitok/prior` — 이전 회차 보고서 임시로 올리기(우리 한글 hwp·hwpx 또는 타회사·우리 PDF) → token + 알아낸 것(연도·반기·동 수 / 결함표).
- `POST /sitok/onboard` — 등록하고 시작: 동마다 시설물(관리대장·건축물대장 PDF는 시설물 폴더로) → 2동 이상이면 묶음 → 계약(1번 동) →
  이전 회차 한글은 이미 낸 보고서로 등록(여러 동 보고서면 동마다 나눔) → 이번 반기 회차(묶인 동 같이 — 전회차 데이터는 방금 등록한 것) →
  이전 회차가 PDF면 그 회차 현장 조사에 전회차 결함(한 동일 때 — 여러 동이면 현장 조사에서 동마다).
"""
from __future__ import annotations

import secrets
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokFacility, SitokGroup, TechPerson, User
from server.api.deps import get_current_user, get_db
from server.api.routers.sitok import (UPLOAD_DIR, ContractIn, FacilityIn, _add_contract, _apply_facility, _clean_uploads, _facility_dir,
                                      _facility_out, _take, default_badges, default_type, next_mgmt_no)
from server.api.routers.sitok_reports import HALVES, _chapter_count, _group_reports, _new_report, _out, register_prior_file
from server.contract_docs import hwp_queue
from server.sitok import report_build as rb

router = APIRouter(prefix="/sitok", tags=["sitok"])


def _prior_path(token: str | None) -> Path | None:
    if not token or not token.isalnum():
        return None
    return next((p for p in (UPLOAD_DIR / f"{token}.hwpx", UPLOAD_DIR / f"{token}.pdf") if p.exists()), None)


@router.post("/prior")
def upload_prior(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    """이전 회차 보고서 임시로 — 한글이면 결과표 연도·반기·동 수, PDF면 우리 사진첩/타회사 결함표가 있는지."""
    name = file.filename or "이전회차"
    ext = Path(name).suffix.lower()
    data = file.file.read()
    _clean_uploads()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(12)
    if ext in (".hwp", ".hwpx"):
        if ext == ".hwp":
            try:
                data = hwp_queue.convert_via_worker(data, ".hwp", to="hwpx", wait=170)
            except RuntimeError as err:
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(err)) from err
        path = UPLOAD_DIR / f"{token}.hwpx"
        path.write_bytes(data)
        try:
            v = rb.read_old(path)
        except Exception as err:  # noqa: BLE001
            path.unlink(missing_ok=True)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
        return {"token": token, "kind": "hwpx", "name": name, "year": v.year, "half": v.half, "title": v.title, "chapters": _chapter_count(path)}
    if not data.startswith(b"%PDF"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "이전 회차 보고서는 한글(.hwp·.hwpx) 또는 PDF로 올려 주세요.")
    import pymupdf

    from server.sitok import album_read, foreign_read

    path = UPLOAD_DIR / f"{token}.pdf"
    path.write_bytes(data)
    ours = bool(album_read.read(data).rows)
    found = ours or bool(foreign_read.defect_tables(pymupdf.open(stream=data, filetype="pdf")))
    return {"token": token, "kind": "pdf", "name": name, "ours": ours, "has_defects": found}


class BuildingIn(BaseModel):
    facility: FacilityIn
    ledger_token: str | None = None  # 시설물관리대장(없으면 직접 입력 — 법정 외)
    ledger_extra: dict | None = None
    register_token: str | None = None  # 건축물대장(없으면 그 칸 "-")


class OnboardIn(BaseModel):
    buildings: list[BuildingIn]
    contract: ContractIn | None = None
    prior_token: str | None = None
    prior_name: str | None = None
    group_name: str | None = None
    year: int
    half: str


def _default_people(db: Session, company_id: int) -> tuple[int | None, list[int]]:
    """이번 회차 기본 기술자 — 책임 = 시특법 기술등급에 "특급", 참여 = 그다음 사람(회차 카드 [새 회차]와 같음)."""
    ps = db.query(TechPerson).filter(TechPerson.company_id == company_id, TechPerson.active.is_(True)).order_by(TechPerson.name).all()
    chief = next((p for p in ps if "특급" in (p.sitok_grade or "")), ps[0] if ps else None)
    other = next((p for p in ps if chief is None or p.id != chief.id), None)
    return (chief.id if chief else None), ([other.id] if other else [])


@router.post("/onboard")
def onboard(body: OnboardIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from server.api.routers.sitok_defects import start_import

    if not body.buildings:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "동을 하나 이상 넣어 주세요.")
    if body.half not in HALVES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "이번 회차 반기를 고르세요.")
    for i, b in enumerate(body.buildings, 1):
        if not (b.facility.name or "").strip():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{i}번 동 시설물명을 넣어 주세요(시설물관리대장을 올리면 채워집니다).")
    by = user.display_name or ""
    notes: list[str] = []
    # 1) 동마다 시설물
    facs = []
    for b in body.buildings:
        f = SitokFacility(company_id=user.company_id, created_by=by, ledger=b.ledger_extra or None)
        _apply_facility(f, b.facility)
        db.add(f)
        db.flush()
        f.ledger_pdf = _take(b.ledger_token, _facility_dir(f) / "시설물관리대장.pdf")
        if not _take(b.register_token, _facility_dir(f) / "건축물대장.pdf"):
            notes.append(f"{f.name}: 건축물대장 없음 — 시설물 현황·1.2.8은 \"-\"로 두고 직접 입력")
        facs.append(f)
    lead = facs[0]
    # 번호표·계약 구분(10/13) — 묶인 동은 한 번호(1번 동에 적은 번호, 없으면 다음 번호), 구분은 계약(민간 = 장기·지속, 관급 = 1회성)
    sector = (body.contract.sector if body.contract else None) or lead.sector or "민간"
    no = lead.mgmt_no or next_mgmt_no(db, user.company_id, sector)
    for f in facs:
        f.mgmt_no = no
        f.sector = sector
        default_badges(f, body.contract.field if body.contract else None)
        if body.buildings[0].facility.contract_type is None:
            f.contract_type = default_type(body.contract.sector if body.contract else None)
    # 2) 묶음(2동 이상)
    if len(facs) > 1:
        g = SitokGroup(company_id=user.company_id, name=(body.group_name or "").strip() or lead.owner_name or lead.name)
        db.add(g)
        db.flush()
        for i, f in enumerate(facs):
            f.group_id, f.group_order = g.id, i
    # 3) 계약(1번 동)
    c = _add_contract(db, user, lead, body.contract) if body.contract is not None else None
    db.flush()
    # 4) 이전 회차 — 한글이면 이미 낸 보고서로(이번 회차의 전회차 데이터), PDF면 보관(아래 5에서 결함 가져오기)
    prior = _prior_path(body.prior_token)
    prior_pdf: Path | None = None
    if prior is not None and prior.suffix == ".hwpx":
        tmp = _facility_dir(lead) / "_올림_지난보고서.hwpx"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(prior), tmp)
        register_prior_file(db, user, lead, tmp, body.prior_name or "이전 회차 보고서")
        db.flush()
    elif prior is not None:
        prior_pdf = _facility_dir(lead) / "이전회차보고서.pdf"
        prior_pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(prior), prior_pdf)
    # 5) 이번 반기 회차(묶인 동 같이)
    chief, parts = _default_people(db, user.company_id)
    from core.models_web import SitokReport

    r = db.query(SitokReport).filter(SitokReport.facility_id == lead.id, SitokReport.year == body.year, SitokReport.half == body.half).first()
    if r is None:
        from server.api.routers.sitok import kind_known
        kind = kind_known(db, c, body.year, body.half)  # 10/14: 새 등록도 계약서 회차 줄·계약건명으로 종류, 모르면 정기 + 안내
        if kind is None:
            notes.append(f"{body.year}년 {body.half} 회차 종류(정기/정밀)를 계약서에서 못 읽어 정기로 만들었습니다 — 회차 줄의 배지를 눌러 바꾸세요")
        r = _new_report(db, by, lead, body.year, body.half, contract_id=c.id if c else None, chief_id=chief, participant_ids=parts, kind=kind or "정기")
    else:
        notes.append(f"{body.year}년 {body.half}는 이전 회차 보고서로 등록돼 있어 새로 만들지 않았습니다 — 다음 회차를 만드세요")
    if len(facs) > 1:
        _group_reports(db, r, by)
    db.commit()
    if prior_pdf is not None:
        if len(facs) == 1 and r.status != "done":
            try:
                start_import(db, r, prior_pdf.read_bytes(), user.company_id)
                notes.append("이전 회차 PDF에서 전회차 결함을 가져오는 중 — 현장 조사 화면에서 확인하세요")
            except ValueError as err:
                notes.append(f"이전 회차 PDF: {err}")
        else:
            notes.append("이전 회차 PDF는 시설물 폴더에 보관 — 여러 동이면 현장 조사에서 동마다 [지난 보고서 PDF에서 가져오기]")
    return {"facility": _facility_out(db, lead), "report": _out(r), "notes": notes}
