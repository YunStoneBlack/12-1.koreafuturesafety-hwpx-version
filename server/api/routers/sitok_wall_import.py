"""옹벽 전회차 가져오기(2026-10-20 사용자 제안) — 지난 보고서(PDF 또는 한글 hwp·hwpx) 부록2 사진첩의 "주요 손상 및 현황 사진"·전경사진을 읽어
AI가 부위·구분·부재·결함유형을 추천 → 확인 창에서 점검자가 고친 뒤 넣음. 읽기는 server/sitok/wall_album.py.

- `POST   /sitok/reports/{id}/defects/import/wall` — 파일 올리기(한글은 작업 프로그램이 PDF로 1~3분, 그다음 AI 1번) → 뒤에서 돌고 IMPORTS 상태 running → review.
  확인 대기 상태는 sitok_report.survey["wall_import"]에(API가 다시 떠도 남음), 사진은 회차 폴더 "전회차_가져오기/".
- `GET    /sitok/reports/{id}/defects/import/wall` — 확인 창 자료(시설물 장 목록·고른 장·전경·사진 줄 + 목록).
- `GET    /sitok/reports/{id}/defects/import/wall/photo?f=` — 잘라 낸 사진.
- `POST   /sitok/reports/{id}/defects/import/wall/pick {idx}` — 17곳 한 권이면 다른 장으로(다시 읽고 AI 다시).
- `POST   /sitok/reports/{id}/defects/import/wall/confirm {rows, overview}` — 결함(전회차 값·사진) / 상태양호 / 빼기, 전경 6장은 전경사진 탭에.
- `DELETE /sitok/reports/{id}/defects/import/wall` — 확인 취소(가져온 것 지움).
"""
from __future__ import annotations

import datetime
import shutil
import threading
import traceback
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokDefect, SitokFacility, SitokReport, User
from server.api.deps import get_current_user, get_db
from server.api.routers.sitok_defects import IMPORTS, _photo_dir, _require_empty, list_defects
from server.api.routers.sitok_good import wall_category
from server.api.routers.sitok_overview import DIR as OV_DIR
from server.api.routers.sitok_reports import _report_dir, _require
from server.api.routers.sitok_settings import vocab_names
from server.contract_docs import hwp_queue
from server.sitok import good as G
from server.sitok import kinds, wall_album
from server.sitok import parts as P
from server.api.routers.sitok_parts import DIR as PARTS_DIR

router = APIRouter(prefix="/sitok", tags=["sitok"])
DIR = "전회차_가져오기"
EXTS = (".pdf", ".hwp", ".hwpx")
HWP_WAIT = 900  # 한글 → PDF(부록 100쪽 넘을 수 있음)


def _dir(db: Session, r: SitokReport) -> Path:
    return _report_dir(db.get(SitokFacility, r.facility_id), r) / DIR


def state_of(r: SitokReport) -> dict | None:
    s = (r.survey or {}).get("wall_import")
    return s if isinstance(s, dict) and isinstance(s.get("rows"), list) else None


def review_state(r: SitokReport) -> dict | None:
    """현장 조사 화면 importing 칸용 — 확인 대기면 {state: review}."""
    s = state_of(r)
    return {"state": "review", "msg": f"지난 보고서 사진 {len(s['rows'])}장을 읽었습니다 — 부위·결함유형을 확인하고 넣으세요"} if s else None


def _require_wall(db: Session, user: User, report_id: int) -> tuple[SitokReport, SitokFacility]:
    r = _require(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    if not kinds.is_wall(f):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "옹벽 시설물에서만 쓰는 가져오기입니다.")
    return r, f


