// 제출 현황(status.html) — 그달(지도일 기준) 보고서 상태·지도 기한 임박/초과·월별 막대·요원별 현황.
// 데이터는 GET /submission/overview 한 번(server/api/routers/submission.py). "제출 완료" 판정은 서버 server/api/submission.py 한 곳.
// 할 일 버튼: 📧 전송(mail.js 전송 창 그대로) · 직접 제출함/되돌리기 · 이어서 작성 · + 새 보고서(기한 임박·초과 현장).

const errorEl = document.getElementById("error");
const today = new Date();
const stView = { year: today.getFullYear(), month: today.getMonth() + 1, staff: "", filter: "all", open: false };
let stData = null;

const STATE = {
  writing: ["작성 중", "draft"],
  outdated: ["수정 전 버전", "rejected"],
  pdf_ready: ["PDF 완료·미전송", "pending"],
  submitted: ["제출 완료", "approved"],
};
const WD = "일월화수목금토";

function h(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function md(iso) {
  const d = new Date(`${iso}T00:00:00`);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}
function mdw(iso) {
  const d = new Date(`${iso}T00:00:00`);
  return `${d.getMonth() + 1}/${d.getDate()}(${WD[d.getDay()]})`;
}
function dueText(d) {
  if (d.days_left < 0) return `기한 ${mdw(d.deadline)} · ${-d.days_left}일 지남`;
  if (d.days_left === 0) return `기한 오늘 ${mdw(d.deadline)}`;
  return `기한 ${mdw(d.deadline)} · D-${d.days_left}`;
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
  renderCards();
  renderChart();
  renderStaff();
  renderList();
}

function renderCards() {
  const c = stData.cards;
  const cards = [
    ["all", `${stData.month}월 보고서`, c.total, "지도일 기준", ""],
    ["submitted", "제출 완료", c.submitted, `전송 ${c.submitted_mail} · 직접 제출 ${c.submitted_manual}`, "ok"],
    ["pdf_ready", "PDF 완료·미전송", c.pdf_ready, "보내면 끝", "wait"],
    ["pending", "작성 중·수정 전", c.writing + c.outdated, `작성 중 ${c.writing} · 수정 전 버전 ${c.outdated}`, "idle"],
    ["deadline-imminent", "⏰ 기한 임박", c.imminent, `기한 D-${stData.imminent_days} 이내 · 지금 기준`, "warn"],
    ["deadline-over", "⚠ 기한 초과", c.over, "마지막 지도일 + 15일 지남", "crit"],
  ];
  const el = document.getElementById("st-cards");
  el.innerHTML = cards.map(([key, label, n, sub, tone]) => `
    <button type="button" class="st-card ${tone}${stView.filter === key ? " active" : ""}${(key.startsWith("deadline") && n > 0) ? " alert" : ""}" data-filter="${key}">
      <span class="l">${tone && !key.startsWith("deadline") ? `<i class="st-dot ${tone}"></i>` : ""}${label}</span>
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
    const warn = [s.imminent ? `⏰ 임박 ${s.imminent}` : "", s.over ? `⚠ 초과 ${s.over}` : ""].filter(Boolean).join(" · ");
    return `<div class="st-staff-row"><span class="nm">${h(s.name)}</span>
      <span class="st-staff-bar">${s.total ? `<span class="ok" style="width:${pct}%"></span><span class="wait" style="width:${100 - pct}%"></span>` : ""}</span>
      <span class="num">제출 ${s.submitted} / ${s.total}건</span>
      ${warn ? `<span class="st-staff-warn">${warn}</span>` : ""}</div>`;
  }).join("");
  box.innerHTML = `<b>요원별 ${stData.month}월</b>${rows || '<div class="st-empty">이달 보고서가 없습니다.</div>'}`;
}

function reportActions(r) {
  const open = `<a class="secondary-link" href="report.html?id=${r.id}">${r.state === "writing" ? "이어서 작성" : "보고서 열기"}</a>`;
  if (r.state === "pdf_ready") {
    return `<button type="button" class="st-send" data-id="${r.id}">📧 전송</button>` +
      `<button type="button" class="secondary st-mark" data-id="${r.id}">직접 제출함</button>`;
  }
  if (r.state === "submitted" && r.modified_after) {
    return `<button type="button" class="st-send" data-id="${r.id}">📧 다시 전송</button>${open}`;
  }
  return open;
}

function submittedCell(r) {
  if (r.state !== "submitted") return '<span class="st-none">—</span>';
  const when = md(r.submitted_at.slice(0, 10));
  const main = r.submitted_via === "mail"
    ? `📧 ${when} 전송<span>${r.to_count}곳${r.submitted_by ? ` · ${h(r.submitted_by)}` : ""}</span>`
    : `✋ ${when} 직접 제출<span>${r.submitted_by ? `${h(r.submitted_by)} 표시` : ""}</span>`;
  const undo = r.has_mark ? `<button type="button" class="st-unmark" data-id="${r.id}">되돌리기</button>` : "";
  const mod = r.modified_after ? '<em class="st-mod">⚠ 제출 뒤 수정됨</em>' : "";
  return `<div class="st-sent">${main}</div>${mod}${undo}`;
}

function filteredReports() {
  let rows = stData.reports;
  if (stView.open) rows = rows.filter((r) => r.state !== "submitted" || r.modified_after);
  const f = stView.filter;
  if (f === "submitted") rows = rows.filter((r) => r.state === "submitted");
  else if (f === "pdf_ready") rows = rows.filter((r) => r.state === "pdf_ready");
  else if (f === "pending") rows = rows.filter((r) => r.state === "writing" || r.state === "outdated");
  else if (f.startsWith("deadline")) rows = [];
  return rows;
}

function filteredDeadlines() {
  const f = stView.filter;
  if (f === "deadline-imminent") return stData.deadlines.filter((d) => d.stage === "imminent");
  if (f === "deadline-over") return stData.deadlines.filter((d) => d.stage === "over");
  if (f === "all") return stData.deadlines;
  return [];
}

function renderList() {
  const el = document.getElementById("st-list");
  const dls = filteredDeadlines();
  const rows = filteredReports();
  let html = "";
  if (dls.length) {
    html += `<div class="st-group">⏰ 지도 기한 임박·초과 — 마지막 지도일 + 15일 기준(오늘 기준, D-${stData.imminent_days}부터 임박)</div>`;
    html += dls.map((d) => `
      <div class="st-dl ${d.stage}">
        <div class="st-dl-main"><a class="st-site" href="site.html?id=${d.site_id}">${h(d.site_name)}</a>
          <div class="st-dl-due">${d.stage === "over" ? "⚠" : "⏰"} ${dueText(d)}</div>
          <div class="st-sub">${d.last_date ? `마지막 지도 ${md(d.last_date)} · ${d.last_visit_no}회차` : "아직 지도 기록 없음(공사 시작일 기준)"} · 담당 ${h(d.staff_name || "미지정")}</div></div>
        <div class="st-act"><button type="button" class="secondary st-new" data-site="${d.site_id}">+ 새 보고서</button></div>
      </div>`).join("");
  }
  if (!stView.filter.startsWith("deadline")) {
    html += `<div class="st-head"><span>${stData.month}월 보고서 (지도일 기준)</span><span>회차</span><span>지도일</span><span>담당</span><span>상태</span><span>제출</span><span></span></div>`;
    html += rows.length ? rows.map((r) => {
      const [label, pill] = STATE[r.state];
      return `<div class="st-rep ${r.state}">
        <div class="c-site"><a class="st-site" href="site.html?id=${r.site_id}">${h(r.site_name)}</a><div class="st-sub">${h(r.hq_company)}</div>
          <div class="c-meta">${r.visit_no}회차 · ${md(r.date)}${r.has_guidance_date ? "" : "(만든 날)"} · ${h(r.staff_name || "담당 미지정")}</div></div>
        <div class="c-no">${r.visit_no}</div>
        <div class="c-date">${md(r.date)}${r.has_guidance_date ? "" : '<span class="st-sub"> (만든 날)</span>'}</div>
        <div class="c-staff">${h(r.staff_name || "미지정")}</div>
        <div class="c-state"><span class="status-pill ${pill}">${label}</span></div>
        <div class="c-sent">${submittedCell(r)}</div>
        <div class="st-act">${reportActions(r)}</div>
      </div>`;
    }).join("") : '<div class="empty-note">해당하는 보고서가 없습니다.</div>';
  } else if (!dls.length) {
    html += '<div class="empty-note">지금 기한이 임박하거나 지난 현장이 없습니다.</div>';
  }
  el.innerHTML = html;
  bindListActions(el);
}

function bindListActions(el) {
  const find = (id) => stData.reports.find((r) => r.id === Number(id));
  el.querySelectorAll(".st-send").forEach((b) => b.addEventListener("click", () => {
    const r = find(b.dataset.id);
    openMailModal(r.id, `${r.site_name} ${r.visit_no}회차`, loadStatus);
  }));
  el.querySelectorAll(".st-mark").forEach((b) => b.addEventListener("click", async () => {
    const r = find(b.dataset.id);
    if (!confirm(`${r.site_name} ${r.visit_no}회차를 "직접 제출함"으로 표시할까요?\n(메일 말고 직접 보냈거나 출력해서 낸 경우 — 누가 언제 표시했는지 남습니다)`)) return;
    try { await apiPost(`/reports/${r.id}/submit-mark`); loadStatus(); } catch (err) { showError(errorEl, err); }
  }));
  el.querySelectorAll(".st-unmark").forEach((b) => b.addEventListener("click", async () => {
    const r = find(b.dataset.id);
    if (!confirm(`${r.site_name} ${r.visit_no}회차의 "직접 제출함" 표시를 되돌릴까요?`)) return;
    try { await api(`/reports/${r.id}/submit-mark`, { method: "DELETE" }); loadStatus(); } catch (err) { showError(errorEl, err); }
  }));
  el.querySelectorAll(".st-new").forEach((b) => b.addEventListener("click", async () => {
    b.disabled = true;
    try {
      const report = await apiPost(`/sites/${b.dataset.site}/reports`, {});
      window.location.href = `report.html?id=${report.id}`;
    } catch (err) {
      b.disabled = false;
      showError(errorEl, err);
    }
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
document.getElementById("st-open").addEventListener("change", (e) => { stView.open = e.target.checked; renderList(); });

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
