"""착수계·완수계 자료실(설정 탭, 2026-10-06) — 갑지 담당 이름, 완수계 회사 서류 6장, 착수계 기술자 명단과 그 서류.

- `GET /contract-docs/library` — 전부 한 번에(설정 탭·현장 서류 창이 같이 씀)
- `PUT /contract-docs/contact {name}` — 갑지 "담당"(기본 유현경)
- `POST /contract-docs/company/{kind}` (파일 + issued_on·valid_until) / `DELETE` — 회사 서류(종류는 build.COMPANY_DOCS)
- `POST /contract-docs/persons`, `PATCH|DELETE /contract-docs/persons/{id}` — 기술자
- `POST|DELETE /contract-docs/persons/{id}/docs/{kind}` — 기술자 서류(build.PERSON_DOCS)
- `PATCH /contract-docs/docs/{doc_id} {issued_on, valid_until}`, `GET /contract-docs/docs/{doc_id}/image`
유효기간: 완납증명서는 비우면 발급일 + 30일(사용자 10/6 "보통 30일"). 지나면 서류 만들 때 경고 — 판정은 doc_status 한 곳.
"""
from __future__ import annotations

import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core import config
from core.models_web import SubmitDoc, TechPerson, User
from server.api.deps import get_current_user, get_db
from server.contract_docs import doc_dates, files
from server.contract_docs.build import COMPANY_DOCS, PERSON_DOCS

router = APIRouter(prefix="/contract-docs", tags=["contract-docs"])

COMPANY_LABELS = dict(COMPANY_DOCS)
PERSON_LABELS = dict(PERSON_DOCS)
# 유효기간이 있는 서류와 "유효기간이 안 적혀 있을 때" 규칙(사용자 10/2·10/6) — 여기 없는 서류(사업자등록증·통장·자격증·교육수료증)는 유효기간 없음
VALID_RULES = {
    "ins_health": ("days", 30), "ins_employ": ("days", 30), "tax_national": ("days", 30), "tax_local": ("days", 30),  # 완납증명서: 발급일 + 30일
    "career": ("months", 3),  # 경력증명서: 발급일 + 3개월
    "sitok_edu": ("months", 60),  # 시특법 정밀안전진단 교육 수료증: 수료일 + 5년(민재형 10/10 — 지나면 알림). 시특법 다른 서류는 유효기간 없음
}


def default_valid_until(kind: str, issued: datetime.date) -> datetime.date | None:
    rule = VALID_RULES.get(kind)
    if rule is None:
        return None
    unit, n = rule
    if unit == "days":
        return issued + datetime.timedelta(days=n)
    month = issued.month - 1 + n
    year, month = issued.year + month // 12, month % 12 + 1
    for day in (issued.day, 30, 29, 28):  # 31일 → 그달 마지막 날
        try:
            return datetime.date(year, month, day)
        except ValueError:
            continue
    return None


def _date(text: str | None) -> datetime.date | None:
    if not text:
        return None
    try:
        return datetime.date.fromisoformat(text.strip()[:10])
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"날짜 형식이 아닙니다: {text}") from err


def _drop_doc(db: Session, row: SubmitDoc | None) -> None:
    """서류 행과 저장소 그림 파일을 같이 지운다."""
    if row is None:
        return
    if row.file:
        Path(row.file).unlink(missing_ok=True)
    db.delete(row)
    db.commit()


def doc_status(doc: SubmitDoc | None, on: datetime.date | None = None) -> str:
    """"" 없음 | ok | expired(유효기간 지남) | nodate(완납증명서인데 발급일·유효기간을 모름 — 경고, 사용자 10/6). on = 기준일(서류 내는 날, 기본 오늘)."""
    if doc is None or not doc.file:
        return ""
    if doc.valid_until and doc.valid_until < (on or datetime.date.today()):
        return "expired"
    if doc.kind in VALID_RULES and not doc.valid_until:
        return "nodate"
    return "ok"


def doc_out(doc: SubmitDoc | None, kind: str, label: str) -> dict:
    return {
        "kind": kind, "label": label, "id": doc.id if doc else None, "status": doc_status(doc), "dated": kind in VALID_RULES,
        "issued_on": doc.issued_on.isoformat() if doc and doc.issued_on else "",
        "valid_until": doc.valid_until.isoformat() if doc and doc.valid_until else "",
        "updated_at": doc.updated_at.strftime("%Y-%m-%d") if doc and doc.updated_at else "",
        "ts": int(doc.updated_at.timestamp()) if doc and doc.updated_at else 0,
    }


