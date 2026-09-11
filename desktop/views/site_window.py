"""현장별 독립 창 — 대시보드에서 현장을 클릭하면 이 창이 새로 뜬다(현장마다 하나, 여러
개를 동시에 열어둘 수 있음, 사용자 요청 2026-09-11). 전에는 대시보드/현장상세/보고서
마법사가 `MainWindow`의 스택 하나를 전부 같이 썼는데(따라서 창이 하나뿐이고 현장상세·
마법사 인스턴스도 전역에 하나씩만 존재), 이제 이 창이 "현장상세"/"보고서 작성 마법사"만
자체 스택으로 갖는다 — 그래서 현장 A 창을 열어둔 채로 현장 B 창을 또 열어도 서로 상태가
안 섞인다.

보고서 작성 마법사는 이 창 밖으로 안 뺐다(사용자 확인) — 마법사를 열 때도 새 창이 아니라
이 현장 창 안에서 화면만 전환된다. `QMainWindow`를 부모 없이(또는 `Qt.WindowType.Window`
플래그로) 띄우는 비모달 창이라, 이 창이 떠 있어도 대시보드(메인 창)는 계속 움직이고
조작할 수 있다 — 모달 다이얼로그였다면 부모 창이 막혔을 것.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QMainWindow, QStackedWidget

from desktop.views.report_wizard_view import ReportWizardView
from desktop.views.site_detail_view import SiteDetailView


class SiteWindow(QMainWindow):
    # 이 창 안에서 보고서가 저장되는 등 대시보드 통계(전체 현장/평균 공정률/작성 보고서 수
    # 등)가 달라질 수 있는 변화가 생겼을 때 emit — MainWindow가 이걸 받아
    # `dashboard_view.refresh()`를 부른다(사용자 요청, 여러 창을 띄워놔도 대시보드가
    # 실시간으로 맞게 보이도록).
    data_changed = pyqtSignal()

    def __init__(self, site_id: int, parent=None):
        super().__init__(parent)
        self.site_id = site_id
        self.resize(1200, 800)
        # 닫으면(예: "← 현장 목록") 그냥 숨기지 말고 실제로 파괴한다 — MainWindow가
        # `destroyed` 시그널로 열린 창 목록에서 지우는데, 이 속성이 없으면 close()가
        # 숨기기만 해서 그 신호가 (앱 종료 전까지) 영영 안 오고, 다시 같은 현장을 열 때마다
        # 계속 쌓여 메모리를 차지한다.
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.site_detail_view = SiteDetailView()
        self.report_wizard_view = ReportWizardView()
        self.stack.addWidget(self.site_detail_view)
        self.stack.addWidget(self.report_wizard_view)

        self.site_detail_view.back_requested.connect(self.close)
        self.site_detail_view.new_report_requested.connect(self._show_wizard_new)
        self.site_detail_view.edit_report_requested.connect(self._show_wizard_edit)

        self.report_wizard_view.back_requested.connect(self.show_detail)
        self.report_wizard_view.report_saved.connect(self._on_report_saved)

        self.show_detail()

    def show_detail(self, *_args) -> None:
        """현장상세 화면을 (다시) 불러와 보여준다 — 새로 만든 창의 초기 화면으로도,
        이미 열려있던 창을 다시 활성화할 때(MainWindow가 최신 데이터로 새로고침하려고)도
        쓴다. `*_args`는 시그널에서 site_id 등을 같이 넘겨도 무시하고 받아주기 위함."""
        self.site_detail_view.load_site(self.site_id)
        self.stack.setCurrentWidget(self.site_detail_view)
        name = self.site_detail_view.name_label.text()
        self.setWindowTitle(f"한국미래안전 — {name}" if name else "한국미래안전 — 현장")

    def _show_wizard_new(self, site_id: int) -> None:
        self.report_wizard_view.load_for_site(site_id)
        self.stack.setCurrentWidget(self.report_wizard_view)

    def _show_wizard_edit(self, site_id: int, report_id: int) -> None:
        self.report_wizard_view.load_for_site(site_id, report_id)
        self.stack.setCurrentWidget(self.report_wizard_view)

    def show_new_report(self) -> None:
        """대시보드 "이어서 작성"(작성된 보고서가 아직 없는 현장)에서 이 창을 열자마자
        곧바로 마법사부터 보여줄 때 쓴다."""
        self._show_wizard_new(self.site_id)

    def show_edit_report(self, report_id: int) -> None:
        """대시보드 "이어서 작성"(이미 시작한 보고서를 이어쓰기)에서 이 창을 열자마자
        곧바로 마법사부터 보여줄 때 쓴다."""
        self._show_wizard_edit(self.site_id, report_id)

    def _on_report_saved(self, site_id: int) -> None:
        self.show_detail(site_id)
        self.data_changed.emit()
