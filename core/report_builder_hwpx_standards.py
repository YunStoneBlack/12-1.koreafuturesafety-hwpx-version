"""10번 "사업장 지원 사항" 표 맨 아래 참고 기준표 — 작업면의 조도기준(안전보건규칙 제8조)과 건설현장 5대 가스 적정공기 기준치.

예전에는 "복합농도측정기 가스 기준치" 그림(템플릿에 들어 있던 BMP 이미지, 한글 2018/2024 PDF에서는 96dpi로 뭉개짐)이 표 마지막 행에
떠 있었다. 사장님 요청(2026-09-21)으로 그 그림을 지우고 같은 자리(표 마지막 칸 안)에 진짜 표 두 개를 넣는다 — 글자는 벡터라
PDF에서도 선명하고, 표 칸 크기를 내용에 맞춰 이전 그림(가로 174mm·세로 126mm)이 차지하던 공간 안에 들어가게 했다.
"""

from __future__ import annotations

from core.report_builder_hwpx_images import _clear_cell_pictures, _locate_field_cell

_TBM_ANCHOR_FIELD = "t16_002"  # 10번 표 안의 필드 — 이 필드가 있는 표의 마지막 행이 기준표 자리다

_TABLE_WIDTH_MM = 174.4          # 이전 그림 가로 크기 — 표 마지막 칸 안쪽 폭
_MM = 7200 / 25.4
_HEADER_FILL = "#BFCCEE"         # 이 문서의 다른 표 제목 칸과 같은 색
_LINE_COLOR = "#000000"
_LINE_WIDTH = "0.12 mm"
_CENTER_PARA_PR = "3"            # 가운데 정렬·줄간격 100%
_LEFT_PARA_PR = "19"             # 왼쪽 정렬·줄간격 100% (제목용)
_BODY_LEFT_PARA_PR = "18"        # 양쪽 정렬·줄간격 150%, 들여쓰기 없음 — 짧은 줄이라 왼쪽 정렬처럼 보이고 여러 줄도 답답하지 않다
_BODY_PT = 8
_TITLE_PT = 9
_ROW_HEIGHT_MM = 5.6
_LINE_HEIGHT_MM = 4.4            # 한 칸에 두 줄 이상 들어갈 때 줄마다 더해주는 높이

# 제목·표 사이 여백(mm) — "여유 간격이 너무 없다"는 피드백(2026-09-21)으로 빈 문단으로 띄운다. 10번 표가 페이지를 거의 채우도록 넓혔다(2026-09-21, 사용자 요청) — 페이지 아래 약 20~25mm는 교육내용·조치사항 줄이 늘어도 안 넘치게 남겨둔 안전 여유이니 더 키우지 말 것.
_GAP_BEFORE_ILLUMINANCE_MM = 9.0  # 조치사항 줄 ↔ 조도기준 제목
_GAP_TITLE_TO_TABLE_MM = 4.0      # 제목 ↔ 바로 아래 표
_GAP_BETWEEN_TABLES_MM = 14.0     # 조도기준 표 ↔ 5대 가스 제목
_GAP_AFTER_LAST_MM = 10.0         # 5대 가스 표 ↔ 큰 표 아래 테두리
_SPACER_LINE_FACTOR = 1.5         # 한글 100% 줄 높이 ≈ 글자 크기의 이 배수(실측 보정용)

_ILLUMINANCE_TITLE = "● 작업면의 조도기준(안전보건규칙 제8조)"
_ILLUMINANCE_HEADER = ("작업 구분", "조도 기준", "해당 작업 예시")
_ILLUMINANCE_ROWS = [
    ("초정밀작업", "750럭스 이상", "초정밀기계작업, 정밀조각, 검사작업 등"),
    ("정밀작업", "300럭스 이상", "인쇄, 검사, 수선, 비행기 조립, 짙은색의 방직 등"),
    ("보통작업", "150럭스 이상", "일반기계조작, 연마, 가공, 용접, 금속의 열처리, 제약, 증류 등"),
    ("그 밖의 작업", "75럭스 이상", "목공, 농업, 주조, 금속로(주입) 작업 등"),
]
_ILLUMINANCE_WIDTHS_MM = (30.0, 32.0, 112.4)

_GAS_TITLE = "● 건설현장 5대 가스 적정공기 기준치"
_GAS_HEADER = ("구분(가스 종류)", "적정공기 기준치(허용 범위)", "주요 위험성 및 특징")
_GAS_ROWS = [
    ("산소(O₂)", ["18% 이상 ~ 23.5% 미만"], ["18% 미만: 산소결핍으로 인한 질식 위험", "23.5% 이상: 산소 과다로 인한 화재·폭발 위험 증가"]),
    ("일산화탄소(CO)", ["30ppm 미만"], ["무색·무취의 유독가스", "두통, 어지러움, 구토 및 질식 유발"]),
    ("황화수소(H₂S)", ["10ppm 미만"], ["썩은 달걀 냄새(고농도 시 후각 마비로 감지 불가)", "호흡 중추 마비 및 사망 위험"]),
    ("이산화탄소(CO₂)", ["1.5% 미만(15,000ppm)"], ["3% 초과 시 호흡곤란, 7~8% 초과 시 의식상실 유발"]),
    ("가연성 가스(LEL)", ["폭발하한계(LEL)의 10% 미만"], ["메탄, 프로판 등 인화성 가스로 인한 화재·폭발 예방"]),
]
_GAS_WIDTHS_MM = (34.0, 46.0, 94.4)


