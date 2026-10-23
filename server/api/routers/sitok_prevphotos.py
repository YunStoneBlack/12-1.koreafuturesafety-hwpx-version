"""시특법 현장 조사 — 전회차 사진 보여 주기·이번 회차에 그대로 넣기(2026-10-23 사용자 "다음 회차 시 전회차 보여 주기 — 상태양호·내진보강·공중이용·기타시설 등
전회차 사진 금회차에 그대로 넣기 기능"). 화면 js/sitok-prevphotos.js(네 탭 위 "📷 전회차 사진 N장 [보기] [빈 칸에 그대로 넣기]").

- `GET  /sitok/reports/{id}/prev-photos` — 직전 회차(같은 시설물, 앞선 반기 중 이 네 탭에 사진이 있는 가장 최근 것 — 보고서를 안 만들었어도)와 탭마다 사진·이번에 채울 수 있는 칸.
  사진은 직전 회차의 원래 주소(…/good/photo·/seismic/photo·/parts/photo)로 봄.
- `POST /sitok/reports/{id}/prev-photos/copy` {tab: good|seismic|public|other} — 이번 회차에서 **비어 있는 칸에만** 직전 회차 사진을 복사(이미 찍은 칸은 그대로).
  상태양호 = 이번 사진이 없는 항목에 직전 회차 사진(최대 PER장)·강재 해당없음, 내진보강 = 빈 사진 칸·해당없음, 공중이용 = 사진도 해당없음도 없는 항목에 사진(또는 해당없음),
  기타시설 = 빈 항목에 사진들. 복사한 사진은 이번 회차 사진이 됨(파일도 이번 회차 폴더로 — 직전 회차 파일은 그대로).
"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.models_web import SitokFacility, SitokReport, User
from server.api.deps import get_current_user, get_db
from server.api.routers.sitok_reports import _order, _report_dir, _require
from server.sitok import good as G
from server.sitok import kinds, seasons
from server.sitok import parts as P

router = APIRouter(prefix="/sitok", tags=["sitok"])
TABS = ("good", "seismic", "public", "other")


def _ok(base: Path, rel: str | None) -> bool:
    return bool(rel) and (base / rel).exists()


def _view(db: Session, r: SitokReport, fam: str) -> dict:
    """그 회차의 네 탭 사진(있는 것만) — {good: {key: [(idx, title, file)]}, steel_na, seismic: {photos: [file|None]*2, none}, public: {key: (file, which) | "none"}, other: {key: [file]}}."""
    base = _report_dir(db.get(SitokFacility, r.facility_id), r)
    g = G.norm(r.survey, fam)
    p = P.norm(r.parts)
    good = {}
    for k, _ in G.cats_for(fam):
        own = [(i, x["title"], x["file"]) for i, x in enumerate(g["good"][k]) if not x["prev"] and _ok(base, x["file"])]
        good[k] = own or [(i, x["title"], x["file"]) for i, x in enumerate(g["good"][k]) if _ok(base, x["file"])]
    se = g["seismic"]
    pub = {}
    for k, _ in P.PUBLIC:
        it = p["public"].get(k) or {}
        if _ok(base, it.get("file")):
            pub[k] = (it["file"], "now")
        elif _ok(base, it.get("prev")):
            pub[k] = (it["prev"], "prev")
        elif it.get("none"):
            pub[k] = "none"
    return {"base": base, "good": good, "steel_na": g["steel_na"],
            "seismic": {"photos": [x if _ok(base, x) else None for x in se["photos"]], "none": se["none"]},
            "public": pub, "other": {k: [x for x in p["other"][k] if _ok(base, x)] for k, _ in P.OTHER}}


def _has_any(v: dict) -> bool:
    return any(v["good"].values()) or any(v["seismic"]["photos"]) or any(x != "none" for x in v["public"].values()) or any(v["other"].values())


def prev_round(db: Session, r: SitokReport, fam: str) -> SitokReport | None:
    """같은 시설물의 앞선 회차 중 이 네 탭에 사진이 있는 가장 최근 것(보고서를 안 만들었어도 — 현장에서 찍어 둔 것)."""
    rows = [x for x in db.query(SitokReport).filter(SitokReport.facility_id == r.facility_id, SitokReport.id != r.id)
            if seasons.is_seismic(x.half) == seasons.is_seismic(r.half) and _order(x) < _order(r)]
    for x in sorted(rows, key=_order, reverse=True):
        if _has_any(_view(db, x, fam)):
            return x
    return None


def _fam(db: Session, r: SitokReport) -> str:
    return kinds.family_of(db.get(SitokFacility, r.facility_id))


@router.get("/reports/{report_id}/prev-photos")
def get_prev_photos(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    fam = _fam(db, r)
    pr = prev_round(db, r, fam)
    if pr is None:
        return {"prev": None}
    pv, cur = _view(db, pr, fam), _view(db, r, fam)
    cur_own = {k: [x for x in G.norm(r.survey, fam)["good"][k] if not x["prev"] and _ok(cur["base"], x["file"])] for k, _ in G.cats_for(fam)}
    good = [{"key": k, "name": name, "photos": [{"idx": i, "title": t} for i, t, _ in pv["good"][k]], "fill": bool(pv["good"][k]) and not cur_own[k]}
            for k, name in G.cats_for(fam) if pv["good"][k]]
    se = {"photos": [bool(x) for x in pv["seismic"]["photos"]], "none": pv["seismic"]["none"],
          "fill": sum(1 for a, b in zip(pv["seismic"]["photos"], cur["seismic"]["photos"]) if a and not b and not cur["seismic"]["none"])
          + (1 if pv["seismic"]["none"] and not cur["seismic"]["none"] and not any(cur["seismic"]["photos"]) else 0)}
    pub = []
    for k, name in P.PUBLIC:
        x = pv["public"].get(k)
        if x is None:
            continue
        pub.append({"key": k, "name": name, "none": x == "none", "which": "" if x == "none" else x[1], "fill": k not in cur["public"]})
    oth = [{"key": k, "name": name, "slots": len(pv["other"][k]), "fill": bool(pv["other"][k]) and not cur["other"][k]} for k, name in P.OTHER if pv["other"][k]]
    return {"prev": {"id": pr.id, "label": f"{pr.year} {pr.half}"}, "good": good, "steel_na": pv["steel_na"], "seismic": se if any(se["photos"]) or se["none"] else None,
            "public": pub, "other": oth}


def _copy(src_base: Path, rel: str, dst_base: Path) -> str:
    p = Path(rel)
    new = str(p.parent / f"{p.stem.split('_전회차')[0]}_{uuid.uuid4().hex[:6]}{p.suffix or '.jpg'}").replace("\\", "/")
    (dst_base / new).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_base / rel, dst_base / new)
    return new


@router.post("/reports/{report_id}/prev-photos/copy")
def copy_prev_photos(report_id: int, tab: str = Body(..., embed=True), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if tab not in TABS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "탭이 맞지 않습니다.")
    r = _require(db, user, report_id)
    fam = _fam(db, r)
    pr = prev_round(db, r, fam)
    if pr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "전회차 사진이 없습니다.")
    pv, cur = _view(db, pr, fam), _view(db, r, fam)
    sb, db_ = pv["base"], cur["base"]
    n = 0
    if tab in ("good", "seismic"):
        g = G.norm(r.survey, fam)
        if tab == "good":
            for k, _ in G.cats_for(fam):
                if not pv["good"][k] or any(not x["prev"] and _ok(db_, x["file"]) for x in g["good"][k]):
                    continue  # 전회차에 없거나 이번에 이미 찍음
                new = [{"file": _copy(sb, rel, db_), "title": title, "prev": False} for _, title, rel in pv["good"][k][:G.PER]]
                g["good"][k] = new + g["good"][k]  # 이번 사진(전회차 그대로) 앞, 옹벽 가져오기 전회차 사진은 뒤
                n += len(new)
            if pv["steel_na"] and not g["steel_na"] and not any(not x["prev"] for x in g["good"].get("steel", [])):
                g["steel_na"] = True
                n += 1
        else:
            se = g["seismic"]
            if pv["seismic"]["none"] and not se["none"] and not any(cur["seismic"]["photos"]):
                se["none"] = True
                n += 1
            elif not se["none"]:
                for i, rel in enumerate(pv["seismic"]["photos"]):
                    if rel and not cur["seismic"]["photos"][i]:
                        se["photos"][i] = _copy(sb, rel, db_)
                        n += 1
        r.survey = {**(r.survey or {}), "good": g["good"], "steel_na": g["steel_na"], "seismic": g["seismic"]}
    else:
        p = P.norm(r.parts)
        if tab == "public":
            for k, x in pv["public"].items():
                if k in cur["public"]:
                    continue  # 이번에 사진·해당없음이 이미 있음
                it = dict(p["public"].get(k) or {})
                if x == "none":
                    it["none"] = True
                else:
                    it["file"] = _copy(sb, x[0], db_)
                p["public"][k] = it
                n += 1
        else:
            for k, lst in pv["other"].items():
                if lst and not cur["other"][k]:
                    p["other"][k] = [_copy(sb, rel, db_) for rel in lst][:P.OTHER_SLOTS]
                    n += len(p["other"][k])
        r.parts = p
    db.commit()
    return {"copied": n, "from": f"{pr.year} {pr.half}"}
