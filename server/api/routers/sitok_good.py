"""시특법 현장 조사 [👍 상태양호]·[🏫 내진보강] 탭 API(2026-10-19 민재형 요구사항 B3·B5). 값·보고서 넣기는 server/sitok/good.py, 화면 js/sitok-good.js.

- `GET    /sitok/reports/{id}/good` — {cats: [{key, name, defects, photos: [{idx, title}]}], steel_na, school, seismic: {none, photos: [bool, bool], rows, opinion, at, items}}
- `POST   /sitok/reports/{id}/good/photo` (form key, file) · `PATCH …/good/photo` {key, idx, title} · `DELETE …/good/photo?key=&idx=` · `GET …/good/photo?key=&idx=`
- `POST   /sitok/reports/{id}/good/steel` {na}
- `POST   /sitok/reports/{id}/seismic` {none?, rows?, opinion?} · `POST/DELETE/GET …/seismic/photo` (slot 0·1)
- `POST   /sitok/reports/{id}/seismic/ai` — 사진 2장을 AI가 보고 6항목·종합의견(AI 1번)
"""
from __future__ import annotations

import datetime
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokFacility, SitokReport, User
from server.api.deps import get_current_user, get_db
from server.api.routers.sitok_reports import _report_dir, _require
from server.contract_docs import files
from server.sitok import good as G

router = APIRouter(prefix="/sitok", tags=["sitok"])


def _base(db: Session, r: SitokReport) -> Path:
    return _report_dir(db.get(SitokFacility, r.facility_id), r)


def _save(r: SitokReport, g: dict) -> None:
    r.survey = {**(r.survey or {}), "good": g["good"], "steel_na": g["steel_na"], "seismic": g["seismic"]}


def _out(db: Session, r: SitokReport) -> dict:
    from server.api.routers.sitok_defects import _defects_for_cost
    from server.sitok.ai_draft import category_of

    from server.sitok import kinds

    f = db.get(SitokFacility, r.facility_id)
    fam = kinds.family_of(f)
    g = G.norm(r.survey, fam)
    base = _base(db, r)
    counts: dict = {}
    school = (f.template or "") == "3종학교"
    for d in _defects_for_cost(db, r.id):
        k = wall_category(d.floor) if fam == "wall" else category_of(d.part, d.member, d.dtype)
        counts[k] = counts.get(k, 0) + 1
        if school and G.is_brick({"part": d.part, "member": d.member, "dtype": d.dtype, "note": d.note}):
            counts["brick"] = counts.get("brick", 0) + 1
    se = g["seismic"]
    hints = {"brick": "1.7 외부 치장벽돌 안전점검 특이사항 — 치장벽돌 결함이 없으면 AI 초안이 이 사진을 보고 씁니다"}
    return {"cats": [{"key": k, "name": name, "defects": counts.get(k, 0), "hint": hints.get(k, ""),
                      "photos": [{"idx": i, "title": x["title"], "prev": bool(x.get("prev"))} for i, x in enumerate(g["good"][k]) if (base / x["file"]).exists()]}
                     for k, name in G.cats_for(fam, school)],
            "fam": fam, "per": G.PER, "steel_na": g["steel_na"], "steel_text": G.STEEL_NA_TEXT, "school": (f.template or "") == "3종학교",
            "seismic": {"none": se["none"], "photos": [bool(x and (base / x).exists()) for x in se["photos"]], "rows": se["rows"], "opinion": se["opinion"],
                        "at": se["at"], "items": G.SEISMIC_ITEMS}}


def wall_category(unit: str) -> str:
    """옹벽 결함 부위 → 1.4 절(상태양호 항목): 지반 및 기초부 = found, 전면부 = front, 나머지(상부·배수시설·공중이용·기타) = etc."""
    return {"지반 및 기초부": "found", "전면부": "front"}.get(unit or "", "etc")


