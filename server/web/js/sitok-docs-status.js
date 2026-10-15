// 서류 자동화 · 시특법 — 제출 현황(sitok-docs-status.html, 2026-10-15 민재형 문서번호 일치화 문서 "서류 제출현황 관리").
// 상·하반기로(◀ ▶), 한 줄 = 그 반기에 걸친 계약(시설물 카드 번호·이름과 같이). 민간·관급·뱃지 거르기(엑셀 필터처럼).
// 칸: 관급 착수계·완수계 — [만들기]로 PDF까지 = 제출(첨부 넣고 만들기), 프로그램 쓰기 전 낸 것은 "직접 제출함" / 민간 계약서 — 날인본 받음·만듦 / 계산서 발행일(달력).
// 칸을 누르면: 관급 서류 = 착수계·완료계 창(js/sitok-docs-gov.js) 또는 직접 제출함 표시, 계산서 = 날짜 넣기.
// API: GET /sitok/status/docs?year&half, POST /sitok/status/docs/{id}/mark — server/api/routers/sitok_status.py

(function () {
  const errorEl = document.getElementById("error");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const HALF_KEY = "kfsc-report:sitok-docs-status-half";
  const now = new Date();
  let cur = { year: now.getFullYear(), half: now.getMonth() < 6 ? "상반기" : "하반기" };
  try { cur = { ...cur, ...JSON.parse(sessionStorage.getItem(HALF_KEY) || "{}") }; } catch { /* 지금 반기 */ }
  let rows = [];
  const view = { sector: "", field: "", kind: "", card: "", q: "" };
  const md = (iso) => (iso ? `${iso.slice(5, 7)}/${iso.slice(8, 10)}` : "");
  const startOk = (r) => !!(r.start.made && (r.contract.sector === "민간" || r.start.pdf)) || !!r.start.mark || r.start.signed;
  const doneOk = (r) => !r.done || !!(r.done.made || r.done.mark);
  const CARDS = [["", "전체", "이 반기 계약", () => true],
    ["start", "착수계 미제출", "관급 — 착수계 안 만듦", (r) => r.contract.sector === "관급" && !startOk(r)],
    ["done", "완수계 미제출", "관급 — 완료계 안 만듦", (r) => r.contract.sector === "관급" && !doneOk(r)],
    ["civil", "계약서 미완료", "민간 — 날인본 안 받음", (r) => r.contract.sector === "민간" && !r.start.signed && !r.start.mark],
    ["invoice", "계산서 미발행", "발행일 없음", (r) => !r.invoice.date]];

  async function load() {
    document.getElementById("ds-label").textContent = `${cur.year}년 ${cur.half}`;
    try {
      rows = (await api(`/sitok/status/docs?year=${cur.year}&half=${encodeURIComponent(cur.half)}`)).rows;
      render();
    } catch (err) {
      showError(errorEl, err);
    }
  }
  const shift = (d) => {
    const i = cur.year * 2 + (cur.half === "하반기" ? 1 : 0) + d;
    cur = { year: Math.floor(i / 2), half: i % 2 ? "하반기" : "상반기" };
    try { sessionStorage.setItem(HALF_KEY, JSON.stringify(cur)); } catch { /* 지금만 */ }
    load();
  };
  document.getElementById("ds-prev").addEventListener("click", () => shift(-1));
  document.getElementById("ds-next").addEventListener("click", () => shift(1));
  document.querySelectorAll(".ss-sector button").forEach((b) => b.addEventListener("click", () => { view.sector = b.dataset.sector; if (view.sector === "민간") view.kind = ""; render(); }));
  document.getElementById("ds-search").addEventListener("input", (e) => { view.q = e.target.value.trim().toLowerCase(); render(); });

  const fac = (r) => r.facility || { badge_field: "", badge_kind: "" };
  const base = () => rows.filter((r) => (!view.sector || r.contract.sector === view.sector) && (!view.field || fac(r).badge_field === view.field) &&
    (!view.kind || fac(r).badge_kind === view.kind) &&
    (!view.q || `${r.facility ? `${r.facility.mgmt_no} ${r.facility.name}` : ""} ${r.contract.title} ${r.contract.client}`.toLowerCase().includes(view.q)));

  function render() {
    document.querySelectorAll(".ss-sector button").forEach((b) => b.classList.toggle("on", b.dataset.sector === view.sector));
    const inSector = rows.filter((r) => !view.sector || r.contract.sector === view.sector);
    const chip = (dim, v) => {
      const n = inSector.filter((r) => (dim === "field" ? fac(r).badge_field : fac(r).badge_kind) === v).length;
      return `<button type="button" class="sk-badge-f b-${dim}${view[dim] === v ? " on" : ""}" data-dim="${dim}" data-v="${esc(v)}">${esc(v)} <b>${n}</b></button>`;
    };
    const bEl = document.getElementById("ds-badges");
    bEl.innerHTML = `<span class="sk-badge-l">분야</span>${["건축", "토목", "건축·토목"].map((v) => chip("field", v)).join("")}` +
      (view.sector === "민간" ? "" : `<span class="sk-badge-l">관급</span>${["학교", "일반"].map((v) => chip("kind", v)).join("")}`);
    bEl.querySelectorAll(".sk-badge-f").forEach((b) => b.addEventListener("click", () => { view[b.dataset.dim] = view[b.dataset.dim] === b.dataset.v ? "" : b.dataset.v; render(); }));
    const list0 = base();
    const cardsEl = document.getElementById("ds-cards");
    cardsEl.innerHTML = CARDS.map(([k, label, sub, ok]) => `<button type="button" class="st-card${view.card === k ? " active" : ""}${k && list0.filter(ok).length ? " warn" : ""}" data-k="${k}">
      <span class="l">${label}</span><span class="n">${list0.filter(ok).length}건</span><span class="s">${sub}</span></button>`).join("");
    cardsEl.querySelectorAll(".st-card").forEach((b) => b.addEventListener("click", () => { view.card = b.dataset.k; render(); }));
    const ok = CARDS.find((c) => c[0] === view.card)[3];
    const shown = list0.filter(ok);
    document.getElementById("ds-title").textContent = `${cur.year}년 ${cur.half} 서류 제출 현황${view.card ? ` — ${CARDS.find((c) => c[0] === view.card)[1]}` : ""}`;
    document.getElementById("ds-count").textContent = `${shown.length}건`;
    const list = document.getElementById("ds-list");
    if (!rows.length) { list.innerHTML = '<div class="empty-note">이 반기에 걸친 계약이 없습니다.</div>'; return; }
    if (!shown.length) { list.innerHTML = '<div class="empty-note">맞는 계약이 없습니다.</div>'; return; }
    list.innerHTML = '<div class="ss-grid ss-docs ss-head"><span>계약</span><span>착수계 / 계약서</span><span>완수계</span><span>계산서 발행</span></div>';
    for (const r of shown) list.appendChild(rowEl(r));
  }

  const badge = (tone, text) => `<span class="ss-b ${tone}">${esc(text)}</span>`;
  function startBadge(r) {
    const s = r.start;
    if (r.contract.sector === "민간") return s.signed ? badge("ok", "✓ 날인본 받음") : s.mark ? badge("ok", `✓ 직접 처리 ${md(s.mark.at)}`) : s.made ? badge("pdf", `계약서 만듦 ${md(s.made)}`) : badge("todo", "계약서 안 만듦");
    if (s.mark) return badge("ok", `✓ 직접 제출 ${md(s.mark.at)}`);
    return s.made && s.pdf ? badge("ok", `✓ 만듦·제출 ${md(s.made)}`) : badge("todo", "미제출");
  }
  function doneBadge(r) {
    if (!r.done) return '<span class="ss-b na">— 민간 없음</span>';
    if (r.done.mark) return badge("ok", `✓ 직접 제출 ${md(r.done.mark.at)}`);
    if (r.done.made) return badge("ok", `✓ 만듦·제출 ${md(r.done.made)}`);
    return badge(startOk(r) ? "todo" : "na", startOk(r) ? "미제출" : "착수계 먼저");
  }
  function rowEl(r) {
    const el = document.createElement("div");
    el.className = "ss-grid ss-docs ss-row";
    const f = r.facility, c = r.contract;
    el.innerHTML = `
      <div class="ss-fac">${f ? "" : '<span class="ss-nocard">카드 없음 <button type="button" class="ss-mini ss-link">🔗 카드에 넣기</button><button type="button" class="ss-mini ss-del">🗑 지우기</button></span>'}${f ? `<span class="site-no">${esc(f.mgmt_no)}</span>` : ""}<span class="sk-sector ${c.sector === "관급" ? "gov" : "pri"}">${esc(c.sector)}</span>
        <b>${esc(f ? f.name : c.client || "(시설물 카드 없음)")}</b>${c.half ? `<span class="sd-half${c.half === "해당없음" ? " na" : ""}">${esc(c.half)}</span>` : ""}
        ${f && f.badge_field ? `<span class="sk-badge b-field">${esc(f.badge_field)}</span>` : ""}${f && f.badge_kind ? `<span class="sk-badge b-kind">${esc(f.badge_kind)}</span>` : ""}
        <span class="sub">${esc([c.title, c.period].filter(Boolean).join(" · "))}</span></div>
      <div class="ss-c" data-label="착수계 / 계약서"><button type="button" class="ss-cell" data-item="start">${startBadge(r)}</button></div>
      <div class="ss-c" data-label="완수계">${r.done ? `<button type="button" class="ss-cell" data-item="done">${doneBadge(r)}</button>` : doneBadge(r)}</div>
      <div class="ss-c" data-label="계산서 발행"><button type="button" class="ss-cell" data-item="invoice">${r.invoice.date ? badge("ok", `✓ ${md(r.invoice.date)} 발행`) : badge("todo", "안 함")}</button></div>`;
    el.querySelectorAll(".ss-cell").forEach((b) => b.addEventListener("click", () => openCell(r, b.dataset.item)));
    const lk = el.querySelector(".ss-link");
    if (lk) lk.addEventListener("click", () => linkCard(r));
    const dl = el.querySelector(".ss-del");
    if (dl) dl.addEventListener("click", async () => {
      const pw = await dcAskPassword(`"${r.contract.title || r.contract.client || "계약"}" — 시설물 카드에 안 넣은 계약을 지웁니다(올린 파일까지). 되돌릴 수 없습니다.`);
      if (pw == null) return;
      try { await api(`/sitok/docs/contracts/${r.contract.id}`, { method: "DELETE", body: JSON.stringify({ password: pw }) }); load(); } catch (err) { showError(errorEl, err); }
    });
    return el;
  }

  // 카드 없는 계약 → 있는 시설물 카드에 넣기 / 새 카드 만들어 넣기(계약서 PDF로 시설물 + 보고서 쪽 계약·회차까지 — 계약 목록의 [🏢 시설물 카드 만들어 넣기]와 같음)
  async function linkCard(r) {
    const overlay = document.createElement("div");
    overlay.className = "mail-overlay";
    overlay.innerHTML = '<div class="mail-box ss-mark" role="dialog" aria-modal="true"><div class="mail-wait">불러오는 중…</div></div>';
    document.body.appendChild(overlay);
    const box = overlay.querySelector(".mail-box");
    const close = () => overlay.remove();
    overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });
    let cards = [];
    try { cards = (await api("/sitok/docs/facilities")).facilities.filter((k) => k.sector === r.contract.sector); } catch (err) { box.innerHTML = `<div class="mail-msg bad">${esc(err.message)}</div>`; return; }
    box.innerHTML = `<div class="mail-head"><b>🔗 시설물 카드에 넣기</b><span class="mail-sub">${esc(r.contract.title || r.contract.client)}</span></div>
      <label class="cd-field"><span>있는 카드</span><select class="lc-pick"><option value="">— 카드 고르기 —</option>${cards.map((k) => `<option value="${k.id}">${esc(k.mgmt_no)} ${esc(k.members.length > 1 ? k.group_name || k.name : k.name)}</option>`).join("")}</select></label>
      <div class="mail-note">없으면 계약서 PDF로 새 카드를 만들어 넣습니다(보고서 자동화에도 같은 번호로 생기고 이번 반기 회차까지).</div>
      <div class="mail-msg" hidden></div>
      <div class="mail-foot"><button type="button" class="lc-close">닫기</button><button type="button" class="lc-new">🏢 새 카드 만들어 넣기</button><button type="button" class="mail-primary lc-ok">카드에 넣기</button></div>`;
    const bad = (err) => { const m = box.querySelector(".mail-msg"); m.hidden = false; m.className = "mail-msg bad"; m.textContent = err.message; };
    box.querySelector(".lc-close").addEventListener("click", close);
    box.querySelector(".lc-ok").addEventListener("click", async () => {
      const fid = Number(box.querySelector(".lc-pick").value);
      if (!fid) return;
      try { await apiPost(`/sitok/docs/contracts/${r.contract.id}/link`, { facility_id: fid }); close(); load(); } catch (err) { bad(err); }
    });
    box.querySelector(".lc-new").addEventListener("click", async (e) => {
      e.target.disabled = true;
      try { await apiPost(`/sitok/docs/contracts/${r.contract.id}/to-facility`, {}); close(); load(); } catch (err) { bad(err); e.target.disabled = false; }
    });
  }

  // 칸 창 — 착수계·완수계: [서류 창 열기](관급) + 직접 제출함 날짜, 계산서: 발행일
  function openCell(r, item) {
    const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    const civil = r.contract.sector === "민간";
    const mark = item === "invoice" ? (r.invoice.date ? { at: r.invoice.date } : null) : (r[item] || {}).mark;
    const title = item === "invoice" ? `계산서 발행 (${r.invoice.key === "all" ? "계약" : r.invoice.key.replace("-", " ")})` : item === "start" ? (civil ? "계약서" : "착수계") : "완수계";
    const overlay = document.createElement("div");
    overlay.className = "mail-overlay";
    overlay.innerHTML = `<div class="mail-box ss-mark" role="dialog" aria-modal="true">
      <div class="mail-head"><b>${esc(title)}</b><span class="mail-sub">${esc(r.facility ? `${r.facility.mgmt_no} ${r.facility.name}` : r.contract.client)} · ${esc(r.contract.title)}</span></div>
      ${item !== "invoice" && !civil ? '<button type="button" class="secondary m-open">📑 서류 창 열기(첨부 넣고 만들기)</button>' : ""}
      ${item === "start" && civil ? '<a class="secondary-link" href="sitok-docs.html">📝 계약 목록에서 계약서 열기</a>' : ""}
      <div class="mail-note">${mark ? `지금: ✓ ${esc(mark.at)}${mark.by ? ` (${esc(mark.by)})` : ""}` : item === "invoice" ? "아직 발행일 없음" : "직접 제출함 표시 없음"}</div>
      <label class="cd-field"><span>${item === "invoice" ? "발행일" : civil ? "직접 처리한 날(날인본 없이 끝난 계약 등)" : "직접 제출한 날(프로그램 쓰기 전 낸 것 등)"}</span>
        <input type="date" class="ss-date" value="${mark && mark.at ? mark.at : iso(new Date())}" /></label>
      <div class="mail-msg" hidden></div>
      <div class="mail-foot"><button type="button" class="m-close">닫기</button>${mark ? '<button type="button" class="m-clear">지우기</button>' : ""}
        <button type="button" class="mail-primary m-done">${item === "invoice" ? "✓ 발행일 저장" : "✓ 직접 제출함"}</button></div></div>`;
    document.body.appendChild(overlay);
    const close = () => overlay.remove();
    overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });
    overlay.querySelector(".m-close").addEventListener("click", close);
    const op = overlay.querySelector(".m-open");
    if (op) op.addEventListener("click", () => { close(); openSitokGov(r.contract.id, item, load); });
    const send = async (action) => {
      try {
        await apiPost(`/sitok/status/docs/${r.contract.id}/mark`, { item, action, date: overlay.querySelector(".ss-date").value || null, key: r.invoice.key });
        close();
        load();
      } catch (err) {
        const m = overlay.querySelector(".mail-msg");
        m.hidden = false;
        m.className = "mail-msg bad";
        m.textContent = err.message;
      }
    };
    overlay.querySelector(".m-done").addEventListener("click", () => send("done"));
    const cl = overlay.querySelector(".m-clear");
    if (cl) cl.addEventListener("click", () => send("clear"));
  }

  load();
})();
