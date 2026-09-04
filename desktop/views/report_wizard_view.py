"""보고서 작성 마법사 — 9단계(전경/안전교육/지적사항/특이사항/이전지적사항/계측자료/제공자료/기인물/진행공정).

화면 조립(1~9번 섹션 빌더)은 report_wizard_sections._SectionBuilderMixin,
저장/생성 로직은 report_wizard_save._SaveGenerateMixin, 각 섹션의 "한 칸" 위젯들은
desktop/widgets/report_wizard_slots.py로 분리되어 있다. 이 파일은 그 세 조각을 엮어
회차 불러오기/AI 액션 트리거만 담당한다.
"""

from __future__ import annotations

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core import config
from core.db import SessionLocal
from core.material_recommender import recommend_materials
from core.models_db import MaterialLibrary, Report, Site, Staff
from core.text_generator import generate_special_note
from core.vision_analyzer import count_people
from desktop.dialogs.material_picker_dialog import ClickableThumb, MaterialPickerDialog, MaterialPreviewDialog
from desktop.views.report_wizard_sections import _SectionBuilderMixin
from desktop.views.report_wizard_sections2 import _SectionBuilderMixin2
from desktop.views.report_wizard_sections3 import _SectionBuilderMixin3
from desktop.views.report_wizard_save import _SaveGenerateMixin
from desktop.widgets.cursors import zoom_cursor
from desktop.workers.ai_worker import AIWorker


