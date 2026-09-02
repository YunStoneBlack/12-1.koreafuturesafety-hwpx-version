"""ReportWizardView의 신규 섹션 UI 조립 로직 — Sub-phase 7(실제 표준 서식 9섹션 개편)에서
추가된 부분: 대형사고 위험작업 사항 / 건설기계장비·위험기계기구·유해위험물질 안전조치 평가 /
현재 진행중인 공정.

기존 report_wizard_sections.py가 이미 600줄에 가까워서 새 섹션은 별도 mixin 파일로 분리했다
(오늘 계속 써온 `_SectionBuilderMixin` 분리 패턴 그대로). ReportWizardView가 이 mixin도 함께
상속한다.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from core.constants import HAND_TOOL_ITEMS, HAZMAT_ITEMS, MACHINERY_EQUIPMENT_ITEMS, MAJOR_HAZARD_WORKS
from desktop.widgets.photo_drop_zone import PhotoDropZone
from desktop.widgets.report_wizard_slots import _badge_style, _limited_text_edit
from desktop.widgets.section_header import SectionHeader


def _bold_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-weight: 700; margin-top: 6px;")
    return label


_EQUIPMENT_EVAL_STYLE_OFF = (
    "QPushButton { background: white; color: #6b7280; border: 1px solid #d1d5db; "
    "border-radius: 10px; padding: 2px 10px; font-size: 12px; }"
)
_EQUIPMENT_EVAL_STYLE_ON = (
    "QPushButton { background: #4f46e5; color: white; border: 1px solid #4f46e5; "
    "border-radius: 10px; padding: 2px 10px; font-weight: 600; font-size: 12px; }"
)


def _centered_widget(inner: QWidget) -> QWidget:
    wrapper = QWidget()
    layout = QHBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(inner)
    return wrapper


class _EquipmentEvalCell(QWidget):
    """평가(양호/미흡) 버튼 쌍 — 표 셀에 끼워 넣는 위젯."""

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        self.eval_buttons = QButtonGroup(self)
        self.eval_buttons.setExclusive(True)
        for label in ("양호", "미흡"):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setAutoDefault(False)
            btn.setStyleSheet(_EQUIPMENT_EVAL_STYLE_OFF)
            btn.toggled.connect(self._update_eval_styles)
            self.eval_buttons.addButton(btn)
            layout.addWidget(btn)

    def _update_eval_styles(self) -> None:
        for btn in self.eval_buttons.buttons():
            btn.setStyleSheet(_EQUIPMENT_EVAL_STYLE_ON if btn.isChecked() else _EQUIPMENT_EVAL_STYLE_OFF)

    def evaluation(self) -> str:
        checked = self.eval_buttons.checkedButton()
        return checked.text() if checked else ""

    def set_evaluation(self, value: str) -> None:
        for btn in self.eval_buttons.buttons():
            btn.setChecked(btn.text() == value)


class _EquipmentItemControls:
    """표(QTableWidget) 셀에 심어진 위젯(체크박스/지도사항 줄별 평가 버튼)에 대한 접근자.

    유/무 체크박스는 항목당 하나(실제 문서도 항목 단위 개념)지만, 평가는 지도사항 줄마다
    독립된 버튼을 둔다 — 처음엔 항목당 하나로 합쳐(줄 수만큼 병합) 보여줬는데, 항목이
    여러 줄일 때 줄마다 서로 다르게 평가할 수 있어야 한다는 피드백으로 줄 개수만큼
    `_EquipmentEvalCell`을 따로 갖는 구조로 바꿨다.
    """

    def __init__(self, item_name: str, checkbox: QCheckBox, eval_cells: list[_EquipmentEvalCell]):
        self.item_name = item_name
        self.checkbox = checkbox
        self._eval_cells = eval_cells

    def evaluations(self) -> list[str]:
        return [cell.evaluation() for cell in self._eval_cells]

    def set_evaluations(self, values: list[str]) -> None:
        for cell, value in zip(self._eval_cells, values):
            cell.set_evaluation(value)


class _CurrentProcessRow(QFrame):
    """6번 섹션(현재 진행중인 공정) 한 행 — 유해위험요인/현재안전보건조치/위험성수준/평가."""

    def __init__(self, slot: int):
        super().__init__()
        self.slot = slot
        self.setStyleSheet("QFrame { background: #fafafa; border: 1px solid #e5e7eb; border-radius: 8px; }")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"유해위험요인 {slot}"))

        self.hazard_edit, self.hazard_counter = _limited_text_edit(200)
        self.hazard_edit.setPlaceholderText("유해위험요인")
        self.measure_edit, self.measure_counter = _limited_text_edit(200)
        self.measure_edit.setPlaceholderText("현재안전보건조치")
        layout.addWidget(self.hazard_edit)
        layout.addWidget(self.hazard_counter)
        layout.addWidget(self.measure_edit)
        layout.addWidget(self.measure_counter)

        bottom_row = QHBoxLayout()
        bottom_row.addWidget(QLabel("위험성수준"))
        self.risk_buttons = QButtonGroup(self)
        self.risk_buttons.setExclusive(True)
        for label in ("상", "중", "하"):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setAutoDefault(False)
            btn.setStyleSheet(_badge_style(""))
            btn.toggled.connect(self._update_styles)
            self.risk_buttons.addButton(btn)
            bottom_row.addWidget(btn)

        bottom_row.addWidget(QLabel("평가"))
        self.eval_buttons = QButtonGroup(self)
        self.eval_buttons.setExclusive(True)
        for label in ("양호", "미흡"):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setAutoDefault(False)
            self.eval_buttons.addButton(btn)
            bottom_row.addWidget(btn)

        layout.addLayout(bottom_row)

    def _update_styles(self) -> None:
        for btn in self.risk_buttons.buttons():
            btn.setStyleSheet(_badge_style(btn.text() if btn.isChecked() else ""))

    def risk_level(self) -> str:
        checked = self.risk_buttons.checkedButton()
        return checked.text() if checked else ""

    def evaluation(self) -> str:
        checked = self.eval_buttons.checkedButton()
        return checked.text() if checked else ""

    def has_data(self) -> bool:
        return bool(self.hazard_edit.toPlainText() or self.measure_edit.toPlainText())


class _SectionBuilderMixin2:
    """ReportWizardView 전용 — 단독으로 인스턴스화하지 않는다."""

    def _build_major_hazard_work_section(self) -> QFrame:
        self.major_hazard_header = SectionHeader(4, "대형사고 위험작업 사항", required=False)
        note = QLabel("해당하는 작업이 있으면 체크하세요.")
        note.setStyleSheet("color: #6b7280; font-size: 12px;")
        self.major_hazard_checkboxes: list[QCheckBox] = []
        widgets: list[QWidget] = [self.major_hazard_header, note]
        for work in MAJOR_HAZARD_WORKS:
            checkbox = QCheckBox(work)
            self.major_hazard_checkboxes.append(checkbox)
            widgets.append(checkbox)
        return self._card(*widgets)

    def _equipment_table(self, items: list[tuple[str, list[str]]], rows_store: list) -> QTableWidget:
        """건설기계장비/위험기계기구/유해위험물질 표 하나 — 항목 | 유/무 | 필수지도사항 확인 | 평가.

        실제 문서는 항목 하나에 지도사항이 1~3줄씩 별도 행을 차지한다. 유/무는 항목 단위
        개념이라 그 줄 수만큼 병합해 한 번만 표기하지만, 평가는 줄마다 따로 판단할 수
        있어야 해서 병합하지 않고 줄마다 독립된 양호/미흡 버튼을 둔다(처음엔 평가도 항목당
        하나로 합쳤었는데, 항목이 여러 줄일 때 줄마다 다르게 평가할 수 있어야 한다는
        피드백으로 되돌렸다 — `core/report_builder_hwp_fields.py`의
        `fill_equipment_data_fields()`도 줄마다 독립된 필드를 채운다). 예전에는 항목마다
        지도사항을 한 줄짜리 문구로 뭉쳐서 보여줬는데, 실제로는 항목당 줄 수가 제각각이라
        (굴착기 3줄, 덤프트럭 1줄 등) 마법사만 보면 항목이 실제보다 적어 보이는 문제가
        있었다 — 5-1/5-2(17대 기인물)에 쓴 QTableWidget+setSpan 패턴을 가져와 마법사도
        보고서와 같은 행 구조로 보이게 한다.
        """
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["항목", "유/무", "필수지도사항 확인", "평가"])
        table.verticalHeader().setVisible(False)
        table.setShowGrid(True)
        table.setStyleSheet(
            "QTableWidget { gridline-color: #d1d5db; border: 1px solid #9ca3af; border-radius: 0px; background: white; }"
            "QHeaderView::section { background: #dbeafe; font-weight: 600; border: 1px solid #9ca3af; padding: 4px; }"
        )
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table.setFrameShape(QFrame.Shape.NoFrame)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        total_rows = sum(max(len(lines), 1) for _, lines in items)
        table.setRowCount(total_rows)

        row_cursor = 0
        for name, lines in items:
            row_span = max(len(lines), 1)

            name_label = QLabel(name)
            name_label.setWordWrap(True)
            name_label.setStyleSheet("padding: 2px 6px; font-weight: 600;")
            table.setCellWidget(row_cursor, 0, name_label)

            checkbox = QCheckBox()
            table.setCellWidget(row_cursor, 1, _centered_widget(checkbox))

            if row_span > 1:
                table.setSpan(row_cursor, 0, row_span, 1)
                table.setSpan(row_cursor, 1, row_span, 1)

            eval_cells: list[_EquipmentEvalCell] = []
            for i, line in enumerate(lines):
                line_label = QLabel(line)
                line_label.setWordWrap(True)
                line_label.setStyleSheet("padding: 2px 6px; color: #374151; font-size: 12px;")
                table.setCellWidget(row_cursor + i, 2, line_label)

                eval_cell = _EquipmentEvalCell()
                table.setCellWidget(row_cursor + i, 3, eval_cell)
                eval_cells.append(eval_cell)

            rows_store.append(_EquipmentItemControls(name, checkbox, eval_cells))
            row_cursor += row_span

        table.resizeRowsToContents()
        header_height = table.horizontalHeader().height()
        rows_height = sum(table.rowHeight(r) for r in range(total_rows))
        table.setFixedHeight(header_height + rows_height + 4)
        return table

    def _build_equipment_check_widgets(self) -> list[QWidget]:
        """5-3. 건설기계장비·위험기계기구·유해위험물질 안전조치 평가.

        실제 문서에서는 이 표들이 12대 기인물 표(표6) 바로 뒤에 별도 번호 없이 이어진다 —
        마법사에서만 5번 카드 안의 소제목("5-3.")으로 구분해서 보여준다(예전엔 독립된
        "6번" 카드였다). 그래서 독자적인 `self._card(...)`로 감싸지 않고 위젯 목록만
        반환한다 — `_build_hazard_factors_section()`이 이 목록을 자기 카드 안에 이어붙인다.
        """
        self.equipment_header = SectionHeader(
            None, "5-3. 건설기계장비·위험기계기구·유해위험물질 안전조치 평가", required=False
        )

        widgets: list[QWidget] = [self.equipment_header]

        self.machinery_rows: list[_EquipmentItemControls] = []
        widgets.append(_bold_label("건설기계장비"))
        widgets.append(self._equipment_table(MACHINERY_EQUIPMENT_ITEMS, self.machinery_rows))

        self.hand_tool_rows: list[_EquipmentItemControls] = []
        widgets.append(_bold_label("위험기계기구"))
        widgets.append(self._equipment_table(HAND_TOOL_ITEMS, self.hand_tool_rows))

        self.hazmat_rows: list[_EquipmentItemControls] = []
        widgets.append(_bold_label("유해위험물질"))
        widgets.append(self._equipment_table(HAZMAT_ITEMS, self.hazmat_rows))

        return widgets

    def _build_current_process_section(self) -> QFrame:
        self.current_process_header = SectionHeader(6, "현재 진행중인 공정 유해위험요인 파악")

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("공정명"))
        self.current_process_name_input = QLineEdit()
        self.current_process_name_input.setPlaceholderText("예: 보도블록 철거작업")
        name_row.addWidget(self.current_process_name_input)
        name_widget = QWidget()
        name_widget.setLayout(name_row)

        photos_row = QHBoxLayout()
        self.current_process_photo_1 = PhotoDropZone("현장사진1")
        self.current_process_photo_2 = PhotoDropZone("현장사진2")
        photos_row.addWidget(self.current_process_photo_1)
        photos_row.addWidget(self.current_process_photo_2)
        photos_row.addStretch()
        photos_widget = QWidget()
        photos_widget.setLayout(photos_row)

        self.current_process_slots: list[_CurrentProcessRow] = [_CurrentProcessRow(i) for i in range(1, 5)]

        return self._card(
            self.current_process_header, name_widget, photos_widget, *self.current_process_slots
        )
