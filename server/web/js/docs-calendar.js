// ---------- 서류 자동화 — 착수·완수 일정 달력(docs-calendar.html, 2026-10-06) ----------
// 계약마다 착수계 기한·완수계 기한 날에 한 칸씩(파랑 = 착수계, 보라 = 완수계). 제출했으면 ✓, 미제출인데 지났으면 빨강. 누르면 그 창.
// PC = 월 달력, 폰 = 그 달 날짜별 목록(같은 자료, css/docs.css가 바꿔 보임). 기한 규칙은 서버 contract_status.due_dates(임시).

(function () {
  const errorEl = document.getElementById("error");
  const WEEK = ["일", "월", "화", "수", "목", "금", "토"];
  let contracts = [];
  const now = new Date();
  let ym = { y: now.getFullYear(), m: now.getMonth() };

  async function load() {
    try {
      contracts = (await dcLoad()).contracts;
      render();
    } catch (err) {
      showError(errorEl, err);
    }
  }

  const pad = (n) => String(n).padStart(2, "0");
  const iso = (y, m, d) => `${y}-${pad(m + 1)}-${pad(d)}`;

  function eventsByDay() {
    const map = {};
    for (const c of contracts) {
      for (const [k, label] of DC_KINDS) {
        const day = c.due[k];
        if (!day) continue;
        (map[day] ||= []).push({ c, k, label, s: dcDocState(c, k) });
      }
    }
    return map;
  }

  function chip(e) {
    return `<button type="button" class="dk-ev ${e.k} ${e.s.cls}" data-id="${e.c.id}" data-kind="${e.k}" title="${mailEsc(`${e.label} · ${e.c.title} — ${e.s.text}`)}">
      ${e.s.cls === "ok" ? "✓ " : ""}<b>${e.label}</b> ${mailEsc(e.c.title || "(용역명 없음)")}</button>`;
  }

  function render() {
    document.getElementById("dk-month").textContent = `${ym.y}년 ${ym.m + 1}월`;
    const map = eventsByDay();
    const first = new Date(ym.y, ym.m, 1);
    const days = new Date(ym.y, ym.m + 1, 0).getDate();
    const today = iso(now.getFullYear(), now.getMonth(), now.getDate());
    let cells = WEEK.map((w, i) => `<div class="dk-wd${i === 0 ? " sun" : i === 6 ? " sat" : ""}">${w}</div>`).join("");
    for (let i = 0; i < first.getDay(); i++) cells += '<div class="dk-day empty"></div>';
    const listParts = [];
    for (let d = 1; d <= days; d++) {
      const key = iso(ym.y, ym.m, d);
      const evs = map[key] || [];
      const wd = new Date(ym.y, ym.m, d).getDay();
      cells += `<div class="dk-day${key === today ? " today" : ""}${wd === 0 ? " sun" : wd === 6 ? " sat" : ""}"><span class="dk-n">${d}</span>${evs.map(chip).join("")}</div>`;
      if (evs.length) listParts.push(`<div class="dk-lday${key === today ? " today" : ""}"><div class="dk-ldate">${ym.m + 1}/${d} (${WEEK[wd]})</div>${evs.map(chip).join("")}</div>`);
    }
    document.getElementById("dk-grid").innerHTML = cells;
    document.getElementById("dk-list").innerHTML = listParts.join("") || '<div class="empty-note">이 달엔 착수·완수 기한이 없습니다.</div>';
    document.querySelectorAll(".dk-ev").forEach((b) => b.addEventListener("click", () => openContractDocs(Number(b.dataset.id), b.dataset.kind, load)));
  }

  const move = (n) => { const d = new Date(ym.y, ym.m + n, 1); ym = { y: d.getFullYear(), m: d.getMonth() }; render(); };
  document.getElementById("dk-prev").addEventListener("click", () => move(-1));
  document.getElementById("dk-next").addEventListener("click", () => move(1));
  document.getElementById("dk-today").addEventListener("click", () => { ym = { y: now.getFullYear(), m: now.getMonth() }; render(); });

  load();
})();
