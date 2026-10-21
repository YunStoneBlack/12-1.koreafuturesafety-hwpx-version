// 시특법 회차 화면(sitok-round.html?report=, 2026-10-14 형 피드백 ⑦ 3층 구조) — 시설물 화면의 회차 카드(js/sitok-reports.js)에 있던 것을 한 회차만 크게.
// 위 = 현장 점검 버튼(📱 현장 조사 → 📐 재료시험·📊 상태평가(정밀) → 📝 면담·변경사항), 가운데 = 보고서(🏢 시설물 현황·🤖 AI 초안·[보고서 만들기]·파일·지난 보고서 한글),
// 아래 = 접힌 회차 정보(계약·종류·점검기간·제출일·기술자·묶음 금액·삭제). 창(현황·면담·AI)은 js/sitok-detail.js·sitok-survey.js·sitok-ai.js 그대로.
// 묶음(여러 동 한 보고서)이면 현장 점검 칸에 동 이름만(민재형 10/15 그림 "시설물명만 2개 → 누르면 1개 시설물일 때 화면") — 누르면 ?report=그 동 회차&one=1
// (한 동 화면: 현장 조사·재료시험·상태평가·면담·현황·AI 초안). 묶음 공통(만들기·합본·FMS·회차 정보)은 동 고르기 화면에도. 동 목록 = GET /sitok/reports/{id}.group_rounds.
// 만들기는 백그라운드(한글 PDF 몇 분) — 3초마다 진행 확인. 서버 server/api/routers/sitok_reports.py.

