// 제출 현황(status.html) — 그달(지도일 기준) 보고서 상태·월별 막대·요원별 현황.
// 데이터는 GET /submission/overview 한 번(server/api/routers/submission.py). "제출 완료" 판정은 서버 server/api/submission.py 한 곳.
// 할 일 버튼: 📧 전송(mail.js 전송 창 그대로) · 직접 제출함/되돌리기 · 📤 K2B 제출(js/k2b-submit.js 창 그대로) · K2B 직접 제출함 · 이어서 작성.
// 제출 완료 = 전송(또는 직접 제출함) + K2B(2026-10-10). 전송만 하고 K2B가 안 됐으면 "K2B 미제출".
// (2026-10-01 "마지막 지도일 + 15일" 기한 임박·초과 칸과 목록은 없앰 — 실제 규칙이 아니었음.)

const errorEl = document.getElementById("error");
const today = new Date();
const stView = { year: today.getFullYear(), month: today.getMonth() + 1, staff: "", filter: "all", open: false, site: null, progAll: false };
let stData = null;

const STATE = {
  writing: ["작성 중", "draft"],
  outdated: ["수정 전 버전", "rejected"],
  pdf_ready: ["PDF 완료·미전송", "pending"],
  k2b_missing: ["K2B 미제출", "pending"],
  submitted: ["제출 완료", "approved"],
};

