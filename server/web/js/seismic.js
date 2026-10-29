// 내진성능평가(seismic.html, 2026-10-21 사용자 — 시특법과 완전히 별개 용역) — 목록 + [＋ 새 내진성능평가].
// 만들기 = 용역계약서·건축물대장 PDF(둘 다 또는 하나) + 이름(선택) → POST /seismic/projects → 건 화면(seismic-project.html?id=).
// 목록 카드: 건물·용역명·발주처·기간·서류 N/11·진행(결함·철근탐사·보고서) + [📂 열기] [PDF 보기].
// 10/30 사용자 — [최신순](최근 만든 건 위, 처음 모양) [번호순 ▼▲](건 번호 26-1…, 시특법 목록과 같게 한 번 더 = 방향), 이 기기에 기억.

(function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const errorEl = document.getElementById("error");
  const $ = (id) => document.getElementById(id);
  const say = (text, ok) => { const m = $("sv-msg"); m.hidden = !text; m.className = `mail-msg${ok ? "" : " bad"}`; m.textContent = text || ""; };
  const dot = (iso) => (iso ? iso.slice(0, 10).replace(/-/g, ".") : "");

  for (const [input, drop, msg] of [["sv-c", "sv-c-drop", "sv-c-msg"], ["sv-r", "sv-r-drop", "sv-r-msg"]]) {
    if (typeof enableFileDrop === "function") enableFileDrop($(drop), $(input));
    $(input).addEventListener("change", () => {
      const f = $(input).files[0];
      if (f) { $(msg).textContent = `✓ ${f.name}`; $(drop).classList.add("on"); }
    });
  }

  $("sv-create").addEventListener("click", async () => {
    const c = $("sv-c").files[0], r = $("sv-r").files[0], name = $("sv-name").value.trim();
    if (!c && !r && !name) { say("용역계약서나 건축물대장 PDF를 올리거나 건물 이름을 넣으세요."); return; }
    const fd = new FormData();
    if (c) fd.append("contract", c);
    if (r) fd.append("ledger", r);
    fd.append("name", name);
    $("sv-create").disabled = true;
    say("읽는 중…", true);
    try {
      const p = await apiUpload("/seismic/projects", fd);
      location.href = `seismic-project.html?id=${p.id}`;
    } catch (e) { say(e.message); $("sv-create").disabled = false; }
  });

  function card(p) {
    const s = p.seismic || {};
    const f = p.field || {};
    const bits = [`서류 ${p.docs}/${p.docs_total}`, f.defects ? `결함 ${f.checked}/${f.defects} 확인` : "결함 아직", s.rebar ? `철근탐사 ${s.rebar}개소` : "철근탐사 아직"];
    const state = p.status === "running" ? '<span class="sk-rep-st run">⏳ 만드는 중</span>'
      : p.status === "failed" ? '<span class="sk-rep-st bad">✗ 만들기 실패</span>'
        : p.has_pdf ? `<span class="ds-done">보고서 ${esc((p.made_at || "").slice(5, 10).replace("-", "/"))} 만듦</span>` : "";
    const el = document.createElement("div");
    el.className = "ds-card";
    el.innerHTML = `<div class="ds-card-main">
        <div class="ds-card-title">${p.no ? `<span class="site-no" title="서류 자동화 › 내진성능평가 카드와 같은 번호">${esc(p.no)}</span>` : ""}<b>${esc(p.name)}</b>${p.start_date ? `<span class="ds-kind">${esc(p.start_date.slice(0, 4))}년</span>` : ""}${state}</div>
        <div class="ds-card-sub">${esc(p.title || "용역명 없음")}${p.client ? ` · ${esc(p.client)}` : ""}${p.start_date ? ` · ${dot(p.start_date)} ~ ${dot(p.end_date)}` : ""}</div>
        <div class="ds-card-meta">${bits.map(esc).join(" · ")}</div>
      </div>
      <div class="ds-card-btns">
        <a class="secondary-link" href="seismic-project.html?id=${p.id}">📂 열기</a>
        ${p.has_pdf ? `<a class="secondary-link" href="${BASE}/api/sitok/reports/${p.id}/file/pdf?v=${encodeURIComponent(p.made_at || "")}" target="_blank" rel="noopener">PDF 보기</a>` : ""}
      </div>`;
    return el;
  }

  // ---------- 정렬(10/30) ----------
  const SORT_KEY = "kfsc-report:seismic-sort";
  let sort = { mode: "new", desc: true };
  try { sort = { ...sort, ...JSON.parse(localStorage.getItem(SORT_KEY) || "{}") }; } catch { /* 기억 못 하면 기본 */ }
  const noKey = (p) => { // "26-3" → 26·3(해마다 1부터), 번호 없는 건은 맨 뒤
    const m = String(p.no || "").match(/^(\d{2}|\d{4})-0*(\d+)$/);
    return m ? Number(m[1].slice(-2)) * 1e5 + Number(m[2]) : null;
  };
  const byNumber = (a, b) => {
    const x = noKey(a), y = noKey(b);
    if (x === null || y === null) return x === null ? (y === null ? b.id - a.id : 1) : -1;
    return (sort.desc ? y - x : x - y) || b.id - a.id;
  };
  const sortRows = (list) => (sort.mode === "no" ? list.sort(byNumber) : list.sort((a, b) => b.id - a.id));
  function drawSort() {
    document.querySelectorAll(".sv-sort button").forEach((b) => {
      const on = b.dataset.sort === sort.mode;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on);
      if (b.dataset.sort === "no") b.textContent = `번호순 ${on ? (sort.desc ? "▼" : "▲") : ""}`.trim();
    });
  }
  document.querySelectorAll(".sv-sort button").forEach((b) => b.addEventListener("click", () => {
    if (b.dataset.sort === "no" && sort.mode === "no") sort.desc = !sort.desc; // 번호순 한 번 더 → 방향 바꿈
    else if (b.dataset.sort === "no") sort.desc = true;
    sort.mode = b.dataset.sort;
    try { localStorage.setItem(SORT_KEY, JSON.stringify(sort)); } catch { /* 지금은 바뀜 */ }
    render();
  }));

  let projects = [];
  function render() {
    drawSort();
    const box = $("sv-list");
    box.innerHTML = projects.length ? "" : '<div class="ds-empty">아직 내진성능평가가 없습니다 — 위에 용역계약서·건축물대장 PDF를 올리고 [읽어서 만들기]를 누르세요.</div>';
    sortRows([...projects]).forEach((p) => box.appendChild(card(p)));
  }

  async function load() {
    try {
      const d = await api("/seismic/projects");
      projects = d.projects;
      $("sv-count").textContent = projects.length ? `${projects.length}건` : "";
      render();
    } catch (e) { showError(errorEl, e); }
  }

  load();
})();
