# -*- coding: utf-8 -*-
"""K2BClient: 상세 모달의 기본 입력 필드(기술지도일/공정률/현장책임자/특이사항/
비계사용현황/현재작업공정/통보방법/이전 기술지도 이행여부).

`core/k2b_client.py`의 600줄 초과 문제로 기능별 분리한 파일 중 하나(2026-09-16).
내용/셀렉터/실기록 주석은 원본에서 그대로 옮겼다."""
from __future__ import annotations

import datetime

from server.k2b import selectors as sel
from server.k2b.base import K2BClientBase


class FieldsMixin(K2BClientBase):
    def set_guidance_date(self, target: datetime.date) -> None:
        """기술지도일을 캘린더 팝업에서 원하는 날짜(다른 달 포함)로 선택한다(CONFIRMED,
        같은 달/다른 달 이동 모두 실화면에서 검증)."""
        self.log(f"기술지도일을 {target.isoformat()}로 변경 중...")
        self.page.locator(sel.GUIDANCE_DATE_CALENDAR_BUTTON_ID).click()
        self._pick_date_in_open_calendar(
            target,
            sel.GUIDANCE_DATE_CALENDAR_YEAR_ID, sel.GUIDANCE_DATE_CALENDAR_MONTH_ID,
            sel.GUIDANCE_DATE_CALENDAR_PREV_BUTTON_ID, sel.GUIDANCE_DATE_CALENDAR_NEXT_BUTTON_ID,
            sel.GUIDANCE_DATE_CALENDAR_DAY_CELLS,
        )

    def fill_progress_rate(self, percent: int) -> None:
        self.log(f"공정률 {percent}% 입력 중...")
        self._type_into(sel.PROGRESS_RATE_INPUT_ID, str(percent))

    def fill_site_manager_name(self, name: str) -> None:
        self.log(f"현장책임자명 '{name}' 입력 중...")
        self._type_into(sel.SITE_MANAGER_NAME_INPUT_ID, name)

    def fill_site_manager_phone(self, phone: str) -> None:
        """현장책임자 연락처를 입력한다. 마스크 입력 필드라 하이픈 유무와 무관하게
        숫자만 뽑아서 순서대로 입력하면 "010-1234-5678" 형태로 자동 포맷된다(CONFIRMED).
        보고서에 "031-757-1930"/"0317571930" 두 표기가 섞여 나올 수 있어 숫자만 추출한다."""
        digits = "".join(ch for ch in phone if ch.isdigit())
        if not digits:
            return
        self.log(f"현장책임자 연락처 입력 중... ({digits})")
        self._type_into(sel.SITE_MANAGER_PHONE_INPUT_ID, digits)

    def fill_special_note(self, text: str) -> None:
        self.log("특이사항 입력 중...")
        self._type_into(sel.SPECIAL_NOTE_INPUT_ID, text)

    # 점검자(INSCTR_NM)는 CONFIRMED readonly -- 로그인 계정 이름이 자동 적용되고 화면에서
    # 수정 불가능하다(k2b_selectors.INSPECTOR_NAME_INPUT_ID 주석 참고). 그래서 이 클래스에
    # 점검자를 채우는 메서드가 의도적으로 없다. 담당요원별로 실제 별도 K2B 계정이 있음을
    # 고객이 확인해줬고(2026-09-16), 보고서의 담당요원 본인 명의 계정으로 로그인하는
    # 방식으로 이미 처리 중(desktop/main_window.py의 계정 자동 선택 로직 참고).

    def set_scaffold_usage(self, used: bool, types: list[str] | None = None) -> None:
        """비계사용현황을 설정한다. used=True면 "사용" 선택 후 types(예: ["강관비계"])의
        비계종류 체크박스도 켠다. used=False면 "미사용"만 선택(비계종류는 자동 비활성화됨,
        CONFIRMED).

        주의(실기록, 2026-09-16 실사용 중 발견): "사용"/"미사용" 텍스트가 페이지에 각각
        2개씩 존재한다 -- 하나는 화면에 안 보이는 다른 요소(id 없음, y좌표가 한참 아래,
        아마 다른 곳의 숨겨진 필터/옵션)이고, 실제 눈에 보이는 라디오는 **마지막(.last)**
        매치다. `.first`를 썼다가 엉뚱한(화면 밖) 요소를 클릭해 "Element is outside of
        the viewport" 오류로 자동입력이 중단되는 버그가 실사용 중 발생함 -- `.last`로
        고치고 실화면에서 정상 토글되는 것까지 재검증함.

        비계종류(강관비계/시스템비계) 체크박스도 처음엔 똑같은 함정에 빠졌었다: Day1에
        "상세모달이 아니라 검색화면(103015010) DOM 소속"이라고 잘못 기록해뒀던 id
        (`..._CURR_SCFDG_INSTL_STLE_CMMN_CD_5`)를 그대로 썼는데, 이 요소는 실제로 화면
        좌표가 모달 창 범위 밖(x=1120, 모달은 x=280~1000)에 있어서 Nexacro의 모달 배경
        딤(dim) 오버레이(z-index 1000002)에 항상 가려져 있었다 -- `document.
        elementFromPoint()`로 실측: 그 좌표를 클릭하면 체크박스가 아니라 오버레이가
        이벤트를 받음. 반면 사람이 화면을 보고 클릭하면 실제로 "보이는" 다른 요소(모달
        소속, id에 "CURR_" 없음, x=797)를 클릭하게 되므로 항상 성공했던 것 -- 셀렉터가
        가리키는 요소와 화면에 실제로 보이는 요소가 서로 달랐다. `k2b_selectors.py`에서
        모달 소속의 올바른 id로 수정한 뒤로는 다른 모달 체크박스와 동일하게 평범한
        `click()`만으로 정상 동작함(뷰포트 조작 등 우회 불필요, CONFIRMED)."""
        page = self.page
        if used:
            self.log("비계사용현황 '사용'으로 설정 중...")
            radio = page.get_by_text(sel.SCAFFOLD_USAGE_RADIO_GROUP_TEXT["사용"], exact=True).last
            self._scroll_into_view(radio)
            radio.click(force=True)
            for t in types or []:
                checkbox_id = sel.SCAFFOLD_TYPE_CHECKBOX_IDS.get(t)
                if checkbox_id is None:
                    raise ValueError(f"알 수 없는 비계종류: {t}")
                checkbox = page.locator(checkbox_id)
                self._scroll_into_view(checkbox)
                checkbox.click()
        else:
            self.log("비계사용현황 '미사용'으로 설정 중...")
            radio = page.get_by_text(sel.SCAFFOLD_USAGE_RADIO_GROUP_TEXT["미사용"], exact=True).last
            self._scroll_into_view(radio)
            radio.click(force=True)

    def select_current_process(self, process_name: str) -> None:
        self.log(f"현재 작업공정 '{process_name}' 선택 중...")
        page = self.page
        dropdown = page.locator(sel.CURRENT_PROCESS_DROPDOWN_ID)
        self._scroll_into_view(dropdown)
        dropdown.click()
        page.get_by_text(process_name, exact=True).first.click()

    def check_notification_method(self, method: str) -> None:
        """method: '직접전달' | '등기우편' | '전자우편' | '모바일' | '기타'"""
        checkbox_id = sel.NOTIFICATION_METHOD_CHECKBOX_IDS.get(method)
        if checkbox_id is None:
            raise ValueError(f"알 수 없는 통보방법: {method}")
        self.log(f"통보방법 '{method}' 체크 중...")
        checkbox = self.page.locator(checkbox_id)
        self._scroll_into_view(checkbox)
        checkbox.click()

    def check_prev_guidance_implemented(self, status: str) -> None:
        """status: '이행' | '불이행' | '해당없음' (세 옵션 모두 실제 클릭으로 CONFIRMED)"""
        checkbox_id = sel.PREV_GUIDANCE_IMPLEMENTED_CHECKBOX_IDS.get(status)
        if checkbox_id is None:
            raise ValueError(f"알 수 없는 이행여부: {status}")
        self.log(f"이전 기술지도 이행여부 '{status}' 체크 중...")
        checkbox = self.page.locator(checkbox_id)
        self._scroll_into_view(checkbox)
        checkbox.click()
