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
from server.sitok import kinds as _kinds
from server.sitok import reader
from server.sitok import seasons

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
BADGE_KINDS = ("학교", "일반")  # 내진성능평가는 따로 빼기로(민재형 10/15 밤)
# 뱃지 자동(민재형 10/15 "계약서 보고 뱃지 자동선택") — 발주처·시설물명·계약건명·제원·용도에 이 말이 있으면(주소는 안 봄 — "○○로"가 도로로 잡힘)
SCHOOL_WORDS = ("학교", "유치원", "교육청", "교육지원청")
BUILD_WORDS = ("건축물", "건물", "교사동", "체육관", "강당", "교회", "아파트", "공동주택", "기숙사", "청사", "주택", "빌딩", "센터", "병원", "어린이집", "학교", "유치원")
CIVIL_WORDS = ("교량", "터널", "옹벽", "사면", "절토", "도로", "하천", "제방", "배수", "수문", "육교", "지하차도", "상수도", "하수도", "댐", "항만", "방조제",
               "저수지", "수리시설", "토목")
FAC_FIELDS = ("fms_no", "name", "template", "kind", "use_type", "main_use", "address", "owner_name", "owner_type", "owner_phone",
              "class_no", "safety_grade", "last_precision", "last_diagnosis",  # 도래주기(0056, 10/20 — server/sitok/cycle.py)
              "completion_date", "structure", "floors_above", "floors_below", "floors_roof", "max_height", "total_area", "building_area", "memo", "legal",
              "mgmt_no", "contact_name", "contact_phone", "contract_type", "sector", "badge_field", "badge_kind")
CON_FIELDS = ("sector", "title", "contract_no", "contract_date", "start_date", "end_date", "halves", "first_half_end", "second_half_start",
              "amount", "rep_name", "joint_type", "joint_pct", "bid_method", "field")
DATES = {"completion_date", "contract_date", "start_date", "end_date", "first_half_end", "second_half_start", "last_precision", "last_diagnosis"}
CLASS_NOS = ("", "1종", "2종", "3종")  # 종별(도래주기) — ""는 보고서 틀로(3종 틀이면 3종, 아니면 2종)
SAFETY_GRADES = ("", "A", "B", "C", "D", "E")  # ""는 최근 보고서 결과표


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
    class_no: str | None = None  # 종별 1종·2종·3종(0056 도래주기) — "" = 보고서 틀로
    safety_grade: str | None = None  # 안전등급 A~E — "" = 최근 보고서 결과표
    last_precision: datetime.date | None = None  # 전회차 정밀안전점검 완료일(우리 회차·전회차 보고서 이력이 없을 때)
    last_diagnosis: datetime.date | None = None  # 전회차 정밀안전진단 완료일(1종)
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
    holder: str | None = None  # 소유주 — 관리대장 "소유자" 칸(10/21 사용자, 결과표 대표자), ledger JSON에 보관
    land_area: float | None = None  # 대지면적(㎡)·건폐율(%)·용적율(%) — SafetyMan 건물개요(10/15 민재형), ledger JSON에 보관
    coverage_ratio: float | None = None
    floor_area_ratio: float | None = None
    # 옹벽 관리대장 칸(10/21 형 "옹벽 시설물관리대장 양식으로") — ledger JSON "wall"에 보관(wall_ledger.KEYS), 보고서 1.2.1 현황표·요약문·과업대상 표가 씀
    wall_form: str | None = None
    wall_material: str | None = None
    wall_length: str | None = None
    wall_height: str | None = None
    wall_base_width: str | None = None
    wall_route: str | None = None
    wall_surround: str | None = None
    wall_builder: str | None = None
    wall_attached: str | None = None
    wall_project: str | None = None


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


LEDGER_KEYS = ("base_wall", "base_slab", "land_area", "coverage_ratio", "floor_area_ratio", "holder")  # 표 열 없이 ledger JSON에 두는 시설물 칸
WALL_KEYS = ("form", "material", "length", "height", "base_width", "route", "surround", "builder", "attached", "project")  # ledger["wall"] — 시설물 칸 wall_*
# 교량 제원(10/29 — 교량 원본 1.2.1 시설물 현황표 칸): 설계하중·노선명(이정)·연장·경간 구성·폭·차로·상부/하부 형식·교대/교각 기초·받침·신축이음·교차시설물·통과 높이·부착시설.
# 옹벽과 같은 ledger["wall"](토목 제원 칸)에 담음 — 화면은 wall_<키>로 주고받음(겹치는 length·route·attached는 같이 씀).
BRIDGE_KEYS = ("load", "route", "length", "spans", "width", "lanes", "super_type", "sub_type", "abut_found", "pier_found", "bearing", "joint", "crossing", "clearance", "attached")
CIVIL_KEYS = tuple(dict.fromkeys(WALL_KEYS + BRIDGE_KEYS))
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
    _check("종별", data.get("class_no"), CLASS_NOS)
    _check("안전등급", data.get("safety_grade"), SAFETY_GRADES)
    if data.get("last_precision"):  # 날짜를 넣으면 "아직 안 함(최초)"은 풂(계약 창 도래주기 칸과 같게)
        row.precision_first = False
    if data.get("last_diagnosis"):
        row.diagnosis_first = False
    bases = {k: data.pop(k) for k in LEDGER_KEYS if k in data}
    if bases:
        row.ledger = {**(row.ledger or {}), **bases}
    wall = {k: (data.pop(f"wall_{k}") or "").strip() for k in CIVIL_KEYS if f"wall_{k}" in data}
    if wall:
        row.ledger = {**(row.ledger or {}), "wall": {**((row.ledger or {}).get("wall") or {}), **wall}}
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


