"""산안법 용역 계약 ↔ 현장(2026-10-20 형 문서 "산안법 서류자동화 – 보고서 자동화 연동", alembic 0057 contract_site).

- 계약 하나에 현장 여럿(시특법처럼 — 한 용역계약서에 현장별 K2B 기술지도계약서 n개), 현장 하나는 계약 하나.
- 같은 관리번호끼리 자동 연결: 계약 "26-3" ↔ 현장 "26-3"(현장 하나)·"26-3-1"·"26-3-2"…(여럿). [🔗 현장 연결]은 번호가 다를 때만.
- 새 번호 = 계약·현장 통틀어 그해 "YY-N"의 가장 큰 N + 1(지금 26-68 → 26-69). 현장이 여럿이면 "26-69-1"·"26-69-2"….
- 공기 경과(현장 목록·현장 화면·방문 달력 진행 막대)는 연결된 계약의 용역 기간(착수일~완수일, 나라장터·국방조달 용역계약서)이 있으면 그것,
  없으면 현장 공사기간(기술지도계약서).
"""
from __future__ import annotations

import datetime
import re

from sqlalchemy.orm import Session

from core.models_db import Site
from core.models_web import ContractSite, ServiceContract
from server.api.site_label import short_mgmt


def number_match(contract_no: str | None, site_no: str | None) -> bool:
    c, s = short_mgmt(contract_no), short_mgmt(site_no)
    return bool(c) and (s == c or bool(re.fullmatch(re.escape(c) + r"-\d+", s)))


def _suffix(site: Site) -> int:
    m = re.search(r"-(\d+)-(\d+)$", short_mgmt(site.management_no))
    return int(m.group(2)) if m else 0


def sites_of(db: Session, contract_id: int) -> list[Site]:
    """계약의 현장들 — 번호 뒤 "-k" 순(기본 번호 현장이 먼저)."""
    ids = [sid for (sid,) in db.query(ContractSite.site_id).filter(ContractSite.contract_id == contract_id)]
    sites = db.query(Site).filter(Site.id.in_(ids)).all() if ids else []
    return sorted(sites, key=lambda s: (_suffix(s), s.id))


def contract_of(db: Session, site_id: int) -> ServiceContract | None:
    link = db.get(ContractSite, site_id)
    return db.get(ServiceContract, link.contract_id) if link else None


def contract_map(db: Session, site_ids: list[int]) -> dict[int, ServiceContract]:
    """현장 → 연결된 계약(목록 화면용, 한 번에)."""
    if not site_ids:
        return {}
    links = dict(db.query(ContractSite.site_id, ContractSite.contract_id).filter(ContractSite.site_id.in_(site_ids)))
    rows = {c.id: c for c in db.query(ServiceContract).filter(ServiceContract.id.in_(set(links.values())))} if links else {}
    return {sid: rows[cid] for sid, cid in links.items() if cid in rows}


def site_counts(db: Session, contract_ids: list[int]) -> dict[int, int]:
    from sqlalchemy import func

    if not contract_ids:
        return {}
    return dict(db.query(ContractSite.contract_id, func.count(ContractSite.site_id)).filter(ContractSite.contract_id.in_(contract_ids))
                .group_by(ContractSite.contract_id))


def link(db: Session, contract: ServiceContract, site: Site) -> None:
    row = db.get(ContractSite, site.id)
    if row is None:
        db.add(ContractSite(site_id=site.id, contract_id=contract.id, created_at=datetime.datetime.now()))
    else:
        row.contract_id = contract.id


def unlink(db: Session, site_id: int) -> None:
    row = db.get(ContractSite, site_id)
    if row is not None:
        db.delete(row)


def auto_link(db: Session, company_id: int) -> int:
    """같은 관리번호끼리 아직 안 이어진 현장을 계약에 잇는다(번호가 겹치는 계약이 둘 이상이면 건너뜀) → 이은 수. 목록을 열 때·만들 때 부름."""
    contracts = db.query(ServiceContract).filter(ServiceContract.company_id == company_id).all()
    by_no: dict[str, list[ServiceContract]] = {}
    for c in contracts:
        if short_mgmt(c.management_no):
            by_no.setdefault(short_mgmt(c.management_no), []).append(c)
    linked = {sid for (sid,) in db.query(ContractSite.site_id).join(Site, Site.id == ContractSite.site_id).filter(Site.company_id == company_id)}
    n = 0
    for s in db.query(Site).filter(Site.company_id == company_id).all():
        if s.id in linked:
            continue
        no = short_mgmt(s.management_no)
        base = re.sub(r"-\d+$", "", no) if re.fullmatch(r".+-\d+-\d+", no) else no
        for key in dict.fromkeys((no, base)):
            cands = by_no.get(key) or []
            if len(cands) == 1 and number_match(cands[0].management_no, s.management_no):
                link(db, cands[0], s)
                n += 1
                break
    if n:
        db.commit()
    return n


def next_no(db: Session, company_id: int, year: int | None = None) -> str:
    """새 계약·현장 관리번호 "YY-N" — 계약·현장 통틀어 그해 가장 큰 N + 1(형 10/20 "마지막 번호 다음 번호", 26-68 → 26-69)."""
    yy = f"{(year or datetime.date.today().year) % 100:02d}"
    top = 0
    for (no,) in db.query(ServiceContract.management_no).filter(ServiceContract.company_id == company_id).union_all(
            db.query(Site.management_no).filter(Site.company_id == company_id)):
        m = re.fullmatch(rf"{yy}-(\d+)(?:-\d+)?", short_mgmt(no))
        if m:
            top = max(top, int(m.group(1)))
    return f"{yy}-{top + 1}"


def pace_period(contract: ServiceContract | None, site: Site) -> tuple[datetime.date | None, datetime.date | None]:
    """공기 경과 기간 — 계약 용역 기간(착수일·완수일 둘 다 있을 때), 아니면 현장 공사기간(10/20 형)."""
    if contract is not None and contract.start_date and contract.end_date:
        return contract.start_date, contract.end_date
    return site.period_start, site.period_end
