"""한글(.hwp) 산출물 생성 — `data/templates/report_template.hwp`(실제 원본 서식을 그대로
가져온 누름틀 템플릿, `data/build_hwp_template.py`로 생성)를 열어 필드를 채운 뒤 새 파일로
저장한다.

`core/report_builder_pdf.py`(reportlab로 코드에서 직접 그리는 방식)와 달리, 이쪽은
"실제 서식 파일 자체를 템플릿으로 재사용"하는 방식이라 실제 산출물과 서식이 100%
동일하다는 장점이 있다. 필드를 채우는 코드(`report_builder_hwp_fields.py`)는 표별로 나뉘어
있고, 현재 표1/2(현장·본사 정보)/표5(대형사고위험작업)/표11(현재진행공정)/표13·14(향후진행공정)/
표15(TBM·장비사용)를 채운다 — 표4(이전지적사항)/표8·9·10(3종 장비 안전조치)/표12는 아직
빈 누름틀 상태로 남아있다(`report_builder_hwp_fields.py` 모듈 docstring과
`report_template_fields.json` 참고).

이 PC에 한글 프로그램이 설치되어 있어야 동작한다(COM 자동화, pyhwpx) — `hwpx_exporter.py`와
동일한 방식으로 pyhwpx 미설치 시 명확한 한국어 에러를 낸다.
"""

from __future__ import annotations

import gc
import shutil
import tempfile
import time
from pathlib import Path

from core.db import BASE_DIR, SessionLocal
from core.hwp_cleanup import kill_orphaned_hwp_processes
from core.models_db import Report
from core.report_builder_hwp_fields import fill_all
from core.report_builder_hwp_fields_cleanup import _remove_blank_pages
from core.report_builder_hwp_images import fill_signoff_images, fill_support_images
from core.report_builder_hwp_images_findings import (
    fill_finding_images,
    fill_material_appendix,
    fill_overview_inspection_images,
    fill_previous_finding_images,
)

_TEMPLATE_PATH = BASE_DIR / "data" / "templates" / "report_template.hwp"
_PDF_CACHE_DIR = Path(tempfile.gettempdir()) / "claude" / "hwp_pdf_cache"


class HwpBuildError(RuntimeError):
    pass


class HwpNotAvailableError(HwpBuildError):
    """pyhwpx/한글이 이 PC에 아예 없어서 애초에 시도할 수 없는 경우 — 이 경우에만
    `report_builder.build_report()`가 예전 reportlab 방식으로 조용히 대체한다.

    다른 `HwpBuildError`(템플릿 파일 못 찾음, 자동화 중 일시적 COM 오류 등)는 한글이
    설치돼 있는데 무언가 잘못된 경우라, 조용히 다른 서식으로 대체하면 안 된다 — 그러면
    사용자가 못 알아채는 사이에 완전히 다른(예전) 서식의 보고서가 나가버린다(실측으로
    발견된 사고 — 아주 가끔 미리보기가 딴판으로 나왔다가 다시 누르면 정상으로 돌아오던
    현상이 바로 이 문제였다). 그런 경우는 에러를 그대로 사용자에게 보여줘서 재시도하게
    해야 한다.
    """


