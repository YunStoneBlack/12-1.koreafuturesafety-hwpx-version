# -*- coding: utf-8 -*-
"""K2BClient: 로그인 -> 메뉴 이동 -> 현장 검색/선택(find_and_select_site — 화면 뒤 검색 결과 데이터로, site_match.py) -> 상세보기/차수 추가.
예전의 화면 글자 찾아 누르기(search_site·select_result_row)는 보이는 줄만 그려지는 그리드라 못 찾거나 다른 현장을 골라 10/8에 뺐다.

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

    def show_selected_row(self) -> None:
        """현장 선택 화면용(10/8) — 고른 줄(rowposition)이 결과 표에 보이게 표를 그 줄까지 내리고, 옆으로는 맨 왼쪽(현장명 칸)으로."""
        from server.k2b import site_match as sm
        self.page.evaluate(f"""() => {{
            const f = __k2bForm(); if (!f) return;
            const d = __k2bDs('{sm.LIST_DS}'); if (!d) return;
            const kids = (o) => (o && o.all) ? Object.keys(o.all).map(k => o.all[k]).filter(x => x && typeof x === 'object') : [];
            const walk = (o, depth) => depth > 4 ? [] : kids(o).flatMap(x => [x, ...walk(x, depth + 1)]);
            const grid = walk(f, 0).find(x => x.binddataset === '{sm.LIST_DS}' || (x._binddataset && x._binddataset.id === '{sm.LIST_DS}'));
            if (!grid) return;
            try {{ if (grid.scrollTo) grid.scrollTo(0, 0); }} catch (e) {{}}
            try {{ if (grid.setCellPos) grid.setCellPos(0); }} catch (e) {{}}
            try {{ if (grid.scrollToRow) grid.scrollToRow(d.rowposition); else if (grid.vscrollbar) grid.vscrollbar.set_pos(Math.max(0, d.rowposition - 1) * 24); }} catch (e) {{}}
        }}""")
        self.page.wait_for_timeout(500)
