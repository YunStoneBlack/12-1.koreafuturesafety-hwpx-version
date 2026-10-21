// 보고서 자동화 · 시특법 — 시설물 목록(sitok.html, 2026-10-10). 서버 GET /sitok/facilities(server/api/routers/sitok.py).
// 줄을 누르면 sitok-facility.html?id= (시설물·계약 보기·고치기). 보고서 틀은 2종 / 3종 일반 / 3종 학교.
// 10/13 사용자·민재형 — 산안법 현장 목록(dashboard.html)과 같게: 이름 앞 번호표 "26-4", [최근 열람순] [번호순 ▼▲](이 기기에 기억),
// [📞 전화](담당자, 없으면 관리주체 전화) [📍 지도](시설물 주소 — PC 네이버 지도, 폰 티맵·네이버 고르기, app.js siteLinkButtons), [전체·민간·관급] 거르기,
// 목록함 구분 카드 장기·지속계약 / 1회성·입찰계약 / 지속계약 종료(누르면 그것만) + 줄마다 바꾸는 버튼(서로 옮김, 묶인 동은 같이 — 산안법 공사 상태 4칸처럼).
// 10/15 민재형 "같은 계약인데 시설물 카드가 2개 — 이상함": 한 보고서로 묶인 동은 카드 하나(묶음 이름 + N동, 동 칩 → 그 동 화면, 줄 → 대표 동). 속 자료는 동마다 따로(FMS·결과표).
// 10/15 민재형 "전체 선택 삭제기능 없애줘": 목록의 체크 칸·[전체 선택]·[선택 삭제]를 뺌(지우기는 시설물 화면 [삭제] 하나씩).
// 10/15 민재형 문서번호 일치화: 번호 "민간-3"·"관급-1"(서류 자동화 시설물 카드와 같은 번호), 민간·관급은 시설물 칸(sector),
// 뱃지(분야 건축/토목/건축·토목, 관급 종류 학교/일반/내진) 줄마다 + 뱃지 칩(개수, 누르면 그것만).

