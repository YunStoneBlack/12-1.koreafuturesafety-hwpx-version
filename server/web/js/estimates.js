// 통합 견적 목록(2026-10-29 사용자) — 새 견적(용역 8가지) · 목록(상태 칩·용역·찾기) · 기준표. 서버 server/api/routers/estimates.py.
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const won = (n) => (n == null || n === "" ? "-" : `${Math.round(Number(n)).toLocaleString("ko-KR")}원`);
  const errorEl = $("error");
  const ICON = { sitok_regular: "🏢", sitok_precision: "🔍", survey: "📏", blcm: "🏬", health_ledger: "📒", impl_check: "✅", tech_guide: "🦺", site_safety: "🚧" };
  const HINT = { sitok_regular: "시설물별 내역서(인·일 × 노임)", sitok_precision: "기계·기구손료 5% 포함", survey: "조사별 내역서", blcm: "지침 7장(연면적·경과년수·용도)",
    health_ledger: "업무·등급 × 인원 × 일수", impl_check: "회당 × 횟수(공사기간 ÷ 15일)", tech_guide: "공사금액 구간 · 횟수", site_safety: "항목 × 횟수 × 단가" };
  let meta = null, status = "", kind = "", q = "", timer = null;

  function drawKinds() {
    $("es-kinds").innerHTML = meta.kinds.map((k) => `<button type="button" class="es-kind" data-k="${k.key}"><span class="es-kind-i">${ICON[k.key] || "📄"}</span>
      <b>${esc(k.label)}</b><small>${esc(HINT[k.key] || "")}</small></button>`).join("");
    $("es-kinds").querySelectorAll(".es-kind").forEach((b) => b.addEventListener("click", async () => {
      b.disabled = true;
      try { const e = await apiPost("/estimates", { kind: b.dataset.k }); location.href = `estimate.html?id=${e.id}`; } catch (err) { showError(errorEl, err); b.disabled = false; }
    }));
    $("es-kind").innerHTML = '<option value="">용역 전체</option>' + meta.kinds.map((k) => `<option value="${k.key}">${esc(k.label)}</option>`).join("");
  }

  function card(x) {
    const el = document.createElement("div");
    el.className = "ds-card";
    el.innerHTML = `<div class="ds-card-main">
        <div class="ds-card-title"><span class="site-no">${esc(x.no)}</span><b>${esc(x.subject || x.client || "(이름 없음)")}</b><span class="ds-kind">${esc(x.kind_label)}</span>
          <span class="es-st ${esc(x.status)}">${esc(x.status_label)}</span></div>
        <div class="ds-card-sub">${esc(x.client || "발주처 없음")}${x.staff ? ` · 담당 ${esc(x.staff)}` : ""}</div>
        <div class="ds-card-meta"><b class="es-money">${won(x.total)}</b> (VAT 포함) · 견적일 ${esc(x.issued_on || "-")} · 수정 ${esc(x.updated)}</div>
      </div>
      <div class="ds-card-btns"><a class="secondary-link" href="estimate.html?id=${x.id}">📂 열기</a><button type="button" class="secondary es-copy">📋 복사</button></div>`;
    el.querySelector(".es-copy").addEventListener("click", async (ev) => {
      ev.currentTarget.disabled = true;
      try { const e = await apiPost(`/estimates/${x.id}/copy`, {}); location.href = `estimate.html?id=${e.id}`; } catch (err) { showError(errorEl, err); }
    });
    return el;
  }

  async function load() {
    try {
      const p = new URLSearchParams();
      if (status) p.set("status", status);
      if (kind) p.set("kind", kind);
      if (q) p.set("q", q);
      const d = await api(`/estimates?${p}`);
      const all = Object.values(d.counts).reduce((a, b) => a + b, 0);
      $("es-status").innerHTML = [["", "전체", all], ...Object.entries(meta.status).map(([k, v]) => [k, v, d.counts[k] || 0])]
        .map(([k, v, n]) => `<button type="button" class="es-chip${k === status ? " on" : ""}" data-s="${k}">${esc(v)} <small>${n}</small></button>`).join("");
      $("es-status").querySelectorAll(".es-chip").forEach((b) => b.addEventListener("click", () => { status = b.dataset.s; load(); }));
      $("es-count").textContent = `${d.estimates.length}건`;
      const box = $("es-list");
      box.innerHTML = "";
      if (!d.estimates.length) { box.innerHTML = '<div class="empty-note">견적이 없습니다 — 위에서 용역을 골라 시작하세요.</div>'; return; }
      d.estimates.forEach((x) => box.appendChild(card(x)));
    } catch (err) { showError(errorEl, err); }
  }
  $("es-kind").addEventListener("change", (e) => { kind = e.target.value; load(); });
  $("es-q").addEventListener("input", (e) => { clearTimeout(timer); timer = setTimeout(() => { q = e.target.value.trim(); load(); }, 300); });

  // ---------- 기준표 ----------
  let R = null, year = "";
  function drawRates() {
    const years = Object.keys(R.labor).sort().reverse();
    if (!year || !R.labor[year]) year = R.labor_year || years[0];
    const t = R.labor[year] || {};
    const missing = meta.grades.filter((g) => t[g] == null).length;
    $("es-rates").innerHTML = `<div class="bj-sec-t es-sec">엔지니어링 노임단가(건설, 원/일)</div>
      <div class="es-row"><label>연도 <select id="es-year">${years.map((y) => `<option${y === year ? " selected" : ""}>${y}</option>`).join("")}</select></label>
        <button type="button" class="secondary" id="es-year-add">＋ 연도 더하기</button>
        <label class="es-inline"><input type="radio" name="es-default" ${R.labor_year === year ? "checked" : ""} id="es-default" /> 새 견적에 이 연도 쓰기</label>
        ${missing ? `<span class="es-warn">⚠ 빈 등급 ${missing}개 — 한국엔지니어링협회 공표값을 넣으세요(지금은 0원으로 계산)</span>` : ""}</div>
      <div class="field-grid es-grid4">${meta.grades.map((g) => `<div class="sk-f"><label>${esc(g)}</label><input data-g="${esc(g)}" inputmode="numeric" value="${t[g] ?? ""}" placeholder="확인 필요" /></div>`).join("")}</div>
      <div class="bj-sec-t es-sec">기술지도·이행점검 회당 인건비(공사금액 구간)</div>
      <div class="es-bands">${R.visit_bands.map((b, i) => `<div class="es-band" data-i="${i}"><input data-b="label" value="${esc(b.label)}" placeholder="구간 이름" />
        <input data-b="under" inputmode="numeric" value="${b.under ?? ""}" placeholder="미만(원) — 끝 구간은 비움" /><input data-b="grade" value="${esc(b.grade)}" placeholder="등급" />
        <input data-b="rate" inputmode="numeric" value="${b.rate}" placeholder="원/일" /></div>`).join("")}</div>
      <div class="bj-sec-t es-sec">율·기타</div>
      <div class="field-grid es-grid4">
        <div class="sk-f"><label>제경비율(직접인건비 ×)</label><input id="es-oh" value="${R.overhead}" /></div>
        <div class="sk-f"><label>기술료율((인건비+제경비) ×)</label><input id="es-tech" value="${R.tech}" /></div>
        <div class="sk-f"><label>현지보조인부 노임(원/일)</label><input id="es-helper" value="${R.helper_rate}" /></div>
        <div class="sk-f"><label>기술지도 간격(일 — 공사기간 ÷)</label><input id="es-vdays" value="${R.visit_days}" /></div></div>
      <div class="ds-foot"><span class="mail-note" id="es-rates-msg"></span><button type="button" id="es-rates-save">저장</button></div>`;
    $("es-year").addEventListener("change", (e) => { readRates(); year = e.target.value; drawRates(); });
    $("es-year-add").addEventListener("click", () => {
      const y = prompt("더할 연도(예: 2027)", String(new Date().getFullYear() + 1));
      if (!y || !/^\d{4}$/.test(y.trim())) return;
      readRates();
      R.labor[y.trim()] = R.labor[y.trim()] || Object.fromEntries(meta.grades.map((g) => [g, null]));
      year = y.trim();
      drawRates();
    });
    $("es-rates-save").addEventListener("click", async (e) => {
      readRates();
      e.currentTarget.disabled = true;
      try { R = (await api("/estimates/rates", { method: "PUT", body: JSON.stringify(R) })).rates; meta.rates = R; drawRates(); $("es-rates-msg").textContent = "✓ 저장했습니다"; }
      catch (err) { $("es-rates-msg").textContent = err.message; e.currentTarget.disabled = false; }
    });
  }
  function readRates() {
    const box = $("es-rates");
    if (!box.querySelector("[data-g]")) return;
    const num = (v) => (String(v).trim() === "" ? null : Number(String(v).replace(/,/g, "")));
    R.labor[year] = Object.fromEntries([...box.querySelectorAll("[data-g]")].map((i) => [i.dataset.g, num(i.value)]));
    if ($("es-default").checked) R.labor_year = year;
    R.visit_bands = [...box.querySelectorAll(".es-band")].map((b) => {
      const v = (k) => b.querySelector(`[data-b="${k}"]`).value.trim();
      return { label: v("label"), under: num(v("under")), grade: v("grade"), rate: num(v("rate")) || 0 };
    });
    R.overhead = num($("es-oh").value); R.tech = num($("es-tech").value); R.helper_rate = num($("es-helper").value); R.visit_days = num($("es-vdays").value);
  }

  (async () => {
    try {
      meta = await api("/estimates/meta");
      R = meta.rates;
      drawKinds(); drawRates(); load();
      if (location.hash === "#rates") { $("es-rates-panel").open = true; $("es-rates-panel").scrollIntoView(); }  // 견적 화면 경고의 [기준표 열기]
    } catch (err) { showError(errorEl, err); }
  })();
})();
