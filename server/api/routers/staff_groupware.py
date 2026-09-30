"""담당요원 ↔ 그룹웨어 직원정보 연결(2026-09-30 사용자 결정: 담당요원은 그룹웨어 직원정보에서 가져오고, 누가 담당요원인지는 여기서 체크).

그룹웨어 직원 목록은 보고서 서버가 직접 받지 않고 **담당요원 탭을 연 브라우저**가 그룹웨어 `/report-shell/employees`(같은 도메인,
그룹웨어 로그인으로 보호 — 로그인한 직원이면 누구나 보는 조직도와 같은 범위)에서 받아 여기로 보낸다. 그래서 nginx·SSH 통로를
바꿀 필요가 없다. 받은 목록을 믿는 수준은 기존 담당요원 추가·수정 API(로그인한 직원 누구나 가능)와 같다.

- `POST /staff-groupware/sync {employees}` — 이어진 요원의 이름·연락처·메일·부서·직위·아이디를 그룹웨어 값으로 맞추고, 아직 안 이어진
  요원은 **이름이 정확히 같은 직원이 한 명뿐일 때** 자동으로 잇는다(기존 현민재·권태형처럼 원래 있던 요원 — 보고서·현장 배정·서명 유지).
  화면에 그릴 목록(직원마다 담당요원 여부·서명 여부, 안 이어진 요원, 지금 로그인한 사람의 요원 id)을 돌려준다.
- `POST /staff-groupware/check {employee, on}` — [담당요원] 체크: 켜면 이어진 요원을 활성화(없으면 새로 만들어 잇기), 끄면 비활성화
  (지우지 않음 — 지난 보고서의 담당요원 이름·서명이 그대로 남도록).
- `POST /staff-groupware/link/{staff_id} {employee}` — 이름이 달라 자동으로 안 이어진 요원을 직접 잇기.
- `GET /staff-groupware/me` — 지금 로그인한 그룹웨어 아이디와 이어진 요원(방문 달력 "나만").
"""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_db import Staff
from core.models_web import StaffContact, StaffGroupwareLink, User
from server.api import repo
from server.api.deps import get_current_user, get_db
from server.api.mailer import valid_email

router = APIRouter(prefix="/staff-groupware", tags=["staff"])


class Employee(BaseModel):
    id: int
    name: str
    department: str = ""
    position: str = ""
    phone: str = ""
    email: str = ""
    username: str = ""
    loginEnabled: bool = False


class SyncIn(BaseModel):
    employees: list[Employee]


class CheckIn(BaseModel):
    employee: Employee
    on: bool


class LinkIn(BaseModel):
    employee: Employee


def gw_username(user: User) -> str:
    """그룹웨어 모드 사용자는 email 칸에 "gw:아이디"로 저장돼 있다(deps._groupware_user)."""
    return user.email[3:] if (user.email or "").startswith("gw:") else ""


def _links(db: Session, company_id: int) -> dict[int, StaffGroupwareLink]:
    rows = db.query(StaffGroupwareLink).filter(StaffGroupwareLink.company_id == company_id).all()
    return {row.staff_id: row for row in rows}


def _apply(db: Session, staff: Staff, link: StaffGroupwareLink, emp: Employee) -> None:
    """그룹웨어 값으로 맞춘다. 그룹웨어 쪽이 비어 있는 연락처·메일은 보고서에 있던 값을 지우지 않는다."""
    name = emp.name.strip()
    if name:
        staff.name = name
    if emp.phone.strip():
        staff.phone = emp.phone.strip()
    email = emp.email.strip()
    if email and valid_email(email):
        contact = db.get(StaffContact, staff.id)
        if contact is None:
            db.add(StaffContact(staff_id=staff.id, email=email))
        else:
            contact.email = email
    link.gw_employee_id = emp.id
    link.gw_username = emp.username.strip()
    link.department = emp.department.strip()
    link.position = emp.position.strip()
    link.synced_at = datetime.datetime.now()


