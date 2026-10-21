"""API 안전 재시작(2026-10-21) — 뒤에서 도는 일이 없을 때만 웹판 API(uvicorn 8000)를 껐다가 워치독이 다시 띄우게 함.

뒤에서 도는 일 = GET /api/sitok/busy: 시특법 보고서 만들기(DB status "running")·분권·AI 초안(89차부터 뒤에서)·전회차 가져오기.
API가 꺼져 있거나 옛판이라 조회가 없으면 DB의 보고서 만들기만 봄. 10/20 보고서 만드는 중에 재시작해 의정부 441이 끊긴 뒤로 늘 이 확인을 함.
끄는 대상 = data/logs/watchdog.log 마지막 "api 시작 (PID n)" — 끄면 워치독(server/scripts/web_watchdog.ps1)이 몇 초 안에 다시 띄움.

    python -m server.scripts.safe_restart_api            # 바쁘면 그만(종료 코드 2)
    python -m server.scripts.safe_restart_api --wait 20  # 바쁘면 15초마다 다시 보며 20분까지 기다림
    python -m server.scripts.safe_restart_api --check    # 바쁜 일만 보여 줌
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import requests  # noqa: E402

from server.settings import GROUPWARE_RELAY_SECRET, WEB_BASE_PATH  # noqa: E402

LOG = ROOT / "data" / "logs" / "watchdog.log"
API = f"http://127.0.0.1:8000{WEB_BASE_PATH or ''}/api"
START_RE = re.compile(r"api 시작 \(PID (\d+)\)")


def _headers() -> dict:
    from core.db import SessionLocal
    from core.models_web import User

    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email.like("gw:%"), User.active.is_(True)).order_by(User.id).first()
        return {"X-Relay-Secret": GROUPWARE_RELAY_SECRET, "X-Gw-User": quote(u.email[3:]), "X-Gw-Name": quote(u.display_name or "")} if u else {}
    finally:
        db.close()


def busy() -> dict:
    """{builds, splits, ai, imports} — 조회가 안 되면 DB 보고서 만들기만."""
    try:
        r = requests.get(f"{API}/sitok/busy", headers=_headers(), timeout=10)
        if r.ok:
            return r.json()
    except requests.RequestException:
        pass
    from core.db import SessionLocal
    from core.models_web import SitokReport

    db = SessionLocal()
    try:
        return {"builds": [rid for (rid,) in db.query(SitokReport.id).filter(SitokReport.status == "running")], "note": "API 조회 안 됨 — DB만 봄"}
    finally:
        db.close()


def _is_busy(b: dict) -> bool:
    return any(b.get(k) for k in ("builds", "splits", "ai", "imports"))


def _last_pid() -> int | None:
    pids = START_RE.findall(LOG.read_text(encoding="utf-8-sig", errors="ignore")) if LOG.exists() else []
    return int(pids[-1]) if pids else None


def restart() -> bool:
    old = _last_pid()
    if not old:
        print("워치독 기록에서 API PID를 못 찾았습니다:", LOG)
        return False
    subprocess.run(["taskkill", "/PID", str(old), "/F"], capture_output=True)
    for _ in range(45):  # 새 "api 시작" 줄
        time.sleep(2)
        new = _last_pid()
        if new and new != old:
            break
    else:
        print("90초 안에 API가 다시 뜨지 않았습니다 — 워치독을 확인하세요")
        return False
    for _ in range(30):  # 새 API가 답할 때까지
        try:
            if requests.get(f"{API}/sitok/busy", headers=_headers(), timeout=5).status_code < 500:
                print(f"API 다시 뜸 — PID {old} → {new}")
                return True
        except requests.RequestException:
            pass
        time.sleep(2)
    print(f"PID {new}로 떴지만 아직 답이 없습니다")
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait", type=float, default=0, help="바쁘면 기다릴 분(기본 0 = 그만)")
    ap.add_argument("--check", action="store_true", help="바쁜 일만 보여 주고 끝")
    a = ap.parse_args()
    deadline = time.time() + a.wait * 60
    while True:
        b = busy()
        if a.check or not _is_busy(b):
            break
        if time.time() >= deadline:
            print("뒤에서 도는 일이 있어 재시작하지 않았습니다:", b)
            return 2
        print("기다리는 중:", b)
        time.sleep(15)
    print("뒤에서 도는 일:", b if _is_busy(b) else "없음")
    if a.check:
        return 0
    return 0 if restart() else 1


if __name__ == "__main__":
    sys.exit(main())
