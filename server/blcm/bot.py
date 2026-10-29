"""건축물 생애이력관리시스템(blcm.go.kr) 입력 봇(2026-10-29 4단계, 사용자 "시작") — 우리 건(BlcmJob) 결과를 사이트 보고서작성 화면에 넣음.

단계(mode):
- list: 로그인 → 점검현황(정기점검) 목록 읽기(쪽 1~8) → 로그아웃. 사이트 보고서 고르기용, 아무것도 안 씀.
- practice: 고른 보고서(작성중)를 열어 소항목 상세 창마다 칸을 읽고 우리 값으로 채워 보기만 — 쓰기 요청은 브라우저에서 끊음(guard), 저장 안 누름.
  관리계획·그 밖의 항목·의견·점검기관 칸도 채워 보고 화면을 찍음. 상세 창 칸 짜임(schema)은 저장해 다음 고침에 씀.
- save: 같은 채우기 + 상세 창마다 [저장](사진 올리기 포함) + 관리계획·그 밖의 항목·의견 [전체저장]. **[점검보고서 제출]은 누르지 않음** — 사람이 사이트에서 보고 직접.

사이트 함정(10/29 실측, 핵심기술 43절): hashMap.js가 전역 Map을 덮어써 Playwright 선택자·evaluate가 깨짐 → CDP Runtime.evaluate로만 읽고 누름 /
로그인 5번 틀리면 잠김 → 실패 답이 오면 다시 안 함 / 같은 아이디 새 로그인은 다른 사람(형) 접속을 끊을 수 있음 → 한 번에 하나, 사람이 누를 때만 /
미실시('01') 보고서는 열면 새 보고서가 생김 → 열지 않음 / [전체삭제]가 저장 단추 옆 → 함수 이름으로만 부름.
상세 창 칸 번호: 소항목 S(대·중·소 세 자리, 예 111) — S0 현행기준 비교(개선필요 101·해당없음 102), S00 설계도서 적합여부(적합 111·부적합 112·도면없음 113·해당없음 115),
S1~S7 세부 판정(적합 141·부적합 143·해당없음 145 / 양호 151·보통 153·미흡 155·불량 157·해당없음 159 / 인증 161·재인증 163·만료 165·해당없음 167),
S8 개선사항(위법)·S9 성능개선사항, 점검현황(#detlItemHtml 체크·글 — 우리 항목표 status 조각 차례와 같음), 현황사진 = .blcmFile[data-file-job-cd=FL0310](고르는 순간 올라감).
값은 번호가 아니라 라벨 글자(양호·적합…)로 고름 — 번호가 바뀌어도 맞게."""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

from server.blcm import items as I

BASE = "https://blcm.go.kr"
LOGIN_URL = f"{BASE}/blcm/com/uat/memb/blcmLoginCnfirm.do"
LIST_URL = f"{BASE}/blcm/mcm/chkmgmcmmn/chkoprtntrgetbldmgm/selectFdrmchkTrgetCheInfoList.do"
LOGOUT_URL = f"{BASE}/uat/uia/actionLogout.do"
# 연습 때 끊는 요청 — GET 말고(POST 등) 쓰기로 보이는 것 전부 + 모르는 것 전부. 로그인·조회·창 열기만 통과.
# 10/29 첫 연습: "del[A-Z]"가 selectCmmCodeList의 "deL"에 걸려 코드 조회를 막음("정보 조회에 실패") → delete만. 세션 확인(sessionCheck)은 통과.
_WRITE = re.compile(r"(update|insert|save|delete|upload|file|regist|submit|apply|modify|trsct|send|remove|caption)", re.I)
_SAFE = re.compile(r"(blcmLogin\.do|loginProc|Logout|rsa|Pswd|returnUrl|select\w*\.do|List\.do|detlItem\.do|pop/|search|getCode|cmmCode|sessionCheck)", re.I)
_ERR = re.compile(r"입력|선택|필수|확인|오류|실패|잘못|없습니다|불가|초과")
RUN_DIR = None  # 화면 저장 폴더(worker가 정함)


class BlcmError(RuntimeError):
    pass


class Run:
    """한 번 돌린 기록 — 글(log)·화면(shots)·알림창(alerts)·끊은 요청(blocked)."""

    def __init__(self, out: Path, mode: str):
        self.out, self.mode = out, mode
        self.log: list[str] = []
        self.shots: list[str] = []
        self.alerts: list[str] = []
        self.blocked: list[str] = []
        self.items: dict[str, dict] = {}
        self.tried_login = False
        out.mkdir(parents=True, exist_ok=True)

    def say(self, msg: str) -> None:
        self.log.append(f"{datetime.datetime.now():%H:%M:%S} {msg}")

    def shot(self, pg, name: str) -> None:
        try:
            p = self.out / f"{len(self.shots) + 1:02d}_{name}.png"
            pg.screenshot(path=str(p), full_page=True)
            self.shots.append(p.name)
        except Exception:  # noqa: BLE001 — 화면을 못 찍어도 일은 계속
            pass

    def out_dict(self) -> dict:
        return {"log": self.log[-300:], "shots": self.shots, "alerts": self.alerts[-80:], "blocked": len(self.blocked),
                "blocked_urls": sorted({u.split("?")[0] for u in self.blocked})[:30], "items": self.items}


