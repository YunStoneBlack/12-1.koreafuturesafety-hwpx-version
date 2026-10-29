"""건축물관리점검 생애이력시스템 입력 작업 프로그램(2026-10-29) — BlcmJob.site.run(queued)을 하나씩 꺼내 이 PC에서 blcm.go.kr에 입력(server/blcm/bot.py).

FMS 작업처럼 supervisor_entry의 별도 스레드. 한 번에 하나 — 같은 아이디로 새로 로그인하면 이전 접속(형 화면 포함)이 끊길 수 있어 동시에 안 돌림.
대기열은 표를 늘리지 않고 건의 site JSON: {"run": {id, mode list|practice|save, status queued|running|done|failed, at, by, started, ended, result}, "list": {...}, "target": {...}}.
화면은 저장소 _시스템/blcm/job_{건}_{run}/."""
from __future__ import annotations

import datetime
import time
import traceback

from sqlalchemy.orm.attributes import flag_modified

from core import models_web  # noqa: F401 — 표 정의
from core.db import DATA_DIR, SessionLocal
from core.models_web import BlcmJob

POLL_SECONDS = 4
ROOT = DATA_DIR / "_시스템" / "blcm"


def run_dir(jid: int, rid: int):
    return ROOT / f"job_{jid}_{rid}"


def _claim(db) -> int | None:
    rows = db.query(BlcmJob).filter(BlcmJob.site.isnot(None)).order_by(BlcmJob.id).all()
    for j in rows:
        r = (j.site or {}).get("run") or {}
        if r.get("status") == "queued":
            j = db.query(BlcmJob).filter(BlcmJob.id == j.id).with_for_update().one()
            site = dict(j.site or {})
            r = dict(site.get("run") or {})
            if r.get("status") != "queued":
                continue
            r["status"], r["started"] = "running", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            site["run"] = r
            j.site = site
            flag_modified(j, "site")
            db.commit()
            return j.id
    return None


def _finish(jid: int, res: dict) -> None:
    with SessionLocal() as db:
        j = db.get(BlcmJob, jid)
        site = dict(j.site or {})
        r = dict(site.get("run") or {})
        r["status"] = "failed" if res.get("error") or any(v.get("state") == "fail" for v in (res.get("items") or {}).values()) else "done"
        r["ended"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        r["result"] = {k: v for k, v in res.items() if k != "list"}
        site["run"] = r
        if res.get("list") is not None:
            site["list"] = {"rows": res["list"], "at": r["ended"]}
        hist = list(site.get("history") or [])[-19:]
        hist.append({"id": r.get("id"), "mode": r.get("mode"), "status": r["status"], "at": r["ended"], "by": r.get("by"),
                     "error": (res.get("error") or "")[:160]})
        site["history"] = hist
        j.site = site
        flag_modified(j, "site")
        db.commit()


def _process(jid: int) -> None:
    from server.api.routers.blcm import company_cred, folder
    from server.blcm import bot

    with SessionLocal() as db:
        j = db.get(BlcmJob, jid)
        r = (j.site or {}).get("run") or {}
        cred = company_cred(db, j.company_id)
        snapshot = {"results": j.results or {}, "opinion": j.opinion or {}, "contract": j.contract or {}, "owner": j.owner or {},
                    "building": j.building or {}, "site": j.site or {}}
        base = folder(j)
    if cred is None:
        _finish(jid, {"error": "생애이력시스템 계정이 없습니다 — 건축물관리점검 목록 화면에서 계정을 넣으세요."})
        return
    out = run_dir(jid, int(r.get("id") or 0))
    try:
        res = bot.run_job(r.get("mode") or "practice", snapshot, base, cred, out, only=r.get("only") or None)
    except Exception as err:  # noqa: BLE001
        res = {"error": f"봇이 멈췄습니다: {str(err)[:300]}", "log": traceback.format_exc().splitlines()[-8:]}
    _finish(jid, res)


def _reset_stale() -> None:
    """켜질 때 — 지난번 돌다 끊긴(running) 것은 실패로(안 그러면 다음 실행이 막힘)."""
    with SessionLocal() as db:
        for j in db.query(BlcmJob).filter(BlcmJob.site.isnot(None)).all():
            r = (j.site or {}).get("run") or {}
            if r.get("status") == "running":
                site = dict(j.site)
                site["run"] = {**r, "status": "failed", "ended": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                               "result": {**(r.get("result") or {}), "error": "작업 프로그램이 다시 켜져 중간에 멈췄습니다 — 사이트에서 저장 상태를 확인하세요."}}
                j.site = site
                flag_modified(j, "site")
        db.commit()


def run_forever() -> None:
    try:
        _reset_stale()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    while True:
        jid = None
        try:
            with SessionLocal() as db:
                jid = _claim(db)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        if jid is None:
            time.sleep(POLL_SECONDS)
            continue
        try:
            _process(jid)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            try:
                _finish(jid, {"error": "작업 프로그램 오류 — 기록을 보세요"})
            except Exception:  # noqa: BLE001
                traceback.print_exc()