def kind_known(db: Session, c: SitokContract | None, year: int, half: str, name: str | None = None) -> str | None:
    """그 반기 회차 종류(정기/정밀) — ① 보고서 쪽 계약의 회차 줄 ② 그 계약을 만든 서류 자동화 계약의 회차 줄 ③ 계약건명에 정밀·정기 중 하나만 있으면 그것(10/14 형 피드백 —
    스캔 계약서라 회차 줄을 못 읽은 꿈에블리스나인 "정기(정밀)"는 둘 다 있어 못 정함) → 모르면 None(회차 만들기가 물음)."""
    from core.models_web import SitokDocContract
    from server.sitok import civil

    if c is None:
        return None
    if seasons.is_seismic_title(c.title):  # 내진성능평가 계약(10/21)
        return "성능평가"
    rounds = c.rounds or []
    unit = next((r for r in rounds if r.get("open_ended")), None)
    k = civil.kind_for(rounds, unit, unit is not None, year, half, name)  # name = 그 시설물(동) 이름 — 같은 반기에도 동마다 정기·정밀·진단이 다를 수 있음(10/31)
    if k is None:
        doc = db.query(SitokDocContract).filter(SitokDocContract.report_contract_id == c.id).first() or next(
            (d for d in db.query(SitokDocContract).filter(SitokDocContract.company_id == c.company_id, SitokDocContract.report_contracts.isnot(None))
             if c.id in [int(v) for v in (d.report_contracts or {}).values()]), None)  # 시설물 여럿 계약(0052) — 둘째 시설물의 보고서 쪽 계약
        if doc is not None:
            k = civil.kind_for(doc.rounds, doc.unit, doc.open_ended, year, half, name)
    if k is None:
        t = (c.title or "").replace(" ", "")
        has_pre, has_reg = "정밀" in t, "정기" in t
        k = "정밀" if has_pre and not has_reg else "정기" if has_reg and not has_pre else None
    # 정밀안전진단 회차(10/20 계약서에 넣음) — 보고서 자동화엔 진단 틀이 없어 정밀(안전점검) 틀로 회차를 만듦(진단 보고서는 회사 양식으로 따로)
    return "정밀" if k == "진단" else k


def kind_for(db: Session, c: SitokContract | None, year: int, half: str, name: str | None = None) -> str:
    """kind_known, 모르면 정기(목록 기본값 표시용 — 회차 만들기는 create_report가 428로 물음)."""
    return kind_known(db, c, year, half, name) or "정기"


def _contract_out(c: SitokContract) -> dict:
    dv = c.deliver or {}
    return {"id": c.id, **{k: _iso(getattr(c, k)) for k in CON_FIELDS}, "rounds": c.rounds or [],
            "has_pdf": bool(c.contract_pdf and Path(c.contract_pdf).exists()),
            "has_order": bool(c.order_pdf and Path(c.order_pdf).exists()),  # 발주처 과업지시서(0060, 형 10/21)
            "deliver": {"book": str(dv.get("book") or "-"), "usb": str(dv.get("usb") or "-"), "note": str(dv.get("note") or "협의"), "src": str(dv.get("src") or "")},
            "created_at": c.created_at.strftime("%Y-%m-%d") if c.created_at else ""}


def _wall_kind_text(f: SitokFacility) -> str:
    """옹벽 "종류" 칸 — 저장값 > 관리대장 세분류 글로 FMS 표에서(건축물옹벽 등, 10/21 사용자) > 시설물 구분 글로."""
    from server.sitok import wall_ledger

    return wall_ledger.facility_kind_text(f)


def register_path(f: SitokFacility) -> Path:
    """건축물대장 PDF — 시설물 폴더에 하나(시설물 현황 AI·1.2.8 초안이 같이 씀). 10/14 시설물 정보·서류 칸에서 올림."""
    return _facility_dir(f) / "건축물대장.pdf"