def _fill_and_save(report_id: int, hwp_path: Path, pdf_path: Path | None) -> None:
    """템플릿을 한 번만 열어 필드를 채우고, .hwp와(요청하면) PDF를 같은 세션에서 저장한다.

    `Hwp()` 인스턴스 생성/종료 자체에 초 단위 오버헤드가 있어서(미리보기를 누를 때마다
    체감되는 지연의 대부분이 이거였다), .hwp 저장과 PDF 변환을 별도 세션으로 나누지 않고
    하나로 합쳤다.
    """
    try:
        from pyhwpx import Hwp
    except ImportError as e:
        raise HwpNotAvailableError("pyhwpx가 설치되어 있지 않습니다 (pip install pyhwpx pywin32).") from e

    if not _TEMPLATE_PATH.exists():
        raise HwpBuildError(
            f"한글 템플릿을 찾을 수 없습니다: {_TEMPLATE_PATH}\n"
            "data/build_hwp_template.py를 먼저 실행해 템플릿을 만들어야 합니다."
        )

    with SessionLocal() as session:
        report = session.get(Report, report_id)
        if report is None:
            raise ValueError(f"Report {report_id}를 찾을 수 없습니다.")
        site = report.site

        hwp_path.parent.mkdir(parents=True, exist_ok=True)

        hwp = None
        try:
            # 이전 세션이 남긴 숨은 한글 프로세스가 있으면, 지금 새로 띄우는 세션이 그걸
            # 재사용해 창이 안 뜨는 것처럼 보이는 문제를 막기 위해 먼저 정리한다
            # (core/hwp_cleanup.py 참고, 근본 원인은 미파악).
            kill_orphaned_hwp_processes()
            hwp = Hwp(visible=False, register_module=True)
            # 해당사항없음 섹션의 빈 페이지를 정리할 때 표/개체 삭제 확인 팝업이 뜨면
            # 화면이 안 보이는 상태(visible=False)라 응답할 수 없어 자동화가 멈춘다
            # (실측으로 확인됨) — 모든 확인 대화상자를 자동으로 통과시킨다.
            hwp.hwp.SetMessageBoxMode(0x2FFFF1)
            if not hwp.open(str(_TEMPLATE_PATH)):
                raise HwpBuildError("한글 템플릿 파일을 여는 데 실패했습니다.")

            fill_all(hwp, report, site)
            fill_overview_inspection_images(hwp, report)
            fill_signoff_images(hwp, report, site)
            fill_support_images(hwp, report)
            fill_finding_images(hwp, report)
            fill_previous_finding_images(hwp, report)
            # `fill_all()` 안에서 이미 한 차례 빈 페이지를 정리하지만(지적사항 3·4번 표
            # 삭제 등), 그 시점 이후 여기서 사진들을 넣으면서(특히 이전지적사항 이행완료
            # 증빙 사진) 칸 높이가 달라져 페이지 경계가 다시 밀리는 경우가 실측으로
            # 확인됐다 — 표4/5(전경·점검사진) 추가로 문서 전체 분량이 늘어난 뒤 이 문제가
            # 더 잘 드러났다. 본문 사진을 전부 넣은 뒤, 부록(10. 제공자료, 맨 끝에 새 페이지로
            # 추가됨)을 붙이기 전에 한 번 더 정리한다.
            _remove_blank_pages(hwp)
            fill_material_appendix(hwp, report)

            if not hwp.save_as(str(hwp_path)):
                raise HwpBuildError("한글 파일로 저장하는 데 실패했습니다.")
            if pdf_path is not None:
                pdf_path.parent.mkdir(parents=True, exist_ok=True)
                if not hwp.save_as(str(pdf_path), format="PDF"):
                    raise HwpBuildError("PDF로 변환하는 데 실패했습니다.")
        except HwpBuildError:
            raise
        except Exception as e:  # noqa: BLE001 - 한글 COM 자동화 에러를 그대로 전달
            raise HwpBuildError(f"한글 자동화 중 오류가 발생했습니다: {e}") from e
        finally:
            if hwp is not None:
                try:
                    hwp.quit()
                except Exception:
                    pass
                del hwp
                gc.collect()
                time.sleep(0.5)

        report.hwp_path = str(hwp_path)
        report.status = "final"
        session.commit()


def build_report_hwp(report_id: int, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    _fill_and_save(report_id, output_path, None)
    return output_path


def build_report_pdf_via_hwp(report_id: int, output_path: str | Path) -> Path:
    """한글 템플릿을 채운 뒤 한글 프로그램으로 PDF 변환한다.

    PDF도 실제 서식(로고·결재란·관리번호·체크박스 등)과 100% 일치시키려고
    `core/report_builder_pdf.py`(reportlab로 코드에서 직접 그리는 방식) 대신 이 경로를 쓴다
    — 미리보기 왼쪽 패널과 "PDF 생성" 버튼 둘 다 이 함수를 거친다.

    중간 산출물(.hwp, 변환 중간 PDF)은 임시 폴더에서 만들고 최종 PDF만 목적 경로로 복사한다
    — 프로젝트 폴더가 OneDrive 동기화 대상이라 그 안에 반복 저장하면 20분 넘게 멈추는 문제를
    `data/build_hwp_template.py` 작업 중 실측으로 확인했다(핵심기술.md 참고). 미리보기는
    "미리보기 갱신"을 누를 때마다 이 함수를 다시 호출하므로 특히 중요하다.
    """
    output_path = Path(output_path)
    _PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp_hwp = _PDF_CACHE_DIR / f"report_{report_id}.hwp"
    tmp_pdf = _PDF_CACHE_DIR / f"report_{report_id}.pdf"

    _fill_and_save(report_id, tmp_hwp, tmp_pdf)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tmp_pdf, output_path)
    return output_path
