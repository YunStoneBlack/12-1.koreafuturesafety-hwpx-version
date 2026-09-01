"""ReportWizardView의 신규 섹션 UI 조립 로직 — Sub-phase 7(실제 표준 서식 9섹션 개편)에서
추가된 부분: 대형사고 위험작업 사항 / 건설기계장비·위험기계기구·유해위험물질 안전조치 평가 /
현재 진행중인 공정.

기존 report_wizard_sections.py가 이미 600줄에 가까워서 새 섹션은 별도 mixin 파일로 분리했다
(오늘 계속 써온 `_SectionBuilderMixin` 분리 패턴 그대로). ReportWizardView가 이 mixin도 함께
상속한다.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
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


class _EquipmentCheckRow(QWidget):
    """건설기계장비/위험기계기구/유해위험물질 표 한 줄 — 항목명 + 필수지도사항 문구(고정,
    실제 서식 그대로) + 유/무 체크박스 + 평가(비고) 입력칸."""

    def __init__(self, item_name: str, guidance_text: str):
        super().__init__()
        self.item_name = item_name
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)

        self.checkbox = QCheckBox(item_name.replace("\n", " "))
        self.checkbox.setFixedWidth(220)
        layout.addWidget(self.checkbox)

        guidance_label = QLabel(guidance_text)
        guidance_label.setWordWrap(True)
        guidance_label.setStyleSheet("color: #6b7280; font-size: 11px;")
        layout.addWidget(guidance_label, stretch=1)

        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("평가(예: 양호/미흡)")
        self.note_input.setFixedWidth(140)
        layout.addWidget(self.note_input)


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
        self.major_hazard_header = SectionHeader(3, "대형사고 위험작업 사항", required=False)
        note = QLabel("해당하는 작업이 있으면 체크하세요.")
        note.setStyleSheet("color: #6b7280; font-size: 12px;")
        self.major_hazard_checkboxes: list[QCheckBox] = []
        widgets: list[QWidget] = [self.major_hazard_header, note]
        for work in MAJOR_HAZARD_WORKS:
            checkbox = QCheckBox(work)
            self.major_hazard_checkboxes.append(checkbox)
            widgets.append(checkbox)
        return self._card(*widgets)

    def _build_equipment_checks_section(self) -> QFrame:
        self.equipment_header = SectionHeader(
            5, "건설기계장비·위험기계기구·유해위험물질 안전조치 평가", required=False
        )

        widgets: list[QWidget] = [self.equipment_header]

        self.machinery_rows: list[_EquipmentCheckRow] = []
        widgets.append(_bold_label("건설기계장비"))
        for name, guidance in MACHINERY_EQUIPMENT_ITEMS:
            row = _EquipmentCheckRow(name, guidance)
            self.machinery_rows.append(row)
            widgets.append(row)

        self.hand_tool_rows: list[_EquipmentCheckRow] = []
        widgets.append(_bold_label("위험기계기구"))
        for name, guidance in HAND_TOOL_ITEMS:
            row = _EquipmentCheckRow(name, guidance)
            self.hand_tool_rows.append(row)
            widgets.append(row)

        self.hazmat_rows: list[_EquipmentCheckRow] = []
        widgets.append(_bold_label("유해위험물질"))
        for name, guidance in HAZMAT_ITEMS:
            row = _EquipmentCheckRow(name, guidance)
            self.hazmat_rows.append(row)
            widgets.append(row)

        return self._card(*widgets)

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
