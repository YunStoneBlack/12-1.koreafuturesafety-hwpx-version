"""시특법 시설물·점검 용역 계약(2026-10-10 2단계) — 보고서 자동화 · 시특법 화면(sitok.html 목록, sitok-facility.html 등록·고치기).

- `GET    /sitok/facilities` — 목록(시설물 + 가장 최근 계약).
- `POST   /sitok/read` — PDF 하나 올리기(kind = ledger 관리대장 | contract 계약서) → AI로 읽은 칸 + 임시 표(token). 읽기에 실패해도 token은 준다(손으로 채움).
- `POST   /sitok/facilities` — 시설물 + 첫 계약 저장(ledger_token·contract_token이 있으면 PDF를 시설물 폴더로 옮김).
- `GET/PATCH/DELETE /sitok/facilities/{id}` — 보기·고치기·지우기(지우기는 현장 삭제와 같은 회사 삭제 비밀번호).
- `POST   /sitok/facilities/{id}/contracts`, `PATCH/DELETE /sitok/contracts/{id}` — 계약 더하기(다음 해 등)·고치기·지우기.
- `GET    /sitok/files/ledger/{facility_id}`, `/sitok/files/contract/{contract_id}` — 올린 PDF 보기.
- `POST   /sitok/facilities/{id}/contract-type` {contract_type: 장기|1회성|종료} — 시설물 목록함 구분(묶인 동 같이, 10/13 민재형).
  목록 번호표(mgmt_no "26-4", 새 등록 때 자동 next_mgmt_no)·담당자 📞·최근 열람순(sitok_view — 시설물·회차 화면을 열면 mark_view)은 0042.
- 회차 ↔ 계약(10/13 사용자): 회차는 그 반기를 계약기간이 덮는 계약에 붙음(contract_for — 이 동 먼저, 묶인 동이면 묶음 계약),
  계약을 추가하면 계약 없이 만든 회차 중 덮이는 것에 붙임(attach_contract), 장기·지속 시설물은 마지막 계약 끝나기 60일 전부터 알림(renew_info).
값의 뜻·기본값(민간 = 독자수행 100%·수의계약·건축, 템플릿 2종/3종일반/3종학교)은 core/models_web.py SitokFacility·SitokContract 설명.
"""

from __future__ import annotations

import datetime
import re
import secrets
import shutil
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core import config
from core.db import DATA_DIR
from core.models_web import SitokContract, SitokFacility, SitokView, User, SitokReport
from server.api import storage
from server.api.deps import get_current_user, get_db
from server.api.security import verify_password
from server.sitok import reader

router = APIRouter(prefix="/sitok", tags=["sitok"])
ROOT = DATA_DIR / "_시특법"
UPLOAD_DIR = storage.SYSTEM_DIR / "시특법_올림"  # 등록 전 임시(하루 지나면 지움)
TEMPLATES = ("2종", "3종일반", "3종학교")
SECTORS = ("민간", "관급")
HALVES = ("상반기", "하반기", "연간")
JOINT_TYPES = ("독자수행", "공동이행", "분담이행")  # 점검진단실적 제출 사이트와 같은 선택지
BID_METHODS = ("일반경쟁", "제한경쟁", "지명경쟁", "수의계약", "기타")
FIELDS = ("교량 및 터널", "건축", "항만", "수리시설")
# 시설물 목록함 구분(10/13 민재형): 장기·지속계약(연락·일정 관리 대상) / 1회성·입찰계약 / 지속계약 종료 — 서로 옮길 수 있음
CONTRACT_TYPES = ("장기", "1회성", "종료")
# 시설물 카드 뱃지(10/15 민재형 문서번호 일치화): 분야(민간·관급) + 관급 종류 — 목록에서 뱃지별 개수·거르기
BADGE_FIELDS = ("건축", "토목", "건축·토목")
BADGE_KINDS = ("학교", "일반", "내진")
FAC_FIELDS = ("fms_no", "name", "template", "kind", "use_type", "main_use", "address", "owner_name", "owner_type", "owner_phone",
              "completion_date", "structure", "floors_above", "floors_below", "floors_roof", "max_height", "total_area", "building_area", "memo", "legal",
              "mgmt_no", "contact_name", "contact_phone", "contract_type", "sector", "badge_field", "badge_kind")
