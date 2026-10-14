// 실적 탭(docs-performance.html, 2026-10-14 사용자 — 계약 기준 금액을 한눈에, 전년 동기 대비). 서버 /performance(server/api/routers/performance.py).
// 위 = 연도·구분 거르기·엑셀, 카드(올해 합계·시특법·산안법·전년 같은 기간 대비), 월별 막대(올해 파랑 #2A7DE1 · 작년 갈주황 #C2410C — dataviz 검증 통과), 계약 목록(1건 = 1줄, 반기 내역 펼침).

(function () {
  const errorEl = document.getElementById("error");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const won = (n) => `${Math.round(Number(n) || 0).toLocaleString()}원`;
  const man = (n) => { const v = Math.round((Number(n) || 0) / 10000); return v >= 10000 ? `${(v / 10000).toFixed(1)}억` : `${v.toLocaleString()}만`; };
  const ymd = (s) => (s || "").replaceAll("-", ".");
  const $ = (id) => document.getElementById(id);
  let data = null;
  let law = "";
  let year = Number(new URLSearchParams(location.search).get("year")) || new Date().getFullYear();

  function cards() {
    const s = data.summary;
    const diff = s.this.total - s.prev.total;
    const pct = s.prev.total ? Math.round((diff / s.prev.total) * 100) : null;
    const tone = pct === null ? "" : pct >= 0 ? "up" : "down";
    $("pf-cards").innerHTML = `
      <div class="pf-card"><span class="pf-k">${data.year}년 계약 합계</span><b class="pf-v">${man(s.this.total)}원</b><span class="pf-s">${won(s.this.total)} · ${s.this.count}건</span></div>
      <div class="pf-card"><span class="pf-k">시특법</span><b class="pf-v">${man(s.this.sitok)}원</b><span class="pf-s">${won(s.this.sitok)}</span></div>
      <div class="pf-card"><span class="pf-k">산안법 기술지도</span><b class="pf-v">${man(s.this.sanan)}원</b><span class="pf-s">${won(s.this.sanan)}</span></div>
      <div class="pf-card ${tone}"><span class="pf-k">전년 ${s.cutoff ? `같은 기간(~${ymd(s.cutoff).slice(5)})` : "전체"} 대비</span>
        <b class="pf-v">${pct === null ? "—" : `${pct >= 0 ? "▲" : "▼"} ${Math.abs(pct)}%`}</b>
        <span class="pf-s">${data.year - 1}년 ${s.cutoff ? "같은 기간" : ""} ${man(s.prev.total)}원${s.cutoff ? ` · ${data.year - 1}년 전체 ${man(s.prev_full.total)}원` : ""}</span></div>`;
  }

  // 월별 막대 — 올해·작년 두 묶음(SVG). 색은 dataviz 검증(#2A7DE1·#C2410C, CVD ΔE 29). 막대 위에 값은 최대 두 개(가장 큰 달)만, 나머지는 hover 툴팁.
  function chart() {
    const m = data.monthly;
    const vals = [...m.this, ...m.prev];
    const max = Math.max(...vals, 1);
    const W = 760, H = 220, L = 54, B = 28, T = 16;
    const bw = (W - L - 16) / 12;
    const yv = (v) => T + (H - T - B) * (1 - v / max);
    const rows = [];
    const top = [...m.this.map((v, i) => [v, i])].sort((a, b) => b[0] - a[0]).slice(0, 2).filter(([v]) => v > 0).map(([, i]) => i);
    for (let i = 0; i < 12; i++) {
      const x = L + i * bw;
      const h1 = H - B - yv(m.this[i]), h2 = H - B - yv(m.prev[i]);
      rows.push(`<g class="pf-bar" data-i="${i}">
        <rect x="${x + 6}" y="${yv(m.prev[i])}" width="${bw / 2 - 8}" height="${h2}" rx="3" fill="#C2410C" opacity=".85"><title>${data.year - 1}년 ${i + 1}월 ${won(m.prev[i])}</title></rect>
        <rect x="${x + bw / 2 + 2}" y="${yv(m.this[i])}" width="${bw / 2 - 8}" height="${h1}" rx="3" fill="#2A7DE1"><title>${data.year}년 ${i + 1}월 ${won(m.this[i])}</title></rect>
        ${top.includes(i) ? `<text x="${x + bw / 2 + 2 + (bw / 2 - 8) / 2}" y="${yv(m.this[i]) - 4}" text-anchor="middle" class="pf-val">${man(m.this[i])}</text>` : ""}
        <text x="${x + bw / 2}" y="${H - 8}" text-anchor="middle" class="pf-ax">${i + 1}월</text></g>`);
    }
    const grid = [0, 0.5, 1].map((f) => `<line x1="${L}" x2="${W - 10}" y1="${yv(max * f)}" y2="${yv(max * f)}" class="pf-grid" /><text x="${L - 6}" y="${yv(max * f) + 4}" text-anchor="end" class="pf-ax">${man(max * f)}</text>`).join("");
    $("pf-chart").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${data.year}년과 ${data.year - 1}년 월별 계약금액">${grid}${rows.join("")}</svg>
      <div class="pf-legend"><span><i style="background:#2A7DE1"></i>${data.year}년</span><span><i style="background:#C2410C"></i>${data.year - 1}년</span></div>`;
    $("pf-chart-note").textContent = `계약일(민간 반기는 반기 시작일) 기준 · 값 표시는 올해 큰 달 두 곳, 나머지는 막대에 마우스`;
  }

  function list() {
    const rows = data.rows.filter((r) => !law || r.law === law);
    $("pf-count").textContent = `${rows.length}건 · ${won(rows.reduce((a, r) => a + r.amount, 0))}`;
    if (!rows.length) { $("pf-list").innerHTML = '<div class="empty-note">이 해에 계약이 없습니다.</div>'; return; }
    $("pf-list").innerHTML = `<div class="pf-head"><span>번호</span><span>구분</span><span>용역명 · 발주처</span><span class="r">${data.year}년 금액</span><span class="r">계약 총액</span><span>계약일 · 기간</span></div>`
      + rows.map((r) => `<div class="pf-row">
        <span class="pf-no">${esc(r.no) || "-"}</span>
        <span class="pf-kind ${r.law === "시특법" ? "sitok" : "sanan"}">${esc(r.kind)}</span>
        <span class="pf-name"><a href="${esc(r.link)}">${esc(r.title)}</a><small>${esc([r.client, r.facility && r.facility !== r.title ? r.facility : ""].filter(Boolean).join(" · "))}</small>
          ${r.halves.length > 1 ? `<small class="pf-halves">${r.halves.map((h) => `${esc(h.label)} ${man(h.amount)}`).join(" · ")}</small>` : ""}</span>
        <span class="r pf-amt">${won(r.amount)}</span>
        <span class="r pf-total">${r.total !== r.amount ? won(r.total) : ""}</span>
        <span class="pf-date"><small>${ymd(r.date) || "-"}</small><small>${ymd(r.start)} ~ ${ymd(r.end)}</small></span></div>`).join("");
  }

  function draw() {
    const sel = $("pf-year");
    sel.innerHTML = data.years.map((y) => `<option value="${y}"${y === data.year ? " selected" : ""}>${y}년</option>`).join("");
    $("pf-xlsx").href = `${BASE}/api/performance/xlsx?year=${data.year}`;
    cards();
    chart();
    list();
  }

  async function load() {
    try { data = await api(`/performance?year=${year}`); draw(); } catch (e) { showError(errorEl, e); }
  }
  $("pf-year").addEventListener("change", (e) => { year = Number(e.target.value); load(); });
  document.querySelectorAll(".pf-law button").forEach((b) => b.addEventListener("click", () => {
    law = b.dataset.law;
    document.querySelectorAll(".pf-law button").forEach((x) => x.classList.toggle("on", x === b));
    list();
  }));
  load();
})();