def _guard(run: Run):
    def f(route):
        r = route.request
        path = r.url.split("?")[0]
        if r.method != "GET" and (_WRITE.search(path) or not _SAFE.search(path)):
            run.blocked.append(r.url)
            return route.abort()
        return route.continue_()
    return f


def ev(cdp, expr: str):
    """사이트 스크립트를 그대로 둔 채 값 읽기·함수 부르기(Playwright evaluate는 사이트의 Map 덮어쓰기로 깨짐)."""
    r = cdp.send("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
    if "exceptionDetails" in r:
        d = r["exceptionDetails"]
        raise BlcmError(f"화면 스크립트 오류: {d.get('text', '')} {str(d.get('exception', {}).get('description', ''))[:160]}")
    return r.get("result", {}).get("value")


def _wait(pg, ms: int) -> None:
    pg.wait_for_timeout(ms)


def _dialogs(pg, run: Run, where: str = "") -> None:
    """알림·확인창은 글을 적고 확인(저장하시겠습니까? 포함 — 저장은 save 단계에서만 부르므로)."""
    def on(d):
        run.alerts.append(f"{where}{d.message.strip()[:300]}")
        try:
            d.accept()
        except Exception:  # noqa: BLE001
            pass
    pg.on("dialog", on)


def login(ctx, pg, cdp, run: Run, user_id: str, pw: str) -> None:
    """로그인 한 번 — 실패 답(SUCS 아님)이면 다시 시도하지 않고 멈춤(5번 틀리면 계정 잠김).
    답 본문은 길목(route)에서 받아 읽음 — response 이벤트로 읽으면 사이트가 곧바로 다음 화면으로 넘어가 본문이 사라짐(10/29 첫 연습: 성공했는데 "답 없음"으로 멈춤).
    그래도 못 읽으면 화면으로 판정: 비밀번호 변경 안내(PswdDateChk)나 로그인 화면 밖이면 성공, 로그인 화면 그대로면 실패."""
    status: dict = {}

    def on_login(route):
        try:
            resp = route.fetch()
            try:
                j = resp.json()
                status.update({k: j.get(k) for k in ("loginStatus", "escala", "cntOfpswdFail")})
            except Exception as e:  # noqa: BLE001
                status["err"] = str(e)[:80]
            route.fulfill(response=resp)
        except Exception as e:  # noqa: BLE001
            status["err"] = str(e)[:80]
            route.continue_()
    ctx.route("**/blcmLogin.do*", on_login)
    pg.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
    for _ in range(20):
        _wait(pg, 500)
        if ev(cdp, "!!document.querySelector('#membId') && typeof checkIdPw === 'function'"):
            break
    else:
        raise BlcmError("로그인 화면을 못 열었습니다(사이트가 바뀌었거나 느림) — 로그인은 시도하지 않았습니다.")
    run.tried_login = True
    ev(cdp, f"document.querySelector('#membId').value = {json.dumps(user_id)}; document.querySelector('#pw').value = {json.dumps(pw)}; checkIdPw(); 1")
    for _ in range(40):
        _wait(pg, 500)
        if status.get("loginStatus") or "PswdDateChk" in pg.url or "LoginCnfirm" not in pg.url:
            break
    try:
        ctx.unroute("**/blcmLogin.do*")
    except Exception:  # noqa: BLE001
        pass
    st = status.get("loginStatus")
    moved = "PswdDateChk" in pg.url or "LoginCnfirm" not in pg.url
    run.say(f"로그인 답: {status or '본문 못 읽음'} · 화면 {pg.url.split('/')[-1][:40]}")
    if st and st != "SUCS" or (not st and not moved):
        raise BlcmError(f"생애이력시스템 로그인이 안 됐습니다({st or '답 없음'}{', 틀린 횟수 ' + str(status.get('cntOfpswdFail')) if status.get('cntOfpswdFail') else ''}) — "
                        "계정 잠김을 막으려고 다시 시도하지 않습니다. 설정의 아이디·비밀번호를 확인하세요.")
    if status.get("escala") == "Y":
        raise BlcmError("로그인 뒤 동의 창이 떴습니다 — 사이트에서 한 번 직접 로그인해 동의한 뒤 다시 하세요.")
    settle(pg, cdp, run)
    run.say("로그인")


def settle(pg, cdp, run: Run | None = None, seconds: int = 15) -> None:
    """화면이 멈출 때까지 — 로그인 뒤 첫 화면(mainPage)이 잠깐 떴다가 "오래된 비밀번호 변경"(PswdDateChk)으로 넘어감(10/29 두 번째 연습: 첫 화면만 보고
    넘어가 목록이 0줄). 이 안내가 보이면 [다음에 변경하기](returnUrl) — 누르기 전엔 어느 화면으로 가도 다시 이 안내로 돌아옴."""
    last, same = "", 0
    for _ in range(seconds * 2):
        _wait(pg, 500)
        url = pg.url
        if "PswdDateChk" in url:
            try:
                if ev(cdp, "typeof returnUrl === 'function'"):
                    ev(cdp, "returnUrl(); 1")
                    if run:
                        run.say("비밀번호 변경 안내 → 다음에 변경하기")
                    _wait(pg, 2000)
            except BlcmError:
                pass
            last, same = "", 0
            continue
        same = same + 1 if url == last else 0
        last = url
        if same >= 3:
            break


def goto(pg, cdp, url: str, run: Run | None = None) -> None:
    """사이트 안 이동 — 비밀번호 변경 안내로 돌려보내지면 [다음에 변경하기] 뒤 한 번 더."""
    pg.goto(url, wait_until="domcontentloaded", timeout=60000)
    settle(pg, cdp, run, seconds=6)
    if url.split("?")[0].split("/")[-1] not in pg.url:
        pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        settle(pg, cdp, run, seconds=6)


def logout(pg, run: Run) -> None:
    try:
        pg.goto(LOGOUT_URL, wait_until="domcontentloaded", timeout=30000)
        run.say("로그아웃")
    except Exception:  # noqa: BLE001
        pass


LIST_JS = r"""(() => [...document.querySelectorAll('table tbody tr')].map(tr => {
  const td = [...tr.querySelectorAll('td')].map(c => c.innerText.replace(/\s+/g, ' ').trim());
  const a = tr.querySelector('a[href*="fn_go_detail_view"]');
  const m = a ? a.getAttribute('href').match(/fn_go_detail_view\(([^)]*)\)/) : null;
  return {cells: td, args: m ? m[1].split(',').map(s => s.trim().replace(/^'|'$/g, '')) : null};
}).filter(r => r.cells.length >= 6))()"""


def read_list(pg, cdp, run: Run, pages: int = 8) -> list[dict]:
    goto(pg, cdp, LIST_URL, run)
    rows: list[dict] = []
    for n in range(1, pages + 1):
        if n > 1:
            if not ev(cdp, f"typeof fn_search === 'function' && !!document.querySelector('[onclick*=\"fn_search({n})\"]')"):
                break
            ev(cdp, f"fn_search({n}); 1")
            _wait(pg, 1500)
            settle(pg, cdp, run, seconds=6)  # 쪽 넘김 = 화면 새로 — 다 뜬 뒤 읽기
        got = ev(cdp, LIST_JS) or []
        for r in got:
            c = r["cells"]
            a = r.get("args") or []
            rows.append({"kind": c[1], "notice": c[2], "address": c[3], "count": c[4], "status": c[5], "received": c[6] if len(c) > 6 else "",
                         "done": c[7] if len(c) > 7 else "", "inst": a[0] if a else "", "oprtn": a[1] if len(a) > 1 else "",
                         "trsct": a[2] if len(a) > 2 else "", "prog": a[3] if len(a) > 3 else "", "gb": a[4] if len(a) > 4 else ""})
    run.say(f"목록 {len(rows)}줄")
    return rows


def open_report(pg, cdp, run: Run, target: dict) -> None:
    if target.get("prog") == "01":
        raise BlcmError("미실시 보고서는 열면 새 보고서가 생겨 봇이 열지 않습니다 — 사이트에서 [보고서 작성]을 먼저 누르세요.")
    if target.get("prog") not in ("02",):
        raise BlcmError(f"작성중 보고서만 입력할 수 있습니다(지금 상태: {target.get('status') or target.get('prog')}).")
    goto(pg, cdp, LIST_URL, run)
    args = ", ".join(json.dumps(target[k]) for k in ("inst", "oprtn", "trsct", "prog", "gb"))
    ev(cdp, f"fn_go_detail_view({args}); 1")
    for _ in range(30):
        _wait(pg, 500)
        if "selectRsltReprt" in pg.url and ev(cdp, "typeof fn_Tab === 'function'"):
            break
    else:
        raise BlcmError("보고서 화면을 못 열었습니다.")
    _wait(pg, 2000)
    run.say(f"보고서 열기 — {target.get('address')}")


# ---------- 상세 창 ----------
POPUP_SCHEMA = r"""(() => {
  const lab = e => { const l = e.closest('label') || (e.id && document.querySelector('label[for="' + e.id + '"]')); return l ? l.innerText.replace(/\s+/g, ' ').trim() : (e.title || ''); };
  const radios = {};
  document.querySelectorAll('input[type=radio][name^="chklist"]').forEach(e => {
    (radios[e.name] = radios[e.name] || []).push({value: e.value, label: lab(e), weight: e.dataset.weight || '', checked: e.checked, disabled: e.disabled, hidden: e.style.display === 'none'});
  });
  const selects = [...document.querySelectorAll('select[name^="chklist"]')].map(s => ({name: s.name, value: s.value, options: [...s.options].map(o => [o.value, o.text.trim()])}));
  const detl = [...document.querySelectorAll('#detlItemHtml input')].map((e, i) => ({idx: i, type: e.type, id: e.id, name: e.name, title: e.title || '', label: (e.type === 'checkbox' || e.type === 'radio') ? lab(e) : (e.title || ''), value: e.value, checked: e.checked}));
  const ta = {}; ['ilgltOpin', 'performncOpin', 'basisNdLaword', 'rm'].forEach(id => { const t = document.getElementById(id); ta[id] = t ? t.value : null; });
  const files = [...document.querySelectorAll('input.blcmFile')].map(e => e.dataset.fileJobCd);
  const photos = {}; document.querySelectorAll('li[data-file-job-cd][data-file-id]').forEach(li => { const c = li.dataset.fileJobCd; if (li.dataset.fileId) photos[c] = (photos[c] || 0) + 1; });
  const save = [...document.querySelectorAll('button, a, input[type=button]')].map(b => b.getAttribute('onclick') || '').find(s => /fn_save\(/.test(s)) || '';
  const t = id => { const e = document.getElementById(id); return e ? e.innerText.trim() : ''; };
  return {big: t('chkLNm'), mid: t('chkMNm'), small: t('chkSNm'), radios, selects, detl, textareas: ta, files, photos, save, dataVer: (document.getElementById('dataVerPk') || {}).value || ''};
})()"""


def _norm(s: str) -> str:
    """비교용 — 괄호 안(가중치 "양호(1)" 등) 빼고 글자·숫자·+만(가운뎃점 종류가 달라도 같게, 10/29 옹벽ㆍ석축)."""
    return re.sub(r"[^0-9A-Za-z가-힣+]", "", re.sub(r"\([^)]*\)", "", s or ""))


def _pick_radio(cdp, name: str, label: str) -> str:
    """이름 name인 라디오 중 라벨이 label인 것을 누름(이벤트 그대로). 결과: ok | missing | disabled | same."""
    js = f"""(() => {{ const want = {json.dumps(_norm(label))};
      const els = [...document.querySelectorAll('input[type=radio]')].filter(e => e.name === {json.dumps(name)});
      if (!els.length) return 'noname';
      const norm = s => (s || '').replace(/\\([^)]*\\)/g, '').replace(/[^0-9A-Za-z가-힣+]/g, '');
      const lab = e => {{ const l = e.closest('label') || (e.id && document.querySelector('label[for="' + e.id + '"]')); return norm(l ? l.innerText : e.title); }};
      const el = els.find(e => lab(e) === want);
      if (!el) return 'missing';
      if (el.disabled) return 'disabled';
      if (el.checked) return 'same';
      el.click(); if (!el.checked) {{ el.checked = true; el.dispatchEvent(new Event('change', {{bubbles: true}})); }}
      return 'ok'; }})()"""
    return ev(cdp, js) or "noname"


def _set_value(cdp, selector: str, value: str) -> bool:
    js = f"""(() => {{ const e = document.querySelector({json.dumps(selector)}); if (!e) return false; e.value = {json.dumps(value)};
      ['input', 'change', 'keyup'].forEach(t => e.dispatchEvent(new Event(t, {{bubbles: true}}))); return true; }})()"""
    return bool(ev(cdp, js))


def _set_select_text(cdp, name: str, text: str) -> bool:
    js = f"""(() => {{ const s = [...document.querySelectorAll('select')].find(x => x.name === {json.dumps(name)}); if (!s) return false;
      const o = [...s.options].find(o => o.text.replace(/\\s/g, '') === {json.dumps(re.sub(r"\\s", "", text))}); if (!o) return false;
      s.value = o.value; s.dispatchEvent(new Event('change', {{bubbles: true}})); return true; }})()"""
    return bool(ev(cdp, js))


def _check(cdp, el_id: str, on: bool) -> None:
    ev(cdp, f"""(() => {{ const e = document.getElementById({json.dumps(el_id)}); if (!e || e.checked === {str(on).lower()}) return 0; e.click(); return 1; }})()""")


def design_of(it: dict, res: dict, ev_: dict) -> str:
    """설계도서 적합여부 — 점검자가 정한 값, 없으면 판정으로(사이트 규칙: 적합·양호·보통 → 적합, 부적합·미흡·불량 → 부적합, 해당없음 → 해당없음)."""
    if res.get("design"):
        return res["design"]
    if ev_["state"] == "na":
        return "해당없음"
    js = [ev_.get("judge")] + [d.get("judge") for d in ev_.get("details") or []]
    if any(j in ("부적합", "미흡", "불량") for j in js if j):
        return "부적합"
    return "적합" if any(js) else ""


def plan_for(group: list[dict], results: dict) -> dict:
    """사이트 소항목 하나에 넣을 값 — group = 우리 소항목(보통 하나, 범죄예방 세부기준은 둘·셋).
    {cmp, design, details: [(판정 글, [작은 점검 판정 글…])], count, status: [(type, label, value)], texts{ilgltOpin…}, photos: [rel…], na}"""
    details, status, photos, texts = [], [], [], {"ilgltOpin": [], "performncOpin": [], "basisNdLaword": [], "rm": []}
    cmps, designs, count, nas, det_items = [], [], None, [], []
    for gi, it in enumerate(group):
        res = results.get(it["code"]) or {}
        e = I.evaluate(it, res)
        nas.append(e["state"] == "na")
        cmps.append(res.get("cmp") or "")
        designs.append(design_of(it, res, e))
        rt = res.get("ratings") or {}
        for i, d in enumerate(it["details"]):
            det_items.append(gi)
            if e["state"] == "na":
                details.append(("해당없음", ["해당없음"] * len(d.get("subs") or [])))
                continue
            if it["kind"] == "count":
                details.append((e.get("judge") or "", []))
                count = e.get("count")
            elif it["kind"] == "cert":
                details.append(((res.get("cert") or {}).get(f"d{i}") or "", []))
            else:
                dj = (e.get("details") or [{}] * (i + 1))[i].get("judge") or ""
                subs = [rt.get(f"d{i}.s{k}") or "" for k in range(len(d.get("subs") or []))] if d.get("subs") else []
                if not d.get("subs"):
                    dj = rt.get(f"d{i}") or dj
                details.append((dj, subs))
        st = res.get("status") or {}
        for li, ln in enumerate(it.get("status") or []):
            for ti, tok in enumerate(ln):
                if tok["t"] in ("check", "blank"):
                    v = st.get(f"l{li}t{ti}")
                    status.append((tok["t"], tok.get("v", ""), v, gi))
        tx = res.get("texts") or {}
        for ours, theirs in (("ilglt", "ilgltOpin"), ("perf", "performncOpin"), ("basis", "basisNdLaword"), ("rm", "rm")):
            v = (tx.get(ours) or "").strip()
            if v and v != "-":
                texts[theirs].append(v)
        photos += [p["rel"] for p in sorted(res.get("photos") or [], key=lambda p: (p.get("slot") is None, p.get("slot") or 0, 0 if p.get("kind") == "bad" else 1))]  # 견본 칸 차례, 그 밖은 지적 먼저(10/30)
    na = all(nas)
    cmp = "개선필요" if "개선필요" in cmps else "해당없음"
    design = next((d for d in designs if d == "부적합"), None) or next((d for d in designs if d), "")
    return {"cmp": cmp, "design": design, "details": details, "det_items": det_items, "count": count, "status": status, "na": na, "photos": photos,
            "texts": {k: "\n".join(dict.fromkeys(v)) or "-" for k, v in texts.items()}}  # 합쳐진 항목(범죄예방 세부기준)의 같은 글은 한 번만


def site_groups() -> list[tuple[str, list[dict]]]:
    """사이트 소항목 번호(대·중·소) → 우리 소항목들. 범죄예방 "세부기준 1-1·1-2"는 사이트 "세부기준 1" 하나(세부 둘), "2-1~2-3"은 "세부기준 2"."""
    out: list[tuple[str, list[dict]]] = []
    bigs: dict[str, int] = {}
    mids: dict[tuple, int] = {}
    smalls: dict[tuple, int] = {}
    for it in I.items():
        b = bigs.setdefault(it["big_key"], len(bigs) + 1)
        mk = (it["big_key"], _norm(it["mid"]))
        m = mids.setdefault(mk, sum(1 for k in mids if k[0] == it["big_key"]) + 1)
        base = re.sub(r"(세부기준\s*\d)-\d+", r"\1", it["name"])
        sk = mk + (_norm(base),)
        if sk not in smalls:
            smalls[sk] = sum(1 for k in smalls if k[:2] == mk) + 1
            out.append((f"{b}{m}{smalls[sk]}", []))
        next(g for c, g in out if c == f"{b}{m}{smalls[sk]}").append(it)
    return out


def _digits_ok(a: str, b: str) -> bool:
    """비슷한 라벨 짝 — 양쪽에 숫자가 다 있는데 다르면 다른 칸("1등급"·"7등급")."""
    da, db = "".join(ch for ch in a if ch.isdigit()), "".join(ch for ch in b if ch.isdigit())
    return not (da and db and da != db)


def status_pairs(detl: list[dict], ours: list[tuple]):
    """점검현황 — 사이트 칸(detl)과 우리 조각(ours = [(check|blank, 라벨, 값)])을 라벨로 차례 맞춤(difflib).
    → (사이트 칸, 우리 조각, 맞은 짝 [(i, j)], 우리가 값을 적었는데 못 맞춘 조각 라벨들)."""
    import difflib

    site_in = [x for x in detl if x["type"] in ("checkbox", "radio", "text")]
    key_s = [("c", _norm(a["label"])) if a["type"] != "text" else ("t",) for a in site_in]
    key_o = [("c", _norm(x[1])) if x[0] == "check" else ("t",) for x in ours]
    pairs = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, key_s, key_o, autojunk=False).get_opcodes():
        if tag == "equal":
            pairs += list(zip(range(i1, i2), range(j1, j2)))
        elif tag == "replace" and i2 - i1 == j2 - j1:  # 같은 자리·같은 수로 어긋남 — 빈칸끼리, 또는 라벨이 비슷하면(60%↑, "판단불가 2)"·"판단불가") 짝
            for i, j in zip(range(i1, i2), range(j1, j2)):
                if key_s[i][0] == key_o[j][0] == "t" or (key_s[i][0] == key_o[j][0] == "c" and _digits_ok(key_s[i][1], key_o[j][1])
                                                         and difflib.SequenceMatcher(None, key_s[i][1], key_o[j][1]).ratio() >= 0.6):
                    pairs.append((i, j))
    matched = {j for _, j in pairs}
    lost = [x[1] or "빈칸" for j, x in enumerate(ours) if j not in matched and x[2] not in (None, "", False)]
    return site_in, ours, pairs, lost