CON_FIELDS = ("sector", "title", "contract_no", "contract_date", "start_date", "end_date", "halves", "first_half_end", "second_half_start",
              "amount", "rep_name", "joint_type", "joint_pct", "bid_method", "field")
DATES = {"completion_date", "contract_date", "start_date", "end_date", "first_half_end", "second_half_start"}


class FacilityIn(BaseModel):
    fms_no: str | None = None
    name: str | None = None
    template: str | None = None
    kind: str | None = None
    use_type: str | None = None
    main_use: str | None = None
    address: str | None = None
    owner_name: str | None = None
    owner_type: str | None = None
    owner_phone: str | None = None
    completion_date: datetime.date | None = None
    structure: str | None = None
    floors_above: int | None = None
    floors_below: int | None = None
    floors_roof: int | None = None
    max_height: float | None = None
    total_area: float | None = None
    building_area: float | None = None
    memo: str | None = None
    legal: bool | None = None  # 법정(1·2·3종) 시설물 — False = 자체 점검(관리대장 없음, 결과표 종별 "해당없음")
    mgmt_no: str | None = None  # 목록 번호표 "민간-3"·"관급-1"(10/15, 예전 "26-4") — 비우고 새 등록하면 구분별 다음 번호
    sector: str | None = None  # 시설물 카드 구분 민간 / 관급(번호 앞 글자)
    badge_field: str | None = None  # 건축 / 토목 / 건축·토목
    badge_kind: str | None = None  # 관급 종류 학교 / 일반 / 내진(민간은 빈칸)
    contact_name: str | None = None  # 담당자(관리소장 등) — 목록 📞
    contact_phone: str | None = None
    contract_type: str | None = None  # 장기 / 1회성 / 종료
    base_wall: float | None = None  # 면적률 기준 면적(㎡) — ledger JSON에 보관(10/11)
    base_slab: float | None = None
    land_area: float | None = None  # 대지면적(㎡)·건폐율(%)·용적율(%) — SafetyMan 건물개요(10/15 민재형), ledger JSON에 보관
    coverage_ratio: float | None = None
    floor_area_ratio: float | None = None


class ContractIn(BaseModel):
    sector: str | None = None
    title: str | None = None
    contract_no: str | None = None
    contract_date: datetime.date | None = None
    start_date: datetime.date | None = None
    end_date: datetime.date | None = None
    halves: str | None = None
    first_half_end: datetime.date | None = None
    second_half_start: datetime.date | None = None
    amount: int | None = None
    rep_name: str | None = None
    joint_type: str | None = None
    joint_pct: int | None = None
    bid_method: str | None = None
    field: str | None = None
    rounds: list[dict] | None = None  # 회차 줄 [{year, half, kind, amount}] — 계약서를 읽으면 같이(회차 종류 자동, 0043)
    contract_token: str | None = None


class CreateIn(BaseModel):
    facility: FacilityIn
    contract: ContractIn | None = None
    ledger_token: str | None = None
    ledger_extra: dict | None = None  # 관리대장에서 읽은 나머지 값(시설물분류 등)


# ---------- 파일 ----------

def _facility_dir(f: SitokFacility) -> Path:
    return ROOT / f"{storage._clean(f.name)[:30] or '시설물'}_{f.id}"


def _token_path(token: str | None) -> Path | None:
    if not token or not token.isalnum():
        return None
    p = UPLOAD_DIR / f"{token}.pdf"
    return p if p.exists() else None


