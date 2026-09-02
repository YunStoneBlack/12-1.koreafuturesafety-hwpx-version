"""대시보드(홈) 화면 — 통계 카드, 현장 목록/검색/상태 필터. 실제 사이트 화면 구성을 따른다."""

from __future__ import annotations

import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import func

from core.db import SessionLocal
from core.hangul_match import matches as hangul_matches
from core.models_db import Finding, Report, Site, SiteProcessDefault

_WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]
_STATUS_TABS = ["진행중", "완료", "보류"]
_STATUS_PARTICLE = {"진행중": "인", "완료": "된", "보류": ""}
_SORT_OPTIONS = ["최근 보고서일순 (기본)", "이름순"]

# QLabel도 내부적으로 QFrame이라, 라벨에 스타일시트를 지정하면(색상만 지정해도)
# 부모 카드의 border/background까지 새어 들어온다. 이 파일의 모든 라벨은 이걸 덧붙인다.
_LABEL_RESET = "border: none; background: transparent;"


class _StatCard(QFrame):
    def __init__(self, accent: str, value: str, label: str, sub: str):
        super().__init__()
        self.setStyleSheet(
            f"QFrame {{ background: white; border: 1px solid #e5e7eb; border-left: 4px solid {accent}; "
            f"border-radius: 8px; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        label_widget = QLabel(label)
        label_widget.setStyleSheet(f"color: #6b7280; font-size: 12px; {_LABEL_RESET}")
        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(f"font-size: 24px; font-weight: 700; {_LABEL_RESET}")
        self.sub_label = QLabel(sub)
        self.sub_label.setStyleSheet(f"color: #9ca3af; font-size: 11px; {_LABEL_RESET}")
        layout.addWidget(label_widget)
        layout.addWidget(self.value_label)
        layout.addWidget(self.sub_label)


class _SiteCard(QFrame):
    clicked = pyqtSignal(int)
    continue_requested = pyqtSignal(int, object)  # site_id, report_id(있으면 int, 없으면 None)
    delete_requested = pyqtSignal(int)

    def __init__(self, site: Site, latest_report: Report | None):
        super().__init__()
        self._site_id = site.id
        self._latest_report_id = latest_report.id if latest_report else None
        self.setStyleSheet(
            "QFrame { background: white; border: 1px solid #e5e7eb; border-radius: 8px; }"
            "QFrame:hover { border-color: #4f46e5; }"
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(6)

        top_row = QHBoxLayout()
        name = QLabel(site.name or "(이름 없음)")
        name.setStyleSheet(f"font-size: 14px; font-weight: 600; {_LABEL_RESET}")
        top_row.addWidget(name)
        top_row.addStretch()

        # 마우스를 올렸을 때만 보이는 빠른 작업 버튼 — 실제 사이트의 "임시저장된 보고서"
        # 배너에 있던 "이어서 작성/삭제"를 현장 카드 위에 올렸을 때로 옮겨왔다.
        self.continue_btn = QPushButton("▶ 이어서 작성")
        self.continue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.continue_btn.setStyleSheet(
            "QPushButton { background: #4f46e5; color: white; border-radius: 6px; "
            "padding: 4px 10px; font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background: #4338ca; }"
        )
        self.continue_btn.clicked.connect(
            lambda: self.continue_requested.emit(self._site_id, self._latest_report_id)
        )
        self.delete_btn = QPushButton("🗑")
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_btn.setFixedWidth(28)
        self.delete_btn.setStyleSheet(
            "QPushButton { color: #ef4444; border: 1px solid #fecaca; border-radius: 6px; padding: 4px; }"
            "QPushButton:hover { background: #fef2f2; }"
        )
        self.delete_btn.clicked.connect(lambda: self.delete_requested.emit(self._site_id))
        for btn in (self.continue_btn, self.delete_btn):
            btn.setVisible(False)
            top_row.addWidget(btn)
        outer.addLayout(top_row)

        visit_no = latest_report.visit_no if latest_report else 0
        total = site.total_guidance_count if site.total_guidance_count else "-"
        date_text = (
            latest_report.guidance_date.strftime("%Y.%m.%d")
            if latest_report and latest_report.guidance_date
            else "-"
        )
        sub = QLabel(f"{visit_no}/{total}회차 · {date_text}")
        sub.setStyleSheet(f"color: #9ca3af; font-size: 12px; {_LABEL_RESET}")
        outer.addWidget(sub)

        progress = (latest_report.progress_rate if latest_report else 0) or 0
        progress_row = QHBoxLayout()
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(progress)
        bar.setTextVisible(False)
        bar.setFixedHeight(6)
        bar.setStyleSheet(
            "QProgressBar { background: #e5e7eb; border: none; border-radius: 3px; }"
            "QProgressBar::chunk { background: #4f46e5; border-radius: 3px; }"
        )
        pct_label = QLabel(f"{progress}%")
        pct_label.setStyleSheet(f"color: #6b7280; font-size: 11px; {_LABEL_RESET}")
        progress_row.addWidget(bar, stretch=1)
        progress_row.addWidget(pct_label)
        outer.addLayout(progress_row)

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.continue_btn.setVisible(True)
        self.delete_btn.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.continue_btn.setVisible(False)
        self.delete_btn.setVisible(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.clicked.emit(self._site_id)
        super().mousePressEvent(event)


class DashboardView(QWidget):
    new_site_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    staff_requested = pyqtSignal()
    report_upload_requested = pyqtSignal()
    site_selected = pyqtSignal(int)
    continue_requested = pyqtSignal(int, object)  # site_id, report_id(없으면 None)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_status = "진행중"
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(16)

        header_row = QHBoxLayout()
        header_text = QVBoxLayout()
        today = datetime.date.today()
        weekday = _WEEKDAYS_KO[today.weekday()]
        date_label = QLabel(f"{today.year}년 {today.month}월 {today.day}일 ({weekday})")
        date_label.setStyleSheet(f"color: #6b7280; font-size: 12px; {_LABEL_RESET}")
        self.greeting_label = QLabel("한국미래안전님, 안녕하세요")
        self.greeting_label.setStyleSheet(f"font-size: 22px; font-weight: 700; {_LABEL_RESET}")
        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet(f"color: #6b7280; {_LABEL_RESET}")
        header_text.addWidget(date_label)
        header_text.addWidget(self.greeting_label)
        header_text.addWidget(self.summary_label)
        header_row.addLayout(header_text)
        header_row.addStretch()

        staff_btn = QPushButton("👥 담당요원 및 서명관리")
        staff_btn.clicked.connect(self.staff_requested.emit)
        settings_btn = QPushButton("⚙ AI 관리")
        settings_btn.clicked.connect(self.settings_requested.emit)
        upload_btn = QPushButton("⬆ 이전 보고서 업로드")
        upload_btn.clicked.connect(self.report_upload_requested.emit)
        new_site_btn = QPushButton("+ 신규현장 추가")
        new_site_btn.setStyleSheet(
            "QPushButton { background: #111827; color: white; padding: 8px 16px; border-radius: 6px; }"
        )
        new_site_btn.clicked.connect(self.new_site_requested.emit)
        header_row.addWidget(staff_btn)
        header_row.addWidget(settings_btn)
        header_row.addWidget(upload_btn)
        header_row.addWidget(new_site_btn)
        root.addLayout(header_row)

        stats_row = QHBoxLayout()
        self.stat_total = _StatCard("#3b82f6", "0개", "전체 현장", "")
        self.stat_progress = _StatCard("#8b5cf6", "0%", "평균 공정률", "전체 현장 평균")
        self.stat_reports = _StatCard("#10b981", "0건", "작성 보고서", "시스템 내 저장된 보고서")
        self.stat_missing = _StatCard("#ef4444", "0개", "보고서 미작성", "")
        for card in (self.stat_total, self.stat_progress, self.stat_reports, self.stat_missing):
            stats_row.addWidget(card)
        root.addLayout(stats_row)

        list_label = QLabel("현장 목록")
        list_label.setStyleSheet(f"font-size: 15px; font-weight: 600; margin-top: 8px; {_LABEL_RESET}")
        root.addWidget(list_label)

        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("현장명, 회차, 지적사항으로 검색...")
        self.search_input.textChanged.connect(self.refresh)
        search_row.addWidget(self.search_input, stretch=1)
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(_SORT_OPTIONS)
        self.sort_combo.currentIndexChanged.connect(self.refresh)
        search_row.addWidget(self.sort_combo)
        root.addLayout(search_row)

        tabs_row = QHBoxLayout()
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self._tab_buttons: dict[str, QPushButton] = {}
        for status in _STATUS_TABS:
            btn = QPushButton(status)
            btn.setCheckable(True)
            btn.setChecked(status == self._active_status)
            btn.clicked.connect(lambda _checked, s=status: self._on_tab_clicked(s))
            self._tab_group.addButton(btn)
            self._tab_buttons[status] = btn
            tabs_row.addWidget(btn)
        tabs_row.addStretch()
        root.addLayout(tabs_row)

        self.section_label = QLabel("")
        self.section_label.setStyleSheet(f"color: #374151; font-size: 13px; font-weight: 600; {_LABEL_RESET}")
        root.addWidget(self.section_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setSpacing(8)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_container)
        root.addWidget(scroll)

    def _on_tab_clicked(self, status: str) -> None:
        self._active_status = status
        self.refresh()

    def _continue_report(self, site_id: int, report_id: int | None) -> None:
        self.continue_requested.emit(site_id, report_id)

    def _delete_site(self, site_id: int) -> None:
        reply = QMessageBox.question(
            self,
            "현장 삭제",
            "이 현장을 삭제하면 저장된 모든 보고서도 함께 삭제됩니다. 계속하시겠습니까?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        with SessionLocal() as session:
            site = session.get(Site, site_id)
            if not site:
                return
            session.query(SiteProcessDefault).filter_by(site_id=site_id).delete()
            for report in session.query(Report).filter_by(site_id=site_id).all():
                session.delete(report)
            session.delete(site)
            session.commit()
        self.refresh()

    def refresh(self) -> None:
        with SessionLocal() as session:
            all_sites = session.query(Site).all()
            total_count = len(all_sites)
            in_progress_count = sum(1 for s in all_sites if s.status == "진행중")
            report_count = session.query(Report).count()
            sites_with_reports = {r[0] for r in session.query(Report.site_id).distinct().all()}
            missing_count = total_count - len(sites_with_reports)

            avg_progress = (
                session.query(func.avg(Report.progress_rate)).scalar() if report_count else None
            )

            self.summary_label.setText(f"한국미래안전 · {total_count}개 현장을 관리하고 있습니다")
            self.stat_total.value_label.setText(f"{total_count}개")
            self.stat_total.sub_label.setText(f"진행중 {in_progress_count}개")
            self.stat_progress.value_label.setText(f"{round(avg_progress or 0)}%")
            self.stat_reports.value_label.setText(f"{report_count}건")
            self.stat_missing.value_label.setText(f"{missing_count}개")
            self.stat_missing.sub_label.setText("모두 작성 완료" if missing_count == 0 else "보고서 작성 필요")

            for status, btn in self._tab_buttons.items():
                count = sum(1 for s in all_sites if s.status == status)
                btn.setText(f"{status}{_STATUS_PARTICLE[status]} 현장 {count}")

            # 현장명 + 최근 회차번호 + 지적사항 제목/내용까지 자모 단위로 검색한다.
            keyword = self.search_input.text().strip()
            site_ids_matching_reports: set[int] = set()
            if keyword:
                for report in session.query(Report).all():
                    if hangul_matches(keyword, str(report.visit_no)):
                        site_ids_matching_reports.add(report.site_id)
                for finding in session.query(Finding).all():
                    if hangul_matches(keyword, finding.title) or hangul_matches(keyword, finding.content):
                        report = session.get(Report, finding.report_id)
                        if report:
                            site_ids_matching_reports.add(report.site_id)

            def site_matches(site: Site) -> bool:
                if not keyword:
                    return True
                return hangul_matches(keyword, site.name or "") or site.id in site_ids_matching_reports

            filtered = [s for s in all_sites if s.status == self._active_status and site_matches(s)]

            latest_by_site: dict[int, Report | None] = {}
            for site in filtered:
                reports = session.query(Report).filter(Report.site_id == site.id).order_by(
                    Report.visit_no.desc()
                ).all()
                latest_by_site[site.id] = reports[0] if reports else None

            if self.sort_combo.currentText() == "이름순":
                filtered.sort(key=lambda s: s.name or "")
            else:
                filtered.sort(
                    key=lambda s: (
                        latest_by_site[s.id].guidance_date or datetime.date.min
                        if latest_by_site[s.id]
                        else datetime.date.min
                    ),
                    reverse=True,
                )

            particle = _STATUS_PARTICLE[self._active_status]
            self.section_label.setText(f"{self._active_status}{particle} 현장 {len(filtered)}개")

            while self._list_layout.count() > 1:
                item = self._list_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            for site in filtered:
                card = _SiteCard(site, latest_by_site[site.id])
                card.clicked.connect(self.site_selected.emit)
                card.continue_requested.connect(self._continue_report)
                card.delete_requested.connect(self._delete_site)
                self._list_layout.insertWidget(self._list_layout.count() - 1, card)
