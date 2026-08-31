"""AI(Claude API) 호출처럼 시간이 걸리는 작업을 백그라운드 스레드에서 실행해
UI가 멈추지 않게 해주는 공용 워커. 보고서 작성 마법사의 여러 AI추천 버튼에서도
동일하게 재사용한다."""

from __future__ import annotations

from typing import Any, Callable

from PyQt6.QtCore import QThread, pyqtSignal


class AIWorker(QThread):
    finished_ok = pyqtSignal(object)
    finished_error = pyqtSignal(str)

    def __init__(self, task: Callable[[], Any], parent=None):
        super().__init__(parent)
        self._task = task

    def run(self) -> None:
        try:
            result = self._task()
        except Exception as e:  # noqa: BLE001 - 사용자에게 그대로 보여줄 에러 메시지
            self.finished_error.emit(str(e))
        else:
            self.finished_ok.emit(result)
