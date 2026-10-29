"""건축물관리점검(건축물관리법 정기점검) 보고서 자동화 API(2026-10-29 사용자) — 건(BlcmJob, 0069)·항목 결과·사진·AI.

- `GET  /blcm/items` — 항목표(대항목 탭·소항목 50개, 매뉴얼 25.02)
- `GET  /blcm/jobs` · `POST /blcm/jobs`(form name·address·ledger = 건축물대장 PDF) · `GET|PATCH|DELETE /blcm/jobs/{id}`(지우기 = 회사 삭제 비밀번호)
- `POST /blcm/jobs/{id}/register`(건축물대장 PDF → 건축물 개요, ai=1이면 스캔도 AI로)
- `PUT  /blcm/jobs/{id}/items/{code}` — 소항목 결과 저장(판정·점검현황·글) → 판정 계산
- `POST /blcm/jobs/{id}/items/{code}/photos`(file·kind good|bad·caption) · `PATCH|DELETE …/photos/{pid}` · `GET /blcm/jobs/{id}/photo/{pid}`
- `POST /blcm/jobs/{id}/items/{code}/ai` {extra} — 사진·대장으로 점검현황·글 채우기(점검자 판정은 그대로, 약 30~60원)
- `POST /blcm/jobs/{id}/ai/rewrite` {label, current, note} — 글 한 칸 덧붙인 내용 반영해 다시 쓰기(app.js aiRewrite, 약 10원)
건 폴더 = 저장소 _건축물관리점검/NNN_건축물명(사진/·서류/)."""
from __future__ import annotations

import datetime
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from core import config
from core.db import DATA_DIR
from core.models_web import BlcmJob, User
from server.api import storage
from server.api.deps import get_current_user, get_db
from server.api.security import verify_password
from server.blcm import building as B
from server.blcm import items as I

router = APIRouter(prefix="/blcm", tags=["blcm"])
ROOT = DATA_DIR / "_건축물관리점검"


def folder(j: BlcmJob) -> Path:
    """건 폴더 "007_건축물명" — 이름이 바뀌면 예전 폴더를 옮김."""
    prefix = f"{j.id:03d}_"
    want = ROOT / (prefix + (storage._clean((j.name or "건축물")[:40]) or "건축물"))
    if want.exists():
        return want
    old = next((p for p in ROOT.glob(f"{prefix}*") if p.is_dir()), None) if ROOT.exists() else None
    if old is not None:
        try:
            old.rename(want)
        except OSError:
            return old
    return want


def _require(db: Session, user: User, jid: int) -> BlcmJob:
    j = db.get(BlcmJob, jid)
    if j is None or j.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "건축물관리점검 건을 찾을 수 없습니다.")
    return j


def _item(code: str) -> dict:
    it = I.by_code().get(code)
    if it is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"없는 점검 항목입니다: {code}")
    return it


def _touch(j: BlcmJob, user: User, *cols: str) -> None:
    for c in cols:
        flag_modified(j, c)
    j.updated_at, j.updated_by = datetime.datetime.now(), user.display_name or ""


def progress(j: BlcmJob) -> dict:
    res = j.results or {}
    ev = {code: I.evaluate(it, res.get(code)) for code, it in I.by_code().items()}
    done = sum(1 for e in ev.values() if e["state"] in ("done", "na"))
    bad = sum(1 for e in ev.values() if e.get("judge") == "부적합" or any(d.get("judge") in ("미흡", "불량", "부적합") for d in e.get("details") or []))
    photos = sum(len((r or {}).get("photos") or []) for r in res.values())
    return {"done": done, "total": len(ev), "bad": bad, "photos": photos}


def _list_out(j: BlcmJob) -> dict:
    b = j.building or {}
    return {"id": j.id, "name": j.name, "address": j.address or b.get("address") or "", "use": b.get("use") or "", "approval_date": b.get("approval_date") or "",
            "updated": f"{j.updated_at:%Y-%m-%d %H:%M}" if j.updated_at else f"{j.created_at:%Y-%m-%d %H:%M}", **progress(j)}


def _out(j: BlcmJob) -> dict:
    res = j.results or {}
    return {**_list_out(j), "building": j.building or {}, "owner": j.owner or {}, "contract": j.contract or {}, "opinion": j.opinion or {}, "memo": j.memo or "",
            "files": j.files or {}, "results": res, "eval": {code: I.evaluate(it, res.get(code)) for code, it in I.by_code().items()}}