def _clean_uploads() -> None:
    if not UPLOAD_DIR.exists():
        return
    old = datetime.datetime.now().timestamp() - 86400
    for p in UPLOAD_DIR.glob("*.*"):  # PDF·이전 회차 hwpx(10/12)
        if p.stat().st_mtime < old:
            p.unlink(missing_ok=True)


def _take(token: str | None, dest: Path) -> str:
    """임시로 올린 PDF를 시설물 폴더로 옮기고 저장할 경로(문자열)를 준다. 없으면 ""."""
    src = _token_path(token)
    if src is None:
        return ""
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), dest)
    return str(dest)


# ---------- 값 다듬기 ----------

def _iso(v):
    return v.isoformat() if isinstance(v, (datetime.date, datetime.datetime)) else v


def _check(field: str, value, allowed) -> None:
    if value is not None and value not in allowed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{field}은(는) {'·'.join(allowed)} 중 하나입니다.")


LEDGER_KEYS = ("base_wall", "base_slab", "land_area", "coverage_ratio", "floor_area_ratio")  # 표 열 없이 ledger JSON에 두는 시설물 칸
BASE_WALL, BASE_SLAB = 24.5, 49.0  # 기준 면적 기본값 — 벽 한 면 = 기둥간격 7m × 층고 3.5m, 슬래브 한 칸 = 7m × 7m


def base_areas(f: SitokFacility) -> tuple[float, float]:
    """면적률 기준 면적(벽, 슬래브) — 시설물마다 한 번 정해 계속 씀(인수인계 10/10, 사용자: 현장에서 일일이 못 잼). 안 넣었으면 기본값."""
    led = f.ledger or {}
    return float(led.get("base_wall") or BASE_WALL), float(led.get("base_slab") or BASE_SLAB)


def _apply_facility(row: SitokFacility, body: FacilityIn) -> None:
    data = body.model_dump(exclude_unset=True)
    _check("보고서 틀", data.get("template"), TEMPLATES)
    _check("계약 구분", data.get("contract_type"), CONTRACT_TYPES)
    _check("민간·관급", data.get("sector"), SECTORS)
    _check("분야", data.get("badge_field"), BADGE_FIELDS)
    if data.get("badge_kind"):
        _check("관급 종류", data.get("badge_kind"), BADGE_KINDS)
    bases = {k: data.pop(k) for k in LEDGER_KEYS if k in data}
    if bases:
        row.ledger = {**(row.ledger or {}), **bases}
    for k, v in data.items():
        setattr(row, k, v.strip() if isinstance(v, str) else v)


def _apply_contract(row: SitokContract, body: ContractIn) -> None:
    data = body.model_dump(exclude_unset=True, exclude={"contract_token"})
    _check("계약 구분", data.get("sector"), SECTORS)
    _check("반기", data.get("halves"), HALVES)
    _check("공동수급", data.get("joint_type"), JOINT_TYPES)
    _check("입찰방식", data.get("bid_method"), BID_METHODS)
    _check("수행분야", data.get("field"), FIELDS)
    if "rounds" in data:
        from server.sitok import civil
        data["rounds"] = civil.normalize_rounds(data["rounds"]) or None
    for k, v in data.items():
        setattr(row, k, v.strip() if isinstance(v, str) else v)