def company_docs(db: Session, company_id: int) -> dict[str, SubmitDoc]:
    rows = db.query(SubmitDoc).filter(SubmitDoc.company_id == company_id, SubmitDoc.person_id.is_(None)).all()
    return {r.kind: r for r in rows}


def person_docs(db: Session, person_id: int) -> dict[str, SubmitDoc]:
    return {r.kind: r for r in db.query(SubmitDoc).filter(SubmitDoc.person_id == person_id).all()}


def person_out(db: Session, p: TechPerson) -> dict:
    docs = person_docs(db, p.id)
    return {
        "id": p.id, "name": p.name, "address": p.address, "position": p.position, "qualification": p.qualification, "grade": p.grade,
        "birth_date": p.birth_date.isoformat() if p.birth_date else "", "join_date": p.join_date.isoformat() if p.join_date else "",
        "active": p.active, "docs": [doc_out(docs.get(k), k, label) for k, label in PERSON_DOCS],
    }


def persons(db: Session, company_id: int) -> list[TechPerson]:
    return db.query(TechPerson).filter(TechPerson.company_id == company_id).order_by(TechPerson.name, TechPerson.id).all()


@router.get("/library")
def library(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    docs = company_docs(db, user.company_id)
    return {
        "contact_name": config.get_doc_contact_name(user.company_id),
        "company_docs": [doc_out(docs.get(k), k, label) for k, label in COMPANY_DOCS],
        "persons": [person_out(db, p) for p in persons(db, user.company_id)],
        "dated_kinds": sorted(VALID_RULES),
    }


class ContactIn(BaseModel):
    name: str


@router.put("/contact")
def set_contact(body: ContactIn, user: User = Depends(get_current_user)):
    if not body.name.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "담당자 이름을 적으세요.")
    config.set_doc_contact_name(body.name, user.company_id)
    return {"contact_name": config.get_doc_contact_name(user.company_id)}


def _save_doc(db: Session, user: User, row: SubmitDoc | None, person_id: int | None, kind: str, path,
              issued_on: str, valid_until: str) -> SubmitDoc:
    if row is None:
        row = SubmitDoc(company_id=user.company_id, person_id=person_id, kind=kind)
        db.add(row)
    row.file = str(path)
    _set_dates(row, issued_on, valid_until)
    row.updated_at = datetime.datetime.now()
    row.updated_by = user.display_name or ""
    db.commit()
    return row


def _set_dates(row: SubmitDoc, issued_on: str | None, valid_until: str | None) -> None:
    row.issued_on = _date(issued_on)
    row.valid_until = _date(valid_until)
    if row.valid_until is None and row.issued_on:
        row.valid_until = default_valid_until(row.kind, row.issued_on)


