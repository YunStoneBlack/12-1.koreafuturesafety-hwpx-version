"""현장 [📑 착수계]·[📑 완수계](2026-10-06) — 용역 계약 정보 저장·계약서 PDF 읽기·서류 만들기·받기.

- `GET /sites/{id}/service-contract` — 창에 필요한 것 전부(계약 값, 기본값, 기술자·회사 서류 상태, 만든 파일)
- `PUT /sites/{id}/service-contract` — 계약 값 저장
- `POST /sites/{id}/service-contract/pdf` — 용역계약서 PDF 올리기 → 읽은 값으로 채움(읽은 칸만 덮어씀), PDF는 현장 폴더에 보관
- `POST /sites/{id}/contract-docs/{start|done}` — 엑셀 만들고 합본 PDF로(LibreOffice + 붙임 파일, 10초 안팎). 경고(빠진 서류·유효기간 지남)는 막지 않고 알림
- `POST|GET|DELETE /sites/{id}/contract-docs/{start|done}/attach/{칸}[/{파일}]` — 붙임 파일(산출내역서·완수내역서·기술지도보고서·완료증명서, attachments.py)
- `GET /sites/{id}/contract-docs/{start|done}.{xlsx|pdf}` — 받기
"""
from __future__ import annotations

import datetime
import tempfile
from pathlib import Path
from typing import Literal

import openpyxl

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core import config
from core.models_web import ServiceContract, TechPerson, User
from server.api import repo
from server.api.deps import get_current_user, get_db
from server.api.routers.contract_library import company_docs, doc_status, person_docs, persons
from server.contract_docs import attachments, build, contract_pdf, files, to_pdf

router = APIRouter(prefix="/sites/{site_id}", tags=["contract-docs"])

KIND_LABEL = {"start": "착수계", "done": "완수계"}
CONTRACT_FIELDS = ("client", "title", "contract_no", "amount", "contract_date", "start_date", "end_date", "settle_amount",
                   "actual_end_date")
DATE_FIELDS = {"contract_date", "start_date", "end_date", "actual_end_date"}


def _require_site(db: Session, user: User, site_id: int):
    site = repo.get_site(db, user.company_id, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "현장을 찾을 수 없습니다.")
    return site


def _contract(db: Session, site) -> ServiceContract:
    row = db.get(ServiceContract, site.id)
    if row is None:
        row = ServiceContract(site_id=site.id, company_id=site.company_id, client="", title="", contract_no="", contract_pdf="",
                              updated_by="")
        db.add(row)
        db.flush()
    return row


def _iso(d) -> str:
    return d.isoformat() if d else ""


def _contract_values(row: ServiceContract) -> build.Contract:
    return build.Contract(**{k: getattr(row, k) for k in CONTRACT_FIELDS})


def _made(db: Session, site, row: ServiceContract) -> dict:
    out = {}
    for kind, label in KIND_LABEL.items():
        at = row.start_made_at if kind == "start" else row.done_made_at
        out[kind] = {
            "at": at.strftime("%Y-%m-%d %H:%M") if at else "",
            "xlsx": files.find_out(db, site, label, ".xlsx") is not None,
            "pdf": files.find_out(db, site, label, ".pdf") is not None,
        }
    return out


def _state(db: Session, user: User, site) -> dict:
    row = _contract(db, site)
    c = _contract_values(row)
    today = datetime.date.today()
    docs = company_docs(db, user.company_id)
    return {
        "contract": {k: (_iso(v) if k in DATE_FIELDS else v) for k, v in vars(c).items()} | {"has_pdf": files.find_out(db, site, "용역계약서", ".pdf") is not None},
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
        "made": _made(db, site, row),
        "attachments": {kind: _attach_state(db, site, kind) for kind in KIND_LABEL},
    }


def _attach_state(db: Session, site, kind: str) -> list[dict]:
    out_dir = files.site_out_dir(db, site)
    return [{"slot": key, "label": label, "files": [attachments.file_info(f) for f in attachments.list_files(out_dir, kind, key)]}
            for key, label, _ in attachments.SLOTS[kind]]


def _person_state(db: Session, p: TechPerson) -> dict:
    docs = person_docs(db, p.id)
    return {"id": p.id, "name": p.name, "qualification": p.qualification, "grade": p.grade,
            "missing": [label for k, label in build.PERSON_DOCS if not doc_status(docs.get(k))],
            "expired": [label for k, label in build.PERSON_DOCS if doc_status(docs.get(k)) == "expired"]}


