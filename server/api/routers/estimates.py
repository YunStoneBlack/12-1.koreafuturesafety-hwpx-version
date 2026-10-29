"""통합 견적 API(2026-10-29 사용자 "그룹웨어 통합 견적서 — 각 용역별로 선택해서 쓰고 관리") — 서류 자동화 › 견적(estimates.html·estimate.html).

- `GET  /estimates/meta` — 용역 8가지·줄 계산 방식·등급·건축물 용도·상태·기준표·견적담당 추천
- `GET  /estimates` (?status·kind·q) · `POST /estimates` {kind, copy_from} · `GET|PATCH|DELETE /estimates/{id}`(지우기 = 회사 삭제 비밀번호)
- `POST /estimates/{id}/copy` — 같은 내용으로 새 견적(새 번호·오늘·작성중) · `POST /estimates/{id}/fit` {total} — 합계(VAT 포함)를 이 금액으로
- `POST /estimates/{id}/export` — 엑셀·PDF(회사 견적서 양식 — server/estimate/export.py) · `GET /estimates/{id}/file/{xlsx|pdf}`
- `POST /estimates/{id}/handoff` — 수주 → 계약으로 넘기기(server/estimate/handoff — 기술지도 = 산안법 용역 계약 · 정기·정밀 = 시특법 민간 계약 · 건축물관리점검 = 건)
- `GET  /estimates/stats` (?year) — 수주 통계(용역별·견적담당별·달별, 수주율 = 수주 ÷ 보낸 견적)
- `POST /estimates/rates/check` — 노임단가 새 공표 지금 확인(server/estimate/rate_watch — 12·1월·8·9월엔 견적 화면을 열 때 하루 한 번 뒤에서 저절로)
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
from server.estimate import handoff as H

router = APIRouter(prefix="/estimates", tags=["estimates"])
STATUS = {"draft": "작성중", "sent": "보냄", "won": "수주", "lost": "실패"}
RATES_KEY = "estimate_rates"
WATCH_KEY = "estimate_rates_watch"  # {last, notices: [...]} — 자동 갱신 기록
NO_RE = re.compile(r"^KFSC-(\d{2})-(\d{1,4})$")


# ---------- 기준표 ----------
def _setting(db: Session, company_id: int, key: str):
    from core.models_db import AppSetting

    return db.query(AppSetting).filter(AppSetting.company_id == company_id, AppSetting.key == key).first()


def _json(db: Session, company_id: int, key: str) -> dict:
    row = _setting(db, company_id, key)
    try:
        return json.loads(row.value) if row and row.value else {}
    except ValueError:
        return {}


def _put_json(db: Session, company_id: int, key: str, val: dict) -> None:
    from core.models_db import AppSetting

    row = _setting(db, company_id, key)
    text = json.dumps(val, ensure_ascii=False)
    if row is None:
        db.add(AppSetting(company_id=company_id, key=key, value=text))
    else:
        row.value = text
    db.commit()


def rates(db: Session, company_id: int) -> dict:
    return C.rates_with(_json(db, company_id, RATES_KEY) or None)


def watch_run(company_id: int, force: bool = False) -> list[dict]:
    """노임단가 새 공표 살피기 — 자기 DB 연결로(뒤에서 돌 때). 검사를 통과한 것만 기준표에, 알림은 watch에(마지막 12개)."""
    from core.db import SessionLocal
    from server.estimate import rate_watch as W

    with SessionLocal() as db2:
        def load():
            return _json(db2, company_id, RATES_KEY)

        def save(v):
            _put_json(db2, company_id, RATES_KEY, v)

        def notify(found):
            w = _json(db2, company_id, WATCH_KEY)
            w["last"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            w["notices"] = (list(w.get("notices") or []) + found)[-12:]
            _put_json(db2, company_id, WATCH_KEY, w)
        return W.run(load, save, notify, force=force)


def maybe_watch(db: Session, company_id: int) -> None:
    """살피는 달(12·1·8·9월)이고 마지막 확인이 20시간 넘었으면 뒤에서 한 번(화면은 안 기다림)."""
    import threading

    from server.estimate import rate_watch as W

    if not W.in_window(datetime.date.today()):
        return
    last = _json(db, company_id, WATCH_KEY).get("last") or ""
    try:
        if last and datetime.datetime.now() - datetime.datetime.strptime(last, "%Y-%m-%d %H:%M") < datetime.timedelta(hours=20):
            return
    except ValueError:
        pass
    threading.Thread(target=watch_run, args=(company_id,), daemon=True, name="estimate_rate_watch").start()


def watch_info(db: Session, company_id: int) -> dict:
    w = _json(db, company_id, WATCH_KEY)
    return {"last": w.get("last") or "", "notices": list(reversed(w.get("notices") or []))[:6]}


@router.get("/rates")
def get_rates(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"rates": rates(db, user.company_id), "grades": C.GRADES, "watch": watch_info(db, user.company_id)}


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
    old, eff = _json(db, user.company_id, RATES_KEY), rates(db, user.company_id)
    for k in ("labor_auto", "helper_key", "labor_next", "helper_next"):  # 자동 갱신 기록은 지킴
        if old.get(k):
            clean[k] = old[k]
    if clean.get("labor_year") and clean["labor_year"] != eff.get("labor_year"):
        clean.pop("labor_next", None)  # 사람이 연도를 바꿈 = 사람 결정대로
    if clean.get("helper_rate") is not None and float(clean["helper_rate"]) != float(eff.get("helper_rate") or 0):
        clean.pop("helper_next", None)
    _put_json(db, user.company_id, RATES_KEY, clean)
    return {"rates": rates(db, user.company_id), "grades": C.GRADES, "watch": watch_info(db, user.company_id)}


@router.post("/rates/check")
def check_rates(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """노임단가 새 공표 지금 확인(5~20초) — 검사를 통과하면 바로 기준표에(적용일부터), 아니면 알림만."""
    found = watch_run(user.company_id, force=True)
    db.expire_all()
    return {"found": found, "rates": rates(db, user.company_id), "watch": watch_info(db, user.company_id), "grades": C.GRADES}


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
    maybe_watch(db, user.company_id)
    return {"watch": watch_info(db, user.company_id),
            "kinds": [{"key": k, **{x: v[x] for x in ("label", "task", "subject", "row", "check", "conditions")}} for k, v in C.KINDS.items()],
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


def pinned(e: Estimate, R: dict) -> dict:
    """견적에 붙인 노임 연도·보조인부 단가(만들 때 값 — 새 공표가 들어와도 지난 견적 금액은 그대로). 없으면 지금 기준표."""
    o = e.options or {}
    out = dict(R)
    if o.get("labor_year") and str(o["labor_year"]) in R["labor"]:
        out["labor_year"] = str(o["labor_year"])
    if o.get("helper_rate"):
        out["helper_rate"] = o["helper_rate"]
    return out


def compute(db: Session, e: Estimate) -> tuple[list[dict], dict, list[str]]:
    R = pinned(e, rates(db, e.company_id))
    outs = [C.calc_row(r, R, _project(e)) for r in (e.rows or [])]
    warn = []
    if any(o.get("missing_rate") for o in outs):
        yr = R.get("labor_year")
        warn.append(f"노임단가 {yr}년 표에 빈 등급이 있습니다 — 견적 목록 화면 [⚙ 기준표]에서 넣으세요(지금은 0원으로 계산)")
    R0 = rates(db, e.company_id)
    if R.get("labor_year") != R0.get("labor_year"):
        warn.append(f"이 견적은 만들 때 노임단가 {R['labor_year']}년 기준입니다(지금 기준표 {R0['labor_year']}년) — 새 단가로 하려면 [노임 연도 바꾸기]")
    return outs, C.totals(outs, R), warn


def _list_out(e: Estimate) -> dict:
    t = e.totals or {}
    return {"id": e.id, "no": e.no, "kind": e.kind, "kind_label": (C.KINDS.get(e.kind) or {}).get("label", e.kind), "status": e.status,
            "status_label": STATUS.get(e.status, e.status), "issued_on": e.issued_on.isoformat() if e.issued_on else "",
            "client": (e.client or {}).get("name") or "", "subject": (e.project or {}).get("name") or "", "total": t.get("total"),
            "supply": t.get("supply"), "staff": (e.staff or {}).get("name") or "",
            "link_to": (e.link or {}).get("to") or "", "link_label": (e.link or {}).get("label") or "", "can_handoff": e.kind in H.TARGETS,
            "updated": f"{e.updated_at or e.created_at:%Y-%m-%d %H:%M}"}


LINK_URL = {"sanan": "docs.html?contract={id}", "sitok": "sitok-docs.html?contract={id}", "blcm": "blcm-job.html?id={id}"}


def link_view(db: Session, e: Estimate) -> dict:
    """넘긴 계약·건(지금 이름·주소) — 저쪽에서 지웠으면 gone(다시 넘길 수 있음)."""
    from core.models_web import BlcmJob, ServiceContract, SitokDocContract

    ln = e.link or {}
    if not ln.get("to"):
        return {}
    model = {"sanan": ServiceContract, "sitok": SitokDocContract, "blcm": BlcmJob}.get(ln["to"])
    row = db.get(model, ln.get("id")) if model else None
    if row is None or row.company_id != e.company_id:
        return {**ln, "gone": True, "where": H.TARGET_LABEL.get(ln["to"], "")}
    if ln["to"] == "sanan":
        from server.api.routers.contracts import contract_label
        label = contract_label(row)
    elif ln["to"] == "sitok":
        from server.sitok import civil
        label = row.title or civil.default_title(row)
    else:
        label = row.name
    return {**ln, "label": label, "gone": False, "url": LINK_URL[ln["to"]].format(id=row.id), "where": H.TARGET_LABEL[ln["to"]]}


def _out(db: Session, e: Estimate) -> dict:
    outs, tot, warn = compute(db, e)
    return {**_list_out(e), "title": e.title, "client": e.client or {}, "project": e.project or {}, "staff": e.staff or {},
            "rows": e.rows or [], "rows_out": outs, "totals": tot, "options": e.options or {}, "memo": e.memo or "", "link": link_view(db, e),
            "handoff": {"to": H.TARGETS.get(e.kind, ""), "where": H.TARGET_LABEL.get(H.TARGETS.get(e.kind, ""), "")},
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
    maybe_watch(db, user.company_id)
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


@router.get("/stats")
def get_stats(year: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """수주 통계 — year 비우면 올해, "all"이면 전체."""
    rows = db.query(Estimate).filter(Estimate.company_id == user.company_id).all()
    y = None if year == "all" else (int(year) if year.isdigit() else datetime.date.today().year)
    return H.stats(rows, y)


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
                 options={"conditions": list(k["conditions"]), "labor_year": rates(db, user.company_id)["labor_year"],
                          "helper_rate": rates(db, user.company_id)["helper_rate"]}, created_by=user.display_name or "")
    if body.copy_from:
        src = _require(db, user, body.copy_from)
        e.client, e.project, e.staff = dict(src.client or {}), dict(src.project or {}), dict(src.staff or {})
        if src.kind == body.kind:
            keep = {k: e.options[k] for k in ("labor_year", "helper_rate")}  # 복사본은 오늘 기준표로
            e.rows, e.options, e.title = [dict(r) for r in src.rows or []], {**dict(src.options or {}), **keep}, src.title
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
        if body.options.get("labor_year"):  # [노임 연도 바꾸기] — 기준표에 있는 연도만
            y = str(body.options["labor_year"])
            if y not in rates(db, e.company_id)["labor"]:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"기준표에 {y}년 노임단가가 없습니다.")
            o["labor_year"] = y
        if body.options.get("helper_now"):  # 보조인부 단가를 지금 기준표 값으로
            o["helper_rate"] = rates(db, e.company_id)["helper_rate"]
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
    R = pinned(e, rates(db, e.company_id))
    clean = [{**r, "price": None} for r in (e.rows or [])]
    outs = [C.calc_row(r, R, _project(e)) for r in clean]
    e.rows = C.fit_total(clean, outs, total, R)
    _save(db, e, user)
    return _out(db, e)


@router.post("/{eid}/handoff")
def handoff(eid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """수주 → 계약으로 넘기기: 견적 칸을 옮긴 계약·건을 만들고 견적을 수주로, 서로 이어 둠(한 번에 저장). 이미 넘겼으면 409."""
    from core.models_web import BlcmJob, SitokDocContract

    e = _require(db, user, eid)
    to = H.TARGETS.get(e.kind)
    label_kind = (C.KINDS.get(e.kind) or {}).get("label", e.kind)
    if not to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{label_kind}은(는) 넘길 계약 화면이 아직 없습니다 — 상태를 [수주]로 두면 수주 통계에 들어갑니다.")
    cur = link_view(db, e)
    if cur and not cur.get("gone"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"이미 넘겼습니다 — {cur['where']} {cur['label']}")
    if not ((e.project or {}).get("name") or (e.client or {}).get("name") or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "발주처나 공사명·시설명을 먼저 넣어 주세요.")
    outs, tot, _ = compute(db, e)
    if not tot.get("total"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "견적 금액이 0원입니다 — 금액 줄을 먼저 채워 주세요.")
    now = datetime.datetime.now()
    if to == "sanan":
        from server.api.routers import contracts as CT

        row = CT._new(db, user)
        CT._apply_contract(row, H.sanan_fields(e, tot), user)
        db.flush()
        tid, label = row.id, CT.contract_label(row)
    elif to == "sitok":
        from server.api.routers import sitok_docs as SD
        from server.sitok import civil

        R = pinned(e, rates(db, e.company_id))
        c = SitokDocContract(company_id=user.company_id, created_by=user.display_name or "", rounds=[], guarantee="-", delay_rate="-", field="시특법")
        SD._apply(c, SD.ContractIn(**H.sitok_fields(e, outs, float(R.get("vat") or 0.1))), user, db)
        db.add(c)
        db.flush()
        tid, label = c.id, c.title or civil.default_title(c)
    else:
        j = BlcmJob(company_id=user.company_id, created_by=user.display_name or "", results={}, opinion={}, site={}, files={}, **H.blcm_fields(e, tot))
        db.add(j)
        db.flush()
        tid, label = j.id, j.name
    e.link = {"to": to, "id": tid, "label": label, "at": now.strftime("%Y-%m-%d %H:%M"), "by": user.display_name or ""}
    e.status = "won"
    flag_modified(e, "link")
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


# ---------- 엑셀·PDF(10/29 2단계) ----------
def _folder(e: Estimate):
    from core.db import DATA_DIR
    from server.api import storage

    return DATA_DIR / "_견적" / f"{e.id:04d}_{storage._clean(e.no or '견적')}"


@router.post("/{eid}/export")
def export(eid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """회사 견적서 양식 그대로 엑셀 → PDF(LibreOffice, 몇 초). 파일 이름 = 번호_발주처(또는 공사·시설명)_견적서."""
    from server.api import storage
    from server.contract_docs.to_pdf import office_to_pdf
    from server.estimate import export as X

    e = _require(db, user, eid)
    out = _out(db, e)
    R = rates(db, e.company_id)
    who = (e.client or {}).get("name") or (e.project or {}).get("name") or ""
    base = f"{e.no}_{storage._clean(who)[:40]}_견적서".strip("_")
    folder = _folder(e)
    try:
        res = X.build(out, out["rows_out"], out["totals"], R, folder / f"{base}.xlsx")
    except FileNotFoundError as err:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(err)) from err
    pdf_err = ""
    pages = None
    try:
        office_to_pdf(res["xlsx"], folder / f"{base}.pdf")
        import pymupdf

        with pymupdf.open(folder / f"{base}.pdf") as d:
            pages = d.page_count
    except Exception as err:  # noqa: BLE001 — 엑셀은 받을 수 있게
        pdf_err = str(err)[:200]
    e.files = {"xlsx": f"{base}.xlsx", "pdf": f"{base}.pdf" if not pdf_err else "", "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
               "by": user.display_name or "", "notes": res["notes"] + ([f"PDF를 못 만들었습니다: {pdf_err}"] if pdf_err else []), "pages": pages,
               "sheets": res["sheets"]}
    flag_modified(e, "files")
    db.commit()
    return _out(db, e)


@router.get("/{eid}/file/{kind}")
def get_file(eid: int, kind: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse

    e = _require(db, user, eid)
    name = (e.files or {}).get(kind) if kind in ("xlsx", "pdf") else None
    p = _folder(e) / name if name else None
    if p is None or not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일이 없습니다 — [📄 엑셀·PDF 만들기]를 먼저 누르세요.")
    media = "application/pdf" if kind == "pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return FileResponse(p, media_type=media, filename=name, content_disposition_type="inline" if kind == "pdf" else "attachment",
                        headers={"Cache-Control": "no-store"})
