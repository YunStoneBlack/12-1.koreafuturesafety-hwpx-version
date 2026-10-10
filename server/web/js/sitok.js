// 보고서 자동화 · 시특법 — 시설물 목록(sitok.html, 2026-10-10). 서버 GET /sitok/facilities(server/api/routers/sitok.py).
// 줄을 누르면 sitok-facility.html?id= (시설물·계약 보기·고치기). 보고서 틀은 2종 / 3종 일반 / 3종 학교.

(function () {
  const errorEl = document.getElementById("error");
  const TEMPLATE_LABEL = { "2종": "2종", "3종일반": "3종 일반", "3종학교": "3종 학교" };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const money = (n) => (n ? `${Number(n).toLocaleString("ko-KR")}원` : "");
  const ymd = (s) => (s ? s.replaceAll("-", ".") : "?");
  let rows = [];

  function render() {
    const q = document.getElementById("sk-search").value.trim().toLowerCase();
    const shown = rows.filter((f) => !q || `${f.name} ${f.address} ${f.owner_name} ${f.fms_no}`.toLowerCase().includes(q));
    document.getElementById("sk-count").textContent = `${shown.length}곳`;
    const list = document.getElementById("sk-list");
    if (!rows.length) {
      list.innerHTML = '<div class="empty-note">아직 등록한 시설물이 없습니다. 오른쪽 위 [+ 시설물 등록]에서 시설물관리대장·계약서 PDF를 올리면 칸이 채워집니다.</div>';
      return;
    }
    list.innerHTML = shown.length ? shown.map((f) => {
      const c = f.latest;
      const contract = c
        ? `<span class="sk-sector ${c.sector === "관급" ? "gov" : "pri"}">${esc(c.sector)}</span> ${ymd(c.start_date)} ~ ${ymd(c.end_date)}` +
          `${c.amount ? ` · ${money(c.amount)}${c.sector === "민간" && c.halves === "연간" ? "(반기)" : ""}` : ""}`
        : '<span class="sk-none">계약 없음</span>';
      return `<a class="sk-row" href="sitok-facility.html?id=${f.id}">
        <div class="sk-name"><b>${esc(f.name)}</b><span class="sk-tpl t${esc(f.template)}">${esc(TEMPLATE_LABEL[f.template] || f.template)}</span>
          <small>${esc([f.fms_no, f.use_type || f.main_use].filter(Boolean).join(" · "))}</small></div>
        <div class="sk-where"><span>${esc(f.address)}</span><small>${esc(f.owner_name)}</small></div>
        <div class="sk-contract">${contract}</div>
      </a>`;
    }).join("") : '<div class="empty-note">검색에 맞는 시설물이 없습니다.</div>';
  }

  document.getElementById("sk-search").addEventListener("input", render);
  api("/sitok/facilities").then((r) => { rows = r; render(); }).catch((err) => showError(errorEl, err));
})();
