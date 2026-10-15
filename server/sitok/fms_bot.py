"""시특법 FMS 화면 채우기(Playwright) — 2026-10-15 연습 모드부터(사용자 "연습 모드 시작").

연습 모드(practice=True, 지금 유일하게 있는 모드):
- 쓰기로 보이는 요청(save·insert·update·delete·approval·request·upload·submit…)은 브라우저에서 끊는다(_guard) — 실수로 눌러도 서버에 안 감.
- 저장·작성완료·승인요청 버튼은 누르지 않는다. 채운 화면을 찍어 돌려준다.
- 새 계약 일반현황 탭을 값대로 채움(관리주체는 찾기 팝업에서 골라 코드까지), 시설물·기술자는 찾기 팝업에서 FMS 값과 대조
  (시설물·기술자 탭은 계약을 저장해야 열려서 연습 모드에선 화면을 못 띄움 — 넣을 값 표로 대신).
FMS 함정(2026-10-15 실측): 로그인 양식이 두 개(loginForm·pLoginForm) — goLogin()은 loginForm을 읽음 / 같은 아이디로 새로 로그인하면 이전 세션(형 화면 포함)을
강제 종료 / 창을 닫으면 세션이 끝나 저장한 쿠키로 다시 못 씀 / 일반현황 등 탭 내용은 anyMain.do 안의 iframe(any12001_edit.do 등) /
참여업체 줄(const_amt0·design_amt0)에 쓰면 위 계약·설계금액이 자동(형 PPT 3장).
"""
from __future__ import annotations

import re
from pathlib import Path

BASE = "https://www.fms.or.kr"
_WRITE = re.compile(r"(save|insert|update|delete|del\b|regist|reg\.do|apprv|approval|appr|request|req\b|confirm|complete|cmplt|submit|upload|send|trans)", re.I)
_SAFE = re.compile(r"(list|form|view|search|select|popup|pop|find|sch|redirectEx|loginForm|login\.do|actionLogin|mainForm|menu|code|combo|detail|info)", re.I)


def _guard(blocked: list):
    def f(route):
        r = route.request
        path = r.url.split("?")[0]
        if r.method == "POST" and _WRITE.search(path) and not _SAFE.search(path):
            blocked.append(r.url)
            return route.abort()
        return route.continue_()
    return f


