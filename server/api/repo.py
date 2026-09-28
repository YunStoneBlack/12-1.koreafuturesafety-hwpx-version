"""모든 DB 조회는 이 모듈을 거친다 — 라우터에서 session.query(...)를 직접 쓰지 않는 것이
Sub-phase 33 설계의 핵심 안전장치다. company_id 필터를 어딘가에서 한 번이라도 빠뜨리면
다른 회사 데이터가 그대로 보이는 사고가 나는데, 그 필터를 매 호출부마다 손으로 반복하는
대신 이 한 곳에 모아두면 실수할 자리 자체가 줄어든다.

Report와 그 자식 테이블들은 company_id 컬럼이 없다 — Site를 거쳐 간접적으로 격리한다
(Report.site_id -> Site.company_id). 지금 규모에서는 이 정도 join으로 충분하다."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.models_db import Report, Site, Staff
from core.models_web import ReportJob


def list_sites(db: Session, company_id: int) -> list[Site]:
    return db.query(Site).filter(Site.company_id == company_id).order_by(Site.created_at.desc()).all()


def get_site(db: Session, company_id: int, site_id: int) -> Site | None:
    return db.query(Site).filter(Site.company_id == company_id, Site.id == site_id).first()


def create_site(db: Session, company_id: int, **fields) -> Site:
    site = Site(company_id=company_id, **fields)
    db.add(site)
    db.commit()
    db.refresh(site)
    return site


def update_site(db: Session, company_id: int, site_id: int, **fields) -> Site | None:
    site = get_site(db, company_id, site_id)
    if site is None:
        return None
    for key, value in fields.items():
        setattr(site, key, value)
    db.commit()
    db.refresh(site)
    return site


def list_staff(db: Session, company_id: int) -> list[Staff]:
    return db.query(Staff).filter(Staff.company_id == company_id, Staff.active.is_(True)).all()


def get_report(db: Session, company_id: int, report_id: int) -> Report | None:
    return (
        db.query(Report)
        .join(Site, Report.site_id == Site.id)
        .filter(Site.company_id == company_id, Report.id == report_id)
        .first()
    )


def create_report(db: Session, company_id: int, site_id: int, **fields) -> Report | None:
    site = get_site(db, company_id, site_id)
    if site is None:
        return None
    visit_no = fields.pop("visit_no", None)
    if visit_no is None:
        # site.reports(관계 컬렉션)는 같은 세션 안에서 캐시되어 있을 수 있어(특히
        # expire_on_commit=False라 커밋 후에도 안 갱신됨) 새로 추가된 보고서를 못 볼 수
        # 있다 — 그래서 관계 대신 매번 새로 집계 쿼리를 날린다.
        max_visit_no = db.query(func.max(Report.visit_no)).filter(Report.site_id == site_id).scalar()
        visit_no = (max_visit_no or 0) + 1
    report = Report(site_id=site_id, visit_no=visit_no, **fields)
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def create_render_job(db: Session, company_id: int, report_id: int) -> ReportJob | None:
    if get_report(db, company_id, report_id) is None:
        return None
    job = ReportJob(report_id=report_id, status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, company_id: int, job_id: int) -> ReportJob | None:
    job = db.get(ReportJob, job_id)
    if job is None:
        return None
    if get_report(db, company_id, job.report_id) is None:
        return None  # 다른 회사의 job — 못 본 것처럼 취급
    return job
