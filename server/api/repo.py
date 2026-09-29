"""모든 DB 조회는 이 모듈을 거친다 — 라우터에서 session.query(...)를 직접 쓰지 않는 것이
Sub-phase 33 설계의 핵심 안전장치다. company_id 필터를 어딘가에서 한 번이라도 빠뜨리면
다른 회사 데이터가 그대로 보이는 사고가 나는데, 그 필터를 매 호출부마다 손으로 반복하는
대신 이 한 곳에 모아두면 실수할 자리 자체가 줄어든다.

Report와 그 자식 테이블들은 company_id 컬럼이 없다 — Site를 거쳐 간접적으로 격리한다
(Report.site_id -> Site.company_id). 지금 규모에서는 이 정도 join으로 충분하다."""

from __future__ import annotations

from sqlalchemy import func, inspect
from sqlalchemy.orm import Session

from core.models_db import Report, Site, Staff
from core.models_web import ReportJob

# 전경사진(OverviewPhoto)/점검사진(InspectionPhoto)은 (report_id, slot, photo_path) 뿐인
# 완전히 같은 모양이라, 슬롯 사진 공용 헬퍼 하나로 둘 다 처리한다 — 데스크톱(models_db.py)도
# "표4/5로 독립된 별개 표"라서 모델은 둘로 나눴지만, 다루는 로직 자체는 항상 같이 다닌다.


# 고객사 메일 보낸 기록(report_mail) — server/api/routers/report_mail.py·reports.py(목록의 "✓ 전송")가 같이 쓴다
_table_ready = False


def mail_table_ready(db: Session) -> bool:
    """report_mail 표가 DB에 있나(alembic 0004 적용 전이면 False) — 새 코드가 먼저 돌아도 현장 화면 목록이 깨지지 않게.
    한 번 있으면 계속 있으므로 True는 기억해 둔다."""
    global _table_ready
    if not _table_ready:
        _table_ready = inspect(db.get_bind()).has_table("report_mail")
    return _table_ready


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


def get_staff(db: Session, company_id: int, staff_id: int) -> Staff | None:
    return db.query(Staff).filter(Staff.company_id == company_id, Staff.id == staff_id).first()


def list_reports_for_site(db: Session, company_id: int, site_id: int) -> list[Report]:
    site = get_site(db, company_id, site_id)
    if site is None:
        return []
    return db.query(Report).filter(Report.site_id == site_id).order_by(Report.visit_no).all()


def get_report(db: Session, company_id: int, report_id: int) -> Report | None:
    return (
        db.query(Report)
        .join(Site, Report.site_id == Site.id)
        .filter(Site.company_id == company_id, Report.id == report_id)
        .first()
    )


def update_report(db: Session, company_id: int, report_id: int, **fields) -> Report | None:
    report = get_report(db, company_id, report_id)
    if report is None:
        return None
    for key, value in fields.items():
        setattr(report, key, value)
    db.commit()
    db.refresh(report)
    return report


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


def get_slot_row(db: Session, model_cls, report_id: int, slot: int):
    """(report_id, slot) 모양의 슬롯형 테이블 공용 조회 — PreviousFinding처럼 사진 외에
    텍스트 필드도 같이 갖는 모델에 쓴다(순수 사진뿐인 Overview/InspectionPhoto는 아래
    get_photo_slot 계열을 계속 쓴다, 이미 검증된 걸 안 건드리려고)."""
    return db.query(model_cls).filter(model_cls.report_id == report_id, model_cls.slot == slot).first()


def upsert_slot_row(db: Session, model_cls, report_id: int, slot: int, **fields):
    row = get_slot_row(db, model_cls, report_id, slot)
    if row is None:
        row = model_cls(report_id=report_id, slot=slot, **fields)
        db.add(row)
    else:
        for key, value in fields.items():
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def get_photo_slot(db: Session, model_cls, report_id: int, slot: int):
    return db.query(model_cls).filter(model_cls.report_id == report_id, model_cls.slot == slot).first()


def upsert_photo_slot(db: Session, model_cls, report_id: int, slot: int, photo_path: str):
    row = get_photo_slot(db, model_cls, report_id, slot)
    if row is None:
        row = model_cls(report_id=report_id, slot=slot, photo_path=photo_path)
        db.add(row)
    else:
        row.photo_path = photo_path
    db.commit()
    db.refresh(row)
    return row


def delete_photo_slot(db: Session, model_cls, report_id: int, slot: int) -> None:
    row = get_photo_slot(db, model_cls, report_id, slot)
    if row is not None:
        db.delete(row)
        db.commit()


def get_process_entry(db: Session, entry_model, report_id: int, slot: int):
    """7번(현재 진행공정)/9번(향후 진행공정) 공용 — CurrentProcessEntry/ProcessHazardEntry는
    완전히 같은 모양(process_name + items 관계)이라 모델 클래스만 바꿔서 재사용한다."""
    return db.query(entry_model).filter(entry_model.report_id == report_id, entry_model.slot == slot).first()


def upsert_process_entry(
    db: Session, entry_model, item_model, report_id: int, slot: int, process_name: str, items: list[dict]
):
    entry = get_process_entry(db, entry_model, report_id, slot)
    if entry is None:
        entry = entry_model(report_id=report_id, slot=slot, process_name=process_name)
        db.add(entry)
        db.flush()
    else:
        entry.process_name = process_name
    # items는 매번 전체 교체 — cascade="all, delete-orphan"이 이전 항목을 정리해준다
    # (데스크톱도 저장할 때마다 항목을 지우고 다시 만드는 같은 방식).
    entry.items = [
        item_model(order=i + 1, hazard=it.get("hazard", ""), prevention=it.get("prevention", ""), risk_level=it.get("risk_level", ""))
        for i, it in enumerate(items)
    ]
    db.commit()
    db.refresh(entry)
    return entry


def get_job(db: Session, company_id: int, job_id: int) -> ReportJob | None:
    job = db.get(ReportJob, job_id)
    if job is None:
        return None
    if get_report(db, company_id, job.report_id) is None:
        return None  # 다른 회사의 job — 못 본 것처럼 취급
    return job
