"""건축물관리점검(건축물관리법 정기점검) 보고서 자동화 API(2026-10-29 사용자) — 건(BlcmJob, 0069)·항목 결과·사진·AI.

- `GET  /blcm/items` — 항목표(대항목 탭·소항목 50개, 매뉴얼 25.02)
- `GET  /blcm/jobs` · `POST /blcm/jobs`(form name·address·ledger = 건축물대장 PDF) · `GET|PATCH|DELETE /blcm/jobs/{id}`(지우기 = 회사 삭제 비밀번호)
- `POST /blcm/jobs/{id}/register`(건축물대장 PDF → 건축물 개요, ai=1이면 스캔도 AI로)
- `PUT  /blcm/jobs/{id}/items/{code}` — 소항목 결과 저장(판정·점검현황·글) → 판정 계산
- `POST /blcm/jobs/{id}/items/{code}/photos`(file·kind good|bad·caption) · `PATCH|DELETE …/photos/{pid}` · `GET /blcm/jobs/{id}/photo/{pid}`
- `POST /blcm/jobs/{id}/items/{code}/ai` {extra} — 사진·대장으로 점검현황·글 채우기(점검자 판정은 그대로, 약 30~60원)
- `POST /blcm/jobs/{id}/ai/rewrite` {label, current, note} — 글 한 칸 덧붙인 내용 반영해 다시 쓰기(app.js aiRewrite, 약 10원)
- `PUT  /blcm/jobs/{id}/opinion` {plan, other, texts} — 관리계획 8줄·그 밖의 항목 12줄·주요 개선방안 의견 다섯 칸·종합의견(10/29 2단계 나머지)
- `POST /blcm/jobs/{id}/opinion/ai` {extra} — 의견·종합의견 AI(점검 결과 전부로, 약 50~100원)
- `POST|DELETE /blcm/jobs/{id}/doc/{kind}` — 보고서 서류: cover(표지 사진)·contract_doc(계약서)·site_pdf(생애이력시스템 [점검보고서 출력] PDF)
- `GET  /blcm/persons` · `POST|DELETE|GET /blcm/persons/{pid}/edu` — 참여기술자(서류 자동화 기술자)·점검교육 이수증(사람마다 한 번, 모든 건 공통)
- `POST /blcm/jobs/{id}/report` — 최종 보고서 PDF(표지·책등·제출문·등록증·명단·목차 + 본문 + 부록 계약서·이수증, server/blcm/front.py)
건 폴더 = 저장소 _건축물관리점검/NNN_건축물명(사진/·서류/·보고서/)."""
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
from core.models_web import BlcmJob, TechPerson, User
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
            "files": j.files or {}, "results": res, "eval": {code: I.evaluate(it, res.get(code)) for code, it in I.by_code().items()},
            "recap": I.recap(res), "plan_grade": I.plan_grade((j.opinion or {}).get("plan"))}


@router.get("/items")
def get_items(user: User = Depends(get_current_user)):
    return {"groups": I.groups(), "items": [I.public(it) for it in I.items()], "text_keys": I.TEXT_KEYS,
            "plan_rows": I.PLAN_ROWS, "other_rows": I.OTHER_ROWS, "other_values": I.OTHER_VALUES, "opinion_keys": [(k, lab) for k, lab, _ in I.OPINION_KEYS]}


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
    j = _require(db, user, jid)
    return _out(j) | {"people_default": default_people(db, j)}


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
    media = "image/jpeg" if p.suffix.lower() in (".jpg", ".jpeg") else "application/pdf"
    return FileResponse(p, media_type=media, filename=f.get("name") or p.name, content_disposition_type="inline", headers={"Cache-Control": "no-store"})


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
    return {"result": res[code], "eval": I.evaluate(it, res[code]), "progress": progress(j), "recap": I.recap(res)}


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
    return {"result": res[code], "eval": I.evaluate(it, res[code]), "progress": progress(j), "ai": got, "recap": I.recap(res)}


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


# ---------- 관리계획·그 밖의 항목·주요 개선방안 의견(10/29 2단계 나머지) ----------
class OpinionIn(BaseModel):
    plan: dict | None = None    # {"61": "적합"|"부적합"}
    other: dict | None = None   # {"701": {"v": "예"|"아니오"|"기타"|"해당없음", "note": "26.02.15 소방점검"}}
    texts: dict | None = None   # {func, energy, fire, struct, etc, total}


