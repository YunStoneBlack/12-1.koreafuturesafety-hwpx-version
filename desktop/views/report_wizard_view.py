"""보고서 작성 마법사 — 9단계(전경/안전교육/지적사항/특이사항/이전지적사항/계측자료/제공자료/기인물/진행공정).

화면 조립(1~9번 섹션 빌더)은 report_wizard_sections._SectionBuilderMixin,
저장/생성 로직은 report_wizard_save._SaveGenerateMixin, 기존 보고서 불러오기는
report_wizard_load._LoadReportMixin(691줄을 넘겨 분리, 2026-09-08), 각 섹션의 "한 칸"
위젯들은 desktop/widgets/report_wizard_slots.py로 분리되어 있다. 이 파일은 그 조각들을
엮어 화면 진입점(`load_for_site`)과 AI 액션 트리거만 담당한다.
"""

from __future__ import annotations

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
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
from core.thumbnail_generator import resolve_material_path
from core.vision_analyzer import count_people
from desktop.dialogs.material_picker_dialog import ClickableThumb, MaterialPickerDialog, MaterialPreviewDialog
from desktop.views.report_wizard_load import _DEFAULT_EDUCATION_MATERIAL, _LoadReportMixin
from desktop.views.report_wizard_sections import _SectionBuilderMixin
from desktop.views.report_wizard_sections2 import _SectionBuilderMixin2
from desktop.views.report_wizard_sections3 import _SectionBuilderMixin3
from desktop.views.report_wizard_save import _SaveGenerateMixin
from desktop.widgets.cursors import zoom_cursor
from desktop.workers.ai_worker import AIWorker


