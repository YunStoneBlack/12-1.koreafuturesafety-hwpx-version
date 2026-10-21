"""한글(hwp·hwpx) 붙임 파일 → PDF(2026-10-06). 한글 COM은 한 번에 하나만 안정적으로 돌아서 보고서 PDF 작업 프로그램(render_worker)이
쉬는 틈에 맡는다 — API는 폴더 대기열에 파일을 넣고 결과를 기다린다(DB 표를 늘리지 않으려고 폴더로).

    _시스템\\hwp2pdf\\<번호>.hwpx   → 작업 프로그램이 바꿔서 <번호>.pdf(성공) / <번호>.err(실패 이유)
    _시스템\\hwp2pdf\\<번호>__x.hwp  → 한글 형식만 바꿔 <번호>__x.outx(= hwpx, 시특법 지난 보고서 올리기 2026-10-10)
    _시스템\\hwp2pdf\\<번호>__m0.hwpx + _add\\<번호>__m0.hwpx → 한글이 뒤 파일을 앞 파일 끝에 끼워 넣어(파일 끼워 넣기, 쪽 나눔 뒤) <번호>__m0.outx
      (10/21 내진성능평가 — 외주 3~7장을 우리 1~2장 뒤에: 장 번호·쪽 번호·머리말이 사람이 붙여 넣은 것처럼 이어짐. m0 = 구역 설정 안 가져옴, m1 = 가져옴)
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


def convert_via_worker(data: bytes, ext: str, to: str = "pdf", wait: int = WAIT_SECONDS, add: bytes | None = None, keep_section: int = 0) -> bytes:
    """API 쪽 — 대기열에 넣고 작업 프로그램이 PDF로(to="hwpx"면 한글 hwpx로) 바꿀 때까지 기다린다(보고서 PDF 작업이 앞에 있으면 그만큼 더).
    큰 파일(시특법 보고서 100쪽 넘음)은 wait를 늘려 백그라운드에서 부른다."""
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    key = uuid.uuid4().hex + ("__x" if to == "hwpx" else f"__m{1 if keep_section else 0}" if to == "merge" else "")
    add_path = None
    if to == "merge":  # 끼워 넣을 파일은 하위 폴더(_add)에 먼저 — 대기열 폴더에 두면 일감으로 집힘
        (QUEUE_DIR / "_add").mkdir(exist_ok=True)
        add_path = QUEUE_DIR / "_add" / f"{key}.hwpx"
        add_path.write_bytes(add or b"")
    tmp = QUEUE_DIR / f"{key}.part"
    tmp.write_bytes(data)
    src = tmp.rename(QUEUE_DIR / f"{key}{ext}")
    pdf, err = QUEUE_DIR / (f"{key}.outx" if to in ("hwpx", "merge") else f"{key}.pdf"), QUEUE_DIR / f"{key}.err"
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
        for p in (src, pdf, err, add_path):
            if p is not None:
                p.unlink(missing_ok=True)


def process_pending() -> bool:
    """작업 프로그램 쪽(render_worker가 쉴 때 부름) — 대기 중인 한글 파일 하나를 PDF로. 한 게 있으면 True."""
    if not QUEUE_DIR.exists():
        return False
    pending = sorted((p for p in QUEUE_DIR.iterdir() if p.suffix.lower() in HWP_EXTS), key=lambda p: p.stat().st_mtime)
    for src in pending:
        merge = src.stem.endswith(("__m0", "__m1"))
        to_hwpx = src.stem.endswith("__x") or merge
        pdf, err = src.with_suffix(".outx" if to_hwpx else ".pdf"), src.with_suffix(".err")
        if pdf.exists() or err.exists():
            continue
        try:
            add = QUEUE_DIR / "_add" / f"{src.stem}.hwpx" if merge else None
            _to_pdf(src, pdf, "HWPX" if to_hwpx else "PDF", add=add, keep_section=1 if src.stem.endswith("__m1") else 0)
        except Exception as e:  # noqa: BLE001 — 이유를 남기고 다음으로
            err.write_text(str(e) or type(e).__name__, encoding="utf-8")
        return True
    return False


QUIT_TIMEOUT = 20  # 한글 닫기(quit)가 이보다 오래 걸리면 그때 띄운 Hwp.exe를 강제 종료(10/20 — 닫히다 멈춘 한글이 변환 줄 전체를 막음)
RUN_TIMEOUT = 240  # 열기·저장까지 이보다 오래 걸리면 강제 종료(옹벽 현장조사 부분 — PDF는 다 써 놓고 save_as가 안 돌아옴, 10/20)


def _kill_hwp_since(t0: float) -> int:
    """t0 뒤에 뜬 Hwp.exe 죽이기(다른 스레드에서 — COM 호출 아님). 죽인 수."""
    n = 0
    try:
        import psutil

        for p in psutil.process_iter(["name", "create_time"]):
            try:
                if (p.info["name"] or "").lower() == "hwp.exe" and (p.info["create_time"] or 0) >= t0 - 5:
                    p.kill()
                    n += 1
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    return n


class _Guard:
    """변환 한 번의 감시 — 단계(열기·저장 / 닫기)마다 시간이 넘으면 그 한글을 죽여 멈춤을 푼다(죽으면 COM 호출이 오류로 돌아옴)."""

    def __init__(self, t0: float):
        import threading

        self.t0 = t0
        self.deadline = t0 + RUN_TIMEOUT
        self.done = threading.Event()
        self.killed = False
        self.th = threading.Thread(target=self._watch, daemon=True)
        self.th.start()

    def _watch(self) -> None:
        while not self.done.wait(1):
            if time.time() >= self.deadline:
                self.killed = bool(_kill_hwp_since(self.t0)) or self.killed
                self.deadline = time.time() + 30  # 혹시 남으면 30초마다 다시

    def phase(self, seconds: int) -> None:
        self.deadline = time.time() + seconds

    def stop(self) -> None:
        self.done.set()


def _to_pdf(src: Path, dest: Path, fmt: str = "PDF", add: Path | None = None, keep_section: int = 0) -> None:
    from desktop.workers.ai_worker import with_com
    from core.hwp_cleanup import ensure_hwp_security_module_registered

    def run():
        from pyhwpx import Hwp

        ensure_hwp_security_module_registered()
        t0 = time.time()
        guard = _Guard(t0)
        work = dest.parent / "_work"
        work.mkdir(exist_ok=True)
        tmp = work / (dest.stem + (".pdf" if fmt == "PDF" else ".hwpx"))
        tmp.unlink(missing_ok=True)
        err: Exception | None = None
        hwp = None
        try:
            hwp = Hwp(visible=False, register_module=True)
            hwp.hwp.SetMessageBoxMode(0x2FFFF1)  # 확인 창 자동 통과(안 보이는 창이라 응답 못 함)
            if not hwp.open(str(src)):
                raise RuntimeError("한글에서 파일을 열지 못했습니다.")
            if add is not None:  # 합치기(10/21) — 문서 끝에서 쪽 나눔 뒤 파일 끼워 넣기(글자·문단 모양·스타일은 끼우는 파일 것 유지)
                if not add.exists():
                    raise RuntimeError("끼워 넣을 파일이 없습니다.")
                hwp.MoveDocEnd()
                hwp.hwp.HAction.Run("BreakPage")
                if not hwp.insert_file(str(add), keep_section=keep_section, keep_charshape=1, keep_parashape=1, keep_style=1):
                    raise RuntimeError("파일 끼워 넣기를 하지 못했습니다.")
            # 임시 파일은 대기열 밖(_work)에 — 대기열 안에 .hwpx로 두면 다음 일감으로 다시 집힘(10/10)
            if not hwp.save_as(str(tmp), format=fmt):
                raise RuntimeError(f"{fmt}로 저장하지 못했습니다.")
        except Exception as e:  # noqa: BLE001 — 결과 파일이 있으면(저장은 됐는데 호출만 안 돌아옴) 성공으로
            err = e
        finally:
            guard.phase(QUIT_TIMEOUT)
            if hwp is not None:
                try:
                    hwp.quit()
                except Exception:  # noqa: BLE001 — 강제 종료됐으면 RPC 오류
                    pass
                del hwp
                gc.collect()
            guard.stop()
        time.sleep(0.5)
        if not (tmp.exists() and tmp.stat().st_size > 0):
            raise err or RuntimeError("결과 파일이 없습니다.")
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