@router.post("/company/{kind}")
def upload_company_doc(kind: str, file: UploadFile = File(...), issued_on: str = Form(""), valid_until: str = Form(""),
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """회사 서류 올리기 — 완납증명서는 날짜를 안 적었으면 증명서에서 발급일·유효기간을 읽어 넣는다(글자 → 못 찾으면 AI, 사용자 10/6).
    못 찾아도 올라감(줄에 "⚠ 발급일을 적어 주세요"). def라 AI를 기다리는 동안 다른 요청은 안 막힘."""
    if kind not in COMPANY_LABELS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 서류 종류입니다.")
    return _upload_dated(db, user, file, kind, COMPANY_LABELS[kind], files.company_doc_path(COMPANY_LABELS[kind]),
                         company_docs(db, user.company_id).get(kind), None, issued_on, valid_until)


def _upload_dated(db: Session, user: User, file: UploadFile, kind: str, label: str, path: Path, row: SubmitDoc | None,
                  person_id: int | None, issued_on: str, valid_until: str) -> dict:
    """서류 그림 저장 + 유효기간이 있는 서류(VALID_RULES)면 날짜를 안 적었을 때 증명서에서 읽음(글자 → 못 찾으면 AI). 못 찾아도 올라감."""
    data = file.file.read()
    jpeg = files.to_jpeg(data, file.filename or "")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(jpeg)
    auto = None
    if kind in VALID_RULES and not issued_on and not valid_until:
        auto = doc_dates.read_dates(data, file.filename or "", jpeg, user.company_id)
        issued_on = auto["issued_on"].isoformat() if auto["issued_on"] else ""
        valid_until = auto["valid_until"].isoformat() if auto["valid_until"] else ""
    row = _save_doc(db, user, row, person_id, kind, path, issued_on, valid_until)
    out = doc_out(row, kind, label)
    if auto is not None:
        out["auto"] = {"source": auto["source"], "error": auto["error"],
                       "issued_found": bool(auto["issued_on"]), "valid_found": bool(auto["valid_until"])}
    return out


@router.delete("/company/{kind}")
def delete_company_doc(kind: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _drop_doc(db, company_docs(db, user.company_id).get(kind))
    return {"ok": True}


class PersonIn(BaseModel):
    name: str | None = None
    address: str | None = None
    birth_date: str | None = None
    position: str | None = None
    join_date: str | None = None
    qualification: str | None = None
    grade: str | None = None
    active: bool | None = None


def _require_person(db: Session, user: User, person_id: int) -> TechPerson:
    p = db.get(TechPerson, person_id)
    if p is None or p.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "기술자를 찾을 수 없습니다.")
    return p


def _apply_person(p: TechPerson, body: PersonIn) -> None:
    fields = body.model_dump(exclude_unset=True)
    for key in ("name", "address", "position", "qualification", "grade"):
        if key in fields:
            setattr(p, key, (fields[key] or "").strip())
    for key in ("birth_date", "join_date"):
        if key in fields:
            setattr(p, key, _date(fields[key]))
    if fields.get("active") is not None:
        p.active = bool(fields["active"])
    if not p.name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "이름을 적으세요.")
    p.updated_at = datetime.datetime.now()


@router.post("/persons")
def create_person(body: PersonIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = TechPerson(company_id=user.company_id, name="")
    _apply_person(p, body)
    db.add(p)
    db.commit()
    return person_out(db, p)


@router.patch("/persons/{person_id}")
def update_person(person_id: int, body: PersonIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _require_person(db, user, person_id)
    _apply_person(p, body)
    db.commit()
    return person_out(db, p)


@router.delete("/persons/{person_id}")
def delete_person(person_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _require_person(db, user, person_id)
    for row in person_docs(db, p.id).values():
        _drop_doc(db, row)
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.post("/persons/{person_id}/docs/{kind}")
def upload_person_doc(person_id: int, kind: str, file: UploadFile = File(...), issued_on: str = Form(""),
                      valid_until: str = Form(""), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """기술자 서류 올리기 — 경력증명서는 발급일을 읽어 넣는다(유효기간 = 발급일 + 3개월, 사용자 10/6). 자격증·교육수료증은 유효기간 없음."""
    p = _require_person(db, user, person_id)
    if kind not in PERSON_LABELS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 서류 종류입니다.")
    return _upload_dated(db, user, file, kind, PERSON_LABELS[kind], files.person_doc_path(p.id, p.name, PERSON_LABELS[kind]),
                         person_docs(db, p.id).get(kind), p.id, issued_on, valid_until)


@router.delete("/persons/{person_id}/docs/{kind}")
def delete_person_doc(person_id: int, kind: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _require_person(db, user, person_id)
    _drop_doc(db, person_docs(db, p.id).get(kind))
    return {"ok": True}


def _require_doc(db: Session, user: User, doc_id: int) -> SubmitDoc:
    row = db.get(SubmitDoc, doc_id)
    if row is None or row.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "서류를 찾을 수 없습니다.")
    return row


class DocDatesIn(BaseModel):
    issued_on: str = ""
    valid_until: str = ""


@router.patch("/docs/{doc_id}")
def update_doc_dates(doc_id: int, body: DocDatesIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _require_doc(db, user, doc_id)
    _set_dates(row, body.issued_on, body.valid_until)
    row.updated_by = user.display_name or ""
    db.commit()
    label = COMPANY_LABELS.get(row.kind) or PERSON_LABELS.get(row.kind, row.kind)
    return doc_out(row, row.kind, label)


@router.get("/docs/{doc_id}/image")
def doc_image(doc_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _require_doc(db, user, doc_id)
    if not row.file or not Path(row.file).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일이 없습니다.")
    return FileResponse(row.file, media_type="image/jpeg")
