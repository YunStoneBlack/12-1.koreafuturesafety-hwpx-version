"""AI(Claude) 호출 토큰 기록(2026-10-30 민재형 "정기점검 한 건당 토큰·가격이 얼마인지") — 호출마다 한 줄씩 DATA_DIR/_ai_usage/YYYY-MM.jsonl.

쓰는 법: 응답을 받은 곳에서 `ai_usage.log(response, company_id)` 한 줄. 실패해도 본 작업엔 영향 없음(전부 try).
집계: `python -m server.scripts.ai_usage_report [--since 2026-10-30T21:00] [--until ...]` — 부른 곳별·합계 토큰과 대략 가격.
회차별로 보려면 그 회차를 만든 시간대(--since/--until)를 주면 됨(이 서버는 AI를 이 프로그램만 씀).
가격표 PRICES = 100만 토큰당 달러(입력, 출력, 캐시 읽기) — 모델이 바뀌면 여기만 고침."""
from __future__ import annotations

import datetime
import inspect
import json
import os
import threading
from pathlib import Path

PRICES = {  # 모델 접두어 → (입력, 출력) $/1M 토큰 (claude-api 자료 2026-10-06)
    "claude-sonnet-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-fable-5": (10.0, 50.0),
}
_lock = threading.Lock()


def _dir() -> Path:
    from core.db import DATA_DIR

    d = Path(DATA_DIR) / "_ai_usage"
    d.mkdir(parents=True, exist_ok=True)
    return d


def price(model: str, tin: int, tout: int) -> float:
    key = max((k for k in PRICES if (model or "").startswith(k)), key=len, default=None)
    pin, pout = PRICES.get(key, (2.0, 10.0))
    return (tin * pin + tout * pout) / 1_000_000


def log(response, company_id: int | None = None, caller: str = "") -> None:
    """response.usage의 토큰을 한 줄 기록. 부른 함수 이름(두 단계 위)을 같이 적음."""
    try:
        u = response.usage
        if not caller:
            fr = inspect.stack()[2:5]
            caller = " < ".join(f"{os.path.basename(f.filename)}:{f.function}" for f in fr)
        row = {"at": datetime.datetime.now().isoformat(timespec="seconds"), "model": getattr(response, "model", ""),
               "in": int(getattr(u, "input_tokens", 0) or 0), "out": int(getattr(u, "output_tokens", 0) or 0),
               "cache_read": int(getattr(u, "cache_read_input_tokens", 0) or 0), "cache_write": int(getattr(u, "cache_creation_input_tokens", 0) or 0),
               "company": company_id, "caller": caller}
        line = json.dumps(row, ensure_ascii=False)
        with _lock, open(_dir() / f"{row['at'][:7]}.jsonl", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:  # noqa: BLE001 — 기록 실패가 보고서 작업을 막으면 안 됨
        pass
