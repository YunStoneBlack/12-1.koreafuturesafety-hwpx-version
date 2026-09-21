"""3번 "전경사진 및 점검사진" 표(전경 2x2 / 점검 2x2 사진 칸) 채우기 — `report_builder_hwpx_images.py`가 600줄을 넘어 분리했다."""

from __future__ import annotations

from core.models_db import Report
from core.report_builder_hwpx_images import _PHOTO_V_MARGIN_MM, _fill_photo_cell, _parse_cell_addr

_SITE_PHOTO_CELLS = {1: "B1", 2: "C1", 3: "B2", 4: "C2"}
_OVERVIEW_PHOTO_TABLE_INDEX = 4
_INSPECTION_PHOTO_TABLE_INDEX = 5


def _align_overview_inspection_tables(doc) -> None:
    """3번 전경/점검 표의 사진 두 열 폭을 같게 맞춘다(사용자 피드백 2026-09-21).

    템플릿에서 두 열의 폭이 22660/23793(약 4mm 차이)이라 오른쪽 사진의 좌우 여백이 더 컸다. 표 전체 폭은 그대로 두고 반반으로
    나눈다. (두 표의 좌우 위치 어긋남은 `report_builder_hwpx_borders.normalize_table_styles`가 맞춘다.)
    """
    tables = [doc.tables.all[_OVERVIEW_PHOTO_TABLE_INDEX], doc.tables.all[_INSPECTION_PHOTO_TABLE_INDEX]]
    for table in tables:
        first = [table.cell(r, 1) for r in range(table.row_count)]
        second = [table.cell(r, 2) for r in range(table.row_count)]
        total = first[0].width + second[0].width
        half = total // 2
        for cell in first:
            cell.set_size(width=half, height=cell.height)
        for cell in second:
            cell.set_size(width=total - half, height=cell.height)


def fill_overview_inspection_images(doc, report: Report) -> None:
    """3. 전경사진 및 점검사진 — 표4(전경사진)/표5(점검사진)의 2x2 사진 칸."""
    _align_overview_inspection_tables(doc)
    for table_index, photos in (
        (_OVERVIEW_PHOTO_TABLE_INDEX, report.overview_photos),
        (_INSPECTION_PHOTO_TABLE_INDEX, report.inspection_photos),
    ):
        by_slot = {p.slot: p for p in photos}
        table = doc.tables.all[table_index]
        for slot, addr in _SITE_PHOTO_CELLS.items():
            row, col = _parse_cell_addr(addr)
            photo = by_slot.get(slot)
            _fill_photo_cell(
                doc,
                table.cell(row, col),
                photo.photo_path if photo else None,
                no_photo=report.misc_no_photo,
                v_margin_mm=_PHOTO_V_MARGIN_MM,
            )
