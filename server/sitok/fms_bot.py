"""시특법 FMS 화면 채우기(Playwright) — 2026-10-15 연습 모드 → 같은 날 실제 제출(사용자 "시작", 민재형 흐름).

단계(stage):
- practice: 새 계약 일반현황만 채워 찍고 시설물·기술자를 FMS 목록과 대조. 쓰기로 보이는 요청은 브라우저에서 끊음(_guard) — 서버에 아무것도 안 감.
- practice_result(10/25): 계약 번호가 생긴 뒤의 연습 — 실적 수정 화면(계약 승인 뒤 열림)에 일반현황·시설물 실적 값을 채워 찍기만(goSave 안 누름),
  e-보고서 창은 용역 고르기 → 폴더 이름 확인까지(파일은 고르는 순간 올라갈 수 있어 안 고름). 같은 _guard.
- contract: 점검진단계약 등록(일반현황 저장 → 대상시설물 → 책임(참여)기술자) → 승인요청 → (관리주체 계정이 있으면) 관리주체 승인.
- result: 점검진단실적(수시보고) 일반현황 실제 기간 → 대상시설물 실적(주요결과·보수보강(안)·안전등급…) → e-보고서 파일 올리기 → 승인요청 → 관리주체 승인.
실제 단계도 알림창 글에 오류 말(입력하지·선택하지·일치하지 않…)이 있으면 그 자리에서 멈추고 화면을 남긴다(FmsError). 이미 만든 계약 번호(project_no)가 있으면
새로 만들지 않고 그 계약에서 이어서(이미 넣은 시설물은 건너뜀). stop_before_request = 승인요청 전에 멈춤(처음 몇 번 — 형이 FMS에서 보고 직접 승인요청).

FMS 함정(2026-10-15 실측): 로그인 양식이 두 개(loginForm·pLoginForm) — goLogin()은 loginForm을 읽음 / 같은 아이디로 새로 로그인하면 이전 세션(형 화면 포함)을
강제 종료 / 창을 닫으면 세션이 끝남 / 탭 내용은 anyMain.do 안의 iframe(any12001·13001·14001·15001_edit) / 참여업체 줄(const_amt0·design_amt0)에 쓰면
위 금액이 자동 / 정기는 분야 옆 regular_gbn(0106 상반기·0712 하반기) / 기술자 찾기 팝업은 우리 계약 번호가 있어야 목록 / 승인요청 = 상세 화면 goSignRequest()
(/esign/signRequest.do) / 관리주체 결재 = 결재대기 /esign/sgn01001_list.do → goDetail(msg_no, 종류) 창(sgn01002_select) — 승인 버튼은 관리주체 화면에만
(2026-10-15엔 못 봄 — 첫 실제 건에서 맞춤) / e-보고서 = doc.fms.or.kr 창(INNORIX 업로더: 용역 goSelect → 폴더 나무 고르기 → goFileDialog('FILE') → goSend()).
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path

from server.sitok import seasons

BASE = "https://www.fms.or.kr"
_WRITE = re.compile(r"(save|insert|update|delete|del\b|regist|reg\.do|apprv|approval|appr|request|req\b|confirm|complete|cmplt|submit|upload|send|trans)", re.I)
_SAFE = re.compile(r"(list|form|view|search|select|popup|pop|find|sch|redirectEx|loginForm|login\.do|actionLogin|mainForm|menu|code|combo|detail|info)", re.I)
_ERR = re.compile(r"입력하지|선택하지|일치하지|없습니다|잘못|오류|실패|초과할 수|이전이어야|이후이어야|확인하시기|필수|중복|불가능")
GRADE_NAME = {"1": "특급기술인", "2": "고급기술인", "3": "중급기술인", "4": "초급기술인"}
HALF_CODE = {"상반기": "0106", "하반기": "0712"}
FOLDERS = ["계약서 및 대가내역서", "과업지시서", "결과표", "보고서", "보고서 부록"]


class FmsError(RuntimeError):
    pass


class Job:
    """단계 기록 — 글(log)·화면(shots)·알림창(alerts)."""

    def __init__(self, shots: Path, real: bool):
        self.dir = shots
        self.real = real
        self.log: list[str] = []
        self.shots: list[str] = []
        self.alerts: list[str] = []
        self.blocked: list[str] = []
        shots.mkdir(parents=True, exist_ok=True)

    def say(self, msg: str) -> None:
        self.log.append(f"{datetime.datetime.now():%H:%M:%S} {msg}")

    def shot(self, pg, name: str) -> None:
        try:
            name = re.sub(r'[\\/:*?"<>|]', "_", name)  # "급식실/다목적관" — 파일 이름에 못 쓰는 글자(10/25, 안 바꾸면 폴더로 갈라짐)
            p = self.dir / f"{len(self.shots) + 1:02d}_{name}.png"
            pg.screenshot(path=str(p), full_page=True)
            self.shots.append(str(p))
        except Exception:  # noqa: BLE001 — 화면을 못 찍어도 일은 계속
            pass

    def watch(self, pg) -> None:
        pg.on("dialog", lambda d: (self.alerts.append(d.message.strip()[:300]), d.accept()))


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
    for attempt in range(3):  # 첫 화면 스크립트가 늦게 뜨는 때가 있음(goLoginPop 없음) — 기다리고, 안 되면 새로 고침
        pg.goto(f"{BASE}/com/mainForm.do", wait_until="domcontentloaded", timeout=60000)
        try:
            pg.wait_for_function("typeof window.goLoginPop === 'function'", timeout=15000)
            break
        except Exception:  # noqa: BLE001
            if attempt == 2:
                raise
    pg.wait_for_timeout(800)
    pg.evaluate("goLoginPop()")
    pg.wait_for_selector("#dialog-form #user_id", timeout=15000)
    pg.wait_for_timeout(600)
    try:  # 양식이 다 뜰 때까지(10/15 — 덜 뜬 페이지에서 loginForm이 없어 실패한 적 있음)
        pg.wait_for_function("!!((document.loginForm && document.loginForm.user_id) || (document.pLoginForm && document.pLoginForm.user_id))", timeout=15000)
    except Exception:  # noqa: BLE001
        pass
    use = pg.evaluate("""([i, w]) => { const f = (document.loginForm && document.loginForm.user_id) ? document.loginForm : document.pLoginForm;
        if (!f) return ''; f.user_id.value = i; f.pswd.value = w; return f === document.loginForm ? 'goLogin' : 'goPLogin'; }""", [user_id, pw])
    if not use:
        raise RuntimeError("FMS 로그인 양식을 찾지 못했습니다(FMS 화면이 바뀌었을 수 있음).")
    try:  # FMS가 느릴 때 화면 전환(load)이 30초를 넘김(10/15) — 문서가 뜨는 것까지만, 넘어도 실제 로그인 여부로 판단
        with pg.expect_navigation(timeout=60000, wait_until="domcontentloaded"):
            pg.evaluate(f"{use}()")
    except Exception:  # noqa: BLE001
        pass
    for _ in range(20):
        pg.wait_for_timeout(1000)
        try:
            if pg.locator("text=로그아웃").count() > 0:
                return True
        except Exception:  # noqa: BLE001 — 전환 중
            continue
    return False


def _frame(pg, part: str, wait_ms: int = 10000):
    end = datetime.datetime.now() + datetime.timedelta(milliseconds=wait_ms)
    while True:
        fr = next((f for f in pg.frames if part in f.url), None)
        if fr is not None or datetime.datetime.now() > end:
            return fr
        pg.wait_for_timeout(300)


def _set(fr, name: str, value) -> bool:
    """칸 값 넣기 + 화면 스크립트가 듣는 이벤트(쉼표·합계 계산) — 읽기 전용 날짜 칸도 값으로 넣음. 선택 칸에 없는 값이면 False."""
    return fr.evaluate("""([n, v]) => { const e = document.getElementsByName(n)[0] || document.getElementById(n); if (!e) return false;
        e.removeAttribute && e.removeAttribute('readonly'); e.value = v;
        if (e.tagName === 'SELECT' && e.value !== v) return false;
        ['input', 'keyup', 'change', 'blur'].forEach(t => e.dispatchEvent(new Event(t, {bubbles: true}))); return true; }""", [name, str(value)])


def _set_text(fr, name: str, text: str) -> str:
    """선택 칸에서 보기 글자로 고르기(코드를 모를 때 — 10/16 D등급 정기 구분 해빙기·우기·동절기). 고른 값, 없으면 ""."""
    return fr.evaluate("""([n, t]) => { const e = document.getElementsByName(n)[0] || document.getElementById(n); if (!e || e.tagName !== 'SELECT') return '';
        const o = [...e.options].find((x) => x.text.replace(/\\s/g, '').includes(t)); if (!o) return '';
        e.value = o.value; ['input', 'change', 'blur'].forEach(k => e.dispatchEvent(new Event(k, {bubbles: true}))); return o.value; }""", [name, text])


def _check(fr, name: str, on: bool) -> None:
    fr.evaluate("([n, on]) => { const e = document.getElementsByName(n)[0]; if (e && e.checked !== on) { e.click(); } }", [name, bool(on)])


def _act(job: Job, where, js: str, label: str, wait_ms: int = 3500, ok: str | None = None) -> None:
    """화면 함수 부르기(확인창은 [확인]) → 새 알림창에 오류 말이 있으면 멈춤(FmsError)."""
    n = len(job.alerts)
    try:
        where.evaluate(js)
    except Exception as e:  # noqa: BLE001 — 페이지가 넘어가며 끊기는 건 정상
        if "Execution context was destroyed" not in str(e) and "Target" not in str(e):
            raise FmsError(f"{label}: 화면 함수 오류 {str(e)[:150]}") from e
    page = where.page if hasattr(where, "page") else where
    page.wait_for_timeout(wait_ms)
    new = job.alerts[n:]
    job.say(f"{label}" + (f" — 알림: {' / '.join(a[:80] for a in new)}" if new else ""))
    bad = [a for a in new if _ERR.search(a) and not (ok and ok in a)]
    if bad:
        raise FmsError(f"{label}에서 FMS가 막음: {bad[0][:200]}")


def _popup_select(ctx, opener, open_js: str, match, wait_ms: int = 10000) -> str:
    """찾기 팝업 열기 → goSelect 줄 중 match(인자 목록)에 맞는 것 부르기(고르면 팝업이 닫힘) → 고른 goSelect 글."""
    with ctx.expect_page(timeout=15000) as pop:
        opener.evaluate(open_js)
    w = pop.value
    w.on("dialog", lambda d: d.accept())
    w.wait_for_load_state("domcontentloaded")
    _wait_select(w, wait_ms)
    sels = w.evaluate("() => [...document.querySelectorAll('[onclick^=\"goSelect\"], a[href^=\"javascript:goSelect\"]')].map(b => b.getAttribute('onclick') || b.getAttribute('href'))")
    hit = next((s for s in sels if match(re.findall(r"'([^']*)'", s))), None)
    if hit is None:
        if not w.is_closed():
            w.close()
        return ""
    try:
        w.evaluate(hit.replace("javascript:", ""))
    except Exception:  # noqa: BLE001
        pass
    opener_page = opener.page if hasattr(opener, "page") else opener
    opener_page.wait_for_timeout(1500)
    if not w.is_closed():
        w.close()
    return hit


def _norm_name(s: str) -> str:
    """이름 비교용 — 빈칸·㈜/(주) 차이 무시."""
    return re.sub(r"\s|\(주\)|㈜|주식회사", "", str(s or ""))


def _js_args(call: str) -> list[str]:
    """"goSelect('의정부도시공사','A1','…')" · 큰따옴표 "goSelect(\"…\")" 둘 다 → 인자 글자들."""
    return [m[2] for m in re.finditer(r"""(['"])(.*?)\1""", call or "")]


_OWNER_ROWS = """() => [...document.querySelectorAll('table tbody tr')].map(t => ({text: t.innerText.replace(/\\s+/g, ' ').trim(),
    first: ((t.cells && t.cells[0] && t.cells[0].innerText) || '').replace(/\\s+/g, ' ').trim(),
    sel: [...t.querySelectorAll('[onclick*="goSelect"], a[href*="goSelect"]')].map(a => a.getAttribute('onclick') || a.getAttribute('href'))[0] || ''})).filter(x => x.sel)"""


def _owner_search(w, owner_name: str) -> list[dict]:
    """검색칸에 이름 → 돋보기(검색 단추)를 눌러 검색(없으면 goSearch()) → 결과 표에 그 이름이 뜰 때까지(최대 10초) → 줄들.
    10/29 의정부도시공사: 예전엔 goSearch()를 부르고 바로 읽어, 결과가 바뀌기 전 표를 읽었을 수 있음(민재형 "돋보기를 눌러 검색해야")."""
    want = _norm_name(owner_name)
    w.fill("input[name=search_val]", owner_name)
    btn = None
    for css in ("[onclick*='goSearch']", "a[href*='goSearch']", "button.btn_search", "a.btn_search", "img[alt*='검색']", "button:has-text('검색')", "a:has-text('검색')"):
        try:
            btn = w.query_selector(css)
        except Exception:  # noqa: BLE001
            btn = None
        if btn is not None and btn.is_visible():
            break
        btn = None
    try:
        if btn is not None:
            btn.click()
        else:
            w.evaluate("goSearch()")
    except Exception:  # noqa: BLE001 — 누르는 순간 화면이 바뀌면(폼 전송) 여기로 — 그대로 기다림
        pass
    rows: list[dict] = []
    for _ in range(20):  # 0.5초씩 — 화면이 새로 뜨는 중이면 읽기가 실패할 수 있어 다시
        w.wait_for_timeout(500)
        try:
            w.wait_for_load_state("domcontentloaded", timeout=5000)
            rows = w.evaluate(_OWNER_ROWS)
        except Exception:  # noqa: BLE001
            continue
        if any(want and want in _norm_name(r["text"]) for r in rows):
            break
    return rows


def pick_owner(ctx, fr, owner_name: str, job=None) -> dict:
    """관리주체 찾기 팝업에서 이름이 똑같은 줄 고르기 → {ok, code, rows}. 못 찾으면 팝업 화면을 찍어 둠(job이 있으면)."""
    with ctx.expect_page(timeout=15000) as pop:
        fr.evaluate("document.querySelector('#btnFindMngMain').click()")
    w = pop.value
    w.on("dialog", lambda d: d.accept())
    w.wait_for_load_state("domcontentloaded")
    w.wait_for_timeout(1200)
    want = _norm_name(owner_name)
    hit, rows = None, []
    for _ in range(2):  # 결과가 늦게 뜨는 때가 있음 — 없으면 한 번 더 검색
        rows = _owner_search(w, owner_name)
        hit = next((r for r in rows if any(_norm_name(x) == want for x in _js_args(r["sel"]))), None) \
            or next((r for r in rows if _norm_name(r["first"]) == want), None)  # 고르기 인자에 이름이 없어도 첫 칸이 그 이름이면
        if hit:
            break
    out = {"ok": False, "rows": [r["text"][:80] for r in rows]}
    if hit:
        args = _js_args(hit["sel"])
        code = next((x for x in args if re.fullmatch(r"[A-Z]\d{3,}", x)), args[1] if len(args) > 1 else "")
        try:  # 고르면 팝업이 스스로 닫힘
            w.evaluate(hit["sel"].replace("javascript:", ""))
        except Exception:  # noqa: BLE001
            pass
        fr.page.wait_for_timeout(1500)
        out.update(ok=True, code=code)
    elif job is not None:
        job.shot(w, "관리주체_찾기_결과")
        job.say(f"관리주체 찾기 결과 {len(rows)}줄: " + (" / ".join(r["text"][:60] for r in rows[:5]) or "없음"))
    if not w.is_closed():
        w.close()
    return out


def _wait_select(w, ms: int = 10000) -> bool:
    try:
        w.wait_for_selector('[onclick^="goSelect"]', timeout=ms)
        return True
    except Exception:  # noqa: BLE001
        return False


_MARK = """(keys) => { let n = 0; document.querySelectorAll('[onclick^="goSelect"]').forEach((b) => {
  const s = b.getAttribute('onclick') || ''; if (keys.some((k) => k && s.includes("'" + k + "'"))) { const tr = b.closest('tr') || b; tr.style.background = '#FFF3B0'; n++; } }); return n; }"""  # 우리 줄 노랗게(찍기 전)


def lookup_facilities(ctx, owner_code: str, fms_nos: list[str], job=None) -> dict:
    """시설물 찾기 팝업(관리주체 기준) → {fms_no: {name, use, class, completed} | {missing}}. job을 주면(연습) 우리 시설물 줄을 노랗게 하고 화면을 찍음(10/25)."""
    w = ctx.new_page()
    sels = []
    for _ in range(3):  # 가끔 빈 표로 뜸 — 다시
        w.goto(f"{BASE}/popup/facilNoSearch.do?1=1&mng_main_cd={owner_code}&addColumn=vent_yn,facil_capacity&reqUrl=any13001", wait_until="domcontentloaded")
        _wait_select(w)
        sels = w.evaluate("() => [...document.querySelectorAll('[onclick^=\"goSelect\"]')].map(b => b.getAttribute('onclick'))")
        if sels:
            break
    if job is not None:
        try:
            w.evaluate(_MARK, fms_nos)
        except Exception:  # noqa: BLE001
            pass
        job.shot(w, "점검진단대상시설물_찾기(연습)")
    w.close()
    found = {}
    for s in sels:
        args = re.findall(r"'([^']*)'", s)
        if args:
            found[args[0]] = {"name": args[1], "use": args[2] if len(args) > 2 else "", "class": args[3] if len(args) > 3 else "", "completed": args[4] if len(args) > 4 else ""}
    return {no: found.get(no, {"missing": True}) for no in fms_nos} | {"_all": list(found)}


def lookup_engineers(ctx, names: list[str], project_no: str = "", corp_cd: str = "E02210", job=None) -> dict:
    """기술자 찾기 팝업 → {이름: {birth, grade(1 특급·2 고급…), grade_label, field(건축·토목·안전관리)}}.
    팝업은 우리 회사 계약 번호(project_no)가 있어야 회사 기술자 목록이 나옴(빈 검색·이름 검색만으론 빈 표 — 2026-10-15)."""
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
        if job is not None and rows:  # 연습 — 우리 기술자 줄 노랗게 찍기(10/25)
            try:
                w.evaluate(_MARK, names)
            except Exception:  # noqa: BLE001
                pass
            job.shot(w, "책임기술자_찾기(연습)")
        w.close()
        if rows:
            break
    return {n: rows.get(n, {"missing": True}) for n in names}


def _cell_after(fr, label: str) -> str:
    """표에서 이름칸(th) 오른쪽 칸 글(띄어쓰기 무시) — 일반현황의 대표자·전화번호(관리주체를 고르면 FMS가 채움)."""
    return fr.evaluate("""(lab) => { const n = s => (s || '').replace(/\\s/g, '');
        const th = [...document.querySelectorAll('th')].find(t => n(t.textContent) === n(lab) && t.nextElementSibling && t.nextElementSibling.tagName === 'TD');
        const td = th && th.nextElementSibling;  // 참여업체 표 머리줄의 "대표자"(옆도 th)는 건너뜀
        if (!td) return '';
        const inp = td.querySelector('input:not([type=hidden]), textarea');  // 읽기 전용 입력칸에 든 경우
        return ((inp && inp.value) || td.textContent || '').replace(/\\s+/g, ' ').trim(); }""", label)


def _company_page(b, job: Job, user_id: str, pw: str):
    ctx = b.new_context(viewport={"width": 1500, "height": 1100}, locale="ko-KR")
    if not job.real:
        ctx.route("**/*", _guard(job.blocked))
    pg = ctx.new_page()
    job.watch(pg)
    if not login(pg, user_id, pw):
        raise FmsError("FMS 회사 계정으로 로그인하지 못했습니다(아이디·비밀번호 확인).")
    for _ in range(2):  # 로그인이 바로 풀리는 때가 있음 — 목록이 안 뜨면 한 번 더
        pg.goto(f"{BASE}/maint/any01001_list.do", wait_until="domcontentloaded")
        pg.wait_for_timeout(1500)
        if pg.evaluate("typeof window.goWrite === 'function'"):
            break
        login(pg, user_id, pw)
    job.say("FMS 회사 계정 로그인(이전 접속은 FMS가 끊음)")
    return ctx, pg


def _fill_general(ctx, fr, c: dict, job=None) -> dict:
    """일반현황 탭 칸 채우기(계약·실적 공통) → {owner, fms_rep, fms_phone}."""
    for k in ("project_nm", "start_ymd", "end_ymd", "contract_ymd", "financing_ratio", "etc_comment"):
        if c.get(k) is not None:
            _set(fr, k, c[k])
    for k in ("divide_gbn", "bid_method", "eval_method", "contract_method", "price_method", "tech_field"):
        _set(fr, k, c[k])
    _set(fr, "financing_ratio0", c["financing_ratio"])
    _set(fr, "const_amt0", c["const_amt"])
    _set(fr, "design_amt0", c["design_amt"])
    out: dict = {}
    if not fr.evaluate("(document.getElementsByName('mng_main_cd')[0] || {}).value || ''"):
        out["owner"] = pick_owner(ctx, fr, c["mng_main_nm"], job)
        if not out["owner"].get("ok"):
            found = out["owner"].get("rows") or []
            raise FmsError(f"FMS 관리주체 찾기에서 \"{c['mng_main_nm']}\"를 못 찾았습니다 — "
                           + (f"찾기 결과 {len(found)}줄: {' / '.join(x[:40] for x in found[:3])}" if found else "찾기 결과가 비었습니다")
                           + " (찾기 창 화면을 남겼습니다). 이름이 맞으면 관리자에게 알려 주세요.")
    read = lambda i: fr.evaluate("(i) => ((document.getElementById(i) || {}).textContent || '').replace(/\\s+/g, ' ').trim()", i)  # noqa: E731
    for _ in range(10):  # 관리주체를 고르면 대표자·전화번호가 조금 뒤에 채워짐(<div id=mng_main_ceo·mng_main_tel>, 10/15 실측)
        out["fms_rep"] = read("mng_main_ceo") or _cell_after(fr, "대표자")
        if out["fms_rep"]:
            break
        fr.page.wait_for_timeout(500)
    out["fms_phone"] = read("mng_main_tel")
    return out


def _project_no(pg, wait_ms: int = 15000) -> str:
    end = datetime.datetime.now() + datetime.timedelta(milliseconds=wait_ms)
    while datetime.datetime.now() < end:
        for f in pg.frames:
            m = re.search(r"project_no=(E\d{6,})", f.url)
            if m:
                return m[1]
        v = pg.evaluate("(document.main && document.main.project_no && document.main.project_no.value) || ''")
        if v:
            return v
        pg.wait_for_timeout(500)
    return ""


def practice(payload: dict, user_id: str, pw: str, shots: Path) -> dict:
    """연습 모드 — 로그인 → 새 계약 일반현황 채우기(관리주체 팝업 포함) → 찍기 → 시설물·기술자 대조. 저장 안 함."""
    from playwright.sync_api import sync_playwright

    job = Job(shots, real=False)
    report: dict = {"blocked": job.blocked, "alerts": job.alerts}
    c = payload["contract"]
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx, pg = _company_page(b, job, user_id, pw)
        report["login"] = True
        m = re.search(r"goDetail\('(E\d+)'\)", pg.content())
        our_project = m[1] if m else ""  # 기술자 찾기 팝업에 필요(우리 회사 계약이면 아무거나 — 읽기만)
        pg.evaluate("goWrite()")
        pg.wait_for_load_state("domcontentloaded")
        fr = _frame(pg, "any12001_edit")
        pg.wait_for_timeout(2000)
        got = _fill_general(ctx, fr, c, job)
        report["owner"] = got.get("owner", {})
        report["fms_rep"], report["fms_phone"] = got.get("fms_rep", ""), got.get("fms_phone", "")
        pg.wait_for_timeout(1000)
        report["filled"] = fr.evaluate("""() => Object.fromEntries(['project_nm','start_ymd','end_ymd','contract_ymd','mng_main_nm','mng_main_cd','const_amt','design_amt',
            'divide_gbn','financing_ratio','bid_method','eval_method','contract_method','price_method','tech_field','const_amt0','design_amt0']
            .map(n => { const e = document.getElementsByName(n)[0] || document.getElementById(n); return [n, e ? (e.tagName === 'SELECT' ? e.options[e.selectedIndex].text.trim() : e.value) : null]; }))""")
        job.shot(pg, "계약_일반현황(연습)")
        code = report["owner"].get("code") or report["filled"].get("mng_main_cd") or ""
        report["facilities"] = lookup_facilities(ctx, code, [f["fms_no"] for f in payload["facilities"]], job=job) if code else {}
        report["engineers"] = lookup_engineers(ctx, [e["name"] for e in payload["engineers"]], our_project, job=job)
        b.close()  # 저장 안 하고 닫음(새 계약은 서버에 안 생김)
    report["shots"], report["log"] = job.shots, job.log
    return report


def practice_result(payload: dict, user_id: str, pw: str, shots: Path, project_no: str) -> dict:
    """실적 연습(10/25 민재형 "계약 등록하면 실적보고도 연습이 생기는지?") — 저장 안 함.
    → {target, editable, filled, facilities: {이름: {ok, grade, error}}, eboard: {found, folders, missing, facilities}, error, shots, log}."""
    from playwright.sync_api import sync_playwright

    job = Job(shots, real=False)
    report: dict = {"target": "result", "blocked": job.blocked, "alerts": job.alerts, "facilities": {}, "eboard": {}}
    c = payload["contract"]
    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            ctx, pg = _company_page(b, job, user_id, pw)
            pg.goto(f"{BASE}/maint/any11002_select.do?project_no={project_no}", wait_until="domcontentloaded")
            pg.wait_for_timeout(1500)
            report["editable"] = bool(pg.evaluate("typeof window.goEdit === 'function'"))
            if not report["editable"]:  # 계약 승인 전이거나 실적을 이미 승인요청함
                job.shot(pg, "실적_수정없음(연습)")
            else:
                pg.evaluate("goEdit()")
                pg.wait_for_load_state("domcontentloaded")
                fr = _frame(pg, "any12001_edit")
                pg.wait_for_timeout(2000)
                _fill_result_general(fr, c)
                report["filled"] = fr.evaluate("""() => Object.fromEntries(['start_ymd','end_ymd','const_amt0','design_amt0']
                    .map(n => { const e = document.getElementsByName(n)[0]; return [n, e ? e.value : null]; }))""")
                job.shot(pg, "실적_일반현황(연습)")
                for f in payload["facilities"]:
                    report["facilities"][f["name"]] = _practice_facility(pg, job, f)
                report["eboard"] = _practice_eboard(ctx, pg, job, payload)
        except Exception as e:  # noqa: BLE001 — 멈춘 자리까지 찍은 화면·기록은 남김
            report["error"] = next((ln.strip() for ln in str(e).splitlines() if ln.strip() and not ln.strip().startswith("=")), type(e).__name__)[:160]
            job.say(f"멈춤: {report['error']}")
        finally:
            b.close()  # 저장 안 하고 닫음
    report["shots"], report["log"] = job.shots, job.log
    return report


def _practice_facility(pg, job: Job, f: dict) -> dict:
    """실적 연습 — 실적 시설물 목록에서 하나 열어 값 채워 찍기(저장 안 함, 다음 시설물은 목록을 다시 열어서)."""
    pg.evaluate("goTabpage('2')")
    pg.wait_for_timeout(2500)
    fr2 = _frame(pg, "any13001")
    if not fr2.evaluate("typeof window.goEdit === 'function'"):
        return {"ok": False, "error": "실적 시설물 목록을 못 열었습니다"}
    fr2.evaluate(f"goEdit('{f['fms_no']}')")
    pg.wait_for_timeout(2500)
    fr2 = _frame(pg, "any13001")
    if not fr2.evaluate("!!document.getElementsByName('dign_content')[0]"):
        job.shot(pg, f"실적_시설물없음_{f['name']}(연습)")
        return {"ok": False, "error": f"FMS 실적 목록에 {f['fms_no']}가 없습니다"}
    grade = f.get("overall_grade") or ""
    ok = _fill_result_facility(fr2, f)
    job.shot(pg, f"실적_시설물_{f['name']}(연습)")
    return {"ok": ok, "grade": grade, **({} if ok else {"error": f"안전등급 \"{grade}\"을 FMS 선택지에서 못 골랐습니다"})}


def _practice_eboard(ctx, pg, job: Job, payload: dict) -> dict:
    """실적 연습 — e-보고서 창: 용역 고르기 → 폴더 이름·시설물 체크 칸 수 확인까지(파일은 안 고름)."""
    with ctx.expect_page(timeout=20000) as pop:
        pg.evaluate("goTabpage('6')")
    e = pop.value
    job.watch(e)
    e.wait_for_load_state("domcontentloaded")
    e.wait_for_timeout(4000)
    inx = _eboard_row(e, payload)
    if not inx:
        job.shot(e, "e보고서_용역없음(연습)")
        return {"found": False}
    e.evaluate(f"goSelect('{inx}', 'Y')")
    e.wait_for_timeout(4000)
    names = e.evaluate("""() => [...document.querySelectorAll("[id^='divTree_'][id$='_span']")].map(x => (x.textContent || '').trim())""")
    have = {re.sub(r"\s", "", x) for x in names}
    facs = e.evaluate("() => document.querySelectorAll('input[type=checkbox][name^=facil_no]').length")
    job.shot(e, "e보고서_폴더(연습)")
    return {"found": True, "folders": names, "missing": [f for f in FOLDERS if re.sub(r"\s", "", f) not in have], "facilities": facs}


# ---------- 실제 제출 ----------

def _contract_tabs(ctx, pg, job: Job, payload: dict, project_no: str) -> str:
    """계약 일반현황 저장 → 대상시설물 → 기술자. 이미 project_no가 있으면 그 계약을 수정 화면으로(이어서)."""
    c = payload["contract"]
    if project_no:
        pg.goto(f"{BASE}/maint/any01002_select.do?project_no={project_no}", wait_until="domcontentloaded")
        pg.wait_for_timeout(1500)
        if not pg.evaluate("typeof window.goEdit === 'function'"):
            raise FmsError(f"FMS 계약 {project_no}을 수정할 수 없습니다(이미 승인요청·승인됐을 수 있음).")
        pg.evaluate("goEdit()")
        job.say(f"이어서: FMS 계약 {project_no}")
    else:
        pg.evaluate("goWrite()")
    pg.wait_for_load_state("domcontentloaded")
    fr = _frame(pg, "any12001_edit")
    if fr is None:
        raise FmsError("일반현황 화면이 열리지 않았습니다.")
    pg.wait_for_timeout(2000)
    gen = _fill_general(ctx, fr, c, job)
    job.say(f"일반현황 채움 — FMS 대표자 {gen.get('fms_rep') or '-'}")
    job.shot(pg, "계약_일반현황")
    _act(job, fr, "goSave()", "일반현황 저장", wait_ms=4000)
    project_no = project_no or _project_no(pg)
    if not project_no:
        job.shot(pg, "계약번호_못받음")
        raise FmsError("일반현황을 저장했지만 FMS 계약 번호를 못 받았습니다 — FMS 목록에서 확인해 주세요.")
    job.say(f"FMS 계약 번호 {project_no}")
    # 대상시설물
    pg.evaluate("goTabpage('2')")
    fr2 = _frame(pg, "any13001")
    pg.wait_for_timeout(2500)
    have = set(fr2.evaluate("() => [...document.querySelectorAll('tr[facil_no]')].map(t => t.getAttribute('facil_no'))"))
    for f in payload["facilities"]:
        if f["fms_no"] in have:
            job.say(f"시설물 {f['name']} 이미 있음 — 건너뜀")
            continue
        fr2.evaluate("goWrite()")
        pg.wait_for_timeout(600)
        mng = fr2.evaluate("(document.getElementsByName('mng_main_cd')[0] || {}).value || ''")
        hit = _popup_select(ctx, fr2, "document.querySelector('#imgFacilFind').click()", lambda a, no=f["fms_no"]: bool(a) and a[0] == no)
        if not hit:
            raise FmsError(f"FMS 시설물 찾기에서 {f['name']}({f['fms_no']})를 못 찾았습니다{f' (관리주체 {mng})' if mng else ''}.")
        fr2 = _frame(pg, "any13001")
        _set(fr2, "dign_gbn", f["dign_gbn"])
        fr2.evaluate(f"typeof changeDignGbn === 'function' && changeDignGbn('{f['dign_gbn']}')")
        if seasons.is_season(f.get("half")):  # D등급 연 3회 — FMS 정기 구분 칸 보기가 해빙기·우기·동절기로 바뀜(형 10/16), 코드를 몰라 보기 글자로 고름
            if not _set_text(fr2, "regular_gbn", f["half"]):
                raise FmsError(f"FMS 정기 구분 칸에 '{f['half']}' 보기가 없습니다 — FMS에서 {f['name']} 시설물 등급(D·E)을 확인하세요.")
        elif f.get("half") in HALF_CODE:
            _set(fr2, "regular_gbn", HALF_CODE[f["half"]])
        for k in ("dign_amt", "design_amt", "base_amt"):
            _set(fr2, k, f[k])
        job.shot(pg, f"계약_시설물_{f['name']}")
        _act(job, fr2, "goSave()", f"시설물 {f['name']} 저장", wait_ms=4000)
        fr2 = _frame(pg, "any13001")
    # 기술자
    pg.evaluate("goTabpage('3')")
    fr3 = _frame(pg, "any14001")
    pg.wait_for_timeout(2500)
    _engineer_rows(ctx, pg, fr3, job, payload["engineers"], project_no)
    job.shot(pg, "계약_기술자")
    _act(job, _frame(pg, "any14001"), "goSave()", "기술자 저장", wait_ms=4000)
    return project_no


def _engineer_rows(ctx, pg, fr3, job: Job, engineers: list[dict], project_no: str) -> None:
    """기술자 줄 — 이름이 같은 줄은 고치고 없으면 줄을 더해 찾기 팝업에서 고름."""
    existing = fr3.evaluate("""() => { const out = {}; for (let i = 0; i < 40; i++) { const e = document.getElementsByName('engineer_nm' + i)[0]; if (e) out[i] = e.value; } return out; }""")
    used = set()
    for e in engineers:
        idx = next((int(i) for i, nm in existing.items() if nm == e["name"] and int(i) not in used), None)
        if idx is None:
            idx = next((int(i) for i, nm in existing.items() if not nm and int(i) not in used), None)
        if idx is None:
            fr3.evaluate("goAddTr()")
            pg.wait_for_timeout(500)
            existing = fr3.evaluate("""() => { const out = {}; for (let i = 0; i < 40; i++) { const e = document.getElementsByName('engineer_nm' + i)[0]; if (e) out[i] = e.value; } return out; }""")
            idx = max(int(i) for i in existing)
        used.add(idx)
        grade, field = e.get("tech_grade") or "", ""
        if existing.get(str(idx), existing.get(idx)) != e["name"]:
            hit = _popup_select(ctx, fr3, f"findEngineer('&project_no={project_no}&rownum={idx}')", lambda a, n=e["name"]: len(a) > 1 and a[1] == n)
            if not hit:
                raise FmsError(f"FMS 기술자 찾기에서 {e['name']}를 못 찾았습니다(FMS에 등록된 기술자인지 확인).")
            a = re.findall(r"'([^']*)'", hit)
            grade, field = (a[4] if len(a) > 4 else grade), (a[5] if len(a) > 5 else "")  # FMS에 등록된 등급·분야를 따름(민재형 10/15)
            fr3 = _frame(pg, "any14001")
        _set(fr3, f"rep_yn{idx}", e["rep_yn"])
        for k, v in (("start_ymd", e["start"]), ("end_ymd", e["end"]), ("parti_days", e["days"]), ("parti_rate", e["rate"])):
            _set(fr3, f"{k}{idx}", v)
        if grade:
            _set(fr3, f"tech_grade{idx}", grade)
        if field:  # 건축물: 안전관리 분야면 안전관리(건축), 나머지 건축 / 교량·터널은 (교량및터널)
            building = "(교량" not in e["parti_field"]
            e = {**e, "parti_field": ("안전관리(건축)" if "안전" in field else "건축") if building else (("안전관리" if "안전" in field else "토목") + "(교량및터널)")}
        if not _set(fr3, f"parti_field{idx}", e["parti_field"]):
            job.say(f"{e['name']} 직무분야 \"{e['parti_field']}\" 선택지가 없어 비워 둠")
        job.say(f"기술자 {e['name']}({'책임' if e['rep_yn'] == 'Y' else '참여'}) 줄 {idx}")


def _sign_request(pg, job: Job, detail_url: str, label: str) -> None:
    pg.goto(detail_url, wait_until="domcontentloaded")
    pg.wait_for_timeout(2000)
    if not pg.evaluate("typeof window.goSignRequest === 'function'"):
        job.shot(pg, f"{label}_승인요청없음")
        raise FmsError(f"{label} 화면에 승인요청 버튼이 없습니다(이미 승인요청했거나 승인됨).")
    _act(job, pg, "goSignRequest()", f"{label} 승인요청", wait_ms=4000, ok="승인요청되었습니다")
    job.shot(pg, f"{label}_승인요청")
    if not any("승인요청되었습니다" in a for a in job.alerts[-3:]):
        raise FmsError(f"{label} 승인요청 결과를 확인하지 못했습니다(마지막 알림: {job.alerts[-1][:80] if job.alerts else '없음'}).")


def owner_approve(b, job: Job, owner_id: str, owner_pw: str, project_nm: str, kind: str) -> None:
    """관리주체 계정으로 결재대기 → 그 용역 문서 → [승인]. kind = "점검진단계약" | "수시보고". 회사 계정과 다른 사람이라 회사 접속은 안 끊김."""
    ctx = b.new_context(viewport={"width": 1500, "height": 1100}, locale="ko-KR")
    pg = ctx.new_page()
    job.watch(pg)
    try:
        if not login(pg, owner_id, owner_pw):
            raise FmsError("관리주체 FMS 계정으로 로그인하지 못했습니다(시설물 카드의 관리주체 계정 확인).")
        job.say("관리주체 계정 로그인")
        hit = None
        for _ in range(4):  # 승인요청 직후엔 결재대기에 늦게 뜰 수 있음
            pg.goto(f"{BASE}/esign/sgn01001_list.do", wait_until="domcontentloaded")
            pg.wait_for_timeout(2000)
            rows = pg.evaluate("""() => [...document.querySelectorAll('table tbody tr')].map(t => ({text: t.innerText.replace(/\\s+/g, ' '),
                js: [...t.querySelectorAll('[onclick*="goDetail"]')].map(a => a.getAttribute('onclick'))[0] || ''})).filter(x => x.js)""")
            hit = next((r for r in rows if kind in r["text"] and re.sub(r"\s", "", project_nm)[:20] in re.sub(r"\s", "", r["text"])), None)
            if hit:
                break
            pg.wait_for_timeout(5000)
        if hit is None:
            job.shot(pg, "관리주체_결재대기")
            raise FmsError(f"관리주체 결재대기에 \"{project_nm}\" {kind} 승인요청이 없습니다.")
        call = re.search(r"goDetail\([^)]*\)", hit["js"])[0]
        with ctx.expect_page(timeout=15000) as pop:
            pg.evaluate(call)
        w = pop.value
        job.watch(w)
        w.wait_for_load_state("domcontentloaded")
        w.wait_for_timeout(2500)
        job.shot(w, f"관리주체_{kind}_문서")
        btn = w.evaluate("""() => { const b = [...document.querySelectorAll('button, a.btn, input[type=button]')].find(e => e.offsetParent !== null
            && /^승인$|^승 인$|^결재$/.test((e.textContent || e.value || '').replace(/\\s+/g, ' ').trim())); if (!b) return '';
            b.setAttribute('data-fms-approve', '1'); return (b.textContent || b.value || '').trim(); }""")
        if not btn:
            raise FmsError("관리주체 결재 화면에서 [승인] 버튼을 찾지 못했습니다 — 화면을 보고 맞추겠습니다(첫 실제 건).")
        n = len(job.alerts)
        w.click("[data-fms-approve='1']")
        w.wait_for_timeout(4000)
        new = job.alerts[n:]
        job.say(f"관리주체 {kind} 승인" + (f" — 알림: {' / '.join(a[:80] for a in new)}" if new else ""))
        if any(_ERR.search(a) for a in new):
            raise FmsError(f"관리주체 승인에서 FMS가 막음: {new[-1][:200]}")
        if not w.is_closed():
            job.shot(w, f"관리주체_{kind}_승인")
    finally:
        ctx.close()


def _fill_result_general(fr, c: dict) -> None:
    """실적 일반현황 — 실제 점검기간·금액(진짜 제출·연습 같이)."""
    for k in ("start_ymd", "end_ymd"):
        _set(fr, k, c[k])
    _set(fr, "const_amt0", c["const_amt"])
    _set(fr, "design_amt0", c["design_amt"])


def _fill_result_facility(fr2, f: dict) -> bool:
    """실적 시설물 한 곳 값 — 주요결과·보수보강(안)·중대결함·공중이용·안전등급·내진(진짜 제출·연습 같이). 등급을 못 고르면 False."""
    _set(fr2, "dign_content", f["dign_content"])
    _set(fr2, "amend_content", f["amend_content"])
    _check(fr2, "serious_defect_yn", f["serious_defect_yn"] == "Y")
    _check(fr2, "public_defect_yn", f["public_defect_yn"] == "Y")
    _check(fr2, "amend_req_yn", False)  # 형 PPT 13장 — 체크 안 함(체크하면 요약보고서 상태평가/보수보강안까지 필수)
    ok = fr2.evaluate("""(g) => { const s = document.getElementsByName('overall_grade')[0]; if (!s) return false;
        const o = [...s.options].find(o => o.value === g || o.text.trim().startsWith(g) || o.text.includes('(' + g + ')')); if (!o) return false;
        s.value = o.value; s.dispatchEvent(new Event('change', {bubbles: true})); return true; }""", f.get("overall_grade") or "")
    _set(fr2, "quake_target_yn", f.get("quake_target_yn") or "N")
    return bool(ok)


def _eboard_row(e, payload: dict) -> str:
    """e-보고서 창 용역 줄 번호 — 용역명 앞 20자가 든 줄(하나뿐이면 그 줄), 없으면 ""."""
    nm = re.sub(r"\s", "", payload["contract"]["project_nm"])
    return e.evaluate("""(nm) => { const rows = [...document.querySelectorAll("tr[id^='targetRow']")];
        const r = rows.find(t => t.innerText.replace(/\\s/g, '').includes(nm.slice(0, 20))) || (rows.length === 1 ? rows[0] : null);
        return r ? r.id.replace('targetRow', '') : ''; }""", nm)


def _result_tabs(ctx, pg, job: Job, payload: dict, project_no: str) -> None:
    """실적(수시보고) — 일반현황 실제 기간 저장 → 시설물마다 실적 값 저장."""
    pg.goto(f"{BASE}/maint/any11002_select.do?project_no={project_no}", wait_until="domcontentloaded")
    pg.wait_for_timeout(1500)
    if not pg.evaluate("typeof window.goEdit === 'function'"):
        job.shot(pg, "실적_수정없음")
        raise FmsError("실적보고 화면을 수정할 수 없습니다(계약 승인 전이거나 이미 승인요청됨).")
    pg.evaluate("goEdit()")
    pg.wait_for_load_state("domcontentloaded")
    fr = _frame(pg, "any12001_edit")
    pg.wait_for_timeout(2000)
    _fill_result_general(fr, payload["contract"])
    job.shot(pg, "실적_일반현황")
    _act(job, fr, "goSave()", "실적 일반현황 저장", wait_ms=4000)
    pg.evaluate("goTabpage('2')")
    pg.wait_for_timeout(2500)
    for f in payload["facilities"]:
        fr2 = _frame(pg, "any13001")
        fr2.evaluate(f"goEdit('{f['fms_no']}')")
        pg.wait_for_timeout(2500)
        fr2 = _frame(pg, "any13001")
        if not _fill_result_facility(fr2, f):
            raise FmsError(f"{f['name']} 안전등급 \"{f.get('overall_grade') or ''}\"을 FMS 선택지에서 못 골랐습니다.")
        job.shot(pg, f"실적_시설물_{f['name']}")
        _act(job, fr2, "goSave()", f"실적 {f['name']} 저장", wait_ms=4000)


def _eboard(ctx, pg, job: Job, payload: dict, files: list[dict], project_no: str) -> None:
    """e-보고서 — 실적 수정 화면 6탭 → doc.fms.or.kr 창 → 용역 고르기 → 시설물 체크 → 폴더마다 파일 → 전송."""
    pg.goto(f"{BASE}/maint/any11002_select.do?project_no={project_no}", wait_until="domcontentloaded")
    pg.wait_for_timeout(1500)
    pg.evaluate("goEdit()")
    pg.wait_for_load_state("domcontentloaded")
    pg.wait_for_timeout(2000)
    with ctx.expect_page(timeout=20000) as pop:
        pg.evaluate("goTabpage('6')")
    e = pop.value
    job.watch(e)
    e.wait_for_load_state("domcontentloaded")
    e.wait_for_timeout(4000)
    inx = _eboard_row(e, payload)
    if not inx:
        job.shot(e, "e보고서_용역없음")
        raise FmsError("e-보고서 창에 이 용역이 없습니다(실적 일반현황 저장 확인).")
    _act(job, e, f"goSelect('{inx}', 'Y')", "e-보고서 용역 고르기", wait_ms=4000)
    e.evaluate("() => document.querySelectorAll('input[type=checkbox][name^=facil_no]').forEach(c => { if (!c.checked) c.click(); })")
    by_folder: dict = {}
    for f in files:
        by_folder.setdefault(f["folder"], []).append(f["file"])
    for folder in FOLDERS:
        paths = by_folder.get(folder)
        if not paths:
            continue
        node = e.evaluate("""(name) => { const n = s => (s || '').replace(/\\s/g, ''); const sp = [...document.querySelectorAll("[id^='divTree_'][id$='_span']")]
            .find(x => n(x.textContent) === n(name)); if (!sp) return ''; sp.click(); return sp.id; }""", folder)
        if not node:
            raise FmsError(f"e-보고서 폴더 \"{folder}\"를 못 찾았습니다.")
        e.wait_for_timeout(800)
        with e.expect_file_chooser(timeout=15000) as fc:
            e.evaluate("goFileDialog('FILE')")
        fc.value.set_files(paths)
        e.wait_for_timeout(1500 + 300 * len(paths))
        job.say(f"e-보고서 {folder}: {len(paths)}개")
    job.shot(e, "e보고서_파일")
    _act(job, e, "goSend()", "e-보고서 전송", wait_ms=8000)
    for _ in range(120):  # 큰 파일 — 전송 끝날 때까지(최대 약 10분)
        done = e.evaluate("() => /전송\\s*완료|제출\\s*완료|완료되었습니다/.test(document.body.innerText)") if not e.is_closed() else True
        if done or any(re.search(r"완료|전송되었습니다|제출되었습니다", a) for a in job.alerts[-3:]):
            break
        e.wait_for_timeout(5000)
    if not e.is_closed():
        job.shot(e, "e보고서_전송")


def submit(stage: str, payload: dict, cred: tuple[str, str], owner: tuple[str, str] | None, shots: Path,
           project_no: str = "", files: list[dict] | None = None, stop_before_request: bool = False) -> dict:
    """실제 제출 — stage = contract | result. → {ok, project_no, step, message, log, shots, alerts, fms_rep}. 실패해도 예외 대신 ok=False."""
    from playwright.sync_api import sync_playwright

    job = Job(shots, real=True)
    out = {"ok": False, "project_no": project_no, "step": "", "message": ""}
    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            ctx, pg = _company_page(b, job, *cred)
            if stage == "contract":
                out["step"] = "계약 등록"
                out["project_no"] = project_no = _contract_tabs(ctx, pg, job, payload, project_no)
                if stop_before_request:
                    out.update(ok=True, step="계약 저장(승인요청 전 멈춤)", message="FMS에 계약을 저장했습니다 — FMS에서 확인한 뒤 승인요청하세요.")
                else:
                    out["step"] = "계약 승인요청"
                    _sign_request(pg, job, f"{BASE}/maint/any01002_select.do?project_no={project_no}", "계약")
                    if owner:
                        out["step"] = "관리주체 계약 승인"
                        owner_approve(b, job, *owner, payload["contract"]["project_nm"], "점검진단계약")
                        out.update(ok=True, step="계약 승인 완료", message="계약 등록·승인요청·관리주체 승인까지 했습니다.")
                    else:
                        out.update(ok=True, step="계약 승인요청", message="계약을 승인요청했습니다 — 관리주체 계정이 없어 승인은 관리주체가 직접 합니다.")
            elif stage == "result":
                if not project_no:
                    raise FmsError("FMS 계약 번호가 없습니다 — 먼저 [FMS 계약 등록]을 하세요.")
                out["step"] = "실적 입력"
                _result_tabs(ctx, pg, job, payload, project_no)
                if files:
                    out["step"] = "e-보고서 올리기"
                    _eboard(ctx, pg, job, payload, files, project_no)
                if stop_before_request:
                    out.update(ok=True, step="실적 저장(승인요청 전 멈춤)", message="실적과 e-보고서를 FMS에 넣었습니다 — FMS에서 확인한 뒤 승인요청하세요.")
                else:
                    out["step"] = "실적 승인요청"
                    _sign_request(pg, job, f"{BASE}/maint/any11002_select.do?project_no={project_no}", "실적")
                    if owner:
                        out["step"] = "관리주체 실적 승인"
                        owner_approve(b, job, *owner, payload["contract"]["project_nm"], "수시보고")
                        out.update(ok=True, step="실적 승인 완료", message="실적보고·e-보고서·승인요청·관리주체 승인까지 했습니다.")
                    else:
                        out.update(ok=True, step="실적 승인요청", message="실적을 승인요청했습니다 — 관리주체 계정이 없어 승인은 관리주체가 직접 합니다.")
            else:
                raise FmsError(f"모르는 단계: {stage}")
        except FmsError as e:
            out["message"] = str(e)
            try:
                job.shot(pg, "멈춘_화면")  # noqa: F821 — pg가 없으면 아래 except로
            except Exception:  # noqa: BLE001
                pass
        except Exception as e:  # noqa: BLE001
            out["message"] = f"{out['step'] or '시작'} 중 오류: {str(e)[:200]}"
        finally:
            b.close()
    out.update(log=job.log, shots=job.shots, alerts=job.alerts)
    return out
