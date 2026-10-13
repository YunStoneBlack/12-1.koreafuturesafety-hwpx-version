// 보고서 자동화 · 시특법 — 시설물 목록(sitok.html, 2026-10-10). 서버 GET /sitok/facilities(server/api/routers/sitok.py).
// 줄을 누르면 sitok-facility.html?id= (시설물·계약 보기·고치기). 보고서 틀은 2종 / 3종 일반 / 3종 학교.
// 10/13 사용자·민재형 — 산안법 현장 목록(dashboard.html)과 같게: 이름 앞 번호표 "26-4", [최근 열람순] [번호순 ▼▲](이 기기에 기억),
// [📞 전화](담당자, 없으면 관리주체 전화) [📍 지도](시설물 주소 — PC 네이버 지도, 폰 티맵·네이버 고르기, app.js siteLinkButtons), [전체·민간·관급] 거르기,
// 목록함 구분 카드 장기·지속계약 / 1회성·입찰계약 / 지속계약 종료(누르면 그것만) + 줄마다 바꾸는 버튼(서로 옮김, 묶인 동은 같이 — 산안법 공사 상태 4칸처럼).

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

  // ---------- 정렬(산안법과 같음) ----------
  const SORT_KEY = "kfsc-report:sitok-sort";
  let sort = { mode: "no", desc: true };
  try { sort = { ...sort, ...JSON.parse(localStorage.getItem(SORT_KEY) || "{}") }; } catch { /* 기억 못 하면 기본 */ }
  const mgmtKey = (f) => {
    const m = String(f.mgmt_no || "").match(/^(\d{2}|\d{4})-0*(\d+)$/);
    return m ? Number(m[1].slice(-2)) * 1e7 + Number(m[2]) : null;
  };
  const byNumber = (a, b, desc) => {
    const x = mgmtKey(a), y = mgmtKey(b);
    if (x === null || y === null) return x === null ? (y === null ? b.id - a.id : 1) : -1;
    return (desc ? y - x : x - y) || a.id - b.id;
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
  document.querySelectorAll(".sk-sector-f button").forEach((b) => b.addEventListener("click", () => { sector = b.dataset.sector; render(); }));

  // 묶인 동(숭의 B동)은 계약이 1번 동에 있어 — 같은 묶음의 계약을 씀(민간·관급 거르기·계약 칸)
  const contractOf = (f) => f.latest || (f.group ? rows.find((x) => x.group && x.group.id === f.group.id && x.latest)?.latest : null) || null;

  function renderCards() {
    const box = document.getElementById("sk-cards");
    const base = rows.filter((f) => !sector || contractOf(f)?.sector === sector);
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
    drawSort();
    const q = document.getElementById("sk-search").value.trim().replace(/\s+/g, "").toLowerCase();
    const shown = sortRows(rows.filter((f) => (!typeFilter || f.contract_type === typeFilter) && (!sector || contractOf(f)?.sector === sector) &&
      (!q || [f.name, f.address, f.owner_name, f.fms_no, f.mgmt_no, f.contact_name].some((v) => (v || "").replace(/\s+/g, "").toLowerCase().includes(q)))));
    const filtered = q || typeFilter || sector;
    document.getElementById("sk-count").textContent = filtered ? `${shown.length} / ${rows.length}곳` : `${rows.length}곳`;
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
      const c = contractOf(f);
      const contract = c
        ? `<span class="sk-sector ${c.sector === "관급" ? "gov" : "pri"}">${esc(c.sector)}</span> ${ymd(c.start_date)} ~ ${ymd(c.end_date)}` +
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
          <div class="sk-title">${f.mgmt_no ? `<span class="site-no">${esc(f.mgmt_no)}</span>` : ""}<b>${esc(f.name)}</b>
            <span class="sk-tpl t${esc(f.template)}">${esc(TEMPLATE_LABEL[f.template] || f.template)}</span></div>
          <div class="sk-sub">${esc([f.address, f.owner_name].filter(Boolean).join(" · "))}</div>
          <div class="sk-sub">${esc([f.fms_no, f.use_type || f.main_use, f.contact_name && `담당 ${f.contact_name}`].filter(Boolean).join(" · "))}</div>
        </div>
        <div class="sk-contract">${contract}${renew}</div>`;
      const links = siteLinkButtons(f.contact_phone || f.owner_phone, f.address); // [📞 전화] [📍 지도]
      if (links) row.querySelector(".sk-main").appendChild(links);
      row.appendChild(typeSwitch(f));
      list.appendChild(row);
    }
  }

  document.getElementById("sk-search").addEventListener("input", render);
  api("/sitok/facilities").then((r) => { rows = r; render(); }).catch((err) => showError(errorEl, err));
})();