@router.get("/service-contract")
def get_service_contract(site_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    site = _require_site(db, user, site_id)
    out = _state(db, user, site)
    db.commit()
    return out


class ContractIn(BaseModel):
    client: str | None = None
    title: str | None = None
    contract_no: str | None = None
    amount: int | None = None
    contract_date: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    settle_amount: int | None = None
    actual_end_date: str | None = None


def _apply_contract(row: ServiceContract, fields: dict, user: User) -> None:
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


@router.put("/service-contract")
def put_service_contract(site_id: int, body: ContractIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    site = _require_site(db, user, site_id)
    _apply_contract(_contract(db, site), body.model_dump(exclude_unset=True), user)
    db.commit()
    return _state(db, user, site)


@router.post("/service-contract/pdf")
async def upload_contract_pdf(site_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user),
                              db: Session = Depends(get_db)):
    site = _require_site(db, user, site_id)
    data = await file.read()
    if data[:4] != b"%PDF":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "용역계약서 PDF 파일을 올리세요.")
    dest = files.site_out_path(db, site, "용역계약서", ".pdf")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    try:
        parsed = contract_pdf.parse_pdf(dest)
    except Exception as err:  # noqa: BLE001 — 글자가 없는 스캔 PDF 등
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "계약서에서 글자를 읽지 못했습니다 — 칸을 직접 채우세요.") from err
    found = {k: (_iso(v) if k in DATE_FIELDS else v) for k, v in parsed.items() if v}
    row = _contract(db, site)
    _apply_contract(row, found, user)
    row.contract_pdf = str(dest)
    db.commit()
    missing = [k for k in parsed if not parsed[k]]
    return _state(db, user, site) | {"read": sorted(found), "unread": missing}


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


@router.post("/contract-docs/{kind}")
def make_docs(site_id: int, kind: Literal["start", "done"], body: MakeIn, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    site = _require_site(db, user, site_id)
    row = _contract(db, site)
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
    xlsx = files.site_out_path(db, site, label, ".xlsx")
    pdf = files.site_out_path(db, site, label, ".pdf")
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
            to_pdf.xlsx_to_pdf(xlsx, sheets)
            count = len(openpyxl.load_workbook(xlsx, read_only=True).sheetnames)
            warnings += attachments.merge(sheets, files.site_out_dir(db, site), kind, count, pdf)
    except Exception as err:  # noqa: BLE001 — 엑셀은 받을 수 있게 두고 PDF 실패만 알림
        pdf.unlink(missing_ok=True)
        pdf_error = str(err)
    if kind == "start":
        row.start_made_at = datetime.datetime.now()
    else:
        row.done_made_at = datetime.datetime.now()
    db.commit()
    return {"warnings": warnings, "pdf_error": pdf_error, "made": _made(db, site, row)}


@router.get("/contract-docs/{kind}.{ext}")
def download_docs(site_id: int, kind: Literal["start", "done"], ext: Literal["xlsx", "pdf"], inline: bool = False,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    site = _require_site(db, user, site_id)
    path = files.find_out(db, site, KIND_LABEL[kind], f".{ext}")
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"아직 만든 {KIND_LABEL[kind]}가 없습니다.")
    media = "application/pdf" if ext == "pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return FileResponse(path, media_type=media, filename=path.name, content_disposition_type="inline" if inline else "attachment")


def _require_slot(kind: str, slot: str) -> None:
    if slot not in {key for key, _, _ in attachments.SLOTS[kind]}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 붙임 칸입니다.")


@router.post("/contract-docs/{kind}/attach/{slot}")
def upload_attachment(site_id: int, kind: Literal["start", "done"], slot: str, file: UploadFile = File(...),
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """붙임 파일 올리기 — 바로 PDF로 바꿔 둔다(한글은 작업 프로그램이 바꿔서 몇 초~1분). def라 기다리는 동안 다른 요청은 안 막힘."""
    site = _require_site(db, user, site_id)
    _require_slot(kind, slot)
    try:
        attachments.add_file(files.site_out_dir(db, site), kind, slot, file.file.read(), file.filename or "")
    except (ValueError, RuntimeError) as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
    return _attach_state(db, site, kind)


@router.delete("/contract-docs/{kind}/attach/{slot}/{name}")
def delete_attachment(site_id: int, kind: Literal["start", "done"], slot: str, name: str,
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    site = _require_site(db, user, site_id)
    _require_slot(kind, slot)
    attachments.remove_file(files.site_out_dir(db, site), kind, slot, name)
    return _attach_state(db, site, kind)


@router.get("/contract-docs/{kind}/attach/{slot}/{name}")
def view_attachment(site_id: int, kind: Literal["start", "done"], slot: str, name: str,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    site = _require_site(db, user, site_id)
    _require_slot(kind, slot)
    path = attachments.slot_dir(files.site_out_dir(db, site), kind, slot) / Path(name).name
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일이 없습니다.")
    return FileResponse(path, media_type="application/pdf", filename=path.name, content_disposition_type="inline")