def kind_known(db: Session, c: SitokContract | None, year: int, half: str) -> str | None:
    """그 반기 회차 종류(정기/정밀) — ① 보고서 쪽 계약의 회차 줄 ② 그 계약을 만든 서류 자동화 계약의 회차 줄 ③ 계약건명에 정밀·정기 중 하나만 있으면 그것(10/14 형 피드백 —
    스캔 계약서라 회차 줄을 못 읽은 꿈에블리스나인 "정기(정밀)"는 둘 다 있어 못 정함) → 모르면 None(회차 만들기가 물음)."""
    from core.models_web import SitokDocContract
    from server.sitok import civil

    if c is None:
        return None
    rounds = c.rounds or []
    unit = next((r for r in rounds if r.get("open_ended")), None)
    k = civil.kind_for(rounds, unit, unit is not None, year, half)
    if k is None:
        doc = db.query(SitokDocContract).filter(SitokDocContract.report_contract_id == c.id).first()
        if doc is not None:
            k = civil.kind_for(doc.rounds, doc.unit, doc.open_ended, year, half)
    if k is None:
        t = (c.title or "").replace(" ", "")
        has_pre, has_reg = "정밀" in t, "정기" in t
        k = "정밀" if has_pre and not has_reg else "정기" if has_reg and not has_pre else None
    return k


def kind_for(db: Session, c: SitokContract | None, year: int, half: str) -> str:
    """kind_known, 모르면 정기(목록 기본값 표시용 — 회차 만들기는 create_report가 428로 물음)."""
    return kind_known(db, c, year, half) or "정기"


def _contract_out(c: SitokContract) -> dict:
    return {"id": c.id, **{k: _iso(getattr(c, k)) for k in CON_FIELDS}, "rounds": c.rounds or [],
            "has_pdf": bool(c.contract_pdf and Path(c.contract_pdf).exists()),
            "created_at": c.created_at.strftime("%Y-%m-%d") if c.created_at else ""}


def register_path(f: SitokFacility) -> Path:
    """건축물대장 PDF — 시설물 폴더에 하나(시설물 현황 AI·1.2.8 초안이 같이 씀). 10/14 시설물 정보·서류 칸에서 올림."""
    return _facility_dir(f) / "건축물대장.pdf"


def _facility_out(db: Session, f: SitokFacility, with_contracts: bool = True) -> dict:
    contracts = (db.query(SitokContract).filter(SitokContract.facility_id == f.id)
                 .order_by(SitokContract.start_date.desc().nullslast(), SitokContract.id.desc()).all())
    out = {"id": f.id, **{k: _iso(getattr(f, k)) for k in FAC_FIELDS}, "ledger": f.ledger or {},
           "has_ledger_pdf": bool(f.ledger_pdf and Path(f.ledger_pdf).exists()), "has_register": register_path(f).exists(),
           **{k: (f.ledger or {}).get(k) for k in LEDGER_KEYS},
           "latest": _contract_out(contracts[0]) if contracts else None, "contract_count": len(contracts)}
    from server.api.routers.sitok_groups import group_out
    out["group"] = group_out(db, f)  # 한 보고서로 묶인 동(10/12)
    out["renew"] = renew_info(db, f)  # 장기·지속 계약 끝나기 전 알림(10/13)
    if with_contracts:
        used: dict[int, list[str]] = {}  # 계약 → 쓰는 회차(10/14 계약 패널 "쓰는 회차: 2026 상·하")
        for rp in db.query(SitokReport).filter(SitokReport.facility_id == f.id, SitokReport.contract_id.isnot(None)).order_by(SitokReport.year, SitokReport.half).all():
            used.setdefault(rp.contract_id, []).append(f"{rp.year} {rp.half[:1]}")
        out["contracts"] = [{**_contract_out(c), "used_by": used.get(c.id, [])} for c in contracts]
    return out


def next_mgmt_no(db: Session, company_id: int, sector: str | None = None) -> str:
    """다음 번호표 "민간-5"·"관급-2" — 그 구분 번호 중 가장 큰 것 + 1(10/15 민재형 문서번호 일치화: 드롭박스 폴더를 관급·민간으로만 나눠 번호,
    서류 자동화 시설물 카드·보고서 자동화 시설물이 같은 번호, 연도 없음). 시특법은 산안법과 따로 매김."""
    sector = sector if sector in SECTORS else "민간"
    nums = [int(m[1]) for (no,) in db.query(SitokFacility.mgmt_no).filter(SitokFacility.company_id == company_id)
            if (m := re.match(rf"^{sector}-0*(\d+)$", (no or "").strip()))]
    return f"{sector}-{max(nums, default=0) + 1}"