@router.post("/reports/{report_id}/defects/import/wall")
def start(report_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r, f = _require_wall(db, user, report_id)
    _require_empty(db, r)
    if IMPORTS.get(r.id, {}).get("state") == "running":
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 읽는 중입니다.")
    data = file.file.read()
    ext = Path(file.filename or "").suffix.lower()
    if data.startswith(b"%PDF"):
        ext = ".pdf"
    if ext not in EXTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "지난 보고서 PDF 또는 한글 파일(hwp·hwpx)을 올려 주세요.")
    folder = _dir(db, r)
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"원본{ext}").write_bytes(data)
    IMPORTS[r.id] = {"state": "running", "msg": "한글 파일을 PDF로 바꾸는 중(1~3분) — 그다음 사진첩을 읽습니다" if ext != ".pdf" else "부록 사진첩을 읽는 중(AI 분류 10~30초)"}
    threading.Thread(target=_run, args=(r.id, user.company_id, f.name, data, ext, folder), daemon=True).start()
    return {**list_defects(report_id, user, db), "importing": IMPORTS[r.id]}


def _run(report_id: int, company_id: int, fac_name: str, data: bytes, ext: str, folder: Path) -> None:
    from core.db import SessionLocal

    db = SessionLocal()
    try:
        pdf = data if ext == ".pdf" else hwp_queue.convert_via_worker(data, ext, to="pdf", wait=HWP_WAIT)
        (folder / "원본.pdf").write_bytes(pdf)
        try:  # 같은 PDF를 회차 "전회차 보고서 PDF" 칸에도(1.3.1·1.4.5 전회 칸·도면이 읽음) + 1.2.4 뒤 도면 쪽 → 시설물 첨부 도면(아직 없을 때만, 형 10/21)
            from server.api.routers.sitok import _facility_dir
            from server.sitok import prev_pdf, wall_drawings

            r0 = db.get(SitokReport, report_id)
            f0 = db.get(SitokFacility, r0.facility_id)
            pv = prev_pdf.path(_report_dir(f0, r0))
            if not pv.exists():
                pv.parent.mkdir(parents=True, exist_ok=True)
                pv.write_bytes(pdf)
                r0.survey = {**(r0.survey or {}), "prev_name": "전회차 가져오기 원본.pdf"}
                db.commit()
            if wall_drawings.seed(f0, _facility_dir(f0), folder / "원본.pdf"):
                db.commit()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        IMPORTS[report_id] = {"state": "running", "msg": "부록 사진첩을 읽는 중(AI 분류 10~30초)"}
        album = wall_album.read_pdf(pdf)
        if not album.facilities:
            raise ValueError("설명 글이 붙은 사진을 찾지 못했습니다 — 지난 보고서 부록2 사진첩(전경·주요 손상 및 현황 사진)이 든 파일인지 확인하세요")
        r = db.get(SitokReport, report_id)
        if db.query(SitokDefect).filter(SitokDefect.report_id == report_id).first():
            raise ValueError("그 사이 결함이 들어와 있어 넣지 않았습니다")
        _store(db, r, album, wall_album.pick(album, fac_name), company_id, folder)
        IMPORTS[report_id] = review_state(r)
    except Exception as err:  # noqa: BLE001 — 이유를 화면에
        traceback.print_exc()
        IMPORTS[report_id] = {"state": "failed", "msg": f"지난 보고서를 읽지 못했습니다: {str(err).splitlines()[0][:150]}"}
    finally:
        db.close()