def _facility_out(db: Session, f: SitokFacility, with_contracts: bool = True) -> dict:
    contracts = (db.query(SitokContract).filter(SitokContract.facility_id == f.id)
                 .order_by(SitokContract.start_date.desc().nullslast(), SitokContract.id.desc()).all())
    out = {"id": f.id, **{k: _iso(getattr(f, k)) for k in FAC_FIELDS}, "ledger": f.ledger or {},
           "has_ledger_pdf": bool(f.ledger_pdf and Path(f.ledger_pdf).exists()), "has_register": register_path(f).exists(),
           **{k: (f.ledger or {}).get(k) for k in LEDGER_KEYS},
           "is_wall": _kinds.is_wall(f), "is_bridge": _kinds.is_bridge(f), **{f"wall_{k}": ((f.ledger or {}).get("wall") or {}).get(k) or "" for k in CIVIL_KEYS},  # 옹벽·교량 칸(10/21·10/29)
           **({"wall_kind_text": _wall_kind_text(f), "use_type": _wall_kind_text(f)} if _kinds.is_civil(f) else {}),
           "civil_kind": _kinds.civil_kind(f), "template_block": _kinds.template_block(f),  # 보고서 틀 종류별(10/21 형)  # 옹벽 "종류" 칸 = use_type(비면 관리대장 세분류 → FMS 시설물종류)
           "latest": _contract_out(contracts[0]) if contracts else None, "contract_count": len(contracts)}
    from server.api.routers.sitok_groups import group_out
    out["group"] = group_out(db, f)  # 한 보고서로 묶인 동(10/12)
    from server.api.routers.sitok_docs import _card_units
    us = _card_units(db, f)
    out["card_units"] = [{"id": u.id, "mgmt_no": u.mgmt_no, "name": u.name, "book": k} for k, u in enumerate(us, 1)] if len(us) > 1 else []  # 보고서 따로 시설물(보고서 1·2, 10/16 등록 칸)
    card = card_facilities(db, f)
    out["card_fms"] = [{"id": x.id, "fms_no": x.fms_no, "name": x.name, "mgmt_no": x.mgmt_no} for x in card if x.fms_no]  # 등록 칸이 이미 있는 건물을 뺌(10/16)
    # ① 건물 타일 — 카드의 모든 건물(묶음·따로 섞여도, 보고서 순서 → 묶음 안 순서, 10/20 민재형 "시설물명만 나열, 누르면 시설물 정보")
    out["card_all"] = [{"id": x.id, "name": x.name, "kind": _kinds.civil_kind(x) or "건물"} for x in sorted(card, key=lambda x: (x.book_order or 0, x.group_order or 0, x.id))]  # kind = 타일 머리 "건물 3 · 옹벽 1"(10/21)
    out["renew"] = renew_info(db, f)  # 장기·지속 계약 끝나기 전 알림(10/13)
    if with_contracts:
        used: dict[int, list[str]] = {}  # 계약 → 쓰는 회차(10/14 계약 패널 "쓰는 회차: 2026 상·하")
        for rp in db.query(SitokReport).filter(SitokReport.facility_id == f.id, SitokReport.contract_id.isnot(None)).order_by(SitokReport.year, SitokReport.half).all():
            used.setdefault(rp.contract_id, []).append(f"{rp.year} {rp.half[:1]}")
        out["contracts"] = [{**_contract_out(c), "used_by": used.get(c.id, [])} for c in contracts]
    return out


NO_RE = re.compile(r"^(관급|민간)-0*(\d+)(?:-0*(\d+))?$")  # "관급-6" — 뒤 "-2"는 예전 모양(10/15 밤 시설물 여럿 카드, 10/19부터 안 붙임 — 0054)


def base_no(no: str | None) -> str:
    """카드 번호(앞 번호) — "관급-6-2" → "관급-6". 모양이 다르면 그대로."""
    m = NO_RE.match((no or "").strip())
    return f"{m[1]}-{int(m[2])}" if m else (no or "").strip()


def card_facilities(db: Session, f: SitokFacility) -> list[SitokFacility]:
    """같은 시설물 카드(같은 앞 번호)의 시설물 전부 — 시설물 여럿 카드(6-1·6-2)와 묶인 동 포함. 번호가 없으면 자기 묶음만."""
    b = base_no(f.mgmt_no)
    if not b:
        return db.query(SitokFacility).filter(SitokFacility.group_id == f.group_id).all() if f.group_id else [f]
    return [x for x in db.query(SitokFacility).filter(SitokFacility.company_id == f.company_id).order_by(SitokFacility.id) if base_no(x.mgmt_no) == b]


def next_mgmt_no(db: Session, company_id: int, sector: str | None = None) -> str:
    """다음 번호표 "민간-5"·"관급-2" — 그 구분 번호 중 가장 큰 것 + 1(10/15 민재형 문서번호 일치화: 드롭박스 폴더를 관급·민간으로만 나눠 번호,
    서류 자동화 시설물 카드·보고서 자동화 시설물이 같은 번호, 연도 없음). 시특법은 산안법과 따로 매김."""
    sector = sector if sector in SECTORS else "민간"
    nums = [int(m[2]) for (no,) in db.query(SitokFacility.mgmt_no).filter(SitokFacility.company_id == company_id)
            if (m := NO_RE.match((no or "").strip())) and m[1] == sector]  # 관급-6-2도 앞 번호 6으로 셈
    return f"{sector}-{max(nums, default=0) + 1}"