def _link(db: Session, company_id: int, staff: Staff, emp: Employee) -> StaffGroupwareLink:
    taken = (
        db.query(StaffGroupwareLink)
        .filter(StaffGroupwareLink.company_id == company_id, StaffGroupwareLink.gw_employee_id == emp.id)
        .first()
    )
    if taken is not None and taken.staff_id != staff.id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{emp.name} 직원은 이미 다른 담당요원과 이어져 있습니다.")
    link = db.get(StaffGroupwareLink, staff.id)
    if link is None:
        link = StaffGroupwareLink(staff_id=staff.id, company_id=company_id, gw_employee_id=emp.id)
        db.add(link)
    _apply(db, staff, link, emp)
    return link


def _view(db: Session, user: User, employees: list[Employee]) -> dict:
    links = _links(db, user.company_id)
    staff_rows = {s.id: s for s in db.query(Staff).filter(Staff.company_id == user.company_id).all()}
    staff_by_emp = {link.gw_employee_id: staff_rows[sid] for sid, link in links.items() if sid in staff_rows}
    emp_ids = {e.id for e in employees}
    me_name = gw_username(user)
    out_emps = []
    for e in employees:
        s = staff_by_emp.get(e.id)
        out_emps.append({
            **e.model_dump(),
            "staff_id": s.id if s else None,
            "is_staff": bool(s and s.active),
            "has_signature": bool(s and s.signature_path),
            "is_me": bool(me_name and e.username == me_name),
        })
    unlinked = [
        {"id": s.id, "name": s.name, "active": s.active, "has_signature": bool(s.signature_path),
         "gone": s.id in links}  # gone: 이어져 있었는데 그룹웨어 직원정보에서 사라짐
        for s in staff_rows.values()
        if s.id not in links or links[s.id].gw_employee_id not in emp_ids
    ]
    unlinked.sort(key=lambda r: (not r["active"], r["name"]))
    me = next((sid for sid, link in links.items() if me_name and link.gw_username == me_name), None)
    return {"employees": out_emps, "unlinked_staff": unlinked, "me_staff_id": me}


@router.post("/sync")
def sync(body: SyncIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    links = _links(db, user.company_id)
    by_id = {e.id: e for e in body.employees}
    staff_rows = db.query(Staff).filter(Staff.company_id == user.company_id).all()
    linked_emp_ids = {link.gw_employee_id for link in links.values()}
    for staff in staff_rows:
        link = links.get(staff.id)
        if link is not None:
            emp = by_id.get(link.gw_employee_id)
            if emp is not None:
                _apply(db, staff, link, emp)
            continue
        same = [e for e in body.employees if e.name.strip() == staff.name.strip() and e.id not in linked_emp_ids]
        if len(same) == 1:
            _link(db, user.company_id, staff, same[0])
            linked_emp_ids.add(same[0].id)
    db.commit()
    return _view(db, user, body.employees)


@router.post("/check")
def check(body: CheckIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    emp = body.employee
    link = (
        db.query(StaffGroupwareLink)
        .filter(StaffGroupwareLink.company_id == user.company_id, StaffGroupwareLink.gw_employee_id == emp.id)
        .first()
    )
    staff = repo.get_staff(db, user.company_id, link.staff_id) if link else None
    if body.on:
        if staff is None:
            if not emp.name.strip():
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "직원 이름이 비어 있습니다.")
            staff = Staff(company_id=user.company_id, name=emp.name.strip(), phone=emp.phone.strip())
            db.add(staff)
            db.flush()
        _link(db, user.company_id, staff, emp)
        staff.active = True
    elif staff is not None:
        staff.active = False
    db.commit()
    return {"ok": True, "staff_id": staff.id if staff else None}


@router.post("/link/{staff_id}")
def link_staff(staff_id: int, body: LinkIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    staff = repo.get_staff(db, user.company_id, staff_id)
    if staff is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "담당요원을 찾을 수 없습니다.")
    _link(db, user.company_id, staff, body.employee)
    db.commit()
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    name = gw_username(user)
    link = (
        db.query(StaffGroupwareLink)
        .filter(StaffGroupwareLink.company_id == user.company_id, StaffGroupwareLink.gw_username == name)
        .first()
        if name
        else None
    )
    return {"username": name, "staff_id": link.staff_id if link else None}
