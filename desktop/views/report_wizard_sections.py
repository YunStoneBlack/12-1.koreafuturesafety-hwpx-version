"""ReportWizardView의 섹션별 UI 조립 로직 (1~9번 카드 빌더).

report_wizard_view.py에서 분리됨. _SectionBuilderMixin은 그 자체로는 동작하지 않고,
ReportWizardView가 이 믹스인을 상속해 self.xxx 위젯 속성들을 만들어 붙인다.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
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
        self.education_header = SectionHeader(9, "안전교육")
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

        form_col.addWidget(QLabel("교육장소"))
        self.education_location_input = QLineEdit()
        self.education_location_input.setPlaceholderText("예: 현장 사무실")
        form_col.addWidget(self.education_location_input)

        form_col.addWidget(QLabel("교육내용"))
        self.education_content_input = QLineEdit()
        self.education_content_input.setPlaceholderText("예: 추락재해 예방교육")
        form_col.addWidget(self.education_content_input)

        form_col.addWidget(QLabel("교육자료"))
        self.education_material_input = QLineEdit()
        self.education_material_input.setPlaceholderText("예: 안전보건표지판")
        form_col.addWidget(self.education_material_input)

        form_col.addStretch()
        row.addLayout(form_col)
        row.addStretch()
        row_widget = QWidget()
        row_widget.setLayout(row)
        return self._card(self.education_header, row_widget)

    def _build_findings_section(self) -> QFrame:
        self.findings_header = SectionHeader(7, "지적사항")
        note = QLabel("✦ 사진 업로드 후 설명을 입력하시고 AI추천 버튼을 클릭하시면 관련 지적사항을 AI가 작성합니다")
        note.setStyleSheet("color: #4f46e5; font-size: 12px;")
        self.finding_slots = [_FindingSlot(i) for i in range(1, 5)]
        return self._card(self.findings_header, note, *self.finding_slots)

    def _build_special_note_section(self) -> QFrame:
        header_row = QHBoxLayout()
        badge = QLabel("12")
        badge.setFixedSize(24, 24)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet("background: #4f46e5; color: white; border-radius: 12px; font-weight: 600;")
        header_row.addWidget(badge)
        title = QLabel("무제 •")
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
        self.previous_header = SectionHeader(3, "이전지적사항", required=False)
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
        self.measurement_header = SectionHeader(10, "계측자료")
        with SessionLocal() as session:
            standards = {s.instrument_type: s.standard_criteria for s in session.query(MeasurementStandard).all()}
        self.measurement_rows = [
            _MeasurementRow(name, unit, standards.get(name, "")) for name, unit in MEASUREMENT_INSTRUMENTS
        ]
        return self._card(self.measurement_header, *self.measurement_rows)

    def _build_materials_section(self) -> QFrame:
        self.materials_header = SectionHeader(11, "제공자료")
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

    def _hazard_checkbox_style(self, bold: bool = False) -> str:
        # 체크박스 자체 모양(둥근 표시 등)은 4번 카드(대형사고 위험작업)와 같은 기본 스타일을
        # 그대로 쓴다 — 여기서 커스텀 indicator를 따로 입히지 않는다.
        weight = " font-weight: 600;" if bold else ""
        return f"QCheckBox {{ padding: 2px 4px;{weight} }}"

    def _hazard_column(self, numbers: list[int], factors_by_number: dict[int, tuple[str, list[str]]]) -> QTableWidget:
        """기인물 번호 목록 하나를 표 한 열로 그린다(사망사고 다발 기인물 | 필수 지도사항).

        셀 테두리를 QFrame/QLabel에 CSS border를 일일이 발라 흉내 내던 방식은 칸 사이 경계가
        가끔 어긋나 보이는 문제가 있었다 — `QTableWidget`은 격자선을 own 렌더링 기능으로
        그려주므로 이 문제 자체가 생기지 않는다. 기인물 이름 칸은 그 기인물의 지도사항
        줄 수만큼 `setSpan()`으로 세로 병합한다.
        """
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["사망사고 다발 기인물", "필수 지도사항"])
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
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.setFrameShape(QFrame.Shape.NoFrame)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        total_rows = sum(max(len(factors_by_number[number][1]), 1) for number in numbers)
        table.setRowCount(total_rows)

        row_cursor = 0
        for number in numbers:
            name, lines = factors_by_number[number]
            row_span = max(len(lines), 1)

            checkbox = QCheckBox(f"{number}. {name}")
            checkbox.setStyleSheet(self._hazard_checkbox_style(bold=True))
            table.setCellWidget(row_cursor, 0, checkbox)
            if row_span > 1:
                table.setSpan(row_cursor, 0, row_span, 1)
            self.hazard_checkboxes[number] = checkbox

            line_checkboxes: list[QCheckBox] = []
            for line in lines:
                line_checkbox = QCheckBox(line)
                line_checkbox.setStyleSheet(self._hazard_checkbox_style())
                table.setCellWidget(row_cursor + len(line_checkboxes), 1, line_checkbox)
                line_checkboxes.append(line_checkbox)
            self.hazard_line_checkboxes[number] = line_checkboxes

            row_cursor += row_span

        table.resizeRowsToContents()
        header_height = table.horizontalHeader().height()
        rows_height = sum(table.rowHeight(r) for r in range(total_rows))
        table.setFixedHeight(header_height + rows_height + 4)
        return table

    def _build_hazard_grid(
        self, left_numbers: list[int], right_numbers: list[int], factors_by_number: dict[int, tuple[str, list[str]]]
    ) -> QFrame:
        """왼쪽/오른쪽 표는 각자 항목 수가 달라 원래 높이가 서로 다른데, 그대로 두면 짧은 쪽
        표의 테두리가 긴 쪽보다 먼저 닫혀버려 중간에 네모난 모서리가 튀어나온 것처럼 보인다
        (표 두 개가 옆으로 붙어있을 뿐 하나로 안 보임). 둘 중 더 큰 높이로 맞춰 짧은 쪽
        아래에 빈 여백을 주면 테두리가 같은 줄에서 끝나 자연스럽게 이어져 보인다.
        """
        frame = QFrame()
        outer = QHBoxLayout(frame)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        left_table = self._hazard_column(left_numbers, factors_by_number)
        right_table = self._hazard_column(right_numbers, factors_by_number)
        max_height = max(left_table.height(), right_table.height())
        left_table.setFixedHeight(max_height)
        right_table.setFixedHeight(max_height)
        outer.addWidget(left_table, 0, Qt.AlignmentFlag.AlignTop)
        outer.addWidget(right_table, 0, Qt.AlignmentFlag.AlignTop)
        return frame

    def _build_hazard_factors_section(self) -> QFrame:
        self.hazard_header = SectionHeader(5, "위험성평가 기준 및 12대 기인물 필수 지도사항")
        self.hazard_checkboxes: dict[int, QCheckBox] = {}
        self.hazard_line_checkboxes: dict[int, list[QCheckBox]] = {}
        factors_by_number = {number: (name, lines) for number, name, lines in FIXED_HAZARD_FACTORS}

        sub1 = QLabel("5-1. 사망사고 다발 12대 기인물과 필수 지도사항")
        sub1.setStyleSheet("font-size: 13px; font-weight: 600; margin-top: 4px;")
        main_grid_widget = self._build_hazard_grid([1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12], factors_by_number)

        sub2 = QLabel("5-2. 기타사항")
        sub2.setStyleSheet("font-size: 13px; font-weight: 600; margin-top: 8px;")
        misc_grid_widget = self._build_hazard_grid([13, 15, 17], [14, 16], factors_by_number)

        note = QLabel("1회차에 체크하면 다음 회차부터 자동으로 동일하게 적용됩니다.")
        note.setStyleSheet("color: #9ca3af; font-size: 11px;")

        # 5-3. 건설기계장비·위험기계기구·유해위험물질 안전조치 평가 — 실제 문서에서 12대
        # 기인물 표 바로 뒤에 번호 없이 이어지는 구조라 별도 카드로 안 만들고 여기 이어붙인다
        # (_SectionBuilderMixin2에 정의됨, ReportWizardView가 두 mixin을 함께 상속하므로
        # self로 바로 접근된다).
        equipment_widgets = self._build_equipment_check_widgets()

        return self._card(
            self.hazard_header, sub1, main_grid_widget, sub2, misc_grid_widget, *equipment_widgets, note
        )

    def _apply_hazard_checks(self, checked_ids: set[str]) -> None:
        """`hazard_factor_checks`(JSON 문자열 목록, "N"=기인물 자체, "N-M"=지도사항 M번째 줄)를
        체크박스 상태로 반영한다. 새 회차 초기화/기존 보고서 불러오기 둘 다 이 메서드를 쓴다."""
        for number, checkbox in self.hazard_checkboxes.items():
            checkbox.setChecked(str(number) in checked_ids)
        for number, line_checkboxes in self.hazard_line_checkboxes.items():
            for line_index, line_checkbox in enumerate(line_checkboxes):
                line_checkbox.setChecked(f"{number}-{line_index}" in checked_ids)

    def _build_process_section(self) -> QFrame:
        self.process_header = SectionHeader(8, "향후 진행공정 유해·위험 요인 파악 및 대책")
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
