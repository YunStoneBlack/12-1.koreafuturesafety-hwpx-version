"""파일 저장(한글/PDF 내보내기) 중 뜨는 짧은 모달 — 실제로 디스크에 파일이 다 써질 때까지
보여준다.

사용자 피드백(2026-09-15): 저장 위치를 고르는 대화상자에서 파일 이름을 정하고 "저장"을
누르면, 실제 파일이 만들어지기까지 몇 초 걸리는데 그동안 화면에 아무 표시가 없어 "오류가
난 줄 알았다"는 피드백이 있었다 — 미리보기 갱신 때 이미 쓰고 있는 `FakeProgressBar`를
재사용해 저장 완료까지 명확히 보여준다.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QLabel, QVBoxLayout

from desktop.widgets.fake_progress_bar import FakeProgressBar


class SavingProgressDialog(QDialog):
    def __init__(self, message: str = "파일을 저장하는 중입니다...", parent=None):
        super().__init__(parent)
        self.setWindowTitle("저장 중")
        self.setFixedSize(360, 90)
        self.setModal(True)
        # 저장 도중 실수로 닫아버리지 못하게 닫기 버튼을 없앤다 — 저장이 끝나면(`finish()`/
        # `fail()`) 코드가 알아서 닫는다.
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)

        layout = QVBoxLayout(self)
        label = QLabel(message)
        label.setStyleSheet("color: #374151;")
        layout.addWidget(label)
        self.progress_bar = FakeProgressBar()
        layout.addWidget(self.progress_bar)
        layout.addStretch()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.progress_bar.start()

    def finish(self) -> None:
        """저장이 성공적으로 끝났을 때 — 100%까지 채운 뒤 닫는다."""
        self.progress_bar.finish()
        self.accept()

    def fail(self) -> None:
        """저장이 실패했을 때 — 진행 표시 없이 바로 닫는다."""
        self.progress_bar.reset_hidden()
        self.reject()