def default_badges(f: SitokFacility, field: str | None = None) -> None:
    """새 시설물 뱃지 기본값 — 분야는 계약 수행분야(건축 → 건축, 그 밖 → 토목), 관급 종류는 보고서 틀(3종학교 → 학교, 그 밖 → 일반). 목록에서 바꿈."""
    if not f.badge_field:
        f.badge_field = "건축" if (field or "건축") == "건축" else "토목"
    if f.sector == "관급" and not f.badge_kind:
        f.badge_kind = "학교" if f.template == "3종학교" else "일반"
    if f.sector != "관급":
        f.badge_kind = ""


def default_type(sector: str | None) -> str:
    """새 등록 때 계약 구분 기본값 — 민간(반기마다 이어지는 계약) = 장기·지속, 관급(입찰) = 1회성. 목록에서 바꿈."""
    return "장기" if sector == "민간" else "1회성"


def mark_view(db: Session, user_id: int, facility_id: int | None) -> None:
    """마지막으로 연 때를 지금으로(목록 "최근 열람순") — 실패해도 화면은 열리게."""
    if not facility_id:
        return
    try:
        row = db.get(SitokView, (user_id, facility_id))
        if row is None:
            db.add(SitokView(user_id=user_id, facility_id=facility_id, viewed_at=datetime.datetime.now()))
        else:
            row.viewed_at = datetime.datetime.now()
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()


# ---------- 회차 ↔ 계약(10/13 사용자 — "2026 계약이 끝나고 2027 계약서는 다음 회차에 어떻게?") ----------

RENEW_DAYS = 60  # 장기·지속 계약 끝나기 이만큼 전부터 "다음 계약서 필요" 표시


def half_range(year: int, half: str) -> tuple[datetime.date, datetime.date]:
    return (datetime.date(year, 1, 1), datetime.date(year, 6, 30)) if half == "상반기" else (datetime.date(year, 7, 1), datetime.date(year, 12, 31))


def covers(c: SitokContract, year: int, half: str) -> bool:
    """계약이 그 반기를 덮는지 — 계약기간이 반기와 겹치고, 반기 하나 계약(halves 상반기/하반기)이면 그 반기만. 끝 날짜가 없으면 계속."""
    if c.halves in ("상반기", "하반기") and c.halves != half:
        return False
    if c.start_date is None:
        return False
    a, b = half_range(year, half)
    return c.start_date <= b and (c.end_date is None or c.end_date >= a)


def _family(db: Session, f: SitokFacility) -> list[int]:
    """이 동 먼저, 묶인 동이면 묶음 다른 동(한 계약서에 여러 동 — 계약은 보통 1번 동에)."""
    if not f.group_id:
        return [f.id]
    from server.api.routers.sitok_groups import members
    return [f.id] + [m.id for m in members(db, f.group_id) if m.id != f.id]


def contract_for(db: Session, f: SitokFacility, year: int, half: str) -> SitokContract | None:
    """그 반기를 덮는 계약(여럿이면 늦게 시작한 것). 없으면 None — 회차 만들기 화면이 "새 계약서를 올리세요"로 안내."""
    for fid in _family(db, f):
        cs = [c for c in db.query(SitokContract).filter(SitokContract.facility_id == fid).all() if covers(c, year, half)]
        if cs:
            return max(cs, key=lambda c: (c.start_date, c.id))
    return None


def attach_contract(db: Session, c: SitokContract) -> int:
    """계약을 추가·고친 뒤 — 이 동(묶인 동 포함) 회차 중 계약 없이 만든 것을 이 계약이 덮으면 붙임. 이미 계약이 있는 회차는 그대로. 붙인 수."""
    from core.models_web import SitokReport

    f = db.get(SitokFacility, c.facility_id)
    n = 0
    for r in db.query(SitokReport).filter(SitokReport.facility_id.in_(_family(db, f)), SitokReport.contract_id.is_(None)).all():
        if covers(c, r.year, r.half):
            r.contract_id = c.id
            n += 1
    return n


