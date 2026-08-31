"""디바운스 검색용 QLineEdit — 한글(IME) 조합 중인 마지막 글자까지 포함해서 검색한다.

한글은 마지막으로 입력 중인 글자가 다음 동작(다음 글자 입력, 스페이스, 방향키 등)이
있기 전까지는 QLineEdit.text()에 반영되지 않는다(예: "안전"을 입력해도 "전"이 아직
조합 중이면 text()는 "안"만 돌려준다). 이 상태에서 단순히 text()만 보고 검색하면,
사용자는 화면에 "안전"이 다 보이는데 검색 결과는 "안"만으로 나온 것처럼 보이거나,
입력을 멈춰도 결과가 갱신되지 않아 "느려졌다"고 느껴진다.
그래서 inputMethodEvent로 조합 중인 글자(preedit)를 따로 들고 있다가, 실제 검색을
발동시킬 때는 커밋된 텍스트 + 조합 중인 글자를 합쳐서 사용한다.
"""

from __future__ import annotations

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import QLineEdit


class DebouncedSearchInput(QLineEdit):
    search_triggered = pyqtSignal()

    def __init__(self, delay_ms: int = 250, parent=None):
        super().__init__(parent)
        self._delay_ms = delay_ms
        self._preedit = ""

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.search_triggered.emit)

        self.textChanged.connect(self._reschedule)

    def _reschedule(self) -> None:
        self._timer.start(self._delay_ms)

    def inputMethodEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._preedit = event.preeditString()
        super().inputMethodEvent(event)
        self._reschedule()

    def current_text(self) -> str:
        """커밋된 텍스트 + 지금 조합 중인 글자까지 합친, 화면에 실제로 보이는 텍스트."""
        return self.text() + self._preedit