def fill_popup(cdp, run: Run, S: str, plan: dict, schema: dict) -> dict:
    """열린 상세 창 채우기 — 결과 {warn[], filled n, after(다시 읽은 칸)}.
    판정 방식이 셋(10/29 연습): ① 작은 점검 라디오(급수성능 21111…, 방화구획 521111처럼 번호 길이가 다름) → 사이트가 세부 판정 계산
    ② 고르기 칸 evlScore·evlCount(건수형 0건~6건, 범죄예방 세부기준·이상징후 청문점검 = 점검현황 체크 수, 인증 여부 = 인증·재인증·만료·해당없음) ③ 세부 라디오 직접."""
    warn: list[str] = []
    n = 0
    r = _pick_radio(cdp, f"chklist||{S}0|choiseItem", plan["cmp"])
    n += r in ("ok", "same")
    if r not in ("ok", "same"):
        warn.append(f"현행기준 비교 '{plan['cmp']}' {r}")
    radios = schema.get("radios") or {}
    det_names = sorted(k for k in radios if re.fullmatch(rf"chklist\|\|{S}[1-7]\|choiseItem", k))
    if len(det_names) != len(plan["details"]):
        warn.append(f"세부항목 수가 다름(사이트 {len(det_names)} / 우리 {len(plan['details'])})")
    for i, (dj, subs) in enumerate(plan["details"]):
        d_code = f"{S}{i + 1}"
        mine = sorted(k for k in radios if k.split("|")[2].startswith(d_code) and len(k.split("|")[2]) > len(d_code) and k.endswith("|choiseItem"))
        want = subs if subs else ([dj] * len(mine) if dj else [])  # 우리에게 작은 점검이 없으면(마감재 육안점검 등) 세부 판정으로
        if subs and mine and len(mine) != len(subs):
            warn.append(f"세부 {i + 1} 작은 점검 수가 다름(사이트 {len(mine)} / 우리 {len(subs)})")
        for name, sv in zip(mine, want):
            if sv:
                r = _pick_radio(cdp, name, sv)
                n += r in ("ok", "same")
                if r not in ("ok", "same", "disabled"):
                    warn.append(f"세부 {i + 1} 작은 점검 '{sv}' {r}")
        if dj and not mine and f"chklist||{d_code}|choiseItem" in radios:
            r = _pick_radio(cdp, f"chklist||{d_code}|choiseItem", dj)
            n += r in ("ok", "same")
            if r not in ("ok", "same", "disabled"):
                warn.append(f"세부 {i + 1} 판정 '{dj}' {r}")
    if plan["design"]:
        r = _pick_radio(cdp, f"chklist||{S}00|choiseItem", plan["design"])
        n += r in ("ok", "same")
        if r not in ("ok", "same"):
            warn.append(f"설계도서 적합여부 '{plan['design']}' {r}")
    # 점검현황 — 사이트 칸과 우리 조각을 라벨로 차례 맞춤(difflib), 맞은 칸만 넣음. 체크 수(라벨 "가중치 N")는 우리 항목마다 셈 → 건수 칸
    site_in, ours, pairs, lost = status_pairs(schema["detl"], plan["status"])
    counts: dict[int, int] = {}
    for i, j in pairs:
        a, (t, lab, v, gi) = site_in[i], ours[j]
        if t == "check":
            if v is True or (a["type"] == "checkbox" and a["checked"]):
                on = "true" if v is True else "false"
                ev(cdp, "(() => { const e = document.querySelectorAll('#detlItemHtml input')[" + str(a["idx"]) + "]; if (!e) return 0;"
                        " if (e.type === 'radio') { if (!e.checked) e.click(); return 1; } if (e.checked !== " + on + ") e.click(); return 1; })()")
                n += v is True
            if v is True and a["type"] == "checkbox":
                m = re.search(r"가중치\s*(\d+)", a["label"] or "")
                counts[gi] = counts.get(gi, 0) + (int(m.group(1)) if m else 1)
        elif v not in (None, "", True):
            ok = ev(cdp, "(() => { const e = document.querySelectorAll('#detlItemHtml input')[" + str(a["idx"]) + "]; if (!e) return false; e.value = "
                    + json.dumps(str(v)) + "; ['input', 'change', 'keyup'].forEach(t => e.dispatchEvent(new Event(t, {bubbles: true}))); return true; })()")
            n += bool(ok)
    if lost:
        warn.append(f"점검현황 {len(lost)}칸 못 넣음({', '.join(x[:10] for x in lost[:4])}) — 사이트에서 직접")
    # 고르기 칸(세부마다 evlScore·evlCount)
    sels = {x["name"]: x for x in schema.get("selects") or []}
    for i, (dj, _) in enumerate(plan["details"]):
        for nm in (f"chklist||{S}{i + 1}|evlScore", f"chklist||{S}{i + 1}|evlCount"):
            sel = sels.get(nm)
            if not sel:
                continue
            opts = [t for _, t in sel["options"]]
            pick = ""
            if dj and _norm(dj) in [_norm(o) for o in opts]:
                pick = dj
            elif any(o.endswith("건") for o in opts):
                if dj == "해당없음" and any(_norm(o) == "해당없음" for o in opts):
                    pick = "해당없음"
                else:
                    gi = (plan.get("det_items") or [0] * (i + 1))[i]
                    cnt = plan["count"] if plan["count"] is not None and len(plan["details"]) == 1 else counts.get(gi, 0)
                    top = max((int(o[:-1]) for o in opts if o.endswith("건") and o[:-1].isdigit()), default=0)
                    pick = f"{min(int(cnt or 0), top)}건"
            if pick:
                if _set_select_text(cdp, nm, pick):
                    n += 1
                else:
                    warn.append(f"세부 {i + 1} 고르기 '{pick}' 못 고름")
    for tid, val in plan["texts"].items():
        if schema["textareas"].get(tid) is not None:
            n += _set_value(cdp, f"#{tid}", val)
    # 다시 읽어 확인 — 세부 판정은 작은 점검·건수를 고르면 사이트가 계산해 잠긴 칸에 체크함: 우리 판정과 다르면 알림(점수 계산이 다를 때)
    after = ev(cdp, POPUP_SCHEMA) or {}
    for i, (dj, _) in enumerate(plan["details"]):
        grp = (after.get("radios") or {}).get(f"chklist||{S}{i + 1}|choiseItem") or []
        got = next((o["label"] for o in grp if o["checked"]), "")
        if dj and grp and _norm(got) != _norm(dj):
            warn.append(f"세부 {i + 1} 사이트 판정 '{got or '비어 있음'}' / 우리 '{dj}'")
    return {"warn": warn, "filled": n, "after": after}