def renew_info(db: Session, f: SitokFacility) -> dict | None:
    """장기·지속 시설물인데 마지막 계약이 곧(60일 안) 끝나거나 끝났으면 {end, days} — 목록·회차 칸에 "다음 계약서 필요". 끝 없는 계약이 있으면 None."""
    if f.contract_type != "장기":
        return None
    cs = db.query(SitokContract).filter(SitokContract.facility_id.in_(_family(db, f))).all()
    if not cs or any(c.end_date is None and c.start_date is not None for c in cs):
        return None
    last = max((c.end_date for c in cs if c.end_date), default=None)
    if last is None:
        return None
    days = (last - datetime.date.today()).days
    return {"end": last.isoformat(), "days": days} if days <= RENEW_DAYS else None


def _require_facility(db: Session, user: User, facility_id: int) -> SitokFacility:
    f = db.get(SitokFacility, facility_id)
    if f is None or f.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "시설물을 찾을 수 없습니다.")
    return f


def _require_contract(db: Session, user: User, contract_id: int) -> SitokContract:
    c = db.get(SitokContract, contract_id)
    if c is None or c.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "계약을 찾을 수 없습니다.")
    return c


def guess_template(grade: str, use_type: str, main_use: str) -> str:
    """관리대장 종별·용도로 보고서 틀 추정 — 3종이면서 학교(교육연구시설)면 3종학교(치장벽돌 점검·내진보강 점검표 추가)."""
    if grade != "3":
        return "2종"
    return "3종학교" if "학교" in main_use or "교육연구" in use_type else "3종일반"


# ---------- API ----------

@router.get("/options")
def options(user: User = Depends(get_current_user)):
    """화면 고르기 칸의 선택지(제출 사이트와 같은 이름)."""
    return {"templates": TEMPLATES, "sectors": SECTORS, "halves": HALVES, "joint_types": JOINT_TYPES, "bid_methods": BID_METHODS, "fields": FIELDS,
            "contract_types": CONTRACT_TYPES, "badge_fields": BADGE_FIELDS, "badge_kinds": BADGE_KINDS}


@router.get("/next-mgmt-no")
def get_next_mgmt_no(sector: str = "민간", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"mgmt_no": next_mgmt_no(db, user.company_id, sector)}


