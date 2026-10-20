"""서류 자동화 — 용역 계약과 착수계·완수계(2026-10-06). 계약은 현장 없이 먼저 생기고(착수계가 현장 등록보다 먼저 — 형), 나중에 현장과 연결한다.

- `GET /contracts` — 계약 목록(관리번호·단계·제출·착수일·완수일·연결 현장), `GET /contracts/next-management-no` — 관리번호 자동생성 — 서류 자동화 계약 목록·제출 현황·일정 달력이 같이 씀
- `POST /contracts` (빈 계약) / `POST /contracts/from-pdf` (용역계약서 PDF로 새 계약 — 글자 규칙, 못 읽은 칸은 Claude API)
- `POST /contracts/new-card` — [+ 새 계약](10/20 형): 용역계약서(선택) + 현장별 K2B 기술지도계약서 n개 → 계약 카드 + 현장 카드(n곳이면 26-69-1…) 함께
- `GET /contracts/{id}/change` · `POST …/change/read/{service|guide}`(첨부 읽기만) · `POST …/change` — [+ 계약변경](10/20 형, 공기연장 등):
  용역 기간·금액 + 현장별 공사기간·금액·지도 횟수를 같이 바꾸고 차수별 기록(service_contract.changes), 변경 계약서는 계약 폴더 "계약변경/N차/"
- `GET|PUT|DELETE /contracts/{id}` — 창에 필요한 것 전부 / 계약 값 저장 / 지우기(파일까지, 삭제 비밀번호)
- `POST /contracts/{id}/pdf` — 계약서 PDF 다시 올리기(읽은 칸만 덮어씀)
- `POST /contracts/{id}/link {site_id, on}` — 현장 연결·해제(계약 하나에 현장 여럿, 현장 하나는 계약 하나 — contract_site 0057, 같은 번호는 자동)
- `POST /contracts/{id}/docs/{start|done}` — 엑셀 + 합본 PDF(LibreOffice + 붙임 파일), `GET …/docs/{kind}.{xlsx|pdf}` — 받기
  완수계는 붙임에 완수내역서가 있을 때만 "검사 및 납품조서"(한글 양식, inspection.py)도 — 표 값은 완수내역서에서 읽어 계약에 둠,
  `GET …/docs/done.hwpx` — 한글 받기
- `POST|GET|DELETE /contracts/{id}/docs/{kind}/attach/{칸}[/{파일}]` — 붙임 파일(attachments.py)
- `POST /contracts/{id}/submit/{kind}` {method: email|direct|post} — 제출 기록(E-mail은 합본 PDF를 바로 보냄), `DELETE …/submit/{기록}`
- `GET /sites/{id}/contract` — 현장 화면 버튼: 연결된 계약, 없으면 연결할 후보(비슷한 이름 순)
"""
from __future__ import annotations

import datetime
import tempfile
from pathlib import Path
from typing import Literal

import openpyxl
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core import config
from core.models_db import Site
from core.models_web import ContractSubmit, ServiceContract, TechPerson, User
from server.api import contract_sites, mailer, repo
from server.api.deps import get_current_user, get_db
from server.api.security import verify_password
from server.api.routers.contract_library import company_docs, doc_status, person_docs, persons
from server.api.site_label import short_mgmt, site_label
from server.contract_docs import attachments, build, contract_ai, contract_pdf, contract_status, files, hwp_queue, inspection, to_pdf

router = APIRouter(prefix="/contracts", tags=["contracts"])
site_router = APIRouter(prefix="/sites/{site_id}", tags=["contracts"])

KIND_LABEL = {"start": "착수계", "done": "완수계"}
INSP_NAME = "검사및납품조서"  # 완수계 붙임 5번 — 계약 폴더에 .hwpx(받기)·.pdf(합본에 들어감)
CONTRACT_FIELDS = ("client", "title", "contract_no", "amount", "contract_date", "start_date", "end_date", "settle_amount",
                   "actual_end_date")
DATE_FIELDS = {"contract_date", "start_date", "end_date", "actual_end_date"}
CONTACT_FIELDS = ("client_manager", "client_phone", "client_email",  # 발주처 계약 담당자(계약부서)
                  "biz_manager", "biz_phone", "biz_email")  # 발주처 사업 담당자(사업부서 — E-mail 기본 받는 사람). 서류엔 안 들어감


class ContractIn(BaseModel):
    management_no: str | None = None
    client_manager: str | None = None
    client_phone: str | None = None
    client_email: str | None = None
    biz_manager: str | None = None
    biz_phone: str | None = None
    biz_email: str | None = None
    client: str | None = None
    title: str | None = None
    contract_no: str | None = None
    amount: int | None = None
    contract_date: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    settle_amount: int | None = None
    actual_end_date: str | None = None
    inspection: dict | None = None  # 검사 및 납품조서 표(inspection.KEYS)


def _iso(d) -> str:
    return d.isoformat() if d else ""


def _require(db: Session, user: User, contract_id: int) -> ServiceContract:
    row = db.get(ServiceContract, contract_id)
    if row is None or row.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "용역 계약을 찾을 수 없습니다.")
    return row




def _contract_values(row: ServiceContract) -> build.Contract:
    return build.Contract(**{k: getattr(row, k) for k in CONTRACT_FIELDS})


def _submits(db: Session, row: ServiceContract) -> dict[str, list[dict]]:
    """서류별 제출 기록(오래된 것부터) — {"start": [{id, method, label, date, to}], "done": [...]}."""
    out: dict[str, list[dict]] = {k: [] for k in KIND_LABEL}
    if not row.id:
        return out
    for r in db.query(ContractSubmit).filter(ContractSubmit.contract_id == row.id).order_by(ContractSubmit.submitted_on, ContractSubmit.id):
        out.setdefault(r.kind, []).append({"id": r.id, "method": r.method, "label": contract_status.METHODS.get(r.method, r.method),
                                           "date": r.submitted_on.isoformat(), "to": r.to_addr})
    return out


def _made(db: Session, row: ServiceContract) -> dict:
    out = {}
    subs = _submits(db, row)
    for kind, label in KIND_LABEL.items():
        at = row.start_made_at if kind == "start" else row.done_made_at
        pdf = files.out_path(row, f"{label}.pdf").exists()
        out[kind] = {"at": at.strftime("%Y-%m-%d %H:%M") if at else "", "xlsx": files.out_path(row, f"{label}.xlsx").exists(),
                     "pdf": pdf, "submits": subs[kind], "submitted": contract_status.submitted(subs[kind]),
                     "hwpx": kind == "done" and files.out_path(row, f"{INSP_NAME}.hwpx").exists()}
    return out