def popup_for(ctx, pg, cdp, S: str, run: Run):
    """본 화면에서 소항목 S 상세 창 열기 → (창, cdp). 단추 onclick 글을 그대로 부름."""
    call = ev(cdp, f"""(() => {{ const b = [...document.querySelectorAll('[onclick*="fn_open_detlChklist"]')].find(x => /\\|{S}\\|detlItem/.test(x.getAttribute('onclick')));
        return b ? b.getAttribute('onclick') : null; }})()""")
    if not call:
        return None, None
    with ctx.expect_page(timeout=30000) as info:
        ev(cdp, call.replace("javascript:", "") + "; 1")
    pop = info.value
    _dialogs(pop, run, f"[{S}] ")
    pop.wait_for_load_state("domcontentloaded")
    pcdp = ctx.new_cdp_session(pop)
    for _ in range(30):
        pop.wait_for_timeout(400)
        try:
            if ev(pcdp, "!!document.getElementById('detlItemHtml') && typeof fn_save === 'function'"):
                break
        except BlcmError:
            continue
    pop.wait_for_timeout(800)
    return pop, pcdp


def upload_photos(pop, pcdp, files: list[Path]) -> int:
    """현황사진 칸(FL0310)에 파일 넣기 — CDP DOM.setFileInputFiles(사이트 Map 덮어쓰기 때문에 Playwright set_input_files 안 씀). 고르는 순간 사이트로 올라감."""
    if not files:
        return 0
    doc = pcdp.send("DOM.getDocument", {"depth": 1})
    node = pcdp.send("DOM.querySelector", {"nodeId": doc["root"]["nodeId"], "selector": "input.blcmFile[data-file-job-cd='FL0310']"})
    if not node.get("nodeId"):
        return 0
    before = ev(pcdp, "document.querySelectorAll(\"li[data-file-job-cd='FL0310'][data-file-id]\").length") or 0
    pcdp.send("DOM.setFileInputFiles", {"nodeId": node["nodeId"], "files": [str(f) for f in files]})
    for _ in range(60):
        pop.wait_for_timeout(500)
        now = ev(pcdp, "document.querySelectorAll(\"li[data-file-job-cd='FL0310'][data-file-id]\").length") or 0
        if now - before >= len(files):
            break
    return (ev(pcdp, "document.querySelectorAll(\"li[data-file-job-cd='FL0310'][data-file-id]\").length") or 0) - before


