// 제출 현황(status.html) — 그달(지도일 기준) 보고서 상태·월별 막대·요원별 현황.
// 데이터는 GET /submission/overview 한 번(server/api/routers/submission.py). "제출 완료" 판정은 서버 server/api/submission.py 한 곳.
// 할 일 버튼: 📧 전송(mail.js 전송 창 그대로) · 직접 제출함/되돌리기 · 📤 K2B 제출(js/k2b-submit.js 창 그대로) · K2B 직접 제출함 · 이어서 작성.
// 제출 완료 = 전송(또는 직접 제출함) + K2B(2026-10-10). 전송만 하고 K2B가 안 됐으면 "K2B 미제출".
// (2026-10-01 "마지막 지도일 + 15일" 기한 임박·초과 칸과 목록은 없앰 — 실제 규칙이 아니었음.)

const errorEl = document.getElementById("error");
const today = new Date();
const stView = { year: today.getFullYear(), month: today.getMonth() + 1, staff: "", filter: "all", open: false };
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
  renderCards();
  renderChart();
  renderStaff();
  renderList();
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

function submittedCell(r) {
  if (!r.submitted_at) return '<span class="st-none">—</span>';
  const when = md(r.submitted_at.slice(0, 10));
  const main = r.submitted_via === "mail"
    ? `📧 ${when} 전송<span>${r.to_count}곳${r.submitted_by ? ` · ${h(r.submitted_by)}` : ""}</span>`
    : `✋ ${when} 직접 제출<span>${r.submitted_by ? `${h(r.submitted_by)} 표시` : ""}</span>`;
  const undo = r.has_mark ? `<button type="button" class="st-unmark" data-id="${r.id}">되돌리기</button>` : "";
  const mod = r.modified_after ? '<em class="st-mod">⚠ 제출 뒤 수정됨</em>' : "";
  return `<div class="st-sent">${main}</div>${mod}${undo}`;
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
