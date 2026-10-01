"""K2B(k2b.kosha.or.kr) 브라우저 자동화.

Playwright 자체 Chromium을 사용(CDP로 기존 크롬에 붙는 방식 아님) — 로컬에서는 headed로
개발/검증하고, 나중에 서버(AWS)로 옮길 때 headless=True만 바꾸면 그대로 동작하도록 설계.

웹판(2026-10-01): 이 클라이언트는 입력·첨부까지(14번 그대로). **저장 누르기·확인 창·저장 뒤 화면 찍기는
server/k2b/runner.py**가 한다(코하이젠 시험 6차수로 실측 — 사용자 결정: 저장까지 자동).

중요(실사용 중 발견): 이 사이트는 Nexacro 기반이라 상세 모달 전체가 하나의 거대한
절대좌표(absolute positioning) 패널로 그려진다 — 일반적인 `overflow:scroll` 컨테이너가
아니라서 Playwright의 자동 "스크롤해서 보이게 하기"(`scrollIntoViewIfNeeded`)가 먹히지
않는다. 화면 아래쪽 요소(사진첨부/보고서 파일첨부 등)를 클릭하기 전에는 반드시
`_scroll_into_view()`로 실제 마우스 휠 이벤트를 보내 스크롤해야 한다 — 안 그러면
"Timeout ... waiting for event 'filechooser'"류 오류가 난다(버튼 자체가 화면 밖에 있어
클릭이 씹힘).

리팩토링 메모(2026-09-16): 이 파일이 600줄을 넘어서 기능별로 `core/k2b_client_*.py`
mixin 파일로 나눴다 -- `K2BClient`는 그 mixin들을 전부 합쳐 상속하기만 한다. 동작/셀렉터/
실기록 주석은 그대로이고, `from core.k2b_client import K2BClient, open_browser, ...`
같은 기존 임포트 경로는 전부 그대로 동작한다(이 파일이 재수출함).
  - `k2b_client_base.py`: 공통 상태(`self.page`/`self.log`)와 헬퍼(스크롤/타이핑/캘린더)
  - `k2b_client_nav.py`: 로그인/메뉴이동/검색/행선택/상세보기/차수추가
  - `k2b_client_fields.py`: 기술지도일/공정률/현장책임자/특이사항/비계사용현황/
    현재작업공정/통보방법/이전 기술지도 이행여부
  - `k2b_client_hazard.py`: 대형사고 위험작업 그리드
  - `k2b_client_attachments.py`: 불량사업장 통보, 사진/보고서 파일 첨부
"""

from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

from server.k2b.attachments import AttachmentMixin
from server.k2b.base import K2BClientBase, LogFn, ReportModificationExpiredError
from server.k2b.fields import FieldsMixin
from server.k2b.hazard import HazardWorkMixin
from server.k2b.nav import NavigationMixin

__all__ = [
    "K2BClient",
    "LogFn",
    "ReportModificationExpiredError",
    "open_browser",
]


class K2BClient(NavigationMixin, FieldsMixin, HazardWorkMixin, AttachmentMixin, K2BClientBase):
    """K2B 화면 자동화 — 로그인부터 필드 입력/사진 첨부까지(저장은 server/k2b/runner.py).

    실제 메서드는 전부 위 mixin들에 있다(각 파일의 docstring/주석 참고)."""



def _find_system_chrome() -> str | None:
    """고객 PC에 이미 설치된 구글 크롬 실행파일을 찾는다.

    exe로 배포할 때 Playwright 번들 Chromium(150MB+)을 통째로 넣지 않기 위해, 가능하면
    시스템에 이미 있는 크롬을 그대로 제어한다(`chromium.launch(executable_path=...)`).
    못 찾으면 None을 반환하고, 그때는 Playwright 번들 Chromium으로 폴백한다(로컬 개발
    환경엔 `playwright install chromium`으로 이미 설치돼 있어 그대로 동작함)."""
    candidates = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return None


def open_browser(headless: bool = False):
    """Playwright를 시작하고 브라우저/페이지를 연다.

    사용 예:
        playwright, browser, page = open_browser()
        try:
            client = K2BClient(page, log=print)
            client.login(user_id, password)
            ...
        finally:
            browser.close()
            playwright.stop()
    """
    playwright = sync_playwright().start()
    chrome_path = _find_system_chrome()
    launch_kwargs = {"headless": headless}
    if chrome_path:
        launch_kwargs["executable_path"] = chrome_path
    browser = playwright.chromium.launch(**launch_kwargs)
    # 주의(2026-09-16, 시도했다가 되돌림): 한때 비계종류 체크박스가 기본 720px 뷰포트
    # 밖에 있다고 보고 뷰포트를 1280x1200으로 키워봤는데, 그러면 대형사고 위험작업의
    # 발생형태 콤보(y=1097)가 반응을 멈추는 부작용이 있었다(Nexacro가 "화면에 보이는
    # 범위"를 내부적으로 720px 기준으로 처리하는 것으로 추정). 나중에 알고보니 애초에
    # 비계종류 체크박스가 뷰포트 밖에 있다는 진단 자체가 틀렸다(실제로는 셀렉터가 화면에
    # 안 보이는 다른 요소를 가리키고 있었을 뿐 -- k2b_selectors.py의
    # SCAFFOLD_TYPE_CHECKBOX_IDS 주석 참고). 그래서 뷰포트는 항상 기본값 그대로 둔다.
    context = browser.new_context()
    page = context.new_page()
    return playwright, browser, page
