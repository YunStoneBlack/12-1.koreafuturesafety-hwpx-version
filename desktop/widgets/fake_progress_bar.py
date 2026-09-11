"""한글 자동화를 거치는 작업(미리보기 생성, 한글/PDF 내보내기)은 정확한 진행률을 알 방법이
없다 — 자동화 안이 몇 단계인지, 사진이 몇 장인지 등에 따라 몇 초~십몇 초까지 편차가 크다.

그렇다고 "실제 서식으로 만드는 중입니다..." 문구만 띄워두면 정말 동작 중인지 멈춘 건지
구분이 안 돼 "고장난 줄 알았다"는 피드백을 받았다(사용자, 2026-09-11). 정직한 %는 계산할
근거가 없으므로, 깃허브/슬랙 업로드 등에서 흔히 쓰는 "가짜 진행바" 패턴을 쓴다 — 처음엔
빠르게 차오르다가 90%에서 멈춰 기다리고, 실제 작업이 끝나는 순간(`finish()`) 100%로
채운다. 얼마나 오래 걸리든 절대 "멈춘 것처럼" 보이지 않는다.
"""

from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QProgressBar

_CAP = 90  # finish() 전까지는 이 이상 못 올라간다 — 실제로 안 끝났는데 100%로 보이면 안 됨
_TICK_MS = 80


class FakeProgressBar(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0, 100)
        self.setValue(0)
        self.setTextVisible(False)
        self.setFixedHeight(4)
        self.setStyleSheet(
            "QProgressBar { background: #e5e7eb; border: none; border-radius: 2px; }"
            "QProgressBar::chunk { background: #4f46e5; border-radius: 2px; }"
        )
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        # `finish()`가 100%를 잠깐 보여준 뒤 숨기는 예약 타이머 — 전용 인스턴스로 둬야
        # `start()`가 이걸 취소할 수 있다. 두 단계 작업(예: 미리보기 생성 → 파일 내보내기)이
        # 이어질 때, finish()의 숨김 예약이 아직 안 끝난 채로 다음 단계의 start()가 다시
        # show()를 부르면 그 예약이 뒤늦게 발동해 진행 중인 바를 잘못 숨겨버리는 문제가
        # 있었다(실측 확인) — start()에서 이 타이머를 멈춰서 막는다.
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)
        self.hide()

    def start(self) -> None:
        """처음엔 빠르게, `_CAP`(90%)에 가까워질수록 남은 거리에 비례해 느려지는 감속
        곡선 — 몇 번 틱만에 90%까지 훅 올라간 뒤 거기서 계속 기다리는 모양이 된다."""
        self._hide_timer.stop()
        self._timer.stop()
        self.setValue(0)
        self.show()
        self._timer.start(_TICK_MS)

    def _tick(self) -> None:
        current = self.value()
        if current >= _CAP:
            self._timer.stop()
            return
        step = max(1, int((_CAP - current) * 0.12))
        self.setValue(min(_CAP, current + step))

    def finish(self) -> None:
        """실제 작업이 끝났을 때 호출 — 곧바로 100%로 채우고 잠시 뒤 숨긴다."""
        self._timer.stop()
        self.setValue(100)
        self._hide_timer.start(250)

    def reset_hidden(self) -> None:
        """진행 표시 없이(예: 에러로 중단) 바로 숨긴다."""
        self._hide_timer.stop()
        self._timer.stop()
        self.setValue(0)
        self.hide()