@router.get("/items")
def get_items(user: User = Depends(get_current_user)):
    return {"groups": I.groups(), "items": [I.public(it) for it in I.items()], "text_keys": I.TEXT_KEYS}


@router.get("/jobs")
def list_jobs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(BlcmJob).filter(BlcmJob.company_id == user.company_id).order_by(BlcmJob.id.desc()).all()
    return {"jobs": [_list_out(j) for j in rows]}


def _pdf(file: UploadFile) -> bytes:
    from server.contract_docs.attachments import to_pdf_bytes

    try:
        return to_pdf_bytes(file.file.read(), file.filename or "파일")
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err


def _read_register(j: BlcmJob, data: bytes, name: str, user: User, use_ai: bool) -> dict:
    dest = folder(j) / "서류" / "건축물대장.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    files = dict(j.files or {})
    files["register"] = {"rel": "서류/건축물대장.pdf", "name": name, "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "by": user.display_name or ""}
    j.files = files
    got = B.read(dest, user.company_id, use_ai=use_ai)
    b = dict(j.building or {})
    for k, v in got.items():
        if v not in (None, "", []):
            b[k] = v
    j.building = b
    if not (j.name or "").strip() and got.get("name"):
        j.name = got["name"]
    if not (j.address or "").strip() and got.get("address"):
        j.address = got["address"]
    return got


@router.post("/jobs")
def create_job(name: str = Form(""), address: str = Form(""), ledger: UploadFile | None = File(None), ai: bool = Form(False),
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """새 건 — 건축물대장 PDF를 주면 개요를 읽어 이름·주소도 채움(이름이 비었을 때). 글자 없는 대장은 ai=1일 때만 AI로."""
    data = _pdf(ledger) if ledger is not None and ledger.filename else None
    if not name.strip() and data is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "건축물 이름을 넣거나 건축물대장을 올려 주세요.")
    j = BlcmJob(company_id=user.company_id, name=name.strip()[:80], address=address.strip()[:200], created_by=user.display_name or "",
                building={}, results={}, owner={}, contract={}, opinion={}, site={}, files={})
    db.add(j)
    db.flush()
    read = None
    if data is not None:
        read = _read_register(j, data, ledger.filename or "건축물대장.pdf", user, ai)
    if not (j.name or "").strip():
        j.name = "이름 없는 건축물"
    db.commit()
    return _out(j) | {"read": {"text_ok": bool((read or {}).get("text_ok"))} if read is not None else None}


@router.get("/jobs/{jid}")
def get_job(jid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(_require(db, user, jid))


class JobIn(BaseModel):
    name: str | None = None
    address: str | None = None
    building: dict | None = None
    owner: dict | None = None
    contract: dict | None = None
    opinion: dict | None = None
    memo: str | None = None


@router.patch("/jobs/{jid}")
def patch_job(jid: int, body: JobIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = _require(db, user, jid)
    if body.name is not None and body.name.strip():
        j.name = body.name.strip()[:80]
    if body.address is not None:
        j.address = body.address.strip()[:200]
    for col in ("building", "owner", "contract", "opinion"):
        v = getattr(body, col)
        if v is not None:
            setattr(j, col, {**(getattr(j, col) or {}), **{k: x for k, x in v.items() if isinstance(k, str)}})
    if body.memo is not None:
        j.memo = body.memo[:4000]
    _touch(j, user, "building", "owner", "contract", "opinion")
    db.commit()
    return _out(j)


@router.delete("/jobs/{jid}")
def delete_job(jid: int, password: str = Body("", embed=True), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """지우기(사진·서류까지, 되돌릴 수 없음) — 회사 공용 삭제 비밀번호."""
    h = config.get_site_delete_password_hash(user.company_id)
    if not h:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "삭제 비밀번호가 아직 없습니다. 설정에서 먼저 정하세요.")
    if not verify_password(password, h):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "삭제 비밀번호가 맞지 않습니다.")
    j = _require(db, user, jid)
    base = folder(j)
    db.delete(j)
    db.commit()
    shutil.rmtree(base, ignore_errors=True)
    return {"ok": True}


@router.post("/jobs/{jid}/register")
def upload_register(jid: int, file: UploadFile = File(...), ai: bool = Form(False), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = _require(db, user, jid)
    got = _read_register(j, _pdf(file), file.filename or "건축물대장.pdf", user, ai)
    _touch(j, user, "building", "files")
    db.commit()
    return _out(j) | {"read": {"text_ok": bool(got.get("text_ok")), "keys": [k for k in B.KEYS if got.get(k) not in (None, "", [])]}}


@router.get("/jobs/{jid}/file/{kind}")
def get_file(jid: int, kind: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = _require(db, user, jid)
    f = (j.files or {}).get(kind)
    p = folder(j) / f["rel"] if f else None
    if p is None or not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일이 없습니다.")
    return FileResponse(p, media_type="application/pdf", filename=f.get("name") or p.name, content_disposition_type="inline", headers={"Cache-Control": "no-store"})


class ItemIn(BaseModel):
    na: bool | None = None
    cmp: str | None = None
    design: str | None = None
    judge: str | None = None
    count: int | None = None
    ratings: dict | None = None
    cert: dict | None = None
    status: dict | None = None
    texts: dict | None = None


def _clean_result(it: dict, body: ItemIn, cur: dict) -> dict:
    out = dict(cur)
    if body.na is not None:
        out["na"] = bool(body.na)
    if body.cmp is not None:
        out["cmp"] = body.cmp if body.cmp in ("개선필요", "해당없음") else ""
    if body.design is not None:
        out["design"] = body.design if body.design in ("적합", "부적합", "도면없음", "해당없음") else ""
    if body.judge is not None:
        out["judge"] = body.judge if body.judge in I.FITS else ""
    if body.count is not None:
        out["count"] = max(0, min(int(body.count), 99))
    elif "count" in body.model_fields_set:
        out.pop("count", None)
    if body.ratings is not None:
        valid = {f"d{i}.s{k}" for i, d in enumerate(it["details"]) for k in range(len(d.get("subs") or []))} | {f"d{i}" for i, d in enumerate(it["details"]) if not d.get("subs")}
        out["ratings"] = {k: v for k, v in body.ratings.items() if k in valid and v in I.RATINGS + I.FITS}
    if body.cert is not None:
        out["cert"] = {k: v for k, v in body.cert.items() if v in I.CERTS}
    if body.status is not None:
        keys = {f"l{li}t{ti}": tok["t"] for li, ln in enumerate(it.get("status") or []) for ti, tok in enumerate(ln) if tok["t"] in ("check", "blank")}
        st = {}
        for k, v in body.status.items():
            if keys.get(k) == "check" and v is True:
                st[k] = True
            elif keys.get(k) == "blank" and isinstance(v, (str, int, float)) and str(v).strip() and v is not True:
                st[k] = str(v).strip()[:40]
        out["status"] = st
    if body.texts is not None:
        out["texts"] = {**(out.get("texts") or {}), **{k: str(v or "")[:3000] for k, v in body.texts.items() if k in I.TEXT_KEYS}}
    return out


@router.put("/jobs/{jid}/items/{code}")
def put_item(jid: int, code: str, body: ItemIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = _require(db, user, jid)
    it = _item(code)
    res = dict(j.results or {})
    res[code] = _clean_result(it, body, res.get(code) or {})
    j.results = res
    _touch(j, user, "results")
    db.commit()
    return {"result": res[code], "eval": I.evaluate(it, res[code]), "progress": progress(j)}


@router.post("/jobs/{jid}/items/{code}/photos")
def add_photo(jid: int, code: str, file: UploadFile = File(...), kind: str = Form("good"), caption: str = Form(""),
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """현황사진 — 사진(폰 원본도)은 긴 변 2000px JPG로(files.save_jpeg). kind = good(양호) | bad(지적)."""
    from server.contract_docs import files

    j = _require(db, user, jid)
    it = _item(code)
    pid = uuid.uuid4().hex[:10]
    rel = f"사진/{code}_{pid}.jpg"
    files.save_jpeg(file.file.read(), file.filename or "사진.jpg", folder(j) / rel)
    res = dict(j.results or {})
    r = dict(res.get(code) or {})
    r["photos"] = [*(r.get("photos") or []), {"id": pid, "rel": rel, "name": file.filename or "", "kind": "bad" if kind == "bad" else "good",
                                               "caption": caption.strip()[:60], "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}]
    res[code] = r
    j.results = res
    _touch(j, user, "results")
    db.commit()
    return {"result": r, "eval": I.evaluate(it, r), "progress": progress(j)}


class PhotoIn(BaseModel):
    caption: str | None = None
    kind: str | None = None


def _photo(j: BlcmJob, code: str, pid: str) -> tuple[dict, dict, dict]:
    res = dict(j.results or {})
    r = dict(res.get(code) or {})
    p = next((x for x in r.get("photos") or [] if x.get("id") == pid), None)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return res, r, p


@router.patch("/jobs/{jid}/items/{code}/photos/{pid}")
def patch_photo(jid: int, code: str, pid: str, body: PhotoIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = _require(db, user, jid)
    res, r, p = _photo(j, code, pid)
    r["photos"] = [{**x, **({"caption": (body.caption or "").strip()[:60]} if body.caption is not None else {}),
                    **({"kind": "bad" if body.kind == "bad" else "good"} if body.kind is not None else {})} if x.get("id") == pid else x for x in r["photos"]]
    res[code] = r
    j.results = res
    _touch(j, user, "results")
    db.commit()
    return {"result": r, "eval": I.evaluate(_item(code), r)}


@router.delete("/jobs/{jid}/items/{code}/photos/{pid}")
def delete_photo(jid: int, code: str, pid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = _require(db, user, jid)
    res, r, p = _photo(j, code, pid)
    (folder(j) / p["rel"]).unlink(missing_ok=True)
    r["photos"] = [x for x in r["photos"] if x.get("id") != pid]
    res[code] = r
    j.results = res
    _touch(j, user, "results")
    db.commit()
    return {"result": r, "eval": I.evaluate(_item(code), r), "progress": progress(j)}


@router.get("/jobs/{jid}/photo/{pid}")
def get_photo(jid: int, pid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = _require(db, user, jid)
    p = next((x for r in (j.results or {}).values() for x in (r or {}).get("photos") or [] if x.get("id") == pid), None)
    f = folder(j) / p["rel"] if p else None
    if f is None or not f.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return FileResponse(f, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


class AiIn(BaseModel):
    extra: str = ""


@router.post("/jobs/{jid}/items/{code}/ai")
def item_ai(jid: int, code: str, body: AiIn | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """사진·건축물 개요로 점검현황 체크·빈칸·글 네 칸·사진 설명 — 점검자가 정한 판정·체크는 그대로(빈 것만), 글 칸은 AI 글로. 약 30~60원."""
    from server.blcm import ai as A

    j = _require(db, user, jid)
    it = _item(code)
    if not config.has_api_key(user.company_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Claude API 키가 없어 AI 분석을 할 수 없습니다 — 설정에서 키를 넣으세요.")
    res = dict(j.results or {})
    cur = dict(res.get(code) or {})
    try:
        got = A.ask(it, cur, j.building, A.photo_bytes(folder(j), cur.get("photos") or []), user.company_id, (body.extra if body else "")[:600])
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI 분석을 못 했습니다: {str(err).splitlines()[0][:150]}") from err
    res[code] = A.merge(cur, got)
    j.results = res
    _touch(j, user, "results")
    db.commit()
    return {"result": res[code], "eval": I.evaluate(it, res[code]), "progress": progress(j), "ai": got}


class RewriteIn(BaseModel):
    label: str = ""
    current: str = ""
    note: str = ""


@router.post("/jobs/{jid}/ai/rewrite")
def ai_rewrite(jid: int, body: RewriteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """글 한 칸을 덧붙인 내용 반영해 다시 씀(app.js aiRewrite — 화면이 받은 글을 칸에 넣고 저장). 약 10원."""
    from core.report_style import rewrite_prompt
    from server.sitok import vision

    j = _require(db, user, jid)
    ctx = f"{j.name} 건축물관리법 정기점검" + (f" · {(j.building or {}).get('use')}" if (j.building or {}).get("use") else "")
    try:
        text = vision.ask(user.company_id, [], rewrite_prompt(body.label[:80], body.current[:3000], body.note[:600], ctx), max_tokens=2000, effort="low", writing=True).strip()
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI 글을 못 만들었습니다: {str(err).splitlines()[0][:120]}") from err
    if not text:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "AI 답을 읽지 못했습니다 — 다시 눌러 주세요.")
    return {"text": text}