(function () {
  const rid = Number(new URLSearchParams(location.search).get("report")) || null;
  const errorEl = document.getElementById("error");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const err = (e) => showError(errorEl, e);
  const $ = (id) => document.getElementById(id);
  const ymdDot = (s) => (s || "?").replaceAll("-", ".");
  let r = null; // 회차
  let data = null; // 시설물 회차 목록 응답(persons·group·group_contracts)
  let contracts = [];
  let timer = null;
  const one = new URLSearchParams(location.search).get("one") === "1"; // 묶음에서 한 동만 보는 화면
  if (!rid) { err(new Error("회차가 없습니다 (?report=)")); return; }

  const title = () => (r.half === "성능평가" ? `${r.year}년 내진성능평가` : `${r.year}년 ${r.half}`); // 내진성능평가 회차 = 반기 칸 "성능평가"(10/21)
  const personOptions = (selected) => '<option value="">—</option>' + data.persons.map((p) => `<option value="${p.id}"${p.id === selected ? " selected" : ""}>${esc(p.name)}${p.position ? ` ${esc(p.position)}` : ""}</option>`).join("");
  const big = (href, icon, label, on, sub) => `<a class="rd-btn${on ? " on" : ""}" href="${href}"><span class="rd-ic">${icon}</span><span class="rd-lb">${label}${on ? ' <em class="rd-ok">✓</em>' : ""}</span>${sub ? `<span class="rd-sub">${sub}</span>` : ""}</a>`;
  const bigBtn = (cls, icon, label, on, sub) => `<button type="button" class="rd-btn ${cls}${on ? " on" : ""}"><span class="rd-ic">${icon}</span><span class="rd-lb">${label}${on ? ' <em class="rd-ok">✓</em>' : ""}</span>${sub ? `<span class="rd-sub">${sub}</span>` : ""}</button>`;

  // 묶음 동 고르기 버튼 — 진행 표시는 아래 작은 글, 회차가 아직 없으면(묶음 보고서 만들기 때 같이 생김) 안내만
  function dongPick(d) {
    if (!d.report_id) return `<div class="rd-btn rd-off"><span class="rd-ic">🏢</span><span class="rd-lb">제${d.index}장 ${esc(d.name)}</span><span class="rd-sub">이 반기 회차가 아직 없습니다 — [묶음 보고서 만들기] 때 같이 생깁니다</span></div>`;
    const pre = (d.kind || "정기") === "정밀";
    const steps = [["현장 조사", d.has_field], ...(pre ? [["재료시험", d.has_tests], ["상태평가", d.has_rating]] : []), ["면담", d.has_survey], ...(r && r.wall ? [] : [["현황", d.has_detail]]), ["AI 초안", d.has_ai]]; // 옹벽은 현황 없음(10/21)
    const done = d.has_field && (!pre || (d.has_tests && d.has_rating));
    return big(`sitok-round.html?report=${d.report_id}&one=1`, "🏢", `제${d.index}장 ${esc(d.name)}`, done, steps.map(([t, ok]) => `${t}${ok ? " ✓" : ""}`).join(" · "));
  }

  // 현장 조사 칸 아래 글(10/18 형) — ✓는 현장 조사 화면 [✓ 조사 완료]로만, 그 전엔 "결함 12/125 확인 · 전경 3장"
  function fieldSub(kind) {
    const f = r.field || {};
    const prog = f.defects || f.overview ? [f.defects ? `결함 ${f.checked}/${f.defects} 확인` : "", `전경 ${f.overview || 0}장`].filter(Boolean).join(" · ") : "";
    if (f.done) return `${ymdDot(f.done.at).slice(5)} ${esc(f.done.by)} 조사 완료${prog ? ` · ${prog}` : ""}`;
    return prog || "결함·전경사진·공중이용·기타시설" + (kind === "정밀" ? "·자료수집·하중" : "");
  }

  // 칸 아래 글 — ✓는 그 칸의 [✓ 조사 완료]·[✓ 작성 완료]로만(10/18 민재형, js/sitok-steps.js), 완료면 날짜·이름
  function doneSub(k, dflt) {
    const s = (r.steps || {})[k];
    return s ? `${ymdDot(s.at).slice(5)} ${esc(s.by)} 완료` : dflt;
  }

  // 만들기 끝 안내 — 줄마다 하나(요약 / 끼운 자료 / ⚠ 알림마다, 사용자 10/15 "알림 1개당 줄바꿈"). 예전 안내(" · "로 이어 붙임)도 ⚠ 앞에서 나눔
  function doneText() {
    const lines = String(r.message || "").replace(/ · (?=⚠)/g, "\n").split("\n").map((s) => s.trim()).filter(Boolean);
    const [head, ...rest] = lines;
    return `<div class="sk-rep-st ok"><div>✓ ${esc(r.made_at)} 만듦 — ${esc(head || "")}</div>${rest.map((s) => `<div class="${s.startsWith("⚠") ? "rd-warn" : "rd-note"}">${esc(s)}</div>`).join("")}</div>`;
  }

  function draw() {
    const kind = r.kind || "정기";
    const g = data.group;
    document.title = `${r.facility_name} ${title()} - 시특법`;
    $("rd-fac-link").textContent = r.facility_name;
    $("rd-fac-link").href = `sitok-facility.html?id=${r.facility_id}`;
    $("rd-crumb").textContent = title();
    const dongs = !r.past && !one && (r.group_rounds || []).length > 1 ? r.group_rounds : null;
    const seis = kind === "성능평가";
    $("rd-head").innerHTML = `<h1>${esc(dongs && g ? g.name : r.facility_name)} <span class="rd-round">${title()}</span>${seis ? '<span class="sk-kind pre">내진성능평가</span>'
      : `<button type="button" class="sk-kind sk-kind-btn ${kind === "정밀" ? "pre" : ""}" title="누르면 ${kind === "정밀" ? "정기" : "정밀"}로 바꿉니다">${kind}안전점검 ▾</button>`}</h1>
      <div class="rd-src">${seis ? "내진성능평가 — 현장 조사(결함)·구조 일람표·철근탐사는 지금, 보고서(우리 1~2장 + 외주 3~7장 합치기)는 준비 중" : r.past ? "이미 낸 보고서를 등록한 회차 — 다음 회차가 이 보고서의 데이터를 씁니다"
        : r.has_source ? `전회차 보고서: ${esc(r.source_note)}` : "전회차 보고서 없음 — 처음 세팅하는 시설물(전회차가 있으면 🏢 시설물 현황·📝 면담 창에 전회차 보고서 PDF)"}
        ${r.period_start ? ` · 점검기간 ${ymdDot(r.period_start)} ~ ${ymdDot(r.period_end)}` : ""}</div>
      ${g && !r.past ? `<div class="sk-rep-group">📚 묶음 보고서 <b>${esc(g.name)}</b> — ${g.members.map((m, i) => `제${i + 1}장 ${esc(m.name)}`).join(" · ")}
        <span class="sk-help">점검기간·제출일·기술자는 묶인 동 회차도 같이 바뀝니다. 현장 조사·현황·AI 초안은 동마다.</span></div>` : ""}
      ${g && one && !r.past ? `<a class="rd-back" href="sitok-round.html?report=${r.id}">← ${esc(g.name)} 동 고르기</a>` : ""}${booksBar()}`;

    const fms = $("rd-fms-panel");
    if (fms) fms.hidden = seis; // 내진성능평가는 FMS 정기·정밀 제출이 아님(10/21)
    if (dongs) {
      // 묶음 — 동 이름만(누르면 그 동 화면), 보고서 칸은 묶음 공통(만들기·합본)만
      $("rd-field").innerHTML = dongs.map(dongPick).join("");
      $("rd-report").innerHTML = "";
      $("rd-report").hidden = true;
    } else {
      $("rd-report").hidden = false;
      // 현장 점검
      const sm = r.seismic || {};
      $("rd-field").innerHTML = r.past ? '<div class="empty-note">이미 낸 보고서를 등록한 회차라 현장 점검은 없습니다.</div>'
        : seis ? big(`sitok-field.html?report=${r.id}`, "📱", "현장 조사", r.has_field, (r.field || {}).defects ? fieldSub(kind) : "결함조사 — 외관조사망도·사진첩") // 내진성능평가(10/21)
          + big(`sitok-schedule.html?facility=${r.facility_id}`, "📏", "구조 일람표 부재 목록", sm.schedule > 0 && !sm.schedule_need,
            sm.schedule ? `${sm.schedule}칸${sm.schedule_need ? ` · 확인 필요 ${sm.schedule_need}칸` : " · 모두 확인"}` : "일람표를 AI로 읽어 설계값 — 철근탐사 전에")
          + big(`sitok-seismic.html?report=${r.id}`, "🧪", "현장시험(철근탐사)", sm.rebar > 0, sm.rebar ? `철근탐사 ${sm.rebar}개소` : "층·부호만 고르면 설계값, 탐사기 캡처로 조사값")
        : big(`sitok-field.html?report=${r.id}`, "📱", "현장 조사", r.has_field, fieldSub(kind))
          + (kind === "정밀" ? big(`sitok-tests.html?report=${r.id}`, "📐", "재료시험", r.has_tests, doneSub("tests", "표본층·규격·강도·탄산화·기울기·부등침하"))
            + big(`sitok-rating.html?report=${r.id}`, "📊", "상태평가", r.has_rating, doneSub("rating", "부재 개수 → 상태평가 등급")) : "")
          + bigBtn("rd-survey", "📝", r.wall ? "면담·점검 이력 조사" : "면담·변경사항 조사", r.has_survey, doneSub("survey", r.wall ? "1.3.2 점검 이력 · 1.3.3 보수 이력" : "1.2.7 보수 이력 · 1.2.8 변경사항"));
      // 보고서
      $("rd-report").innerHTML = r.past || seis ? "" : (r.wall ? "" : bigBtn("rd-detail", "🏢", "시설물 현황", r.has_detail, doneSub("detail", "1.1 현황표 · 1.2 구조·마감·용도"))) // 옹벽은 현황 칸 없음(제원은 관리대장에서, 10/21)
        + ((r.ai_left || []).length // 10/18 형 요청1 — 앞 칸을 다 [완료]해야 AI 초안이 열림
          ? `<div class="rd-btn rd-off rd-lock" title="앞 칸을 다 완료하면 열립니다"><span class="rd-ic">🤖</span><span class="rd-lb">AI 초안 🔒</span><span class="rd-sub">먼저 완료: ${r.ai_left.map(esc).join(" · ")}</span></div>`
          : bigBtn("rd-ai", "🤖", "AI 초안", r.has_ai, doneSub("ai", kind === "정밀" ? "22항목 — 결함·시험·상태평가 글" : "결과표·외관조사 서술·종합결론·등급")));
    }
    const stateText = r.status === "running" ? `<span class="sk-rep-st run">⏳ ${esc(r.message)}</span>`
      : r.status === "failed" ? `<span class="sk-rep-st bad">✗ 실패: ${esc(r.message)}</span>`
        : r.status === "done" ? doneText() : '<span class="sk-rep-st">아직 안 만듦</span>';
    const v = encodeURIComponent(r.made_at || "");
    const blocked = !r.past && !!r.build_block; // 보고서 틀이 없는 시설물·회차(교량·수리·옹벽 정밀 — 형 10/21 "준비 중입니다", 만들기 막기)
    const locked = blocked || (!r.past && (r.build_left || []).length > 0); // 10/18 형 요청1 — AI 초안까지 칸을 다 완료해야 보고서 합본(묶음은 동마다)
    $("rd-build").innerHTML = `<div class="sk-rep-foot">${stateText}
      ${r.has_pdf ? `<a class="secondary-link" href="${BASE}/api/sitok/reports/${r.id}/file/pdf?v=${v}" target="_blank" rel="noopener">${kind === "정밀" ? "합본 PDF" : "PDF 보기"}</a>` : ""}
      ${r.has_cover ? `<a class="secondary-link" href="${BASE}/api/sitok/reports/${r.id}/file/cover_pdf?v=${v}" target="_blank" rel="noopener" title="표지 + 책등 — 제본소에 따로 보내는 파일(합본에는 책등 없음)">표지(제본용) PDF</a>` : ""}
      ${r.has_hwpx ? `<a class="secondary-link" href="${BASE}/api/sitok/reports/${r.id}/file/hwpx?v=${v}">${kind === "정밀" ? "본문 한글" : "한글 받기"}</a>` : ""}
      ${r.has_appendix ? `<a class="secondary-link" href="${BASE}/api/sitok/reports/${r.id}/file/appendix?v=${v}">부록 한글</a>` : ""}
      ${r.past ? "" : blocked ? '<button type="button" class="sk-rep-build" disabled title="보고서 틀 준비 중">🔒 보고서 틀 준비 중</button>'
        : `<button type="button" class="sk-rep-build"${r.status === "running" || locked ? " disabled" : ""}${locked ? ' title="칸을 다 완료하면 열립니다"' : ""}>${locked ? "🔒 " : ""}${r.has_pdf ? "다시 만들기" : g ? `묶음 보고서 만들기(${g.members.length}동)` : "보고서 만들기"}</button>`}</div>
      ${blocked ? `<div class="rd-lock-note">🛠 ${esc(r.build_block)}</div>`
        : locked ? `<div class="rd-lock-note">🔒 보고서를 만들려면 먼저 완료: ${(r.build_left || []).map((x) => `<div>${esc(x)}</div>`).join("")}</div>` : ""}
      ${!r.past && !(r.period_start && r.period_end) ? (autoOk()
        ? `<div class="rd-lock-note rd-period-note ok">📅 점검기간 — 만들 때 자동으로 <b>${ymdDot(r.auto_period.start)} ~ ${ymdDot(r.auto_period.end)}</b>
            <button type="button" class="secondary btn-sm rd-go-period">바꾸기</button><div>${esc(r.auto_period.rule)}</div></div>`
        : `<div class="rd-lock-note rd-period-note">📅 점검기간이 비어 있습니다 — 보고서를 만들려면 넣어야 합니다
            <button type="button" class="secondary btn-sm rd-go-period">점검기간 넣기</button>
            <div>${esc((r.auto_period || {}).rule || "")} — 아래 ⚙ 회차 정보 칸</div></div>`) : ""}
`;
    // 회차 정보
    const conList = data.group && data.group_contracts ? data.group_contracts : contracts;
    const contractOpts = '<option value="">계약 고르기</option>' + conList.map((c) =>
      `<option value="${c.id}"${c.id === r.contract_id ? " selected" : ""}>${c.facility ? `[${esc(c.facility)}] ` : ""}${esc(c.sector)} · ${esc(c.title || "계약")} (${esc(c.start_date)}~${esc(c.end_date)})</option>`).join("");
    const parts = r.participant_ids || [];
    $("rd-info").innerHTML = `<div class="sk-rep-grid">
        <label>계약<span class="sk-help"></span><select data-k="contract_id">${contractOpts}</select></label>
        ${seis ? '<label>종류 <span class="sk-help">새 회차로만 바꿀 수 있음</span><input value="내진성능평가" disabled /></label>'
          : `<label>종류 <span class="sk-help">계약서 회차 줄에서 자동 — 틀리면 직접</span><select data-k="kind">${["정기", "정밀"].map((k) => `<option${k === kind ? " selected" : ""}>${k}</option>`).join("")}</select></label>`}
        <label>점검기간 시작 <span class="sk-help">${autoOk() ? `비우면 ${ymdDot(r.auto_period.start)}(자동)` : "비우면 만들 때 자동(규칙대로)"}</span><input type="date" data-k="period_start" value="${esc(r.period_start)}" /></label>
        <label>점검기간 끝 <span class="sk-help">${autoOk() ? `비우면 ${ymdDot(r.auto_period.end)}(자동)` : "민간 정기 = 현장 간 날"}</span><input type="date" data-k="period_end" value="${esc(r.period_end)}" /></label>
        <label>제출일 <span class="sk-help">표지·제출문 연월, 비우면 점검기간 끝</span><input type="date" data-k="report_date" value="${esc(r.report_date)}" /></label>
        <label>책임기술자<span class="sk-help"></span><select data-k="chief_id">${personOptions(r.chief_id)}</select></label>
        <label>참여기술자<span class="sk-help"></span><select data-k="p0">${personOptions(parts[0])}</select></label>
        ${g && !r.past && !dongs ? `<label>이 동 점검금액(천원) <span class="sk-help">같은 계약서를 여러 동이 같이 쓰면 꼭 — 비면 계약 금액</span>
          <input data-k="amount_k" inputmode="numeric" value="${esc(r.amount_k)}" placeholder="예: 550" /></label>` : ""}
      </div>
      <div class="rd-info-foot"><span class="sk-help">계약서를 바꾸거나 더하려면 시설물 화면의 "계약" 칸에서.</span><button type="button" class="secondary btn-sm rd-del">이 회차 삭제</button></div>`;
    bind();
    if (r.status === "running") poll();
  }

  function bind() {
    $("rd-head").querySelector(".sk-kind-btn")?.addEventListener("click", async () => { // 종류 바꾸기(10/14 형 피드백)
      const to = (r.kind || "정기") === "정밀" ? "정기" : "정밀";
      if (!confirm(`${title()}를 ${to}안전점검으로 바꿀까요? 정밀이면 재료시험·상태평가 버튼이 생깁니다.`)) return;
      try { await apiPatch(`/sitok/reports/${r.id}`, { kind: to }); load(); } catch (e) { err(e); }
    });
    $("rd-info").querySelectorAll("[data-k]").forEach((inp) => inp.addEventListener("change", async () => {
      const k = inp.dataset.k;
      const body = k === "p0" ? { participant_ids: inp.value ? [Number(inp.value)] : [] }
        : k === "amount_k" ? { amount_k: inp.value.trim() }
          : { [k]: k.endsWith("_id") ? (inp.value ? Number(inp.value) : null) : (inp.value || null) };
      try {
        await apiPatch(`/sitok/reports/${r.id}`, body);
        inp.classList.add("sk-filled");
        setTimeout(() => inp.classList.remove("sk-filled"), 1200);
        if (k === "kind" || k === "period_start" || k === "period_end") load(); // 종류가 바뀌면 버튼이 달라짐
      } catch (e) { err(e); }
    }));
    $("rd-info").querySelector(".rd-del").addEventListener("click", async () => {
      if (!confirm(`${title()} 보고서를 지울까요? 만든 한글·PDF도 지워집니다.`)) return;
      try { await api(`/sitok/reports/${r.id}`, { method: "DELETE" }); location.href = `sitok-facility.html?id=${r.facility_id}`; } catch (e) { err(e); }
    });
    const opener = (sel, open) => document.querySelectorAll(sel).forEach((b) => b.addEventListener("click", () => // 묶음이면 그 동 회차(data-rid)
      open(b.dataset.rid ? Number(b.dataset.rid) : r.id, b.dataset.name ? `${b.dataset.name} ${title()}` : title(), load)));
    opener(".rd-ai", openSitokAi);
    opener(".rd-detail", openSitokDetail);
    opener(".rd-survey", openSitokSurvey);
    document.querySelector(".rd-go-period")?.addEventListener("click", goPeriod);
    document.querySelector(".sk-rep-build")?.addEventListener("click", async () => {
      if (!(r.period_start && r.period_end) && !autoOk()) { goPeriod(); return; } // 10/20 형 "점검기간을 정하라는데 어디서 적는지 모름" — 자동도 못 하면 그 칸으로
      try { await apiPost(`/sitok/reports/${r.id}/build`); load(); } catch (e) { err(e); }
    });
  }

  function autoOk() { // 비어 있는 점검기간을 만들 때 자동으로 넣을 수 있음(GET /sitok/reports/{id} auto_period — 10/20 형 규칙)
    return !!(r.auto_period && r.auto_period.start && r.auto_period.end);
  }

  function goPeriod() { // 접힌 ⚙ 회차 정보를 펼쳐 빈 점검기간 칸에 표시·커서
    $("rd-info-panel").open = true;
    const inps = [...$("rd-info").querySelectorAll('[data-k="period_start"], [data-k="period_end"]')];
    inps.forEach((x) => x.classList.toggle("rd-need", !x.value));
    inps[0].scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => (inps.find((x) => !x.value) || inps[0]).focus({ preventScroll: true }), 450);
  }

  function poll() {
    if (timer) return;
    timer = setInterval(async () => {
      try {
        const x = await api(`/sitok/reports/${rid}`);
        if (x.status !== "running") { clearInterval(timer); timer = null; load(); window.dispatchEvent(new Event("sitok-report-built")); } // 분권 칸(js/sitok-split.js)도 다시
        else { const st = document.querySelector(".sk-rep-st"); if (st) st.textContent = `⏳ ${x.message}`; }
      } catch (_) { /* 다음에 다시 */ }
    }, 3000);
  }

  // 이 현장 보고서 N권(10/16 민재형 "보고서가 2개인 경우 한 개는 어디?") — 같은 카드의 다른 보고서로(그 반기 회차, 없으면 시설물 화면)
  let books = null;
  function booksBar() { // 📚 이 현장 보고서 N권 — ① 동 타일과 같은 크기 칸(10/16 형 "버튼 크기 차이"), 지금 보는 보고서 = 파란 테두리
    if (!books || books.books.length < 2) return "";
    const here = books.books.findIndex((b) => b.ids.includes(r.facility_id));
    const nameOf = (id) => (books.buildings.find((x) => x.id === id) || {}).name || "";
    const all = books.buildings.map((x) => x.name || "");
    let pre = all[0] || "";
    all.forEach((n) => { while (pre && !n.startsWith(pre)) pre = pre.slice(0, -1); });
    const short = (id) => nameOf(id).slice(pre.length).trim() || nameOf(id);
    const plain = (b) => (b.ids.length > 1 ? (b.name || nameOf(b.ids[0])) : nameOf(b.ids[0]));
    const tiles = books.books.map((b, k) => {
      const lead = books.buildings.find((x) => x.id === b.ids[0]) || {};
      const same = books.books.filter((x) => plain(x) === plain(b)).length > 1; // 묶음 이름이 같으면(번호 9-1·9-2로 가르던 것, 10/19) 건물 이름을 붙임
      const name = esc(same && b.ids.length > 1 ? `${plain(b)} ${b.ids.map(short).join("·")}` : plain(b));
      const head = `보고서 ${k + 1}${b.ids.length > 1 ? ` · ${b.ids.length}동` : ""}`; // 번호는 현장 번호 하나(10/19 뒷번호 없앰)
      const inner = (right) => `<small><span>${head}</span>${right}</small><b>${name}</b>`;
      if (k === here) return `<span class="fi-tile on" title="${name}">${inner('<em class="fi-edit">여기</em>')}</span>`;
      return lead.round ? `<a class="fi-tile" href="sitok-round.html?report=${lead.round.id}" title="${name}">${inner("")}</a>`
        : `<a class="fi-tile rd-none" href="sitok-facility.html?id=${b.ids[0]}" title="이 반기 회차가 아직 없습니다 — 시설물 화면에서 만들기">${inner('<em class="rd-none-t">회차 없음</em>')}</a>`;
    });
    return `<div class="rd-books"><div class="rd-books-h">📚 이 현장 보고서 ${books.books.length}권 <span class="fi-sub">누르면 그 보고서 회차로 — 파란 테두리가 지금 보는 보고서</span></div>
      <div class="fi-tiles">${tiles.join("")}</div></div>`;
  }

  async function load() {
    try {
      r = await api(`/sitok/reports/${rid}`);
      try { books = await api(`/sitok/facilities/${r.facility_id}/compose?year=${r.year}&half=${encodeURIComponent(["해빙기", "우기", "상반기"].includes(r.half) ? "상반기" : "하반기")}`); } catch { books = null; }
      const [d, f] = await Promise.all([api(`/sitok/facilities/${r.facility_id}/reports`), api(`/sitok/facilities/${r.facility_id}`)]);
      data = d;
      contracts = f.contracts || [];
      const fresh = d.reports.find((x) => x.id === rid); // 목록 쪽 _out(진행 표시)과 같음
      if (fresh) r = { ...fresh, facility_id: r.facility_id, facility_name: r.facility_name, group_rounds: r.group_rounds, build_left: r.build_left, auto_period: r.auto_period, build_block: r.build_block };
      draw();
    } catch (e) { err(e); }
  }
  load();
})();
