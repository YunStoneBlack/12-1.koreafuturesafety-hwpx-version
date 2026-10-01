"""K2B 로그인 확인(2026-10-01) — 담당요원 탭 [로그인 확인]. 이 PC에서 화면 없는 크롬(Playwright)으로 K2B에 로그인만 해 보고 나온다(아무것도 제출 안 함).

- 성공 판단: 로그인 뒤 첫 화면의 "재해예방기관 기술지도" 메뉴가 보이면 성공(14번 프로젝트 CONFIRMED 흐름).
- 이름 확인: K2B는 로그인한 계정 이름이 보고서 "점검자"로 고정 입력된다 → 화면 글자에서 담당요원 이름을 찾고, 없으면 "○○님" 모양 이름을 찾아 알려 준다.
- 매번 화면을 `_시스템/k2b/`에 찍어 둔다(실패 이유·이름 위치 확인용 — 첫 실계정 시험 때 이름 칸을 정확히 맞출 것).
로그인 칸 위치는 server/k2b/selectors.py(14번에서 옮김), 입력 방식은 `server/k2b/base._type_into`와 같음 — Nexacro 입력칸은 .fill()이 이어붙는 문제가 있어
클릭 → 전체 선택·삭제 → 한 글자씩 입력. K2B 제출(server/k2b/runner.py)은 같은 칸으로 K2BClient.login을 쓴다.
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass

from core.db import DATA_DIR
from server.k2b import selectors as sel

# 로그인 칸 위치는 K2B 제출 코드와 한 곳에서(server/k2b/selectors.py — 14번에서 옮긴 CONFIRMED 값)
LOGIN_URL = sel.K2B_LOGIN_URL
LOGIN_ID_INPUT = sel.LOGIN_ID_INPUT
LOGIN_PW_INPUT = sel.LOGIN_PW_INPUT
LOGIN_BUTTON_TEXT = sel.LOGIN_BUTTON_TEXT
DASHBOARD_TEXT = "재해예방기관 기술지도"
SHOT_DIR = DATA_DIR / "_시스템" / "k2b"
# 실패 창 문구(실측 2026-10-01: "로그인 정보가 올바르지 않습니다.") — 로그인 화면 FAQ에도 같은 글이 있어서 누르기 전보다 **늘어난** 것만 본다
_FAIL_HINT = re.compile(r"[^\n]*(올바르지 않|일치하지 않|잠금|잠겼|횟수|만료|변경하|사용할 수 없)[^\n]*")


@dataclass
class LoginResult:
    status: str  # ok(이름 같음) | mismatch(로그인 됐지만 이름이 다름/못 찾음) | fail(로그인 안 됨)
    name: str  # K2B 화면에서 찾은 이름
    message: str
    screenshot: str


def _type_into(page, selector: str, text: str) -> None:
    field = page.locator(selector)
    field.wait_for(state="visible", timeout=30000)
    field.click()
    field.press("Control+A")
    field.press("Delete")
    field.press_sequentially(text, delay=30)


def _page_text(page) -> str:
    """화면 글자 + 글자 칸(textarea) 내용 — K2B(Nexacro) 알림 창 문구는 textarea 값으로 들어 있어 innerText로는 안 보인다(실측 2026-10-01)."""
    body = page.inner_text("body") if page.locator("body").count() else ""
    areas = page.eval_on_selector_all("textarea", "els => els.map(e => e.value)")
    return body + "\n" + "\n".join(a for a in areas if a)


def check_login(staff_id: int, k2b_id: str, password: str, expect_name: str, timeout_s: int = 40) -> LoginResult:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright

    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    shot = SHOT_DIR / f"login_staff_{staff_id}.png"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900}, locale="ko-KR")
            try:
                page.goto(LOGIN_URL, timeout=30000)
                _type_into(page, LOGIN_ID_INPUT, k2b_id)
                _type_into(page, LOGIN_PW_INPUT, password)
                before = [m.group(0).strip() for m in _FAIL_HINT.finditer(_page_text(page))]
                page.get_by_text(LOGIN_BUTTON_TEXT, exact=True).first.click()
            except (PlaywrightTimeout, PlaywrightError) as err:
                page.screenshot(path=str(shot))
                return LoginResult("fail", "", f"K2B 로그인 화면을 열지 못했습니다(사이트 점검·인터넷 확인): {str(err).splitlines()[0][:120]}", str(shot))
            # 1초마다: 첫 화면 메뉴가 보이면 성공, 실패 창 문구가 새로 생기면 바로 실패(끝까지 안 기다림)
            logged_in, reason = False, ""
            menu = page.get_by_text(DASHBOARD_TEXT, exact=True)
            for _ in range(timeout_s):
                page.wait_for_timeout(1000)
                if menu.count() and menu.first.is_visible():
                    logged_in = True
                    break
                lines = [m.group(0).strip() for m in _FAIL_HINT.finditer(_page_text(page))]
                new = [ln for ln in lines if ln not in before or lines.count(ln) > before.count(ln)]
                if new:
                    reason = new[0][:120]
                    break
            page.wait_for_timeout(1000)
            page.screenshot(path=str(shot))
            text = _page_text(page)
        finally:
            browser.close()
    if not logged_in:
        return LoginResult("fail", "", f"로그인 실패 — {reason or '시간 안에 K2B 첫 화면이 안 떴습니다(아이디·비밀번호 확인)'}", str(shot))
    # 계정 이름 = 첫 화면 오른쪽 위 "권태형님 | 접속유지시간"(실측 2026-10-01, 요원 4명 모두 확인) — 화면 어딘가에 이름이 있는 것만으론 판단하지 않는다
    found = re.search(r"([가-힣]{2,5})\s*님\s*\n?\s*\|?\s*접속유지", text) or re.search(r"([가-힣]{2,5})\s*님", text)
    name = found.group(1) if found else ""
    if expect_name and name == expect_name:
        return LoginResult("ok", name, f"로그인 성공 — K2B 점검자 이름이 '{name}'{_ro(name)} 담당요원과 같습니다.", str(shot))
    msg = (f"로그인은 됐지만 K2B 이름이 '{name}'{_ro(name)} 보입니다 — 이 계정으로 제출하면 점검자가 '{name}'{_ro(name)} 들어갑니다. 본인 계정인지 확인하세요."
           if name else "로그인은 됐지만 K2B 화면에서 담당요원 이름을 찾지 못했습니다 — 화면 사진으로 확인해 주세요.")
    return LoginResult("mismatch", name, msg, str(shot))


def _ro(word: str) -> str:
    """'으로'/'로' — 마지막 글자 받침(ㄹ 받침은 '로')."""
    jong = (ord(word[-1]) - 0xAC00) % 28 if word and "가" <= word[-1] <= "힣" else 0
    return "으로" if jong and jong != 8 else "로"


def now() -> datetime.datetime:
    return datetime.datetime.now().replace(microsecond=0)
