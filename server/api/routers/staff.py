"""담당요원 목록 — 지금은 조회만(보고서 담당요원 선택 드롭다운용). 등록/서명 관리는
데스크톱의 '담당요원 관리' 화면에 해당하는 웹판 화면이 아직 없어서 다음 단계에서 추가한다."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.models_web import User
from server.api import repo
from server.api.deps import get_current_user, get_db
from server.schemas.staff import StaffOut

router = APIRouter(prefix="/staff", tags=["staff"])


@router.get("", response_model=list[StaffOut])
def list_staff(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return repo.list_staff(db, user.company_id)