def login(pg, user_id: str, pw: str) -> bool:
    pg.goto(f"{BASE}/com/mainForm.do", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(1500)
    pg.evaluate("goLoginPop()")
    pg.wait_for_selector("#dialog-form #user_id", timeout=15000)
    pg.wait_for_timeout(600)
    pg.evaluate("([i, w]) => { document.loginForm.user_id.value = i; document.loginForm.pswd.value = w; }", [user_id, pw])
    with pg.expect_navigation(timeout=30000):
        pg.evaluate("goLogin()")
    pg.wait_for_timeout(2500)
    return pg.locator("text=로그아웃").count() > 0


def _frame(pg, part: str):
    return next((f for f in pg.frames if part in f.url), None)


def _set(fr, name: str, value) -> None:
    """칸 값 넣기 + 화면 스크립트가 듣는 이벤트(쉼표·합계 계산) — 읽기 전용 날짜 칸도 값으로 넣음."""
    fr.evaluate("""([n, v]) => { const e = document.getElementsByName(n)[0] || document.getElementById(n); if (!e) return false;
        e.removeAttribute && e.removeAttribute('readonly'); e.value = v;
        if (e.tagName === 'SELECT' && e.value !== v) return false;
        ['input', 'keyup', 'change', 'blur'].forEach(t => e.dispatchEvent(new Event(t, {bubbles: true}))); return true; }""", [name, str(value)])


def pick_owner(ctx, fr, owner_name: str) -> dict:
    """관리주체 찾기 팝업에서 이름이 똑같은 줄 고르기 → {ok, code, name, rows}."""
    with ctx.expect_page(timeout=15000) as pop:
        fr.evaluate("document.querySelector('#btnFindMngMain').click()")
    w = pop.value
    w.wait_for_load_state("domcontentloaded")
    w.wait_for_timeout(1200)
    w.fill("input[name=search_val]", owner_name)
    w.evaluate("goSearch()")
    w.wait_for_timeout(2500)
    rows = w.evaluate("""() => [...document.querySelectorAll('table tbody tr')].map(t => ({text: t.innerText.replace(/\\s+/g, ' ').trim(),
        sel: [...t.querySelectorAll('[onclick^="goSelect"], a[href^="javascript:goSelect"]')].map(a => a.getAttribute('onclick') || a.getAttribute('href'))[0] || ''})).filter(x => x.sel)""")
    hit = next((r for r in rows if re.search(rf"'{re.escape(owner_name)}'", r["sel"])), None)
    out = {"ok": False, "rows": [r["text"][:80] for r in rows]}
    if hit:
        code = re.search(r"goSelect\('[^']*','([^']+)'", hit["sel"])
        try:  # 고르면 팝업이 스스로 닫힘
            w.evaluate(hit["sel"].replace("javascript:", ""))
        except Exception:  # noqa: BLE001
            pass
        fr.page.wait_for_timeout(1500)
        out.update(ok=True, code=code[1] if code else "")
    if not w.is_closed():
        w.close()
    return out


GRADE_NAME = {"1": "특급기술인", "2": "고급기술인", "3": "중급기술인", "4": "초급기술인"}


def _wait_select(w, ms: int = 10000) -> bool:
    try:
        w.wait_for_selector('[onclick^="goSelect"]', timeout=ms)
        return True
    except Exception:  # noqa: BLE001
        return False


def lookup_facilities(ctx, owner_code: str, fms_nos: list[str]) -> dict:
    """시설물 찾기 팝업(관리주체 기준) → {fms_no: {name, kind, grade_kind, completed, found}}."""
    w = ctx.new_page()
    sels = []
    for _ in range(3):  # 가끔 빈 표로 뜸 — 다시
        w.goto(f"{BASE}/popup/facilNoSearch.do?1=1&mng_main_cd={owner_code}&addColumn=vent_yn,facil_capacity&reqUrl=any13001", wait_until="domcontentloaded")
        _wait_select(w)
        sels = w.evaluate("() => [...document.querySelectorAll('[onclick^=\"goSelect\"]')].map(b => b.getAttribute('onclick'))")
        if sels:
            break
    w.close()
    found = {}
    for s in sels:
        args = re.findall(r"'([^']*)'", s)
        if args:
            found[args[0]] = {"name": args[1], "use": args[2] if len(args) > 2 else "", "class": args[3] if len(args) > 3 else "", "completed": args[4] if len(args) > 4 else ""}
    return {no: found.get(no, {"missing": True}) for no in fms_nos} | {"_all": list(found)}


def lookup_engineers(ctx, names: list[str], project_no: str = "", corp_cd: str = "E02210") -> dict:
    """기술자 찾기 팝업 → {이름: {birth, grade(1 특급·2 고급…), grade_label, field(건축·토목·안전관리)}}.
    팝업은 우리 회사 계약 번호(project_no)가 있어야 회사 기술자 목록이 나옴(빈 검색·이름 검색만으론 빈 표 — 2026-10-15).
    corp_cd = 우리 회사 진단기관 코드(E02210 — FMS goSelect 첫 값)."""
    rows: dict = {}
    for q in (f"&corp_cd={corp_cd}", f"&project_no={project_no}" if project_no else ""):
        if not q:
            continue
        w = ctx.new_page()
        w.on("dialog", lambda d: d.accept())
        w.goto(f"{BASE}/popup/engineerSearch.do?1=1&rownum=0{q}", wait_until="domcontentloaded")
        _wait_select(w, 5000)
        for sel in w.evaluate("() => [...document.querySelectorAll('[onclick^=\"goSelect\"]')].map(b => b.getAttribute('onclick'))"):
            a = re.findall(r"'([^']*)'", sel)
            if len(a) >= 6:
                rows[a[1]] = {"birth": a[2], "grade": a[4], "grade_label": GRADE_NAME.get(a[4], a[4]), "field": a[5]}
        w.close()
        if rows:
            break
    return {n: rows.get(n, {"missing": True}) for n in names}




def practice(payload: dict, user_id: str, pw: str, shots: Path) -> dict:
    """연습 모드 — 로그인 → 새 계약 일반현황 채우기(관리주체 팝업 포함) → 찍기 → 시설물·기술자 대조. 저장 안 함."""
    from playwright.sync_api import sync_playwright

    shots.mkdir(parents=True, exist_ok=True)
    blocked: list = []
    report: dict = {"blocked": blocked, "shots": []}
    c = payload["contract"]
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1500, "height": 1100}, locale="ko-KR")
        ctx.route("**/*", _guard(blocked))
        pg = ctx.new_page()
        alerts: list = []
        pg.on("dialog", lambda d: (alerts.append(d.message[:200]), d.accept()))
        report["alerts"] = alerts
        report["login"] = login(pg, user_id, pw)
        for attempt in range(2):  # 로그인이 바로 풀리는 때가 있음(짧은 간격으로 다시 로그인할 때) — 목록에 새로작성이 없으면 한 번 더
            pg.goto(f"{BASE}/maint/any01001_list.do", wait_until="domcontentloaded")
            pg.wait_for_timeout(1500)
            if pg.evaluate("typeof window.goWrite === 'function'"):
                break
            report["login"] = login(pg, user_id, pw)
        m = re.search(r"goDetail\('(E\d+)'\)", pg.content())
        our_project = m[1] if m else ""  # 기술자 찾기 팝업에 필요(우리 회사 계약이면 아무거나 — 읽기만)
        pg.evaluate("goWrite()")
        pg.wait_for_load_state("domcontentloaded")
        pg.wait_for_timeout(3000)
        fr = _frame(pg, "any12001_edit")
        for k in ("project_nm", "start_ymd", "end_ymd", "contract_ymd", "financing_ratio", "etc_comment"):
            _set(fr, k, c[k])
        for k in ("divide_gbn", "bid_method", "eval_method", "contract_method", "price_method", "tech_field"):
            _set(fr, k, c[k])  # 선택 칸도 이름 또는 id로(일부는 id만 있음)
        _set(fr, "financing_ratio0", c["financing_ratio"])
        _set(fr, "const_amt0", c["const_amt"])
        _set(fr, "design_amt0", c["design_amt"])
        report["owner"] = pick_owner(ctx, fr, c["mng_main_nm"])
        pg.wait_for_timeout(1500)
        got = fr.evaluate("""() => Object.fromEntries(['project_nm','start_ymd','end_ymd','contract_ymd','mng_main_nm','mng_main_cd','const_amt','design_amt',
            'divide_gbn','financing_ratio','bid_method','eval_method','contract_method','price_method','tech_field','const_amt0','design_amt0']
            .map(n => { const e = document.getElementsByName(n)[0] || document.getElementById(n); return [n, e ? (e.tagName === 'SELECT' ? e.options[e.selectedIndex].text.trim() : e.value) : null]; }))""")
        report["filled"] = got
        # 저장 버튼이 보내는 주소(안전장치 확인용) — goSave 안의 .do 주소들
        report["save_targets"] = sorted(set(re.findall(r"['\"]([^'\"]*\.do[^'\"]*)['\"]", fr.evaluate("String(window.goSave) + String(window.goCancel || '')"))))
        pg.screenshot(path=str(shots / "1_계약_일반현황.png"), full_page=True)
        report["shots"].append("1_계약_일반현황.png")
        code = report["owner"].get("code") or got.get("mng_main_cd") or ""
        report["facilities"] = lookup_facilities(ctx, code, [f["fms_no"] for f in payload["facilities"]]) if code else {}
        report["engineers"] = lookup_engineers(ctx, [e["name"] for e in payload["engineers"]], our_project)
        b.close()  # 저장 안 하고 닫음(새 계약은 서버에 안 생김)
    return report
