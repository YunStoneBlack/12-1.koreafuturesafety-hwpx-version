"""HWPX 산출물 생성 — `report_builder_hwp.py`(pyhwpx/COM, 한글 프로그램 설치 필요)를
python-hwpx(순수 파이썬, COM/한글 프로그램 불필요 — 리눅스 서버에서도 동작)로 옮긴 버전.

`data/templates/report_template.hwpx`(기존 `report_template.hwp`를 한글에서 "다른 이름으로
저장 > HWPX"로 한 번 변환해 만든 파일 — 누름틀 필드 이름이 그대로 유지된다, 실측 확인)를
열어 필드를 채운 뒤 새 파일로 저장한다.

pyhwpx/COM 버전(`report_builder_hwp.py`)의 기능을 전부 포팅 완료했다 — 텍스트 필드, 지적사항/
이전지적사항(빈 슬롯 표 삭제 포함), 이미지(사진·도장·절대좌표 서명 겹침·제공자료 부록),
글자 스타일(담당요원 칸, 표12·15 예방대책 칸, 위험성 등급 배경색+가운데정렬+굵게)까지.
"""

from __future__ import annotations

import gc
import shutil
import tempfile
import time
from pathlib import Path

from hwpx.document import HwpxDocument

from core.db import BASE_DIR, SessionLocal
from core.models_db import Report
from core.report_builder_hwpx_fields import fill_all
from core.report_builder_hwpx_images import (
    fill_finding_images,
    fill_material_appendix,
    fill_overview_inspection_images,
    fill_previous_finding_images,
    fill_signoff_images,
    fill_support_images,
)

_TEMPLATE_PATH = BASE_DIR / "data" / "templates" / "report_template.hwpx"
_PDF_CACHE_DIR = Path(tempfile.gettempdir()) / "claude" / "hwpx_pdf_cache"


class HwpxBuildError(RuntimeError):
    pass


def build_report_hwpx(report_id: int, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    if not _TEMPLATE_PATH.exists():
        raise HwpxBuildError(f"HWPX 템플릿을 찾을 수 없습니다: {_TEMPLATE_PATH}")

    with SessionLocal() as session:
        report = session.get(Report, report_id)
        if report is None:
            raise ValueError(f"Report {report_id}를 찾을 수 없습니다.")
        site = report.site

        output_path.parent.mkdir(parents=True, exist_ok=True)

        doc = HwpxDocument.open(_TEMPLATE_PATH)
        try:
            fill_all(doc, report, site)
            fill_overview_inspection_images(doc, report)
            fill_signoff_images(doc, report, site)
            fill_support_images(doc, report)
            fill_finding_images(doc, report)
            fill_previous_finding_images(doc, report)
            fill_material_appendix(doc, report)
            doc.save_to_path(output_path)
        finally:
            doc.close()

        report.hwp_path = str(output_path)
        session.commit()

    return output_path


def build_report_pdf_via_hwpx(report_id: int, output_path: str | Path) -> Path:
    """신규 엔진(COM 불필요)으로 내용을 채운 뒤, 그 결과물을 한글 COM으로 열어 PDF로
    "변환만" 한다 — 필드 채우기는 `build_report_hwpx` 하나로 통일하고 COM은 PDF 렌더러로만
    쓴다.

    기존에는 미리보기/PDF 생성이 `report_builder_hwp.py`(COM이 직접 필드를 채우는 옛 엔진)를
    거쳤는데, 그 결과가 "한글 파일 생성" 버튼(신규 엔진)의 결과물과 미묘하게 달랐다(사진
    칸 맞춤 계산, 절대좌표 서명 위치 계산을 두 엔진이 각각 독립적으로 구현해서) — 사용자가
    직접 두 결과물을 나란히 열어보고 발견함(2026-09-14). 이제 미리보기·PDF·한글 파일 셋 다
    같은 소스(`build_report_hwpx`)에서 나오므로 더 이상 서로 달라질 수 없다.

    `report_builder_hwp.py`의 `build_report_pdf_via_hwp()`와 같은 패턴(임시 폴더에서 작업 후
    최종 PDF만 목적 경로로 복사 — 프로젝트 폴더가 OneDrive 동기화 대상이라 반복 저장이
    느려지는 문제 회피)을 그대로 따른다.
    """
    from core.hwp_cleanup import kill_orphaned_hwp_processes
    from core.report_builder_hwp import HwpBuildError, HwpNotAvailableError

    output_path = Path(output_path)
    _PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp_hwpx = _PDF_CACHE_DIR / f"report_{report_id}.hwpx"
    tmp_pdf = _PDF_CACHE_DIR / f"report_{report_id}.pdf"

    build_report_hwpx(report_id, tmp_hwpx)

    try:
        from pyhwpx import Hwp
    except ImportError as e:
        raise HwpNotAvailableError("pyhwpx가 설치되어 있지 않습니다 (pip install pyhwpx pywin32).") from e

    hwp = None
    try:
        # report_builder_hwp.py의 _fill_and_save()와 같은 이유로 필요 — 이전 세션이 남긴
        # 숨은 한글 프로세스 정리 + 삭제 확인 팝업 자동 통과(visible=False라 응답 불가하면
        # 자동화가 영원히 멈춘다).
        kill_orphaned_hwp_processes()
        hwp = Hwp(visible=False, register_module=True)
        hwp.hwp.SetMessageBoxMode(0x2FFFF1)
        if not hwp.open(str(tmp_hwpx)):
            raise HwpBuildError("생성된 hwpx 파일을 여는 데 실패했습니다.")
        if not hwp.save_as(str(tmp_pdf), format="PDF"):
            raise HwpBuildError("PDF로 변환하는 데 실패했습니다.")
    except HwpBuildError:
        raise
    except Exception as e:  # noqa: BLE001 - 한글 COM 자동화 에러를 그대로 전달
        raise HwpBuildError(f"PDF 변환 중 오류가 발생했습니다: {e}") from e
    finally:
        if hwp is not None:
            try:
                hwp.quit()
            except Exception:
                pass
            del hwp
            gc.collect()
            time.sleep(0.5)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tmp_pdf, output_path)

    with SessionLocal() as session:
        report = session.get(Report, report_id)
        report.status = "final"
        session.commit()

    return output_path