def guess_badges(texts: list[str]) -> tuple[str, str]:
    """글들 → (분야, 관급 종류). 건물 말만 → 건축, 토목 말만 → 토목, 둘 다 → 건축·토목, 아무것도 없으면 건축. 학교 말 → 학교, 아니면 일반."""
    t = "".join(x for x in texts if x).replace(" ", "")
    b, c = any(w in t for w in BUILD_WORDS), any(w in t for w in CIVIL_WORDS)
    return ("건축·토목" if b and c else "토목" if c else "건축"), ("학교" if any(w in t for w in SCHOOL_WORDS) else "일반")


def auto_badges(db: Session, f: SitokFacility) -> None:
    """카드(묶인 동 같이) 뱃지를 이름·용도·계약들 글로 다시 정함 — 사람이 바꾼 카드(badge_manual)는 그대로."""
    from core.models_web import SitokDocContract

    members = db.query(SitokFacility).filter(SitokFacility.group_id == f.group_id).all() if f.group_id else [f]
    if any(m.badge_manual for m in members):
        return
    ids = [m.id for m in members]
    texts = [x for m in members for x in (m.name, m.owner_name, m.use_type, m.main_use, m.kind if m.kind != "건축물" else "")]
    for d in db.query(SitokDocContract).filter(SitokDocContract.facility_id.in_(ids)):
        texts += [d.client, d.facility_name, d.title, d.spec]
    for c in db.query(SitokContract).filter(SitokContract.facility_id.in_(ids)):
        texts.append(c.title)
    field, kind = guess_badges(texts)
    for m in members:
        m.badge_field = field
        m.badge_kind = kind if m.sector == "관급" else ""


def default_badges(f: SitokFacility, field: str | None = None) -> None:
    """새 시설물 뱃지 기본값 — 분야는 계약 수행분야(건축 → 건축, 그 밖 → 토목), 관급 종류는 보고서 틀(3종학교 → 학교, 그 밖 → 일반). 목록에서 바꿈."""
    if not f.badge_field:
        f.badge_field = "건축" if (field or "건축") == "건축" else "토목"
    if f.sector == "관급" and not f.badge_kind:
        f.badge_kind = "학교" if f.template == "3종학교" else "일반"
    if f.sector != "관급":
        f.badge_kind = ""


def check_number(db: Session, f: SitokFacility, no: str) -> None:
    """번호가 다른 카드와 겹치면 409 — 같은 카드 건물끼리는 같은 번호(묶인 동·보고서 따로, 10/19 뒷번호 없앰)라 괜찮음."""
    other = db.query(SitokFacility).filter(SitokFacility.company_id == f.company_id, SitokFacility.mgmt_no == no, SitokFacility.id != f.id).all()
    other = [o for o in other if not (f.group_id and o.group_id == f.group_id) and not (f.mgmt_no and base_no(o.mgmt_no) == base_no(f.mgmt_no))]
    if other:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{no}은(는) {other[0].name}이(가) 쓰고 있습니다 — 다른 번호를 고르세요.")


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
    return seasons.date_range(year, half)  # 상·하반기 + 연 3회 해빙기(2~3월)·우기(5~6월)·동절기(11~12월)


def covers(c: SitokContract, year: int, half: str) -> bool:
    """계약이 그 반기를 덮는지 — 계약기간이 반기와 겹치고, 반기 하나 계약(halves 상반기/하반기)이면 그 반기만. 끝 날짜가 없으면 계속.
    내진성능평가(10/21): 성능평가 회차는 건명에 "성능평가"가 있는 계약만, 정기·정밀 회차는 그런 계약을 안 씀(같은 기간이어도)."""
    if seasons.is_seismic_title(c.title) != seasons.is_seismic(half):
        return False
    if c.halves in ("상반기", "하반기") and c.halves != seasons.bucket(half):
        return False
    th = seasons.title_half(c.title)  # 연간이어도 건명이 "2026년 하반기 …"면 그 반기만 — 완수일이 다음 해 1월이어도 다음 해 상반기는 "계약 없음"(10/25 민재형)
    if th and c.halves not in ("상반기", "하반기") and not seasons.is_seismic(half) and th != (year, seasons.bucket(half)):
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


def refit_contracts(db: Session, reports) -> list[dict]:
    """회차에 붙은 계약이 그 반기를 안 덮으면 덮는 계약(contract_for — 그 동 → 묶음, 늦게 시작한 것)으로 바꿈 — 덮는 계약이 없으면 그대로.
    바꾼 것 [{report_id, old, new}](부르는 쪽이 commit)."""
    out = []
    for r in reports:
        if not r.contract_id:
            continue
        cur = db.get(SitokContract, r.contract_id)
        if cur is not None and covers(cur, r.year, r.half):
            continue
        best = contract_for(db, db.get(SitokFacility, r.facility_id), r.year, r.half)
        if best is not None and best.id != r.contract_id:
            out.append({"report_id": r.id, "old": r.contract_id, "new": best.id})
            r.contract_id = best.id
    return out


