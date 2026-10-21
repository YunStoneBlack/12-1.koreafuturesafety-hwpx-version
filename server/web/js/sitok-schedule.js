// 구조 일람표 부재 목록(sitok-schedule.html, 2026-10-21 — 내진성능평가 철근탐사 1단계).
// [🤖 일람표 읽기] → 서버가 쪽마다 AI로 읽음(뒤에서, 4초마다 상태) → 기둥·보·벽체 카드(단면 그림 + 값 칸). 칸을 고치면 바로 저장,
// 기둥 단변·장변 점 개수·두 줄 하부근은 그림을 보고 [✓ 확인]. 서버 server/api/routers/sitok_rebar.py.

(function () {
  const fid = Number(new URLSearchParams(location.search).get("facility")) || null;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const $ = (id) => document.getElementById(id);
  const errorEl = $("error");
  const URL_ = `/sitok/facilities/${fid}/rebar-schedule`;
  let d = null;
  let filter = "need";
  let timer = null;

  const POS = ["단부", "중앙부", "전체", "단부(내부)", "단부(외부)"];
  const F = { // [필드, 이름, 종류(text|num|pos|layers), 넓게]
    기둥: [["marks", "부호"], ["floors", "층"], ["size", "크기(b×h)"], ["main", "주근"], ["short_side", "단변 점 개수", "num"], ["long_side", "장변 점 개수", "num"],
      ["hoop", "대근(중앙부)"], ["hoop_end", "단부 대근"], ["hoop_aux", "보조대근"]],
    보: [["marks", "부호"], ["floors", "층"], ["position", "위치", "pos"], ["size", "크기(b×h)"], ["top", "상부근"], ["bottom", "하부근"],
      ["bottom_layers", "하부근 줄 수", "layers"], ["bottom_row", "아래 줄 점 개수", "num"], ["stirrup", "늑근"]],
    벽체: [["marks", "부호"], ["floors", "층"], ["thickness", "두께(mm)", "num"], ["vertical", "수직근"], ["horizontal", "수평근"]],
  };

  const showErr = (m) => { errorEl.textContent = m || ""; errorEl.style.display = m ? "block" : "none"; };
  const val = (it, k) => (k === "marks" ? (it.marks || []).join(", ") : it[k] ?? "");

  function input(it, [k, label, type]) {
    const uns = (it.unsure || []).includes(k) ? " rs-unsure" : "";
    const v = val(it, k);
    let ctl;
    if (type === "pos") {
      const opts = POS.includes(v) || !v ? POS : [...POS, v];
      ctl = `<select data-f="${k}">${["", ...opts].map((o) => `<option${o === v ? " selected" : ""}>${esc(o)}</option>`).join("")}</select>`;
    } else if (type === "layers") {
      ctl = `<select data-f="${k}">${[["1", "한 줄"], ["2", "두 줄(복)"]].map(([o, t]) => `<option value="${o}"${String(v || 1) === o ? " selected" : ""}>${t}</option>`).join("")}</select>`;
    } else {
      ctl = `<input data-f="${k}" value="${esc(v)}"${type === "num" ? ' type="number" inputmode="numeric" min="0" max="999"' : ""} />`;
    }
    const hide = it.kind === "보" && k === "bottom_row" && Number(it.bottom_layers || 1) === 1 ? " hidden" : ""; // 한 줄이면 글자 총수 그대로
    return `<div class="sk-f${uns}"${hide}><label>${esc(label)}${uns ? ' <span class="rs-q" title="AI가 확실하지 않다고 한 칸">?</span>' : ""}</label>${ctl}</div>`;
  }

  function card(it) {
    const ok = it.check || {};
    const need = !it.confirmed || ok.ok === false;
    const title = `${(it.marks || []).join(", ") || "부호 없음"} · ${it.floors || "층?"}${it.position ? ` · ${it.position}` : ""}`;
    const img = it.box ? `<a href="${BASE}/api${URL_}/crop/${it.id}?v=${encodeURIComponent(d.read_at || "")}" target="_blank" rel="noopener" title="크게 보기">
        <img loading="lazy" src="${BASE}/api${URL_}/crop/${it.id}?v=${encodeURIComponent(d.read_at || "")}" alt="${esc(title)} 단면" /></a>`
      : '<div class="rs-noimg">그림 위치 없음</div>';
    return `<div class="rs-card${need ? " need" : ""}" data-id="${it.id}">
      <div class="rs-card-h"><b>${esc(title)}</b>
        <span class="rs-badge ${it.confirmed ? "ok" : "todo"}">${it.confirmed ? `✓ 확인${it.by ? ` · ${esc(it.by)}` : ""}` : "확인 필요"}</span>
        ${ok.why ? `<span class="rs-why${ok.ok === false ? " bad" : ""}">${esc(ok.why)}</span>` : ""}
        ${it.same_as ? `<span class="sk-help">${esc(it.same_as)}과 같음</span>` : ""}</div>
      <div class="rs-card-b"><div class="rs-img">${img}</div>
        <div class="field-grid rs-fields">${F[it.kind].map((f) => input(it, f)).join("")}</div></div>
      <div class="rs-card-f"><span class="rs-preview">→ ${esc(it.preview || "")}</span>
        <button type="button" class="link-btn rs-del" title="이 칸 지우기">🗑</button>
        <button type="button" class="${it.confirmed ? "secondary btn-sm" : "btn-sm"} rs-ok">${it.confirmed ? "확인 취소" : "✓ 확인"}</button></div></div>`;
  }

  function draw() {
    $("rs-fac-link").textContent = d.facility.name || "시설물";
    $("rs-fac-link").href = `sitok-facility.html?id=${fid}`;
    document.title = `구조 일람표 부재 목록 - ${d.facility.name}`;
    const items = d.items || [];
    const by = { 기둥: [], 보: [], 벽체: [] };
    items.forEach((it) => by[it.kind] && by[it.kind].push(it));
    $("rs-count").textContent = items.length ? `기둥 ${by.기둥.length} · 보 ${by.보.length} · 벽체 ${by.벽체.length} — 확인 필요 ${d.need}칸` : "";
    $("rs-files").innerHTML = d.files.length ? `일람표 도면: ${d.files.map((f) => `<span class="rs-file">${esc(f.name)}</span>`).join(" ")}
        <a class="secondary-link" href="sitok-facility.html?id=${fid}">도면 바꾸기</a>`
      : `<div class="mail-msg bad">구조 일람표 도면이 없습니다 — <a href="sitok-facility.html?id=${fid}">시설물 정보·서류</a>의 도면 칸 "📏 구조 일람표"에 올리세요.</div>`;
    const running = d.status === "running";
    $("rs-read").disabled = running || !d.files.length;
    $("rs-read").textContent = running ? "읽는 중…" : items.length ? "🤖 다시 읽기" : "🤖 일람표 읽기";
    $("rs-status").innerHTML = running ? `⏳ ${esc(d.message)}`
      : d.job && d.job.state === "failed" ? `<span class="rs-why bad">✗ ${esc(d.job.msg)}</span>`
      : d.read_at ? `${esc(d.read_at)} 읽음 — ${esc(d.message)}${items.length ? " · 다시 읽어도 사람이 확인한 칸은 그대로" : ""}`
      : "쪽마다 AI가 읽습니다(쪽당 30초~4분, 약 120원). 읽는 동안 다른 화면으로 가도 됩니다.";
    const chips = [["need", `확인 필요 ${d.need}`], ["all", `전체 ${items.length}`], ["기둥", "기둥"], ["보", "보"], ["벽체", "벽체"]];
    $("rs-filter").innerHTML = items.length ? chips.map(([k, t]) => `<button type="button" class="ds-chip${filter === k ? " on" : ""}" data-k="${k}">${esc(t)}</button>`).join("") : "";
    $("rs-filter").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { filter = b.dataset.k; draw(); }));
    const pass = (it) => filter === "all" || (filter === "need" ? (!it.confirmed || (it.check || {}).ok === false) : it.kind === filter);
    $("rs-lists").innerHTML = Object.entries(by).filter(([, list]) => list.some(pass)).map(([k, list]) => `<section class="panel">
        <div class="panel-head"><h2>${k}</h2><span class="panel-count">${list.filter(pass).length}칸</span></div>
        <div class="panel-body rs-cards">${list.filter(pass).map(card).join("")}</div></section>`).join("")
      || (items.length ? '<section class="panel"><div class="panel-body empty-note">확인할 칸이 없습니다 — 모두 확인했습니다 ✓</div></section>' : "");
    bind();
    clearTimeout(timer);
    if (running) timer = setTimeout(load, 4000);
  }

  function itemOf(id) { return (d.items || []).find((x) => x.id === id); }

  async function save(id, body) {
    try { d = await apiPatch(`${URL_}/items/${id}`, body); showErr(""); } catch (e) { showErr(e.message); return; }
    const el = document.querySelector(`.rs-card[data-id="${id}"]`);
    const it = itemOf(id);
    if (!el || !it) { draw(); return; }
    const focus = document.activeElement && el.contains(document.activeElement) ? document.activeElement.dataset.f : null;
    el.outerHTML = card(it);
    $("rs-count").textContent = `확인 필요 ${d.need}칸`;
    bind();
    if (focus) { const f = document.querySelector(`.rs-card[data-id="${id}"] [data-f="${focus}"]`); if (f) f.focus(); }
  }

  function bind() {
    document.querySelectorAll(".rs-card").forEach((el) => {
      if (el.dataset.bound) return;
      el.dataset.bound = "1";
      const id = el.dataset.id;
      el.querySelectorAll("[data-f]").forEach((inp) => inp.addEventListener("change", () => {
        const k = inp.dataset.f;
        let v = inp.value.trim();
        if (k === "marks") v = v.split(/[,，/]/).map((s) => s.trim()).filter(Boolean);
        else if (inp.type === "number" || k === "bottom_layers") v = v === "" ? null : Math.max(0, Math.floor(Number(v)));
        save(id, { [k]: v });
      }));
      el.querySelector(".rs-ok").addEventListener("click", () => save(id, { confirmed: !itemOf(id).confirmed }));
      el.querySelector(".rs-del").addEventListener("click", async () => {
        if (!confirm("이 칸을 지울까요? 다시 읽으면 도면에 있는 칸은 다시 생깁니다.")) return;
        try { d = await api(`${URL_}/items/${id}`, { method: "DELETE" }); draw(); } catch (e) { showErr(e.message); }
      });
    });
  }

  // ---------- 칸 직접 추가 ----------
  function drawAdd(kind) {
    kind = kind || "기둥";
    $("rs-add").innerHTML = `<div class="sk-f"><label>종류</label><select id="rs-add-kind">${Object.keys(F).map((k) => `<option${k === kind ? " selected" : ""}>${k}</option>`).join("")}</select></div>`
      + F[kind].map((f) => input({ kind, marks: [], unsure: [], bottom_layers: 1 }, f)).join("");
    $("rs-add").querySelector('[data-f="bottom_row"]')?.closest(".sk-f")?.removeAttribute("hidden");
    $("rs-add-kind").addEventListener("change", (e) => drawAdd(e.target.value));
  }

  $("rs-add-btn").addEventListener("click", async () => {
    const kind = $("rs-add-kind").value;
    const body = { kind };
    $("rs-add").querySelectorAll("[data-f]").forEach((inp) => {
      const k = inp.dataset.f;
      const v = inp.value.trim();
      if (v === "") return;
      body[k] = k === "marks" ? v.split(/[,，/]/).map((s) => s.trim()).filter(Boolean) : (inp.type === "number" || k === "bottom_layers") ? Math.floor(Number(v)) : v;
    });
    const m = $("rs-add-msg");
    try {
      d = await apiPost(`${URL_}/items`, body);
      m.hidden = false; m.className = "mail-msg"; m.textContent = "추가했습니다.";
      drawAdd(kind);
      draw();
    } catch (e) { m.hidden = false; m.className = "mail-msg bad"; m.textContent = e.message; }
  });

  $("rs-read").addEventListener("click", async () => {
    if ((d.items || []).length && !confirm("다시 읽을까요? 사람이 확인·고친 칸은 그대로 두고 나머지를 새로 읽습니다(쪽당 약 120원).")) return;
    $("rs-read").disabled = true;
    try { d = await apiPost(`${URL_}/read`, {}); showErr(""); } catch (e) { showErr(e.message); }
    draw();
  });

  async function load() {
    try { d = await api(URL_); showErr(""); } catch (e) { showErr(e.message); return; }
    if (filter === "need" && !d.need && (d.items || []).length) filter = "all";
    draw();
  }

  if (!fid) { showErr("시설물이 지정되지 않았습니다 — 시설물 정보·서류 화면의 도면 칸에서 들어오세요."); return; }
  drawAdd();
  load();
})();
