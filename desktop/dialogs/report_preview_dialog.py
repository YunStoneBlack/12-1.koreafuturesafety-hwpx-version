"""보고서 미리보기 모달 — 왼쪽에 실제 PDF 렌더링 결과, 오른쪽에 텍스트 항목 수정 폼.

실제 사이트는 미리보기 생성 횟수에 제한(5회)이 있지만, 우리는 그런 제약을 둘 이유가
없어 누를 때마다 새로 렌더링한다. 편집 필드는 이 다이얼로그 자체가 들고 있지 않고
ReportWizardView의 위젯 값을 그대로 읽고 쓴다 — "이 내용으로 PDF 재생성"을 누르면
다이얼로그의 값을 마법사 위젯에 되돌려 쓴 뒤 마법사의 저장 로직(`_save`)을 그대로
호출하므로, 저장 경로가 두 군데로 갈라져 데이터가 어긋나는 일이 없다.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.thumbnail_generator import render_pdf_pages


def _section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-weight: 700; font-size: 13px;")
    return label


class ReportPreviewDialog(QDialog):
    def __init__(self, wizard_view, parent=None):
        super().__init__(parent or wizard_view)
        self._wizard = wizard_view
        self.setWindowTitle("보고서 미리보기")
        self.resize(1400, 880)
        self._finding_rows: list[dict] = []
        self._previous_rows: list[dict] = []
        self._build_ui()
        self._load_from_wizard()
        self._regenerate()

    # ---- UI ----

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        title = QLabel("보고서 미리보기")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        subtitle = QLabel("실제 PDF로 렌더링된 결과입니다. 우측에서 텍스트만 수정할 수 있습니다.")
        subtitle.setStyleSheet("color: #6b7280; font-size: 12px;")
        root.addWidget(title)
        root.addWidget(subtitle)

        body = QHBoxLayout()
        body.addWidget(self._build_left_panel(), stretch=7)
        body.addWidget(self._build_right_panel(), stretch=4)
        root.addLayout(body, stretch=1)

        bottom = QHBoxLayout()
        bottom.addStretch()
        edit_btn = QPushButton("수정하기")
        edit_btn.clicked.connect(self.reject)
        regen_btn = QPushButton("📄 이 내용으로 PDF 재생성")
        regen_btn.setStyleSheet(
            "QPushButton { background: #2563eb; color: white; padding: 10px 20px; "
            "border-radius: 6px; font-weight: 600; }"
        )
        regen_btn.clicked.connect(self._regenerate_and_export)
        bottom.addWidget(edit_btn)
        bottom.addWidget(regen_btn)
        root.addLayout(bottom)

    def _build_left_panel(self) -> QWidget:
        left_widget = QWidget()
        left_col = QVBoxLayout(left_widget)
        left_col.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        header.addWidget(QLabel("실제 출력 미리보기"))
        header.addStretch()
        refresh_btn = QPushButton("↻ 미리보기 갱신")
        refresh_btn.clicked.connect(self._regenerate)
        header.addWidget(refresh_btn)
        left_col.addLayout(header)

        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setStyleSheet("QScrollArea { background: #f3f4f6; border: 1px solid #e5e7eb; }")
        self.preview_container = QWidget()
        self.preview_layout = QVBoxLayout(self.preview_container)
        self.preview_layout.setContentsMargins(12, 12, 12, 12)
        self.preview_layout.setSpacing(12)
        self.preview_scroll.setWidget(self.preview_container)
        left_col.addWidget(self.preview_scroll, stretch=1)

        return left_widget

    def _build_right_panel(self) -> QWidget:
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_content = QWidget()
        self.right_layout = QVBoxLayout(right_content)
        self.right_layout.setSpacing(14)

        info_frame = QFrame()
        info_frame.setStyleSheet("QFrame { background: #f9fafb; border-radius: 8px; }")
        info_layout = QHBoxLayout(info_frame)
        self.info_labels: dict[str, QLabel] = {}
        for key, caption in (("site", "현장명"), ("visit", "회차"), ("date", "지도일"), ("progress", "공정률")):
            col = QVBoxLayout()
            cap = QLabel(caption)
            cap.setStyleSheet("color: #9ca3af; font-size: 11px;")
            value = QLabel("-")
            value.setStyleSheet("font-weight: 600;")
            self.info_labels[key] = value
            col.addWidget(cap)
            col.addWidget(value)
            info_layout.addLayout(col)
        self.right_layout.addWidget(info_frame)

        self.right_layout.addWidget(_section_title("기타 특이사항"))
        self.note_edit = QTextEdit()
        self.note_edit.setFixedHeight(80)
        self.right_layout.addWidget(self.note_edit)

        self.right_layout.addWidget(_section_title("안전교육 — 참석인원"))
        self.attendee_edit = QSpinBox()
        self.attendee_edit.setRange(0, 999)
        self.attendee_edit.setSuffix("명")
        self.right_layout.addWidget(self.attendee_edit)

        self.findings_title_label = _section_title("지적사항 (0건)")
        self.right_layout.addWidget(self.findings_title_label)
        self.findings_container = QVBoxLayout()
        self.right_layout.addLayout(self.findings_container)

        self.previous_title_label = _section_title("이전지적사항 (0건)")
        self.right_layout.addWidget(self.previous_title_label)
        self.previous_container = QVBoxLayout()
        self.right_layout.addLayout(self.previous_container)

        self.right_layout.addWidget(_section_title("제공자료"))
        self.materials_container = QVBoxLayout()
        self.right_layout.addLayout(self.materials_container)

        self.right_layout.addStretch()
        right_scroll.setWidget(right_content)
        return right_scroll

    # ---- 데이터 ----

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _load_from_wizard(self) -> None:
        wiz = self._wizard
        self.info_labels["site"].setText(wiz.site_name_label.text() or "-")
        self.info_labels["visit"].setText(f"{wiz.visit_no_label.text()}회차")
        self.info_labels["date"].setText(wiz.guidance_date_input.date().toString("yyyy-MM-dd"))
        self.info_labels["progress"].setText(f"{wiz.progress_input.value()}%")

        self.note_edit.setPlainText(wiz.special_note_edit.toPlainText())
        attendee_text = wiz.attendee_input.text().strip()
        self.attendee_edit.setValue(int(attendee_text) if attendee_text.isdigit() else 0)

        self._finding_rows = []
        self._clear_layout(self.findings_container)
        active_findings = [s for s in wiz.finding_slots if s.has_data()]
        self.findings_title_label.setText(f"지적사항 ({len(active_findings)}건)")
        for slot_widget in active_findings:
            row = self._build_finding_row(slot_widget)
            self.findings_container.addWidget(row["widget"])
            self._finding_rows.append(row)

        self._previous_rows = []
        self._clear_layout(self.previous_container)
        active_previous = [s for s in wiz.previous_slots if s.is_active()]
        self.previous_title_label.setText(f"이전지적사항 ({len(active_previous)}건)")
        for slot_widget in active_previous:
            row = self._build_previous_row(slot_widget)
            self.previous_container.addWidget(row["widget"])
            self._previous_rows.append(row)

        self._clear_layout(self.materials_container)
        materials = wiz._selected_materials
        if not materials:
            empty = QLabel("선택된 자료가 없습니다.")
            empty.setStyleSheet("color: #9ca3af;")
            self.materials_container.addWidget(empty)
        for material in materials:
            label = QLabel(f"• {material.title}")
            self.materials_container.addWidget(label)

    def _build_finding_row(self, slot_widget) -> dict:
        card = QFrame()
        card.setStyleSheet("QFrame { background: #fafafa; border: 1px solid #e5e7eb; border-radius: 6px; }")
        layout = QVBoxLayout(card)
        title_edit = QLineEdit(slot_widget.title_input.text())
        content_edit = QTextEdit()
        content_edit.setPlainText(slot_widget.content_edit.toPlainText())
        content_edit.setFixedHeight(60)
        law_edit = QLineEdit(slot_widget.law_input.text())
        law_edit.setPlaceholderText("관련 법령")
        layout.addWidget(title_edit)
        layout.addWidget(content_edit)
        layout.addWidget(law_edit)
        return {"widget": card, "slot": slot_widget, "title": title_edit, "content": content_edit, "law": law_edit}

    def _build_previous_row(self, slot_widget) -> dict:
        card = QFrame()
        card.setStyleSheet("QFrame { background: #fafafa; border: 1px solid #e5e7eb; border-radius: 6px; }")
        layout = QVBoxLayout(card)
        title_edit = QLineEdit(slot_widget.title_input.text())
        content_edit = QTextEdit()
        content_edit.setPlainText(slot_widget.content_edit.toPlainText())
        content_edit.setFixedHeight(50)
        action_row = QHBoxLayout()
        action_row.addWidget(QLabel("조치 결과"))
        action_edit = QLineEdit(slot_widget.action_input.text())
        action_row.addWidget(action_edit)
        layout.addWidget(title_edit)
        layout.addWidget(content_edit)
        layout.addLayout(action_row)
        return {"widget": card, "slot": slot_widget, "title": title_edit, "content": content_edit, "action": action_edit}

    # ---- 재생성 ----

    def _sync_edits_to_wizard(self) -> None:
        for row in self._finding_rows:
            row["slot"].title_input.setText(row["title"].text())
            row["slot"].content_edit.setPlainText(row["content"].toPlainText())
            row["slot"].law_input.setText(row["law"].text())
        for row in self._previous_rows:
            row["slot"].title_input.setText(row["title"].text())
            row["slot"].content_edit.setPlainText(row["content"].toPlainText())
            row["slot"].action_input.setText(row["action"].text())
        self._wizard.special_note_edit.setPlainText(self.note_edit.toPlainText())
        self._wizard.attendee_input.setText(str(self.attendee_edit.value()))

    def _regenerate(self) -> None:
        """상단 "미리보기 갱신" — 편집 내용을 저장하고 왼쪽 렌더링만 새로 만든다."""
        self._sync_edits_to_wizard()
        self._wizard._save(navigate=False)
        if not self._wizard._report_id:
            return
        self._render_preview()

    def _regenerate_and_export(self) -> None:
        """하단 "이 내용으로 PDF 재생성" — 미리보기를 갱신하고, 사용자가 고른 위치에도
        PDF를 저장한다(파일명 기본값: "{현장명}_{회차}회차.pdf")."""
        self._sync_edits_to_wizard()
        self._wizard._save(navigate=False)
        if not self._wizard._report_id:
            return
        self._render_preview()
        self._wizard._export_pdf_as()

    def _render_preview(self) -> None:
        self._clear_layout(self.preview_layout)
        try:
            pdf_path = self._wizard._build_and_store_pdf(self._wizard._report_id)
            # 좌측 패널 실제 폭(전체 7:4 비율 중 좌측 몫)에 맞춰 렌더링해서 스크롤 없이
            # 옆으로 잘리지 않게 한다. 다이얼로그가 아직 화면에 그려지기 전(생성 직후)에는
            # 자식 위젯의 viewport 폭이 레이아웃 계산 전이라 신뢰할 수 없어서, resize()로
            # 바로 반영되는 다이얼로그 자체 폭에서 역산한다.
            viewport_width = self.preview_scroll.viewport().width()
            if viewport_width < 400:
                viewport_width = int(self.width() * 7 / 11) - 60
            render_width = max(480, viewport_width - 30)
            pages = render_pdf_pages(pdf_path, width=render_width)
        except Exception as e:  # noqa: BLE001 - 사용자에게 그대로 보여줄 에러 메시지
            err = QLabel(f"미리보기를 만들지 못했습니다: {e}")
            err.setStyleSheet("color: #dc2626;")
            err.setWordWrap(True)
            self.preview_layout.addWidget(err)
            return

        if not pages:
            self.preview_layout.addWidget(QLabel("미리보기를 표시할 수 없습니다."))
            return

        for png_bytes in pages:
            pixmap = QPixmap()
            pixmap.loadFromData(png_bytes)
            page_label = QLabel()
            page_label.setPixmap(pixmap)
            page_label.setStyleSheet("background: white; border: 1px solid #d1d5db;")
            self.preview_layout.addWidget(page_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.preview_layout.addStretch()
