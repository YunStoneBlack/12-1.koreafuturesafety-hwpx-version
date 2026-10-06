"""서류 자동화 — 용역 계약과 착수계·완수계(2026-10-06). 계약은 현장 없이 먼저 생기고(착수계가 현장 등록보다 먼저 — 형), 나중에 현장과 연결한다.

- `GET /contracts` — 계약 목록(관리번호·단계·제출·착수일·완수일·연결 현장), `GET /contracts/next-management-no` — 관리번호 자동생성 — 서류 자동화 계약 목록·제출 현황·일정 달력이 같이 씀
- `POST /contracts` (빈 계약) / `POST /contracts/from-pdf` (용역계약서 PDF로 새 계약 — 글자 규칙, 못 읽은 칸은 Claude API)
- `GET|PUT|DELETE /contracts/{id}` — 창에 필요한 것 전부 / 계약 값 저장 / 지우기(파일까지, 삭제 비밀번호)
- `POST /contracts/{id}/pdf` — 계약서 PDF 다시 올리기(읽은 칸만 덮어씀)
- `POST /contracts/{id}/link {site_id|null}` — 현장 연결·해제(현장 하나에 계약 하나)
- `POST /contracts/{id}/docs/{start|done}` — 엑셀 + 합본 PDF(LibreOffice + 붙임 파일), `GET …/docs/{kind}.{xlsx|pdf}` — 받기
- `POST|GET|DELETE /contracts/{id}/docs/{kind}/attach/{칸}[/{파일}]` — 붙임 파일(attachments.py)
- `GET /sites/{id}/contract` — 현장 화면 버튼: 연결된 계약, 없으면 연결할 후보(비슷한 이름 순)
"""
from __future__ import annotations

import datetime
import tempfile
from pathlib import Path
from typing import Literal

import openpyxl
from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core import config
from core.models_db import Site
from core.models_web import ServiceContract, TechPerson, User
from server.api import repo
from server.api.deps import get_current_user, get_db
from server.api.security import verify_password
from server.api.routers.contract_library import company_docs, doc_status, person_docs, persons
from server.api.site_label import short_mgmt, site_label
from server.contract_docs import attachments, build, contract_ai, contract_pdf, contract_status, files, to_pdf

router = APIRouter(prefix="/contracts", tags=["contracts"])
site_router = APIRouter(prefix="/sites/{site_id}", tags=["contracts"])

KIND_LABEL = {"start": "착수계", "done": "완수계"}
CONTRACT_FIELDS = ("client", "title", "contract_no", "amount", "contract_date", "start_date", "end_date", "settle_amount",
                   "actual_end_date")
DATE_FIELDS = {"contract_date", "start_date", "end_date", "actual_end_date"}


class ContractIn(BaseModel):
    management_no: str | None = None
    client: str | None = None
    title: str | None = None
    contract_no: str | None = None
    amount: int | None = None
    contract_date: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    settle_amount: int | None = None
    actual_end_date: str | None = None


def _iso(d) -> str:
    return d.isoformat() if d else ""


def _require(db: Session, user: User, contract_id: int) -> ServiceContract:
    row = db.get(ServiceContract, contract_id)
    if row is None or row.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "용역 계약을 찾을 수 없습니다.")
    return row




def _contract_values(row: ServiceContract) -> build.Contract:
    return build.Contract(**{k: getattr(row, k) for k in CONTRACT_FIELDS})


def _made(row: ServiceContract) -> dict:
    out = {}
    for kind, label in KIND_LABEL.items():
        at = row.start_made_at if kind == "start" else row.done_made_at
        pdf = files.out_path(row, f"{label}.pdf").exists()
        out[kind] = {"at": at.strftime("%Y-%m-%d %H:%M") if at else "", "xlsx": files.out_path(row, f"{label}.xlsx").exists(),
                     "pdf": pdf, "submitted": contract_status.submitted(row, kind, pdf)}
    return out


def next_management_no(db: Session, company_id: int, year: int | None = None) -> str:
    """계약 관리번호 자동생성 — "{연도}-{7자리 일련번호}", 이 회사 계약 중 그 연도의 가장 큰 번호 + 1.
    현장 관리번호(sites.next_management_no)와 같은 모양이지만 계약끼리 따로 센다(사용자 10/6 가안)."""
    prefix = f"{year or datetime.date.today().year}-"
    max_seq = 0
    for (no,) in db.query(ServiceContract.management_no).filter(ServiceContract.company_id == company_id):
        suffix = (no or "")[len(prefix):] if (no or "").startswith(prefix) else ""
        if suffix.isdigit():
            max_seq = max(max_seq, int(suffix))
    return f"{prefix}{max_seq + 1:07d}"


