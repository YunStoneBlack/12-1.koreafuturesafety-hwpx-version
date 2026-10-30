"""건축물관리점검(건축물관리법 정기점검) 보고서 자동화 API(2026-10-29 사용자) — 건(BlcmJob, 0069)·항목 결과·사진·AI.

- `GET  /blcm/items` — 항목표(대항목 탭·소항목 50개, 매뉴얼 25.02)
- `GET  /blcm/jobs` · `POST /blcm/jobs`(form name·address·ledger = 건축물대장 PDF) · `GET|PATCH|DELETE /blcm/jobs/{id}`(지우기 = 회사 삭제 비밀번호)
- `POST /blcm/jobs/{id}/register`(건축물대장 PDF → 건축물 개요, ai=1이면 스캔도 AI로)
- `PUT  /blcm/jobs/{id}/items/{code}` — 소항목 결과 저장(판정·점검현황·글) → 판정 계산
- `POST /blcm/jobs/{id}/items/{code}/photos`(file·kind good|bad·caption·slot·bad = 부적합 칸 key) · `PATCH|DELETE …/photos/{pid}` · `GET /blcm/jobs/{id}/photo/{pid}`
  — 부적합 칸(items.bad_types) 사진이면 판정·변경 유형 체크를 사진대로(items.apply_photos, 10/30 사용자 "지적 사진을 넣어도 적합으로 표시됨")
- `POST /blcm/jobs/{id}/items/{code}/ai` {extra} — 사진·대장으로 점검현황·글 채우기(점검자 판정은 그대로, 약 30~60원)
- `POST /blcm/jobs/{id}/drawings`(file PDF·그림 — PDF는 쪽마다) · `DELETE …/drawings/{did}` · `GET …/drawings/{did}/img` · `POST …/drawings/register`(올린 건축물대장 쪽) —
  📐 도면·서류 그림 모음(files.drawings, 10/30 사용자 "도면 넣는 칸은 따로 빼서 한꺼번에 넣고 해당 위치로") · `PUT /blcm/jobs/{id}/items/{code}/slot/{n}` {drawing}
  — 그 항목 견본 도면 칸에 고른 그림(현황사진으로 복사, photos[].slot·drawing). 사진 올리기 slot = 견본 칸(같은 칸 사진은 바꿈), 개수 제한 없음.
- `GET  /blcm/jobs/{id}/plan` · `PUT …/facts` {facts} · `POST …/plan/na` {codes?, evidence} — 점검 목록([① 서류검토 확정] = 해당없음·사유 + 근거 그림 — 대장 칸·확인원·법령 조문 빨간 네모, server/blcm/evidence.py)(server/blcm/applicability.py — 법령상 적용대상 판정, 회사 결정 = 추천안):
  반드시 찍을 사진 / 있으면 찍을 사진 / 면담·서류로 확인 / 해당없음(사유) / 확인 필요, 현장·면담 답은 contract.facts, 해당없음 넣기 = 손대지 않은 항목에 na + 비고 사유(10/30)
- `POST /blcm/jobs/{id}/landuse`(토지이용계획확인원 PDF·그림) — 서류/토지이용계획확인원.pdf + 쪽을 도면 모음에(3.5.8 칸), 지정여부 칸에서 방화지구·가로구역 높이·지구단위계획을 읽어
  점검 목록 답으로(server/blcm/doc_facts.py — 대장 승강기·인증·건축주·변동사항도, 점검자 답이 이김, 10/30)
- `GET  /blcm/bad-samples` · `PUT /blcm/bad-samples` {code, key, file|null, ok} — 부적합 견본 고르기(회사 보고서 후보 server/scripts/scan_blcm_bad_samples.py → 형·민재형이 고름, items.bad_file, 10/30)
- `GET  /blcm/samples/{file}` — 견본 참고 사진(우리프라자 보고서 현황사진, server/blcm/samples.json·저장소 _건축물관리점검/_참고사진, 10/30)
- `GET  /blcm/jobs/{id}/check` · `POST /blcm/jobs/{id}/done` {done} — 빠진 것(소항목마다 items.missing + 관리계획·그 밖의 항목·의견)·[✓ 점검 완료](contract.field_done, 10/30)
- `POST /blcm/jobs/{id}/ai/rewrite` {label, current, note} — 글 한 칸 덧붙인 내용 반영해 다시 쓰기(app.js aiRewrite, 약 10원)
- `PUT  /blcm/jobs/{id}/opinion` {plan, other, texts} — 관리계획 8줄·그 밖의 항목 12줄·주요 개선방안 의견 다섯 칸·종합의견(10/29 2단계 나머지)
- `POST /blcm/jobs/{id}/opinion/ai` {extra} — 의견·종합의견 AI(점검 결과 전부로, 약 50~100원)
- `POST|DELETE /blcm/jobs/{id}/doc/{kind}` — 보고서 서류: cover(표지 사진)·contract_doc(계약서)·site_pdf(생애이력시스템 [점검보고서 출력] PDF)
- `GET  /blcm/persons` · `POST|DELETE|GET /blcm/persons/{pid}/edu` — 참여기술자(서류 자동화 기술자)·점검교육 이수증(사람마다 한 번, 모든 건 공통)
- `POST /blcm/jobs/{id}/report` — 최종 보고서 PDF(표지·책등·제출문·등록증·명단·목차 + 본문 + 부록 계약서·이수증, server/blcm/front.py)
- `GET|PUT /blcm/account` — 회사 생애이력시스템 계정(app_setting 암호화, 바꾸기는 관리자) · `POST /blcm/jobs/{id}/site/run` {mode list|practice|save} ·
  `PUT …/site/target` {oprtn} · `GET …/site` · `GET …/site/shot/{name}` — 입력 봇(10/29 4단계, server/blcm/bot.py — 제출은 안 누름)
건 폴더 = 저장소 _건축물관리점검/NNN_건축물명(사진/·서류/·보고서/)."""
from __future__ import annotations

