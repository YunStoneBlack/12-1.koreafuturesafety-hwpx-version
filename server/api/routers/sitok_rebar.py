"""구조 일람표 부재 목록(2026-10-21 — 내진성능평가 철근탐사 1단계) — 시설물 도면 "구조 일람표"를 AI가 읽어 부재 칸 목록으로 저장하고,
기둥 변별 점 개수·두 줄 하부근은 단면 그림을 보며 사람이 한 번 확인(server/sitok/rebar_schedule.py).

- `GET    /sitok/facilities/{id}/rebar-schedule` — 목록(검산·확인 필요 수) + 읽는 중 상태(job) + 일람표 도면 수
- `POST   /sitok/facilities/{id}/rebar-schedule/read` — 쪽마다 AI 읽기 시작(뒤에서 — 쪽당 30초~4분, 3쪽씩 동시), 사람이 확인·고친 줄은 다시 읽어도 남음
- `PATCH  /sitok/facilities/{id}/rebar-schedule/items/{item}` — 칸 고치기·[✓ 확인]
- `POST   /sitok/facilities/{id}/rebar-schedule/items` — 칸 직접 추가(도면에 없거나 못 읽은 것)
- `DELETE /sitok/facilities/{id}/rebar-schedule/items/{item}`
- `GET    /sitok/facilities/{id}/rebar-schedule/crop/{item}` — 그 칸 단면 그림(PNG)
읽기 작업은 JOBS(시설물 → 상태) — /sitok/busy "schedules"에 들어가 안전 재시작이 기다림.
"""
from __future__ import annotations

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.db import SessionLocal
from core.models_web import SitokFacility, User
from server.api.deps import get_current_user, get_db
from server.api.routers.sitok import _facility_dir, _require_facility
from server.sitok import drawings as D
from server.sitok import rebar_schedule as RS

router = APIRouter(prefix="/sitok", tags=["sitok-rebar"])
JOBS: dict[int, dict] = {}  # 시설물 id → {state: running/done/failed, msg, done, total}
KEY = "rebar_schedule"


def _data(f: SitokFacility) -> dict:
    return dict((f.ledger or {}).get(KEY) or {})


def _put(f: SitokFacility, data: dict) -> None:
    f.ledger = {**(f.ledger or {}), KEY: data}  # 새 dict로(같은 dict를 고치면 SQLAlchemy가 바뀐 줄 모름)


def _files(f: SitokFacility) -> list[dict]:
    return D.items(f, "schedule", _facility_dir(f))


def _out(f: SitokFacility) -> dict:
    v = RS.view(_data(f))
    job = JOBS.get(f.id)
    if job and job.get("state") == "running":
        v["status"], v["message"] = "running", job.get("msg") or "읽는 중…"
    return v | {"facility": {"id": f.id, "name": f.name, "mgmt_no": f.mgmt_no, "floors_above": f.floors_above, "floors_below": f.floors_below},
                "files": [{"id": x["id"], "name": x.get("name")} for x in _files(f)], "job": job or {"state": "idle"}}


