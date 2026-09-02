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


def with_com(task: Callable[[], Any]) -> Callable[[], Any]:
    """pyhwpx(win32com) 자동화처럼 COM을 쓰는 작업을 `AIWorker`(QThread) 안에서 돌릴 때
    감싸는 헬퍼. COM은 스레드마다 초기화(`CoInitialize`)가 따로 필요해서, 메인 스레드가
    아닌 QThread 안에서 그냥 호출하면 실패한다 — 실제로 COM 초기화 후 정상 동작하는 것까지
    확인했다."""

    def wrapped():
        import pythoncom

        pythoncom.CoInitialize()
        try:
            return task()
        finally:
            pythoncom.CoUninitialize()

    return wrapped
