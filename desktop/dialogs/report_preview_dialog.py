"""보고서 미리보기 모달 — 실제 PDF 렌더링 결과를 전체 화면에 보여준다.

실제 사이트는 미리보기 생성 횟수에 제한(5회)이 있지만, 우리는 그런 제약을 둘 이유가
없어 누를 때마다 새로 렌더링한다. 텍스트 수정은 마법사 화면에서 하고, 이 다이얼로그는
"실제로 어떻게 나오는지" 확인 + 최종 산출물(.hwpx/.pdf) 생성 용도다(사용자 요청으로
텍스트 편집 폼은 제거함 — 미리보기 화면만 보이게).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.thumbnail_generator import render_pdf_pages
from desktop.widgets.fake_progress_bar import FakeProgressBar
from desktop.workers.ai_worker import AIWorker, with_com


class ReportPreviewDialog(QDialog):
    def __init__(self, wizard_view, parent=None):
        super().__init__(parent or wizard_view)
        self._wizard = wizard_view
        self.setWindowTitle("보고서 미리보기")
        self.resize(1400, 880)
        self._preview_worker: AIWorker | None = None
        self._build_ui()
        self._load_from_wizard()
        self._regenerate()

    # ---- UI ----

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        title = QLabel("보고서 미리보기")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        subtitle = QLabel("실제 PDF로 렌더링된 결과입니다.")
        subtitle.setStyleSheet("color: #6b7280; font-size: 12px;")
        root.addWidget(title)
        root.addWidget(subtitle)

        root.addWidget(self._build_info_bar())
        root.addWidget(self._build_preview_panel(), stretch=1)

        bottom = QHBoxLayout()
        bottom.addStretch()
        # 세 버튼 다 "PDF 생성"과 똑같은 디자인(크기·글자 크기·색)으로 통일한다(사용자 요청).
        # `:pressed`가 없으면 커스텀 스타일시트가 Qt 기본 눌림 효과까지 덮어써서 클릭해도
        # 아무 반응이 없어 보인다("타격감이 없다", 사용자 피드백 2026-09-11) — 눌렀을 때
        # 더 진한 색으로 바뀌게 해서 클릭이 실제로 먹혔다는 걸 바로 알 수 있게 한다.
        _button_style = (
            "QPushButton { background: #2563eb; color: white; padding: 10px 20px; "
            "border-radius: 6px; font-weight: 600; }"
            "QPushButton:pressed { background: #1e40af; }"
            "QPushButton:disabled { background: #93c5fd; }"
        )
        self.edit_btn = QPushButton("수정하기")
        self.edit_btn.setStyleSheet(_button_style)
        self.edit_btn.clicked.connect(self.reject)
        self.hwp_btn = QPushButton("한글 파일 생성")
        self.hwp_btn.setStyleSheet(_button_style)
        self.hwp_btn.clicked.connect(self._regenerate_and_export_hwp)
        self.pdf_btn = QPushButton("PDF 생성")
        self.pdf_btn.setStyleSheet(_button_style)
        self.pdf_btn.clicked.connect(self._regenerate_and_export_pdf)
        bottom.addWidget(self.edit_btn)
        bottom.addWidget(self.hwp_btn)
        bottom.addWidget(self.pdf_btn)
        root.addLayout(bottom)

    def _build_info_bar(self) -> QFrame:
        """현장명·회차·지도일·공정률 — 예전엔 우측 편집 패널 안에 있었는데, 편집 폼을
        없애면서(사용자 요청) 미리보기 위쪽으로 옮겨왔다."""
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
        return info_frame

    def _build_preview_panel(self) -> QWidget:
        panel = QWidget()
        col = QVBoxLayout(panel)
        col.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        header.addWidget(QLabel("실제 출력 미리보기"))
        header.addStretch()
        self.refresh_btn = QPushButton("↻ 미리보기 갱신")
        self.refresh_btn.clicked.connect(self._regenerate)
        header.addWidget(self.refresh_btn)
        col.addLayout(header)

        self.progress_bar = FakeProgressBar()
        col.addWidget(self.progress_bar)

        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setStyleSheet("QScrollArea { background: #f3f4f6; border: 1px solid #e5e7eb; }")
        self.preview_container = QWidget()
        self.preview_layout = QVBoxLayout(self.preview_container)
        self.preview_layout.setContentsMargins(12, 12, 12, 12)
        self.preview_layout.setSpacing(12)
        self.preview_scroll.setWidget(self.preview_container)
        col.addWidget(self.preview_scroll, stretch=1)

        return panel

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
        self.info_labels["visit"].setText(f"{wiz.visit_no_input.value()}회차")
        self.info_labels["date"].setText(wiz.guidance_date_input.date().toString("yyyy-MM-dd"))
        self.info_labels["progress"].setText(f"{wiz.progress_input.value()}%")

    # ---- 재생성 ----

    def _regenerate(self) -> None:
        """상단 "미리보기 갱신" — 마법사에 이미 저장된 내용 그대로 왼쪽 렌더링만 새로 만든다."""
        self._wizard._save(navigate=False)
        if not self._wizard._report_id:
            return
        self._render_preview()

    def refresh_from_wizard(self) -> None:
        """마법사의 "저장" 버튼에서 호출 — 비모달 미리보기를 열어둔 채로 마법사 내용을
        고치고 저장하면, 이 창도 다시 "미리보기 갱신"을 누를 필요 없이 최신 내용으로
        같이 갱신되게 한다(사용자 요청). 호출 시점에 마법사가 이미 저장을 마친 상태이므로
        `_regenerate()`처럼 다시 저장하지 않고 정보 표시줄 + 렌더링만 새로고침한다."""
        if not self._wizard._report_id:
            return
        self._load_from_wizard()
        self._render_preview()

    def _regenerate_and_export_pdf(self) -> None:
        """하단 "PDF 생성" — 미리보기를 갱신한 뒤(완료되면 이어서) 사용자가 고른 위치에도
        PDF를 저장한다(파일명 기본값: "{현장명}_{회차}회차.pdf")."""
        self._wizard._save(navigate=False)
        if not self._wizard._report_id:
            return

        def _start_export():
            self._set_busy(True)  # 내보내기 단계도 계속 "작업 중"으로 표시(연속 클릭 방지)
            self.progress_bar.start()

            def _on_finished(path):
                self._set_busy(False)
                self.progress_bar.finish() if path else self.progress_bar.reset_hidden()

            self._wizard._export_pdf_as(on_finished=_on_finished)

        self._render_preview(on_done=_start_export)

    def _regenerate_and_export_hwp(self) -> None:
        """하단 "한글 파일 생성" — 사용자가 고른 위치에 실제 서식 그대로의 .hwpx 파일을
        저장한다(COM 없는 신규 엔진, Sub-phase 19).

        예전엔 `_regenerate_and_export_pdf`와 똑같이 왼쪽 미리보기(PDF 렌더링, 한글 COM
        자동화 필요)부터 갱신한 뒤 그게 성공해야만 저장 단계로 넘어갔다 — 그런데 실제
        파일 저장(`_export_hwp_as` → `build_report_hwpx`)은 COM이 전혀 필요 없는 순수
        파이썬 엔진이라, 이렇게 묶어두면 그 PC의 한글 COM 자동화(`hwp.open()`)가 실패할
        때 "한글 파일 생성"까지 덩달아 막혀버린다 — 실사용 배포판에서 미리보기와 한글파일
        생성이 완전히 똑같은 에러로 동시에 실패하는 걸로 발견(Sub-phase 20 후속). COM
        문제와 무관하게 최소한 .hwpx 파일은 받을 수 있도록 미리보기 갱신 없이 바로
        저장을 시도한다."""
        self._wizard._save(navigate=False)
        if not self._wizard._report_id:
            return

        self._set_busy(True)
        self.progress_bar.start()

        def _on_finished(path):
            self._set_busy(False)
            self.progress_bar.finish() if path else self.progress_bar.reset_hidden()

        self._wizard._export_hwp_as(on_finished=_on_finished)

    def _set_busy(self, busy: bool) -> None:
        for btn in (self.refresh_btn, self.hwp_btn, self.pdf_btn):
            btn.setEnabled(not busy)

    def _render_preview(self, on_done=None) -> None:
        """PDF 산출물을 만들어 패널에 렌더링한다.

        한글 자동화를 거치는 산출물 생성이 몇 초 걸려서(실측 약 8초 — 실제 서식과 100%
        일치시키려고 reportlab 대신 한글 템플릿→PDF 변환 경로를 쓰기 때문에 생기는 지연,
        `core/report_builder_hwp.py` 참고) 백그라운드에서 돌려 화면이 멈춘 것처럼 보이지
        않게 한다. `on_done`은 성공적으로 렌더링까지 끝난 뒤 이어서 할 작업(내보내기 등)이
        있을 때 쓴다.
        """
        self._clear_layout(self.preview_layout)
        loading = QLabel("실제 서식으로 만드는 중입니다... (몇 초 걸릴 수 있습니다)")
        loading.setStyleSheet("color: #6b7280;")
        self.preview_layout.addWidget(loading)
        self._set_busy(True)
        self.progress_bar.start()

        report_id = self._wizard._report_id
        self._preview_worker = AIWorker(with_com(lambda: self._wizard._build_and_store_pdf(report_id)))
        self._preview_worker.finished_ok.connect(lambda path: self._on_preview_built(path, on_done))
        self._preview_worker.finished_error.connect(self._on_preview_error)
        self._preview_worker.start()

    def _on_preview_error(self, message: str) -> None:
        self._set_busy(False)
        self.progress_bar.reset_hidden()
        self._clear_layout(self.preview_layout)
        err = QLabel(f"미리보기를 만들지 못했습니다: {message}")
        err.setStyleSheet("color: #dc2626;")
        err.setWordWrap(True)
        self.preview_layout.addWidget(err)

    def _on_preview_built(self, pdf_path, on_done) -> None:
        self._set_busy(False)
        self.progress_bar.finish()
        self._clear_layout(self.preview_layout)
        try:
            # 패널 실제 폭에 맞춰 렌더링해서 스크롤 없이 옆으로 잘리지 않게 한다. 다이얼로그가
            # 아직 화면에 그려지기 전(생성 직후)에는 자식 위젯의 viewport 폭이 레이아웃 계산
            # 전이라 신뢰할 수 없어서, resize()로 바로 반영되는 다이얼로그 자체 폭에서 역산한다.
            viewport_width = self.preview_scroll.viewport().width()
            if viewport_width < 400:
                viewport_width = self.width() - 60
            render_width = max(480, viewport_width - 30)
            pages = render_pdf_pages(pdf_path, width=render_width)
        except Exception as e:  # noqa: BLE001 - 사용자에게 그대로 보여줄 에러 메시지
            self._on_preview_error(str(e))
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

        if on_done:
            on_done()