@router.get("/facilities/{facility_id}/rebar-schedule")
def get_schedule(facility_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(_require_facility(db, user, facility_id))


@router.post("/facilities/{facility_id}/rebar-schedule/read")
def read_schedule(facility_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = _require_facility(db, user, facility_id)
    files = _files(f)
    if not files:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "구조 일람표 도면이 없습니다 — 🏢 시설물 현황 창의 도면 칸 \"📏 구조 일람표\"에 올리세요.")
    if (JOBS.get(f.id) or {}).get("state") == "running":
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 읽는 중입니다.")
    pages = RS.schedule_pages(files)
    JOBS[f.id] = {"state": "running", "msg": f"일람표 {len(pages)}쪽 읽는 중 — 0/{len(pages)}쪽", "done": 0, "total": len(pages)}
    threading.Thread(target=_job, args=(f.id, user.company_id, user.display_name or ""), daemon=True).start()
    return _out(f)


def _job(facility_id: int, company_id: int, by: str) -> None:
    db = SessionLocal()
    try:
        f = db.get(SitokFacility, facility_id)
        files = {x["id"]: x for x in _files(f)}
        pages = RS.schedule_pages(list(files.values()))
        usage = {"in": 0, "out": 0}
        results: dict[int, list] = {}
        failed: list[str] = []

        def one(i: int):
            pg = pages[i]
            try:
                raw, use = RS.read_page(company_id, Path(files[pg["src"]]["path"]), pg["page"])
                results[i] = raw
                usage["in"] += use["in"]
                usage["out"] += use["out"]
            except Exception as err:  # noqa: BLE001 — 그 쪽만 빼고 계속
                traceback.print_exc()
                failed.append(f"{pg['name']} {pg['page'] + 1}쪽: {str(err).splitlines()[0][:80]}")
            job = JOBS[facility_id]
            job["done"] = job.get("done", 0) + 1
            job["msg"] = f"일람표 {len(pages)}쪽 읽는 중 — {job['done']}/{len(pages)}쪽"

        with ThreadPoolExecutor(3) as ex:
            list(ex.map(one, range(len(pages))))
        new = [it for i in sorted(results) for raw in results[i] if (it := RS.normalize_item(raw, i))]
        RS.inherit_same(new)
        old = _data(f)
        items = RS.merge_confirmed([RS.normalize_item(x) for x in old.get("items") or [] if RS.normalize_item(x)], new)
        won = round((usage["in"] / 1e6 * 2 + usage["out"] / 1e6 * 10) * 1400)  # claude-sonnet-5 $2·$10/백만 토큰, 1달러 1,400원 어림
        v = RS.view({"items": items})
        msg = f"{len(pages)}쪽에서 {len(items)}칸 읽음 — 확인 필요 {v['need']}칸 (AI 약 {won:,}원)"
        if failed:
            msg += " · 못 읽은 쪽: " + "; ".join(failed[:3])
        _put(f, {"items": items, "pages": pages, "read_at": RS.stamp(), "by": by, "status": "done", "message": msg,
                 "cost": {"in": usage["in"], "out": usage["out"], "won": won}})
        db.commit()
        JOBS[facility_id] = {"state": "done", "msg": msg}
    except Exception as err:  # noqa: BLE001 — 이유를 화면에
        traceback.print_exc()
        JOBS[facility_id] = {"state": "failed", "msg": f"일람표를 읽지 못했습니다: {str(err).splitlines()[0][:200]}"}
    finally:
        db.close()


class ItemIn(BaseModel):
    kind: str | None = None
    marks: list[str] | None = None
    floors: str | None = None
    position: str | None = None
    size: str | None = None
    main: str | None = None
    short_side: int | None = None
    long_side: int | None = None
    hoop: str | None = None
    hoop_end: str | None = None
    hoop_aux: str | None = None
    top: str | None = None
    bottom: str | None = None
    bottom_row: int | None = None
    bottom_layers: int | None = None
    stirrup: str | None = None
    thickness: int | None = None
    vertical: str | None = None
    horizontal: str | None = None
    confirmed: bool | None = None


def _find(data: dict, item_id: str) -> int:
    for i, x in enumerate(data.get("items") or []):
        if x.get("id") == item_id:
            return i
    raise HTTPException(status.HTTP_404_NOT_FOUND, "그 칸이 없습니다 — 화면을 새로 고치세요.")


@router.patch("/facilities/{facility_id}/rebar-schedule/items/{item_id}")
def patch_item(facility_id: int, item_id: str, body: ItemIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = _require_facility(db, user, facility_id)
    data = _data(f)
    i = _find(data, item_id)
    items = [dict(x) for x in data.get("items") or []]
    cur = items[i]
    vals = body.model_dump(exclude_unset=True)
    for k, v in vals.items():
        if k != "confirmed":
            cur[k] = v
    if vals.keys() - {"confirmed"}:  # 값을 고치면 그 값은 확실 — 불확실 표시를 지움
        cur["unsure"] = [u for u in cur.get("unsure") or [] if u not in vals]
    if "confirmed" in vals:
        cur["confirmed"] = bool(vals["confirmed"])
    cur["by"] = user.display_name or "확인"
    it = RS.normalize_item(cur)
    if it is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "부재 종류는 기둥·보·벽체입니다.")
    items[i] = it
    _put(f, {**data, "items": items})
    db.commit()
    return _out(f)


@router.post("/facilities/{facility_id}/rebar-schedule/items")
def add_item(facility_id: int, body: ItemIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = _require_facility(db, user, facility_id)
    raw = body.model_dump(exclude_none=True)
    raw.setdefault("confirmed", True)
    raw["by"] = user.display_name or "직접"
    it = RS.normalize_item(raw)
    if it is None or not it["marks"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "부재 종류(기둥·보·벽체)와 부호를 넣으세요.")
    data = _data(f)
    _put(f, {**data, "items": [*(data.get("items") or []), it]})
    db.commit()
    return _out(f)


@router.delete("/facilities/{facility_id}/rebar-schedule/items/{item_id}")
def delete_item(facility_id: int, item_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = _require_facility(db, user, facility_id)
    data = _data(f)
    i = _find(data, item_id)
    items = [x for k, x in enumerate(data.get("items") or []) if k != i]
    _put(f, {**data, "items": items})
    db.commit()
    return _out(f)


@router.get("/facilities/{facility_id}/rebar-schedule/crop/{item_id}")
def crop(facility_id: int, item_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = _require_facility(db, user, facility_id)
    data = _data(f)
    it = (data.get("items") or [])[_find(data, item_id)]
    pages = data.get("pages") or []
    if not it.get("box") or it.get("pg") is None or not (0 <= int(it["pg"]) < len(pages)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "단면 그림 위치가 없습니다.")
    pg = pages[int(it["pg"])]
    src = next((x for x in _files(f) if x["id"] == pg["src"]), None)
    if src is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "일람표 도면 파일이 없습니다(지웠거나 바꿈) — 다시 읽으세요.")
    png = RS.crop_png(Path(src["path"]), int(pg["page"]), it["box"])
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=600"})
