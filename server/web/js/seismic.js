// 내진성능평가(seismic.html, 2026-10-21 사용자 "보고서 자동화 탭에 따로") — 왼쪽 메뉴 보고서 자동화 › 내진성능평가.
// [＋ 새 내진성능평가] 시설물 찾기·고르기 + 연도 → [만들고 회차 열기] = 회차 화면(sitok-round.html?seis=1).
// 목록 카드: 이름·연도·계약·진행(결함·일람표·철근탐사·외주 한글·보고서) + [📂 회차 열기] [PDF 보기]. 서버 GET /sitok/seismic/list.

(function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const errorEl = document.getElementById("error");
  const $ = (id) => document.getElementById(id);
  let facs = [];

  const say = (text, ok) => { const m = $("sv-msg"); m.hidden = !text; m.className = `mail-msg${ok ? "" : " bad"}`; m.textContent = text || ""; };
  const roundUrl = (id) => `sitok-round.html?report=${id}&one=1&seis=1`;

  function drawFacs() { // 찾기 글이 든 시설물만(이름·주소), 많으면 앞 80곳
    const q = $("sv-q").value.trim().replace(/\s+/g, "");
    const hit = facs.filter((f) => !q || `${f.name}${f.address}`.replace(/\s+/g, "").includes(q));
    const keep = $("sv-fac").value;
    const year = Number($("sv-year").value);
    $("sv-fac").innerHTML = (hit.length ? "" : '<option value="">찾는 시설물이 없습니다</option>')
      + hit.slice(0, 80).map((f) => `<option value="${f.id}"${String(f.id) === keep ? " selected" : ""}>${esc(f.name)}${f.years.includes(year) ? ` — ${year}년 있음` : ""}${f.address ? ` (${esc(f.address.split(" ").slice(0, 3).join(" "))})` : ""}</option>`).join("")
      + (hit.length > 80 ? `<option value="" disabled>… ${hit.length - 80}곳 더 — 더 찾아 보세요</option>` : "");
  }

  $("sv-q").addEventListener("input", drawFacs);
  $("sv-year").addEventListener("change", drawFacs);

  $("sv-create").addEventListener("click", async () => {
    const id = Number($("sv-fac").value);
    if (!id) { say("시설물을 고르세요."); $("sv-q").focus(); return; }
    $("sv-create").disabled = true;
    try {
      const r = await apiPost(`/sitok/facilities/${id}/reports`, { year: Number($("sv-year").value), kind: "성능평가", half: "성능평가" });
      location.href = roundUrl(r.id);
    } catch (e) { say(e.message); $("sv-create").disabled = false; }
  });

  function state(r) { // 보고서 칸 — 만듦·만드는 중·실패·아직
    if (r.status === "running") return '<span class="sk-rep-st run">⏳ 만드는 중</span>';
    if (r.status === "failed") return '<span class="sk-rep-st bad">✗ 만들기 실패</span>';
    if (r.has_pdf) return `<span class="ds-done">보고서 ${esc((r.made_at || "").slice(5, 10).replace("-", "/"))} 만듦</span>`;
    return "";
  }

  function card(r) {
    const s = r.seismic || {};
    const f = r.field || {};
    const vendor = (s.files || {}).body;
    const bits = [
      f.defects ? `결함 ${f.checked}/${f.defects} 확인` : "결함 아직",
      s.schedule ? `일람표 ${s.schedule}칸${s.schedule_need ? ` (확인 필요 ${s.schedule_need})` : ""}` : "일람표 아직",
      s.rebar ? `철근탐사 ${s.rebar}개소` : "철근탐사 아직",
      vendor ? "외주 한글 ✓" : "외주 한글 아직",
    ];
    const el = document.createElement("div");
    el.className = "ds-card";
    el.innerHTML = `<div class="ds-card-main">
        <div class="ds-card-title"><b>${esc(r.facility_name)}</b><span class="ds-kind">${r.year}년</span>${state(r)}</div>
        <div class="ds-card-sub">${esc(r.contract_title || "계약 없음")}${r.address ? ` · ${esc(r.address)}` : ""}</div>
        <div class="ds-card-meta">${bits.map(esc).join(" · ")}</div>
      </div>
      <div class="ds-card-btns">
        <a class="secondary-link" href="${roundUrl(r.id)}">📂 회차 열기</a>
        ${r.has_pdf ? `<a class="secondary-link" href="${BASE}/api/sitok/reports/${r.id}/file/pdf?v=${encodeURIComponent(r.made_at || "")}" target="_blank" rel="noopener">PDF 보기</a>` : ""}
      </div>`;
    return el;
  }

  async function load() {
    try {
      const d = await api("/sitok/seismic/list");
      facs = d.facilities;
      if (!$("sv-year").options.length) {
        $("sv-year").innerHTML = [d.year + 1, d.year, d.year - 1, d.year - 2].map((y) => `<option value="${y}"${y === d.year ? " selected" : ""}>${y}년</option>`).join("");
      }
      drawFacs();
      $("sv-count").textContent = d.reports.length ? `${d.reports.length}건` : "";
      const box = $("sv-list");
      box.innerHTML = d.reports.length ? "" : '<div class="ds-empty">아직 내진성능평가가 없습니다 — 위에서 시설물과 연도를 고르고 [만들고 회차 열기]를 누르세요. 서류 자동화에서 건명에 "성능평가"가 든 계약을 시설물에 연결해도 생깁니다.</div>';
      d.reports.forEach((r) => box.appendChild(card(r)));
    } catch (e) { showError(errorEl, e); }
  }

  load();
})();
