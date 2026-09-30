"""현장 연락처 — 현장책임자(현장 정보 그대로) + 발주처·감리단(site_contact, 2026-09-30). 고객사 전송 창의 받는 사람 체크 항목과
[고치기]·[발주처로 저장]·[감리단으로 저장], 현장 등록·수정 화면의 발주처·감리단 칸이 쓴다.

- `GET /sites/{id}/contacts`, `PATCH /sites/{id}/contacts {manager_name?, manager_email?, owner_name?, owner_email?, ...}`
- 메일 칸은 쉼표로 여러 개(현장책임자는 한 개). 저장할 때 ", "로 정리한다.
- 현장책임자 이름·메일은 보고서 표지에 들어가므로 바뀌면 그 현장 보고서를 "수정됨"으로 기록한다(PATCH /sites/{id}와 같은 규칙 —
  PDF를 다시 만들어야 보낼 수 있다). 발주처·감리단은 표지에 없어서 PDF에 영향 없음 — 이 주소(/contacts)는 edit_tracking이 자동으로
  잡지 않으므로(현장 수정 규칙은 `/api/sites/{id}`로 끝나는 주소만) 현장책임자일 때만 여기서 직접 기록한다.
- 빠진 옛 주소는 retired_emails에 모아 "지난번 받는 사람" 자동 채움에서 뺀다(report_mail.mail_info).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SiteContact, User
from server.api import mailer, repo
from server.api.deps import get_current_user, get_db
from server.api.edit_tracking import mark_edited

router = APIRouter(prefix="/sites/{site_id}/contacts", tags=["sites"])


class ContactsIn(BaseModel):
    manager_name: str | None = None
    manager_email: str | None = None
    owner_name: str | None = None
    owner_email: str | None = None
    supervisor_name: str | None = None
    supervisor_email: str | None = None


def split_emails(value: str) -> list[str]:
    out: list[str] = []
    for a in (value or "").replace(";", ",").split(","):
        a = a.strip()
        if a and a.lower() not in (o.lower() for o in out):
            out.append(a)
    return out


def _clean_emails(value: str, label: str, single: bool = False) -> str:
    addrs = split_emails(value)
    bad = [a for a in addrs if not mailer.valid_email(a)]
    if bad:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{label} 메일 주소를 확인하세요: {', '.join(bad)}")
    if single and len(addrs) > 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{label} 메일은 한 개만 넣을 수 있습니다.")
    return ", ".join(addrs)


def contacts_of(db: Session, site) -> dict:
    row = db.get(SiteContact, site.id)
    return {
        "manager_name": site.manager_name or "",
        "manager_email": (site.manager_email or "").strip(),
        "owner_name": row.owner_name if row else "",
        "owner_email": row.owner_email if row else "",
        "supervisor_name": row.supervisor_name if row else "",
        "supervisor_email": row.supervisor_email if row else "",
    }


ROLE_EMAIL_KEYS = (("manager", "manager_email"), ("owner", "owner_email"), ("supervisor", "supervisor_email"))


def _parse_retired(text: str) -> dict[str, str]:
    """"역할:주소, …" → {주소(소문자): 역할}. 역할을 같이 적어 두는 이유: 주소가 바뀐 뒤 첫 전송에서, 지난번에 옛 주소로 받은
    곳(예: 발주처)은 새 주소도 체크된 채로 보여 주려고."""
    out = {}
    for item in split_emails(text):
        role, _, addr = item.rpartition(":")
        out[addr.strip().lower()] = role.strip()
    return out


def retired_emails(db: Session, site_id: int) -> dict[str, str]:
    row = db.get(SiteContact, site_id)
    return _parse_retired(row.retired_emails) if row else {}


def _require_site(db: Session, user: User, site_id: int):
    site = repo.get_site(db, user.company_id, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "현장을 찾을 수 없습니다.")
    return site


@router.get("")
def get_contacts(site_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return contacts_of(db, _require_site(db, user, site_id))


@router.patch("")
def update_contacts(site_id: int, body: ContactsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    site = _require_site(db, user, site_id)
    fields = body.model_dump(exclude_unset=True)
    before = contacts_of(db, site)
    row = db.get(SiteContact, site.id)
    if row is None:
        row = SiteContact(site_id=site.id, owner_name="", owner_email="", supervisor_name="", supervisor_email="", retired_emails="")
        db.add(row)

    manager_changed = False
    if "manager_name" in fields:
        name = (fields["manager_name"] or "").strip()
        manager_changed |= name != (site.manager_name or "")
        site.manager_name = name
    if "manager_email" in fields:
        email = _clean_emails(fields["manager_email"] or "", "현장책임자", single=True)
        manager_changed |= email != (site.manager_email or "").strip()
        site.manager_email = email
    for role, label in (("owner", "발주처"), ("supervisor", "감리단")):
        if f"{role}_name" in fields:
            setattr(row, f"{role}_name", (fields[f"{role}_name"] or "").strip())
        if f"{role}_email" in fields:
            setattr(row, f"{role}_email", _clean_emails(fields[f"{role}_email"] or "", label))

    db.flush()
    after = contacts_of(db, site)
    now_all = {a.lower() for _, k in ROLE_EMAIL_KEYS for a in split_emails(after[k])}
    retired = _parse_retired(row.retired_emails)
    for role, k in ROLE_EMAIL_KEYS:
        for a in split_emails(before[k]):
            retired[a.lower()] = role
    # 다시 쓰이는 주소는 목록에서 뺀다
    row.retired_emails = ", ".join(f"{role}:{a}" for a, role in retired.items() if a not in now_all)
    db.commit()
    if manager_changed:
        mark_edited([], site.id)  # 표지(현장책임자)가 바뀜 → 이 현장 PDF는 다시 만들어야
    return contacts_of(db, site) | {"manager_changed": manager_changed}
