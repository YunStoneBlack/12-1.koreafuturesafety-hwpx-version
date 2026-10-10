// 시특법 시설물 화면의 "점검 보고서" 칸(sitok-facility.html?id=, 2026-10-10 4단계) — 회차(연도·반기) 만들기·틀 올리기·보고서 만들기.
// 틀 = 직전 회차가 만든 한글(자동) 또는 지난 보고서 한글 파일(처음 하는 시설물 — hwp·hwpx). 만들기는 백그라운드(한글 PDF 몇 분) — 3초마다 진행 확인.
// 서버 server/api/routers/sitok_reports.py, 값 바꾸기 server/sitok/report_build.py.

(function () {
  const fid = Number(new URLSearchParams(location.search).get("id")) || null;
  const panel = document.getElementById("sk-rep-panel");
  if (!fid || !panel) return;
  panel.hidden = false;
  const box = document.getElementById("sk-reps");
  const errorEl = document.getElementById("error");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const err = (e) => showError(errorEl, e);
  let data = null;
  let contracts = [];
  const polling = {};

  function personOptions(selected) {
    return '<option value="">—</option>' + data.persons.map((p) => `<option value="${p.id}"${p.id === selected ? " selected" : ""}>${esc(p.name)}${p.position ? ` ${esc(p.position)}` : ""}</option>`).join("");
  }

  function card(r) {
    const el = document.createElement("div");
    el.className = `sk-rep ${r.status}`;
    const contractOpts = '<option value="">계약 고르기</option>' + contracts.map((c) =>
      `<option value="${c.id}"${c.id === r.contract_id ? " selected" : ""}>${esc(c.sector)} · ${esc(c.title || "계약")} (${esc(c.start_date)}~${esc(c.end_date)})</option>`).join("");
    const parts = r.participant_ids || [];
    const stateText = r.status === "running" ? `<span class="sk-rep-st run">⏳ ${esc(r.message)}</span>`
      : r.status === "failed" ? `<span class="sk-rep-st bad">✗ 실패: ${esc(r.message)}</span>`
        : r.status === "done" ? `<span class="sk-rep-st ok">✓ ${esc(r.made_at)} 만듦 — ${esc(r.message)}</span>` : "";
    el.innerHTML = `<div class="sk-rep-head"><b>${r.year}년 ${esc(r.half)}</b>
        <span class="sk-rep-src">${r.past ? "이미 낸 보고서" : r.has_source ? `틀: ${esc(r.source_note)}` : '<span class="bad">틀 없음 — 지난 보고서 한글 파일을 올리세요</span>'}</span>
        <label class="secondary-link"${r.past ? " hidden" : ""}>지난 보고서 한글 올리기<input type="file" accept=".hwp,.hwpx" hidden data-kr-file="1" /></label>
        ${r.past ? "" : `<a class="secondary-link sk-rep-field" href="sitok-field.html?report=${r.id}">📱 현장 조사</a>`}
        <button type="button" class="secondary btn-sm sk-rep-del">삭제</button></div>
      <div class="sk-rep-grid">
        <label>계약<select data-k="contract_id">${contractOpts}</select></label>
        <label>점검기간 시작 <span class="sk-help">민간 = 현장 간 날</span><input type="date" data-k="period_start" value="${esc(r.period_start)}" /></label>
        <label>점검기간 끝 <span class="sk-help">민간 = 보고서 낸 날</span><input type="date" data-k="period_end" value="${esc(r.period_end)}" /></label>
        <label>제출일 <span class="sk-help">표지·제출문 연월, 비우면 점검기간 끝</span><input type="date" data-k="report_date" value="${esc(r.report_date)}" /></label>
        <label>책임기술자<select data-k="chief_id">${personOptions(r.chief_id)}</select></label>
        <label>참여기술자<select data-k="p0">${personOptions(parts[0])}</select></label>
      </div>
      <div class="sk-rep-foot">${stateText}
        ${r.has_pdf ? `<a class="secondary-link" href="${BASE}/api/sitok/reports/${r.id}/file/pdf" target="_blank" rel="noopener">PDF 보기</a>` : ""}
        ${r.has_hwpx ? `<a class="secondary-link" href="${BASE}/api/sitok/reports/${r.id}/file/hwpx">한글 받기</a>` : ""}
        ${r.past ? "" : `<button type="button" class="sk-rep-build"${r.status === "running" || !r.has_source ? " disabled" : ""}>${r.has_pdf ? "다시 만들기" : "보고서 만들기"}</button>`}</div>`;
    el.querySelectorAll("[data-k]").forEach((inp) => inp.addEventListener("change", async () => {
      const k = inp.dataset.k;
      const body = k === "p0" ? { participant_ids: inp.value ? [Number(inp.value)] : [] }
        : { [k]: k.endsWith("_id") ? (inp.value ? Number(inp.value) : null) : (inp.value || null) };
      try { await apiPatch(`/sitok/reports/${r.id}`, body); inp.classList.add("sk-filled"); setTimeout(() => inp.classList.remove("sk-filled"), 1200); } catch (e) { err(e); }
    }));
    const file = el.querySelector('input[type="file"]');
    file.addEventListener("change", async () => {
      if (!file.files[0]) return;
      el.classList.add("busy");
      el.querySelector(".sk-rep-src").textContent = `${file.files[0].name} 올리는 중…(hwp는 한글로 바꾸느라 20~40초)`;
      try {
        const fd = new FormData();
        fd.append("file", file.files[0]);
        await apiUpload(`/sitok/reports/${r.id}/source`, fd);
        load();
      } catch (e) { err(e); load(); }
    });
    enableFileDrop(el.querySelector(".sk-rep-head"), file);
    el.querySelector(".sk-rep-del").addEventListener("click", async () => {
      if (!confirm(`${r.year}년 ${r.half} 보고서를 지울까요? 만든 한글·PDF도 지워집니다.`)) return;
      try { await api(`/sitok/reports/${r.id}`, { method: "DELETE" }); load(); } catch (e) { err(e); }
    });
    el.querySelector(".sk-rep-build")?.addEventListener("click", async () => {
      try { await apiPost(`/sitok/reports/${r.id}/build`); load(); } catch (e) { err(e); }
    });
    if (r.status === "running") poll(r.id);
    return el;
  }

  function poll(id) {
    if (polling[id]) return;
    polling[id] = setInterval(async () => {
      try {
        const r = await api(`/sitok/reports/${id}`);
        if (r.status !== "running") { clearInterval(polling[id]); delete polling[id]; load(); }
        else { const st = box.querySelector(".sk-rep.running .sk-rep-st"); if (st) st.textContent = `⏳ ${r.message}`; }
      } catch (_) { /* 다음에 다시 */ }
    }, 3000);
  }

  function drawNew() {
    const d = data.defaults;
    const el = document.createElement("div");
    el.className = "sk-rep-new";
    el.innerHTML = `<b>새 회차</b>
      <input type="number" class="nr-year" value="${d.year}" min="2000" max="2100" aria-label="연도" />년
      <select class="nr-half"><option${d.half === "상반기" ? " selected" : ""}>상반기</option><option${d.half === "하반기" ? " selected" : ""}>하반기</option></select>
      <button type="button" class="btn-sm nr-add">+ 회차 만들기</button>
      <label class="secondary-link nr-past" title="이미 낸 지난 반기 보고서 한글(.hwp·.hwpx) — 연도·반기·점검기간은 결과표에서 읽고, 다음 회차가 이걸 틀로 씁니다">이미 낸 보고서 등록<input type="file" accept=".hwp,.hwpx" hidden data-kr-file="1" /></label>
      <span class="sk-help nr-msg">직전 회차 보고서가 있으면 그게 틀이 됩니다. 처음이면 [이미 낸 보고서 등록]으로 지난 반기 한글 파일을 올려 두세요.</span>`;
    const past = el.querySelector(".nr-past input");
    past.addEventListener("change", async () => {
      if (!past.files[0]) return;
      const msg = el.querySelector(".nr-msg");
      el.classList.add("busy");
      msg.textContent = `${past.files[0].name} 올리는 중…(큰 파일은 몇십 초)`;
      try {
        const fd = new FormData();
        fd.append("file", past.files[0]);
        await apiUpload(`/sitok/facilities/${fid}/reports/past`, fd);
        load();
      } catch (e) { err(e); el.classList.remove("busy"); msg.textContent = ""; }
    });
    enableFileDrop(el.querySelector(".nr-past"), past);
    el.querySelector(".nr-add").addEventListener("click", async () => {
      const body = { year: Number(el.querySelector(".nr-year").value), half: el.querySelector(".nr-half").value, contract_id: d.contract_id };
      const chief = data.persons.find((p) => p.sitok_grade.includes("특급")) || data.persons[0];
      if (chief) body.chief_id = chief.id;
      const other = data.persons.find((p) => p.id !== chief?.id);
      if (other) body.participant_ids = [other.id];
      try { await apiPost(`/sitok/facilities/${fid}/reports`, body); load(); } catch (e) { err(e); }
    });
    return el;
  }

  async function load() {
    try {
      const [r, f] = await Promise.all([api(`/sitok/facilities/${fid}/reports`), api(`/sitok/facilities/${fid}`)]);
      data = r;
      contracts = f.contracts || [];
      box.innerHTML = "";
      box.appendChild(drawNew());
      data.reports.forEach((x) => box.appendChild(card(x)));
      if (!data.reports.length) box.insertAdjacentHTML("beforeend", '<div class="empty-note">아직 회차가 없습니다.</div>');
    } catch (e) { err(e); }
  }
  load();
})();