def contract_label(row: ServiceContract) -> str:
    """화면 이름 "26-3)_용역명"(현장 이름과 같은 모양 — site_label)."""
    short = short_mgmt(row.management_no)
    title = row.title or "(용역명 없음)"
    return f"{short})_{title}" if short else title


def summary(db: Session, row: ServiceContract) -> dict:
    """목록 한 줄(계약 목록·제출 현황·일정 달력)."""
    made = _made(row)
    site = db.get(Site, row.site_id) if row.site_id else None
    dates = contract_status.plan_dates(row)
    return {
        "id": row.id, "title": row.title, "management_no": row.management_no or "", "label": contract_label(row), "client": row.client, "contract_no": row.contract_no, "amount": row.amount,
        "contract_date": _iso(row.contract_date), "start_date": _iso(row.start_date), "end_date": _iso(row.end_date),
        "site_id": row.site_id, "site_label": site_label(site) if site else "",
        "stage": contract_status.stage(made["start"]["submitted"], made["done"]["submitted"]),
        "made": made, "dates": {k: _iso(v) for k, v in dates.items()},
        "created_at": row.created_at.strftime("%Y-%m-%d") if row.created_at else "",
    }


@router.get("/next-management-no")
def get_next_management_no(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """[자동생성] — 저장은 안 함."""
    return {"management_no": next_management_no(db, user.company_id)}


@router.get("")
def list_contracts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(ServiceContract).filter(ServiceContract.company_id == user.company_id).order_by(ServiceContract.id.desc()).all()
    return {"contracts": [summary(db, r) for r in rows], "stages": contract_status.STAGES}


def _new(db: Session, user: User) -> ServiceContract:
    row = ServiceContract(company_id=user.company_id, client="", title="", contract_no="", contract_pdf="", updated_by=user.display_name or "",
                          management_no=next_management_no(db, user.company_id),  # 만들 때 자동(고칠 수 있음)
                          created_at=datetime.datetime.now(), updated_at=datetime.datetime.now())
    db.add(row)
    db.flush()
    return row


@router.post("")
def create_contract(body: ContractIn | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """새 계약 — 창([+ 새 계약])에서 처음 무언가 할 때(붙임 올리기·현장 연결·착수계 만들기) 그때까지 적은 값으로 만든다."""
    row = _new(db, user)
    if body is not None:
        _apply_contract(row, body.model_dump(exclude_unset=True), user)
    db.commit()
    return state(db, user, row)


@router.get("/blank")
def blank_contract(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """[+ 새 계약] 창의 빈 화면 — DB에 행을 만들지 않는다(아무것도 안 하고 닫으면 빈 계약이 안 남게, 10/6 사용자). id 0 = 아직 없음."""
    row = ServiceContract(id=0, company_id=user.company_id, client="", title="", contract_no="", contract_pdf="", participant_ids=[],
                          management_no=next_management_no(db, user.company_id))  # 미리 보여 주기만(만들 때 다시 셈)
    return state(db, user, row)


def _read_pdf(db: Session, user: User, row: ServiceContract, data: bytes) -> dict:
    if data[:4] != b"%PDF":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "용역계약서 PDF 파일을 올리세요.")
    ai_filled: list[str] = []
    ai_error = ""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "c.pdf"
        src.write_bytes(data)
        try:
            parsed = contract_pdf.parse_pdf(src)
        except Exception:  # noqa: BLE001 — 글자가 없는 스캔 PDF 등 → 전부 AI로
            parsed = {k: None for k in contract_ai.KEY_FIELDS + ("contract_date",)}
        # 글자 규칙으로 못 읽은 중요한 칸이 있으면 Claude API로 빈칸만(사용자 10/6) — 키가 없거나 실패해도 계약은 만들고 칸만 빈다
        if contract_ai.needs_ai(parsed):
            try:
                for k, v in contract_ai.read_with_ai(src, user.company_id).items():
                    if v and not parsed.get(k):
                        parsed[k] = v
                        ai_filled.append(k)
            except Exception as err:  # noqa: BLE001
                ai_error = str(err).splitlines()[0][:200] if str(err) else type(err).__name__
    found = {k: (_iso(v) if k in DATE_FIELDS else v) for k, v in parsed.items() if v}
    _apply_contract(row, found, user)
    db.flush()
    dest = files.out_path(row, "용역계약서.pdf")  # 용역명이 채워진 뒤 폴더 이름이 정해지게
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    row.contract_pdf = str(dest)
    return {"read": sorted(found), "unread": [k for k in parsed if not parsed[k]], "ai_filled": ai_filled, "ai_error": ai_error}


@router.post("/from-pdf")
def create_from_pdf(file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = file.file.read()
    row = _new(db, user)
    info = _read_pdf(db, user, row, data)
    same = (db.query(ServiceContract).filter(ServiceContract.company_id == user.company_id, ServiceContract.id != row.id,
                                             ServiceContract.contract_no == row.contract_no).first() if row.contract_no else None)
    db.commit()
    out = state(db, user, row) | info
    if same is not None:
        out["duplicate_of"] = {"id": same.id, "title": same.title}
    return out


def state(db: Session, user: User, row: ServiceContract) -> dict:
    """착수계·완수계 창에 필요한 것 전부."""
    c = _contract_values(row)
    today = datetime.date.today()
    docs = company_docs(db, user.company_id)
    return summary(db, row) | {
        "contract": {k: (_iso(v) if k in DATE_FIELDS else v) for k, v in vars(c).items()}
        | {"has_pdf": files.out_path(row, "용역계약서.pdf").exists()},
        "defaults": {
            "greeting": build.greeting_word(c.client),
            "doc_no_start": build.default_doc_no(c, c.start_date),
            "doc_no_done": build.default_doc_no(c, today),
            "send_date": today.isoformat(),
            "contact_name": config.get_doc_contact_name(user.company_id),
        },
        "agent_id": row.agent_id,
        "participant_ids": row.participant_ids or [],
        "persons": [_person_state(db, p) for p in persons(db, user.company_id) if p.active],
        "company_docs": [{"kind": k, "label": label, "status": doc_status(docs.get(k)),
                          "valid_until": _iso(docs[k].valid_until) if k in docs else ""} for k, label in build.COMPANY_DOCS],
        "attachments": {kind: _attach_list(row, kind) for kind in KIND_LABEL},
    }


def _person_state(db: Session, p: TechPerson) -> dict:
    docs = person_docs(db, p.id)
    return {"id": p.id, "name": p.name, "qualification": p.qualification, "grade": p.grade,
            "missing": [label for k, label in build.PERSON_DOCS if not doc_status(docs.get(k))],
            "expired": [label for k, label in build.PERSON_DOCS if doc_status(docs.get(k)) == "expired"]}


@router.get("/{contract_id}")
def get_contract(contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return state(db, user, _require(db, user, contract_id))


def _apply_contract(row: ServiceContract, fields: dict, user: User) -> None:
    if "management_no" in fields:  # 서류 값(build.Contract)이 아니라 화면 이름용이라 따로
        row.management_no = (fields["management_no"] or "").strip()
    for k, v in fields.items():
        if k not in CONTRACT_FIELDS:
            continue
        if k in DATE_FIELDS:
            try:
                v = datetime.date.fromisoformat(v[:10]) if v else None
            except ValueError as err:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"날짜 형식이 아닙니다: {v}") from err
        elif isinstance(v, str):
            v = v.strip()
        setattr(row, k, v)
    row.updated_at = datetime.datetime.now()
    row.updated_by = user.display_name or ""


@router.put("/{contract_id}")
def put_contract(contract_id: int, body: ContractIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _require(db, user, contract_id)
    _apply_contract(row, body.model_dump(exclude_unset=True), user)
    db.commit()
    return state(db, user, row)


@router.delete("/{contract_id}")
def delete_contract(contract_id: int, password: str = Body("", embed=True), user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """계약 지우기(만든 착수계·완수계·붙임 파일까지, 되돌릴 수 없음) — 현장 삭제와 같은 회사 공용 삭제 비밀번호(사용자 10/6)."""
    password_hash = config.get_site_delete_password_hash(user.company_id)
    if not password_hash:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "삭제 비밀번호가 아직 없습니다. '설정' 탭에서 먼저 정하세요.")
    if not verify_password(password, password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "삭제 비밀번호가 맞지 않습니다.")
    row = _require(db, user, contract_id)
    files.delete_contract_files(row)
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/{contract_id}/pdf")
def upload_contract_pdf(contract_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    row = _require(db, user, contract_id)
    info = _read_pdf(db, user, row, file.file.read())
    db.commit()
    return state(db, user, row) | info


class LinkIn(BaseModel):
    site_id: int | None = None


@router.post("/{contract_id}/link")
def link_site(contract_id: int, body: LinkIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """현장 연결(현장 하나에 계약 하나 — 그 현장에 다른 계약이 있으면 막음)·해제(site_id 비움)."""
    row = _require(db, user, contract_id)
    if body.site_id is not None:
        site = repo.get_site(db, user.company_id, body.site_id)
        if site is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "현장을 찾을 수 없습니다.")
        other = db.query(ServiceContract).filter(ServiceContract.site_id == site.id, ServiceContract.id != row.id).first()
        if other is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, f"이 현장에는 이미 다른 용역 계약이 연결돼 있습니다: {other.title or other.contract_no}")
    row.site_id = body.site_id
    row.updated_at = datetime.datetime.now()
    db.commit()
    return state(db, user, row)


@router.get("/{contract_id}/site-candidates")
def site_candidates(contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """연결할 현장 고르기 — 아직 계약이 없는 현장, 용역명과 비슷한 순."""
    row = _require(db, user, contract_id)
    taken = {sid for (sid,) in db.query(ServiceContract.site_id).filter(ServiceContract.site_id.isnot(None), ServiceContract.id != row.id)}
    sites = [s for s in db.query(Site).filter(Site.company_id == user.company_id).all() if s.id not in taken]
    scored = sorted(((contract_status.similarity(row.title, s.name), s) for s in sites), key=lambda x: (-x[0], -x[1].id))
    return [{"id": s.id, "label": site_label(s), "address": s.address or "", "score": round(score, 2)} for score, s in scored]


class MakeIn(BaseModel):
    contract: ContractIn | None = None
    doc_no: str = ""
    greeting: str = ""
    send_date: str = ""
    seal: bool = True
    agent_id: int | None = None
    participant_ids: list[int] = []


def _person(db: Session, p: TechPerson) -> build.Person:
    docs = person_docs(db, p.id)
    return build.Person(name=p.name, address=p.address, birth_date=p.birth_date, position=p.position, join_date=p.join_date,
                        qualification=p.qualification, grade=p.grade,
                        docs={k: d.file for k, d in docs.items() if d.file})


def _expired_warnings(db: Session, user: User, kind: str, chosen: list[TechPerson], on: datetime.date) -> list[str]:
    out = []
    if kind == "done":
        docs = company_docs(db, user.company_id)
        for k, label in build.COMPANY_DOCS:
            d = docs.get(k)
            if doc_status(d, on) == "expired":
                out.append(f"⚠ {label} 유효기간 지남({d.valid_until}) — 새로 발급받아 설정 탭에서 바꾸세요.")
    else:
        for p in chosen:
            docs = person_docs(db, p.id)
            for k, label in build.PERSON_DOCS:
                d = docs.get(k)
                if doc_status(d, on) == "expired":
                    out.append(f"⚠ {p.name} {label} 유효기간 지남({d.valid_until}) — 새로 발급받아 설정 탭에서 바꾸세요.")
    return out


@router.post("/{contract_id}/docs/{kind}")
def make_docs(contract_id: int, kind: Literal["start", "done"], body: MakeIn, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    row = _require(db, user, contract_id)
    if body.contract is not None:
        _apply_contract(row, body.contract.model_dump(exclude_unset=True), user)
    c = _contract_values(row)
    if not c.title or not c.client:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "발주처·용역명을 먼저 채우세요(계약서 PDF를 올리면 자동으로 채워집니다).")
    try:
        send = datetime.date.fromisoformat(body.send_date[:10]) if body.send_date else datetime.date.today()
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "발송일 형식이 아닙니다.") from err
    common = build.Common(doc_no=body.doc_no.strip(), greeting=body.greeting.strip(), send_date=send,
                          contact_name=config.get_doc_contact_name(user.company_id), seal=body.seal)
    label = KIND_LABEL[kind]
    xlsx, pdf = files.out_path(row, f"{label}.xlsx"), files.out_path(row, f"{label}.pdf")
    chosen: list[TechPerson] = []
    if kind == "start":
        mine = {p.id: p for p in persons(db, user.company_id)}
        if body.agent_id not in mine:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "현장대리인(책임기술자)을 고르세요.")
        part_ids = [i for i in dict.fromkeys(body.participant_ids) if i in mine and i != body.agent_id]
        chosen = [mine[body.agent_id]] + [mine[i] for i in part_ids]
        warnings = build.build_start(c, common, _person(db, chosen[0]), [_person(db, p) for p in chosen[1:]], xlsx)
        row.agent_id, row.participant_ids = body.agent_id, part_ids
    else:
        docs = company_docs(db, user.company_id)
        warnings = build.build_done(c, common, {k: d.file for k, d in docs.items() if d.file}, xlsx)
    warnings = _expired_warnings(db, user, kind, chosen, send if kind == "done" else datetime.date.today()) + warnings
    pdf_error = ""
    try:  # 시트 PDF → 붙임 파일 끼워 합본 PDF 하나(사용자·형 10/6)
        with tempfile.TemporaryDirectory() as tmp:
            sheets = Path(tmp) / "sheets.pdf"
            to_pdf.office_to_pdf(xlsx, sheets)
            count = len(openpyxl.load_workbook(xlsx, read_only=True).sheetnames)
            warnings += attachments.merge(sheets, files.contract_dir(row), kind, count, pdf)
    except Exception as err:  # noqa: BLE001 — 엑셀은 받을 수 있게 두고 PDF 실패만 알림(PDF가 없으면 제출로 안 봄)
        pdf.unlink(missing_ok=True)
        pdf_error = str(err)
    if kind == "start":
        row.start_made_at = datetime.datetime.now()
    else:
        row.done_made_at = datetime.datetime.now()
    db.commit()
    return {"warnings": warnings, "pdf_error": pdf_error, "made": _made(row)}


@router.get("/{contract_id}/docs/{kind}.{ext}")
def download_docs(contract_id: int, kind: Literal["start", "done"], ext: Literal["xlsx", "pdf"], inline: bool = False,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _require(db, user, contract_id)
    name = f"{KIND_LABEL[kind]}.{ext}"
    path = files.out_path(row, name)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"아직 만든 {KIND_LABEL[kind]}가 없습니다.")
    media = "application/pdf" if ext == "pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return FileResponse(path, media_type=media, filename=files.download_name(row, name),
                        content_disposition_type="inline" if inline else "attachment")


@router.get("/{contract_id}/pdf")
def view_contract_pdf(contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _require(db, user, contract_id)
    path = files.out_path(row, "용역계약서.pdf")
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "올린 계약서가 없습니다.")
    return FileResponse(path, media_type="application/pdf", filename=files.download_name(row, "용역계약서.pdf"),
                        content_disposition_type="inline")


def _attach_list(row: ServiceContract, kind: str) -> list[dict]:
    out_dir = files.contract_dir(row)
    return [{"slot": key, "label": label, "files": [attachments.file_info(f) for f in attachments.list_files(out_dir, kind, key)]}
            for key, label, _ in attachments.SLOTS[kind]]


def _require_slot(kind: str, slot: str) -> None:
    if slot not in {key for key, _, _ in attachments.SLOTS[kind]}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 붙임 칸입니다.")


@router.post("/{contract_id}/docs/{kind}/attach/{slot}")
def upload_attachment(contract_id: int, kind: Literal["start", "done"], slot: str, file: UploadFile = File(...),
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """붙임 파일 올리기 — 바로 PDF로 바꿔 둔다(한글은 작업 프로그램이 바꿔서 몇 초~1분). def라 기다리는 동안 다른 요청은 안 막힘."""
    row = _require(db, user, contract_id)
    _require_slot(kind, slot)
    try:
        attachments.add_file(files.contract_dir(row), kind, slot, file.file.read(), file.filename or "")
    except (ValueError, RuntimeError) as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
    return _attach_list(row, kind)


@router.delete("/{contract_id}/docs/{kind}/attach/{slot}/{name}")
def delete_attachment(contract_id: int, kind: Literal["start", "done"], slot: str, name: str,
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _require(db, user, contract_id)
    _require_slot(kind, slot)
    attachments.remove_file(files.contract_dir(row), kind, slot, name)
    return _attach_list(row, kind)


@router.get("/{contract_id}/docs/{kind}/attach/{slot}/{name}")
def view_attachment(contract_id: int, kind: Literal["start", "done"], slot: str, name: str,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _require(db, user, contract_id)
    _require_slot(kind, slot)
    path = attachments.slot_dir(files.contract_dir(row), kind, slot) / Path(name).name
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일이 없습니다.")
    return FileResponse(path, media_type="application/pdf", filename=path.name, content_disposition_type="inline")


@site_router.get("/contract")
def site_contract(site_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """현장 화면 [📑 착수계]·[📑 완수계] — 연결된 계약이 있으면 그것, 없으면 연결할 후보(아직 현장이 없는 계약, 비슷한 이름 순)."""
    site = repo.get_site(db, user.company_id, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "현장을 찾을 수 없습니다.")
    row = db.query(ServiceContract).filter(ServiceContract.site_id == site.id).first()
    if row is not None:
        return {"contract_id": row.id, "title": row.title, "candidates": []}
    free = db.query(ServiceContract).filter(ServiceContract.company_id == user.company_id, ServiceContract.site_id.is_(None)).all()
    scored = sorted(((contract_status.similarity(r.title, site.name), r) for r in free), key=lambda x: (-x[0], -x[1].id))
    return {"contract_id": None, "title": "",
            "candidates": [summary(db, r) | {"score": round(score, 2)} for score, r in scored]}
