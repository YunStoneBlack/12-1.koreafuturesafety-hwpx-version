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

  const title = () => `${r.year}년 ${r.half}`;
  const personOptions = (selected) => '<option value="">—</option>' + data.persons.map((p) => `<option value="${p.id}"${p.id === selected ? " selected" : ""}>${esc(p.name)}${p.position ? ` ${esc(p.position)}` : ""}</option>`).join("");
  const big = (href, icon, label, on, sub) => `<a class="rd-btn${on ? " on" : ""}" href="${href}"><span class="rd-ic">${icon}</span><span class="rd-lb">${label}${on ? ' <em class="rd-ok">✓</em>' : ""}</span>${sub ? `<span class="rd-sub">${sub}</span>` : ""}</a>`;
  const bigBtn = (cls, icon, label, on, sub) => `<button type="button" class="rd-btn ${cls}${on ? " on" : ""}"><span class="rd-ic">${icon}</span><span class="rd-lb">${label}${on ? ' <em class="rd-ok">✓</em>' : ""}</span>${sub ? `<span class="rd-sub">${sub}</span>` : ""}</button>`;

  // 묶음 동 고르기 버튼 — 진행 표시는 아래 작은 글, 회차가 아직 없으면(묶음 보고서 만들기 때 같이 생김) 안내만
  function dongPick(d) {
    if (!d.report_id) return `<div class="rd-btn rd-off"><span class="rd-ic">🏢</span><span class="rd-lb">제${d.index}장 ${esc(d.name)}</span><span class="rd-sub">이 반기 회차가 아직 없습니다 — [묶음 보고서 만들기] 때 같이 생깁니다</span></div>`;
    const pre = (d.kind || "정기") === "정밀";
    const steps = [["현장 조사", d.has_field], ...(pre ? [["재료시험", d.has_tests], ["상태평가", d.has_rating]] : []), ["면담", d.has_survey], ["현황", d.has_detail], ["AI 초안", d.has_ai]];
    const done = d.has_field && (!pre || (d.has_tests && d.has_rating));
    return big(`sitok-round.html?report=${d.report_id}&one=1`, "🏢", `제${d.index}장 ${esc(d.name)}`, done, steps.map(([t, ok]) => `${t}${ok ? " ✓" : ""}`).join(" · "));
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
    $("rd-head").innerHTML = `<h1>${esc(dongs && g ? g.name : r.facility_name)} <span class="rd-round">${title()}</span><button type="button" class="sk-kind sk-kind-btn ${kind === "정밀" ? "pre" : ""}" title="누르면 ${kind === "정밀" ? "정기" : "정밀"}로 바꿉니다">${kind}안전점검 ▾</button></h1>
      <div class="rd-src">${r.past ? "이미 낸 보고서를 등록한 회차 — 다음 회차가 이 보고서의 데이터를 씁니다"
        : r.has_source ? `전회차 보고서: ${esc(r.source_note)}` : "전회차 보고서 없음 — 처음 맡는 시설물(우리가 하던 시설물이면 아래 [지난 보고서 한글 올리기])"}
        ${r.period_start ? ` · 점검기간 ${ymdDot(r.period_start)} ~ ${ymdDot(r.period_end)}` : ""}</div>
      ${g && !r.past ? `<div class="sk-rep-group">📚 묶음 보고서 <b>${esc(g.name)}</b> — ${g.members.map((m, i) => `제${i + 1}장 ${esc(m.name)}`).join(" · ")}
        <span class="sk-help">점검기간·제출일·기술자는 묶인 동 회차도 같이 바뀝니다. 현장 조사·현황·AI 초안은 동마다.</span></div>` : ""}
      ${g && one && !r.past ? `<a class="rd-back" href="sitok-round.html?report=${r.id}">← ${esc(g.name)} 동 고르기</a>` : ""}${booksBar()}`;

    if (dongs) {
      // 묶음 — 동 이름만(누르면 그 동 화면), 보고서 칸은 묶음 공통(만들기·합본)만
      $("rd-field").innerHTML = dongs.map(dongPick).join("");
      $("rd-report").innerHTML = "";
      $("rd-report").hidden = true;
    } else {
      $("rd-report").hidden = false;
      // 현장 점검
      $("rd-field").innerHTML = r.past ? '<div class="empty-note">이미 낸 보고서를 등록한 회차라 현장 점검은 없습니다.</div>'
        : big(`sitok-field.html?report=${r.id}`, "📱", "현장 조사", r.has_field, "결함·전경사진·공중이용·기타시설" + (kind === "정밀" ? "·자료수집·하중" : ""))
          + (kind === "정밀" ? big(`sitok-tests.html?report=${r.id}`, "📐", "재료시험", r.has_tests, "표본층·규격·강도·탄산화·기울기·부등침하")
            + big(`sitok-rating.html?report=${r.id}`, "📊", "상태평가", r.has_rating, "부재 개수 → 상태평가 등급") : "")
          + bigBtn("rd-survey", "📝", "면담·변경사항", r.has_survey, "1.2.7 보수 이력 · 1.2.8 변경사항");
      // 보고서
      $("rd-report").innerHTML = r.past ? "" : bigBtn("rd-detail", "🏢", "시설물 현황", r.has_detail, "1.1 현황표 · 1.2 구조·마감·용도")
        + bigBtn("rd-ai", "🤖", "AI 초안", r.has_ai, kind === "정밀" ? "22항목 — 결함·시험·상태평가 글" : "결과표·외관조사 서술·종합결론·등급");
    }
    const stateText = r.status === "running" ? `<span class="sk-rep-st run">⏳ ${esc(r.message)}</span>`
      : r.status === "failed" ? `<span class="sk-rep-st bad">✗ 실패: ${esc(r.message)}</span>`
        : r.status === "done" ? doneText() : '<span class="sk-rep-st">아직 안 만듦</span>';
    const v = encodeURIComponent(r.made_at || "");
    $("rd-build").innerHTML = `<div class="sk-rep-foot">${stateText}
      ${r.has_pdf ? `<a class="secondary-link" href="${BASE}/api/sitok/reports/${r.id}/file/pdf?v=${v}" target="_blank" rel="noopener">${kind === "정밀" ? "합본 PDF" : "PDF 보기"}</a>` : ""}
      ${r.has_hwpx ? `<a class="secondary-link" href="${BASE}/api/sitok/reports/${r.id}/file/hwpx?v=${v}">${kind === "정밀" ? "본문 한글" : "한글 받기"}</a>` : ""}
      ${r.has_appendix ? `<a class="secondary-link" href="${BASE}/api/sitok/reports/${r.id}/file/appendix?v=${v}">부록 한글</a>` : ""}
      ${r.past ? "" : `<button type="button" class="sk-rep-build"${r.status === "running" ? " disabled" : ""}>${r.has_pdf ? "다시 만들기" : g ? `묶음 보고서 만들기(${g.members.length}동)` : "보고서 만들기"}</button>`}</div>
      ${r.past ? "" : `<div class="rd-source"><label class="secondary-link" title="이력·시설물 현황·지난 평가 같은 데이터만 가져옵니다(보고서 틀은 회사 원본)">지난 보고서 한글 올리기<input type="file" accept=".hwp,.hwpx" hidden data-kr-file="1" /></label>
        <span class="sk-help rd-source-msg">직전 회차가 없거나 다른 회사가 만든 지난 보고서(.hwp·.hwpx)를 올리면 전회차 데이터로 씁니다.</span></div>`}`;
    // 회차 정보
    const conList = data.group && data.group_contracts ? data.group_contracts : contracts;
    const contractOpts = '<option value="">계약 고르기</option>' + conList.map((c) =>
      `<option value="${c.id}"${c.id === r.contract_id ? " selected" : ""}>${c.facility ? `[${esc(c.facility)}] ` : ""}${esc(c.sector)} · ${esc(c.title || "계약")} (${esc(c.start_date)}~${esc(c.end_date)})</option>`).join("");
    const parts = r.participant_ids || [];
    $("rd-info").innerHTML = `<div class="sk-rep-grid">
        <label>계약<span class="sk-help"></span><select data-k="contract_id">${contractOpts}</select></label>
        <label>종류 <span class="sk-help">계약서 회차 줄에서 자동 — 틀리면 직접</span><select data-k="kind">${["정기", "정밀"].map((k) => `<option${k === kind ? " selected" : ""}>${k}</option>`).join("")}</select></label>
        <label>점검기간 시작 <span class="sk-help">민간 = 현장 간 날</span><input type="date" data-k="period_start" value="${esc(r.period_start)}" /></label>
        <label>점검기간 끝 <span class="sk-help">민간 = 보고서 낸 날</span><input type="date" data-k="period_end" value="${esc(r.period_end)}" /></label>
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
    document.querySelector(".sk-rep-build")?.addEventListener("click", async () => {
      try { await apiPost(`/sitok/reports/${r.id}/build`); load(); } catch (e) { err(e); }
    });
    const file = document.querySelector(".rd-source input[type=file]");
    if (file) {
      file.addEventListener("change", async () => {
        if (!file.files[0]) return;
        const msg = document.querySelector(".rd-source-msg");
        msg.textContent = `${file.files[0].name} 올리는 중…(hwp는 한글로 바꾸느라 20~40초)`;
        try {
          const fd = new FormData();
          fd.append("file", file.files[0]);
          await apiUpload(`/sitok/reports/${r.id}/source`, fd);
          load();
        } catch (e) { err(e); load(); }
      });
      enableFileDrop(document.querySelector(".rd-source"), file);
    }
  }

  function poll() {
    if (timer) return;
    timer = setInterval(async () => {
      try {
        const x = await api(`/sitok/reports/${rid}`);
        if (x.status !== "running") { clearInterval(timer); timer = null; load(); }
        else { const st = document.querySelector(".sk-rep-st"); if (st) st.textContent = `⏳ ${x.message}`; }
      } catch (_) { /* 다음에 다시 */ }
    }, 3000);
  }

  // 이 현장 보고서 N권(10/16 민재형 "보고서가 2개인 경우 한 개는 어디?") — 같은 카드의 다른 보고서로(그 반기 회차, 없으면 시설물 화면)
  let books = null;
  function booksBar() {
    if (!books || books.books.length < 2) return "";
    const here = books.books.findIndex((b) => b.ids.includes(r.facility_id));
    const nameOf = (id) => (books.buildings.find((x) => x.id === id) || {}).name || "";
    return `<div class="rd-books">📚 이 현장 보고서 ${books.books.length}권 — ${books.books.map((b, k) => {
      const lead = books.buildings.find((x) => x.id === b.ids[0]) || {};
      const label = `보고서 ${k + 1} · ${esc(lead.mgmt_no || "")} ${esc(b.ids.length > 1 ? (b.name || nameOf(b.ids[0])) : nameOf(b.ids[0]))}${b.ids.length > 1 ? ` <small>${b.ids.length}동</small>` : ""}`;
      if (k === here) return `<span class="rd-book on">${label} <small>(여기)</small></span>`;
      return lead.round ? `<a class="rd-book" href="sitok-round.html?report=${lead.round.id}">${label} ›</a>`
        : `<a class="rd-book none" href="sitok-facility.html?id=${b.ids[0]}" title="이 반기 회차가 아직 없습니다 — 시설물 화면에서 만들기">${label} <small>회차 없음</small> ›</a>`;
    }).join("")}</div>`;
  }

  async function load() {
    try {
      r = await api(`/sitok/reports/${rid}`);
      try { books = await api(`/sitok/facilities/${r.facility_id}/compose?year=${r.year}&half=${encodeURIComponent(["해빙기", "우기", "상반기"].includes(r.half) ? "상반기" : "하반기")}`); } catch { books = null; }
      const [d, f] = await Promise.all([api(`/sitok/facilities/${r.facility_id}/reports`), api(`/sitok/facilities/${r.facility_id}`)]);
      data = d;
      contracts = f.contracts || [];
      const fresh = d.reports.find((x) => x.id === rid); // 목록 쪽 _out(진행 표시)과 같음
      if (fresh) r = { ...fresh, facility_id: r.facility_id, facility_name: r.facility_name, group_rounds: r.group_rounds };
      draw();
    } catch (e) { err(e); }
  }
  load();
})();