def items_pass(ctx, pg, cdp, run: Run, results: dict, folder: Path, save: bool, only: list[str] | None = None) -> dict:
    """소항목마다 상세 창 — 채우기(연습은 저장 안 하고 닫음). 상세 창 칸 짜임(schema)을 모아 돌려줌."""
    schemas = {}
    for S, group in site_groups():
        if only and S not in only:
            continue
        tab = S[0]
        ev(cdp, f"fn_Tab('{tab}'); 1")
        pg.wait_for_timeout(500)
        codes = [it["code"] for it in group]
        key = "+".join(codes)
        plan = plan_for(group, results)
        if not any((results.get(c) or {}) for c in codes):
            run.items[key] = {"site": S, "state": "skip", "msg": "우리 건에서 아직 안 씀"}
            continue
        try:
            pop, pcdp = popup_for(ctx, pg, cdp, S, run)
        except Exception as err:  # noqa: BLE001
            run.items[key] = {"site": S, "state": "fail", "msg": f"상세 창을 못 열었습니다: {str(err)[:120]}"}
            continue
        if pop is None:
            run.items[key] = {"site": S, "state": "fail", "msg": "상세점검 단추를 못 찾았습니다"}
            continue
        try:
            schema = ev(pcdp, POPUP_SCHEMA) or {}
            schemas[S] = schema
            name_ok = _norm(group[0]["name"].split("-")[0]) in _norm(schema.get("small")) or _norm(schema.get("small")) in _norm(group[0]["name"])
            if not name_ok:
                run.items[key] = {"site": S, "state": "fail", "msg": f"상세 창 이름이 다름(사이트 '{schema.get('small')}' / 우리 '{group[0]['name']}') — 건너뜀"}
                pop.close()
                continue
            got = fill_popup(pcdp, run, S, plan, schema)
            schemas[S] = {**schema, "after_radios": {k: [o["label"] for o in v if o["checked"]] for k, v in (got.get("after") or {}).get("radios", {}).items()}}
            photos = [folder / r for r in plan["photos"] if (folder / r).exists()]
            n_up = 0
            if save:
                n_up = upload_photos(pop, pcdp, photos)  # 장수 제한 없음(10/30 사용자 — 예전 10장까지)
            run.shot(pop, f"{S}_{group[0]['name'][:10]}")
            state = "warn" if got["warn"] else "ok"
            msg = "; ".join(got["warn"])
            if save:
                before = len(run.alerts)
                ev(pcdp, (schema.get("save") or "fn_save()").replace("javascript:", "") + "; 1")
                pop.wait_for_timeout(2500)
                said = run.alerts[before:]
                bad = [a for a in said if not re.search(r"저장하시겠습니까|저장되었습니다", a)]
                if bad:
                    state, msg = "fail", ("; ".join(bad) + ("; " + msg if msg else ""))[:400]
                elif not any("저장되었습니다" in a for a in said):
                    state, msg = "warn", ("저장 답을 못 봤습니다" + ("; " + msg if msg else ""))
            run.items[key] = {"site": S, "state": state, "msg": msg, "filled": got["filled"], "photos": len(photos), "uploaded": n_up}
        except Exception as err:  # noqa: BLE001
            run.items[key] = {"site": S, "state": "fail", "msg": str(err)[:200]}
        finally:
            try:
                if not pop.is_closed():
                    pop.close()
            except Exception:  # noqa: BLE001
                pass
        run.say(f"{S} {key} {run.items[key]['state']}")
    return schemas