import datetime
import json
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile, status
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
SAMPLE_DIR = ROOT / "_참고사진"


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


def _ev(it: dict, r: dict | None, use: str = "") -> dict:
    """판정 + 빠진 것(miss, 10/30) — 화면 카드 머리 ⚠·[✓ 점검 완료] + 잠금(locks — 개수·숫자로 정해지는 판정·설계도서 적합여부, items.ui_locks)."""
    return {**I.evaluate(it, r), "miss": I.missing(it, r), "locks": I.ui_locks(it, r, use)}


def _use(j: BlcmJob) -> str:
    """주용도(3.5.6 반자높이 — 집회·종교·장례·위락은 다른 기준이라 손으로)."""
    return str((j.building or {}).get("use") or "")


def _norm(j: BlcmJob, it: dict, r: dict, prev: dict | None = None, photos: bool = False) -> dict:
    """저장 전 정리(10/30) — 사진 → 판정(photos면) 뒤 하나만 고르는 줄·개수로 정해지는 판정·설계도서 적합여부(items.normalize)."""
    return I.normalize(it, I.apply_photos(it, r) if photos else r, prev, _use(j))


def _list_out(j: BlcmJob) -> dict:
    b = j.building or {}
    return {"id": j.id, "name": j.name, "address": j.address or b.get("address") or "", "use": b.get("use") or "", "approval_date": b.get("approval_date") or "",
            "updated": f"{j.updated_at:%Y-%m-%d %H:%M}" if j.updated_at else f"{j.created_at:%Y-%m-%d %H:%M}", **progress(j)}


def _out(j: BlcmJob) -> dict:
    by = I.by_code()
    res = {c: (I.normalize(by[c], r, use=_use(j)) if c in by and r else r) for c, r in (j.results or {}).items()}  # 예전 값도 규칙대로 보여 줌(고치면 그대로 저장)
    return {**_list_out(j), "building": j.building or {}, "owner": j.owner or {}, "contract": j.contract or {}, "opinion": j.opinion or {}, "memo": j.memo or "",
            "files": j.files or {}, "results": res, "eval": {code: _ev(it, res.get(code), _use(j)) for code, it in I.by_code().items()},
            "field_done": (j.contract or {}).get("field_done"),  # [✓ 점검 완료](10/30)
            "recap": I.recap(res), "plan_grade": I.plan_grade((j.opinion or {}).get("plan")), "site": _site_out(j)}


