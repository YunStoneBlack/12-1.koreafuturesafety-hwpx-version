"""통합 견적 API(2026-10-29 사용자 "그룹웨어 통합 견적서 — 각 용역별로 선택해서 쓰고 관리") — 서류 자동화 › 견적(estimates.html·estimate.html).

- `GET  /estimates/meta` — 용역 8가지·줄 계산 방식·등급·건축물 용도·상태·기준표·견적담당 추천
- `GET  /estimates` (?status·kind·q) · `POST /estimates` {kind, copy_from} · `GET|PATCH|DELETE /estimates/{id}`(지우기 = 회사 삭제 비밀번호)
- `POST /estimates/{id}/copy` — 같은 내용으로 새 견적(새 번호·오늘·작성중) · `POST /estimates/{id}/fit` {total} — 합계(VAT 포함)를 이 금액으로
- `GET|PUT /estimates/rates` — 기준표(엔지니어링 노임단가 연도별·기술지도 회당 인건비 구간·제경비·기술료율 — app_setting estimate_rates)
계산은 server/estimate/calc.py(회사 견적서 엑셀 수식 그대로). 번호 = KFSC-연도2자리-차례(바꿀 수 있음, 회사 안에서 겹치면 409)."""
from __future__ import annotations

import datetime
import json
import re

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from core import config
from core.models_web import Estimate, User
from server.api.deps import get_current_user, get_db
from server.api.security import verify_password
from server.estimate import calc as C

router = APIRouter(prefix="/estimates", tags=["estimates"])
STATUS = {"draft": "작성중", "sent": "보냄", "won": "수주", "lost": "실패"}
RATES_KEY = "estimate_rates"
NO_RE = re.compile(r"^KFSC-(\d{2})-(\d{1,4})$")


# ---------- 기준표 ----------
def _setting(db: Session, company_id: int, key: str):
    from core.models_db import AppSetting

    return db.query(AppSetting).filter(AppSetting.company_id == company_id, AppSetting.key == key).first()


def rates(db: Session, company_id: int) -> dict:
    row = _setting(db, company_id, RATES_KEY)
    try:
        saved = json.loads(row.value) if row and row.value else None
    except ValueError:
        saved = None
    return C.rates_with(saved)


@router.get("/rates")
def get_rates(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"rates": rates(db, user.company_id), "grades": C.GRADES}