def _hu(mm: float) -> int:
    return round(mm * _MM)


def _style_paragraph(doc, paragraph, para_pr: str, *, bold: bool, size: float) -> None:
    paragraph.para_pr_id_ref = para_pr
    style_id = doc.ensure_run_style(bold=bold, size=size)
    for run in paragraph.runs:
        run.char_pr_id_ref = style_id


def _write_cell(doc, cell, lines: list[str], *, center: bool, bold: bool, size: float = _BODY_PT) -> None:
    cell.set_text("\n".join(lines), split_paragraphs=True)
    for paragraph in cell.paragraphs:
        _style_paragraph(doc, paragraph, _CENTER_PARA_PR if center else _BODY_LEFT_PARA_PR, bold=bold, size=size)


def _make_spacer(doc, paragraph, height_mm: float) -> None:
    """빈 문단의 글자 크기로 높이를 맞춰 여백으로 쓴다."""
    paragraph.text = ""
    size_pt = height_mm * 72 / 25.4 / _SPACER_LINE_FACTOR
    _style_paragraph(doc, paragraph, _CENTER_PARA_PR, bold=False, size=size_pt)


def _add_table(doc, outer_cell, header, rows, widths_mm) -> None:
    """`rows`는 (칸1 문자열 또는 줄 목록, 칸2, 칸3) 목록 — 문자열이면 한 줄, 목록이면 줄바꿈으로 여러 줄."""

    def lines_of(value) -> list[str]:
        return [value] if isinstance(value, str) else list(value)

    total_rows = 1 + len(rows)
    table = outer_cell.add_table(total_rows, 3, width=_hu(sum(widths_mm)), height=_hu(_ROW_HEIGHT_MM * total_rows))
    header_fill = doc.ensure_border_fill(
        border_color=_LINE_COLOR, border_width=_LINE_WIDTH, fill_color=_HEADER_FILL
    )
    body_fill = doc.ensure_border_fill(border_color=_LINE_COLOR, border_width=_LINE_WIDTH)

    for row_index in range(total_rows):
        if row_index == 0:
            values, height_mm = list(header), _ROW_HEIGHT_MM
        else:
            values = [lines_of(v) for v in rows[row_index - 1]]
            height_mm = _ROW_HEIGHT_MM + _LINE_HEIGHT_MM * (max(len(v) for v in values) - 1)
        for col_index, width_mm in enumerate(widths_mm):
            cell = table.cell(row_index, col_index)
            cell.set_size(width=_hu(width_mm), height=_hu(height_mm))
            table.set_cell_border_fill(row_index, col_index, header_fill if row_index == 0 else body_fill)
            if row_index == 0:
                _write_cell(doc, cell, [values[col_index]], center=True, bold=True)
            else:
                # 첫 두 칸은 가운데(구분은 굵게), 마지막 칸(설명)은 왼쪽.
                _write_cell(doc, cell, values[col_index], center=col_index < 2, bold=col_index == 0)


def fill_reference_standard_tables(doc) -> None:
    """10번 표 마지막 행의 떠 있던 가스 기준치 그림을 지우고 그 칸 안에 조도기준표·5대 가스 적정공기 기준치표를 넣는다."""
    located = _locate_field_cell(doc, _TBM_ANCHOR_FIELD)
    if located is None:
        return
    table = located[0]
    cell = table.cell(table.row_count - 1, 0)
    _clear_cell_pictures(cell)
    _remove_orphan_gas_image(doc)

    # 표 칸의 첫 문단(그림이 있던 자리)을 여백으로 쓰고, 그 뒤로 제목·표를 차례로 붙인다.
    _make_spacer(doc, cell.paragraphs[0], _GAP_BEFORE_ILLUMINANCE_MM)
    title = cell.add_paragraph(_ILLUMINANCE_TITLE)
    _style_paragraph(doc, title, _LEFT_PARA_PR, bold=True, size=_TITLE_PT)
    _make_spacer(doc, cell.add_paragraph(""), _GAP_TITLE_TO_TABLE_MM)
    _add_table(doc, cell, _ILLUMINANCE_HEADER, _ILLUMINANCE_ROWS, _ILLUMINANCE_WIDTHS_MM)

    _make_spacer(doc, cell.add_paragraph(""), _GAP_BETWEEN_TABLES_MM)
    gas_title = cell.add_paragraph(_GAS_TITLE)
    _style_paragraph(doc, gas_title, _LEFT_PARA_PR, bold=True, size=_TITLE_PT)
    _make_spacer(doc, cell.add_paragraph(""), _GAP_TITLE_TO_TABLE_MM)
    _add_table(doc, cell, _GAS_HEADER, _GAS_ROWS, _GAS_WIDTHS_MM)
    _make_spacer(doc, cell.add_paragraph(""), _GAP_AFTER_LAST_MM)


def _remove_orphan_gas_image(doc) -> None:
    """지운 그림(템플릿의 `image4`, 약 1.6MB BMP)이 패키지에 그대로 남지 않게 지운다 — 다른 곳에선 안 쓴다."""
    try:
        doc.media.remove_image("image4")
    except Exception:  # noqa: BLE001 - 못 지워도 보고서 생성은 계속(파일이 조금 커질 뿐)
        pass
