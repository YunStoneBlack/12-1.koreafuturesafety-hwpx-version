"""데스크톱 앱 진입점."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget

from core.db import init_db
from core.device_checkin import send_checkin_async
from core.hwp_cleanup import kill_orphaned_hwp_processes
from desktop.views.dashboard_view import DashboardView
from desktop.views.report_upload_view import ReportUploadView
from desktop.views.settings_view import SettingsView
from desktop.views.site_form_view import SiteFormView
from desktop.views.site_window import SiteWindow
from desktop.views.staff_view import StaffView


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("한국미래안전 — 기술지도 결과보고서")
        self.resize(1200, 800)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        # 현장별 독립 창(desktop/views/site_window.py) — site_id를 키로 열려있는 창을
        # 추적해서, 같은 현장을 또 클릭하면 새 창 대신 기존 창을 앞으로 가져온다(사용자
        # 요청 2026-09-11). 이 창들은 비모달이라 떠 있는 동안에도 이 메인(대시보드) 창은
        # 계속 움직이고 조작할 수 있다.
        self._site_windows: dict[int, SiteWindow] = {}

        self.dashboard_view = DashboardView()
        self.site_form_view = SiteFormView()
        self.settings_view = SettingsView()
        self.staff_view = StaffView()
        self.report_upload_view = ReportUploadView()

        for widget in (
            self.dashboard_view,
            self.site_form_view,
            self.settings_view,
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

        self.settings_view.back_requested.connect(self._show_dashboard)
        self.staff_view.back_requested.connect(self._show_dashboard)

        self._show_dashboard()

    def _show_dashboard(self) -> None:
        self.dashboard_view.refresh()
        self.stack.setCurrentWidget(self.dashboard_view)

    def _show_site_form(self) -> None:
        self.site_form_view.reset()
        self.stack.setCurrentWidget(self.site_form_view)

    def _get_or_create_site_window(self, site_id: int) -> SiteWindow:
        window = self._site_windows.get(site_id)
        if window is None:
            window = SiteWindow(site_id)
            window.data_changed.connect(self.dashboard_view.refresh)
            # 창을 닫으면(예: "← 현장 목록") 추적 목록에서 빼야 다음에 같은 현장을 클릭할 때
            # 죽은 창 대신 새로 만든다 — `SiteWindow`가 `WA_DeleteOnClose`를 켜두므로 닫힘=
            # 실제 파괴이고, 그 순간 `destroyed`가 불려 여기서 딕셔너리를 정리한다(안 그러면
            # 매번 새 창을 만들 때마다 죽은 참조가 쌓인다).
            window.destroyed.connect(lambda _obj=None, sid=site_id: self._site_windows.pop(sid, None))
            self._site_windows[site_id] = window
        return window

    def _activate_window(self, window: SiteWindow) -> None:
        window.show()
        window.raise_()
        window.activateWindow()

    def _show_site_detail(self, site_id: int) -> None:
        window = self._get_or_create_site_window(site_id)
        # 이미 열려있던 창이 마법사 화면에 가 있었을 수도 있으니, 매번 현장상세로
        # 확실히 되돌리고 최신 데이터로 새로고침한다.
        window.show_detail()
        self._activate_window(window)

    def _show_settings(self) -> None:
        self.settings_view.reload()
        self.stack.setCurrentWidget(self.settings_view)

    def _show_staff(self) -> None:
        self.staff_view.reload()
        self.stack.setCurrentWidget(self.staff_view)

    def _continue_report(self, site_id: int, report_id: int | None) -> None:
        window = self._get_or_create_site_window(site_id)
        if report_id:
            window.show_edit_report(report_id)
        else:
            window.show_new_report()
        self._activate_window(window)

    def _show_report_upload(self) -> None:
        self.stack.setCurrentWidget(self.report_upload_view)


def main() -> None:
    init_db()
    # 이전 실행이 비정상 종료되며 숨은(visible=False) 한글 프로세스를 남겼을 수 있어, 새
    # 세션이 그걸 재사용하지 않도록 앱 시작 시 한 번 정리한다(core/hwp_cleanup.py 참고).
    kill_orphaned_hwp_processes()
    # 사용 현황 파악용 — 실패해도(오프라인 등) 앱 실행에 영향 없음(core/device_checkin.py).
    send_checkin_async()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