def main_pass(pg, cdp, run: Run, job: dict, save: bool) -> dict:
    """본 화면 — 관리계획(탭 6)·그 밖의 항목(탭 7)·점검결과 의견·점검기관 칸. save면 [전체저장](제출은 안 누름)."""
    op = job.get("opinion") or {}
    warn = []
    ev(cdp, "fn_Tab('6'); 1")
    pg.wait_for_timeout(500)
    for code, label in I.PLAN_ROWS:
        v = (op.get("plan") or {}).get(code)
        if v:
            r = _pick_radio(cdp, f"chklist||{code}|choiseItem", v)
            if r not in ("ok", "same"):
                warn.append(f"관리계획 {label} {r}")
    ev(cdp, "fn_Tab('7'); 1")
    pg.wait_for_timeout(500)
    for code, label, _ in I.OTHER_ROWS:
        x = (op.get("other") or {}).get(code) or {}
        if x.get("v"):
            r = _pick_radio(cdp, f"chklist||{code}|choiseItem", x["v"])
            if r not in ("ok", "same"):
                warn.append(f"그 밖의 항목 {code} {r}")
        if x.get("note"):
            ok = ev(cdp, f"""(() => {{ const e = [...document.querySelectorAll('input[type=text]')].find(i => /\\|{code}9\\|opin$/.test(i.name)); if (!e) return false;
                e.value = {json.dumps(x['note'])}; e.dispatchEvent(new Event('change', {{bubbles: true}})); return true; }})()""")
            if not ok:
                warn.append(f"그 밖의 항목 {code} 일자 칸 없음")
    for key, label, site in I.OPINION_KEYS:
        v = ((op.get("texts") or {}).get(key) or "").strip()
        if v and not _set_value(cdp, f"textarea[name='{site}']", v) and not _set_value(cdp, f"#{site}", v):
            warn.append(f"의견 {label} 칸 없음")
    c = job.get("contract") or {}
    fields = {"chkRspnber": c.get("chief"), "chkAmount": re.sub(r"\D", "", str(c.get("amount") or "")), "chkEmpNm": c.get("inspector")}
    for k, v in fields.items():
        if v and not _set_value(cdp, f"input[name='{k}']", str(v)):
            warn.append(f"점검기관 {k} 칸 없음")
    run.shot(pg, "본화면")
    if save:
        before = len(run.alerts)
        ev(cdp, "fn_save('02', ''); 1")
        pg.wait_for_timeout(4000)
        said = run.alerts[before:]
        bad = [a for a in said if not re.search(r"저장하시겠습니까|저장되었습니다|저장 되었습니다", a)]
        if bad:
            warn.append("전체저장: " + "; ".join(bad)[:300])
        run.shot(pg, "전체저장뒤")
    run.items["main"] = {"state": "warn" if warn else "ok", "msg": "; ".join(warn)}
    return {"warn": warn}


