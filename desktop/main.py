"""데스크톱 앱 진입점."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget

from core.db import init_db
from core.hwp_cleanup import kill_orphaned_hwp_processes
from desktop.views.dashboard_view import DashboardView
from desktop.views.report_upload_view import ReportUploadView
from desktop.views.report_wizard_view import ReportWizardView
from desktop.views.settings_view import SettingsView
from desktop.views.site_detail_view import SiteDetailView
from desktop.views.site_form_view import SiteFormView
from desktop.views.staff_view import StaffView


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("한국미래안전 — 기술지도 결과보고서")
        self.resize(1200, 800)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self._current_site_id: int | None = None

        self.dashboard_view = DashboardView()
        self.site_form_view = SiteFormView()
        self.site_detail_view = SiteDetailView()
        self.settings_view = SettingsView()
        self.report_wizard_view = ReportWizardView()
        self.staff_view = StaffView()
        self.report_upload_view = ReportUploadView()

        for widget in (
            self.dashboard_view,
            self.site_form_view,
            self.site_detail_view,
            self.settings_view,
            self.report_wizard_view,
            self.staff_view,
            self.report_upload_view,
        ):
            self.stack.addWidget(widget)

        self.dashboard_view.new_site_requested.connect(self._show_site_form)
        self.dashboard_view.settings_requested.connect(self._show_settings)
        self.dashboard_view.staff_requested.connect(self._show_staff)
        self.dashboard_view.site_selected.connect(self._show_site_detail)
        self.dashboard_view.continue_requested.connect(self._continue_report)
        self.dashboard_view.report_upload_requested.connect(self._show_report_upload)

        self.report_upload_view.back_requested.connect(self._show_dashboard)
        self.report_upload_view.upload_completed.connect(self._show_dashboard)

        self.site_form_view.back_requested.connect(self._show_dashboard)
        self.site_form_view.site_saved.connect(self._show_site_detail)

        self.site_detail_view.back_requested.connect(self._show_dashboard)
        self.site_detail_view.new_report_requested.connect(self._show_report_wizard)
        self.site_detail_view.edit_report_requested.connect(self._show_report_wizard_for_edit)

        self.settings_view.back_requested.connect(self._show_dashboard)
        self.staff_view.back_requested.connect(self._show_dashboard)

        self.report_wizard_view.back_requested.connect(lambda: self._show_site_detail(self._current_site_id))
        self.report_wizard_view.report_saved.connect(self._show_site_detail)

        self._show_dashboard()

    def _show_dashboard(self) -> None:
        self.dashboard_view.refresh()
        self.stack.setCurrentWidget(self.dashboard_view)

    def _show_site_form(self) -> None:
        self.site_form_view.reset()
        self.stack.setCurrentWidget(self.site_form_view)

    def _show_site_detail(self, site_id: int) -> None:
        self._current_site_id = site_id
        self.site_detail_view.load_site(site_id)
        self.stack.setCurrentWidget(self.site_detail_view)

    def _show_settings(self) -> None:
        self.settings_view.reload()
        self.stack.setCurrentWidget(self.settings_view)

    def _show_staff(self) -> None:
        self.staff_view.reload()
        self.stack.setCurrentWidget(self.staff_view)

    def _show_report_wizard(self, site_id: int) -> None:
        self._current_site_id = site_id
        self.report_wizard_view.load_for_site(site_id)
        self.stack.setCurrentWidget(self.report_wizard_view)

    def _show_report_wizard_for_edit(self, site_id: int, report_id: int) -> None:
        self._current_site_id = site_id
        self.report_wizard_view.load_for_site(site_id, report_id)
        self.stack.setCurrentWidget(self.report_wizard_view)

    def _continue_report(self, site_id: int, report_id: int | None) -> None:
        if report_id:
            self._show_report_wizard_for_edit(site_id, report_id)
        else:
            self._show_report_wizard(site_id)

    def _show_report_upload(self) -> None:
        self.stack.setCurrentWidget(self.report_upload_view)


def main() -> None:
    init_db()
    # 이전 실행이 비정상 종료되며 숨은(visible=False) 한글 프로세스를 남겼을 수 있어, 새
    # 세션이 그걸 재사용하지 않도록 앱 시작 시 한 번 정리한다(core/hwp_cleanup.py 참고).
    kill_orphaned_hwp_processes()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
