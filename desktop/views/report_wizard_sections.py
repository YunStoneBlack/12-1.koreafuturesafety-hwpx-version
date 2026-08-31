"""ReportWizardView의 섹션별 UI 조립 로직 (1~9번 카드 빌더).

report_wizard_view.py에서 분리됨. _SectionBuilderMixin은 그 자체로는 동작하지 않고,
ReportWizardView가 이 믹스인을 상속해 self.xxx 위젯 속성들을 만들어 붙인다.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.constants import FIXED_HAZARD_FACTORS, MEASUREMENT_INSTRUMENTS
from core.db import SessionLocal
from core.models_db import MeasurementStandard
from desktop.widgets.photo_drop_zone import PhotoDropZone
from desktop.widgets.report_wizard_slots import (
    _FindingSlot,
    _MeasurementRow,
    _PreviousFindingSlot,
    _ProcessSlot,
    _limited_text_edit,
)
from desktop.widgets.section_header import SectionHeader


class _SectionBuilderMixin:
    """ReportWizardView 전용 — 단독으로 인스턴스화하지 않는다."""

    def _card(self, *widgets: QWidget) -> QFrame:
        card = QFrame()
        card.setStyleSheet("QFrame { background: white; border: 1px solid #e5e7eb; border-radius: 10px; }")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        for w in widgets:
            layout.addWidget(w)
        return card

    def _build_overview_section(self) -> QFrame:
        self.overview_header = SectionHeader(1, "전경사진")
        photos_row = QHBoxLayout()
        self.overview_photo_1 = PhotoDropZone("전경사진1 (필수)")
        self.overview_photo_2 = PhotoDropZone("전경사진2")
        photos_row.addWidget(self.overview_photo_1)
        photos_row.addWidget(self.overview_photo_2)
        photos_row.addStretch()
        photos_widget = QWidget()
        photos_widget.setLayout(photos_row)
        return self._card(self.overview_header, photos_widget)

    def _build_safety_education_section(self) -> QFrame:
        self.education_header = SectionHeader(2, "안전교육")
        row = QHBoxLayout()
        self.education_photo = PhotoDropZone("안전교육 사진")
        row.addWidget(self.education_photo)

        form_col = QVBoxLayout()
        form_col.addWidget(QLabel("참석인원"))
        self.attendee_input = QLineEdit()
        self.attendee_input.setPlaceholderText("예: 12")
        form_col.addWidget(self.attendee_input)
        self.count_people_btn = QPushButton("✨ AI로 인원 세기")
        self.count_people_btn.clicked.connect(self._run_count_people)
        form_col.addWidget(self.count_people_btn)
        form_col.addWidget(QLabel("직접 입력하셔도 됩니다"))
        form_col.addStretch()
        row.addLayout(form_col)
        row.addStretch()
        row_widget = QWidget()
        row_widget.setLayout(row)
        return self._card(self.education_header, row_widget)

    def _build_findings_section(self) -> QFrame:
        self.findings_header = SectionHeader(3, "지적사항")
        note = QLabel("✦ 사진 업로드 후 설명을 입력하시고 AI추천 버튼을 클릭하시면 관련 지적사항을 AI가 작성합니다")
        note.setStyleSheet("color: #4f46e5; font-size: 12px;")
        self.finding_slots = [_FindingSlot(i) for i in range(1, 5)]
        return self._card(self.findings_header, note, *self.finding_slots)

    def _build_special_note_section(self) -> QFrame:
        header_row = QHBoxLayout()
        badge = QLabel("4")
        badge.setFixedSize(24, 24)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet("background: #4f46e5; color: white; border-radius: 12px; font-weight: 600;")
        header_row.addWidget(badge)
        title = QLabel("기타 특이사항 •")
        title.setStyleSheet("font-size: 15px; font-weight: 700; margin-left: 6px;")
        header_row.addWidget(title)
        header_row.addStretch()
        self.note_ai_btn = QPushButton("✨ AI추천")
        self.note_ai_btn.clicked.connect(self._run_generate_note)
        header_row.addWidget(self.note_ai_btn)
        header_widget = QWidget()
        header_widget.setLayout(header_row)

        note = QLabel("✦ AI추천 버튼을 누르면 지적사항을 바탕으로 특이사항에 대한 내용을 작성합니다")
        note.setStyleSheet("color: #4f46e5; font-size: 12px;")

        self.special_note_edit, self.special_note_counter = _limited_text_edit(160)
        self.special_note_edit.setPlaceholderText("예: 금일 현장은 전반적으로 양호하나 일부 구간 안전난간 보완이 필요합니다.")

        return self._card(header_widget, note, self.special_note_edit, self.special_note_counter)

    def _build_previous_findings_section(self) -> QFrame:
        self.previous_header = SectionHeader(5, "이전지적사항", required=False)
        self.previous_hint_label = QLabel("이전 회차 지적사항이 없습니다. 직접 넣으실 항목이 있으면 아래 버튼으로 추가하세요.")
        self.previous_hint_label.setStyleSheet("color: #6b7280;")
        self.previous_slots = [_PreviousFindingSlot(i) for i in range(1, 5)]
        self.previous_add_btn = QPushButton("+ 이전지적사항 추가 (0/4)")
        self.previous_add_btn.clicked.connect(self._add_previous_finding_slot)
        return self._card(
            self.previous_header, self.previous_hint_label, *self.previous_slots, self.previous_add_btn
        )

    def _add_previous_finding_slot(self) -> None:
        inactive = [s for s in self.previous_slots if not s.is_active()]
        if not inactive:
            return
        inactive[0].set_active(True)
        self._update_previous_add_btn()

    def _update_previous_add_btn(self) -> None:
        active_count = sum(1 for s in self.previous_slots if s.is_active())
        self.previous_add_btn.setText(f"+ 이전지적사항 추가 ({active_count}/4)")
        self.previous_add_btn.setEnabled(active_count < 4)

    def _build_measurement_section(self) -> QFrame:
        self.measurement_header = SectionHeader(6, "계측자료")
        with SessionLocal() as session:
            standards = {s.instrument_type: s.standard_criteria for s in session.query(MeasurementStandard).all()}
        self.measurement_rows = [
            _MeasurementRow(name, unit, standards.get(name, "")) for name, unit in MEASUREMENT_INSTRUMENTS
        ]
        return self._card(self.measurement_header, *self.measurement_rows)

    def _build_materials_section(self) -> QFrame:
        self.materials_header = SectionHeader(7, "제공자료")
        note = QLabel("✦ AI추천을 누르면 지적사항 내용을 바탕으로 관련 자료를 찾아줍니다")
        note.setStyleSheet("color: #4f46e5; font-size: 12px;")

        buttons_row = QHBoxLayout()
        self.material_ai_btn = QPushButton("✨ AI 추천")
        self.material_ai_btn.clicked.connect(self._run_recommend_materials)
        self.material_browse_btn = QPushButton("🔎 모든자료 보기")
        self.material_browse_btn.clicked.connect(self._open_material_picker)
        buttons_row.addWidget(self.material_ai_btn)
        buttons_row.addWidget(self.material_browse_btn)
        buttons_row.addStretch()
        buttons_widget = QWidget()
        buttons_widget.setLayout(buttons_row)

        self._selected_materials = []
        self.materials_empty_label = QLabel("선택된 자료가 없습니다.")
        self.materials_empty_label.setStyleSheet("color: #9ca3af;")
        self.materials_preview_row = QHBoxLayout()
        self.materials_preview_row.addWidget(self.materials_empty_label)
        self.materials_preview_row.addStretch()
        materials_preview_widget = QWidget()
        materials_preview_widget.setLayout(self.materials_preview_row)

        return self._card(self.materials_header, note, buttons_widget, materials_preview_widget)

    def _build_hazard_factors_section(self) -> QFrame:
        self.hazard_header = SectionHeader(8, "12대 사망사고 기인물 안전조치")
        self.hazard_checkboxes: list[QCheckBox] = []
        widgets: list[QWidget] = [self.hazard_header]
        for number, name, action in FIXED_HAZARD_FACTORS:
            checkbox = QCheckBox(f"{number}. {name} — {action}")
            self.hazard_checkboxes.append(checkbox)
            widgets.append(checkbox)
        note = QLabel("1회차에 체크하면 다음 회차부터 자동으로 동일하게 적용됩니다.")
        note.setStyleSheet("color: #9ca3af; font-size: 11px;")
        widgets.append(note)
        return self._card(*widgets)

    def _build_process_section(self) -> QFrame:
        self.process_header = SectionHeader(9, "진행공정 유해·위험 요인 파악 및 대책")
        note = QLabel("보고서 6번 표에 인쇄되는 모습 그대로입니다 — 칸을 눌러 공정을 고르세요.")
        note.setStyleSheet("color: #6b7280; font-size: 12px;")
        self.process_slots = [_ProcessSlot(i) for i in range(1, 5)]

        # 실제 사이트처럼 하나의 표(좌측 "주요 진행공정" 라벨 열 + 2x2 칸)로 배치한다.
        # 순서는 1번칸(좌상)-3번칸(우상)-2번칸(좌하)-4번칸(우하) — 보고서 6번 표의
        # 칸 배치와 동일하다.
        table = QFrame()
        table.setStyleSheet("QFrame { background: white; border: 1px solid #d1d5db; border-radius: 8px; }")
        table_layout = QHBoxLayout(table)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)

        label_cell = QLabel("주요\n진행공정")
        label_cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label_cell.setFixedWidth(90)
        label_cell.setStyleSheet(
            "background: #f9fafb; color: #374151; font-weight: 600; "
            "border-right: 1px solid #d1d5db;"
        )
        table_layout.addWidget(label_cell)

        grid = QGridLayout()
        grid.setSpacing(0)
        grid.setContentsMargins(0, 0, 0, 0)
        positions = {1: (0, 0), 3: (0, 1), 2: (1, 0), 4: (1, 1)}
        for process_slot in self.process_slots:
            row, col = positions[process_slot.slot]
            borders = []
            if row == 0:
                borders.append("border-bottom: 1px solid #e5e7eb")
            if col == 0:
                borders.append("border-right: 1px solid #e5e7eb")
            border_css = "; ".join(borders)
            process_slot.setStyleSheet(f"QFrame {{ background: transparent; border: none; {border_css}; }}")
            grid.addWidget(process_slot, row, col)
        grid_widget = QWidget()
        grid_widget.setLayout(grid)
        table_layout.addWidget(grid_widget, stretch=1)

        # 실제 사이트처럼 선택된 공정만 아래쪽 "진행공정/유해·위험요인/예방대책/위험성"
        # 4열 표에 번호를 새로 매겨 나열한다. 빈 칸은 이 표에 아예 나타나지 않는다.
        self.process_detail_frame = QFrame()
        self.process_detail_frame.setStyleSheet(
            "QFrame { background: white; border: 1px solid #d1d5db; border-radius: 8px; }"
        )
        detail_grid = QGridLayout(self.process_detail_frame)
        detail_grid.setSpacing(0)
        detail_grid.setContentsMargins(0, 0, 0, 0)
        detail_grid.setColumnStretch(0, 2)
        detail_grid.setColumnStretch(1, 4)
        detail_grid.setColumnStretch(2, 4)
        detail_grid.setColumnStretch(3, 1)

        for col, text in enumerate(("진행공정", "유해·위험요인", "예방대책", "위험성")):
            header_cell = QLabel(text)
            header_cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
            border = "border-right: 1px solid #d1d5db;" if col < 3 else ""
            header_cell.setStyleSheet(
                f"background: #f9fafb; color: #374151; font-weight: 600; padding: 8px; "
                f"border-bottom: 1px solid #d1d5db; {border}"
            )
            detail_grid.addWidget(header_cell, 0, col)

        for row, process_slot in enumerate(self.process_slots, start=1):
            cells = (
                process_slot.detail_name_widget,
                process_slot.hazard_cell,
                process_slot.prevention_cell,
                process_slot.risk_column,
            )
            for col, cell in enumerate(cells):
                border = "border-right: 1px solid #e5e7eb;" if col < 3 else ""
                cell.setStyleSheet(f"background: white; border-bottom: 1px solid #e5e7eb; {border}")
                detail_grid.addWidget(cell, row, col)

        help_note = QLabel(
            "칸 순서 그대로 보고서 표에 인쇄됩니다. 진행공정 이름·유해위험요인·예방대책은 칸을 클릭해 직접 "
            "수정할 수 있고, 위험성 등급은 상·중·하로 눌러 바꿀 수 있습니다.\n"
            "여기서 선택·수정한 내용은 이 현장에 저장되어, 다음 회차 보고서 작성 시 자동으로 채워집니다 "
            "(매 회차 다시 고를 필요 없이 바뀐 공정만 교체하면 됩니다)."
        )
        help_note.setWordWrap(True)
        help_note.setStyleSheet("color: #4f46e5; font-size: 12px;")

        for process_slot in self.process_slots:
            process_slot.changed.connect(self._update_process_table)
        self._update_process_table()

        return self._card(self.process_header, note, table, self.process_detail_frame, help_note)

    def _update_process_table(self) -> None:
        seq = 0
        for process_slot in self.process_slots:
            filled = process_slot.has_data()
            cells = (
                process_slot.detail_name_widget,
                process_slot.hazard_cell,
                process_slot.prevention_cell,
                process_slot.risk_column,
            )
            for cell in cells:
                cell.setVisible(filled)
            if filled:
                seq += 1
                process_slot.seq_label.setText(f"{seq}.")
        self.process_header.set_count(seq, 4)
        self.process_detail_frame.setVisible(seq > 0)