class ReportWizardView(
    QWidget, _SectionBuilderMixin, _SectionBuilderMixin2, _SectionBuilderMixin3, _SaveGenerateMixin
):
    back_requested = pyqtSignal()
    report_saved = pyqtSignal(int)  # site_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._site_id: int | None = None
        self._report_id: int | None = None
        self._people_worker: AIWorker | None = None
        self._note_worker: AIWorker | None = None
        self._export_worker: AIWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        back_btn = QPushButton("← 현장으로")
        back_btn.setFlat(True)
        back_btn.clicked.connect(self.back_requested.emit)

        top_bar = QVBoxLayout()
        top_bar.setContentsMargins(32, 20, 32, 10)
        top_bar.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        header_row = QHBoxLayout()
        self.site_name_label = QLabel("")
        self.site_name_label.setStyleSheet("font-size: 18px; font-weight: 700;")
        header_row.addWidget(self.site_name_label)
        header_row.addStretch()
        header_row.addWidget(QLabel("담당요원"))
        self.staff_combo = QComboBox()
        self.staff_combo.currentIndexChanged.connect(
            lambda: self._refresh_signoff_previews(self.staff_combo.currentData())
        )
        header_row.addWidget(self.staff_combo)
        top_bar.addLayout(header_row)

        fields_row = QHBoxLayout()
        self.guidance_date_input = QDateEdit()
        self.guidance_date_input.setCalendarPopup(True)
        self.guidance_date_input.setDisplayFormat("yyyy-MM-dd")
        self.guidance_date_input.setDate(QDate.currentDate())
        self.visit_no_input = QSpinBox()
        self.visit_no_input.setRange(1, 999)
        self.visit_no_input.setReadOnly(True)
        self.visit_no_input.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.visit_no_input.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.progress_input = QSpinBox()
        self.progress_input.setRange(0, 100)
        self.progress_input.setSuffix("%")
        self.prev_date_input = QDateEdit()
        self.prev_date_input.setCalendarPopup(True)
        self.prev_date_input.setDisplayFormat("yyyy-MM-dd")
        self.prev_date_input.setDate(QDate.currentDate())
        self.prev_date_none_check = QCheckBox("없음")
        self.prev_date_none_check.toggled.connect(self._on_prev_date_none_toggled)

        fields_row.addWidget(QLabel("지도일"))
        fields_row.addWidget(self.guidance_date_input)
        fields_row.addWidget(self.visit_no_input)
        fields_row.addWidget(QLabel("회차"))
        fields_row.addWidget(QLabel("공정률"))
        fields_row.addWidget(self.progress_input)
        fields_row.addWidget(QLabel("이전지도일"))
        fields_row.addWidget(self.prev_date_input)
        fields_row.addWidget(self.prev_date_none_check)
        fields_row.addStretch()
        top_bar.addLayout(fields_row)

        mgmt_row = QHBoxLayout()
        mgmt_row.addWidget(QLabel("관리번호"))
        self.management_no_input = QLineEdit()
        self.management_no_input.setPlaceholderText("예: 2026-0000001")
        self.management_no_input.setFixedWidth(160)
        mgmt_row.addWidget(self.management_no_input)
        self.management_no_auto_btn = QPushButton("자동생성")
        self.management_no_auto_btn.clicked.connect(self._auto_generate_management_no)
        mgmt_row.addWidget(self.management_no_auto_btn)
        self.management_no_hint = QLabel("")
        self.management_no_hint.setStyleSheet("color: #9ca3af; font-size: 11px;")
        mgmt_row.addWidget(self.management_no_hint)
        mgmt_row.addStretch()
        top_bar.addLayout(mgmt_row)

        top_bar_widget = QWidget()
        top_bar_widget.setLayout(top_bar)
        root.addWidget(top_bar_widget)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(32, 10, 32, 24)
        content_layout.setSpacing(16)

        content_layout.addWidget(self._build_signoff_section())
        content_layout.addWidget(self._build_misc_note_section())
        content_layout.addWidget(self._build_previous_findings_section())
        content_layout.addWidget(self._build_major_hazard_work_section())
        content_layout.addWidget(self._build_hazard_factors_section())
        content_layout.addWidget(self._build_current_process_section())
        content_layout.addWidget(self._build_findings_section())
        content_layout.addWidget(self._build_process_section())
        content_layout.addWidget(self._build_support_section())
        content_layout.addWidget(self._build_materials_section())

        special_note_section = self._build_special_note_section()
        special_note_section.setVisible(False)  # 나중에 필요하면 이 줄만 지우면 다시 보임
        content_layout.addWidget(special_note_section)

        content_layout.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll)

        bottom = QVBoxLayout()
        bottom.setContentsMargins(32, 10, 32, 16)

        self.confirm_checkbox = QCheckBox(
            "위 내용에 대한 모든 사항을 확인했습니다. AI가 생성한 자료는 틀린 내용을 포함할 수 있으므로, "
            "보고서 생성 전 반드시 직접 다시 한 번 확인해야 합니다."
        )
        self.confirm_checkbox.toggled.connect(self._on_confirm_toggled)
        bottom.addWidget(self.confirm_checkbox)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        # 저장/미리보기 버튼 디자인을 통일한다(사용자 요청) — 미리보기 쪽 스타일에 맞춘다.
        _bottom_button_style = (
            "QPushButton { background: #4f46e5; color: white; padding: 10px 24px; border-radius: 6px; }"
            "QPushButton:disabled { background: #c7c7c7; }"
        )
        save_btn = QPushButton("저장")
        save_btn.setStyleSheet(_bottom_button_style)
        save_btn.clicked.connect(self._save)
        self.generate_btn = QPushButton("미리보기")
        self.generate_btn.setEnabled(False)
        self.generate_btn.setStyleSheet(_bottom_button_style)
        self.generate_btn.clicked.connect(self._open_preview)
        bottom_row.addWidget(save_btn)
        bottom_row.addWidget(self.generate_btn)
        bottom.addLayout(bottom_row)
        root.addLayout(bottom)

    # ---- 데이터 로딩 ----

    def load_for_site(self, site_id: int, report_id: int | None = None) -> None:
        self._site_id = site_id
        self._report_id = report_id
        self.confirm_checkbox.setChecked(False)
        self._reset_report_fields()

        with SessionLocal() as session:
            site = session.get(Site, site_id)
            self.site_name_label.setText(site.name if site else "")

            self.staff_combo.clear()
            self.staff_combo.addItem("선택 안 함", userData=None)
            for staff in session.query(Staff).filter_by(active=True).all():
                self.staff_combo.addItem(f"{staff.name} ({staff.phone})", userData=staff.id)
            if site and site.assigned_staff_id:
                idx = self.staff_combo.findData(site.assigned_staff_id)
                if idx >= 0:
                    self.staff_combo.setCurrentIndex(idx)

            existing_reports = (
                session.query(Report).filter(Report.site_id == site_id).order_by(Report.visit_no).all()
            )
            next_visit_no = (existing_reports[-1].visit_no + 1) if existing_reports else 1
            self.visit_no_input.setValue(next_visit_no)
            self._apply_management_no_editability(next_visit_no, site.management_no if site else "")

            self.notify_signee_input.setText(site.manager_name if site else "")
            self.notify_signature_pad.clear_signature()
            self._set_notify_signature_status(False)
            self.set_notification_method("")
            self._refresh_signoff_previews(site.assigned_staff_id if site else None)

            self.misc_overwork_check.setChecked(False)
            self.misc_no_photo_check.setChecked(False)
            self.misc_other_check.setChecked(False)
            self.misc_other_input.clear()
            self.accident_yes_check.setChecked(False)
            self.accident_no_check.setChecked(True)
            self.accident_content_input.clear()

            for slot in self.previous_slots:
                slot.set_active(False)
            if existing_reports and existing_reports[-1].guidance_date:
                self.prev_date_none_check.setChecked(False)
                self.prev_date_input.setDate(QDate(existing_reports[-1].guidance_date))
            else:
                self.prev_date_none_check.setChecked(True)
            if existing_reports:
                last = existing_reports[-1]
                for slot, finding in zip(self.previous_slots, last.findings):
                    slot.load_from_finding(finding)
                self.previous_hint_label.setText(
                    "이전 회차 지적사항이 없습니다. 직접 넣으실 항목이 있으면 아래 버튼으로 추가하세요."
                )
                self.previous_header.set_checked(False)
            else:
                self.previous_hint_label.setText("1회차 보고서입니다. 이전 지적사항이 없습니다.")
                self.previous_header.set_checked(False)
            self._update_previous_add_btn()

            self._apply_hazard_checks(set(site.hazard_factor_checks or []) if site else set())

            process_defaults = site.process_defaults if site else []
            for process_slot in self.process_slots:
                process_slot.reset()
            for process_slot, default in zip(self.process_slots, process_defaults):
                process_slot.load_data(
                    {
                        "process_name": default.process_name,
                        "hazard_text": default.hazard_text,
                        "prevention_text": default.prevention_text,
                        "risk_level": default.risk_level,
                    }
                )

            # 8번(향후 진행공정)과 달리 현장 단위 기본값 승계는 없다 — "현재 진행중인 공정"은
            # 회차마다 실제로 바뀌는 게 자연스러워서, 지난 회차 값을 자동으로 다시 채우면
            # 오히려 오해를 살 수 있다(의도적 설계).
            for process_slot in self.current_process_slots:
                process_slot.reset()

            if report_id:
                report = session.get(Report, report_id)
                if report:
                    self._load_existing_report(report)

    def _reset_report_fields(self) -> None:
        """새 보고서(수정이 아닌)를 시작할 때 이전 회차/이전 현장 편집 흔적이 남지 않도록,
        `_load_existing_report()`가 채우는 위젯들을 전부 빈 상태로 되돌린다.

        마법사 위젯이 화면 전환마다 새로 만들어지지 않고 재사용되기 때문에(다른 현장의
        새 보고서를 열어도 같은 인스턴스), 여기서 명시적으로 안 지우면 직전에 열었던
        보고서의 체크박스·텍스트·사진이 그대로 남아있는 채로 보였다(사용자가 실측으로
        확인한 버그) — 결재란처럼 현장 단위로 의도적으로 이어지는 값(서명, 계약 정보 등)은
        건드리지 않는다.
        """
        for checkbox in self.major_hazard_checkboxes:
            checkbox.setChecked(False)
        self.major_hazard_header.set_checked(False)

        for rows in (self.machinery_rows, self.hand_tool_rows, self.hazmat_rows):
            for row in rows:
                row.checkbox.setChecked(False)
                row.set_evaluations([])
        self.equipment_header.set_checked(False)

        self.education_photo.clear_photo()
        self.attendee_input.clear()
        self.education_location_input.clear()
        self.education_content_input.clear()
        self.education_material_input.clear()
        self.education_header.set_checked(False)

        for slot_widget in self.finding_slots:
            slot_widget.clear()
            slot_widget.set_active(False)
        self.findings_header.set_checked(False)

        self.special_note_edit.clear()

        for row in self.measurement_rows:
            row.photo.clear_photo()
            row.value_input.clear()
        self.measurement_header.set_checked(False)

        self._selected_materials = []
        self._update_materials_summary()
        self.materials_header.set_checked(False)

        for slot_widget in self.previous_slots:
            slot_widget.title_input.clear()
            slot_widget.content_edit.clear()
            slot_widget.action_input.setText("조치완료")
            slot_widget.confirm_btn.setChecked(False)
            slot_widget.set_risk_level("")
        self.previous_header.set_checked(False)

        self.hazard_header.set_checked(False)
        self.current_process_header.set_checked(False)
        self.process_header.set_checked(False)

    def _on_prev_date_none_toggled(self, checked: bool) -> None:
        self.prev_date_input.setEnabled(not checked)

    def _apply_management_no_editability(self, visit_no: int, site_management_no: str) -> None:
        """관리번호는 현장 단위로 고정 — 1회차에서만 입력/자동생성 가능, 이후 회차는 읽기전용."""
        self.management_no_input.setText(site_management_no)
        if visit_no <= 1:
            self.management_no_input.setReadOnly(False)
            self.management_no_auto_btn.setVisible(True)
            self.management_no_hint.setText("1회차 관리번호는 이 현장의 모든 회차에 계속 쓰입니다.")
        else:
            self.management_no_input.setReadOnly(True)
            self.management_no_auto_btn.setVisible(False)
            self.management_no_hint.setText("이 현장의 관리번호(1회차에 등록됨)")

    def _auto_generate_management_no(self) -> None:
        year = self.guidance_date_input.date().year()
        prefix = f"{year}-"
        max_seq = 0
        with SessionLocal() as session:
            for (management_no,) in session.query(Site.management_no).all():
                if management_no and management_no.startswith(prefix):
                    suffix = management_no[len(prefix):]
                    if suffix.isdigit():
                        max_seq = max(max_seq, int(suffix))
        self.management_no_input.setText(f"{prefix}{max_seq + 1:07d}")

    def _load_existing_report(self, report: Report) -> None:
        """기존 보고서를 수정 모드로 불러온다 — '새 회차' 기본값을 실제 저장값으로 덮어쓴다."""
        self.visit_no_input.setValue(report.visit_no)
        if report.prev_guidance_date:
            self.prev_date_none_check.setChecked(False)
            self.prev_date_input.setDate(QDate(report.prev_guidance_date))
        else:
            self.prev_date_none_check.setChecked(True)
        self._apply_management_no_editability(
            report.visit_no, report.site.management_no if report.site else ""
        )

        self.set_notification_method(report.notification_method)
        self.notify_signee_input.setText(
            report.notify_signee_name or (report.site.manager_name if report.site else "")
        )
        if report.notify_signature_path:
            self.notify_signature_pad.load_existing(report.notify_signature_path)
            self._set_notify_signature_status(True)
        else:
            self.notify_signature_pad.clear_signature()
            self._set_notify_signature_status(False)
        self._refresh_signoff_previews(report.assigned_staff_id)

        self.misc_overwork_check.setChecked(report.misc_overwork)
        self.misc_no_photo_check.setChecked(report.misc_no_photo)
        self.misc_other_check.setChecked(report.misc_other)
        self.misc_other_input.setText(report.misc_other_text)
        self.accident_yes_check.setChecked(report.accident_status == "유")
        self.accident_no_check.setChecked(report.accident_status == "무")
        self.accident_content_input.setText(report.accident_content)

        if report.guidance_date:
            self.guidance_date_input.setDate(QDate(report.guidance_date.year, report.guidance_date.month, report.guidance_date.day))
        self.progress_input.setValue(report.progress_rate or 0)
        if report.assigned_staff_id:
            idx = self.staff_combo.findData(report.assigned_staff_id)
            if idx >= 0:
                self.staff_combo.setCurrentIndex(idx)

        major_hazard_checked = set(report.major_hazard_work_checks or [])
        for idx, checkbox in enumerate(self.major_hazard_checkboxes):
            checkbox.setChecked(idx in major_hazard_checked)
        self.major_hazard_header.set_checked(report.major_hazard_na)

        for rows, saved in (
            (self.machinery_rows, report.machinery_checks or []),
            (self.hand_tool_rows, report.hand_tool_checks or []),
            (self.hazmat_rows, report.hazmat_checks or []),
        ):
            for row, entry in zip(rows, saved):
                row.checkbox.setChecked(bool(entry.get("checked")))
                row.set_evaluations(entry.get("notes") or [])
        self.equipment_header.set_checked(report.equipment_checks_na)

        for process_slot in self.current_process_slots:
            process_slot.reset()
        current_process_by_slot = {e.slot: e for e in report.current_process_entries}
        for process_slot in self.current_process_slots:
            e = current_process_by_slot.get(process_slot.slot)
            if e:
                process_slot.load_data(
                    {
                        "process_name": e.process_name,
                        "hazard_text": e.hazard_text,
                        "prevention_text": e.prevention_text,
                        "risk_level": e.risk_level,
                    }
                )
        self.current_process_header.set_checked(report.current_process_na)

        if report.safety_education:
            if report.safety_education.photo_path:
                self.education_photo.set_photo(report.safety_education.photo_path)
            self.attendee_input.setText(
                str(report.safety_education.attendee_count) if report.safety_education.attendee_count is not None else ""
            )
            self.education_header.set_checked(report.safety_education.na_flag)
            self.education_location_input.setText(report.safety_education.location)
            self.education_content_input.setText(report.safety_education.content)
            self.education_material_input.setText(report.safety_education.material)

        findings_by_slot = {f.slot: f for f in report.findings}
        for slot_widget in self.finding_slots:
            slot_widget.set_active(False)
        for slot_widget in self.finding_slots:
            f = findings_by_slot.get(slot_widget.slot)
            if not f:
                continue
            slot_widget.set_active(True)
            if f.photo_path:
                slot_widget.photo.set_photo(f.photo_path)
            slot_widget.description_input.setText(f.description)
            slot_widget.title_input.setText(f.title)
            slot_widget.content_edit.setPlainText(f.content)
            slot_widget.law_input.setText(f.law_citation)
            slot_widget.likelihood_buttons.set_value(f.likelihood)
            slot_widget.severity_buttons.set_value(f.severity)
        self._update_finding_add_btn()
        self.findings_header.set_checked(report.findings_na)

        self.special_note_edit.setPlainText(report.special_note)

        for slot in self.previous_slots:
            slot.set_active(False)
        previous_by_slot = {p.slot: p for p in report.previous_findings}
        for slot_widget in self.previous_slots:
            p = previous_by_slot.get(slot_widget.slot)
            if p:
                slot_widget.set_active(True)
                if p.photo_path:
                    slot_widget.photo.set_photo(p.photo_path)
                slot_widget.title_input.setText(p.title)
                slot_widget.content_edit.setPlainText(p.content)
                slot_widget.action_input.setText(p.action_result)
                slot_widget.confirm_btn.setChecked(p.confirmed)
                slot_widget.set_risk_level(p.risk_level)
        self._update_previous_add_btn()
        self.previous_header.set_checked(report.previous_findings_na)

        measurements_by_type = {m.instrument_type: m for m in report.measurements}
        for row in self.measurement_rows:
            m = measurements_by_type.get(row.instrument_type)
            if m:
                if m.photo_path:
                    row.photo.set_photo(m.photo_path)
                row.value_input.setText(m.value)
        self.measurement_header.set_checked(report.measurements_na)

        self._selected_materials = list(
            [pm.material for pm in report.provided_materials if pm.material_id and pm.material]
        )
        self._update_materials_summary()
        self.materials_header.set_checked(report.materials_na)

        self._apply_hazard_checks(set(report.hazard_factor_checks or []))
        self.hazard_header.set_checked(report.hazard_factors_na)

        for process_slot in self.process_slots:
            process_slot.reset()
        process_by_slot = {e.slot: e for e in report.process_entries}
        for process_slot in self.process_slots:
            e = process_by_slot.get(process_slot.slot)
            if e:
                process_slot.load_data(
                    {
                        "process_name": e.process_name,
                        "hazard_text": e.hazard_text,
                        "prevention_text": e.prevention_text,
                        "risk_level": e.risk_level,
                    }
                )
        self.process_header.set_checked(report.process_na)

    # ---- AI 액션 ----

    def _run_count_people(self) -> None:
        if not self.education_photo.photo_path:
            QMessageBox.warning(self, "사진 필요", "먼저 안전교육 사진을 업로드해주세요.")
            return
        if not config.has_api_key():
            QMessageBox.warning(self, "API 키 필요", "'AI 관리' 화면에서 Claude API 키를 먼저 등록하세요.")
            return
        self.count_people_btn.setEnabled(False)
        self.count_people_btn.setText("세는 중...")
        photo_path = self.education_photo.photo_path
        self._people_worker = AIWorker(lambda: count_people(photo_path))
        self._people_worker.finished_ok.connect(self._on_count_people_done)
        self._people_worker.finished_error.connect(self._on_count_people_error)
        self._people_worker.start()

    def _on_count_people_done(self, count: int | None) -> None:
        self.count_people_btn.setEnabled(True)
        self.count_people_btn.setText("✨ AI로 인원 세기")
        if count is None:
            QMessageBox.information(self, "인식 실패", "사진에서 인원을 읽지 못했습니다. 참석인원을 직접 입력해주세요.")
        else:
            self.attendee_input.setText(str(count))

    def _on_count_people_error(self, message: str) -> None:
        self.count_people_btn.setEnabled(True)
        self.count_people_btn.setText("✨ AI로 인원 세기")
        QMessageBox.warning(self, "AI 분석 실패", message)

    def _run_generate_note(self) -> None:
        if not config.has_api_key():
            QMessageBox.warning(self, "API 키 필요", "'AI 관리' 화면에서 Claude API 키를 먼저 등록하세요.")
            return
        findings = [
            {"title": s.title_input.text(), "content": s.content_edit.toPlainText()}
            for s in self.finding_slots
            if s.has_data()
        ]
        self.note_ai_btn.setEnabled(False)
        self.note_ai_btn.setText("작성 중...")
        self._note_worker = AIWorker(lambda: generate_special_note(findings))
        self._note_worker.finished_ok.connect(self._on_note_done)
        self._note_worker.finished_error.connect(self._on_note_error)
        self._note_worker.start()

    def _on_note_done(self, text: str) -> None:
        self.note_ai_btn.setEnabled(True)
        self.note_ai_btn.setText("✨ AI추천")
        self.special_note_edit.setPlainText(text)

    def _on_note_error(self, message: str) -> None:
        self.note_ai_btn.setEnabled(True)
        self.note_ai_btn.setText("✨ AI추천")
        QMessageBox.warning(self, "AI 생성 실패", message)

    def _run_recommend_materials(self) -> None:
        findings = [
            {"title": s.title_input.text(), "content": s.content_edit.toPlainText()}
            for s in self.finding_slots
            if s.has_data()
        ]
        with SessionLocal() as session:
            library_items = session.query(MaterialLibrary).all()
            recommended = recommend_materials(findings, library_items, limit=2)
            self._selected_materials = list(recommended)
        self._update_materials_summary()
        if not self._selected_materials:
            QMessageBox.information(self, "추천 결과 없음", "지적사항과 관련된 자료를 찾지 못했습니다. '모든자료 보기'에서 직접 선택하세요.")

    def _open_material_picker(self) -> None:
        already = [m.id for m in self._selected_materials]
        dialog = MaterialPickerDialog(max_select=2, already_selected=already, parent=self)
        if dialog.exec():
            self._selected_materials = dialog.get_selected_materials()
            self._update_materials_summary()

    def _update_materials_summary(self) -> None:
        while self.materials_preview_row.count():
            item = self.materials_preview_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._selected_materials:
            self.materials_empty_label = QLabel("선택된 자료가 없습니다.")
            self.materials_empty_label.setStyleSheet("color: #9ca3af;")
            self.materials_preview_row.addWidget(self.materials_empty_label)
            self.materials_preview_row.addStretch()
            return

        for material in self._selected_materials:
            card = QFrame()
            card.setFixedWidth(110)
            card.setStyleSheet("QFrame { background: #fafafa; border: 1px solid #e5e7eb; border-radius: 6px; }")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(6, 6, 6, 6)

            thumb = ClickableThumb()
            thumb.setFixedSize(96, 70)
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb.setStyleSheet("background: white; border-radius: 4px;")
            thumb.setCursor(zoom_cursor())
            thumb.clicked.connect(lambda m=material: MaterialPreviewDialog(m, self).exec())
            pixmap = QPixmap(material.thumbnail_path) if material.thumbnail_path else QPixmap()
            if material.thumbnail_path and not pixmap.isNull():
                thumb.setPixmap(
                    pixmap.scaled(96, 70, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                )
            else:
                thumb.setText("📄")
            card_layout.addWidget(thumb)

            title = QLabel(material.title)
            title.setWordWrap(True)
            title.setStyleSheet("font-size: 10px;")
            card_layout.addWidget(title)

            self.materials_preview_row.addWidget(card)
        self.materials_preview_row.addStretch()