@router.get("/facilities")
def list_facilities(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(SitokFacility).filter(SitokFacility.company_id == user.company_id).order_by(SitokFacility.id.desc()).all()
    seen = dict(db.query(SitokView.facility_id, SitokView.viewed_at).filter(SitokView.user_id == user.id))
    return [_facility_out(db, f, with_contracts=False) | {"viewed_at": seen[f.id].isoformat(timespec="seconds") if f.id in seen else ""}
            for f in rows]


@router.post("/read")
def read_pdf(kind: str = Form(...), file: UploadFile = File(...), user: User = Depends(get_current_user)):
    """kind = ledger(시설물관리대장, AI로 칸) | contract(계약서, AI로 칸) | register(건축물대장 — 보관만, 시설물 현황·1.2.8 초안이 나중에 읽음)."""
    if kind not in ("ledger", "contract", "register"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "kind는 ledger·contract·register입니다.")
    data = file.file.read()
    if not data.startswith(b"%PDF"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "PDF 파일을 올려 주세요.")
    _clean_uploads()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(12)
    path = UPLOAD_DIR / f"{token}.pdf"
    path.write_bytes(data)
    if kind == "register":
        return {"token": token, "fields": {}, "error": ""}
    try:
        parsed = reader.read_ledger(path, user.company_id) if kind == "ledger" else reader.read_contract(path, user.company_id)
    except Exception as err:  # noqa: BLE001 — 읽기 실패해도 파일은 붙이고 손으로 채우게
        return {"token": token, "fields": {}, "error": f"자동으로 읽지 못했습니다 — 직접 입력해 주세요. ({str(err).splitlines()[0][:160]})"}
    fields = {k: _iso(v) for k, v in parsed.items()}
    if kind == "ledger":
        fields["template"] = guess_template(fields.get("grade", ""), fields.get("use_type", ""), fields.get("main_use", ""))
    return {"token": token, "fields": fields, "error": ""}


@router.post("/facilities")
def create_facility(body: CreateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not (body.facility.name or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "시설물명을 넣어 주세요.")
    f = SitokFacility(company_id=user.company_id, created_by=user.display_name or "", ledger=body.ledger_extra or None)
    _apply_facility(f, body.facility)
    if body.facility.sector is None:
        f.sector = (body.contract.sector if body.contract else None) or "민간"
    f.mgmt_no = f.mgmt_no or next_mgmt_no(db, user.company_id, f.sector)
    default_badges(f, body.contract.field if body.contract else None)
    if body.facility.contract_type is None:
        f.contract_type = default_type(f.sector)
    db.add(f)
    db.flush()
    f.ledger_pdf = _take(body.ledger_token, _facility_dir(f) / "시설물관리대장.pdf")
    if body.contract is not None:
        _add_contract(db, user, f, body.contract)
    db.commit()
    return _facility_out(db, f)


def _add_contract(db: Session, user: User, f: SitokFacility, body: ContractIn) -> SitokContract:
    c = SitokContract(company_id=user.company_id, facility_id=f.id, created_by=user.display_name or "")
    _apply_contract(c, body)
    db.add(c)
    db.flush()
    c.contract_pdf = _take(body.contract_token, _facility_dir(f) / f"계약서_{c.id}.pdf")
    return c


@router.get("/facilities/{facility_id}")
def get_facility(facility_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = _require_facility(db, user, facility_id)
    mark_view(db, user.id, f.id)
    return _facility_out(db, f)


class TypeIn(BaseModel):
    contract_type: str


@router.post("/facilities/{facility_id}/contract-type")
def set_contract_type(facility_id: int, body: TypeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """시설물 목록함 구분 바꾸기 — 한 보고서로 묶인 동은 계약이 하나라 같이 바꿈."""
    _check("계약 구분", body.contract_type, CONTRACT_TYPES)
    f = _require_facility(db, user, facility_id)
    members = db.query(SitokFacility).filter(SitokFacility.group_id == f.group_id).all() if f.group_id else [f]
    for m in members:
        m.contract_type = body.contract_type
    db.commit()
    return {"ok": True, "ids": [m.id for m in members], "contract_type": body.contract_type}


@router.patch("/facilities/{facility_id}")
def update_facility(facility_id: int, body: FacilityIn, ledger_token: str | None = None,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = _require_facility(db, user, facility_id)
    old_dir = _facility_dir(f)
    _apply_facility(f, body)
    if _facility_dir(f) != old_dir and old_dir.exists():  # 이름이 바뀌면 폴더도
        old_dir.rename(_facility_dir(f))
        f.ledger_pdf = str(_facility_dir(f) / Path(f.ledger_pdf).name) if f.ledger_pdf else ""
        for c in db.query(SitokContract).filter(SitokContract.facility_id == f.id):
            c.contract_pdf = str(_facility_dir(f) / Path(c.contract_pdf).name) if c.contract_pdf else ""
    if ledger_token:
        f.ledger_pdf = _take(ledger_token, _facility_dir(f) / "시설물관리대장.pdf") or f.ledger_pdf
    db.commit()
    return _facility_out(db, f)


@router.delete("/facilities/{facility_id}")
def delete_facility(facility_id: int, password: str = Body("", embed=True), user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """시설물 지우기(계약·올린 PDF까지, 되돌릴 수 없음) — 현장 삭제와 같은 회사 공용 삭제 비밀번호."""
    _check_delete_password(user, password)
    f = _require_facility(db, user, facility_id)
    _delete_facility(db, f)
    db.commit()
    return {"ok": True}


def _check_delete_password(user: User, password: str) -> None:
    password_hash = config.get_site_delete_password_hash(user.company_id)
    if not password_hash:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "삭제 비밀번호가 아직 없습니다. '설정' 탭에서 먼저 정하세요.")
    if not verify_password(password, password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "삭제 비밀번호가 맞지 않습니다.")


def _delete_facility(db: Session, f: SitokFacility) -> None:
    """계약·회차·올린 서류·만든 보고서 폴더까지. 서류 자동화 쪽 계약(SitokDocContract)은 연결만 끊김(FK SET NULL)."""
    folder = _facility_dir(f)
    db.query(SitokContract).filter(SitokContract.facility_id == f.id).delete()
    db.delete(f)
    db.flush()
    shutil.rmtree(folder, ignore_errors=True)


class BulkDeleteIn(BaseModel):
    ids: list[int]
    password: str = ""


@router.post("/facilities/delete")
def delete_facilities(body: BulkDeleteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """목록에서 고른 시설물 한꺼번에 지우기(10/14 형 피드백 ③) — 비밀번호 한 번, 지워지는 범위는 하나 지우기와 같음."""
    _check_delete_password(user, body.password)
    names = []
    for fid in body.ids:
        f = db.query(SitokFacility).filter(SitokFacility.id == fid, SitokFacility.company_id == user.company_id).first()
        if f is None:
            continue
        names.append(f.name)
        _delete_facility(db, f)
    db.commit()
    return {"ok": True, "deleted": names}


@router.post("/facilities/{facility_id}/contracts")
def add_contract(facility_id: int, body: ContractIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = _require_facility(db, user, facility_id)
    c = _add_contract(db, user, f, body)
    db.flush()
    attached = attach_contract(db, c)  # 계약 없이 만든 회차 중 이 계약이 덮는 것
    db.commit()
    return _facility_out(db, f) | {"new_contract_id": c.id, "attached": attached}


@router.patch("/contracts/{contract_id}")
def update_contract(contract_id: int, body: ContractIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _require_contract(db, user, contract_id)
    _apply_contract(c, body)
    if body.contract_token:
        f = db.get(SitokFacility, c.facility_id)
        c.contract_pdf = _take(body.contract_token, _facility_dir(f) / f"계약서_{c.id}.pdf") or c.contract_pdf
    attach_contract(db, c)  # 날짜를 고쳐 덮게 된 계약 없는 회차
    db.commit()
    return _facility_out(db, db.get(SitokFacility, c.facility_id))


@router.delete("/contracts/{contract_id}")
def delete_contract(contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _require_contract(db, user, contract_id)
    if c.contract_pdf:
        Path(c.contract_pdf).unlink(missing_ok=True)
    fid = c.facility_id
    db.delete(c)
    db.commit()
    return _facility_out(db, db.get(SitokFacility, fid))


@router.get("/files/ledger/{facility_id}")
def ledger_file(facility_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = _require_facility(db, user, facility_id)
    if not f.ledger_pdf or not Path(f.ledger_pdf).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "올린 관리대장이 없습니다.")
    return FileResponse(f.ledger_pdf, media_type="application/pdf", filename=f"{f.name}_시설물관리대장.pdf", content_disposition_type="inline")


@router.get("/files/contract/{contract_id}")
def contract_file(contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _require_contract(db, user, contract_id)
    if not c.contract_pdf or not Path(c.contract_pdf).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "올린 계약서가 없습니다.")
    return FileResponse(c.contract_pdf, media_type="application/pdf", filename=f"계약서_{c.id}.pdf", content_disposition_type="inline")