class ReportWizardView(
    QWidget, _SectionBuilderMixin, _SectionBuilderMixin2, _SectionBuilderMixin3, _SaveGenerateMixin, _LoadReportMixin
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
        self._preview_dialog = None  # ReportPreviewDialog | None — 비모달로 띄운 미리보기 창
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
        # 회차는 자동 계산된 값을 기본으로 보여주되, 실제로는 수정 가능해야 한다(사용자 요청,
        # 2026-09-17) — 예전엔 자동생성 값을 못 믿을 이유가 없다고 보고 읽기전용으로 잠갔지만,
        # 회차가 꼬인 현장(예: 다른 플랫폼에서 이미 진행하던 현장을 이 앱으로 옮겨온 경우)을
        # 직접 고칠 방법이 없었다.
        self.visit_no_input = QSpinBox()
        self.visit_no_input.setRange(1, 999)
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
        fields_row.addWidget(QLabel("회차"))
        fields_row.addWidget(self.visit_no_input)
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
        content_layout.addWidget(self._build_overview_section())
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
        # `:pressed`가 없으면 클릭해도 색이 안 바뀌어 "타격감이 없다"는 피드백을 받았다
        # (2026-09-11) — 눌렀을 때 더 진한 색으로 바뀌게 한다.
        _bottom_button_style = (
            "QPushButton { background: #4f46e5; color: white; padding: 10px 24px; border-radius: 6px; }"
            "QPushButton:pressed { background: #3730a3; }"
            "QPushButton:disabled { background: #c7c7c7; }"
        )
        save_btn = QPushButton("저장")
        save_btn.setStyleSheet(_bottom_button_style)
        save_btn.clicked.connect(self._on_save_button_clicked)
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
            self._apply_management_no_editability(site.management_no if site else "")

            # 현장책임자 성명/통보방법/서명은 회차마다 새로 입력할 이유가 없는 값이라,
            # 이 현장의 마지막 보고서에 저장된 값을 신규 보고서 기본값으로 그대로 승계한다
            # (수정은 그대로 가능, 사용자 요청 2026-09-17) — 아직 이 현장의 첫 보고서라면
            # (이 앱에 다른 플랫폼에서 이미 진행하던 현장을 새로 등록하는 경우도 포함) 승계할
            # 이전 회차가 없으므로 예전처럼 현장 정보의 관리자명만 기본값으로 보여준다.
            last_report = existing_reports[-1] if existing_reports else None
            self.notify_signee_input.setText(
                (last_report.notify_signee_name if last_report and last_report.notify_signee_name else None)
                or (site.manager_name if site else "")
            )
            if last_report and last_report.notify_signature_path:
                self.notify_signature_pad.load_existing(last_report.notify_signature_path)
                self._set_notify_signature_status(True)
            else:
                self.notify_signature_pad.clear_signature()
                self._set_notify_signature_status(False)
            self.set_notification_method(last_report.notification_method if last_report else "")
            self._refresh_signoff_previews(site.assigned_staff_id if site else None)

            self.misc_overwork_check.setChecked(False)
            self.misc_no_photo_check.setChecked(False)
            self.misc_other_check.setChecked(False)
            self.misc_other_input.clear()
            self.accident_yes_check.setChecked(False)
            self.accident_no_check.setChecked(True)
            self.accident_content_input.clear()

            if existing_reports and existing_reports[-1].guidance_date:
                self.prev_date_none_check.setChecked(False)
                self.prev_date_input.setDate(QDate(existing_reports[-1].guidance_date))
            else:
                self.prev_date_none_check.setChecked(True)
            self._reconcile_previous_findings(session, site_id, next_visit_no, existing_report=None)
            self.previous_header.set_checked(False)

            self._apply_hazard_checks(set(site.hazard_factor_checks or []) if site else set())

            # 공정명만 승계한다 — 사진·유해위험요인·예방대책은 매 회차 현장 상태를 새로
            # 찍은 사진으로 AI가 다시 작성해야 하는 값이라 지난 회차 것을 그대로 승계하지
            # 않는다(save 쪽 SiteProcessDefault 기록도 이름만 담음, Sub-phase 20).
            process_defaults = site.process_defaults if site else []
            for process_slot in self.process_slots:
                process_slot.reset()
            for process_slot, default in zip(self.process_slots, process_defaults):
                process_slot.name_input.setText(default.process_name)

            # 8번(향후 진행공정)과 달리 현장 단위 기본값 승계는 없다 — "현재 진행중인 공정"은
            # 회차마다 실제로 바뀌는 게 자연스러워서, 지난 회차 값을 자동으로 다시 채우면
            # 오히려 오해를 살 수 있다(의도적 설계).
            for process_slot in self.current_process_slots:
                process_slot.reset()

            if report_id:
                report = session.get(Report, report_id)
                if report:
                    self._load_existing_report(report, session)

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
        # 매번 똑같이 입력하는 값이라 기본값으로 미리 채워둔다(수정 가능, 사용자 요청,
        # 2026-09-11) — 실제로 바꿀 일은 거의 없지만 혹시 몰라 잠그지는 않는다.
        self.education_material_input.setText(_DEFAULT_EDUCATION_MATERIAL)
        self.education_header.set_checked(False)

        for slot_widget in self.overview_photo_slots:
            slot_widget.clear()
            slot_widget.set_active(False)
        self._update_overview_photo_add_btn()
        for slot_widget in self.inspection_photo_slots:
            slot_widget.clear()
            slot_widget.set_active(False)
        self._update_inspection_photo_add_btn()
        self.overview_header.set_checked(False)

        for slot_widget in self.finding_slots:
            slot_widget.clear()
            slot_widget.set_active(False)
        self.findings_header.set_checked(False)

        self.special_note_edit.clear()

        for row in self.measurement_rows:
            row.photo.clear_photo()
            row.value_input.clear()
            row.set_verdict("")
            row.action_input.clear()
        self.measurement_header.set_checked(False)

        self._selected_materials = []
        self._update_materials_summary()
        self._sync_education_content_from_materials()
        self.materials_header.set_checked(False)

        for slot_widget in self.previous_slots:
            slot_widget.clear()
        self.previous_header.set_checked(False)

        self.hazard_header.set_checked(False)
        self.current_process_header.set_checked(False)
        self.process_header.set_checked(False)

    def _on_prev_date_none_toggled(self, checked: bool) -> None:
        self.prev_date_input.setEnabled(not checked)

    def _apply_management_no_editability(self, site_management_no: str) -> None:
        """관리번호는 현장 단위로 공유되는 값이지만(모든 회차에 같은 값) 어느 회차에서든
        수정할 수 있다(사용자 요청) — 이전엔 1회차에서만 입력 가능하고 이후 회차는
        읽기전용이었는데, 잘못 입력했거나 나중에 바뀌어도 고칠 방법이 없었다. 여기서
        수정하면 저장 시(`report_wizard_save.py`) site.management_no가 갱신되어 이
        현장의 모든 회차에 반영된다."""
        self.management_no_input.setText(site_management_no)
        self.management_no_input.setReadOnly(False)
        self.management_no_auto_btn.setVisible(True)
        self.management_no_hint.setText("이 현장의 관리번호 — 모든 회차에 공통으로 쓰이며 언제든 수정할 수 있습니다.")

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
        self._sync_education_content_from_materials()
        if not self._selected_materials:
            QMessageBox.information(self, "추천 결과 없음", "지적사항과 관련된 자료를 찾지 못했습니다. '모든자료 보기'에서 직접 선택하세요.")

    def _open_material_picker(self) -> None:
        already = [m.id for m in self._selected_materials]
        dialog = MaterialPickerDialog(already_selected=already, parent=self)
        if dialog.exec():
            self._selected_materials = dialog.get_selected_materials()
            self._update_materials_summary()
            self._sync_education_content_from_materials()

    def _sync_education_content_from_materials(self) -> None:
        """10-1 "교육내용"에 11번에서 고른 제공자료 제목을 자동으로 반영한다(쉼표로 나열,
        사용자 요청 2026-09-11) — 마법사에서 자료를 추가/삭제/AI추천할 때마다 다시 불러
        항상 최신 선택과 일치하게 맞춘다. 그래도 일반 입력칸이라 사용자가 직접 고쳐 쓸 수
        있다. 기존 보고서를 불러올 때(`report_wizard_load.py`)는 이미 저장된 교육내용
        값이 있으므로 이 함수를 부르지 않는다 — 안 그러면 사용자가 직접 다르게 써둔 내용을
        자료 제목으로 덮어써버린다.
        """
        self.education_content_input.setText(", ".join(m.title for m in self._selected_materials))

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
            thumb_path = resolve_material_path(material.thumbnail_path)
            pixmap = QPixmap(str(thumb_path)) if thumb_path else QPixmap()
            if thumb_path and not pixmap.isNull():
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

            remove_btn = QPushButton("삭제")
            remove_btn.setStyleSheet(
                "QPushButton { background: #fee2e2; color: #b91c1c; border-radius: 4px; padding: 3px; font-size: 10px; }"
                "QPushButton:hover { background: #fecaca; }"
            )
            remove_btn.clicked.connect(lambda _checked=False, m=material: self._remove_selected_material(m))
            card_layout.addWidget(remove_btn)

            self.materials_preview_row.addWidget(card)
        self.materials_preview_row.addStretch()

    def _remove_selected_material(self, material: MaterialLibrary) -> None:
        self._selected_materials = [m for m in self._selected_materials if m.id != material.id]
        self._update_materials_summary()
        self._sync_education_content_from_materials()
