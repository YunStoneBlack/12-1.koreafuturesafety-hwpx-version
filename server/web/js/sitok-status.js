// 보고서 자동화 · 시특법 — 제출 현황(sitok-status.html, 2026-10-15 민재형 문서번호 일치화 문서 "보고서 제출현황 관리").
// 상·하반기로(◀ ▶), 한 줄 = 그 반기 시설물 카드(묶인 동은 한 줄). 칸 = 보고서 · 발주처 이메일 · FMS · 합본 출력 · 택배.
// 칸을 누르면 작은 창: 날짜 넣고 [표시] / [지우기](FMS는 [해당없음]도). 위 숫자 칸 = 안 끝난 것 개수(누르면 그것만). 민간·관급·뱃지 거르기는 시설물 목록과 같음.
// API: GET /sitok/status/reports?year&half, POST /sitok/status/reports/{id}/mark — server/api/routers/sitok_status.py

(function () {
  const errorEl = document.getElementById("error");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const HALF_KEY = "kfsc-report:sitok-status-half";
  const now = new Date();
  let cur = { year: now.getFullYear(), half: now.getMonth() < 6 ? "상반기" : "하반기" };
  try { cur = { ...cur, ...JSON.parse(sessionStorage.getItem(HALF_KEY) || "{}") }; } catch { /* 지금 반기 */ }
  let rows = [];
  const view = { sector: "", field: "", kind: "", card: "", q: "" };
  const ITEM = { mail: "발주처 이메일 제출", fms: "FMS 처리", print: "합본 출력", parcel: "택배" };
  const md = (iso) => (iso ? `${iso.slice(5, 7)}/${iso.slice(8, 10)}` : "");
  const repDone = (r) => r.report.state === "done";
  // 안 끝난 것(숫자 칸) — 회차 없는 줄은 보고서만 셈
  const CARDS = [["", "전체", "이 반기 시설물", () => true],
    ["report", "보고서 미완료", "합본 PDF 안 만듦", (r) => !repDone(r)],
    ["mail", "이메일 미제출", "발주처에 안 보냄", (r) => !r.mail],
    ["fms", "FMS 미처리", "해당없음 빼고", (r) => !r.fms.done],
    ["print", "출력 안 함", "합본 출력", (r) => !r.print],
    ["parcel", "택배 안 보냄", "보고서 택배", (r) => !r.parcel]];

  async function load() {
    document.getElementById("ss-label").textContent = `${cur.year}년 ${cur.half}`;
    try {
      const out = await api(`/sitok/status/reports?year=${cur.year}&half=${encodeURIComponent(cur.half)}`);
      rows = out.rows;
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
  document.getElementById("ss-prev").addEventListener("click", () => shift(-1));
  document.getElementById("ss-next").addEventListener("click", () => shift(1));
  document.querySelectorAll(".ss-sector button").forEach((b) => b.addEventListener("click", () => { view.sector = b.dataset.sector; if (view.sector === "민간") view.kind = ""; render(); }));
  document.getElementById("ss-search").addEventListener("input", (e) => { view.q = e.target.value.trim().toLowerCase(); render(); });

  const baseRows = () => rows.filter((r) => (!view.sector || r.facility.sector === view.sector) && (!view.field || r.facility.badge_field === view.field) &&
    (!view.kind || r.facility.badge_kind === view.kind) && (!view.q || `${r.facility.mgmt_no} ${r.facility.name} ${r.facility.members.map((m) => m.name).join(" ")}`.toLowerCase().includes(view.q)));

  function render() {
    document.querySelectorAll(".ss-sector button").forEach((b) => b.classList.toggle("on", b.dataset.sector === view.sector));
    // 뱃지 칩
    const inSector = rows.filter((r) => !view.sector || r.facility.sector === view.sector);
    const chip = (dim, v) => {
      const n = inSector.filter((r) => (dim === "field" ? r.facility.badge_field : r.facility.badge_kind) === v).length;
      return `<button type="button" class="sk-badge-f b-${dim}${view[dim] === v ? " on" : ""}" data-dim="${dim}" data-v="${esc(v)}">${esc(v)} <b>${n}</b></button>`;
    };
    const bEl = document.getElementById("ss-badges");
    bEl.innerHTML = `<span class="sk-badge-l">분야</span>${["건축", "토목", "건축·토목"].map((v) => chip("field", v)).join("")}` +
      (view.sector === "민간" ? "" : `<span class="sk-badge-l">관급</span>${["학교", "일반"].map((v) => chip("kind", v)).join("")}`);
    bEl.querySelectorAll(".sk-badge-f").forEach((b) => b.addEventListener("click", () => { view[b.dataset.dim] = view[b.dataset.dim] === b.dataset.v ? "" : b.dataset.v; render(); }));
    // 숫자 칸
    const base = baseRows();
    const cardsEl = document.getElementById("ss-cards");
    cardsEl.innerHTML = CARDS.map(([k, label, sub, ok]) => `<button type="button" class="st-card${view.card === k ? " active" : ""}${k && base.filter(ok).length ? " warn" : ""}" data-k="${k}">
      <span class="l">${label}</span><span class="n">${base.filter(ok).length}곳</span><span class="s">${sub}</span></button>`).join("");
    cardsEl.querySelectorAll(".st-card").forEach((b) => b.addEventListener("click", () => { view.card = b.dataset.k; render(); }));
    const okCard = CARDS.find((c) => c[0] === view.card)[3];
    const shown = base.filter(okCard).sort((a, b) => noKey(b.facility) - noKey(a.facility));
    document.getElementById("ss-title").textContent = `${cur.year}년 ${cur.half} 제출 현황${view.card ? ` — ${CARDS.find((c) => c[0] === view.card)[1]}` : ""}`;
    document.getElementById("ss-count").textContent = `${shown.length}곳`;
    const list = document.getElementById("ss-list");
    if (!rows.length) { list.innerHTML = '<div class="empty-note">이 반기에 회차·계약이 있는 시설물이 없습니다.</div>'; return; }
    if (!shown.length) { list.innerHTML = '<div class="empty-note">맞는 시설물이 없습니다.</div>'; return; }
    list.innerHTML = `<div class="ss-grid ss-head"><span>시설물</span><span>보고서</span><span>발주처 이메일</span><span>FMS</span><span>합본 출력</span><span>택배</span></div>`;
    for (const r of shown) list.appendChild(rowEl(r));
  }
  const noKey = (f) => { const m = String(f.mgmt_no || "").match(/^(관급|민간)-0*(\d+)(?:-0*(\d+))?$/); return m ? (m[1] === "관급" ? 2e8 : 1e8) + Number(m[2]) * 100 + Number(m[3] || 0) : 0; };

  const REP = { none: ["회차 없음", "todo"], writing: ["작성 중", "todo"], running: ["만드는 중", "pdf"], failed: ["만들기 실패", "bad"], done: ["완료", "ok"] };
  function markBadge(v) { return v ? (v.na ? '<span class="ss-b na">해당없음</span>' : `<span class="ss-b ok">✓ ${md(v.at)}</span>`) : '<span class="ss-b todo">안 함</span>'; }
  function rowEl(r) {
    const el = document.createElement("div");
    el.className = "ss-grid ss-row";
    const f = r.facility;
    const [rl, rt] = REP[r.report.state] || REP.writing;
    const roundHref = r.report_id ? `sitok-round.html?report=${r.report_id}` : `sitok-facility.html?id=${f.id}`;
    const fmsAuto = r.fms.auto === "done" ? `<span class="ss-b ok">✓ 실적 ${esc(r.fms.auto_at)}</span>` : r.fms.auto === "contract" ? `<span class="ss-b pdf">계약만 ${esc(r.fms.auto_at)}</span>` : "";
    el.innerHTML = `
      <div class="ss-fac"><span class="site-no">${esc(f.mgmt_no)}</span><span class="sk-sector ${f.sector === "관급" ? "gov" : "pri"}">${esc(f.sector)}</span>
        <a href="sitok-facility.html?id=${f.id}"><b>${esc(f.name)}</b></a>${f.members.length > 1 ? `<span class="sk-dong-n">${f.members.length}동</span>` : ""}
        ${r.kind ? `<span class="ss-kind">${esc(r.kind)}</span>` : ""}${f.badge_field ? `<span class="sk-badge b-field">${esc(f.badge_field)}</span>` : ""}${f.badge_kind ? `<span class="sk-badge b-kind">${esc(f.badge_kind)}</span>` : ""}</div>
      <div class="ss-c" data-label="보고서"><a class="ss-b ${rt}" href="${roundHref}">${rl}${r.report.at ? ` ${esc(r.report.at)}` : ""}</a></div>
      <div class="ss-c" data-label="발주처 이메일"><button type="button" class="ss-cell" data-item="mail">${markBadge(r.mail)}</button></div>
      <div class="ss-c" data-label="FMS"><button type="button" class="ss-cell" data-item="fms">${fmsAuto || markBadge(r.fms.mark)}</button></div>
      <div class="ss-c" data-label="합본 출력"><button type="button" class="ss-cell" data-item="print">${markBadge(r.print)}</button></div>
      <div class="ss-c" data-label="택배"><button type="button" class="ss-cell" data-item="parcel">${markBadge(r.parcel)}</button></div>`;
    el.querySelectorAll(".ss-cell").forEach((b) => b.addEventListener("click", () => openMark(r, b.dataset.item)));
    return el;
  }

  // 칸 표시 창 — 날짜(기본 오늘) [표시] / [지우기] / FMS [해당없음]
  function openMark(r, item) {
    if (!r.report_id) { alert("이 반기 회차를 아직 안 만들었습니다 — 시설물 화면에서 회차를 만든 뒤 표시하세요."); return; }
    const mk = item === "fms" ? r.fms.mark : r[item];
    const today = new Date();
    const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    const overlay = document.createElement("div");
    overlay.className = "mail-overlay";
    overlay.innerHTML = `<div class="mail-box ss-mark" role="dialog" aria-modal="true">
      <div class="mail-head"><b>${ITEM[item]}</b><span class="mail-sub">${esc(r.facility.mgmt_no)} ${esc(r.facility.name)}${r.kind ? ` · ${esc(r.kind)}` : ""}</span></div>
      ${item === "fms" && r.fms.auto ? `<div class="mail-note">FMS 자동 제출 기록: ${r.fms.auto === "done" ? "실적보고까지 끝" : "계약 등록까지"} ${esc(r.fms.auto_at)}</div>` : ""}
      ${item === "mail" && r.email ? `<div class="mail-note">계약 담당 이메일: <a href="mailto:${esc(r.email)}">${esc(r.email)}</a></div>` : ""}
      <div class="mail-note">${mk ? (mk.na ? `지금: 해당없음 (${esc(mk.by || "")})` : `지금: ✓ ${esc(mk.at)} (${esc(mk.by || "")})`) : "지금: 표시 없음"}</div>
      <label class="cd-field"><span>날짜</span><input type="date" class="ss-date" value="${mk && mk.at ? mk.at : iso(today)}" /></label>
      ${r.facility.members.length > 1 ? `<div class="mail-note">묶인 동(${esc(r.facility.members.map((m) => m.name).join(", "))})도 같이 표시됩니다.</div>` : ""}
      <div class="mail-msg" hidden></div>
      <div class="mail-foot"><button type="button" class="m-close">닫기</button>${mk ? '<button type="button" class="m-clear">지우기</button>' : ""}
        ${item === "fms" ? '<button type="button" class="m-na">해당없음</button>' : ""}<button type="button" class="mail-primary m-done">✓ 표시</button></div></div>`;
    document.body.appendChild(overlay);
    const close = () => overlay.remove();
    overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });
    overlay.querySelector(".m-close").addEventListener("click", close);
    const send = async (action) => {
      try {
        await apiPost(`/sitok/status/reports/${r.report_id}/mark`, { item, action, date: overlay.querySelector(".ss-date").value || null });
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
    const na = overlay.querySelector(".m-na");
    if (na) na.addEventListener("click", () => send("na"));
  }

  load();
})();
