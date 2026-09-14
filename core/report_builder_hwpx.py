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
