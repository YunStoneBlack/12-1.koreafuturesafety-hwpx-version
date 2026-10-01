# -*- coding: utf-8 -*-
"""K2BClient: "대형사고 위험작업" 그리드(추가/발생형태/위험작업종류/예정시기).

`core/k2b_client.py`의 600줄 초과 문제로 기능별 분리한 파일 중 하나(2026-09-16).
내용/셀렉터/실기록 주석은 원본에서 그대로 옮겼다."""
from __future__ import annotations

import datetime

from server.k2b import selectors as sel
from server.k2b.base import K2BClientBase


class HazardWorkMixin(K2BClientBase):
    def add_major_hazard_work(
        self, occurrence_type: str, hazard_work: str,
        start_date: datetime.date, end_date: datetime.date,
    ) -> None:
        """"대형사고 위험작업"에 새 행을 추가하고 발생형태/위험작업종류/예정시기(시작·종료)를
        전부 설정한다(CONFIRMED 전체 흐름, 2026-09-16 그리드 구조 재조사 후 재작성).

        업무영역 칸은 "재해예방 기술지도" 고정값이 자동으로 들어가 사람이 고를 필요가
        없어 이 메서드에서 다루지 않는다."""
        if occurrence_type not in sel.MAJOR_HAZARD_WORK_OCCURRENCE_TYPES:
            raise ValueError(f"알 수 없는 발생형태: {occurrence_type}")
        # 대형사고위험작업 드롭다운은 발생형태에 따라 선택지가 필터링되는 사이트라
        # (CONFIRMED, 2026-09-16), 고정 전체 목록이 아니라 해당 발생형태의 필터링된
        # 목록에 속하는지로 검증한다.
        valid_options = sel.MAJOR_HAZARD_WORK_OPTIONS_BY_OCCURRENCE.get(occurrence_type, [])
        if hazard_work not in valid_options:
            raise ValueError(
                f"발생형태 '{occurrence_type}'에서는 선택할 수 없는 대형사고 위험작업: {hazard_work}"
            )
        self.log(f"대형사고 위험작업 '{hazard_work}' 추가 중...")
        page = self.page

        # 이전에 어떤 셀이든 편집모드(드롭다운/캘린더 열림)로 남아있으면 "+ 추가"가
        # 무시된다(실기록으로 확인) -- 다른 곳(예: 섹션 제목)을 먼저 클릭해 편집모드를
        # 벗어난 뒤 추가해야 한다.
        page.locator(sel.MAJOR_HAZARD_WORK_TITLE_ID).click()

        add_button = page.locator(sel.MAJOR_HAZARD_WORK_ADD_BUTTON_ID).get_by_text("추가")
        self._scroll_into_view(add_button)
        add_button.click()
        page.wait_for_timeout(300)

        # 새로 추가된 행의 인덱스를 "추가 전 행 개수"로 계산하지 않는다 -- 이 그리드는
        # 화면 밖으로 스크롤된 앞쪽 행을 DOM에서 지우는 가상 스크롤(virtualization)을 써서
        # (실기록으로 확인: 위쪽 행이 안 보이면 개수 카운트가 실제보다 적게 나옴), 대신
        # "추가 직후 현재 DOM에 남아있는 행들 중 가장 큰 인덱스"를 새 행으로 본다 -- 방금
        # 추가된 행은 항상 렌더링돼 있다고 가정(맨 아래 행이라 보통 스크롤 안에 있음).
        row_index = page.evaluate(
            "() => Math.max(-1, ...[...document.querySelectorAll('[id]')]"
            ".map(e => (e.id.match(/_div_Cnstrc_grd_List_body_gridrow_(\\d+)$/)||[])[1])"
            ".filter(Boolean).map(Number))"
        )

        # 주의(실기록): 이 그리드는 클릭 사이에 짧은 지연 없이 연속으로 누르면 Nexacro가
        # 이전 클릭의 편집모드 전환을 못 끝내고 다음 클릭을 가로채는 경우가 있었다 --
        # 각 전환 뒤에 짧게 대기한다.
        occurrence_cell = page.locator(sel.major_hazard_cell(row_index, 2))
        self._scroll_into_view(occurrence_cell)
        # 이전 행에서 다루던 콤보/캘린더가 이 자리에 남아 클릭을 가로챌 수 있어(실기록)
        # force=True로 우회한다.
        occurrence_cell.click(force=True)
        page.wait_for_timeout(150)
        # 이 콤보 오버레이는 셀을 클릭할 때마다 Nexacro가 새로 만들고 이전 것을 DOM에서
        # 지우지 않는 듯하다 -- 여러 행을 다루면 같은 id를 가진 요소가 여러 개 남아
        # strict-mode 에러가 남. 가장 최근에 생긴 것(문서상 마지막)이 지금 활성화된
        # 것이라고 보고 `.last`로 선택한다.
        combo = page.locator(sel.MAJOR_HAZARD_WORK_CELL_COMBO_ID).last
        combo.click()
        page.wait_for_timeout(150)
        # 드롭다운 옵션 목록도 콤보의 하위 요소가 아니라 별도 오버레이라(combo.get_by_text로
        # 못 찾음, 실기록으로 확인) page 전체에서 찾아야 한다 -- 같은 이유로 이전 행에서
        # 골랐던 같은 텍스트가 쌓여있을 수 있어 `.last`로 지금 막 뜬 목록의 것을 클릭한다.
        page.get_by_text(occurrence_type, exact=True).last.click()
        page.wait_for_timeout(150)
        # 콤보를 닫지 않고 바로 다음(다른 열) 셀을 클릭하면 열려있는 콤보가 그 자리에 그대로
        # 남아 클릭을 가로챈다(실기록: 제목을 눌러도 안 풀림) -- 같은 행의 업무영역 칸(고정
        # 텍스트, 편집 불가)을 클릭하면 확실히 블러된다는 것을 실측으로 확인해 이걸 쓴다.
        blur_cell = page.locator(sel.major_hazard_cell(row_index, 1))
        blur_cell.click()
        page.wait_for_timeout(150)

        work_cell = page.locator(sel.major_hazard_cell(row_index, 3))
        self._scroll_into_view(work_cell)
        # 대형사고 위험작업 옵션 5개짜리 드롭다운 목록은 셀 "아래"로 펼쳐지는데, 셀이
        # 뷰포트 맨 아래쪽에 걸쳐 있으면 목록 일부가 화면 밖으로 잘려 긴 옵션명을 못 찾는다
        # (실기록) -- 이 셀만 위쪽 여유 공간이 더 생기도록 살짝 더 스크롤해둔다.
        page.mouse.wheel(0, 200)
        page.wait_for_timeout(150)
        # 주의(실기록): 발생형태 콤보를 고른 직후엔 공용 콤보 오버레이가 아직 이 열(3번)
        # 자리 위에 남아있어 일반 click()이 "다른 요소가 클릭을 가로챈다"며 계속 실패한다
        # (블러 클릭을 먼저 해도 동일) -- force=True로 실제 DOM 노드에 직접 이벤트를 보내면
        # 정상 동작함을 확인.
        work_cell.click(force=True)
        page.wait_for_timeout(150)
        work_cell.click(force=True)
        page.wait_for_timeout(150)
        page.get_by_text(hazard_work, exact=True).last.click()
        page.wait_for_timeout(150)
        blur_cell.click()
        page.wait_for_timeout(150)

        # 주의(실기록): "+ 추가"로 만든 새 행은 시작/종료일이 둘 다 오늘 날짜로 채워져
        # 있다 -- 시작일을 먼저 오늘보다 뒤로 바꾸면 그 순간 "시작일이 종료일보다 클 수
        # 없습니다" 경고창이 즉시 뜨면서 자동화가 막힌다(종료일이 아직 오늘 그대로라서).
        # 종료일을 먼저 바꾸면(목표 종료일은 항상 목표 시작일 이후이므로 오늘 날짜인
        # 시작일과 비교해도 걸리지 않음) 이 문제가 없다.
        for col, date in ((5, end_date), (4, start_date)):
            date_cell = page.locator(sel.major_hazard_cell(row_index, col))
            self._scroll_into_view(date_cell)
            # 앞서 다룬 캘린더가 아직 그 자리에 남아 있으면 다음 셀 클릭을 가로챈다(같은
            # controlcombo 이슈와 동일한 원인) -- force=True로 우회.
            date_cell.click(force=True)
            page.wait_for_timeout(150)
            page.locator(sel.MAJOR_HAZARD_WORK_CALENDAR_DROPBUTTON_ID).last.click()
            page.wait_for_timeout(150)
            self._pick_date_in_open_calendar(
                date,
                sel.MAJOR_HAZARD_WORK_CALENDAR_YEAR_ID, sel.MAJOR_HAZARD_WORK_CALENDAR_MONTH_ID,
                sel.MAJOR_HAZARD_WORK_CALENDAR_PREV_BUTTON_ID, sel.MAJOR_HAZARD_WORK_CALENDAR_NEXT_BUTTON_ID,
                sel.MAJOR_HAZARD_WORK_CALENDAR_DAY_CELLS,
            )
            blur_cell.click()
            page.wait_for_timeout(150)
