"""render_worker.run_forever()가 예기치 않게 죽어도(예: 한글 프로세스 이상으로 COM 예외가
루프 밖까지 새어나간 경우) 몇 초 후 자동으로 다시 시작하는 안전망. NSSM 서비스로 등록할
때는 이 파일을 실행 대상으로 지정한다 — NSSM 자체도 프로세스 재시작을 해주지만, 이 안전망을
하나 더 두면 재시작 사이 지연을 짧게(2초) 직접 통제할 수 있다.

실행: `python -m server.worker.supervisor_entry`"""

from __future__ import annotations

import sys
import time
import traceback

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import threading

from server.worker.render_worker import run_forever


def _k2b_loop() -> None:
    """K2B 제출 작업(server/worker/k2b_worker.py, 2026-10-01) — PDF 렌더(한글 COM, 주 스레드)와 따로 이 스레드에서. 죽으면 5초 뒤 다시."""
    from server.worker import k2b_worker

    while True:
        try:
            k2b_worker.run_forever()
        except Exception:  # noqa: BLE001
            print("[supervisor] k2b_worker가 예기치 않게 종료됨, 5초 후 재시작:")
            traceback.print_exc()
            time.sleep(5)


if __name__ == "__main__":
    threading.Thread(target=_k2b_loop, name="k2b_worker", daemon=True).start()
    while True:
        try:
            run_forever()
        except Exception:  # noqa: BLE001
            print("[supervisor] render_worker가 예기치 않게 종료됨, 2초 후 재시작:")
            traceback.print_exc()
            time.sleep(2)