def next_management_no(db: Session, company_id: int, year: int | None = None) -> str:
    """계약 관리번호 자동생성 — "YY-N"(10/20 형 "마지막 번호 다음 번호" — 계약·현장 통틀어, 26-68 → 26-69). 전엔 "2026-0000001"(10/6 가안)."""
    return contract_sites.next_no(db, company_id, year)


def contract_label(row: ServiceContract) -> str:
    """화면 이름 "26-3)_용역명"(현장 이름과 같은 모양 — site_label)."""
    short = short_mgmt(row.management_no)
    title = row.title or "(용역명 없음)"
    return f"{short})_{title}" if short else title


def summary(db: Session, row: ServiceContract) -> dict:
    """목록 한 줄(계약 목록·제출 현황·일정 달력). 현장은 여럿일 수 있음(sites) — site_id·site_label은 첫 현장(예전 화면 호환)."""
    made = _made(db, row)
    sites = contract_sites.sites_of(db, row.id) if row.id else []
    dates = contract_status.plan_dates(row)
    return {
        "id": row.id, "title": row.title, "management_no": row.management_no or "", "label": contract_label(row),
        "short_no": short_mgmt(row.management_no), "invoice_date": _iso(row.invoice_date),
        **{k: getattr(row, k) or "" for k in CONTACT_FIELDS}, "client": row.client, "contract_no": row.contract_no, "amount": row.amount,
        "contract_date": _iso(row.contract_date), "start_date": _iso(row.start_date), "end_date": _iso(row.end_date),
        "site_id": sites[0].id if sites else None,
        "site_label": (site_label(sites[0]) + (f" 외 {len(sites) - 1}곳" if len(sites) > 1 else "")) if sites else "",
        "sites": [{"id": s.id, "label": site_label(s)} for s in sites], "changes": last_change_no(row),
        "stage": contract_status.stage(made["start"]["submitted"], made["done"]["submitted"]),
        "made": made, "dates": {k: _iso(v) for k, v in dates.items()},
        "created_at": row.created_at.strftime("%Y-%m-%d") if row.created_at else "",
    }