def _fam(db: Session, r: SitokReport) -> str:
    from server.sitok import kinds

    return kinds.family_of(db.get(SitokFacility, r.facility_id))


def _check_key(key: str, fam: str = "") -> None:
    if key not in dict(G.cats_for(fam, school=True)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "항목이 맞지 않습니다.")


@router.get("/reports/{report_id}/good")
def get_good(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(db, _require(db, user, report_id))


@router.post("/reports/{report_id}/good/photo")
def add_good(report_id: int, key: str = Form(...), file: UploadFile = File(...), title: str = Form(""), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    fam = _fam(db, r)
    _check_key(key, fam)
    g = G.norm(r.survey, fam)
    if key == "steel" and g["steel_na"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "강재가 해당없음으로 되어 있습니다 — [해당없음 풀기] 뒤에 찍으세요.")
    if sum(1 for x in g["good"][key] if not x.get("prev")) >= G.PER:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"항목마다 {G.PER}장까지입니다 — 지우고 다시 찍으세요.")
    rel = f"{G.DIR_GOOD}/{key}_{uuid.uuid4().hex[:8]}.jpg"
    dest = _base(db, r) / rel
    files.save_jpeg(file.file.read(), file.filename or "photo.jpg", dest)  # 큰 사진 줄여 JPG로(다른 탭과 같게)
    title = title if isinstance(title, str) else ""  # 시험에서 직접 부르면 Form 기본값 객체
    g["good"][key].append({"file": rel, "title": title.strip() or f"{dict(G.cats_for(fam, school=True))[key]} 상태양호"})
    _save(r, g)
    db.commit()
    return _out(db, r)


class TitleIn(BaseModel):
    key: str
    idx: int
    title: str
    file: str | None = None  # (안 씀)


@router.patch("/reports/{report_id}/good/photo")
def title_good(report_id: int, body: TitleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    fam = _fam(db, r)
    _check_key(body.key, fam)
    g = G.norm(r.survey, fam)
    if not 0 <= body.idx < len(g["good"][body.key]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    g["good"][body.key][body.idx]["title"] = body.title.strip()
    _save(r, g)
    db.commit()
    return _out(db, r)


@router.delete("/reports/{report_id}/good/photo")
def del_good(report_id: int, key: str, idx: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    fam = _fam(db, r)
    _check_key(key, fam)
    g = G.norm(r.survey, fam)
    if 0 <= idx < len(g["good"][key]):
        x = g["good"][key].pop(idx)
        (_base(db, r) / x["file"]).unlink(missing_ok=True)
        _save(r, g)
        db.commit()
    return _out(db, r)


@router.get("/reports/{report_id}/good/photo")
def good_photo(report_id: int, key: str, idx: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    g = G.norm(r.survey, _fam(db, r))
    lst = g["good"].get(key) or []
    p = _base(db, r) / lst[idx]["file"] if 0 <= idx < len(lst) else None
    if p is None or not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return FileResponse(p, media_type="image/jpeg")


class SteelIn(BaseModel):
    na: bool


@router.post("/reports/{report_id}/good/steel")
def steel_na(report_id: int, body: SteelIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    g = G.norm(r.survey)
    g["steel_na"] = body.na
    _save(r, g)
    db.commit()
    return _out(db, r)


class SeismicIn(BaseModel):
    none: bool | None = None
    rows: list[dict] | None = None
    opinion: str | None = None


@router.post("/reports/{report_id}/seismic")
def save_seismic(report_id: int, body: SeismicIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    g = G.norm(r.survey)
    se = g["seismic"]
    if body.none is not None:
        se["none"] = body.none
    if body.rows is not None:
        se["rows"] = body.rows
    if body.opinion is not None:
        se["opinion"] = body.opinion
    g["seismic"] = G.norm({"seismic": se})["seismic"]
    _save(r, g)
    db.commit()
    return _out(db, r)


@router.post("/reports/{report_id}/seismic/photo")
def add_seismic_photo(report_id: int, slot: int = Form(0), file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    if slot not in (0, 1):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "사진 칸은 두 개입니다.")
    g = G.norm(r.survey)
    old = g["seismic"]["photos"][slot]
    if old:
        (_base(db, r) / old).unlink(missing_ok=True)
    rel = f"{G.DIR_SEISMIC}/사진{slot + 1}_{uuid.uuid4().hex[:6]}.jpg"
    dest = _base(db, r) / rel
    files.save_jpeg(file.file.read(), file.filename or "photo.jpg", dest)
    g["seismic"]["photos"][slot] = rel
    g["seismic"]["none"] = False
    _save(r, g)
    db.commit()
    return _out(db, r)


@router.delete("/reports/{report_id}/seismic/photo")
def del_seismic_photo(report_id: int, slot: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    g = G.norm(r.survey)
    if slot in (0, 1) and g["seismic"]["photos"][slot]:
        (_base(db, r) / g["seismic"]["photos"][slot]).unlink(missing_ok=True)
        g["seismic"]["photos"][slot] = ""
        _save(r, g)
        db.commit()
    return _out(db, r)


@router.get("/reports/{report_id}/seismic/photo")
def seismic_photo(report_id: int, slot: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    g = G.norm(r.survey)
    x = g["seismic"]["photos"][slot] if slot in (0, 1) else ""
    p = _base(db, r) / x if x else None
    if p is None or not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return FileResponse(p, media_type="image/jpeg")


SEISMIC_PROMPT = """학교 건물의 정기안전점검 중 "내진보강시설 육안 점검표"를 쓰려 합니다. 붙인 사진 {n}장은 이 건물의 내진보강 부위(철골 가새·증설 벽·보강 기초 등)입니다.
사진에서 보이는 것만으로 아래 6항목을 판단해 JSON 객체 하나로만 답하세요(설명 없이). 보이지 않는 것은 지어내지 말고 "×"·"이상 없음" 또는 "확인 불가".
{{"rows": [{{"mark": "○(해당 문제가 있음) 또는 ×(없음)", "text": "내용(위치, 상태) 20자 안팎", "action": "조치사항 15자 안팎(없으면 빈 글)"}} — 아래 6항목 순서대로],
 "opinion": "종합의견 한두 문장(보고서 문어체)"}}
항목:
{items}"""


@router.post("/reports/{report_id}/seismic/ai")
def seismic_ai(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """사진 2장을 AI가 보고 점검표 6항목·종합의견(AI 1번) — 저장까지(창에서 고칠 수 있음)."""
    from server.sitok import vision

    r = _require(db, user, report_id)
    g = G.norm(r.survey)
    base = _base(db, r)
    imgs = [(base / x).read_bytes() for x in g["seismic"]["photos"] if x and (base / x).exists()]
    if not imgs:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "내진보강 사진을 먼저 찍으세요(해당없음이면 [해당없음]).")
    try:
        got = vision.ask_json(r.company_id, imgs, SEISMIC_PROMPT.format(n=len(imgs), items="\n".join(f"{i}. {t}" for i, t in enumerate(G.SEISMIC_ITEMS, 1))), writing=True)
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI가 점검표를 쓰지 못했습니다: {str(err).splitlines()[0][:150]}") from err
    rows = [{"mark": "○" if str(x.get("mark") or "").startswith("○") else "×", "text": str(x.get("text") or "").strip(), "action": str(x.get("action") or "").strip()}
            for x in (got.get("rows") or []) if isinstance(x, dict)][:len(G.SEISMIC_ITEMS)] if isinstance(got, dict) else []
    g["seismic"].update({"rows": rows, "opinion": str((got or {}).get("opinion") or "").strip() if isinstance(got, dict) else "", "none": False,
                         "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
    _save(r, g)
    db.commit()
    return _out(db, r)