@router.put("/rates")
def put_rates(body: dict = Body(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """기준표 저장 — 노임단가는 연도 → 등급 → 원, 구간은 [{under, label, grade, rate}], 율은 숫자. 모르는 칸은 버림."""
    from core.models_db import AppSetting

    clean: dict = {}
    lab = body.get("labor")
    if isinstance(lab, dict):
        clean["labor"] = {}
        for y, t in lab.items():
            if re.fullmatch(r"\d{4}", str(y)) and isinstance(t, dict):
                clean["labor"][str(y)] = {g: (int(float(v)) if v not in (None, "") else None) for g, v in t.items() if g in C.GRADES}
    if str(body.get("labor_year") or "") and re.fullmatch(r"\d{4}", str(body.get("labor_year"))):
        clean["labor_year"] = str(body["labor_year"])
    if isinstance(body.get("visit_bands"), list):
        clean["visit_bands"] = [{"under": (int(float(b["under"])) if b.get("under") not in (None, "") else None), "label": str(b.get("label") or "")[:30],
                                 "grade": str(b.get("grade") or "")[:30], "rate": int(float(b.get("rate") or 0))}
                                for b in body["visit_bands"] if isinstance(b, dict)][:8]
    for k in ("overhead", "tech", "helper_rate", "visit_days"):
        if body.get(k) not in (None, ""):
            clean[k] = float(body[k])
    row = _setting(db, user.company_id, RATES_KEY)
    val = json.dumps(clean, ensure_ascii=False)
    if row is None:
        db.add(AppSetting(company_id=user.company_id, key=RATES_KEY, value=val))
    else:
        row.value = val
    db.commit()
    return {"rates": rates(db, user.company_id), "grades": C.GRADES}


# ---------- 메타·번호 ----------
def next_no(db: Session, company_id: int, day: datetime.date | None = None) -> str:
    yy = (day or datetime.date.today()).strftime("%y")
    nums = [int(m.group(2)) for (no,) in db.query(Estimate.no).filter(Estimate.company_id == company_id) if (m := NO_RE.match(no or "")) and m.group(1) == yy]
    return f"KFSC-{yy}-{(max(nums) + 1 if nums else 1):03d}"


@router.get("/meta")
def meta(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    staff = []
    for (s,) in db.query(Estimate.staff).filter(Estimate.company_id == user.company_id).order_by(Estimate.id.desc()).limit(80):
        if isinstance(s, dict) and (s.get("name") or "").strip() and all(x["name"] != s["name"] for x in staff):
            staff.append({"name": s["name"], "phone": s.get("phone") or ""})
    return {"kinds": [{"key": k, **{x: v[x] for x in ("label", "task", "subject", "row", "check", "conditions")}} for k, v in C.KINDS.items()],
            "row_types": [{"key": t, "label": C.ROW_LABEL[t]} for t in C.ROW_TYPES], "grades": C.GRADES, "uses": list(C.BLCM_USE),
            "status": STATUS, "rates": rates(db, user.company_id), "staff": staff[:12], "next_no": next_no(db, user.company_id)}


# ---------- 줄 다듬기·계산 ----------
_NUM = (int, float)


def _num(v, lo=0.0, hi=1e13):
    if v in (None, ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return max(lo, min(hi, x))


def clean_row(kind: str, r: dict) -> dict:
    """줄 — 그 계산 방식의 칸만 남기고 숫자는 숫자로."""
    t = r.get("type") if r.get("type") in C.ROW_TYPES else (C.KINDS.get(kind) or {}).get("row", "item")
    base = C.default_row(kind, t)
    out = {"type": t, "name": str(r.get("name") or "")[:120], "check": str(r.get("check") or "")[:60], "note": str(r.get("note") or "")[:120],
           "times": _num(r.get("times"), 0, 9999), "price": _num(r.get("price"), 0)}
    if r.get("year") and re.fullmatch(r"\d{4}", str(r["year"])):
        out["year"] = str(r["year"])
    for k in ("overhead", "tech"):
        if _num(r.get(k), 0, 5) is not None:
            out[k] = _num(r.get(k), 0, 5)
    for k, dv in base.items():
        if k in out or k in ("type",):
            continue
        v = r.get(k, dv)
        if isinstance(dv, dict):
            v = v if isinstance(v, dict) else {}
            out[k] = {kk: _num(v.get(kk, d2)) if not isinstance(d2, str) else str(v.get(kk) or "") for kk, d2 in dv.items()}
        elif k == "tasks":
            tasks = v if isinstance(v, list) else dv
            out[k] = [{"name": str(tk.get("name") or "")[:80],
                       "lines": [{"grade": ln.get("grade") if ln.get("grade") in C.GRADES else "고급기술자",
                                  "persons": _num(ln.get("persons"), 0, 99), "days": _num(ln.get("days"), 0, 999)}
                                 for ln in (tk.get("lines") or []) if isinstance(ln, dict)][:8]}
                      for tk in tasks if isinstance(tk, dict)][:8]
        elif k in ("use", "mode", "grade", "band", "structure"):
            out[k] = str(v)[:30] if v not in (None,) else dv
        elif isinstance(dv, _NUM) or dv is None:
            out[k] = _num(v, 0) if k not in ("built_year",) else (int(_num(v, 1900, 2100)) if _num(v, 1900, 2100) else None)
        else:
            out[k] = v
    if t == "sitok" and out.get("grade") not in C.GRADES:
        out["grade"] = "고급기술자"
    if t == "blcm" and out.get("structure") not in ("auto", "yes", "no"):
        out["structure"] = "auto"
    return out


def _project(e: Estimate) -> dict:
    p = dict(e.project or {})
    if p.get("amount") not in (None, ""):
        try:
            p["amount"] = float(str(p["amount"]).replace(",", ""))
        except ValueError:
            p["amount"] = None
    return p


def compute(db: Session, e: Estimate) -> tuple[list[dict], dict, list[str]]:
    R = rates(db, e.company_id)
    outs = [C.calc_row(r, R, _project(e)) for r in (e.rows or [])]
    warn = []
    if any(o.get("missing_rate") for o in outs):
        yr = R.get("labor_year")
        warn.append(f"노임단가 {yr}년 표에 빈 등급이 있습니다 — 견적 목록 화면 [⚙ 기준표]에서 넣으세요(지금은 0원으로 계산)")
    return outs, C.totals(outs, R), warn


def _list_out(e: Estimate) -> dict:
    t = e.totals or {}
    return {"id": e.id, "no": e.no, "kind": e.kind, "kind_label": (C.KINDS.get(e.kind) or {}).get("label", e.kind), "status": e.status,
            "status_label": STATUS.get(e.status, e.status), "issued_on": e.issued_on.isoformat() if e.issued_on else "",
            "client": (e.client or {}).get("name") or "", "subject": (e.project or {}).get("name") or "", "total": t.get("total"),
            "supply": t.get("supply"), "staff": (e.staff or {}).get("name") or "",
            "updated": f"{e.updated_at or e.created_at:%Y-%m-%d %H:%M}"}


def _out(db: Session, e: Estimate) -> dict:
    outs, tot, warn = compute(db, e)
    return {**_list_out(e), "title": e.title, "client": e.client or {}, "project": e.project or {}, "staff": e.staff or {},
            "rows": e.rows or [], "rows_out": outs, "totals": tot, "options": e.options or {}, "memo": e.memo or "", "link": e.link or {},
            "files": e.files or {}, "warnings": warn, "korean": C.korean_amount(tot["total"]), "korean_supply": C.korean_amount(tot["supply"])}


def _require(db: Session, user: User, eid: int) -> Estimate:
    e = db.get(Estimate, eid)
    if e is None or e.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "견적을 찾을 수 없습니다.")
    return e


def _save(db: Session, e: Estimate, user: User) -> None:
    outs, tot, _ = compute(db, e)
    e.totals = tot
    e.updated_at, e.updated_by = datetime.datetime.now(), user.display_name or ""
    for c in ("rows", "client", "project", "staff", "options", "totals"):
        flag_modified(e, c)
    db.commit()


# ---------- 목록·만들기 ----------
@router.get("")
def list_estimates(status_: str = Query("", alias="status"), kind: str = "", q: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Estimate).filter(Estimate.company_id == user.company_id).order_by(Estimate.id.desc()).all()
    out = [_list_out(e) for e in rows]
    if status_:
        out = [x for x in out if x["status"] == status_]
    if kind:
        out = [x for x in out if x["kind"] == kind]
    if q.strip():
        k = q.strip().replace(" ", "")
        out = [x for x in out if k in (x["no"] + x["client"] + x["subject"] + x["staff"] + x["kind_label"]).replace(" ", "")]
    counts = {s: sum(1 for e in rows if e.status == s) for s in STATUS}
    return {"estimates": out, "counts": counts}


class NewIn(BaseModel):
    kind: str
    copy_from: int | None = None


@router.post("")
def create(body: NewIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.kind not in C.KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "없는 용역 종류입니다.")
    k = C.KINDS[body.kind]
    today = datetime.date.today()
    e = Estimate(company_id=user.company_id, no=next_no(db, user.company_id, today), kind=body.kind, status="draft", issued_on=today, title=k["task"],
                 client={}, project={}, staff={"name": user.display_name or "", "phone": ""}, rows=C.default_rows(body.kind),
                 options={"conditions": list(k["conditions"])}, created_by=user.display_name or "")
    if body.copy_from:
        src = _require(db, user, body.copy_from)
        e.client, e.project, e.staff = dict(src.client or {}), dict(src.project or {}), dict(src.staff or {})
        if src.kind == body.kind:
            e.rows, e.options, e.title = [dict(r) for r in src.rows or []], dict(src.options or {}), src.title
    db.add(e)
    db.flush()
    _save(db, e, user)
    return _out(db, e)


@router.get("/{eid}")
def get_one(eid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(db, _require(db, user, eid))


class PatchIn(BaseModel):
    no: str | None = None
    status: str | None = None
    issued_on: str | None = None
    title: str | None = None
    client: dict | None = None
    project: dict | None = None
    staff: dict | None = None
    rows: list | None = None
    options: dict | None = None
    memo: str | None = None


def _strs(d: dict, keys: tuple[str, ...], n: int = 200) -> dict:
    return {k: str(d.get(k) or "").strip()[:n] for k in keys if k in d}


@router.patch("/{eid}")
def patch(eid: int, body: PatchIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    e = _require(db, user, eid)
    if body.no is not None:
        no = body.no.strip()[:40]
        if not no:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "견적 번호를 넣어 주세요.")
        if db.query(Estimate).filter(Estimate.company_id == e.company_id, Estimate.no == no, Estimate.id != e.id).first():
            raise HTTPException(status.HTTP_409_CONFLICT, f"{no} 번호를 다른 견적이 쓰고 있습니다.")
        e.no = no
    if body.status is not None:
        if body.status not in STATUS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "없는 상태입니다.")
        e.status = body.status
    if body.issued_on is not None:
        try:
            e.issued_on = datetime.date.fromisoformat(body.issued_on[:10]) if body.issued_on else None
        except ValueError as err:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "견적일자가 날짜가 아닙니다.") from err
    if body.title is not None:
        e.title = body.title.strip()[:120]
    if body.client is not None:
        e.client = {**(e.client or {}), **_strs(body.client, ("name", "rep", "ref", "phone", "email"))}
    if body.project is not None:
        e.project = {**(e.project or {}), **_strs(body.project, ("name", "address", "amount", "period", "floors", "area", "note"), 300)}
    if body.staff is not None:
        e.staff = {**(e.staff or {}), **_strs(body.staff, ("name", "phone"))}
    if body.rows is not None:
        e.rows = [clean_row(e.kind, r) for r in body.rows if isinstance(r, dict)][:30]
    if body.options is not None:
        o = dict(e.options or {})
        if isinstance(body.options.get("conditions"), list):
            o["conditions"] = [str(x).strip()[:200] for x in body.options["conditions"] if str(x).strip()][:12]
        if "note" in body.options:
            o["note"] = str(body.options.get("note") or "")[:1000]
        e.options = o
    if body.memo is not None:
        e.memo = body.memo[:2000]
    _save(db, e, user)
    return _out(db, e)


@router.post("/{eid}/copy")
def copy(eid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    src = _require(db, user, eid)
    return create(NewIn(kind=src.kind, copy_from=src.id), user, db)


@router.post("/{eid}/fit")
def fit(eid: int, total: int = Body(..., embed=True), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """합계(VAT 포함)를 이 금액으로 — 줄마다 산출 비율대로 견적 금액을 나눔(천원 미만 절사, 남은 것은 첫 줄)."""
    e = _require(db, user, eid)
    if total <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "금액을 넣어 주세요.")
    R = rates(db, e.company_id)
    clean = [{**r, "price": None} for r in (e.rows or [])]
    outs = [C.calc_row(r, R, _project(e)) for r in clean]
    e.rows = C.fit_total(clean, outs, total, R)
    _save(db, e, user)
    return _out(db, e)


@router.delete("/{eid}")
def delete(eid: int, password: str = Body("", embed=True), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """지우기(되돌릴 수 없음) — 회사 공용 삭제 비밀번호."""
    h = config.get_site_delete_password_hash(user.company_id)
    if not h:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "삭제 비밀번호가 아직 없습니다. 설정에서 먼저 정하세요.")
    if not verify_password(password, h):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "삭제 비밀번호가 맞지 않습니다.")
    e = _require(db, user, eid)
    db.delete(e)
    db.commit()
    return {"ok": True}
