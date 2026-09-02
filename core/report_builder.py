"""보고서 산출물 빌더 진입점.

실제 구현은 세 파일로 나뉘어 있다(Sub-phase 7에서 PDF를 9섹션 표준 서식으로 다시 짜면서
파일이 600줄을 넘겨 분리했다):
- `core/report_builder_pdf.py` — PDF (reportlab), 실제 표준 서식(9섹션) 최신 반영
- `core/report_builder_docx.py` — DOCX (python-docx), 아직 예전 7섹션 구조 그대로
- `core/report_builder_hwp.py` — 한글(.hwp), 실제 서식 파일을 템플릿으로 재사용
  (Sub-phase 8) — 현재는 표1/표2(현장·본사 정보)만 채워진다

기존 코드가 `from core.report_builder import build_report, build_report_docx`로 쓰고 있어서,
이 파일은 그대로 두고 재수출만 한다.
"""

from __future__ import annotations

from core.report_builder_docx import build_report_docx
from core.report_builder_hwp import build_report_hwp, build_report_pdf_via_hwp
from core.report_builder_pdf import build_report as build_report_reportlab

__all__ = ["build_report", "build_report_docx", "build_report_hwp", "build_report_pdf_via_hwp"]


def build_report(report_id: int, output_path):
    """PDF 생성 진입점. 실제 서식과 100% 일치하는 한글 템플릿 기반 변환을 우선 쓰고,
    한글이 설치되어 있지 않는 등 실패하면 예전 reportlab 방식으로 대체한다."""
    from core.report_builder_hwp import HwpBuildError

    try:
        return build_report_pdf_via_hwp(report_id, output_path)
    except HwpBuildError:
        return build_report_reportlab(report_id, output_path)
