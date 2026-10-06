"""한글(hwp·hwpx) 붙임 파일 → PDF(2026-10-06). 한글 COM은 한 번에 하나만 안정적으로 돌아서 보고서 PDF 작업 프로그램(render_worker)이
쉬는 틈에 맡는다 — API는 폴더 대기열에 파일을 넣고 결과를 기다린다(DB 표를 늘리지 않으려고 폴더로).

    _시스템\\hwp2pdf\\<번호>.hwpx   → 작업 프로그램이 바꿔서 <번호>.pdf(성공) / <번호>.err(실패 이유)
"""
from __future__ import annotations

import gc
import time
import uuid
from pathlib import Path

from core.db import DATA_DIR

QUEUE_DIR = DATA_DIR / "_시스템" / "hwp2pdf"
WAIT_SECONDS = 150
HWP_EXTS = (".hwp", ".hwpx")


def convert_via_worker(data: bytes, ext: str) -> bytes:
    """API 쪽 — 대기열에 넣고 작업 프로그램이 PDF로 바꿀 때까지 기다린다(보고서 PDF 작업이 앞에 있으면 그만큼 더)."""
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    key = uuid.uuid4().hex
    tmp = QUEUE_DIR / f"{key}.part"
    tmp.write_bytes(data)
    src = tmp.rename(QUEUE_DIR / f"{key}{ext}")
    pdf, err = QUEUE_DIR / f"{key}.pdf", QUEUE_DIR / f"{key}.err"
    try:
        deadline = time.time() + WAIT_SECONDS
        while time.time() < deadline:
            if pdf.exists():
                time.sleep(0.3)  # 다 써질 때까지
                return pdf.read_bytes()
            if err.exists():
                raise RuntimeError(f"한글 파일을 PDF로 바꾸지 못했습니다: {err.read_text(encoding='utf-8')[:200]}")
            time.sleep(1)
        raise RuntimeError("한글 파일 변환이 오래 걸려 멈췄습니다 — 보고서 작업 프로그램이 켜져 있는지 확인하거나 PDF로 바꿔 올리세요.")
    finally:
        for p in (src, pdf, err):
            p.unlink(missing_ok=True)


def process_pending() -> bool:
    """작업 프로그램 쪽(render_worker가 쉴 때 부름) — 대기 중인 한글 파일 하나를 PDF로. 한 게 있으면 True."""
    if not QUEUE_DIR.exists():
        return False
    pending = sorted((p for p in QUEUE_DIR.iterdir() if p.suffix.lower() in HWP_EXTS), key=lambda p: p.stat().st_mtime)
    for src in pending:
        pdf, err = src.with_suffix(".pdf"), src.with_suffix(".err")
        if pdf.exists() or err.exists():
            continue
        try:
            _to_pdf(src, pdf)
        except Exception as e:  # noqa: BLE001 — 이유를 남기고 다음으로
            err.write_text(str(e) or type(e).__name__, encoding="utf-8")
        return True
    return False


def _to_pdf(src: Path, dest: Path) -> None:
    from desktop.workers.ai_worker import with_com
    from core.hwp_cleanup import ensure_hwp_security_module_registered

    def run():
        from pyhwpx import Hwp

        ensure_hwp_security_module_registered()
        hwp = Hwp(visible=False, register_module=True)
        try:
            hwp.hwp.SetMessageBoxMode(0x2FFFF1)  # 확인 창 자동 통과(안 보이는 창이라 응답 못 함)
            if not hwp.open(str(src)):
                raise RuntimeError("한글에서 파일을 열지 못했습니다.")
            tmp = dest.with_suffix(".tmp.pdf")
            if not hwp.save_as(str(tmp), format="PDF"):
                raise RuntimeError("PDF로 저장하지 못했습니다.")
            tmp.rename(dest)
        finally:
            try:
                hwp.quit()
            except Exception:  # noqa: BLE001
                pass
            del hwp
            gc.collect()

    with_com(run)()