function h(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function md(iso) {
  const d = new Date(`${iso}T00:00:00`);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

async function loadStatus() {
  errorEl.style.display = "none";
  document.getElementById("st-month-label").textContent = `${stView.year}년 ${stView.month}월`;
  try {
    const q = new URLSearchParams({ year: stView.year, month: stView.month });
    if (stView.staff) q.set("staff_id", stView.staff);
    stData = await api(`/submission/overview?${q}`);
    render();
  } catch (err) {
    showError(errorEl, err);
  }
}

function render() {
  if (stView.site && !(stData.progress || []).some((e) => e.site_id === stView.site)) stView.site = null;
  renderCards();
  renderChart();
  renderStaff();
  renderProgress();
  renderList();
}

// 현장별 그달 추진 현황(10/27 사용자 "26-4 10월 배정 4회차, 4회차 중 2회차 완료 — 그래프로") — 배정 = 방문 달력 예정(없으면 보고서 수),
// 막대 = 제출 완료(초록) · 보고서만 작성(주황) · 남은 회차(회색). 누르면 아래 목록을 그 현장만(다시 누르면 전체).
// 10/28 사용자 "지역별로 묶어서 · 전체 회차가 많이 부족한 현장": 보기 [N월 추진 | 회차 부족] + [📍 지역별](시·군마다 합계 한 줄, 누르면 펼침) — 이 기기에 기억.
// 회차 부족 = 서버 shortage(현장 목록 진행 막대와 같은 계산 — 우리 계약기간 경과율 × 총 회차 = 지금쯤 했어야 할 회차, 빨간 선)에서 MANY회 이상 모자란 곳, 누르면 현장 화면.
const PROG_KEY = "kfsc-report:st-prog";
const MANY = 3; // "많이 부족" — 지금쯤 했어야 할 회차보다 3회 이상 모자람(38곳 중 1~2회는 반올림·월초 차이가 많아서)
try { const v = JSON.parse(localStorage.getItem(PROG_KEY) || "{}"); stView.progMode = v.progMode === "short" ? "short" : "month"; stView.byRegion = !!v.byRegion; } catch { stView.progMode = "month"; }
const openRegions = new Set(); // 펼친 지역 "month:포천"
function saveProg() { try { localStorage.setItem(PROG_KEY, JSON.stringify({ progMode: stView.progMode, byRegion: stView.byRegion })); } catch { /* 지금만 */ } }

// [📅 N회 채워 넣기](10/28 사용자 2번) — 남은 회차 > 오늘 이후 예정인 현장을 방문 달력 [채워 넣기](js/auto-plan.js openShortFill, POST /calendar/short/fill)로
// 미리보기 → [이대로 넣기]. 서버가 세는 남은 회차·예정이 이 화면과 같음(done_counts·오늘 이후 예정). 우리 계약기간이 끝난 현장은 넣을 날이 없어 글만.
const todayIso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`; // 현지 날짜(toISOString은 UTC라 새벽에 하루 어긋남)
const canFill = (e) => !e.period_over && (!e.period_end || e.period_end > todayIso);
const fillChip = (e, lack) => (lack && canFill(e) && typeof openShortFill === "function"
  ? `<button type="button" class="st-fill" data-fill="${e.site_id}" data-name="${h(e.site_name)}" title="오늘 이후 예정이 남은 회차보다 ${lack}회 모자람 — 방문 달력에 채워 넣기(미리보기 뒤 넣음)">📅 ${lack}회 채워 넣기</button>`
  : lack ? `<span class="warn">예정 ${lack}회 모자람</span>` : "");
function onFilled(res) {
  stView.progMsg = `✓ ${res.added}회를 방문 달력에 넣었습니다${res.stuck ? ` · ${res.stuck}회는 마감 전에 넣을 날이 없습니다` : ""}`;
  loadStatus();
}

function progBar(parts) { // parts = [[클래스, %]], 빨간 선은 ["ideal", %]
  return `<span class="st-prog-bar">${parts.map(([c, v]) => (c === "ideal" ? `<i class="ideal" style="left:${v}%"></i>` : `<span class="${c}" style="width:${v}%"></span>`)).join("")}</span>`;
}

function monthRow(e) {
  const left = Math.max(e.assigned - e.reports, 0);
  const full = e.reports >= e.assigned;
  const pct = (n) => (e.assigned ? (n / e.assigned) * 100 : 0);
  const tip = `${e.site_name} — 배정 ${e.assigned}회차(달력 예정 ${e.planned}) · 보고서 ${e.reports} · 제출 완료 ${e.submitted}${left ? ` · 남음 ${left}` : ""}`;
  return `<button type="button" class="st-prog-row${full ? " full" : ""}${stView.site === e.site_id ? " sel" : ""}" data-site="${e.site_id}" title="${h(tip)}">
      <span class="nm">${h(e.site_name)}</span>
      ${progBar([["ok", pct(e.submitted)], ["wait", pct(e.reports - e.submitted)]])}
      <span class="num"><b>${e.reports} / ${e.assigned}회차</b>${full ? ' <i class="st-prog-done">완료</i>' : ""}<small>제출 ${e.submitted}${left ? ` · 남음 ${left}` : ""}</small></span>
    </button>`;
}

function shortRow(e) {
  const pct = (n) => (e.total ? Math.min((n / e.total) * 100, 100) : 0);
  const lack = Math.max(e.left - e.upcoming, 0); // 남은 회차보다 오늘 이후 예정이 모자람 — 방문 달력 [채워 넣기]
  const sub = [e.next_plan ? `다음 ${md(e.next_plan)}` : '<span class="warn">예정 없음</span>', fillChip(e, lack),
    e.period_over ? '<span class="warn">계약기간 끝남</span>' : ""].filter(Boolean).join(" · ");
  const tip = `${e.site_name} — 지금쯤 ${e.ideal}회 했어야 하는데 ${e.performed}회(${e.diff}회 부족) · 총 ${e.total}회 · 남은 ${e.left}회 · 오늘 이후 예정 ${e.upcoming}회`
    + `${e.total_months && e.elapsed_months != null ? ` · 공기 ${e.elapsed_months}/${e.total_months}개월 경과` : ""}`
    + `${e.monthly_needed != null ? ` · 남은 기간 월 ${e.monthly_needed}회 필요` : ""}${e.last_visit ? ` · 최근 지도 ${e.last_visit}` : ""} — 누르면 현장 화면`;
  return `<div class="st-prog-row short" role="link" tabindex="0" data-link="site.html?id=${e.site_id}" title="${h(tip)}">
      <span class="nm"><span class="t">${h(e.site_name)}</span><small>${sub}</small></span>
      ${progBar([["ok", pct(e.performed)], ["ideal", pct(e.ideal)]])}
      <span class="num"><b class="lack">${e.diff}회 부족</b><small>${e.performed} / ${e.total}회${e.monthly_needed != null ? ` · 월 ${e.monthly_needed}회` : ""}</small></span>
    </div>`;
}

// ⏰ 계약 끝 임박(10/28 사용자 4번) — 서버 ending(우리 계약기간 끝 60일 안 + 남은 회차가 있는데 예정이 모자람·월 8회 넘게 필요·기간 지남), 두 보기 모두 맨 위, 누르면 현장 화면
function endingBox(list) {
  if (!list.length) return "";
  const SHOW_END = 4;
  const shown = stView.endAll ? list : list.slice(0, SHOW_END);
  const row = (e) => {
    const dday = e.days_left < 0 ? `기간 ${-e.days_left}일 지남` : e.days_left === 0 ? "오늘 끝" : `D-${e.days_left}`;
    const lack = Math.max(e.left - e.upcoming, 0);
    const sub = [`${md(e.period_end)} 끝`, lack ? fillChip({ ...e, period_over: e.days_left <= 0 }, lack) : `예정 ${e.upcoming}회`,
      e.monthly_needed != null && e.days_left >= 14 ? `${e.monthly_needed > 8 ? '<span class="warn">' : "<span>"}월 ${e.monthly_needed}회</span>` : ""].filter(Boolean).join(" · "); // 2주 안 남은 현장은 월 횟수가 뜻이 없어 뺌
    return `<div class="st-end-row" role="link" tabindex="0" data-link="site.html?id=${e.site_id}" title="${h(`${e.site_name} — 우리 계약기간 끝 ${e.period_end} · 남은 ${e.left}회 · 오늘 이후 예정 ${e.upcoming}회 — 누르면 현장 화면`)}">
        <span class="nm"><span class="t">${h(e.site_name)}</span><small>${sub}</small></span>
        <span class="num"><b>${dday}</b><small>남은 ${e.left}회</small></span></div>`;
  };
  const fill = list.filter((e) => e.left > e.upcoming && e.days_left > 0);
  return `<div class="st-end"><div class="st-end-h"><b>⏰ 계약 끝 임박 ${list.length}곳</b><span class="st-hint">계약 끝 60일 안인데 남은 회차를 다 하기 어렵거나(예정 모자람·월 8회 넘게) 기간이 지난 곳</span>
    ${fill.length > 1 && typeof openShortFill === "function" ? `<button type="button" class="st-fill-all" data-ids="${fill.map((e) => e.site_id).join(",")}" data-name="계약 끝 임박 ${fill.length}곳">📅 예정 모자란 ${fill.length}곳 모두 채워 넣기</button>` : ""}</div>
    ${shown.map(row).join("")}
    ${list.length > SHOW_END ? `<button type="button" class="secondary st-end-more">${stView.endAll ? "접기 ▲" : `나머지 ${list.length - SHOW_END}곳 ▼`}</button>` : ""}</div>`;
}

// 지역(시·군)마다 합계 한 줄 — 누르면 그 지역 현장들. 차례 = 남은 회차(이달)·부족 회차(회차 부족)가 많은 지역부터.
function regionGroups(list, mode) {
  const groups = new Map();
  for (const e of list) {
    const k = e.region || "지역 모름";
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(e);
  }
  const sum = (xs, f) => xs.reduce((a, x) => a + f(x), 0);
  const weight = (xs) => (mode === "short" ? sum(xs, (x) => x.diff) : sum(xs, (x) => Math.max(x.assigned - x.reports, 0)));
  return [...groups.entries()].sort((a, b) => weight(b[1]) - weight(a[1]) || b[1].length - a[1].length || a[0].localeCompare(b[0])).map(([k, xs]) => {
    const key = `${mode}:${k}`, open = openRegions.has(key);
    let bar, num;
    if (mode === "short") {
      const tot = sum(xs, (x) => x.total), perf = sum(xs, (x) => x.performed), ideal = sum(xs, (x) => x.ideal);
      const pct = (n) => (tot ? Math.min((n / tot) * 100, 100) : 0);
      const noPlan = xs.filter((x) => x.left > x.upcoming).length;
      bar = progBar([["ok", pct(perf)], ["ideal", pct(ideal)]]);
      num = `<b class="lack">${sum(xs, (x) => x.diff)}회 부족</b><small>${noPlan ? `<span class="warn">예정 모자람 ${noPlan}곳</span>` : `남은 ${sum(xs, (x) => x.left)}회`}</small>`;
    } else {
      const asg = sum(xs, (x) => x.assigned), rep = sum(xs, (x) => x.reports), sub = sum(xs, (x) => x.submitted);
      const pct = (n) => (asg ? (n / asg) * 100 : 0);
      bar = progBar([["ok", pct(sub)], ["wait", pct(rep - sub)]]);
      num = `<b>${rep} / ${asg}회차</b><small>제출 ${sub}${asg > rep ? ` · 남음 ${asg - rep}` : ""}</small>`;
    }
    const rows = open ? xs.map(mode === "short" ? shortRow : monthRow).join("") : "";
    return `<button type="button" class="st-prog-grp${open ? " open" : ""}" data-region="${h(key)}" aria-expanded="${open}">
        <span class="nm"><i class="chev" aria-hidden="true">${open ? "▾" : "▸"}</i>${h(k)} <small>${xs.length}곳</small></span>${bar}<span class="num">${num}</span></button>${rows}`;
  }).join("");
}

function renderProgress() {
  const box = document.getElementById("st-prog-box");
  const mode = stView.progMode === "short" ? "short" : "month";
  const shortAll = stData.shortage || [];
  const many = shortAll.filter((e) => e.diff >= MANY);
  const shortFill = (stView.shortAll ? shortAll : many).filter((e) => e.left > e.upcoming && canFill(e)); // 회차 부족 목록 중 채워 넣을 수 있는 곳
  let list = mode === "short" ? (stView.shortAll ? shortAll : many) : (stData.progress || []);
  if (mode === "month" && stView.open) list = list.filter((e) => e.submitted < e.assigned);
  const done = (stData.progress || []).filter((e) => e.reports >= e.assigned).length;
  const SHOW = 12; // 묶지 않을 땐 처음 12곳(폰에서 55곳이 다 펼쳐져 너무 길던 것), 나머지는 더 보기
  const grouped = !!stView.byRegion;
  const shown = grouped || stView.progAll || list.length <= SHOW + 2 ? list : list.slice(0, SHOW);
  const body = grouped ? regionGroups(list, mode) : shown.map(mode === "short" ? shortRow : monthRow).join("");
  const hint = mode === "short"
    ? `· 진행 중 현장 중 지금쯤 했어야 할 회차(우리 계약기간 경과율 × 총 회차, 빨간 선)보다 ${MANY}회 이상 모자란 곳 · 누르면 현장 화면`
    : `· ${(stData.progress || []).length}곳 중 ${done}곳 다 다녀옴 · 배정 = 방문 달력 예정(없으면 보고서 수) · 누르면 보고서 목록을 그 현장만`;
  const legend = mode === "short"
    ? '<span><i class="ok"></i>다녀온 회차</span><span><i class="ideal"></i>지금쯤 했어야 할 회차</span>'
    : '<span><i class="ok"></i>제출 완료</span><span><i class="wait"></i>보고서만 작성</span><span><i class="left"></i>남은 회차</span>';
  const empty = mode === "short" ? `<div class="st-empty">${MANY}회 이상 모자란 진행 중 현장이 없습니다.</div>` : '<div class="st-empty">이달 배정·보고서가 없습니다.</div>';
  box.innerHTML = `<div class="st-chart-head"><b>현장별 ${mode === "short" ? "회차 부족" : `${stData.month}월 추진 현황`} <span class="st-hint">${hint}</span></b>
      <div class="st-legend">${legend}</div></div>
    ${endingBox(stData.ending || [])}
    <div class="st-prog-tools">
      <span class="site-sort st-prog-mode" role="group" aria-label="보기"><button type="button" data-mode="month" class="${mode === "month" ? "on" : ""}">${stData.month}월 추진</button><button type="button" data-mode="short" class="${mode === "short" ? "on" : ""}" title="지금쯤 했어야 할 회차보다 ${MANY}회 이상 모자란 진행 중 현장">회차 부족 <b>${many.length}</b></button></span>
      <button type="button" class="st-prog-region${grouped ? " on" : ""}" aria-pressed="${grouped}" title="시·군으로 묶어 지역마다 합계 — 누르면 그 지역 현장">📍 지역별</button>
      ${grouped ? `<button type="button" class="st-prog-fold" title="지역을 모두 펼치기·접기">${list.some((e) => openRegions.has(`${mode}:${e.region || "지역 모름"}`)) ? "모두 접기" : "모두 펼치기"}</button>` : ""}
    </div>
    ${list.length ? `<div class="st-prog-list${grouped ? " grouped" : ""}${mode === "short" ? " short" : ""}">${body}</div>` : empty}
    ${!grouped && list.length > shown.length ? `<button type="button" class="secondary st-prog-more">나머지 ${list.length - shown.length}곳 더 보기 ▼</button>`
      : !grouped && stView.progAll && list.length > SHOW + 2 ? '<button type="button" class="secondary st-prog-more">접기 ▲</button>' : ""}
    ${mode === "short" ? `<div class="st-prog-foot">${shortAll.length > many.length ? `<button type="button" class="secondary st-short-all">${stView.shortAll ? `${MANY}회 이상만 보기` : `1~${MANY - 1}회 부족 ${shortAll.length - many.length}곳도 보기`}</button>` : ""}
      ${shortFill.length > 1 && typeof openShortFill === "function" ? `<button type="button" class="st-fill-all" data-ids="${shortFill.map((e) => e.site_id).join(",")}" data-name="회차 부족 현장 중 예정 모자란 ${shortFill.length}곳">📅 예정 모자란 ${shortFill.length}곳 모두 채워 넣기</button>` : ""}
      <span>넣은 예정은 <a href="calendar.html">방문 달력</a>에서 옮기거나 지울 수 있습니다.</span></div>` : ""}`;
  if (stView.progMsg) { // 채워 넣은 뒤 한 번
    box.insertAdjacentHTML("afterbegin", `<div class="status ok st-prog-msg">${h(stView.progMsg)} — <a href="calendar.html">방문 달력 보기</a></div>`);
    stView.progMsg = "";
  }
  box.querySelector(".st-prog-more")?.addEventListener("click", () => { stView.progAll = !stView.progAll; renderProgress(); });
  box.querySelectorAll(".st-prog-mode button").forEach((b) => b.addEventListener("click", () => { stView.progMode = b.dataset.mode; saveProg(); renderProgress(); }));
  box.querySelector(".st-prog-region").addEventListener("click", () => { stView.byRegion = !stView.byRegion; saveProg(); renderProgress(); });
  box.querySelector(".st-prog-fold")?.addEventListener("click", () => {
    const keys = [...new Set(list.map((e) => `${mode}:${e.region || "지역 모름"}`))];
    const anyOpen = keys.some((k) => openRegions.has(k));
    keys.forEach((k) => (anyOpen ? openRegions.delete(k) : openRegions.add(k)));
    renderProgress();
  });
  box.querySelector(".st-short-all")?.addEventListener("click", () => { stView.shortAll = !stView.shortAll; renderProgress(); });
  box.querySelectorAll(".st-prog-grp").forEach((b) => b.addEventListener("click", () => {
    const k = b.dataset.region;
    if (openRegions.has(k)) openRegions.delete(k);
    else openRegions.add(k);
    renderProgress();
  }));
  box.querySelectorAll(".st-prog-row[data-link], .st-end-row[data-link]").forEach((b) => {
    b.addEventListener("click", (e) => { if (!e.target.closest("button, a")) location.href = b.dataset.link; });
    b.addEventListener("keydown", (e) => { if ((e.key === "Enter" || e.key === " ") && e.target === b) { e.preventDefault(); location.href = b.dataset.link; } });
  });
  box.querySelectorAll(".st-fill").forEach((b) => b.addEventListener("click", (e) => { e.stopPropagation(); openShortFill([Number(b.dataset.fill)], b.dataset.name, onFilled); }));
  box.querySelectorAll(".st-fill-all").forEach((b) => b.addEventListener("click", () => openShortFill(b.dataset.ids.split(",").map(Number), b.dataset.name, onFilled)));
  box.querySelector(".st-end-more")?.addEventListener("click", () => { stView.endAll = !stView.endAll; renderProgress(); });
  box.querySelectorAll(".st-prog-row[data-site]").forEach((b) => b.addEventListener("click", () => {
    const id = Number(b.dataset.site);
    stView.site = stView.site === id ? null : id;
    renderProgress();
    renderList();
  }));
}

function renderCards() {
  const c = stData.cards;
  const cards = [
    ["all", `${stData.month}월 보고서`, c.total, "지도일 기준", ""],
    ["submitted", "제출 완료", c.submitted, "전송 + K2B 둘 다", "ok"],
    ["k2b_missing", "K2B 미제출", c.k2b_missing, "전송은 함 · K2B만 남음", "wait"],
    ["pdf_ready", "PDF 완료·미전송", c.pdf_ready, "전송·K2B 둘 다 남음", "wait"],
    ["pending", "작성 중·수정 전", c.writing + c.outdated, `작성 중 ${c.writing} · 수정 전 버전 ${c.outdated}`, "idle"],
  ];
  const el = document.getElementById("st-cards");
  el.innerHTML = cards.map(([key, label, n, sub, tone]) => `
    <button type="button" class="st-card ${tone}${stView.filter === key ? " active" : ""}" data-filter="${key}">
      <span class="l">${tone ? `<i class="st-dot ${tone}"></i>` : ""}${label}</span>
      <span class="n">${n}</span><span class="s">${h(sub)}</span>
    </button>`).join("");
  el.querySelectorAll(".st-card").forEach((b) => b.addEventListener("click", () => {
    stView.filter = stView.filter === b.dataset.filter ? "all" : b.dataset.filter;
    renderCards();
    renderList();
  }));
}

function renderChart() {
  document.getElementById("st-year-label").textContent = `${stData.year}년`;
  const max = Math.max(1, ...stData.months.map((m) => m.submitted + m.pending));
  // 폰은 좁아서 선택한 달까지 최근 6개월만(style.css .st-bar.far)
  const from = Math.max(1, Math.min(stData.month - 5, 7));
  document.getElementById("st-bars").innerHTML = stData.months.map((m) => {
    const total = m.submitted + m.pending;
    const sel = m.month === stData.month ? " sel" : "";
    const far = m.month < from || m.month > from + 5 ? " far" : "";
    const segs = total
      ? (m.pending ? `<span class="seg wait" style="height:${(m.pending / max) * 100}%"></span>` : "") +
        (m.submitted ? `<span class="seg ok" style="height:${(m.submitted / max) * 100}%"></span>` : "")
      : '<span class="stub"></span>';
    return `<button type="button" class="st-bar${sel}${far}" data-month="${m.month}"
        title="${m.month}월 ${total}건 — 제출 완료 ${m.submitted} · 미제출 ${m.pending}">
      <span class="v">${total}</span><span class="col">${segs}</span><span class="m">${m.month}월</span></button>`;
  }).join("");
  document.querySelectorAll("#st-bars .st-bar").forEach((b) => b.addEventListener("click", () => {
    stView.month = Number(b.dataset.month);
    loadStatus();
  }));
}

function renderStaff() {
  const box = document.getElementById("st-staff-box");
  const rows = stData.staff.map((s) => {
    const pct = s.total ? (s.submitted / s.total) * 100 : 0;
    return `<div class="st-staff-row"><span class="nm">${h(s.name)}</span>
      <span class="st-staff-bar">${s.total ? `<span class="ok" style="width:${pct}%"></span><span class="wait" style="width:${100 - pct}%"></span>` : ""}</span>
      <span class="num">제출 ${s.submitted} / ${s.total}건</span></div>`;
  }).join("");
  box.innerHTML = `<b>요원별 ${stData.month}월</b>${rows || '<div class="st-empty">이달 보고서가 없습니다.</div>'}`;
}

function reportActions(r) {
  const open = `<a class="secondary-link" href="report.html?id=${r.id}">${r.state === "writing" ? "이어서 작성" : "보고서 열기"}</a>`;
  if (r.state === "pdf_ready") {
    return `<button type="button" class="st-send" data-id="${r.id}">📧 전송</button>` +
      `<button type="button" class="secondary st-mark" data-id="${r.id}">직접 제출함</button>`;
  }
  if (r.state === "k2b_missing") {
    return `<button type="button" class="st-k2b" data-id="${r.id}">📤 K2B 제출</button>` +
      `<button type="button" class="secondary st-k2b-mark" data-id="${r.id}">K2B 직접 제출함</button>`;
  }
  if (r.state === "submitted" && r.modified_after) {
    return `<button type="button" class="st-send" data-id="${r.id}">📧 다시 전송</button>${open}`;
  }
  return open;
}

// 고객사 전송 예약(10/26) — "⏰ 10/27 09:00 예약" / "⚠ 예약 못 보냄"
function schedLine(r) {
  const s = r.mail_schedule;
  if (!s) return "";
  return s.status === "failed"
    ? `<em class="st-sched bad" title="${h(s.message || "")}">⚠ 예약 못 보냄</em>`
    : `<em class="st-sched">⏰ ${md(s.run_at.slice(0, 10))} ${s.run_at.slice(11, 16)} 예약</em>`;
}

function submittedCell(r) {
  if (!r.submitted_at) return r.mail_schedule ? schedLine(r) : '<span class="st-none">—</span>';
  const when = md(r.submitted_at.slice(0, 10));
  const main = r.submitted_via === "mail"
    ? `📧 ${when} 전송<span>${r.to_count}곳${r.submitted_by ? ` · ${h(r.submitted_by)}` : ""}</span>`
    : `✋ ${when} 직접 제출<span>${r.submitted_by ? `${h(r.submitted_by)} 표시` : ""}</span>`;
  const undo = r.has_mark ? `<button type="button" class="st-unmark" data-id="${r.id}">되돌리기</button>` : "";
  const mod = r.modified_after ? '<em class="st-mod">⚠ 제출 뒤 수정됨</em>' : "";
  return `<div class="st-sent">${main}</div>${mod}${schedLine(r)}${undo}`;
}

// K2B 칸 — 웹 [K2B 제출] 성공(누르면 저장된 K2B 화면) / K2B 직접 제출함 표시 / 전송은 했는데 안 됨(⚠)
function k2bCell(r) {
  if (r.k2b_via === "web") {
    const when = md(r.k2b_at.slice(0, 10));
    return `<div class="st-sent"><a class="st-k2b-shot" href="${BASE}/api/k2b-jobs/${r.k2b_job_id}/shot" target="_blank" rel="noopener"
      title="눌러서 저장된 K2B 화면 보기">✓ K2B ${when}</a><span>${r.k2b_round ? `${r.k2b_round}차` : ""}${r.k2b_by ? `${r.k2b_round ? " · " : ""}${h(r.k2b_by)}` : ""}</span></div>`;
  }
  if (r.k2b_via === "manual") {
    return `<div class="st-sent">✋ K2B ${md(r.k2b_at.slice(0, 10))} 직접<span>${r.k2b_by ? `${h(r.k2b_by)} 표시` : ""}</span></div>` +
      `<button type="button" class="st-k2b-unmark" data-id="${r.id}">되돌리기</button>`;
  }
  if (r.state === "k2b_missing") return '<em class="st-k2b-miss">⚠ K2B 미제출</em>';
  return '<span class="st-none">—</span>';
}

function filteredReports() {
  let rows = stData.reports;
  if (stView.site) rows = rows.filter((r) => r.site_id === stView.site); // 현장별 추진 현황에서 고른 현장
  if (stView.open) rows = rows.filter((r) => r.state !== "submitted" || r.modified_after);
  const f = stView.filter;
  if (f === "submitted") rows = rows.filter((r) => r.state === "submitted");
  else if (f === "pdf_ready") rows = rows.filter((r) => r.state === "pdf_ready");
  else if (f === "k2b_missing") rows = rows.filter((r) => r.state === "k2b_missing");
  else if (f === "pending") rows = rows.filter((r) => r.state === "writing" || r.state === "outdated");
  return rows;
}

function renderList() {
  const el = document.getElementById("st-list");
  const rows = filteredReports();
  let html = "";
    html += `<div class="st-head"><span>${stData.month}월 보고서 (지도일 기준)</span><span>회차</span><span>지도일</span><span>담당</span><span>상태</span><span>전송</span><span>K2B</span><span></span></div>`;
    html += rows.length ? rows.map((r) => {
      const [label, pill] = STATE[r.state];
      return `<div class="st-rep ${r.state}" data-id="${r.id}" title="눌러서 보고서 열기">
        <div class="c-site"><a class="st-site" href="site.html?id=${r.site_id}">${h(r.site_name)}</a><div class="st-sub">${h(r.hq_company)}</div>
          <div class="c-meta">${r.visit_no}회차 · ${md(r.date)}${r.has_guidance_date ? "" : "(만든 날)"} · ${h(r.staff_name || "담당 미지정")}</div></div>
        <div class="c-no">${r.visit_no}</div>
        <div class="c-date">${md(r.date)}${r.has_guidance_date ? "" : '<span class="st-sub"> (만든 날)</span>'}</div>
        <div class="c-staff">${h(r.staff_name || "미지정")}</div>
        <div class="c-state"><span class="status-pill ${pill}">${label}</span></div>
        <div class="c-sent">${submittedCell(r)}</div>
        <div class="c-k2b">${k2bCell(r)}</div>
        <div class="st-act">${reportActions(r)}</div>
      </div>`;
    }).join("") : '<div class="empty-note">해당하는 보고서가 없습니다.</div>';
  el.innerHTML = html;
  bindListActions(el);
}

function bindListActions(el) {
  const find = (id) => stData.reports.find((r) => r.id === Number(id));
  // 행의 빈 곳을 누르면 보고서 열기(2026-10-10 사용자) — 버튼·링크·글자 고르기 중엔 그대로
  el.querySelectorAll(".st-rep").forEach((row) => row.addEventListener("click", (e) => {
    if (e.target.closest("a, button") || String(window.getSelection())) return;
    location.href = `report.html?id=${row.dataset.id}`;
  }));
  el.querySelectorAll(".st-send").forEach((b) => b.addEventListener("click", () => {
    const r = find(b.dataset.id);
    openMailModal(r.id, `${r.site_name} ${r.visit_no}회차`, loadStatus);
  }));
  el.querySelectorAll(".st-mark").forEach((b) => b.addEventListener("click", async () => {
    const r = find(b.dataset.id);
    if (!confirm(`${r.site_name} ${r.visit_no}회차를 "직접 제출함"으로 표시할까요?\n(메일 말고 직접 보냈거나 출력해서 낸 경우 — 누가 언제 표시했는지 남습니다)`)) return;
    try { await apiPost(`/reports/${r.id}/submit-mark`); loadStatus(); } catch (err) { showError(errorEl, err); }
  }));
  el.querySelectorAll(".st-k2b").forEach((b) => b.addEventListener("click", () => {
    const r = find(b.dataset.id);
    openK2bModal(r.id, `${r.site_name} ${r.visit_no}회차`, loadStatus);
  }));
  el.querySelectorAll(".st-k2b-mark").forEach((b) => b.addEventListener("click", async () => {
    const r = find(b.dataset.id);
    if (!confirm(`${r.site_name} ${r.visit_no}회차를 "K2B 직접 제출함"으로 표시할까요?
(웹 [K2B 제출] 말고 K2B 사이트에 직접 넣은 경우 — 누가 언제 표시했는지 남습니다)`)) return;
    try { await apiPost(`/reports/${r.id}/k2b-mark`); loadStatus(); } catch (err) { showError(errorEl, err); }
  }));
  el.querySelectorAll(".st-k2b-unmark").forEach((b) => b.addEventListener("click", async () => {
    const r = find(b.dataset.id);
    if (!confirm(`${r.site_name} ${r.visit_no}회차의 "K2B 직접 제출함" 표시를 되돌릴까요?`)) return;
    try { await api(`/reports/${r.id}/k2b-mark`, { method: "DELETE" }); loadStatus(); } catch (err) { showError(errorEl, err); }
  }));
  el.querySelectorAll(".st-unmark").forEach((b) => b.addEventListener("click", async () => {
    const r = find(b.dataset.id);
    if (!confirm(`${r.site_name} ${r.visit_no}회차의 "직접 제출함" 표시를 되돌릴까요?`)) return;
    try { await api(`/reports/${r.id}/submit-mark`, { method: "DELETE" }); loadStatus(); } catch (err) { showError(errorEl, err); }
  }));
}

document.getElementById("st-prev").addEventListener("click", () => {
  stView.month -= 1;
  if (stView.month < 1) { stView.month = 12; stView.year -= 1; }
  loadStatus();
});
document.getElementById("st-next").addEventListener("click", () => {
  stView.month += 1;
  if (stView.month > 12) { stView.month = 1; stView.year += 1; }
  loadStatus();
});
document.getElementById("st-staff").addEventListener("change", (e) => { stView.staff = e.target.value; loadStatus(); });
document.getElementById("st-open").addEventListener("change", (e) => { stView.open = e.target.checked; renderProgress(); renderList(); });

api("/staff").then((list) => {
  const sel = document.getElementById("st-staff");
  for (const s of list) {
    const o = document.createElement("option");
    o.value = s.id;
    o.textContent = s.name;
    sel.appendChild(o);
  }
}).catch(() => {});
loadStatus();
