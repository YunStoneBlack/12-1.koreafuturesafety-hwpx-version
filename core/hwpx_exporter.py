"""DOCX를 한글(HWP) 프로그램으로 열어 HWPX로 저장하는 모듈.

HWPX는 python-docx처럼 순수 파이썬으로 만들기 어려워서, 이미 만들어둔 DOCX
(report_builder.build_report_docx)를 한글에서 열고 "다른 이름으로 저장"하는 방식을
쓴다. 이 PC에 한글 프로그램이 설치되어 있어야 동작한다 (COM 자동화, pyhwpx).
"""

from __future__ import annotations

import gc
import time
from pathlib import Path


class HwpxExportError(RuntimeError):
    pass


def convert_docx_to_hwpx(docx_path: str | Path, hwpx_path: str | Path) -> Path:
    try:
        from pyhwpx import Hwp
    except ImportError as e:
        raise HwpxExportError("pyhwpx가 설치되어 있지 않습니다 (pip install pyhwpx pywin32).") from e

    docx_path = Path(docx_path)
    hwpx_path = Path(hwpx_path)
    if not docx_path.exists():
        raise HwpxExportError(f"DOCX 파일을 찾을 수 없습니다: {docx_path}")
    hwpx_path.parent.mkdir(parents=True, exist_ok=True)

    hwp = None
    try:
        hwp = Hwp(visible=False)
        if not hwp.open(str(docx_path), format="OOXML"):
            raise HwpxExportError("한글에서 DOCX 파일을 여는 데 실패했습니다.")
        if not hwp.save_as(str(hwpx_path), format="HWPX"):
            raise HwpxExportError("HWPX로 저장하는 데 실패했습니다.")
    except HwpxExportError:
        raise
    except Exception as e:  # noqa: BLE001 - 한글 COM 자동화 에러를 그대로 전달
        raise HwpxExportError(f"한글 자동화 중 오류가 발생했습니다: {e}") from e
    finally:
        if hwp is not None:
            try:
                hwp.quit()
            except Exception:
                pass
            del hwp
            gc.collect()
            time.sleep(0.5)

    return hwpx_path