def attach_contract(db: Session, c: SitokContract) -> int:
    """계약을 추가·고친 뒤 — 이 동(묶인 동 포함) 회차 중 계약 없이 만든 것을 이 계약이 덮으면 붙임. 이미 계약이 있는 회차는 그대로. 붙인 수.
    붙이는 건 그 반기에 맞는 계약(contract_for — 늦게 시작한 것): 계약 둘을 잇달아 넣을 때 상반기 계약(~7/11)이 하반기 회차를 먼저 가져가지 않게(10/21 관급-30)."""
    from core.models_web import SitokReport

    f = db.get(SitokFacility, c.facility_id)
    n = 0
    for r in db.query(SitokReport).filter(SitokReport.facility_id.in_(_family(db, f)), SitokReport.contract_id.is_(None)).all():
        if covers(c, r.year, r.half):
            best = contract_for(db, db.get(SitokFacility, r.facility_id), r.year, r.half)
            r.contract_id = (best or c).id
            n += 1
    # 계약이 붙어 있어도 그 반기를 안 덮는 회차(상반기 계약 ↔ 하반기 회차) — 덮는 계약으로(10/25 관급-30)
    n += len(refit_contracts(db, db.query(SitokReport).filter(SitokReport.facility_id.in_(_family(db, f)), SitokReport.contract_id.isnot(None)).all()))
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


def ledger_class(grade: str) -> str:
    """관리대장 종별 숫자 → 시설물 종별 칸 "1종"/"2종"/"3종"(10/20 — 1종도 틀은 2종이라 보고서 종별 글자·도래주기는 이 칸으로)."""
    return f"{grade}종" if grade in ("1", "2", "3") else ""


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
            "contract_types": CONTRACT_TYPES, "badge_fields": BADGE_FIELDS, "badge_kinds": BADGE_KINDS, "class_nos": CLASS_NOS, "safety_grades": SAFETY_GRADES}


@router.get("/next-mgmt-no")
def get_next_mgmt_no(sector: str = "민간", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"mgmt_no": next_mgmt_no(db, user.company_id, sector)}


