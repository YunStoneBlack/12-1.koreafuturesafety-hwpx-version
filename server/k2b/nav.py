# -*- coding: utf-8 -*-
"""K2BClient: 로그인 -> 메뉴 이동 -> 현장 검색/선택 -> 상세보기/차수 추가.

`core/k2b_client.py`의 600줄 초과 문제로 기능별 분리한 파일 중 하나(2026-09-16).
내용/셀렉터/실기록 주석은 원본에서 그대로 옮겼다."""
from __future__ import annotations

from server.k2b import selectors as sel
from server.k2b.selectors import K2B_LOGIN_URL
from server.k2b.base import K2BClientBase


class NavigationMixin(K2BClientBase):
    def login(self, user_id: str, password: str) -> None:
        self.log("K2B 로그인 중...")
        page = self.page
        page.goto(K2B_LOGIN_URL)
        self._type_into(sel.LOGIN_ID_INPUT, user_id)
        self._type_into(sel.LOGIN_PW_INPUT, password)
        page.get_by_text(sel.LOGIN_BUTTON_TEXT, exact=True).click()
        self.log("로그인 완료")

    def go_to_guidance_menu(self) -> None:
        """로그인 직후 대시보드("나의업무")의 "나만의 메뉴" 카드에서 "재해예방기관
        기술지도"를 바로 클릭한다(CONFIRMED, 실제 화면에서 단일 클릭으로 검색화면 도달
        확인됨) -- 로그인 후 첫 화면에서만 호출할 것(다른 화면에서는 같은 텍스트가
        사이드바 트리에도 나타나 모호할 수 있음)."""
        self.log("재해예방기관 기술지도 화면으로 이동 중...")
        self.page.get_by_text(sel.MENU_GUIDANCE_ITEM_TEXT, exact=True).click()

    def search_site(self, site_name: str) -> None:
        """현장명으로 검색한다.

        주의(실기록, 2026-09-16): K2B의 현장명 검색은 부분(substring) 일치는 지원하지만
        띄어쓰기 차이엔 전혀 관대하지 않다(실측 CONFIRMED: 원래 등록된 이름에서 공백을
        하나만 추가/제거/이동해도 결과 0건). 12-1과 K2B는 사람이 각각 따로 입력한 별개
        시스템이라 같은 현장이라도 이름 중간의 띄어쓰기가 서로 다르게 저장돼 있을 수 있다
        -- 전체 이름을 그대로 검색어로 쓰면 그 차이 때문에 검색 자체가 0건이 될 위험이
        있다. 대신 이름의 **첫 단어(공백 앞부분)만** 검색어로 써서 이 위험을 피한다 --
        짧은 substring도 정상적으로 결과를 찾아줌을 실측 확인(예: "태봉근린공원 조성사업
        (2단계) 토목공사" 전체 대신 "태봉근린공원"만 넣어도 같은 결과가 뜸). 최종적으로
        정확한 행을 고르는 건 `select_result_row()`가 전체 이름으로 다시 검증한다."""
        query = site_name.split()[0] if site_name.split() else site_name
        self.log(f"현장명 '{site_name}' 검색 중... (검색어: '{query}')")
        page = self.page
        self._type_into(sel.SEARCH_SITE_NAME_INPUT, query)
        page.locator(sel.SEARCH_BUTTON_CONTAINER_ID).get_by_text(sel.SEARCH_BUTTON_TEXT).click()

    def select_result_row(self, site_name: str) -> None:
        """검색 결과 그리드에서 현장명이 일치하는 행을 클릭해 선택한다(CONFIRMED, 체크박스
        불필요 -- 행 클릭만으로 아래 "재해예방 전문지도 기관"/"건설공사 발주자 등" 패널에
        해당 행 데이터가 로드됨을 실제 화면에서 확인).

        주의(실기록, 2026-09-16): 정확히 같은 문자열(`exact=True`)이 아니라 **양쪽 다
        공백을 전부 제거하고 비교**해서 고른다 -- 12-1/K2B 간 띄어쓰기 차이(위 `search_site`
        참고)에 안전하려는 목적. 공백만 무시하고 다른 글자 차이(오타 등)는 여전히 다른
        문자열로 구분됨을 실측 확인(예: "조성사업" vs "조선사업"은 공백을 지워도 여전히
        다름) -- 즉 진짜 같은 현장만 관대하게 봐주고, 비슷해 보이는 다른 현장을 잘못
        고르지는 않는다. 후보가 0개면 못 찾았다는 뜻이고, 2개 이상이면(예: K2B에 완전히
        동일한 이름이 중복 등록됨) 사람이 판단해야 하므로 둘 다 명확한 예외로 멈춘다."""
        self.log(f"검색결과에서 '{site_name}' 행 선택 중...")
        normalized_target = "".join(site_name.split())
        find_js = r"""
            (normalizedTarget) => {
                const all = [...document.querySelectorAll('div, span, td')];
                const results = [];
                for (const el of all) {
                    const txt = (el.textContent || '');
                    const normalized = txt.replace(/\s+/g, '');
                    if (normalized !== normalizedTarget) continue;
                    const hasElementChildWithText = [...el.children].some(
                        c => (c.textContent || '').trim()
                    );
                    if (hasElementChildWithText) continue;  // 텍스트를 가진 가장 안쪽(leaf) 요소만
                    const rect = el.getBoundingClientRect();
                    if (rect.width <= 0 || rect.height <= 0) continue;
                    results.push({
                        x: rect.x + rect.width / 2,
                        y: rect.y + rect.height / 2,
                        text: txt.trim(),
                    });
                }
                return results;
            }
            """
        # 주의(실기록, 2026-09-16): get_by_text().click()과 달리 page.evaluate()는 그 순간의
        # DOM 스냅샷만 한 번 검사하고 끝나서 Playwright의 자동 대기(actionability auto-wait)가
        # 적용되지 않는다 -- 검색 버튼 클릭 직후 결과 그리드가 아직 갱신되기 전에 검사하면
        # 0건으로 오판할 수 있다(실측으로 재현됨). 그리드 갱신을 기다리며 최대 10초간 재시도한다.
        candidates: list[dict] = []
        for _ in range(20):
            candidates = self.page.evaluate(find_js, normalized_target)
            if candidates:
                break
            self.page.wait_for_timeout(500)
        if not candidates:
            raise RuntimeError(
                f"검색결과에서 '{site_name}'와 일치하는 현장을 찾지 못했습니다 "
                f"(띄어쓰기를 무시하고 비교했는데도 못 찾음 -- 12-1과 K2B에 등록된 "
                f"이름 자체가 다를 수 있습니다. K2B 화면에서 직접 확인해보세요)."
            )
        if len(candidates) > 1:
            texts = ", ".join(f"'{c['text']}'" for c in candidates)
            raise RuntimeError(
                f"검색결과에서 '{site_name}'와 일치하는 행이 {len(candidates)}개 있어 "
                f"자동으로 고를 수 없습니다: {texts}. K2B 화면에서 직접 골라 진행하세요."
            )
        self.page.mouse.click(candidates[0]["x"], candidates[0]["y"])

    def open_detail(self) -> None:
        """선택된 행의 상세보기를 연다(CONFIRMED)."""
        self.log("상세보기 여는 중...")
        self.page.get_by_text(sel.DETAIL_VIEW_BUTTON_TEXT).click()

    def add_new_round(self) -> None:
        """새 차수를 추가한다. 기술지도일이 오늘 날짜로 자동 채워지고, 이후 다른 입력
        필드들이 활성화된다(현장에 등록된 차수가 없을 때 실기록으로 확인됨)."""
        self.log("차수 추가 중...")
        self.page.locator(sel.ADD_ROUND_BUTTON_ID).get_by_text(sel.ADD_ROUND_BUTTON_TEXT).click()

    # ---------- 화면 뒤 검색 결과 데이터로 현장 고르기(2026-10-08 — server/k2b/site_match.py 설명) ----------
    def find_and_select_site(self, key) -> "site_match.Pick":
        """검색어를 점점 짧게 바꿔 가며 검색 → 결과 데이터 전부에서 점수로 고름 → 데이터 줄 위치를 옮겨 선택 → 선택된 현장 데이터로 확인.
        맞는 게 안 되면 다음 후보·다음 검색어로 계속(사용자: 멈추지 말고 다시 찾아서 진행). 끝까지 못 찾을 때만 예외."""
        from server.k2b import site_match as sm
        page = self.page
        seen: list[str] = []
        for q in sm.queries(key.name):
            self.log(f"현장명 '{key.name}' 검색 중... (검색어: '{q}')")
            if not page.evaluate(sm.HELPERS_JS):
                raise RuntimeError("K2B 검색 화면의 데이터를 찾지 못했습니다(화면 구조가 바뀌었을 수 있음).")
            page.evaluate(f"() => {{ const d = __k2bDs('{sm.LIST_DS}'); if (d) d.clearData(); }}")
            self._type_into(sel.SEARCH_SITE_NAME_INPUT, q)
            page.locator(sel.SEARCH_BUTTON_CONTAINER_ID).get_by_text(sel.SEARCH_BUTTON_TEXT).click()
            rows: list = []
            for _ in range(16):  # 결과가 데이터에 들어올 때까지(0건이면 8초 뒤 다음 검색어)
                page.wait_for_timeout(500)
                rows = page.evaluate(f"(cols) => __k2bRows('{sm.LIST_DS}', cols)", sm.COLS) or []
                if rows:
                    page.wait_for_timeout(500)
                    rows = page.evaluate(f"(cols) => __k2bRows('{sm.LIST_DS}', cols)", sm.COLS) or rows
                    break
            self.log(f"검색 결과 {len(rows)}건")
            seen += [r[0] for r in rows[:5]]
            for p in sm.rank(key, rows):
                page.evaluate(f"(i) => __k2bDs('{sm.LIST_DS}').set_rowposition(i)", p.index)
                page.wait_for_timeout(1500)
                picked = page.evaluate(f"(cols) => __k2bRows('{sm.PICKED_DS}', cols)", sm.COLS) or []
                got = dict(zip(sm.COLS, picked[0])) if picked else {}
                if got and sm._plain(got.get("ENTRPS_NM")) == sm._plain(p.row["ENTRPS_NM"]) \
                        and sm._digits(got.get("BPLC_MNG_NO")) == sm._digits(p.row["BPLC_MNG_NO"]):
                    self.log(f"K2B 현장 선택: '{p.row['ENTRPS_NM']}' (공사금액 {int(sm._digits(p.row['CSTRN_AMT']) or 0):,}원 · "
                             f"맞은 것: {'·'.join(p.reasons)})")
                    return p
                self.log(f"'{p.row['ENTRPS_NM']}'을 골랐는데 선택이 바뀌지 않아 다음 후보로")
        names = ", ".join(f"'{n}'" for n in dict.fromkeys(seen)) or "없음"
        raise RuntimeError(f"K2B에서 '{key.name}' 현장을 찾지 못했습니다 — 이름·사업장 번호·공사금액·주소·공사 기간이 맞는 현장이 없음"
                           f"(검색된 현장 예: {names}). 웹 현장 정보와 K2B 등록 정보를 확인하세요.")