@router.get("/next-management-no")
def get_next_management_no(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """[자동생성] — 저장은 안 함."""
    return {"management_no": next_management_no(db, user.company_id)}


@router.get("")
def list_contracts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from core.models_web import ContractView

    contract_sites.auto_link(db, user.company_id)  # 같은 관리번호 현장과 자동으로(10/20 형)
    rows = db.query(ServiceContract).filter(ServiceContract.company_id == user.company_id).order_by(ServiceContract.id.desc()).all()
    seen = {k: v.isoformat(timespec="seconds") for k, v in db.query(ContractView.contract_id, ContractView.viewed_at).filter(ContractView.user_id == user.id)}
    return {"contracts": [summary(db, r) | {"viewed_at": seen.get(r.id, "")} for r in rows], "stages": contract_status.STAGES}


def mark_view(db: Session, user_id: int, contract_id: int) -> None:
    """계약 목록 "최근 열람순" — 착수계·완수계 창을 열면 지금으로(실패해도 창은 열리게)."""
    from core.models_web import ContractView

    try:
        v = db.get(ContractView, (user_id, contract_id))
        if v is None:
            db.add(ContractView(user_id=user_id, contract_id=contract_id, viewed_at=datetime.datetime.now()))
        else:
            v.viewed_at = datetime.datetime.now()
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()


class InvoiceIn(BaseModel):
    date: str | None = None  # 계산서 발행일(비우면 지움)


@router.post("/{contract_id}/invoice")
def set_invoice(contract_id: int, body: InvoiceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """제출 현황 계산서 발행일(사용자 10/15 "계산서 발행 날짜 달력")."""
    row = _require(db, user, contract_id)
    try:
        row.invoice_date = datetime.date.fromisoformat(body.date[:10]) if body.date else None
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "날짜 형식이 아닙니다.") from err
    db.commit()
    return summary(db, row)


def _new(db: Session, user: User) -> ServiceContract:
    row = ServiceContract(company_id=user.company_id, client="", title="", contract_no="", contract_pdf="", updated_by=user.display_name or "",
                          management_no=next_management_no(db, user.company_id),  # 만들 때 자동(고칠 수 있음)
                          created_at=datetime.datetime.now(), updated_at=datetime.datetime.now())
    db.add(row)
    db.flush()
    return row


@router.post("")
def create_contract(body: ContractIn | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """새 계약 — 창([+ 새 계약])에서 처음 무언가 할 때(붙임 올리기·현장 연결·착수계 만들기) 그때까지 적은 값으로 만든다."""
    row = _new(db, user)
    if body is not None:
        _apply_contract(row, body.model_dump(exclude_unset=True), user)
    db.commit()
    return state(db, user, row)


@router.get("/blank")
def blank_contract(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """[+ 새 계약] 창의 빈 화면 — DB에 행을 만들지 않는다(아무것도 안 하고 닫으면 빈 계약이 안 남게, 10/6 사용자). id 0 = 아직 없음."""
    row = ServiceContract(id=0, company_id=user.company_id, client="", title="", contract_no="", contract_pdf="", participant_ids=[],
                          management_no=next_management_no(db, user.company_id))  # 미리 보여 주기만(만들 때 다시 셈)
    return state(db, user, row)


def _parse_service(data: bytes, company_id: int) -> tuple[dict, list[str], str]:
    """용역계약서 PDF → (읽은 칸, AI로 채운 칸, AI 오류) — 글자 규칙, 못 읽은 중요한 칸만 Claude API(10/6). 계약에 넣지는 않음."""
    if data[:4] != b"%PDF":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "용역계약서 PDF 파일을 올리세요.")
    ai_filled: list[str] = []
    ai_error = ""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "c.pdf"
        src.write_bytes(data)
        try:
            parsed = contract_pdf.parse_pdf(src)
        except Exception:  # noqa: BLE001
            parsed = {k: None for k in contract_ai.KEY_FIELDS + ("contract_date",)}
        if contract_ai.needs_ai(parsed):
            try:
                for k, v in contract_ai.read_with_ai(src, company_id).items():
                    if v and not parsed.get(k):
                        parsed[k] = v
                        ai_filled.append(k)
            except Exception as err:  # noqa: BLE001
                ai_error = str(err).splitlines()[0][:200] if str(err) else type(err).__name__
    return parsed, ai_filled, ai_error


def _read_pdf(db: Session, user: User, row: ServiceContract, data: bytes) -> dict:
    parsed, ai_filled, ai_error = _parse_service(data, user.company_id)
    found = {k: (_iso(v) if k in DATE_FIELDS else v) for k, v in parsed.items() if v}
    _apply_contract(row, found, user)
    db.flush()
    dest = files.out_path(row, "용역계약서.pdf")  # 용역명이 채워진 뒤 폴더 이름이 정해지게
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    row.contract_pdf = str(dest)
    return {"read": sorted(found), "unread": [k for k in parsed if not parsed[k]], "ai_filled": ai_filled, "ai_error": ai_error}


@router.post("/from-pdf")
def create_from_pdf(file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = file.file.read()
    row = _new(db, user)
    info = _read_pdf(db, user, row, data)
    same = (db.query(ServiceContract).filter(ServiceContract.company_id == user.company_id, ServiceContract.id != row.id,
                                             ServiceContract.contract_no == row.contract_no).first() if row.contract_no else None)
    db.commit()
    out = state(db, user, row) | info
    if same is not None:
        out["duplicate_of"] = {"id": same.id, "title": same.title}
    return out


def _read_guide(data: bytes, company_id: int) -> dict:
    """K2B 기술지도계약서 PDF → 현장 칸(현장 등록 [AI로 자동 채우기]와 같은 core.contract_analyzer — 20초쯤)."""
    from core.contract_analyzer import extract_site_info

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "guide.pdf"
        src.write_bytes(data)
        return extract_site_info(src, company_id=company_id)


def _site_fields(found: dict, name: str, management_no: str) -> dict:
    """읽은 값 → Site 칸(날짜·숫자는 모양이 맞을 때만)."""
    from server.schemas.site import SiteIn

    out = {}
    for k in SiteIn.model_fields:
        v = found.get(k)
        if v in (None, ""):
            continue
        if k in ("period_start", "period_end"):
            try:
                v = datetime.date.fromisoformat(str(v)[:10])
            except ValueError:
                continue
        elif k in ("amount", "total_guidance_count", "assigned_staff_id"):
            try:
                v = int(v)
            except (TypeError, ValueError):
                continue
        out[k] = v
    out["name"] = (out.get("name") or name).strip() or name
    out["management_no"] = management_no
    return out


def _guide_period(found: dict) -> dict:
    """읽은 기술지도계약서 → 기술지도 계약기간 {contract_start, contract_end}(날짜 모양일 때만 — site_contact, 우리 계약기간 첫 기준)."""
    out = {}
    for k in ("contract_start", "contract_end"):
        try:
            out[k] = datetime.date.fromisoformat(str(found.get(k) or "")[:10])
        except ValueError:
            pass
    return out


@router.post("/new-card")
def create_card(guides: list[UploadFile] = File(...), service: UploadFile | None = File(None), management_no: str = Form(""),
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """[+ 새 계약](10/20 형 "새 계약은 카드를 만드는 데 쓴다 — 첨부 = 용역계약서 + 기술지도계약서, 용역계약서를 안 쓰면 기술지도계약서만"):
    계약 카드 + 현장 카드를 함께. 관리번호 = 마지막 번호 다음(계약·현장 통틀어, 26-69), 현장이 여럿이면 26-69-1·26-69-2…(현장 목록에서 한 카드).
    기술지도계약서는 현장 등록과 같은 AI 읽기(하나에 20초쯤 — 6개씩 같이, 그룹웨어 통로 180초 안). 하나라도 못 읽으면 아무것도 안 만듦.
    용역계약서가 없으면 계약 이름 = 첫 현장 이름(외 N곳). 착수계 창은 안 엶 — 카드의 [📑 착수계]로."""
    from concurrent.futures import ThreadPoolExecutor

    from server.api.site_status import NEW_SITE

    gdata = [(g.filename or f"기술지도계약서{k}.pdf", g.file.read()) for k, g in enumerate(guides, 1)]
    if not gdata:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "기술지도계약서 PDF를 하나 이상 올리세요.")
    bad = [n for n, d in gdata if not d.startswith(b"%PDF")]
    if bad:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"PDF가 아닌 파일: {', '.join(bad)}")
    sdata = service.file.read() if service is not None else b""
    if sdata and not sdata.startswith(b"%PDF"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "용역계약서는 PDF로 올리세요.")
    if not config.has_api_key(user.company_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Claude API 키가 없어 기술지도계약서를 읽을 수 없습니다 — 설정에서 먼저 넣으세요.")
    no = short_mgmt((management_no or "").strip()) or contract_sites.next_no(db, user.company_id)
    taken = [r for r in db.query(ServiceContract).filter(ServiceContract.company_id == user.company_id) if short_mgmt(r.management_no) == no] + \
        [s for s in db.query(Site).filter(Site.company_id == user.company_id) if contract_sites.number_match(no, s.management_no)]
    if taken:
        raise HTTPException(status.HTTP_409_CONFLICT, f"관리번호 {no}가 이미 있습니다 — 다른 번호를 쓰거나 비워 두세요(자동 = {contract_sites.next_no(db, user.company_id)}).")

    def read(item):
        try:
            return _read_guide(item[1], user.company_id), ""
        except Exception as err:  # noqa: BLE001 — 어느 파일이 왜 안 됐는지 화면에
            return None, str(err).splitlines()[0][:160] if str(err) else type(err).__name__

    with ThreadPoolExecutor(min(6, len(gdata))) as ex:
        results = list(ex.map(read, gdata))
    failed = [f"{n}({e})" for (n, _), (found, e) in zip(gdata, results) if found is None]
    if failed:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "기술지도계약서를 읽지 못했습니다: " + " / ".join(failed) + " — 아무것도 만들지 않았습니다.")
    row = _new(db, user)
    row.management_no = no
    info = _read_pdf(db, user, row, sdata) if sdata else {}
    many = len(gdata) > 1
    periods = [_guide_period(found) for found, _ in results]
    if not sdata:  # 용역계약서 없이(민간 등) — 계약 이름은 현장에서, 착수·완수는 기술지도계약서 계약기간(여럿이면 가장 이른 시작~가장 늦은 끝, 10/20 사용자)
        first = (results[0][0] or {}).get("name") or Path(gdata[0][0]).stem
        row.title = f"{first} 외 {len(gdata) - 1}곳" if many else first
        starts, ends = [g["contract_start"] for g in periods if "contract_start" in g], [g["contract_end"] for g in periods if "contract_end" in g]
        row.start_date, row.end_date = (min(starts) if starts else None), (max(ends) if ends else None)
    db.flush()
    made = []
    for k, ((fname, data), (found, _)) in enumerate(zip(gdata, results), 1):
        mno = f"{no}-{k}" if many else no
        site = Site(company_id=user.company_id, status=NEW_SITE, **_site_fields(found, Path(fname).stem, mno))
        db.add(site)
        db.flush()
        contract_sites.link(db, row, site)
        if periods[k - 1]:  # 기술지도 계약기간(우리 계약기간 — 자동 배치·공기 경과)
            sc = contract_sites.site_contact_row(db, site.id)
            sc.contract_start, sc.contract_end = periods[k - 1].get("contract_start"), periods[k - 1].get("contract_end")
        dest = files.out_path(row, f"기술지도계약서_{mno}.pdf")  # 계약 폴더에 원본(계약변경 때 비교)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        made.append({"id": site.id, "label": site_label(site)})
    db.commit()
    return state(db, user, row) | info | {"created_sites": made}


# ---------- [+ 계약변경](10/20 형 — 공기연장 등으로 용역기간이 바뀜: 서류 카드에서 바꾸면 현장 카드도, 변경 용역계약서·기술지도계약서 첨부) ----------
CHANGE_CONTRACT = ("contract_date", "start_date", "end_date", "amount")
CHANGE_SITE = ("contract_start", "contract_end", "period_start", "period_end", "amount", "total_guidance_count")
SITE_CONTACT_KEYS = ("contract_start", "contract_end")  # 기술지도 계약기간 — site_contact(0058), 나머지는 Site 칸
CHANGE_LABEL = {"contract_date": "계약일", "start_date": "착수일", "end_date": "완수일", "amount": "계약금액",
                "contract_start": "계약 시작", "contract_end": "계약 종료",
                "period_start": "공사 시작", "period_end": "공사 종료", "total_guidance_count": "지도 총 횟수"}


def _site_val(db: Session, s: Site, k: str):
    if k in SITE_CONTACT_KEYS:
        from core.models_web import SiteContact

        sc = db.get(SiteContact, s.id)
        return getattr(sc, k) if sc else None
    return getattr(s, k)


def _set_site_val(db: Session, s: Site, k: str, v) -> None:
    setattr(contract_sites.site_contact_row(db, s.id) if k in SITE_CONTACT_KEYS else s, k, v)


def _val(v):
    return _iso(v) if isinstance(v, datetime.date) else v


def last_change_no(row: ServiceContract) -> int:
    """마지막 계약변경 차수(0 = 없음). 기록 수가 아니라 차수 — 착수계에 넣었던 변경 계약서를 옮긴 기록은 나라장터 계약번호 끝(-03 = 3차)부터라
    앞 차수가 비어 있을 수 있음(10/20)."""
    return max((int(c.get("no") or 0) for c in row.changes or []), default=0)


def _change_view(db: Session, row: ServiceContract) -> dict:
    sites = contract_sites.sites_of(db, row.id)
    return {"next_no": last_change_no(row) + 1, "contract": {k: _val(getattr(row, k)) for k in CHANGE_CONTRACT},
            "sites": [{"id": s.id, "label": site_label(s), **{k: _val(_site_val(db, s, k)) for k in CHANGE_SITE}} for s in sites],
            "history": row.changes or [], "labels": CHANGE_LABEL}


@router.get("/{contract_id}/change")
def get_change(contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _change_view(db, _require(db, user, contract_id))


@router.post("/{contract_id}/change/read/{kind}")
def read_change(contract_id: int, kind: Literal["service", "guide"], file: UploadFile = File(...), user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """변경 계약서 읽기만(창 칸 채우기 — 저장은 [변경 저장]). service = 용역계약서(변경) 글자 규칙 + AI, guide = 기술지도계약서(변경) AI(20초쯤)."""
    _require(db, user, contract_id)
    data = file.file.read()
    if kind == "service":
        parsed, ai_filled, ai_error = _parse_service(data, user.company_id)
        return {"values": {k: _val(parsed.get(k)) for k in CHANGE_CONTRACT if parsed.get(k)}, "ai_filled": ai_filled, "ai_error": ai_error}
    if not data.startswith(b"%PDF"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "기술지도계약서 PDF를 올리세요.")
    if not config.has_api_key(user.company_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Claude API 키가 없어 기술지도계약서를 읽을 수 없습니다 — 칸을 직접 고치세요.")
    try:
        found = _read_guide(data, user.company_id)
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"기술지도계약서를 읽지 못했습니다: {str(err).splitlines()[0][:160]}") from err
    fields = _site_fields(found, "", "") | _guide_period(found)
    return {"values": {k: _val(fields[k]) for k in CHANGE_SITE if k in fields}}


def _parse_change(v, key: str):
    if v in (None, ""):
        return None
    if key in ("amount", "total_guidance_count"):
        try:
            return int(str(v).replace(",", ""))
        except ValueError as err:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{CHANGE_LABEL[key]}에는 숫자만 적으세요.") from err
    try:
        return datetime.date.fromisoformat(str(v)[:10])
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{CHANGE_LABEL[key]} 날짜 형식이 아닙니다: {v}") from err


@router.post("/{contract_id}/change")
def save_change(contract_id: int, data: str = Form(...), service: UploadFile | None = File(None), guides: list[UploadFile] | None = File(None),
                guide_ids: str = Form(""), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """[변경 저장] — data = {reason, contract: {칸: 값}, sites: {현장 id: {칸: 값}}}(창에 보인 값 전부), service = 용역계약서(변경), guides + guide_ids =
    현장별 기술지도계약서(변경). 바뀐 칸만 계약·현장에 넣고 차수 기록(전·후 값, 첨부 파일). 공기 경과·자동 배치는 바뀐 우리 계약기간으로
    (contract_sites.our_periods — 현장 계약 시작·종료 → 용역 착수·완수 → 공사기간)."""
    import json

    row = _require(db, user, contract_id)
    try:
        body = json.loads(data)
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "보낸 값을 읽지 못했습니다.") from err
    sites = {s.id: s for s in contract_sites.sites_of(db, row.id)}
    before, after = {"contract": {}, "sites": {}}, {"contract": {}, "sites": {}}
    for k, v in (body.get("contract") or {}).items():
        if k in CHANGE_CONTRACT:
            new = _parse_change(v, k)
            if new != getattr(row, k):
                before["contract"][k], after["contract"][k] = _val(getattr(row, k)), _val(new)
                setattr(row, k, new)
    for sid, vals in (body.get("sites") or {}).items():
        s = sites.get(int(sid))
        if s is None:
            continue
        for k, v in (vals or {}).items():
            if k in CHANGE_SITE:
                new, old = _parse_change(v, k), _site_val(db, s, k)
                if new != old:
                    before["sites"].setdefault(str(s.id), {})[k] = _val(old)
                    after["sites"].setdefault(str(s.id), {})[k] = _val(new)
                    _set_site_val(db, s, k, new)
    ids = [int(x) for x in guide_ids.split(",") if x.strip().isdigit()]
    uploads = [("service", service)] if service is not None else []
    uploads += [(f"guide:{sid}", g) for sid, g in zip(ids, guides or [])]
    if not (after["contract"] or after["sites"] or uploads):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "바뀐 칸도 첨부한 변경 계약서도 없습니다.")
    no = last_change_no(row) + 1
    folder = files.contract_dir(row) / "계약변경" / f"{no}차"
    saved = []
    for key, f in uploads:
        data_ = f.file.read()
        if not data_.startswith(b"%PDF"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"PDF가 아닌 파일: {f.filename}")
        if key == "service":
            name = "용역계약서(변경).pdf"
        else:
            s = sites.get(int(key.split(":")[1]))
            name = f"기술지도계약서(변경)_{short_mgmt(s.management_no) if s else key.split(':')[1]}.pdf"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(data_)
        saved.append(name)
    entry = {"no": no, "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "by": user.display_name or "", "reason": (body.get("reason") or "").strip(),
             "before": before, "after": after, "files": saved}
    row.changes = (row.changes or []) + [entry]
    row.updated_at, row.updated_by = datetime.datetime.now(), user.display_name or ""
    db.commit()
    return _change_view(db, row) | {"saved": entry}


@router.get("/{contract_id}/change/{no}/{name}")
def view_change_file(contract_id: int, no: int, name: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _require(db, user, contract_id)
    path = files.contract_dir(row) / "계약변경" / f"{no}차" / Path(name).name
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일이 없습니다.")
    return FileResponse(path, media_type="application/pdf", filename=path.name, content_disposition_type="inline")


def state(db: Session, user: User, row: ServiceContract) -> dict:
    """착수계·완수계 창에 필요한 것 전부."""
    c = _contract_values(row)
    today = datetime.date.today()
    docs = company_docs(db, user.company_id)
    return summary(db, row) | {
        "contract": {k: (_iso(v) if k in DATE_FIELDS else v) for k, v in vars(c).items()}
        | {"has_pdf": files.out_path(row, "용역계약서.pdf").exists()},
        "defaults": {
            "greeting": build.greeting_word(c.client),
            "doc_no_start": build.default_doc_no(c, c.start_date),
            "doc_no_done": build.default_doc_no(c, today),
            "send_date": today.isoformat(),
            "contact_name": config.get_doc_contact_name(user.company_id),
        },
        "agent_id": row.agent_id,
        "participant_ids": row.participant_ids or [],
        "persons": [_person_state(db, p) for p in persons(db, user.company_id) if p.active],
        "company_docs": [{"kind": k, "label": label, "status": doc_status(docs.get(k)),
                          "valid_until": _iso(docs[k].valid_until) if k in docs else ""} for k, label in build.COMPANY_DOCS],
        "attachments": {kind: _attach_list(row, kind) for kind in KIND_LABEL},
        "inspection": inspection.normalize(row.inspection) if row.inspection else None,
    }


def _done_list_files(row: ServiceContract) -> list[Path]:
    return attachments.list_files(files.contract_dir(row), "done", "done_list") if row.id else []


def _read_inspection(row: ServiceContract, overwrite_settle: bool) -> bool:
    """붙임 완수내역서에서 검사 및 납품조서 표 값을 읽어 계약에 둔다. 준공 계 = 정산금액(사용자 10/8 — 완수계 서류끼리 같은 값)."""
    found = inspection.read_done_list(_done_list_files(row))
    if not found:
        return False
    row.inspection = found
    total = inspection.normalize(found)["done_total"]
    if total is not None and (overwrite_settle or row.settle_amount is None):
        row.settle_amount = total
    return True


def _person_state(db: Session, p: TechPerson) -> dict:
    docs = person_docs(db, p.id)
    return {"id": p.id, "name": p.name, "qualification": p.qualification, "grade": p.grade,
            "missing": [label for k, label in build.PERSON_DOCS if not doc_status(docs.get(k))],
            "expired": [label for k, label in build.PERSON_DOCS if doc_status(docs.get(k)) == "expired"],
            "nodate": [label for k, label in build.PERSON_DOCS if doc_status(docs.get(k)) == "nodate"]}


@router.get("/{contract_id}")
def get_contract(contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _require(db, user, contract_id)
    if row.inspection is None and _read_inspection(row, overwrite_settle=False):  # 이 기능 전에 올린 완수내역서(10/8)
        db.commit()
    mark_view(db, user.id, row.id)
    return state(db, user, row)


def _apply_contract(row: ServiceContract, fields: dict, user: User) -> None:
    for key in ("management_no",) + CONTACT_FIELDS:  # 서류 값(build.Contract)이 아니라 화면·연락용이라 따로
        if key in fields:
            setattr(row, key, (fields[key] or "").strip())
    for k, v in fields.items():
        if k not in CONTRACT_FIELDS:
            continue
        if k in DATE_FIELDS:
            try:
                v = datetime.date.fromisoformat(v[:10]) if v else None
            except ValueError as err:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"날짜 형식이 아닙니다: {v}") from err
        elif isinstance(v, str):
            v = v.strip()
        setattr(row, k, v)
    if "inspection" in fields:
        ins = fields["inspection"] or {}
        try:
            row.inspection = {k: (None if ins.get(k) in (None, "") else int(ins[k])) for k in inspection.KEYS} if ins else None
        except (TypeError, ValueError) as err:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "검사 및 납품조서 칸에는 숫자만 적으세요.") from err
    row.updated_at = datetime.datetime.now()
    row.updated_by = user.display_name or ""


@router.post("/{contract_id}/inspection/reread")
def reread_inspection(contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """[완수내역서에서 다시 읽기](10/8 형) — 손으로 잘못 고친 검사 및 납품조서 표를 내역서 값으로 되돌림(정산금액도)."""
    row = _require(db, user, contract_id)
    if not _read_inspection(row, overwrite_settle=True):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "완수내역서에서 값을 읽지 못했습니다 — 완수내역서 칸에 PDF가 있는지 확인하세요.")
    row.updated_at = datetime.datetime.now()
    db.commit()
    return state(db, user, row)


@router.put("/{contract_id}")
def put_contract(contract_id: int, body: ContractIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _require(db, user, contract_id)
    _apply_contract(row, body.model_dump(exclude_unset=True), user)
    db.commit()
    return state(db, user, row)


@router.delete("/{contract_id}")
def delete_contract(contract_id: int, password: str = Body("", embed=True), user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """계약 지우기(만든 착수계·완수계·붙임 파일까지, 되돌릴 수 없음) — 현장 삭제와 같은 회사 공용 삭제 비밀번호(사용자 10/6)."""
    password_hash = config.get_site_delete_password_hash(user.company_id)
    if not password_hash:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "삭제 비밀번호가 아직 없습니다. '설정' 탭에서 먼저 정하세요.")
    if not verify_password(password, password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "삭제 비밀번호가 맞지 않습니다.")
    row = _require(db, user, contract_id)
    files.delete_contract_files(row)
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/{contract_id}/pdf")
def upload_contract_pdf(contract_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    row = _require(db, user, contract_id)
    info = _read_pdf(db, user, row, file.file.read())
    db.commit()
    return state(db, user, row) | info


class LinkIn(BaseModel):
    site_id: int | None = None  # 비우면 이 계약의 현장 연결 모두 끊기
    on: bool = True  # False = 이 현장만 끊기


@router.post("/{contract_id}/link")
def link_site(contract_id: int, body: LinkIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """현장 연결(계약 하나에 현장 여럿 — 그 현장에 다른 계약이 있으면 막음)·해제(on=False 그 현장, site_id 비움 = 전부)."""
    row = _require(db, user, contract_id)
    if body.site_id is None:
        for s in contract_sites.sites_of(db, row.id):
            contract_sites.unlink(db, s.id)
    else:
        site = repo.get_site(db, user.company_id, body.site_id)
        if site is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "현장을 찾을 수 없습니다.")
        if body.on:
            other = contract_sites.contract_of(db, site.id)
            if other is not None and other.id != row.id:
                raise HTTPException(status.HTTP_409_CONFLICT, f"이 현장에는 이미 다른 용역 계약이 연결돼 있습니다: {other.title or other.contract_no}")
            contract_sites.link(db, row, site)
        else:
            contract_sites.unlink(db, site.id)
    row.updated_at = datetime.datetime.now()
    db.commit()
    return state(db, user, row)


@router.get("/{contract_id}/site-candidates")
def site_candidates(contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """연결할 현장 고르기 — 다른 계약에 안 이어진 현장(이 계약에 이어진 것은 linked), 용역명과 비슷한 순."""
    row = _require(db, user, contract_id)
    sites = db.query(Site).filter(Site.company_id == user.company_id).all()
    cmap = contract_sites.contract_map(db, [s.id for s in sites])
    sites = [s for s in sites if s.id not in cmap or cmap[s.id].id == row.id]
    scored = sorted(((contract_status.similarity(row.title, s.name), s) for s in sites), key=lambda x: (-x[0], -x[1].id))
    return [{"id": s.id, "label": site_label(s), "address": s.address or "", "score": round(score, 2), "linked": s.id in cmap}
            for score, s in scored]


class MakeIn(BaseModel):
    contract: ContractIn | None = None
    doc_no: str = ""
    greeting: str = ""
    send_date: str = ""
    seal: bool = True
    agent_id: int | None = None
    participant_ids: list[int] = []


def _person(db: Session, p: TechPerson) -> build.Person:
    docs = person_docs(db, p.id)
    return build.Person(name=p.name, address=p.address, birth_date=p.birth_date, position=p.position, join_date=p.join_date,
                        qualification=p.qualification, grade=p.grade,
                        docs={k: d.file for k, d in docs.items() if d.file})


def _expired_warnings(db: Session, user: User, kind: str, chosen: list[TechPerson], on: datetime.date) -> list[str]:
    out = []
    if kind == "done":
        docs = company_docs(db, user.company_id)
        for k, label in build.COMPANY_DOCS:
            d = docs.get(k)
            if doc_status(d, on) == "expired":
                out.append(f"⚠ {label} 유효기간 지남({d.valid_until}) — 새로 발급받아 설정 탭에서 바꾸세요.")
            elif doc_status(d, on) == "nodate":
                out.append(f"⚠ {label} 발급일을 모릅니다 — 유효기간을 확인할 수 없으니 설정 탭에서 발급일을 적으세요.")
    else:
        for p in chosen:
            docs = person_docs(db, p.id)
            for k, label in build.PERSON_DOCS:
                d = docs.get(k)
                if doc_status(d, on) == "expired":
                    out.append(f"⚠ {p.name} {label} 유효기간 지남({d.valid_until}) — 새로 발급받아 설정 탭에서 바꾸세요.")
                elif doc_status(d, on) == "nodate":
                    out.append(f"⚠ {p.name} {label} 발급일을 모릅니다 — 유효기간(발급일 + 3개월)을 확인할 수 없으니 설정 탭에서 발급일을 적으세요.")
    return out


@router.post("/{contract_id}/docs/{kind}")
def make_docs(contract_id: int, kind: Literal["start", "done"], body: MakeIn, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    row = _require(db, user, contract_id)
    if body.contract is not None:
        _apply_contract(row, body.contract.model_dump(exclude_unset=True), user)
    c = _contract_values(row)
    if not c.title or not c.client:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "발주처·용역명을 먼저 채우세요(계약서 PDF를 올리면 자동으로 채워집니다).")
    try:
        send = datetime.date.fromisoformat(body.send_date[:10]) if body.send_date else datetime.date.today()
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "발송일 형식이 아닙니다.") from err
    common = build.Common(doc_no=body.doc_no.strip(), greeting=body.greeting.strip(), send_date=send,
                          contact_name=config.get_doc_contact_name(user.company_id), seal=body.seal)
    label = KIND_LABEL[kind]
    xlsx, pdf = files.out_path(row, f"{label}.xlsx"), files.out_path(row, f"{label}.pdf")
    chosen: list[TechPerson] = []
    if kind == "start":
        mine = {p.id: p for p in persons(db, user.company_id)}
        if body.agent_id not in mine:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "현장대리인(책임기술자)을 고르세요.")
        part_ids = [i for i in dict.fromkeys(body.participant_ids) if i in mine and i != body.agent_id]
        chosen = [mine[body.agent_id]] + [mine[i] for i in part_ids]
        warnings = build.build_start(c, common, _person(db, chosen[0]), [_person(db, p) for p in chosen[1:]], xlsx)
        row.agent_id, row.participant_ids = body.agent_id, part_ids
    else:
        docs = company_docs(db, user.company_id)
        warnings = build.build_done(c, common, {k: d.file for k, d in docs.items() if d.file}, xlsx)
    warnings = _expired_warnings(db, user, kind, chosen, send if kind == "done" else datetime.date.today()) + warnings
    extra = _make_inspection(row, c, common, warnings) if kind == "done" else {}
    pdf_error = ""
    try:  # 시트 PDF → 붙임 파일 끼워 합본 PDF 하나(사용자·형 10/6)
        with tempfile.TemporaryDirectory() as tmp:
            sheets = Path(tmp) / "sheets.pdf"
            to_pdf.office_to_pdf(xlsx, sheets)
            count = len(openpyxl.load_workbook(xlsx, read_only=True).sheetnames)
            warnings += attachments.merge(sheets, files.contract_dir(row), kind, count, pdf, extra)
    except Exception as err:  # noqa: BLE001 — 엑셀은 받을 수 있게 두고 PDF 실패만 알림(PDF가 없으면 제출로 안 봄)
        pdf.unlink(missing_ok=True)
        pdf_error = str(err)
    if kind == "start":
        row.start_made_at = datetime.datetime.now()
    else:
        row.done_made_at = datetime.datetime.now()
    db.commit()
    return {"warnings": warnings, "pdf_error": pdf_error, "made": _made(db, row)}


def _make_inspection(row: ServiceContract, c: build.Contract, common: build.Common, warnings: list[str]) -> dict[str, list[Path]]:
    """완수계 붙임 5번 검사 및 납품조서 — 붙임에 완수내역서가 있을 때만(사용자 10/8). 한글 양식 채워 .hwpx, 이 PC 한글로 .pdf →
    합본에서 완수내역서 다음(extra). 못 만들면 경고만."""
    hwpx, pdf = files.out_path(row, f"{INSP_NAME}.hwpx"), files.out_path(row, f"{INSP_NAME}.pdf")
    pdf.unlink(missing_ok=True)
    if not _done_list_files(row):
        hwpx.unlink(missing_ok=True)
        return {}
    if row.inspection is None:
        _read_inspection(row, overwrite_settle=row.settle_amount is None)
    d = inspection.normalize(row.inspection)
    lack = inspection.missing(d)
    if lack:
        hwpx.unlink(missing_ok=True)
        warnings.append(f"검사 및 납품조서 — {'·'.join(lack)}을(를) 몰라 뺐습니다(완수내역서에서 못 읽음 — 칸을 직접 채우세요).")
        return {}
    settle = c.settle_amount if c.settle_amount is not None else c.amount
    if settle != d["done_total"]:
        warnings.append(f"⚠ 정산금액({settle or 0:,}원)과 검사 및 납품조서 준공 금액({d['done_total']:,}원)이 다릅니다 — 확인하세요.")
    try:
        inspection.build(hwpx, title=c.title, contract_no=c.contract_no, client=c.client, due=c.actual_end_date or c.end_date,
                         made=common.send_date or datetime.date.today(), seal=common.seal, ins=d)
        pdf.write_bytes(hwp_queue.convert_via_worker(hwpx.read_bytes(), ".hwpx"))
    except Exception as err:  # noqa: BLE001 — 완수계(엑셀·나머지 PDF)는 만들고 이것만 뺌
        pdf.unlink(missing_ok=True)
        warnings.append(f"검사 및 납품조서를 PDF로 못 만들어 뺐습니다: {err}")
        return {}
    return {"done_list": [pdf]}


@router.get("/{contract_id}/docs/{kind}.{ext}")
def download_docs(contract_id: int, kind: Literal["start", "done"], ext: Literal["xlsx", "pdf", "hwpx"], inline: bool = False,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _require(db, user, contract_id)
    if ext == "hwpx" and kind != "done":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "한글 파일은 완수계(검사 및 납품조서)만 있습니다.")
    name = f"{INSP_NAME}.hwpx" if ext == "hwpx" else f"{KIND_LABEL[kind]}.{ext}"
    path = files.out_path(row, name)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"아직 만든 {KIND_LABEL[kind]}가 없습니다.")
    media = {"pdf": "application/pdf", "hwpx": "application/haansofthwpx",
             "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}[ext]
    return FileResponse(path, media_type=media, filename=files.download_name(row, name),
                        content_disposition_type="inline" if inline else "attachment")


@router.get("/{contract_id}/pdf")
def view_contract_pdf(contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _require(db, user, contract_id)
    path = files.out_path(row, "용역계약서.pdf")
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "올린 계약서가 없습니다.")
    return FileResponse(path, media_type="application/pdf", filename=files.download_name(row, "용역계약서.pdf"),
                        content_disposition_type="inline")


def _attach_list(row: ServiceContract, kind: str) -> list[dict]:
    out_dir = files.contract_dir(row)
    return [{"slot": key, "label": label, "files": [attachments.file_info(f) for f in attachments.list_files(out_dir, kind, key)]}
            for key, label, _ in attachments.SLOTS[kind]]


def _require_slot(kind: str, slot: str) -> None:
    if slot not in {key for key, _, _ in attachments.SLOTS[kind]}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 붙임 칸입니다.")


@router.post("/{contract_id}/docs/{kind}/attach/{slot}")
def upload_attachment(contract_id: int, kind: Literal["start", "done"], slot: str, file: UploadFile = File(...),
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """붙임 파일 올리기 — 바로 PDF로 바꿔 둔다(한글은 작업 프로그램이 바꿔서 몇 초~1분). def라 기다리는 동안 다른 요청은 안 막힘."""
    row = _require(db, user, contract_id)
    _require_slot(kind, slot)
    try:
        attachments.add_file(files.contract_dir(row), kind, slot, file.file.read(), file.filename or "")
    except (ValueError, RuntimeError) as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
    if (kind, slot) == ("done", "done_list") and _read_inspection(row, overwrite_settle=True):  # 새 완수내역서 → 표·정산금액(10/8)
        db.commit()
    return _attach_list(row, kind)


@router.delete("/{contract_id}/docs/{kind}/attach/{slot}/{name}")
def delete_attachment(contract_id: int, kind: Literal["start", "done"], slot: str, name: str,
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _require(db, user, contract_id)
    _require_slot(kind, slot)
    attachments.remove_file(files.contract_dir(row), kind, slot, name)
    return _attach_list(row, kind)


@router.get("/{contract_id}/docs/{kind}/attach/{slot}/{name}")
def view_attachment(contract_id: int, kind: Literal["start", "done"], slot: str, name: str,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _require(db, user, contract_id)
    _require_slot(kind, slot)
    path = attachments.slot_dir(files.contract_dir(row), kind, slot) / Path(name).name
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일이 없습니다.")
    return FileResponse(path, media_type="application/pdf", filename=path.name, content_disposition_type="inline")


@site_router.get("/contract")
def site_contract(site_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """현장 화면 [📑 착수계]·[📑 완수계] — 연결된 계약이 있으면 그것, 없으면 연결할 후보(아직 현장이 없는 계약, 비슷한 이름 순)."""
    site = repo.get_site(db, user.company_id, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "현장을 찾을 수 없습니다.")
    row = contract_sites.contract_of(db, site.id)
    if row is not None:
        return {"contract_id": row.id, "title": row.title, "candidates": []}
    free = db.query(ServiceContract).filter(ServiceContract.company_id == user.company_id).all()  # 계약 하나에 현장 여럿이라 모든 계약(10/20)
    scored = sorted(((contract_status.similarity(r.title, site.name), r) for r in free), key=lambda x: (-x[0], -x[1].id))
    return {"contract_id": None, "title": "",
            "candidates": [summary(db, r) | {"score": round(score, 2)} for score, r in scored]}



class SubmitIn(BaseModel):
    method: Literal["email", "direct", "post"]
    submitted_on: str = ""   # 직접·우편 제출일(비면 오늘). E-mail은 보낸 날
    to: str = ""             # E-mail 받는 사람(쉼표로 여러 곳) — 비면 사업 담당자 메일(없으면 계약 담당자)


@router.post("/{contract_id}/submit/{kind}")
def submit_docs(contract_id: int, kind: Literal["start", "done"], body: SubmitIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """제출 기록(사용자 10/6) — E-mail은 합본 PDF를 바로 보내고 기록, 직접·우편은 고른 날짜로 기록. 여러 방식 함께 가능."""
    row = _require(db, user, contract_id)
    label = KIND_LABEL[kind]
    to_addr = ""
    if body.method == "email":
        pdf = files.out_path(row, f"{label}.pdf")
        if not pdf.exists():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"먼저 {label}를 만드세요(합본 PDF를 보냅니다).")
        if not mailer.is_configured():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "회사 메일 설정이 없어 보낼 수 없습니다.")
        addrs = [a.strip() for a in (body.to or row.biz_email or row.client_email or "").replace(";", ",").split(",") if a.strip()]
        bad = [a for a in addrs if not mailer.valid_email(a)]
        if not addrs or bad:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"받는 메일 주소를 확인하세요{': ' + ', '.join(bad) if bad else ''}.")
        title = row.title or "용역"
        subject = f"[{mailer.settings.MAIL_FROM_NAME}] {title} {label} 제출"
        who = row.biz_manager if row.biz_email and row.biz_email in addrs else row.client_manager if row.client_email in addrs else ""
        text = (f"안녕하세요{(' ' + who + '님') if who else ''}.\n\n"
                f"{title} {label}를 첨부하여 제출합니다.\n\n{mailer.settings.MAIL_FROM_NAME} 드림")
        try:
            refused = mailer.send_pdf(addrs, "", subject, text, pdf, files.download_name(row, f"{label}.pdf"))
        except mailer.MailError as err:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
        if refused:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"메일 서버가 거부한 주소: {', '.join(refused)} — 나머지에겐 보냈습니다.")
        to_addr = ", ".join(addrs)
        day = datetime.date.today()
        if not row.biz_email and not row.client_email and len(addrs) == 1:
            row.biz_email = addrs[0]  # 처음 보낸 주소를 사업 담당자 메일로 기억
    else:
        try:
            day = datetime.date.fromisoformat(body.submitted_on[:10]) if body.submitted_on else datetime.date.today()
        except ValueError as err:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "제출일 형식이 아닙니다.") from err
    db.add(ContractSubmit(company_id=user.company_id, contract_id=row.id, kind=kind, method=body.method, submitted_on=day,
                          to_addr=to_addr, created_by=user.display_name or ""))
    db.commit()
    return {"made": _made(db, row)}


@router.delete("/{contract_id}/submit/{submit_id}")
def undo_submit(contract_id: int, submit_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """제출 기록 지우기(잘못 누름) — E-mail은 이미 간 메일을 되돌리진 못하고 기록만 지운다."""
    row = _require(db, user, contract_id)
    rec = db.get(ContractSubmit, submit_id)
    if rec is None or rec.contract_id != row.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "제출 기록을 찾을 수 없습니다.")
    db.delete(rec)
    db.commit()
    return {"made": _made(db, row)}