@router.get("/items")
def get_items(user: User = Depends(get_current_user)):
    return {"groups": I.groups(), "items": [I.public(it) for it in I.items()], "text_keys": I.TEXT_KEYS,
            "places": I.PLACES, "item_places": I.ITEM_PLACES, "samples": I.samples(),  # 장소별 묶음·견본(10/30)
            "slots": {it["code"]: I.slots(it["code"]) for it in I.items()},  # 견본 칸 — 현장 사진·도면(10/30)
            "bad_types": {it["code"]: I.bad_types(it) for it in I.items()},  # 부적합 칸 — 변경 유형·작은 점검마다(10/30)
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


def _floors(j: BlcmJob) -> list:
    """층별 개요 — 저장된 것보다 올린 대장을 칸 차례로 다시 읽은 것이 많으면 그것(10/30 — 두 단 표·두 줄 용도 칸을 놓치던 대장이 있음)."""
    from server.sitok import seismic_docs as SD

    stored = (j.building or {}).get("floors") or []
    reg = (j.files or {}).get("register")
    f = folder(j) / reg["rel"] if reg else None
    if f is not None and f.exists():
        try:
            cells = SD._floor_cells(f)
        except Exception:  # noqa: BLE001 — 못 읽으면 저장된 것
            cells = []
        if len(cells) > len(stored):
            return cells
    return stored


def _docs(j: BlcmJob) -> dict:
    """서류(대장·토지이용계획확인원)에서 미리 읽은 점검 목록 답 — 파일이 바뀔 때만 다시 읽음(doc_facts 캐시)."""
    from server.blcm import doc_facts as DF

    path = lambda k: folder(j) / (j.files or {})[k]["rel"] if (j.files or {}).get(k) else None  # noqa: E731
    return DF.read(path("register"), path("landuse"), j.building or {})


def _plan(j: BlcmJob) -> dict:
    from server.blcm import applicability as AP

    d = _docs(j)
    b = {**(j.building or {}), "changes": d["changes"]}
    p = AP.plan(b, (j.contract or {}).get("facts") or {}, j.results or {}, _floors(j), d["auto"])
    land = (j.files or {}).get("landuse")
    p["docs"] = {"landuse": ({**land, "text_ok": bool((d["land"] or {}).get("text_ok")), "section": (d["land"] or {}).get("section", "")} if land else None),
                 "register": bool((j.files or {}).get("register"))}
    return p


LAND_NAME = "토지이용계획확인원"


@router.post("/jobs/{jid}/landuse")
def upload_landuse(jid: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """토지이용계획확인원(토지이음 출력 PDF 또는 그림) — 저장 + 쪽을 도면 모음에(예전 확인원 쪽은 빼고), 점검 목록 다시."""
    j = _require(db, user, jid)
    data = _pdf(file)
    dest = folder(j) / "서류" / f"{LAND_NAME}.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    files = dict(j.files or {})
    files["landuse"] = {"rel": f"서류/{LAND_NAME}.pdf", "name": file.filename or f"{LAND_NAME}.pdf",
                        "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "by": user.display_name or ""}
    j.files = files
    keep = []
    for d in _drawings(j):
        if d.get("name") == LAND_NAME:
            (folder(j) / d["rel"]).unlink(missing_ok=True)
        else:
            keep.append(d)
    pages = [dict(x, name=LAND_NAME) for x in _add_pages(j, data, LAND_NAME)]
    _save_drawings(j, user, keep + pages)
    db.commit()
    return {**_out(j), **_drawings_out(j), "plan": _plan(j)}


@router.get("/jobs/{jid}/plan")
def get_plan(jid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _plan(_require(db, user, jid))


class FactsIn(BaseModel):
    facts: dict


@router.put("/jobs/{jid}/facts")
def put_facts(jid: int, body: FactsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """현장·면담·서류 답(있음/없음, 빈 글 = 지움) — 점검 목록을 다시 판정해 돌려줌."""
    from server.blcm import applicability as AP

    j = _require(db, user, jid)
    c = dict(j.contract or {})
    facts = dict(c.get("facts") or {})
    for k, v in body.facts.items():
        if k not in AP.FACTS:
            continue
        if v in ("있음", "없음"):
            facts[k] = v
        else:
            facts.pop(k, None)
    c["facts"] = facts
    j.contract = c
    _touch(j, user, "contract")
    db.commit()
    return _plan(j)


class NaIn(BaseModel):
    codes: list[str] | None = None
    evidence: bool = True  # 근거 그림(대장·확인원·법령)도 넣기(10/30)


def _evidence(j: BlcmJob, code: str, r: dict, v: dict) -> dict:
    """해당없음 근거 그림 — 예전 근거 그림은 빼고(파일도) 새로(대장 칸·확인원·법령 조문, 빨간 네모)."""
    from server.blcm import evidence as EV

    keep = []
    for x in r.get("photos") or []:
        if x.get("evidence"):
            (folder(j) / x["rel"]).unlink(missing_ok=True)
        else:
            keep.append(x)
    path = lambda k: folder(j) / (j.files or {})[k]["rel"] if (j.files or {}).get(k) else None  # noqa: E731
    try:
        shots = EV.make(v.get("why") or "", v.get("reason") or "", path("register"), path("landuse"))
    except Exception:  # noqa: BLE001 — 그림을 못 만들면 사유만
        shots = []
    (folder(j) / "사진").mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    for img, cap, kind in shots:
        pid = uuid.uuid4().hex[:10]
        rel = f"사진/{code}_{pid}.jpg"
        (folder(j) / rel).write_bytes(img)
        keep.append({"id": pid, "rel": rel, "name": "", "kind": "good", "caption": cap[:60], "evidence": kind, "at": now})
    return {**r, "photos": keep, "ev_done": True}


@router.post("/jobs/{jid}/plan/na")
def apply_na(jid: int, body: NaIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """[① 서류검토 확정] 법령상 해당없음 항목을 한꺼번에 해당없음으로 — 비고 = 사유(비어 있을 때만) + 근거 그림(evidence).
    점검자가 판정·사진을 넣은 항목은 건드리지 않음. 이미 해당없음으로 넣었는데 근거 그림이 없는 항목은 그림만 더함."""
    j = _require(db, user, jid)
    p = _plan(j)
    res = dict(j.results or {})
    done = []
    for code, v in p["items"].items():
        if v["state"] != "na" or (body.codes is not None and code not in body.codes):
            continue
        r = dict(res.get(code) or {})
        if v["touched"]:
            if body.evidence and r.get("na") and not v.get("evidence") and not v.get("ev_done"):
                res[code] = _evidence(j, code, r, v)
                done.append(code)
            continue
        tx = dict(r.get("texts") or {})
        if not (tx.get("rm") or "").strip():
            tx["rm"] = v["reason"]
        r.update(na=True, texts=tx)
        res[code] = _evidence(j, code, r, v) if body.evidence else r
        done.append(code)
    j.results = res
    _touch(j, user, "results")
    db.commit()
    return {**_out(j), "plan": _plan(j), "applied": done}


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
    prev = res.get(code) or {}
    res[code] = _norm(j, it, _clean_result(it, body, prev), prev)
    j.results = res
    _touch(j, user, "results")
    db.commit()
    return {"result": res[code], "eval": _ev(it, res[code], _use(j)), "progress": progress(j), "recap": I.recap(res)}


@router.post("/jobs/{jid}/items/{code}/photos")
def add_photo(jid: int, code: str, file: UploadFile = File(...), kind: str = Form("good"), caption: str = Form(""), slot: int | None = Form(None),
              bad: str = Form(""), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """현황사진 — 사진(폰 원본도)은 긴 변 2000px JPG로(files.save_jpeg). kind = good(양호) | bad(지적). 장수 제한 없음(10/30 사용자).
    slot = 견본 칸 번호(10/30 — 그 칸에 사진이 있으면 바꿈, 설명이 비면 견본 설명)."""
    from server.contract_docs import files

    j = _require(db, user, jid)
    it = _item(code)
    pid = uuid.uuid4().hex[:10]
    rel = f"사진/{code}_{pid}.jpg"
    files.save_jpeg(file.file.read(), file.filename or "사진.jpg", folder(j) / rel)
    res = dict(j.results or {})
    r = dict(res.get(code) or {})
    keep, old = _take_slot(j, r, slot)
    sl = I.slot(code, slot)
    cap = caption.strip()[:60] or (old[0].get("caption") if old else "") or (sl["caption"] if sl else "")
    p = {"id": pid, "rel": rel, "name": file.filename or "", "kind": "bad" if kind == "bad" else "good", "caption": cap,
         "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
    if sl:
        p["slot"] = slot
        if sl["draw"]:  # 도면 칸을 현장에서 찍은 것(반출이 안 될 때, 10/30) — 도면 그림, 늘 양호
            p["is_draw"], p["kind"] = True, "good"
        else:  # 견본(적합) 칸 = 양호
            p["kind"] = "good"
    bt = _bad_type(it, bad)
    if bt:  # 부적합 칸(10/30) — 지적 사진 + 그 유형, 설명이 비면 유형 이름
        p.update(kind="bad", bad={"key": bt["key"], "label": bt["label"]}, caption=caption.strip()[:60] or bt["label"][:60])
    r["photos"] = [*keep, p]
    r = _norm(j, it, r, res.get(code), photos=True)
    res[code] = r
    j.results = res
    _touch(j, user, "results")
    db.commit()
    return {"result": r, "eval": _ev(it, r, _use(j)), "progress": progress(j)}


class PhotoIn(BaseModel):
    caption: str | None = None
    kind: str | None = None
    bad: str | None = None  # 부적합 칸 key("" = 칸 빼기)


def _bad_type(it: dict, key: str | None) -> dict | None:
    if not key:
        return None
    bt = next((x for x in I.bad_types(it) if x["key"] == key), None)
    if bt is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "그런 부적합 칸이 없습니다.")
    return bt


def _take_slot(j: BlcmJob, r: dict, n: int | None) -> tuple[list, list]:
    """견본 칸 n의 예전 사진을 빼고 파일도 지움 → (남길 사진, 뺀 예전 사진). n이 없으면(더 찍기) 그대로."""
    old = [x for x in r.get("photos") or [] if n is not None and x.get("slot") == n]
    for x in old:
        (folder(j) / x["rel"]).unlink(missing_ok=True)
    return [x for x in r.get("photos") or [] if x not in old], old


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
    it = _item(code)
    bt = _bad_type(it, body.bad) if body.bad else None

    def upd(x: dict) -> dict:
        x = {**x, **({"caption": (body.caption or "").strip()[:60]} if body.caption is not None else {}),
             **({"kind": "bad" if body.kind == "bad" else "good"} if body.kind is not None else {})}
        if bt:
            x.update(kind="bad", bad={"key": bt["key"], "label": bt["label"]})
        elif body.bad == "" or x.get("kind") != "bad":  # 칸 빼기·양호로 바꾸면 유형도 뺌
            x.pop("bad", None)
        return x

    r["photos"] = [upd(x) if x.get("id") == pid else x for x in r["photos"]]
    r = _norm(j, it, r, res.get(code), photos=True)
    res[code] = r
    j.results = res
    _touch(j, user, "results")
    db.commit()
    return {"result": r, "eval": _ev(it, r, _use(j))}


@router.delete("/jobs/{jid}/items/{code}/photos/{pid}")
def delete_photo(jid: int, code: str, pid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = _require(db, user, jid)
    res, r, p = _photo(j, code, pid)
    (folder(j) / p["rel"]).unlink(missing_ok=True)
    r["photos"] = [x for x in r["photos"] if x.get("id") != pid]
    r = _norm(j, _item(code), r, res.get(code), photos=True)
    res[code] = r
    j.results = res
    _touch(j, user, "results")
    db.commit()
    return {"result": r, "eval": _ev(_item(code), r, _use(j)), "progress": progress(j)}


@router.get("/jobs/{jid}/photo/{pid}")
def get_photo(jid: int, pid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = _require(db, user, jid)
    p = next((x for r in (j.results or {}).values() for x in (r or {}).get("photos") or [] if x.get("id") == pid), None)
    f = folder(j) / p["rel"] if p else None
    if f is None or not f.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return FileResponse(f, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


# ---------- 📐 도면·서류 그림 모음(10/30 사용자) — 한꺼번에 올리고 항목 견본 도면 칸에 고름 ----------
def _drawings(j: BlcmJob) -> list[dict]:
    return list((j.files or {}).get("drawings") or [])


def _save_drawings(j: BlcmJob, user: User, items: list[dict]) -> None:
    f = dict(j.files or {})
    f["drawings"] = items
    j.files = f
    _touch(j, user, "files")


def _add_pages(j: BlcmJob, data: bytes, name: str) -> list[dict]:
    """PDF는 쪽마다 200dpi JPG(도면은 원본 화질 규칙 — 줄이지 않음), 그림은 JPG면 그대로·아니면 JPG로. 쪽 글에서 도면 이름(정면도·배치도 …)을 찾아 label에."""
    import io
    import re

    import pymupdf
    from PIL import Image, ImageOps

    out = []
    d = folder(j) / "도면"
    d.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", name or "도면")[:40]
    if data.startswith(b"%PDF"):
        doc = pymupdf.open(stream=data, filetype="pdf")
        if doc.page_count > 80:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"쪽이 너무 많습니다({doc.page_count}쪽) — 필요한 도면만 80쪽 안으로 나눠 올려 주세요.")
        for i, page in enumerate(doc):
            did = uuid.uuid4().hex[:10]
            (d / f"{did}.jpg").write_bytes(page.get_pixmap(dpi=200).tobytes("jpg", jpg_quality=90))
            words = re.findall(r"[0-9가-힣]*(?:정면도|배면도|측면도|배치도|평면도|입면도|단면도|조경)[가-힣]*", re.sub(r"\s", "", page.get_text()))
            out.append({"id": did, "rel": f"도면/{did}.jpg", "name": stem, "page": i + 1, "hint": " ".join(dict.fromkeys(words))[:80]})
    else:
        try:
            im = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
        except Exception as err:  # noqa: BLE001
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "PDF나 그림 파일(jpg·png)을 올려 주세요.") from err
        did = uuid.uuid4().hex[:10]
        if data[:3] == b"\xff\xd8\xff" and im.format != "MPO":
            (d / f"{did}.jpg").write_bytes(data)
        else:
            im.convert("RGB").save(d / f"{did}.jpg", "JPEG", quality=92)
        out.append({"id": did, "rel": f"도면/{did}.jpg", "name": stem, "page": None, "hint": ""})
    return out


def _drawings_out(j: BlcmJob) -> dict:
    used = {}
    for code, r in (j.results or {}).items():
        for p in (r or {}).get("photos") or []:
            if p.get("drawing"):
                used.setdefault(p["drawing"], []).append(f"{code}")
    return {"drawings": [{**x, "used": used.get(x["id"], [])} for x in _drawings(j)], "results": j.results or {},
            "eval": {code: _ev(it, (j.results or {}).get(code), _use(j)) for code, it in I.by_code().items()}}


@router.post("/jobs/{jid}/drawings")
def add_drawings(jid: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = _require(db, user, jid)
    pages = _add_pages(j, file.file.read(), file.filename or "도면")
    _save_drawings(j, user, _drawings(j) + pages)
    db.commit()
    return _drawings_out(j)


@router.post("/jobs/{jid}/drawings/register")
def add_register_pages(jid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """올린 건축물대장 PDF 쪽을 그림 모음에(3.1.15 등 견본 "건축물 대장" 칸)."""
    j = _require(db, user, jid)
    reg = (j.files or {}).get("register")
    f = folder(j) / reg["rel"] if reg else None
    if f is None or not f.exists():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "건축물대장을 먼저 올려 주세요(위 🏢 건축물대장 올리기).")
    pages = [dict(x, name="건축물대장") for x in _add_pages(j, f.read_bytes(), "건축물대장")]
    _save_drawings(j, user, _drawings(j) + pages)
    db.commit()
    return _drawings_out(j)


@router.delete("/jobs/{jid}/drawings/{did}")
def delete_drawing(jid: int, did: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """모음에서 지우기 — 항목에 넣은 것(현황사진에 복사한 것)은 그대로."""
    j = _require(db, user, jid)
    items = _drawings(j)
    x = next((d for d in items if d["id"] == did), None)
    if x is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "그림이 없습니다.")
    (folder(j) / x["rel"]).unlink(missing_ok=True)
    _save_drawings(j, user, [d for d in items if d["id"] != did])
    db.commit()
    return _drawings_out(j)


@router.get("/jobs/{jid}/drawings/{did}/img")
def drawing_img(jid: int, did: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = _require(db, user, jid)
    x = next((d for d in _drawings(j) if d["id"] == did), None)
    f = folder(j) / x["rel"] if x else None
    if f is None or not f.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "그림이 없습니다.")
    return FileResponse(f, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


class SlotIn(BaseModel):
    drawing: str | None = None  # 모음 그림 id, 비우면 그 칸 비움


@router.put("/jobs/{jid}/items/{code}/slot/{n}")
def set_slot(jid: int, code: str, n: int, body: SlotIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """견본 도면 칸 n에 모음 그림 넣기(현황사진으로 복사 — 설명 = 견본 설명, 양호) / 비우기."""
    j = _require(db, user, jid)
    it = _item(code)
    sl = I.slot(code, n)
    if sl is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "그런 견본 칸이 없습니다.")
    res = dict(j.results or {})
    r = dict(res.get(code) or {})
    keep, old = _take_slot(j, r, n)
    if body.drawing:
        src = next((d for d in _drawings(j) if d["id"] == body.drawing), None)
        if src is None or not (folder(j) / src["rel"]).exists():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "그림이 없습니다 — 도면 모음을 다시 여세요.")
        pid = uuid.uuid4().hex[:10]
        rel = f"사진/{code}_{pid}.jpg"
        (folder(j) / "사진").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(folder(j) / src["rel"], folder(j) / rel)
        keep.append({"id": pid, "rel": rel, "name": f"{src['name']}" + (f" {src['page']}쪽" if src.get("page") else ""), "kind": "good",
                     "caption": (old[0].get("caption") if old else "") or sl["caption"], "slot": n, "drawing": src["id"], "is_draw": True,
                     "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
    r["photos"] = keep
    res[code] = r
    j.results = res
    _touch(j, user, "results")
    db.commit()
    return {"result": r, "eval": _ev(it, r, _use(j)), "progress": progress(j)}


@router.get("/samples/{name:path}")
def sample_photo(name: str, user: User = Depends(get_current_user)):
    """견본 참고 사진(10/30 사용자 "우리프라자를 기준으로 해당 항목 샘플 참고사진") — 회사 공통. 후보/… = 부적합 견본 후보(회사 보고서)."""
    import re

    if not re.fullmatch(r"3\.\d\.\d{1,2}_\d{1,2}\.jpg|후보/3\.\d\.\d{1,2}_[0-9a-f]{10}\.jpg", name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    f = SAMPLE_DIR / name
    if not f.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return FileResponse(f, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


def _cands() -> dict:
    try:
        return json.loads((SAMPLE_DIR / "후보" / "candidates.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


@router.get("/bad-samples")
def get_bad_samples(user: User = Depends(get_current_user)):
    """부적합 견본 고르기 — 항목마다 부적합 칸(지금 견본·검토 여부)과 회사 보고서 후보(점수 순)."""
    cands = _cands()
    out = []
    for it in I.items():
        types = I.bad_types(it)
        if not types:
            continue
        out.append({"code": it["code"], "name": it["name"], "big": it["big"],
                    "types": [{"key": t["key"], "label": t["label"], "pick": (t["samples"] or [None])[0]} for t in types],
                    "cands": cands.get(it["code"]) or []})
    return {"items": out}


class BadPickIn(BaseModel):
    code: str
    key: str
    file: str | None = None
    ok: bool = True


@router.put("/bad-samples")
def put_bad_sample(body: BadPickIn, user: User = Depends(get_current_user)):
    """칸 견본 정하기(후보에서 고르기·지금 것 맞음 확인) / 비우기(file 없음) — 회사 공통."""
    it = _item(body.code)
    if not any(t["key"] == body.key for t in I.bad_types(it)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "그런 부적합 칸이 없습니다.")
    f = I.bad_file()
    bad = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    row = dict(bad.get(body.code) or {})
    if not body.file:
        row.pop(body.key, None)
    else:
        src = next((c for c in _cands().get(body.code) or [] if f"후보/{c['file']}" == body.file), None)
        cur = (row.get(body.key) or [None])[0]
        if src is None and not (cur and cur.get("file") == body.file):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "후보에 없는 그림입니다.")
        base = {"file": body.file, "caption": src["caption"], "from": src["from"]} if src else {k: cur[k] for k in ("file", "caption", "from") if k in cur}
        row[body.key] = [{**base, "ok": bool(body.ok), "by": user.display_name or "", "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}]
    bad[body.code] = row
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps({c: v for c, v in bad.items() if v}, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(f)
    return {"types": [{"key": t["key"], "label": t["label"], "pick": (t["samples"] or [None])[0]} for t in I.bad_types(it)]}


def check(j: BlcmJob) -> list[dict]:
    """빠진 것 [{code, tab, title, text}] — 소항목(대항목 탭 차례) + 관리계획·그 밖의 항목·개선방안 의견(10/30)."""
    res = j.results or {}
    out = []
    for g in I.groups():
        for code in g["items"]:
            it = I.by_code()[code]
            miss = I.missing(it, res.get(code))
            if miss:
                out.append({"code": code, "tab": g["key"], "title": f"{code} {it['name']}", "text": " · ".join(miss)})
    op = j.opinion or {}
    n = len(I.PLAN_ROWS) - len(op.get("plan") or {})
    if n:
        out.append({"code": "", "tab": "_plan", "title": "관리계획 수립·이행", "text": f"{n}줄 안 고름"})
    n = len(I.OTHER_ROWS) - sum(1 for v in (op.get("other") or {}).values() if v and v.get("v"))
    if n:
        out.append({"code": "", "tab": "_other", "title": "그 밖의 항목 이행 여부", "text": f"{n}줄 안 고름"})
    n = sum(1 for k, _, _ in I.OPINION_KEYS if not ((op.get("texts") or {}).get(k) or "").strip())
    if n:
        out.append({"code": "", "tab": "_opinion", "title": "주요 개선방안 의견·종합의견", "text": f"빈 칸 {n}개"})
    return out


@router.get("/jobs/{jid}/check")
def get_check(jid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = _require(db, user, jid)
    return {"missing": check(j), "done": (j.contract or {}).get("field_done")}


class DoneIn(BaseModel):
    done: bool = True


@router.post("/jobs/{jid}/done")
def set_done(jid: int, body: DoneIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """[✓ 점검 완료] — 빠진 것이 남아도 점검자가 완료를 누르면 완료(시특법 조사 완료와 같음), 취소하면 지움."""
    j = _require(db, user, jid)
    c = dict(j.contract or {})
    if body.done:
        c["field_done"] = {"at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "by": user.display_name or "", "left": len(check(j))}
    else:
        c.pop("field_done", None)
    j.contract = c
    _touch(j, user, "contract")
    db.commit()
    return {"missing": check(j), "done": c.get("field_done")}


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
    res[code] = _norm(j, it, A.merge(cur, got), cur)  # AI 판정도 점검현황 규칙대로(10/30)
    j.results = res
    _touch(j, user, "results")
    db.commit()
    return {"result": res[code], "eval": _ev(it, res[code], _use(j)), "progress": progress(j), "ai": got, "recap": I.recap(res)}


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
                    "tech_position": p.position or "", "tech_grade": p.grade or "",  # 명단 원래 값(설정 [건축물관리법] 칸 ✏️, 10/30)
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


# ---------- 생애이력시스템 입력 봇(10/29 4단계 — server/blcm/bot.py, server/worker/blcm_worker.py) ----------
def _setting(db: Session, company_id: int, key: str):
    from core.models_db import AppSetting

    return db.query(AppSetting).filter(AppSetting.company_id == company_id, AppSetting.key == key).first()


def company_cred(db: Session, company_id: int) -> tuple[str, str] | None:
    """회사 생애이력시스템 계정 — app_setting blcm_id·blcm_pw(암호화, FMS·K2B와 같은 열쇠). 메모·파일엔 안 둠."""
    from server.api import k2b_secret

    a, b = _setting(db, company_id, "blcm_id"), _setting(db, company_id, "blcm_pw")
    if not a or not a.value or not b or not b.value:
        return None
    return a.value, k2b_secret.decrypt(b.value)


@router.get("/account")
def get_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = _setting(db, user.company_id, "blcm_id")
    return {"has": company_cred(db, user.company_id) is not None, "user_id": a.value if a else ""}


class CredIn(BaseModel):
    user_id: str
    password: str = ""


@router.put("/account")
def save_account(body: CredIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """회사 생애이력시스템 계정 넣기·바꾸기 — 그룹웨어 관리자만(FMS 계정과 같은 규칙). 비밀번호를 비우면 아이디만 바꿈."""
    from core.models_db import AppSetting
    from server.api import k2b_secret
    from server.api.deps import is_groupware_admin

    if not is_groupware_admin(request):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "생애이력시스템 계정은 그룹웨어 관리자만 바꿀 수 있습니다.")
    uid = body.user_id.strip()
    if not uid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "아이디를 넣어 주세요.")
    if not body.password and not _setting(db, user.company_id, "blcm_pw"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "비밀번호를 넣어 주세요.")
    for key, val in (("blcm_id", uid), ("blcm_pw", k2b_secret.encrypt(body.password) if body.password else None)):
        if val is None:
            continue
        row = _setting(db, user.company_id, key)
        if row is None:
            db.add(AppSetting(company_id=user.company_id, key=key, value=val))
        else:
            row.value = val
    db.commit()
    return {"has": True, "user_id": uid}


RUN_MODES = {"list": "사이트 목록 읽기", "practice": "연습(채워 보기)", "save": "입력·저장"}


def _busy(db: Session, company_id: int) -> BlcmJob | None:
    """회사에 대기·도는 실행이 있으면 그 건(같은 아이디 로그인이 겹치면 서로 끊김). 30분 넘게 running이면 끊긴 것으로 봄."""
    now = datetime.datetime.now()
    for jj in db.query(BlcmJob).filter(BlcmJob.company_id == company_id, BlcmJob.site.isnot(None)).all():
        r = (jj.site or {}).get("run") or {}
        if r.get("status") == "queued":
            return jj
        if r.get("status") == "running":
            try:
                if now - datetime.datetime.strptime(r.get("started") or "", "%Y-%m-%d %H:%M:%S") < datetime.timedelta(minutes=30):
                    return jj
            except ValueError:
                return jj
    return None


class RunIn(BaseModel):
    mode: str
    confirm: bool = False
    only: list[str] | None = None


@router.post("/jobs/{jid}/site/run")
def site_run(jid: int, body: RunIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """봇 실행 맡기기 — list(목록 읽기) · practice(연습, 사이트에 아무것도 안 감) · save(입력·저장, confirm 필요 — 제출은 안 누름)."""
    j = _require(db, user, jid)
    if body.mode not in RUN_MODES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "없는 실행 방법입니다.")
    if company_cred(db, user.company_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "생애이력시스템 계정이 없습니다 — 건축물관리점검 목록 화면에서 계정을 넣으세요(관리자).")
    busy = _busy(db, user.company_id)
    if busy is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"다른 실행이 아직 돌고 있습니다({busy.name}) — 끝난 뒤 다시 누르세요(같은 아이디 로그인이 겹치면 서로 끊김).")
    site = dict(j.site or {})
    if body.mode != "list" and not site.get("target"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "사이트 보고서를 먼저 고르세요([🔎 사이트 목록 읽기] → 고르기).")
    if body.mode == "save" and not body.confirm:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "입력·저장은 확인이 필요합니다.")
    rid = int((site.get("run") or {}).get("id") or 0) + 1
    site["run"] = {"id": rid, "mode": body.mode, "status": "queued", "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   "by": user.display_name or "", "only": [x for x in (body.only or []) if isinstance(x, str)][:60] or None}
    j.site = site
    _touch(j, user, "site")
    db.commit()
    return {"site": _site_out(j)}


class TargetIn(BaseModel):
    oprtn: str


@router.put("/jobs/{jid}/site/target")
def site_target(jid: int, body: TargetIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """사이트 보고서 고르기 — 마지막으로 읽은 목록의 한 줄(점검 번호 oprtn)."""
    j = _require(db, user, jid)
    site = dict(j.site or {})
    row = next((r for r in ((site.get("list") or {}).get("rows") or []) if r.get("oprtn") == body.oprtn), None)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "목록에 없는 보고서입니다 — 목록을 다시 읽으세요.")
    site["target"] = row
    j.site = site
    _touch(j, user, "site")
    db.commit()
    return {"site": _site_out(j)}


def _site_out(j: BlcmJob) -> dict:
    s = j.site or {}
    return {"run": s.get("run"), "list": s.get("list"), "target": s.get("target"), "history": s.get("history") or []}


@router.get("/jobs/{jid}/site")
def get_site(jid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"site": _site_out(_require(db, user, jid))}


@router.get("/jobs/{jid}/site/shot/{name}")
def site_shot(jid: int, name: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from server.worker.blcm_worker import run_dir

    j = _require(db, user, jid)
    rid = int(((j.site or {}).get("run") or {}).get("id") or 0)
    p = run_dir(j.id, rid) / Path(name).name
    if not p.exists() or p.suffix.lower() != ".png":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "화면이 없습니다.")
    return FileResponse(p, media_type="image/png", headers={"Cache-Control": "no-store"})
