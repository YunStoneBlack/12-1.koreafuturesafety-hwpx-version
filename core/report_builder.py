"""보고서 산출물 빌더 진입점.

실제 구현은 두 파일로 나뉘어 있다(Sub-phase 7에서 PDF를 9섹션 표준 서식으로 다시 짜면서
파일이 600줄을 넘겨 분리했다):
- `core/report_builder_pdf.py` — PDF (reportlab), 실제 표준 서식(9섹션) 최신 반영
- `core/report_builder_docx.py` — DOCX (python-docx), 아직 예전 7섹션 구조 그대로

기존 코드가 `from core.report_builder import build_report, build_report_docx`로 쓰고 있어서,
이 파일은 그대로 두고 재수출만 한다.
"""

from __future__ import annotations

from core.report_builder_docx import build_report_docx
from core.report_builder_pdf import build_report

__all__ = ["build_report", "build_report_docx"]