def run_job(mode: str, job: dict, folder: Path, cred: tuple[str, str], out: Path, only: list[str] | None = None) -> dict:
    """한 번 돌리기 — 결과 dict(run 기록 + list/schemas). 예외는 기록에 담아 돌려줌(로그아웃까지)."""
    from playwright.sync_api import sync_playwright

    run = Run(out, mode)
    res: dict = {"mode": mode}
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1500, "height": 1000}, locale="ko-KR")
        pg = ctx.new_page()
        _dialogs(pg, run)
        cdp = ctx.new_cdp_session(pg)
        logged = False
        try:
            login(ctx, pg, cdp, run, *cred)
            logged = True
            if mode != "save":  # 쓰기 막기는 로그인 뒤부터(로그인 과정 요청까지 막으면 로그인이 안 될 수 있음)
                ctx.route("**/*", _guard(run))
            if mode == "list":
                res["list"] = read_list(pg, cdp, run)
            else:
                target = (job.get("site") or {}).get("target") or {}
                if not target:
                    raise BlcmError("사이트 보고서를 아직 고르지 않았습니다 — [🔎 사이트 목록 읽기] 뒤 고르세요.")
                open_report(pg, cdp, run, target)
                run.shot(pg, "보고서")
                schemas = items_pass(ctx, pg, cdp, run, job.get("results") or {}, folder, save=(mode == "save"), only=only)
                (out / "schemas.json").write_text(json.dumps(schemas, ensure_ascii=False, indent=1), encoding="utf-8")
                main_pass(pg, cdp, run, job, save=(mode == "save"))
        except Exception as err:  # noqa: BLE001
            res["error"] = str(err)[:400]
            run.say(f"멈춤: {err}")
            run.shot(pg, "멈춤")
        finally:
            if logged or run.tried_login:  # 로그인을 눌렀으면 멈춰도 로그아웃(성공했는데 답만 못 읽은 때도 접속이 남지 않게)
                logout(pg, run)
            b.close()
    res.update(run.out_dict())
    return res