@router.put("/jobs/{jid}/opinion")
def put_opinion(jid: int, body: OpinionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = _require(db, user, jid)
    op = dict(j.opinion or {})
    if body.plan is not None:
        codes = {c for c, _ in I.PLAN_ROWS}
        op["plan"] = {k: v for k, v in body.plan.items() if k in codes and v in ("적합", "부적합")}
    if body.other is not None:
        codes = {c for c, _, _ in I.OTHER_ROWS}
        other = {k: {"v": v.get("v") if v.get("v") in I.OTHER_VALUES else "", "note": str(v.get("note") or "").strip()[:100]}
                 for k, v in body.other.items() if k in codes and isinstance(v, dict)}
        op["other"] = {k: v for k, v in other.items() if v["v"] or v["note"]}
    if body.texts is not None:
        keys = {k for k, _, _ in I.OPINION_KEYS}
        op["texts"] = {**(op.get("texts") or {}), **{k: str(v or "")[:2500] for k, v in body.texts.items() if k in keys}}
    j.opinion = op
    _touch(j, user, "opinion")
    db.commit()
    return {"opinion": op, "plan_grade": I.plan_grade(op.get("plan"))}


@router.post("/jobs/{jid}/opinion/ai")
def opinion_ai(jid: int, body: AiIn | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """주요 개선방안 의견 다섯 칸·종합의견을 점검 결과 전부로(전부 새로 — 화면이 덮기 전에 물음). 약 50~100원."""
    from server.blcm import ai as A

    j = _require(db, user, jid)
    if not config.has_api_key(user.company_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Claude API 키가 없어 AI 분석을 할 수 없습니다 — 설정에서 키를 넣으세요.")
    try:
        got = A.opinion(j, user.company_id, (body.extra if body else "")[:600])
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI 의견을 못 만들었습니다: {str(err).splitlines()[0][:150]}") from err
    op = dict(j.opinion or {})
    op["texts"] = {**(op.get("texts") or {}), **{k: v for k, v in got.items() if k != "made_at" and v}}
    op["ai"] = {"made_at": got["made_at"], "ok": True}
    j.opinion = op
    _touch(j, user, "opinion")
    db.commit()
    return {"opinion": op, "plan_grade": I.plan_grade(op.get("plan"))}


# ---------- 보고서 서류·참여기술자·최종 보고서(10/29 3단계) ----------
DOC_KINDS = {"cover": ("서류/표지사진.jpg", "표지 사진"), "contract_doc": ("서류/계약서.pdf", "계약서"),
             "site_pdf": ("서류/생애이력시스템 보고서.pdf", "생애이력시스템 보고서")}
EDU_KIND, EDU_LABEL = "blcm_edu", "건축물관리점검 교육 이수증"
DEFAULT_ROLES = ("과업 책임기술자", "현장조사 및 보고서 작성")


@router.post("/jobs/{jid}/doc/{kind}")
def upload_doc(jid: int, kind: str, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """표지 사진(JPG) · 계약서(PDF, 사진이면 PDF로) · 생애이력시스템 보고서(사이트 [점검보고서 출력] PDF — 목차 쪽 번호를 여기서 찾음)."""
    import pymupdf

    from server.blcm import front as F
    from server.contract_docs import files

    j = _require(db, user, jid)
    if kind not in DOC_KINDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 서류 종류입니다.")
    rel, label = DOC_KINDS[kind]
    dest = folder(j) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    info = {}
    if kind == "cover":
        files.save_jpeg(file.file.read(), file.filename or "표지.jpg", dest)
    elif kind == "site_pdf":
        data = file.file.read()
        if data[:4] != b"%PDF":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "생애이력시스템 [점검보고서 출력]에서 PDF로 저장한 파일을 올려 주세요.")
        pages = F.toc_pages(data)
        if "detail" not in pages or "law" not in pages:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "생애이력시스템 점검보고서 PDF가 아닌 것 같습니다(정기점검표·점검 세부 항목을 못 찾음).")
        with pymupdf.open(stream=data, filetype="pdf") as d:
            info = {"pages": d.page_count, "toc": pages}
        dest.write_bytes(data)
    else:
        dest.write_bytes(_pdf(file))
    fl = dict(j.files or {})
    fl[kind] = {"rel": rel, "name": file.filename or label, "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "by": user.display_name or "", **info}
    j.files = fl
    _touch(j, user, "files")
    db.commit()
    return _out(j)


@router.delete("/jobs/{jid}/doc/{kind}")
def delete_doc(jid: int, kind: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = _require(db, user, jid)
    if kind not in DOC_KINDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 서류 종류입니다.")
    fl = dict(j.files or {})
    f = fl.pop(kind, None)
    if f:
        (folder(j) / f["rel"]).unlink(missing_ok=True)
    j.files = fl
    _touch(j, user, "files")
    db.commit()
    return _out(j)


def _grade_text(p: TechPerson) -> str:
    return (p.grade or "").replace("기술자", "기술인")


def _person_last(db: Session, company_id: int) -> dict[int, dict]:
    """사람마다 가장 최근 건 명단에 적은 직위·자격 및 등급 — 건축물관리점검은 "특급기술인"처럼 서류 자동화 등급과 다를 수 있어 한 번 고치면 다음 건에 그대로."""
    out: dict[int, dict] = {}
    for jj in db.query(BlcmJob).filter(BlcmJob.company_id == company_id).order_by(BlcmJob.id.desc()).limit(50):
        for x in (jj.contract or {}).get("people") or []:
            if isinstance(x, dict) and x.get("person_id") and x["person_id"] not in out:
                out[x["person_id"]] = x
    return out


def default_people(db: Session, j: BlcmJob) -> list[dict]:
    """명단 기본값 — 점검책임자·점검자 이름(점검 정보)을 기술자 목록에서 찾아, 없으면 최근 건 명단 그대로."""
    persons = db.query(TechPerson).filter(TechPerson.company_id == j.company_id, TechPerson.active.is_(True)).order_by(TechPerson.id).all()
    last = _person_last(db, j.company_id)
    by_name = {p.name.replace(" ", ""): p for p in persons}
    c = j.contract or {}
    out = []
    for i, nm in enumerate(x for x in (c.get("chief"), c.get("inspector")) if (x or "").strip()):
        p = by_name.get(nm.replace(" ", ""))
        lx = last.get(p.id, {}) if p else {}
        out.append({"person_id": p.id if p else None, "role": DEFAULT_ROLES[min(i, 1)], "name": p.name if p else nm.strip(),
                    "position": lx.get("position") or (p.position if p else ""), "grade": lx.get("grade") or (_grade_text(p) if p else ""), "note": "-"})
    if not out:
        recent = next((jj for jj in db.query(BlcmJob).filter(BlcmJob.company_id == j.company_id, BlcmJob.id != j.id).order_by(BlcmJob.id.desc()).limit(20)
                       if (jj.contract or {}).get("people")), None)
        if recent is not None:
            out = [dict(x) for x in recent.contract["people"] if isinstance(x, dict)]
    return out


@router.get("/persons")
def list_persons(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """참여기술자 고르기 — 서류 자동화 기술자 + 이수증 있는지 + 최근 건에 적은 직위·등급."""
    from server.api.routers import contract_library as lib

    last = _person_last(db, user.company_id)
    out = []
    for p in db.query(TechPerson).filter(TechPerson.company_id == user.company_id, TechPerson.active.is_(True)).order_by(TechPerson.id):
        doc = lib.person_docs(db, p.id).get(EDU_KIND)
        lx = last.get(p.id, {})
        out.append({"id": p.id, "name": p.name, "position": lx.get("position") or p.position or "", "grade": lx.get("grade") or _grade_text(p),
                    "edu": bool(doc and doc.file and Path(doc.file).exists()), "edu_ts": int(doc.updated_at.timestamp()) if doc and doc.updated_at else 0})
    return {"persons": out}


@router.post("/persons/{pid}/edu")
def upload_edu(pid: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """점검교육 이수증(건축물관리점검 신규·보수교육) — 사람마다 한 번 올리면 모든 건 부록.2에. 서류 자동화와 같은 서류 표(SubmitDoc kind blcm_edu)."""
    from server.api.routers import contract_library as lib
    from server.contract_docs import files

    p = lib._require_person(db, user, pid)
    lib._upload_dated(db, user, file, EDU_KIND, EDU_LABEL, files.person_doc_path(p.id, p.name, EDU_LABEL), lib.person_docs(db, p.id).get(EDU_KIND), p.id, "", "")
    return list_persons(user, db)


@router.delete("/persons/{pid}/edu")
def delete_edu(pid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from server.api.routers import contract_library as lib

    p = lib._require_person(db, user, pid)
    lib._drop_doc(db, lib.person_docs(db, p.id).get(EDU_KIND))
    return list_persons(user, db)


@router.get("/persons/{pid}/edu")
def get_edu(pid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from server.api.routers import contract_library as lib

    p = lib._require_person(db, user, pid)
    doc = lib.person_docs(db, p.id).get(EDU_KIND)
    if doc is None or not doc.file or not Path(doc.file).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "이수증이 없습니다.")
    return FileResponse(doc.file, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/jobs/{jid}/report")
def make_report(jid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """최종 보고서 PDF — 표지 원본 채우기(한글 PDF, 10~30초) + 생애이력시스템 보고서 + 부록(계약서·이수증). 앞부분 hwpx도 남김(한글로 손볼 때)."""
    from server.api.routers import contract_library as lib
    from server.blcm import front as F
    from server.contract_docs.hwp_queue import convert_via_worker

    j = _require(db, user, jid)
    if not F.TEMPLATE.exists():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "표지 원본(표지 및 내용)이 아직 없습니다 — 관리자에게 알려 주세요.")
    fl = j.files or {}
    base = folder(j)
    site = base / fl["site_pdf"]["rel"] if fl.get("site_pdf") else None
    if site is None or not site.exists():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "생애이력시스템 보고서 PDF를 먼저 올려 주세요(사이트 [점검보고서 출력] → PDF로 저장).")
    site_bytes = site.read_bytes()
    people = [x for x in ((j.contract or {}).get("people") or default_people(db, j)) if isinstance(x, dict) and (x.get("name") or "").strip()]
    if not people:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "참여기술자 명단이 비었습니다 — [📕 보고서 만들기]에서 기술자를 고르세요.")
    cover_f = base / fl["cover"]["rel"] if fl.get("cover") else None
    cover = cover_f.read_bytes() if cover_f is not None and cover_f.exists() else None
    try:
        hwpx, notes = F.fill(j.name, j.address or (j.building or {}).get("address") or "", j.contract, people, F.toc_pages(site_bytes), cover)
        front_pdf = convert_via_worker(hwpx, ".hwpx", wait=300)
    except RuntimeError as err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(err)) from err
    contract_doc = None
    cf = base / fl["contract_doc"]["rel"] if fl.get("contract_doc") else None
    if cf is not None and cf.exists():
        contract_doc = (cf.read_bytes(), fl["contract_doc"].get("name") or "계약서.pdf")
    edu, miss = [], []
    for x in people:
        doc = lib.person_docs(db, x["person_id"]).get(EDU_KIND) if x.get("person_id") else None
        if doc is not None and doc.file and Path(doc.file).exists():
            edu.append((Path(doc.file).read_bytes(), f"{x['name']} 이수증.jpg"))
        else:
            miss.append(x["name"])
    try:
        pdf, info, more = F.assemble(front_pdf, site_bytes, contract_doc, edu)
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
    notes += [m for m in more if not m.startswith("점검교육 이수증이 없어")]
    if miss:
        notes.append("점검교육 이수증이 없는 사람: " + ", ".join(miss) + " — 명단의 [📎 이수증]으로 올리세요")
    name = f"{storage._clean(j.name) or '건축물'} 건축물관리점검 보고서.pdf"
    out = base / "보고서" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pdf)
    (base / "보고서" / "앞부분.hwpx").write_bytes(hwpx)
    fl = dict(j.files or {})
    fl["report"] = {"rel": f"보고서/{name}", "name": name, "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "by": user.display_name or "",
                    **info, "mb": round(len(pdf) / 1e6, 1), "notes": notes}
    j.files = fl
    _touch(j, user, "files")
    db.commit()
    return _out(j) | {"people_default": default_people(db, j)}
