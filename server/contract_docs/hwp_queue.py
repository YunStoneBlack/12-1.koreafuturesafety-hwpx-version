"""한글(hwp·hwpx) 붙임 파일 → PDF(2026-10-06). 한글 COM은 한 번에 하나만 안정적으로 돌아서 보고서 PDF 작업 프로그램(render_worker)이
쉬는 틈에 맡는다 — API는 폴더 대기열에 파일을 넣고 결과를 기다린다(DB 표를 늘리지 않으려고 폴더로).

    _시스템\\hwp2pdf\\<번호>.hwpx   → 작업 프로그램이 바꿔서 <번호>.pdf(성공) / <번호>.err(실패 이유)
    _시스템\\hwp2pdf\\<번호>__x.hwp  → 한글 형식만 바꿔 <번호>__x.outx(= hwpx, 시특법 지난 보고서 올리기 2026-10-10)
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


def convert_via_worker(data: bytes, ext: str, to: str = "pdf", wait: int = WAIT_SECONDS) -> bytes:
    """API 쪽 — 대기열에 넣고 작업 프로그램이 PDF로(to="hwpx"면 한글 hwpx로) 바꿀 때까지 기다린다(보고서 PDF 작업이 앞에 있으면 그만큼 더).
    큰 파일(시특법 보고서 100쪽 넘음)은 wait를 늘려 백그라운드에서 부른다."""
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    key = uuid.uuid4().hex + ("__x" if to == "hwpx" else "")
    tmp = QUEUE_DIR / f"{key}.part"
    tmp.write_bytes(data)
    src = tmp.rename(QUEUE_DIR / f"{key}{ext}")
    pdf, err = QUEUE_DIR / (f"{key}.outx" if to == "hwpx" else f"{key}.pdf"), QUEUE_DIR / f"{key}.err"
    try:
        deadline = time.time() + wait
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
        to_hwpx = src.stem.endswith("__x")
        pdf, err = src.with_suffix(".outx" if to_hwpx else ".pdf"), src.with_suffix(".err")
        if pdf.exists() or err.exists():
            continue
        try:
            _to_pdf(src, pdf, "HWPX" if to_hwpx else "PDF")
        except Exception as e:  # noqa: BLE001 — 이유를 남기고 다음으로
            err.write_text(str(e) or type(e).__name__, encoding="utf-8")
        return True
    return False


def _to_pdf(src: Path, dest: Path, fmt: str = "PDF") -> None:
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
            # 임시 파일은 대기열 밖(_work)에 — 대기열 안에 .hwpx로 두면 다음 일감으로 다시 집힘(10/10)
            work = dest.parent / "_work"
            work.mkdir(exist_ok=True)
            tmp = work / (dest.stem + (".pdf" if fmt == "PDF" else ".hwpx"))
            tmp.unlink(missing_ok=True)
            if not hwp.save_as(str(tmp), format=fmt):
                raise RuntimeError(f"{fmt}로 저장하지 못했습니다.")
        finally:
            try:
                hwp.quit()
            except Exception:  # noqa: BLE001
                pass
            del hwp
            gc.collect()
        # 한글을 닫은 뒤에 옮김 — hwpx로 "다른 이름 저장"하면 한글이 그 파일을 열어 둔 채라 닫기 전엔 못 옮김(10/10)
        for _ in range(20):
            try:
                tmp.replace(dest)
                break
            except PermissionError:
                time.sleep(0.5)
        else:
            tmp.replace(dest)

    with_com(run)()