@router.get("/facilities")
def list_facilities(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(SitokFacility).filter(SitokFacility.company_id == user.company_id, SitokFacility.survey_only.is_(False), SitokFacility.seismic_only.is_(False)).order_by(SitokFacility.id.desc()).all()  # 결함조사만(0061)은 빠짐
    seen = dict(db.query(SitokView.facility_id, SitokView.viewed_at).filter(SitokView.user_id == user.id))
    from server.api.routers.sitok_docs import contract_index, site_phone

    index = contract_index(db, user.company_id)
    group_ids: dict[int, set[int]] = {}
    for f in rows:
        if f.group_id:
            group_ids.setdefault(f.group_id, set()).add(f.id)
    return [_facility_out(db, f, with_contracts=False) | {"viewed_at": seen[f.id].isoformat(timespec="seconds") if f.id in seen else "",
                                                         "phone": site_phone(index, group_ids.get(f.group_id) or {f.id}, f.owner_phone)}  # 10/20 현장 담당, 비면 관리주체
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
        fields["class_no"] = ledger_class(fields.get("grade", ""))
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
    """시설물 목록함 구분 바꾸기 — 한 보고서로 묶인 동은 계약이 하나라 같이 바꿈. 번호가 같은 시설물(보고서 따로)도 같은 카드라 같이(10/30 — 목록도 한 카드)."""
    _check("계약 구분", body.contract_type, CONTRACT_TYPES)
    f = _require_facility(db, user, facility_id)
    members = card_facilities(db, f)  # 번호 없으면 자기 묶음만(없으면 자기만)
    for m in members:
        m.contract_type = body.contract_type
    db.commit()
    return {"ok": True, "ids": [m.id for m in members], "contract_type": body.contract_type}


def move_defect_photos(db: Session, facility_id: int, old_dir: Path, new_dir: Path) -> int:
    """시설물 폴더 이름이 바뀌면(이름 고침·관리대장 시설물명) 결함 사진(이번·전회차) 경로도 새 폴더로 — 10/16 양주덕산초 "전회차 사진이 다 없어짐"."""
    from core.models_web import SitokDefect

    old_s, new_s, n = str(old_dir), str(new_dir), 0
    rids = [r for (r,) in db.query(SitokReport.id).filter(SitokReport.facility_id == facility_id)]
    for d in db.query(SitokDefect).filter(SitokDefect.report_id.in_(rids)) if rids else []:
        for k in ("photo", "prev_photo"):
            v = getattr(d, k)
            if v and v.startswith(old_s):
                setattr(d, k, new_s + v[len(old_s):])
                n += 1
    return n


@router.patch("/facilities/{facility_id}")
def update_facility(facility_id: int, body: FacilityIn, ledger_token: str | None = None,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = _require_facility(db, user, facility_id)
    old_dir = _facility_dir(f)
    if (body.badge_field is not None and body.badge_field != f.badge_field) or (body.badge_kind is not None and (body.badge_kind or "") != (f.badge_kind or "")):
        f.badge_manual = True  # 사람이 뱃지를 바꿈 — 자동이 다시 덮어쓰지 않게(10/15)
    if body.mgmt_no is not None and body.mgmt_no.strip() and body.mgmt_no.strip() != f.mgmt_no:
        check_number(db, f, body.mgmt_no.strip())
    _apply_facility(f, body)
    if _facility_dir(f) != old_dir and old_dir.exists():  # 이름이 바뀌면 폴더도
        old_dir.rename(_facility_dir(f))
        f.ledger_pdf = str(_facility_dir(f) / Path(f.ledger_pdf).name) if f.ledger_pdf else ""
        for c in db.query(SitokContract).filter(SitokContract.facility_id == f.id):
            c.contract_pdf = str(_facility_dir(f) / Path(c.contract_pdf).name) if c.contract_pdf else ""
        move_defect_photos(db, f.id, old_dir, _facility_dir(f))
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


def _heir(db: Session, f: SitokFacility) -> SitokFacility | None:
    """묶음에서 이 동 다음 동(남는 동 중 맨 앞) — 지울 때 계약을 넘겨받음."""
    if not f.group_id:
        return None
    return (db.query(SitokFacility).filter(SitokFacility.group_id == f.group_id, SitokFacility.id != f.id)
            .order_by(SitokFacility.group_order, SitokFacility.id).first())


def _pass_contracts(db: Session, f: SitokFacility, heir: SitokFacility) -> None:
    """묶음의 동을 지울 때 그 동 계약을 다음 동에 넘김(10/16 — 전엔 대표 동을 지우면 묶음 계약·서류 자동화 계약까지 지워짐).
    다음 동이 같은 계약을 이미 가졌으면 이 동 몫만 지우고 그 계약을 쓰던 회차는 다음 동 계약으로. 서류 계약의 맡는 시설물도 이 동 → 다음 동."""
    from core.models_web import SitokDocContract

    def ids(d):
        return [int(x) for x in (d.facility_ids or ([d.facility_id] if d.facility_id else []))]

    docs = [d for d in db.query(SitokDocContract).filter(SitokDocContract.company_id == f.company_id).all() if f.id in ids(d)]
    for rc in db.query(SitokContract).filter(SitokContract.facility_id == f.id).all():
        d = next((x for x in docs if str((x.report_contracts or {}).get(str(f.id))) == str(rc.id)), None)
        keep = db.get(SitokContract, (d.report_contracts or {})[str(heir.id)]) if d is not None and (d.report_contracts or {}).get(str(heir.id)) else None
        if keep is None:
            keep = next((c for c in db.query(SitokContract).filter(SitokContract.facility_id == heir.id).all()
                         if (c.title, c.start_date, c.end_date) == (rc.title, rc.start_date, rc.end_date)), None)
        if keep is not None:  # 다음 동이 같은 계약을 이미 가짐 — 회차만 그쪽으로
            db.query(SitokReport).filter(SitokReport.contract_id == rc.id).update({SitokReport.contract_id: keep.id})
            db.delete(rc)
            continue
        if rc.contract_pdf and Path(rc.contract_pdf).exists():  # 계약서 PDF는 지울 동 폴더에 있음 — 다음 동 폴더로
            dest = _facility_dir(heir) / Path(rc.contract_pdf).name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(rc.contract_pdf, dest)
            rc.contract_pdf = str(dest)
        rc.facility_id = heir.id
        if d is not None:
            d.report_contracts = {**{k: v for k, v in (d.report_contracts or {}).items() if str(k) != str(f.id)}, str(heir.id): rc.id}
    for d in docs:
        new = []
        for x in ids(d):
            y = heir.id if x == f.id else x
            if y not in new:
                new.append(y)
        d.facility_ids = new
        d.facility_id = heir.id if d.facility_id == f.id or d.facility_id not in new else d.facility_id
        amounts = {str(k): v for k, v in (d.amounts or {}).items()}
        if str(f.id) in amounts:
            amounts.setdefault(str(heir.id), amounts.pop(str(f.id)))
        d.amounts = amounts or None
        d.report_contracts = {k: v for k, v in (d.report_contracts or {}).items() if str(k) != str(f.id)} or None
    db.flush()


def _regroup(db: Session, group_id: int | None) -> None:
    """동을 지운 뒤 묶음 — 남은 동 순서를 0부터 다시, 하나만 남으면 묶음을 풂(그 동 혼자 보고서)."""
    if not group_id:
        return
    from core.models_web import SitokGroup

    rest = db.query(SitokFacility).filter(SitokFacility.group_id == group_id).order_by(SitokFacility.group_order, SitokFacility.id).all()
    if len(rest) <= 1:
        for x in rest:
            x.group_id, x.group_order = None, 0
        g = db.get(SitokGroup, group_id)
        if g is not None:
            db.delete(g)
    else:
        for k, x in enumerate(rest):
            x.group_order = k
    db.flush()


def _delete_facility(db: Session, f: SitokFacility) -> None:
    """계약·회차·올린 서류·만든 보고서 폴더까지 + 이 시설물 카드에 든 서류 자동화 계약(계약 폴더까지, 10/15 민재형 — 예전엔 연결만 끊겨 "카드 없음"으로 남았음).
    묶음의 동이면(10/16) 계약은 지우지 않고 다음 동에 넘김 — 잘못 등록한 동을 지워도 묶음 계약은 그대로."""
    from core.models_web import SitokDocContract
    from server.api.routers.sitok_docs import folder as doc_folder

    folder = _facility_dir(f)
    group_id = f.group_id
    heir = _heir(db, f)
    if heir is not None:
        _pass_contracts(db, f, heir)
        db.delete(f)
        db.flush()
        _regroup(db, group_id)
        shutil.rmtree(folder, ignore_errors=True)
        return
    for d in db.query(SitokDocContract).filter(SitokDocContract.company_id == f.company_id).all():
        ids = [int(x) for x in (d.facility_ids or ([d.facility_id] if d.facility_id else []))]
        if f.id not in ids:
            continue
        rest = [x for x in ids if x != f.id]
        if rest:  # 계약 하나에 시설물 여럿(0052) — 이 시설물만 뺌
            d.facility_ids, d.facility_id = rest, rest[0]
            d.amounts = {k: v for k, v in (d.amounts or {}).items() if str(k) != str(f.id)} or None
            d.report_contracts = {k: v for k, v in (d.report_contracts or {}).items() if str(k) != str(f.id)} or None
            continue
        shutil.rmtree(doc_folder(d), ignore_errors=True)
        db.delete(d)
    db.query(SitokContract).filter(SitokContract.facility_id == f.id).delete()
    db.delete(f)
    db.flush()
    shutil.rmtree(folder, ignore_errors=True)


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


# ---------- 발주처 과업지시서(0060, 민재형 10/21) ----------
# 원칙은 발주처가 과업지시서를 주는 것 — 올리면 옹벽 보고서 부록3에 우리 과업지시서 대신 그 PDF를 끼우고, 납품 항목(책자·USB)을 읽어
# 과업수행계획서 5. 과업성과물 납품 항목에 넣음(못 읽으면·없으면 점검자가 직접, 기본 책자 -·USB -·비고 협의).

class DeliverIn(BaseModel):
    book: str = "-"
    usb: str = "-"
    note: str = "협의"


@router.post("/contracts/{contract_id}/order")
def order_upload(contract_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from server.sitok import wall_order

    c = _require_contract(db, user, contract_id)
    f = db.get(SitokFacility, c.facility_id)
    data = file.file.read()
    if not data.startswith(b"%PDF"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "PDF 파일만 올릴 수 있습니다.")
    dest = _facility_dir(f) / f"과업지시서_{c.id}.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    c.order_pdf = str(dest)
    got = wall_order.read_deliver(dest, user.company_id)
    c.deliver = dict(got) if got else dict(wall_order.DEFAULT)
    db.commit()
    return _facility_out(db, f)


@router.delete("/contracts/{contract_id}/order")
def order_delete(contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _require_contract(db, user, contract_id)
    if c.order_pdf:
        Path(c.order_pdf).unlink(missing_ok=True)
    c.order_pdf = ""
    db.commit()
    return _facility_out(db, db.get(SitokFacility, c.facility_id))


@router.patch("/contracts/{contract_id}/deliver")
def deliver_save(contract_id: int, body: DeliverIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _require_contract(db, user, contract_id)
    c.deliver = {"book": body.book.strip() or "-", "usb": body.usb.strip() or "-", "note": body.note.strip() or "협의", "src": "manual"}
    db.commit()
    return _facility_out(db, db.get(SitokFacility, c.facility_id))


# ---------- 위치도(10/21 형 — 옹벽은 주소와 자리가 다름): 시설물 화면 지도에서 핀을 끌어 저장(ledger.wall.lat/lng) 또는 밖에서 만든 그림 올리기 ----------
# 보고서 1.2.2·서두·과업수행계획서 위치도 = 올린 그림 > 핀 좌표 지도 > 주소 지도(server/sitok/locmap.facility_map).

class PinIn(BaseModel):
    lat: float
    lng: float
    zoom: int | None = None  # 화면 지도 확대 단계 — 보고서 위치도도 이 단계로(10/26 형 "축척 상이")


def _locmap_out(f: SitokFacility) -> dict:
    from server.api import geocode
    from server.sitok import locmap

    pin = locmap.pin_of(f)
    addr, rough = None, ""
    try:
        g = geocode.geocode(f.address or "") if f.address else None
        addr = [g[0], g[1]] if g else None
        rough = locmap.rough(f.address or "") if g else ""
    except Exception:  # noqa: BLE001
        addr = None
    return {"pin": [pin[0], pin[1]] if pin else None, "zoom": locmap.zoom_of(f), "address": addr, "rough": rough, "has_image": (_facility_dir(f) / locmap.UPLOADED).exists(),
            "src": "image" if (_facility_dir(f) / locmap.UPLOADED).exists() else "pin" if pin else "address" if addr else ""}


@router.get("/locmap/search")
def locmap_search(q: str = "", user: User = Depends(get_current_user)):
    """위치도 핀 옮기기용 주소·이름 검색(카카오 로컬 — 키워드 먼저, 주소 다음) → [{name, address, lat, lng}] 10개까지."""
    from server.api import geocode

    q = " ".join((q or "").split())[:80]
    if len(q) < 2:
        return {"items": []}
    out, seen = [], set()
    try:
        for url, kind in ((geocode._URL_KEYWORD, "place"), (geocode._URL_ADDR, "addr")):
            for d in geocode._search(url, q)[:8]:
                lat, lng = round(float(d["y"]), 6), round(float(d["x"]), 6)
                if (lat, lng) in seen:
                    continue
                seen.add((lat, lng))
                road = (d.get("road_address") or {}).get("address_name") if isinstance(d.get("road_address"), dict) else d.get("road_address_name")
                out.append({"name": d.get("place_name") or d.get("address_name") or q, "address": road or d.get("address_name") or "", "lat": lat, "lng": lng})
    except Exception as err:  # noqa: BLE001 — 키 없음·카카오 안 됨
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"주소 검색이 안 됩니다: {str(err)[:80]}") from err
    return {"items": out[:10]}


@router.get("/facilities/{facility_id}/locmap")
def locmap_get(facility_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _locmap_out(_require_facility(db, user, facility_id))


@router.put("/facilities/{facility_id}/locmap")
def locmap_pin(facility_id: int, body: PinIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = _require_facility(db, user, facility_id)
    led = dict(f.ledger or {})
    led["wall"] = {**(led.get("wall") or {}), "lat": round(body.lat, 6), "lng": round(body.lng, 6)}
    if body.zoom and 10 <= body.zoom <= 19:
        led["wall"]["zoom"] = int(body.zoom)
    f.ledger = led
    db.commit()
    return _locmap_out(f)


@router.delete("/facilities/{facility_id}/locmap")
def locmap_unpin(facility_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = _require_facility(db, user, facility_id)
    led = dict(f.ledger or {})
    led["wall"] = {k: v for k, v in (led.get("wall") or {}).items() if k not in ("lat", "lng", "zoom")}
    f.ledger = led
    db.commit()
    return _locmap_out(f)


@router.post("/facilities/{facility_id}/locmap/image")
def locmap_image(facility_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from server.contract_docs import files
    from server.sitok import locmap

    f = _require_facility(db, user, facility_id)
    data = file.file.read()
    dest = _facility_dir(f) / locmap.UPLOADED
    dest.parent.mkdir(parents=True, exist_ok=True)
    if data.startswith(b"%PDF"):
        import pymupdf

        with pymupdf.open(stream=data, filetype="pdf") as pdf:
            data = pdf[0].get_pixmap(dpi=150).tobytes("jpg")
    try:
        files.save_jpeg(data, file.filename or "x.jpg", dest)
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"그림을 읽지 못했습니다: {str(err)[:100]}") from err
    return _locmap_out(f)


@router.delete("/facilities/{facility_id}/locmap/image")
def locmap_image_delete(facility_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from server.sitok import locmap

    f = _require_facility(db, user, facility_id)
    (_facility_dir(f) / locmap.UPLOADED).unlink(missing_ok=True)
    return _locmap_out(f)


@router.get("/files/locmap/{facility_id}")
def locmap_file(facility_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """보고서에 들어갈 위치도 그림(올린 그림 > 핀 > 주소) — 화면 미리보기."""
    from server.sitok import locmap

    f = _require_facility(db, user, facility_id)
    p = locmap.facility_map(f, _facility_dir(f))
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "위치도를 만들지 못했습니다(주소로 좌표를 못 찾음) — 지도에서 핀을 찍어 저장하세요.")
    return FileResponse(p, media_type="image/jpeg", filename=f"위치도_{f.id}.jpg", content_disposition_type="inline")


@router.get("/files/order/{contract_id}")
def order_file(contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _require_contract(db, user, contract_id)
    if not c.order_pdf or not Path(c.order_pdf).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "올린 과업지시서가 없습니다.")
    return FileResponse(c.order_pdf, media_type="application/pdf", filename=f"과업지시서_{c.id}.pdf", content_disposition_type="inline")
