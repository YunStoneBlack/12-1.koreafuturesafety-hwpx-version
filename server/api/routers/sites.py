from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.models_web import User
from server.api import repo
from server.api.deps import get_current_user, get_db
from server.schemas.site import SiteIn, SiteOut

router = APIRouter(prefix="/sites", tags=["sites"])


@router.get("", response_model=list[SiteOut])
def list_sites(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return repo.list_sites(db, user.company_id)


@router.post("", response_model=SiteOut)
def create_site(body: SiteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return repo.create_site(db, user.company_id, **body.model_dump())


@router.get("/{site_id}", response_model=SiteOut)
def get_site(site_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    site = repo.get_site(db, user.company_id, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "현장을 찾을 수 없습니다.")
    return site


@router.patch("/{site_id}", response_model=SiteOut)
def update_site(
    site_id: int, body: SiteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    site = repo.update_site(db, user.company_id, site_id, **body.model_dump())
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "현장을 찾을 수 없습니다.")
    return site
