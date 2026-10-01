# -*- coding: utf-8 -*-
"""K2BClient 공통 기반 -- 여러 기능별 mixin(`core/k2b_client_*.py`)이 공유하는 상태/헬퍼.

이 파일 하나에 있던 `core/k2b_client.py`가 600줄을 넘어서 기능별로 분리했다(2026-09-16
리팩토링). 실제 동작/셀렉터/실기록 주석은 그대로 옮겼을 뿐 내용 변경 없음."""
from __future__ import annotations

import datetime
from collections.abc import Callable

from playwright.sync_api import Page

LogFn = Callable[[str], None]


def _noop_log(msg: str) -> None:
    pass


class ReportModificationExpiredError(Exception):
    """"보고서 수정가능 기한"이 지나 보고서 파일첨부 버튼이 비활성화된 경우.

    이 기한은 기술지도일 이후 7일까지다(실화면 안내문). 기존 차수를 그대로 열어
    편집하면 이 기한이 이미 지나있을 수 있다 -- 새 차수로 추가하면 기술지도일이 오늘
    날짜로 자동 설정돼 항상 기한 안에 들어온다."""


class K2BClientBase:
    """`self.page`/`self.log`와 여러 mixin이 공유하는 헬퍼 메서드만 담는다.

    실제 기능(로그인/검색/필드입력/대형사고위험작업/첨부)은 각 `core/k2b_client_*.py`의
    mixin 클래스에 있고, `core/k2b_client.py`의 `K2BClient`가 전부 합쳐서 상속한다."""

    def __init__(self, page: Page, log: LogFn = _noop_log):
        self.page = page
        self.log = log

    def _scroll_into_view(self, locator, max_attempts: int = 20) -> None:
        """이 사이트(Nexacro)는 상세 모달 전체가 절대좌표로 배치된 하나의 거대한 패널이라
        일반적인 `overflow:scroll` 컨테이너가 아니다 -- Playwright의 자동
        `scrollIntoViewIfNeeded`가 먹히지 않아, 화면 아래쪽 요소를 클릭하기 전에는 실제
        마우스 휠 이벤트로 스크롤해야 한다(실사용 중 발견: 이 처리 없이 보고서 파일첨부
        버튼을 클릭했더니 버튼이 화면 밖에 있어 클릭이 씹히고 "filechooser" 이벤트
        타임아웃 발생). 대상 요소가 뷰포트 안에 들어올 때까지 반복 스크롤한다.

        주의(2026-09-16 발견): 처음엔 아래로만 스크롤했는데, "불량사업장 통보" 영역처럼
        한 화면보다 넓게 걸쳐 있는 섹션에서는 대상이 이미 지나쳐서 뷰포트 **위**(y<0)에
        있는 경우도 생긴다 -- 이때 계속 아래로만 스크롤하면 영원히 못 찾는다. box.y의
        부호를 보고 방향을 정하도록 일반화함(요소가 안 보여 box가 None이면 기존처럼
        아래로 스크롤 시도)."""
        viewport = self.page.viewport_size or {"width": 1280, "height": 800}
        self.page.mouse.move(viewport["width"] // 2, viewport["height"] // 2)
        for _ in range(max_attempts):
            box = locator.bounding_box()
            if box is not None and 0 <= box["y"] <= viewport["height"] - 40:
                return
            delta = -500 if (box is not None and box["y"] < 0) else 500
            self.page.mouse.wheel(0, delta)
            self.page.wait_for_timeout(150)

    def _type_into(self, locator_str: str, text: str) -> None:
        """Nexacro 커스텀 입력창은 값을 통째로 덮어쓰는 `.fill()`을 쓰면 내부 상태와
        어긋나 기존 값 뒤에 이어붙는 현상이 있었다(실사용 중 발견) — 클릭 후 전체선택+삭제로
        비우고, 실제 키보드 입력처럼 한 글자씩 입력(`press_sequentially`)한다."""
        field = self.page.locator(locator_str)
        self._scroll_into_view(field)
        field.click()
        field.press("Control+A")
        field.press("Delete")
        field.press_sequentially(text, delay=30)

    def _pick_date_in_open_calendar(
        self, target: datetime.date, year_id: str, month_id: str,
        prev_id: str, next_id: str, day_cells_id: str,
    ) -> None:
        """이미 열려있는 캘린더 팝업에서 month/day를 골라 클릭한다(CONFIRMED, 기술지도일
        캘린더로 검증한 로직을 대형사고 위험작업 예정시기 캘린더에도 그대로 재사용하기
        위해 공통 헬퍼로 뽑음 -- 두 팝업은 Nexacro가 만드는 동일한 구조).

        팝업의 날짜 셀 42개(6주 x 7일)는 Nexacro 특성상 전부 동일한 id를 공유해(중복 id)
        텍스트로 찾으면 이전달/다음달 잔여일과 모호하다 -- 목표 월 1일의 요일을 계산해
        그리드에서 몇 번째 칸인지(0-based) 구한 뒤 `.nth()`로 정확히 클릭한다.

        주의(실기록, 대형사고 위험작업 캘린더에서 발견): 이 팝업을 여러 번 열면(예: 시작일
        -> 종료일, 또는 행을 여러 개 다룰 때) Nexacro가 이전 팝업 DOM을 지우지 않고 매번
        새로 만들어서 쌓아둔다 -- 그래서 year/month 헤더와 42칸 날짜 셀 모두 `.last`/
        "마지막 42개" 기준으로 골라야 방금 연 팝업을 정확히 다룰 수 있다."""
        page = self.page
        year_header = page.locator(year_id).last
        month_header = page.locator(month_id).last

        def shown_year_month() -> tuple[int, int]:
            year = int(year_header.inner_text().strip().rstrip("."))
            month = int(month_header.inner_text().strip())
            return year, month

        shown_year, shown_month = shown_year_month()
        month_diff = (target.year - shown_year) * 12 + (target.month - shown_month)
        step_button = next_id if month_diff > 0 else prev_id
        for _ in range(abs(month_diff)):
            page.locator(step_button).last.click()
            page.wait_for_timeout(100)

        shown_year, shown_month = shown_year_month()
        if (shown_year, shown_month) != (target.year, target.month):
            raise RuntimeError(
                f"캘린더 월 이동 실패: {target.year}.{target.month:02d}로 이동하려 했으나 "
                f"{shown_year}.{shown_month:02d}에서 멈췄습니다."
            )

        # 이 달 1일이 그리드에서 몇 번째 칸(일=0)인지: python weekday()는 월=0이라 +1, %7로
        # 일요일=0 기준으로 바꾼다(실기록으로 검증: 2026.09는 1일이 화요일 -> leading=2,
        # 실제 화면에서 "30 31 1 2 ..." 순서와 일치).
        leading = (datetime.date(target.year, target.month, 1).weekday() + 1) % 7
        cell_index = leading + target.day - 1
        day_cells = page.locator(day_cells_id)
        total = day_cells.count()
        # 42칸씩 마지막 묶음이 방금 연 팝업의 것이라고 본다(위 설명 참고).
        offset = total - 42 if total >= 42 else 0
        day_cells.nth(offset + cell_index).click()
