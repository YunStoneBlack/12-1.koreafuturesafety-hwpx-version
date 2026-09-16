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


def _remove_stale_preview_cache(doc: HwpxDocument) -> None:
    """`Preview/PrvText.txt`(한글이 문서 내용을 요약해 캐시해두는 미리보기 텍스트)를 실제
    내용으로 다시 채우고, `Preview/PrvImage.png`(썸네일 이미지)는 지운다.

    한글은 저장할 때마다 `PrvText.txt`를 실제 내용과 일치하게 자동 갱신하는데, 우리 엔진은
    템플릿을 열어 필드만 채우고 이 캐시는 안 건드려서 항상 템플릿을 처음 만들 때의 빈 상태
    그대로 남는다(실측 확인: 서로 다른 두 보고서로 만든 산출물의 `PrvText.txt`가 한 글자도
    다르지 않고 완전히 동일했음). 한글의 "문서 보안 설정"이 낮음보다 높으면 이 캐시와 실제
    내용을 대조해서 안 맞을 때 "문서가 손상되었거나 변조되었을 가능성이 있습니다"로 판단해
    자동화(`visible=False`라 승인 대화상자를 못 눌러줌)를 막아버린다 — 실사용 배포판에서
    미리보기/PDF 생성이 COM 단계(`hwp.open()`)에서만 실패하는 문제로 발견(보안 설정을
    낮음으로 낮추면 정상 동작함을 실사용자 PC에서 직접 확인).

    `PrvText.txt`는 `META-INF/container.xml`의 rootfile로 선언돼 있어(python-hwpx 자체
    구조검증이 강제) 그냥 지울 수는 없고(`doc.package.delete()`가 `HwpxStructureError`를
    던짐), `doc.text.plain()`(전체 본문 평문 추출)으로 실제 내용을 다시 써 넣는다 — 한글이
    직접 만드는 것과 형식이 완전히 같지는 않겠지만, 최소한 "실제 내용과 완전히 무관한 캐시"
    상태는 벗어난다. `PrvImage.png`는 rootfile이 아니라(container.xml 미선언) 그냥 지워도
    구조검증을 통과한다 — python-hwpx 자체 검증기(`package_validator.py`)도 이 파일들을
    없어도 되는(생략 가능한) 파일로 취급한다.
    """
    doc.package.set_part("Preview/PrvText.txt", doc.text.plain())
    if doc.package.has_part("Preview/PrvImage.png"):
        doc.package.delete("Preview/PrvImage.png")


def _strip_line_seg_arrays(doc: HwpxDocument) -> None:
    """진짜 원인: 각 문단(`<hp:p>`) 안의 `<hp:linesegarray>`(한글이 저장할 때 계산해두는
    줄 레이아웃 캐시 — 글자가 실제로 어느 줄, 어느 위치에서 시작하는지)를 전부 지운다.

    위 `_remove_stale_preview_cache`(미리보기 텍스트 캐시)만으로는 실사용 배포판에서
    "문서가 손상되었거나 변조되었을 가능성이 있습니다" 오류가 해결되지 않아(보안 설정을
    다시 높음으로 돌려 재현·확인), 한컴디벨로퍼 공식 포럼(forum.developer.hancom.com,
    "Hwpx의 section0.xml 문서 수정시 보안설정 오류 발생")에서 진짜 원인을 확인했다 —
    `<hp:linesegarray>`는 선택사항(optional) 요소인데, 문단의 텍스트를 한글이 아닌 다른
    도구로 직접 수정하면 이 캐시된 레이아웃 정보가 더 이상 실제 텍스트와 안 맞게 되고,
    한글이 그 불일치를 "문서 보안 설정"이 낮음보다 높을 때 변조 가능성으로 판단해 자동화
    (`visible=False`라 확인 대화상자를 못 눌러줌)를 막아버린다. 공식 해결책은 정확히
    "텍스트를 수정한 문단의 linesegarray를 지우는 것"이다 — 우리는 어느 문단을 안
    건드렸는지 추적하지 않으므로(값이 같아도 지우면 그만 — 선택사항 요소라 없어도 한글이
    다시 계산해서 채운다) 문서 전체(표 안 포함)에서 전부 지운다.
    """
    for section in doc.sections:
        removed = False
        for element in list(section.element.iter()):
            tag = element.tag if isinstance(element.tag, str) else ""
            if tag.endswith("}linesegarray"):
                parent = element.getparent()
                if parent is not None:
                    parent.remove(element)
                    removed = True
        if removed:
            section.mark_dirty()


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
            _remove_stale_preview_cache(doc)
            _strip_line_seg_arrays(doc)
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
    from core.hwp_cleanup import ensure_hwp_security_module_registered, kill_orphaned_hwp_processes
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
        # register_module=True가 내부적으로 의존하는 pyhwpx 자체 버그(파이썬/pip이 없는
        # 배포 환경에서 보안모듈 자동등록이 조용히 실패)를 미리 막는다 — 실사용 배포판에서
        # "한글 보안 확인창"이 그대로 뜨는 문제로 발견(core/hwp_cleanup.py 참고).
        ensure_hwp_security_module_registered()
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
