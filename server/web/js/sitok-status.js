// 보고서 자동화 · 시특법 — 제출 현황(sitok-status.html, 2026-10-15 민재형 문서번호 일치화 문서 "보고서 제출현황 관리").
// 상·하반기로(◀ ▶), 한 줄 = 그 반기 시설물 카드(묶인 동은 한 줄). 칸 = 계약 · 현장점검 · 보고서 · 발주처 이메일 · FMS · 합본 출력 · 택배.
// 현장점검일·보고서 "밖에서 작성 완료"는 회차가 없는 줄도 표시됨(회차를 만듦). 방문 달력 일정은 표시해도 남음(10/19 민재형 — 완료는 색으로).
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
  const ITEM = { field: "현장점검일", report: "보고서 — 그룹웨어 밖에서 작성 완료", mail: "발주처 이메일 제출", fms: "FMS 처리", print: "합본 출력", parcel: "택배" };
  const md = (iso) => (iso ? `${iso.slice(5, 7)}/${iso.slice(8, 10)}` : "");
  const iso = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const repDone = (r) => r.report.state === "done";
  const fieldDone = (r) => !!(r.field && r.field.at);
  const roundHref = (r) => (r.report_id ? `sitok-round.html?report=${r.report_id}` : `sitok-facility.html?id=${r.facility.id}`);
  // 안 끝난 것(숫자 칸) — 회차 없는 줄은 보고서만 셈
  const CARDS = [["", "전체", "이 반기 시설물", () => true],
    ["field", "현장점검 안 함", "다녀온 날 없음", (r) => !r.field && !repDone(r)],
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
  document.querySelectorAll(".ss-sector button").forEach((b) => b.addEventListener("click", () => {
    view.sector = b.dataset.sector;
    if (view.sector === "민간") view.kind = "";
    if (!view.sector) view.field = view.kind = ""; // [전체] = 칩 거르기도 풀기(10/16)
    render();
  }));
  document.getElementById("ss-search").addEventListener("input", (e) => { view.q = e.target.value.trim().toLowerCase(); render(); });

  // 번호순 ▼▲(10/19 민재형 — 시설물 목록과 같게: 관급 → 민간 차례는 그대로, 그 안의 번호만 방향, 이 기기에 기억)
  const SORT_KEY = "kfsc-report:sitok-status-sort";
  let numDesc = true;
  try { numDesc = localStorage.getItem(SORT_KEY) !== "asc"; } catch { /* 기본 ▼ */ }
  const numKey = (f) => { const m = String((f && f.mgmt_no) || "").match(/^(관급|민간)-0*(\d+)(?:-0*(\d+))?$/); return m ? [m[1] === "관급" ? 0 : 1, Number(m[2]), Number(m[3] || 0)] : [2, 0, 0]; };
  const byNo = (a, b) => { const x = numKey(a), y = numKey(b); const d = numDesc ? -1 : 1; return x[0] - y[0] || d * (x[1] - y[1]) || d * (x[2] - y[2]); };
  document.querySelectorAll(".ss-sort button").forEach((b) => b.addEventListener("click", () => {
    numDesc = !numDesc;
    try { localStorage.setItem(SORT_KEY, numDesc ? "desc" : "asc"); } catch { /* 지금은 바뀜 */ }
    render();
  }));
  const drawSort = () => document.querySelectorAll(".ss-sort button").forEach((b) => { b.textContent = `번호순 ${numDesc ? "▼" : "▲"}`; });

  // 표 머리 엑셀식 필터(10/19 민재형 — 시설물 정기/정밀·건축/토목, 보고서 작성 중/완료, 현장점검·이메일·FMS·출력·택배 안 함/완료).
  // colf[열쇠] = 고른 값들(Set) — 없으면 전부. 열 머리를 누르면 체크 목록, 다른 열 필터·숫자 카드·검색과 함께 걸림. 폰은 표 머리 대신 표 위 버튼 줄(.ss-fbar).
  const isDone = (x) => !!(x && (x.at || x.na));
  const two = (fn) => [["안 함", (r) => !fn(r)], ["완료", fn]];
  const FILTERS = {
    kind: { label: "종류", opts: [["정기", (r) => r.kind === "정기"], ["정밀", (r) => r.kind === "정밀"], ["회차 없음", (r) => !r.kind]] },
    bfield: { label: "분야", opts: ["건축", "토목", "건축·토목"].map((v) => [v, (r) => r.facility.badge_field === v]) },
    contract: { label: "계약", opts: [["완료", (r) => !!r.contract], ["미계약", (r) => !r.contract]] }, // 계약서 있으면 완료(10/19 형)
    field: { label: "현장점검", opts: two((r) => isDone(r.field)) },
    report: { label: "보고서", opts: [["작성 중", (r) => !repDone(r)], ["완료", repDone]] },
    mail: { label: "발주처 이메일", opts: two((r) => isDone(r.mail)) },
    fms: { label: "FMS", opts: two((r) => r.fms.auto === "done" || isDone(r.fms.mark)) },
    print: { label: "합본 출력", opts: two((r) => isDone(r.print)) },
    parcel: { label: "택배", opts: two((r) => isDone(r.parcel)) },
  };
  const HEADS = [["시설물", ["kind", "bfield"]], ["계약", ["contract"]], ["현장점검", ["field"]], ["보고서", ["report"]], ["발주처 이메일", ["mail"]], ["FMS", ["fms"]], ["합본 출력", ["print"]], ["택배", ["parcel"]]];
  const colf = {};
  const passes = (r, key) => !colf[key] || FILTERS[key].opts.some(([n, fn]) => colf[key].has(n) && fn(r));
  const colOk = (r, except = "") => Object.keys(FILTERS).every((k) => k === except || passes(r, k));
  function openFilter(btn, keys, pool) {
    document.querySelector(".ss-fpop")?.remove();
    const pop = document.createElement("div");
    pop.className = "ss-fpop";
    pop.innerHTML = keys.map((k) => `<div class="ss-fgrp">${keys.length > 1 ? `<b>${FILTERS[k].label}</b>` : ""}${FILTERS[k].opts.map(([n, fn]) => {
      const cnt = pool.filter((r) => colOk(r, k) && fn(r)).length;
      return `<label><input type="checkbox" data-k="${k}" value="${esc(n)}"${!colf[k] || colf[k].has(n) ? " checked" : ""} /> ${esc(n)} <span>${cnt}</span></label>`;
    }).join("")}</div>`).join("") + '<div class="ss-fpop-foot"><button type="button" class="ss-fclear">이 칸 필터 풀기</button></div>';
    document.body.appendChild(pop);
    const box = btn.getBoundingClientRect();
    pop.style.top = `${box.bottom + window.scrollY + 4}px`;
    pop.style.left = `${Math.min(box.left + window.scrollX, window.scrollX + document.documentElement.clientWidth - pop.offsetWidth - 8)}px`;
    pop.querySelectorAll("input").forEach((inp) => inp.addEventListener("change", () => {
      const k = inp.dataset.k;
      const set = colf[k] || new Set(FILTERS[k].opts.map(([n]) => n));
      if (inp.checked) set.add(inp.value); else set.delete(inp.value);
      colf[k] = set.size === FILTERS[k].opts.length ? undefined : set;
      render();
    }));
    pop.querySelector(".ss-fclear").addEventListener("click", () => { keys.forEach((k) => { colf[k] = undefined; }); pop.remove(); render(); });
    setTimeout(() => document.addEventListener("mousedown", function off(e) {
      if (!pop.contains(e.target) && !e.target.closest(".ss-hf")) { pop.remove(); document.removeEventListener("mousedown", off); }
    }), 0);
  }

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
      (view.sector === "민간" ? "" : `<span class="sk-badge-l">관급</span>${["학교", "일반"].map((v) => chip("kind", v)).join("")}`) +
      (view.field || view.kind ? '<button type="button" class="sk-badge-f sk-badge-clear" title="분야·관급 거르기 풀기">✕ 전체 보기</button>' : "");
    bEl.querySelectorAll(".sk-badge-f[data-dim]").forEach((b) => b.addEventListener("click", () => { view[b.dataset.dim] = view[b.dataset.dim] === b.dataset.v ? "" : b.dataset.v; render(); }));
    bEl.querySelector(".sk-badge-clear")?.addEventListener("click", () => { view.field = view.kind = ""; render(); });
    // 숫자 칸
    const base = baseRows();
    const cardsEl = document.getElementById("ss-cards");
    cardsEl.innerHTML = CARDS.map(([k, label, sub, ok]) => `<button type="button" class="st-card${view.card === k ? " active" : ""}${k && base.filter(ok).length ? " warn" : ""}" data-k="${k}">
      <span class="l">${label}</span><span class="n">${base.filter(ok).length}곳</span><span class="s">${sub}</span></button>`).join("");
    cardsEl.querySelectorAll(".st-card").forEach((b) => b.addEventListener("click", () => { view.card = b.dataset.k; render(); }));
    const okCard = CARDS.find((c) => c[0] === view.card)[3];
    const pool = base.filter(okCard);
    const shown = pool.filter((r) => colOk(r)).sort((a, b) => byNo(a.facility, b.facility));
    drawSort();
    document.getElementById("ss-title").textContent = `${cur.year}년 ${cur.half} 제출 현황${view.card ? ` — ${CARDS.find((c) => c[0] === view.card)[1]}` : ""}`;
    const list = document.getElementById("ss-list");
    if (!rows.length) { list.innerHTML = '<div class="empty-note">이 반기에 회차·계약이 있는 시설물이 없습니다.</div>'; return; }
    const anyF = Object.values(colf).some(Boolean);
    document.getElementById("ss-count").innerHTML = `${shown.length}곳${anyF ? ' <button type="button" class="ss-fall">✕ 필터 풀기</button>' : ""}`;
    document.querySelector(".ss-fall")?.addEventListener("click", () => { Object.keys(colf).forEach((k) => { colf[k] = undefined; }); render(); });
    const hf = ([label, keys]) => `<button type="button" class="ss-hf${keys.some((k) => colf[k]) ? " on" : ""}" data-keys="${keys.join(",")}" title="누르면 거르기">${label} <i>▾</i></button>`;
    list.innerHTML = `<div class="ss-fbar">${HEADS.map(hf).join("")}</div>` // 폰 — 표 머리가 없어 위에 필터 버튼 줄(10/19)
      + `<div class="ss-grid ss-head">${HEADS.map((h) => `<span>${hf(h)}</span>`).join("")}</div>`;
    list.querySelectorAll(".ss-hf").forEach((b) => b.addEventListener("click", () => openFilter(b, b.dataset.keys.split(","), pool)));
    if (!shown.length) { list.insertAdjacentHTML("beforeend", '<div class="empty-note">맞는 시설물이 없습니다.</div>'); return; }
    for (const r of shown) list.appendChild(rowEl(r));
  }

  const REP = { none: ["회차 없음", "todo"], writing: ["작성 중", "todo"], running: ["만드는 중", "pdf"], failed: ["만들기 실패", "bad"], done: ["완료", "ok"] };
  function markBadge(v) { return v ? (v.na ? '<span class="ss-b na">해당없음</span>' : `<span class="ss-b ok">✓ ${md(v.at)}</span>`) : '<span class="ss-b todo">안 함</span>'; }
  function rowEl(r) {
    const el = document.createElement("div");
    el.className = "ss-grid ss-row";
    const f = r.facility;
    const [rl, rt] = REP[r.report.state] || REP.writing;
    const fmsAuto = r.fms.auto === "done" ? `<span class="ss-b ok">✓ 실적 ${esc(r.fms.auto_at)}</span>` : r.fms.auto === "contract" ? `<span class="ss-b pdf">계약만 ${esc(r.fms.auto_at)}</span>` : "";
    el.innerHTML = `
      <div class="ss-fac"><span class="site-no">${esc(f.mgmt_no)}</span><span class="sk-sector ${f.sector === "관급" ? "gov" : "pri"}">${esc(f.sector)}</span>
        <a href="sitok-facility.html?id=${f.id}"><b>${esc(f.name)}</b></a>${f.members.length > 1 ? `<span class="sk-dong-n">${f.members.length}동</span>` : ""}
        ${r.season ? `<span class="ss-kind ss-season" title="연 3회 — 이 반기 칸 안의 시기">${esc(r.season)}</span>` : ""}${r.kind ? `<span class="ss-kind">${esc(r.kind)}</span>` : ""}${f.badge_field ? `<span class="sk-badge b-field">${esc(f.badge_field)}</span>` : ""}${f.badge_kind ? `<span class="sk-badge b-kind">${esc(f.badge_kind)}</span>` : ""}</div>
      <div class="ss-c" data-label="계약">${r.contract ? '<span class="ss-b ok">완료</span>' : '<span class="ss-b todo" title="이 반기를 맡는 계약서가 없습니다(민간 계약서 작성·날인본, 관급 나라장터 계약서) — 서류 자동화에서 이 반기 계약을 넣으세요">미계약</span>'}</div>
      <div class="ss-c ss-field" data-label="현장점검">${fieldCell(r)}</div>
      <div class="ss-c" data-label="보고서">${r.report.state === "done" && !r.report.outside ? `<a class="ss-b ${rt}" href="${roundHref(r)}">${rl}${r.report.at ? ` ${esc(r.report.at)}` : ""}</a>`
        : `<button type="button" class="ss-cell" data-item="report"><span class="ss-b ${rt}">${r.report.outside ? "완료(밖에서)" : rl}${r.report.at ? ` ${esc(r.report.at)}` : ""}</span></button>`}</div>
      <div class="ss-c" data-label="발주처 이메일"><button type="button" class="ss-cell" data-item="mail">${markBadge(r.mail)}</button></div>
      <div class="ss-c" data-label="FMS"><button type="button" class="ss-cell" data-item="fms">${fmsAuto || markBadge(r.fms.mark)}</button></div>
      <div class="ss-c" data-label="합본 출력"><button type="button" class="ss-cell" data-item="print">${markBadge(r.print)}</button></div>
      <div class="ss-c" data-label="택배"><button type="button" class="ss-cell" data-item="parcel">${markBadge(r.parcel)}</button></div>`;
    el.querySelectorAll(".ss-cell").forEach((b) => b.addEventListener("click", () => openMark(r, b.dataset.item)));
    el.querySelectorAll(".ss-t").forEach((b) => b.addEventListener("click", () => fieldToggle(r, b.dataset.act)));
    return el;
  }

  // 현장점검 칸(10/19 민재형 "현장점검 날짜 표기하고 안함·완료 버튼") — 날짜(완료한 날 또는 방문 달력 일정) + [안 함 | 완료], 날짜를 누르면 다른 날로 표시하는 창
  function fieldCell(r) {
    const done = fieldDone(r);
    const v = r.visit;
    const when = done ? `<span class="ss-b ok">✓ ${md(r.field.at)}</span>`
      : v ? `<span class="ss-date-t">${md(v.start)}${v.end !== v.start ? `~${md(v.end)}` : ""} 예정</span>` : '<span class="ss-date-t none">일정 없음</span>';
    return `<button type="button" class="ss-cell" data-item="field" title="다른 날로 표시하려면 누르세요">${when}</button>
      <span class="ss-tog" role="group" aria-label="현장점검"><button type="button" class="ss-t${done ? "" : " on"}" data-act="clear">안 함</button><button type="button" class="ss-t${done ? " on" : ""}" data-act="done">완료</button></span>`;
  }
  async function postMark(r, item, action, date) {
    if (r.report_id) return apiPost(`/sitok/status/reports/${r.report_id}/mark`, { item, action, date });
    return apiPost(`/sitok/status/facilities/${r.facility.id}/mark`, { item, action, date, year: cur.year, half: r.season || cur.half });
  }
  async function fieldToggle(r, act) {
    const done = fieldDone(r);
    if ((act === "done") === done) return; // 이미 그 상태
    if (act === "clear" && !confirm(`${r.facility.mgmt_no} ${r.facility.name} 현장점검 완료(${md(r.field.at)}) 표시를 지울까요?`)) return;
    const today = iso();
    const date = act === "done" ? (r.visit && r.visit.end <= today ? r.visit.end : today) : null; // 잡힌 날이 지났으면 그날, 아니면 오늘
    try { await postMark(r, "field", act, date); load(); } catch (err) { alert(err.message); }
  }

  // 칸 표시 창 — 날짜(기본 오늘) [표시] / [지우기] / FMS [해당없음]
  function openMark(r, item) {
    const visit = item === "field" || item === "report"; // 현장점검·밖에서 완료 — 회차가 없어도 됨(서버가 회차를 만듦)
    if (!r.report_id && !visit) { alert("이 반기 회차를 아직 안 만들었습니다 — 시설물 화면에서 회차를 만든 뒤 표시하세요."); return; }
    const mk = item === "fms" ? r.fms.mark : item === "report" ? (r.report.outside ? { at: r.report.at_iso || "", by: "" } : null) : r[item];
    const overlay = document.createElement("div");
    overlay.className = "mail-overlay";
    overlay.innerHTML = `<div class="mail-box ss-mark" role="dialog" aria-modal="true">
      <div class="mail-head"><b>${ITEM[item]}</b><span class="mail-sub">${esc(r.facility.mgmt_no)} ${esc(r.facility.name)}${r.season ? ` · ${esc(r.season)}` : ""}${r.kind ? ` · ${esc(r.kind)}` : ""}</span></div>
      ${item === "fms" && r.fms.auto ? `<div class="mail-note">FMS 자동 제출 기록: ${r.fms.auto === "done" ? "실적보고까지 끝" : "계약 등록까지"} ${esc(r.fms.auto_at)}</div>` : ""}
      ${item === "mail" && r.email ? `<div class="mail-note">계약 담당 이메일: <a href="mailto:${esc(r.email)}">${esc(r.email)}</a></div>` : ""}
      ${item === "report" ? `<div class="mail-note">그룹웨어 쓰기 전에 냈거나 밖에서(토목 등) 쓴 보고서면 표시하세요 — 보고서 칸이 완료가 되고 방문 달력 칸은 그대로 남아 진하게 채워집니다. <a href="${roundHref(r)}">${r.report_id ? "회차 화면 열기 ›" : "시설물 화면 열기 ›"}</a></div>` : ""}
      ${item === "field" ? '<div class="mail-note">오늘·지난 날짜 = 다녀옴(완료 — 방문 달력 칸이 색으로 채워짐), 오늘 이후 날짜 = 예정(방문 달력 일정을 그날로). 달력에서 빠지지 않습니다.</div>' : ""}
      <div class="mail-note">${mk ? (mk.na ? `지금: 해당없음 (${esc(mk.by || "")})` : `지금: ✓ ${esc(mk.at)}${mk.by ? ` (${esc(mk.by)})` : ""}`) : "지금: 표시 없음"}</div>
      <label class="cd-field"><span>${item === "field" ? "현장점검일" : "날짜"}</span><input type="date" class="ss-date" value="${mk && mk.at ? mk.at : iso()}" /></label>
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
        const date = overlay.querySelector(".ss-date").value || null;
        await postMark(r, item, action, date);
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