(function () {
  const errorEl = document.getElementById("error");
  const TEMPLATE_LABEL = { "2종": "2종", "3종일반": "3종 일반", "3종학교": "3종 학교" };
  const TYPES = [["장기", "장기·지속계약", "연락·일정 관리 대상"], ["1회성", "1회성·입찰계약", "입찰 · 한 번 점검"], ["종료", "지속계약 종료", "일정 관리에서 빠짐"]];
  const TYPE_SHORT = { "장기": "장기·지속", "1회성": "1회성·입찰", "종료": "계약 종료" };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const money = (n) => (n ? `${Number(n).toLocaleString("ko-KR")}원` : "");
  const ymd = (s) => (s ? s.replaceAll("-", ".") : "?");
  let rows = [];
  let typeFilter = "";
  let sector = "";
  const badge = { field: "", kind: "" };

  // ---------- 정렬(산안법과 같음) ----------
  const SORT_KEY = "kfsc-report:sitok-sort";
  let sort = { mode: "no", desc: true };
  try { sort = { ...sort, ...JSON.parse(localStorage.getItem(SORT_KEY) || "{}") }; } catch { /* 기억 못 하면 기본 */ }
  const mgmtKey = (f) => { // "관급-3" < "민간-1"(구분끼리 묶고 그 안에서 번호), 예전 "26-4"는 맨 뒤
    const s = String(f.mgmt_no || "");
    const m = s.match(/^(관급|민간)-0*(\d+)(?:-0*(\d+))?$/); // 시설물 여럿 카드 "관급-6-2"(10/15 밤)
    if (m) return (m[1] === "관급" ? 1e8 : 2e8) + Number(m[2]) * 100 + Number(m[3] || 0);
    const o = s.match(/^(\d{2}|\d{4})-0*(\d+)$/);
    return o ? 3e8 + Number(o[1].slice(-2)) * 1e5 + Number(o[2]) : null;
  };
  const byNumber = (a, b, desc) => {
    const x = mgmtKey(a), y = mgmtKey(b);
    if (x === null || y === null) return x === null ? (y === null ? b.id - a.id : 1) : -1;
    const block = (k) => Math.floor(k / 1e8); // 구분(관급·민간) 차례는 그대로, 그 안의 번호만 ▼▲
    return block(x) - block(y) || (desc ? y - x : x - y) || a.id - b.id;
  };
  const sortRows = (list) => (sort.mode === "viewed"
    ? list.sort((a, b) => (b.viewed_at || "").localeCompare(a.viewed_at || "") || byNumber(a, b, true))
    : list.sort((a, b) => byNumber(a, b, sort.desc)));
  function drawSort() {
    document.querySelectorAll(".sk-sort button").forEach((b) => {
      const on = b.dataset.sort === sort.mode;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on);
      if (b.dataset.sort === "no") b.textContent = `번호순 ${on ? (sort.desc ? "▼" : "▲") : ""}`.trim();
    });
    document.querySelectorAll(".sk-sector-f button").forEach((b) => {
      const on = b.dataset.sector === sector;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on);
    });
  }
  document.querySelectorAll(".sk-sort button").forEach((b) => b.addEventListener("click", () => {
    if (b.dataset.sort === "no" && sort.mode === "no") sort.desc = !sort.desc; // 번호순 한 번 더 → 방향 바꿈
    else if (b.dataset.sort === "no") sort.desc = true;
    sort.mode = b.dataset.sort;
    try { localStorage.setItem(SORT_KEY, JSON.stringify(sort)); } catch { /* 지금은 바뀜 */ }
    render();
  }));
  document.querySelectorAll(".sk-sector-f button").forEach((b) => b.addEventListener("click", () => {
    sector = b.dataset.sector;
    if (sector === "민간") badge.kind = "";
    if (!sector) badge.field = badge.kind = ""; // [전체] = 칩 거르기도 풀기(10/16)
    render();
  }));
  const sectorOf = (f) => f.sector || contractOf(f)?.sector || "민간";
  const badgeOk = (f) => (!badge.field || f.badge_field === badge.field) && (!badge.kind || f.badge_kind === badge.kind);
  const FIELDS = ["건축", "토목", "건축·토목"], KINDS = ["학교", "일반"];
  // 뱃지 칩(10/15 민재형 "뱃지를 달면 그 뱃지 개수 파악·그 뱃지만") — 지금 구분·목록함 안에서 셈, 누르면 거르기(한 번 더 = 풀기)
  function renderBadges() {
    const box = document.getElementById("sk-badges");
    const base = units().filter((f) => (!sector || sectorOf(f) === sector) && (!typeFilter || f.contract_type === typeFilter));
    const chip = (dim, v) => {
      const n = base.filter((f) => (dim === "field" ? f.badge_field : f.badge_kind) === v).length;
      return `<button type="button" class="sk-badge-f b-${dim}${badge[dim] === v ? " on" : ""}" data-dim="${dim}" data-v="${esc(v)}" aria-pressed="${badge[dim] === v}">${esc(v)} <b>${n}</b></button>`;
    };
    box.innerHTML = `<span class="sk-badge-l">분야</span>${FIELDS.map((v) => chip("field", v)).join("")}` +
      (sector === "민간" ? "" : `<span class="sk-badge-l">관급</span>${KINDS.map((v) => chip("kind", v)).join("")}`) +
      (badge.field || badge.kind ? '<button type="button" class="sk-badge-f sk-badge-clear" title="분야·관급 거르기 풀기">✕ 전체 보기</button>' : "");
    box.querySelectorAll(".sk-badge-f[data-dim]").forEach((b) => b.addEventListener("click", () => {
      badge[b.dataset.dim] = badge[b.dataset.dim] === b.dataset.v ? "" : b.dataset.v;
      render();
    }));
    box.querySelector(".sk-badge-clear")?.addEventListener("click", () => { badge.field = badge.kind = ""; render(); });
  }

  // 묶인 동(숭의 B동)은 계약이 1번 동에 있어 — 같은 묶음의 계약을 씀(민간·관급 거르기·계약 칸)
  const contractOf = (f) => f.latest || (f.group ? rows.find((x) => x.group && x.group.id === f.group.id && x.latest)?.latest : null) || null;

  // 목록 한 줄 = 시설물 하나 또는 묶음 하나(대표 동 값 + members, 최근 열람은 동 중 가장 최근)
  function units() {
    const out = [];
    const byGroup = new Map();
    for (const f of rows) {
      const g = f.group && f.group.members.length > 1 ? f.group : null;
      if (!g) { out.push({ ...f, members: [f] }); continue; }
      if (!byGroup.has(g.id)) byGroup.set(g.id, []);
      byGroup.get(g.id).push(f);
    }
    for (const list of byGroup.values()) {
      const g = list[0].group;
      const order = g.members.map((m) => m.id);
      list.sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
      const lead = list[0];
      out.push({ ...lead, members: list, group_name: g.name, viewed_at: list.map((x) => x.viewed_at || "").sort().pop() });
    }
    return out;
  }
  const unitText = (u) => u.members.flatMap((f) => [f.name, f.address, f.owner_name, f.fms_no, f.mgmt_no, f.contact_name]).concat(u.group_name || "");

  function renderCards() {
    const box = document.getElementById("sk-cards");
    const base = units().filter((f) => (!sector || sectorOf(f) === sector) && badgeOk(f));
    const total = base.length;
    box.innerHTML = [["", "전체", "등록한 시설물 전부"], ...TYPES].map(([t, label, sub]) => {
      const n = t ? base.filter((f) => f.contract_type === t).length : total;
      const pct = total ? Math.round((n / total) * 100) : 0;
      return `<button type="button" class="sc-card${t === typeFilter ? " on" : ""}" data-s="${t}" aria-pressed="${t === typeFilter}">
        <span class="stc-top"><span class="stc-label">${label}</span>${t ? `<span class="stc-pct">${pct}%</span>` : ""}</span>
        <span class="stc-num">${n}<small>곳</small></span>
        <span class="stc-bar"><i style="width:${t ? pct : total ? 100 : 0}%"></i></span>
        <span class="stc-sub">${sub}</span></button>`;
    }).join("");
    box.querySelectorAll(".sc-card").forEach((b) => b.addEventListener("click", () => { typeFilter = b.dataset.s; render(); }));
  }

  // 계약 구분 3칸(줄마다) — 누르면 "A → B로 바꾸시겠습니까?"(산안법 공사 상태와 같음), 묶인 동은 서버가 같이 바꿈
  function typeSwitch(f) {
    const box = document.createElement("div");
    box.className = "st-switch sk-type";
    box.setAttribute("role", "group");
    box.setAttribute("aria-label", "계약 구분");
    for (const [t] of TYPES) {
      const b = document.createElement("button");
      b.type = "button";
      b.dataset.s = t;
      b.textContent = TYPE_SHORT[t];
      b.classList.toggle("on", t === f.contract_type);
      b.setAttribute("aria-pressed", t === f.contract_type);
      b.addEventListener("click", async (e) => {
        e.preventDefault(); // 줄은 링크 — 시설물 화면으로 넘어가지 않게
        e.stopPropagation();
        if (t === f.contract_type) return;
        const group = f.group && f.group.members.length > 1 ? `\n\n한 보고서로 묶인 동(${f.group.members.map((m) => m.name).join(", ")})도 같이 바뀝니다.` : "";
        const jong = (w) => (w.charCodeAt(w.length - 1) - 0xAC00) % 28; // 마지막 글자 받침(0 = 없음, 8 = ㄹ) — 로/으로
        const to = TYPE_SHORT[t];
        if (!confirm(`${TYPE_SHORT[f.contract_type] || "?"} → ${to}${jong(to) && jong(to) !== 8 ? "으로" : "로"} 바꾸시겠습니까?${group}`)) return;
        box.classList.add("busy");
        try {
          const out = await apiPost(`/sitok/facilities/${f.id}/contract-type`, { contract_type: t });
          rows.forEach((x) => { if (out.ids.includes(x.id)) x.contract_type = t; });
          render();
        } catch (err) {
          alert(`바꾸지 못했습니다: ${err.message}`);
          box.classList.remove("busy");
        }
      });
      box.appendChild(b);
    }
    return box;
  }

  function render() {
    renderCards();
    renderBadges();
    drawSort();
    const q = document.getElementById("sk-search").value.trim().replace(/\s+/g, "").toLowerCase();
    const all = units();
    const shown = sortRows(all.filter((f) => (!typeFilter || f.contract_type === typeFilter) && (!sector || sectorOf(f) === sector) && badgeOk(f) &&
      (!q || unitText(f).some((v) => (v || "").replace(/\s+/g, "").toLowerCase().includes(q)))));
    const filtered = q || typeFilter || sector || badge.field || badge.kind;
    document.getElementById("sk-count").textContent = filtered ? `${shown.length} / ${all.length}곳` : `${all.length}곳`;
    const list = document.getElementById("sk-list");
    if (!rows.length) {
      list.innerHTML = '<div class="empty-note">아직 등록한 시설물이 없습니다. 오른쪽 위 [+ 점검 대상 등록]에서 시설물관리대장·계약서 PDF를 올리면 칸이 채워집니다.</div>';
      return;
    }
    if (!shown.length) {
      list.innerHTML = '<div class="empty-note">맞는 시설물이 없습니다.</div>';
      return;
    }
    list.innerHTML = "";
    for (const f of shown) {
      const ids = f.members.map((m) => m.id);
      const multi = ids.length > 1;
      const c = contractOf(f);
      const contract = c
        ? `${ymd(c.start_date)} ~ ${ymd(c.end_date)}` +
          `${c.amount ? ` · ${money(c.amount)}${c.sector === "민간" && c.halves === "연간" ? "(반기)" : ""}` : ""}`
        : '<span class="sk-none">계약 없음</span>';
      const rn = f.renew; // 장기·지속 계약 끝나기 60일 전부터(10/13)
      const renew = rn ? `<span class="sk-renew-tag${rn.days < 0 ? " over" : ""}">${rn.days < 0 ? "⚠ 계약 끝남 — 다음 계약서 필요" : `⏳ ${rn.days}일 뒤 계약 끝 — 다음 계약서 준비`}</span>` : "";
      const row = document.createElement("a");
      row.className = `sk-row${f.contract_type === "종료" ? " ended" : ""}`;
      row.href = `sitok-facility.html?id=${f.id}`;
      // 산안법 현장 목록처럼(10/13 사용자): 번호표·이름·틀 / 주소 · 관리주체 / 시설물번호 · 종류 · 담당 / [📞][📍][주소 복사] 를 이름 칸 한 곳에
      row.innerHTML = `
        <div class="sk-main">
          <div class="sk-title">${f.mgmt_no ? `<span class="site-no">${esc(f.mgmt_no)}</span>` : ""}<span class="sk-sector ${sectorOf(f) === "관급" ? "gov" : "pri"}">${esc(sectorOf(f))}</span><b>${esc(multi ? f.group_name : f.name)}</b>
            ${multi ? `<span class="sk-dong-n">${ids.length}동</span>` : ""}<span class="sk-tpl t${esc(f.civil_kind && f.civil_kind !== "옹벽" ? "none" : f.template)}">${esc(f.civil_kind && f.civil_kind !== "옹벽" ? "틀 준비 중" : f.civil_kind === "옹벽" ? (f.template === "2종" ? "옹벽 2종" : "옹벽 3종") : TEMPLATE_LABEL[f.template] || f.template)}</span>
            ${f.badge_field ? `<span class="sk-badge b-field">${esc(f.badge_field)}</span>` : ""}${f.badge_kind ? `<span class="sk-badge b-kind">${esc(f.badge_kind)}</span>` : ""}</div>
          <div class="sk-sub">${esc([f.address, f.owner_name].filter(Boolean).join(" · "))}</div>
          ${multi ? `<div class="sk-dong-chips">${f.members.map((m, i) => `<span class="sk-dong-chip" data-href="sitok-facility.html?id=${m.id}" title="${esc(m.name)} 화면">제${i + 1}장 ${esc(m.name)}${m.fms_no ? ` <small>${esc(m.fms_no)}</small>` : ""}</span>`).join("")}</div>`
            : `<div class="sk-sub">${esc([f.fms_no, f.use_type || f.main_use, f.contact_name && `담당 ${f.contact_name}`].filter(Boolean).join(" · "))}</div>`}
        </div>
        <div class="sk-contract">${contract}${renew}</div>`;
      row.querySelectorAll(".sk-dong-chip").forEach((c) => c.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); location.href = c.dataset.href; }));
      const links = siteLinkButtons(f.phone, f.address); // [📞 전화] [📍 지도] — 전화 = 계약 정보 현장 담당, 비면 관리주체(10/20)
      if (links) row.querySelector(".sk-main").appendChild(links);
      row.appendChild(typeSwitch(f));
      list.appendChild(row);
    }
  }

  document.getElementById("sk-search").addEventListener("input", render);
  api("/sitok/facilities").then((r) => { rows = r; render(); }).catch((err) => showError(errorEl, err));
})();