def _store(db: Session, r: SitokReport, album: wall_album.WallAlbum, idx: int, company_id: int, folder: Path) -> None:
    """고른 장의 사진을 폴더에 쓰고 AI 분류(낱말 규칙 보완)를 survey["wall_import"]에."""
    fac = album.facilities[idx]
    for p in folder.glob("*.jpg"):
        p.unlink(missing_ok=True)
    allowed = vocab_names(db, company_id, r.id, "wall")
    guesses = wall_album.guess_rows([s.caption for s in fac.shots], company_id, allowed)
    overview, rows = [], []
    for i, s in enumerate(fac.overview, 1):
        (folder / f"ov_{i:02d}.jpg").write_bytes(s.jpg)
        overview.append({"file": f"ov_{i:02d}.jpg", "caption": s.caption})
    for i, (s, g) in enumerate(zip(fac.shots, guesses), 1):
        (folder / f"sh_{i:02d}.jpg").write_bytes(s.jpg)
        rows.append({"file": f"sh_{i:02d}.jpg", "caption": s.caption, "page": s.page + 1, **g})
    r.survey = {**(r.survey or {}), "wall_import": {"facilities": [x.name for x in album.facilities], "picked": idx, "overview": overview, "rows": rows,
                                                   "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}}
    db.commit()


def _out(db: Session, r: SitokReport) -> dict:
    s = state_of(r)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "확인할 가져오기가 없습니다.")
    allowed = vocab_names(db, r.company_id, r.id, "wall")
    return {**s, "units": list(kinds.WALL_PARTS), "parts": list(kinds.WALL_SECTIONS), "members": allowed["member"], "types": allowed["dtype"],
            "unit_part": kinds.WALL_PART_OF_UNIT, "part_of": kinds.part_map("wall"), "good_keys": {u: wall_category(u) for u in kinds.WALL_PARTS},
            "good_names": dict(G.WALL_CATS), "public_items": list(P.PUBLIC)}


@router.get("/reports/{report_id}/defects/import/wall")
def get_review(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r, _ = _require_wall(db, user, report_id)
    return _out(db, r)


@router.get("/reports/{report_id}/defects/import/wall/photo")
def photo(report_id: int, f: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r, _ = _require_wall(db, user, report_id)
    p = _dir(db, r) / Path(f).name
    if not p.exists() or p.suffix != ".jpg":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return FileResponse(p, media_type="image/jpeg")


class PickIn(BaseModel):
    idx: int


@router.post("/reports/{report_id}/defects/import/wall/pick")
def pick(report_id: int, body: PickIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """한 권에 여러 시설물 — 다른 장으로(저장해 둔 PDF를 다시 읽고 AI 분류 다시)."""
    r, _ = _require_wall(db, user, report_id)
    s = state_of(r)
    pdf = _dir(db, r) / "원본.pdf"
    if not s or not pdf.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "확인할 가져오기가 없습니다.")
    album = wall_album.read_pdf(pdf.read_bytes())
    if not 0 <= body.idx < len(album.facilities):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "그 장이 없습니다.")
    _store(db, r, album, body.idx, user.company_id, _dir(db, r))
    return _out(db, r)


class ConfirmIn(BaseModel):
    rows: list[dict]  # [{i, use: defect|good|skip, unit, part, member, dtype, width}]
    overview: bool = True  # 전경사진도 전경사진 탭에


@router.post("/reports/{report_id}/defects/import/wall/confirm")
def confirm(report_id: int, body: ConfirmIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r, f = _require_wall(db, user, report_id)
    s = state_of(r)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "확인할 가져오기가 없습니다.")
    _require_empty(db, r)
    allowed = vocab_names(db, r.company_id, r.id, "wall")
    src = _dir(db, r)
    photo_dir = _photo_dir(db, r)
    photo_dir.mkdir(parents=True, exist_ok=True)
    g = G.norm(r.survey, "wall")
    pp = P.norm(r.parts)
    seq: dict[str, int] = {}
    n_def = n_good = n_skip = n_pub = 0
    for row in body.rows:
        try:
            base = s["rows"][int(row.get("i", -1))]
        except (ValueError, IndexError):
            continue
        use = row.get("use") or "skip"
        unit = str(row.get("unit") or base.get("unit") or "")
        if use == "skip" or not (src / base["file"]).exists():
            n_skip += 1
            continue
        if unit not in kinds.WALL_PARTS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"부위가 맞지 않습니다: {base['caption']}")
        if use == "public":  # 공중이용 탭 전회차 칸(추락방지시설 등 — 민재형 10/21)
            pk = row.get("public") if row.get("public") in dict(P.PUBLIC) else (base.get("public") or "fall")
            rel = f"{PARTS_DIR}/public_{pk}_prev_{uuid.uuid4().hex[:8]}.jpg"
            dest = _report_dir(f, r) / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / base["file"], dest)
            pp["public"][pk] = {**(pp["public"].get(pk) or {}), "prev": rel}
            n_pub += 1
            continue
        if use == "good":
            key = wall_category(unit)
            if sum(1 for x in g["good"][key] if x.get("prev")) >= G.PER:
                n_skip += 1
                continue
            rel = f"{G.DIR_GOOD}/{key}_{uuid.uuid4().hex[:8]}.jpg"
            dest = _report_dir(f, r) / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / base["file"], dest)
            g["good"][key].append({"file": rel, "title": base["caption"], "prev": True})  # 전회차 — 이번 사진은 탭에서 찍음(민재형 10/21)
            n_good += 1
            continue
        part, member, dtype, width = (str(row.get(k) if row.get(k) is not None else base.get(k) or "").strip() for k in ("part", "member", "dtype", "width"))
        if part not in kinds.WALL_SECTIONS:
            part = kinds.default_part(member, "wall") or kinds.WALL_PART_OF_UNIT[unit]
        if not dtype or (dtype not in allowed["dtype"] and not kinds.is_record(dtype)) or (member and member not in allowed["member"]):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"목록에 없는 이름입니다: {base['caption']} → {member} {dtype}")
        seq[unit] = seq.get(unit, 0) + 1
        prev = {"번호": str(seq[unit]), "구분": part, "부재": member, "결함유형": dtype, "개수": "", "폭": width, "길이": "", "물량": "", "면적률": "",
                "결함원인": "", "진행유무": "", "비고": "기존", "설명": base["caption"]}
        d = SitokDefect(report_id=r.id, floor=unit, seq=seq[unit], part=part, member=member, dtype=dtype, width=width, mark="기존", prev=prev,
                        depth=kinds.split_depth(str(base.get("caption") or ""))[1],  # 사진 설명 "파손(D=0.9mm)" → 깊이(10/22)
                        note=base["caption"])
        p = photo_dir / f"{unit}_{seq[unit]:02d}_전회차.jpg"
        shutil.copy2(src / base["file"], p)
        d.prev_photo = str(p)
        db.add(d)
        n_def += 1
    n_ov = 0
    if body.overview:
        ov_dir = _report_dir(f, r) / OV_DIR
        ov_dir.mkdir(parents=True, exist_ok=True)
        rows = [dict(p) for p in (r.overview or [])]
        for o in s.get("overview") or []:
            if not (src / o["file"]).exists():
                continue
            pid = uuid.uuid4().hex[:10]
            shutil.copy2(src / o["file"], ov_dir / f"{pid}_prev.jpg")
            rows.append({"id": pid, "file": "", "prev_file": f"{OV_DIR}/{pid}_prev.jpg", "title": o["caption"], "ai": False})  # 전회차 칸 — 이번은 탭에서 찍음
            n_ov += 1
        r.overview = rows
    sv = {**(r.survey or {}), "good": g["good"], "steel_na": g["steel_na"], "seismic": g["seismic"]}
    sv.pop("wall_import", None)
    r.survey = sv
    if n_pub:
        r.parts = pp
    IMPORTS.pop(r.id, None)
    db.commit()
    shutil.rmtree(src, ignore_errors=True)
    return {**list_defects(report_id, user, db), "imported": {"defects": n_def, "good": n_good, "public": n_pub, "skipped": n_skip, "overview": n_ov}}


@router.delete("/reports/{report_id}/defects/import/wall")
def cancel(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r, _ = _require_wall(db, user, report_id)
    sv = dict(r.survey or {})
    sv.pop("wall_import", None)
    r.survey = sv
    IMPORTS.pop(r.id, None)
    db.commit()
    shutil.rmtree(_dir(db, r), ignore_errors=True)
    return {"ok": True}
