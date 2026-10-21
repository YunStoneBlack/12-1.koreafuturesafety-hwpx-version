// 내진성능평가 현장시험 — 철근탐사(sitok-seismic.html, 2026-10-21). 줄 = 시험 하나(RC-n).
// 층·부재·일람표 칸·위치·변 → 서버가 설계값(구조 일람표 부재 목록)을 채움, 두 줄마다 조사값·피복·실측불가·📷 탐사기 캡처(올리면 서버가 읽어 채움).
// 고치면 줄 전체를 PATCH(설계 칸을 직접 고치면 design_manual — 일람표로 다시 안 덮음). 서버 server/api/routers/sitok_seismic.py.

(function () {
  const rid = Number(new URLSearchParams(location.search).get("report")) || null;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const $ = (id) => document.getElementById(id);
  const errorEl = $("error");
  const URL_ = `/sitok/reports/${rid}/seismic`;
  const KINDS = ["기둥", "보", "벽체"];
  let d = null;
  let saving = null;

  const showErr = (m) => { errorEl.textContent = m || ""; errorEl.style.display = m ? "block" : "none"; };
  const floorLabel = (n) => (d.floors.find((f) => f.n === n) || {}).label || (n == null ? "층?" : n < 0 ? `지하${-n}층` : `지상${n}층`);

  function choices(row) {
    return d.schedule.items.filter((it) => it.kind === row.kind && (row.floor == null || !it.range || (it.range[0] <= row.floor && row.floor <= it.range[1])));
  }

  function line(row, i) {
    const lab = d.lines[row.kind][i];
    const isCount = i === 0 && row.kind !== "벽체";
    const bad = (row.mismatch || []).includes(i);
    const cap = row.captures[i];
    return `<div class="ss-line${row.unable[i] ? " off" : ""}${bad ? " bad" : ""}">
      <b class="ss-lab">${esc(lab)}</b>
      <div class="sk-f"><label>설계</label><input data-f="design" data-i="${i}" value="${esc(row.design[i])}" placeholder="${isCount ? "예: 5EA" : "예: @250"}" /></div>
      <div class="sk-f"><label>조사결과</label><input data-f="measured" data-i="${i}" value="${esc(row.measured[i])}" placeholder="${isCount ? "예: 5EA" : "예: @243"}"${row.unable[i] ? " disabled" : ""} /></div>
      <div class="sk-f ss-cover"><label>피복(mm)</label><input data-f="cover" data-i="${i}" type="number" inputmode="numeric" min="0" max="300" value="${row.cover[i] ?? ""}"${row.unable[i] ? " disabled" : ""} /></div>
      <label class="ss-unable"><input type="checkbox" data-f="unable" data-i="${i}"${row.unable[i] ? " checked" : ""} /> 실측불가</label>
      <label class="secondary-link ss-cap" title="탐사기 파형 그래프 화면 캡처 — 점 개수·간격·피복을 읽어 채움">📷 캡처<input type="file" accept="image/*" hidden data-kr-file="1" data-cap="${i}" /></label>
      ${cap ? `<a class="ss-thumb" href="${BASE}/api${URL_}/rebar/${row.id}/capture/${i}" target="_blank" rel="noopener" title="올린 캡처"><img loading="lazy" src="${BASE}/api${URL_}/rebar/${row.id}/capture/${i}?v=${encodeURIComponent(cap)}" alt="" /></a>` : ""}
      ${bad ? '<span class="ss-diff" title="설계와 다름 — 본문에 &quot;구조도면과 실측 상이&quot;로">≠ 설계</span>' : ""}</div>`;
  }

  function card(row) {
    const ch = choices(row);
    const sel = ch.find((c) => c.id === row.item_id);
    const opts = `<option value="">${ch.length ? "일람표 칸 고르기" : "맞는 일람표 칸 없음 — 부호 직접"}</option>` + ch.map((c) => `<option value="${c.id}"${c.id === row.item_id ? " selected" : ""}>${esc(c.marks.join(", "))}${c.position ? ` ${esc(c.position)}` : ""} (${esc(c.floors)})${c.confirmed ? "" : " ⚠미확인"}</option>`).join("");
    return `<div class="ss-card" data-id="${row.id}">
      <div class="ss-card-h"><b class="ss-no">RC-${row.no}</b><span class="sk-help">${esc(floorLabel(row.floor))} · ${esc(row.kind)}${row.mark ? ` (${esc(row.mark)})` : ""}</span>
        <button type="button" class="link-btn ss-del" title="이 시험 지우기">🗑</button></div>
      <div class="field-grid ss-pick">
        <div class="sk-f"><label>층</label><select data-f="floor"><option value="">층 고르기</option>${d.floors.map((f) => `<option value="${f.n}"${f.n === row.floor ? " selected" : ""}>${esc(f.label)}</option>`).join("")}</select></div>
        <div class="sk-f"><label>부재</label><select data-f="kind">${KINDS.map((k) => `<option${k === row.kind ? " selected" : ""}>${k}</option>`).join("")}</select></div>
        <div class="sk-f ss-wide"><label>일람표 칸 ${sel && !sel.confirmed ? '<a class="ss-warn-link" href="sitok-schedule.html?facility=' + d.report.facility_id + '" title="부재 목록에서 확인">⚠ 확인 안 한 칸</a>' : ""}</label><select data-f="item_id">${opts}</select></div>
        <div class="sk-f"><label>부호</label><input data-f="mark" value="${esc(row.mark)}" placeholder="예: C1" /></div>
        ${row.kind === "벽체" ? "" : `<div class="sk-f"><label>위치</label><select data-f="position">${["중앙부", "단부"].map((p) => `<option${p === row.position ? " selected" : ""}>${p}</option>`).join("")}</select></div>`}
        ${row.kind === "기둥" ? `<div class="sk-f"><label>잰 변</label><select data-f="side">${["단변", "장변"].map((p) => `<option${p === row.side ? " selected" : ""}>${p}</option>`).join("")}</select></div>` : ""}
      </div>
      <div class="ss-lines">${line(row, 0)}${line(row, 1)}</div>
      ${(row.warn || []).length ? `<div class="ss-warn">${row.warn.map((w) => `<div>⚠ ${esc(w)}</div>`).join("")}</div>` : ""}</div>`;
  }

  function drawTop() {
    const r = d.report;
    $("ss-fac-link").textContent = r.facility_name;
    $("ss-fac-link").href = `sitok-facility.html?id=${r.facility_id}`;
    $("ss-round-link").textContent = r.half === "성능평가" ? `${r.year}년 내진성능평가` : `${r.year}년 ${r.half}`;
    $("ss-round-link").href = `sitok-round.html?report=${rid}`;
    document.title = `현장시험 - ${r.facility_name}`;
    $("ss-count").textContent = d.rows.length ? `${d.rows.length}개소` : "";
    const s = d.schedule;
    $("ss-sched").innerHTML = s.count ? `📏 구조 일람표 ${s.count}칸${s.need ? ` — <b class="ss-need">확인 필요 ${s.need}칸</b>(기둥 단변·장변 점 개수 등)` : " — 모두 확인"}
        <a class="secondary-link" href="sitok-schedule.html?facility=${r.facility_id}">부재 목록 열기</a>`
      : `<div class="mail-msg bad">구조 일람표 부재 목록이 비었습니다 — <a href="sitok-schedule.html?facility=${r.facility_id}">부재 목록</a>에서 일람표를 읽으면 설계값이 자동으로 들어갑니다(없으면 설계 칸을 직접).</div>`;
    const q = d.counts;
    $("ss-qty").innerHTML = q.table.length ? `<table class="ss-qty-t"><thead><tr><th>층</th>${KINDS.map((k) => `<th>${k}</th>`).join("")}</tr></thead><tbody>
        ${q.table.map((t) => `<tr><td>${esc(t.label)}</td>${KINDS.map((k) => `<td class="${t[k] >= q.per ? "ok" : t[k] ? "part" : ""}">${t[k]}${t[k] >= q.per ? " ✓" : ` / ${q.per}`}</td>`).join("")}</tr>`).join("")}</tbody></table>
        <span class="sk-help">과업지시서: 도면이 있으면 조사단위(층)마다 부재 종별로 ${q.per}개소 이상</span>` : "";
    $("ss-xlsx").href = `${BASE}/api${URL_}/rebar.xlsx`;
    $("ss-xlsx").hidden = !d.rows.length;
  }

  function draw() {
    drawTop();
    $("ss-rows").innerHTML = d.rows.length ? `<section class="panel"><div class="panel-body ss-cards">${d.rows.map(card).join("")}</div></section>`
      : '<section class="panel"><div class="panel-body empty-note">아직 시험이 없습니다 — 위 [＋ 시험 추가]</div></section>';
    bind();
  }

  async function save(rows, keepFocus) {
    $("ss-saved").textContent = "저장 중…";
    try {
      d = await apiPatch(`${URL_}/rebar`, { rows });
      showErr("");
      $("ss-saved").textContent = "저장됨";
    } catch (e) { showErr(e.message); $("ss-saved").textContent = ""; return; }
    draw();
    if (keepFocus) {
      const el = document.querySelector(`.ss-card[data-id="${keepFocus.id}"] [data-f="${keepFocus.f}"]${keepFocus.i != null ? `[data-i="${keepFocus.i}"]` : ""}`);
      if (el) el.focus();
    }
  }

  function rowsCopy() { return d.rows.map((r) => JSON.parse(JSON.stringify(r))); }

  function bind() {
    document.querySelectorAll(".ss-card").forEach((el) => {
      const id = el.dataset.id;
      el.querySelectorAll("[data-f]").forEach((inp) => inp.addEventListener("change", () => {
        const rows = rowsCopy();
        const row = rows.find((x) => x.id === id);
        const f = inp.dataset.f, i = inp.dataset.i != null ? Number(inp.dataset.i) : null;
        if (f === "floor") { row.floor = inp.value === "" ? null : Number(inp.value); row.item_id = ""; row.design_manual = false; }
        else if (f === "kind") { row.kind = inp.value; row.item_id = ""; row.mark = ""; row.design = ["", ""]; row.measured = ["", ""]; row.design_manual = false; }
        else if (f === "item_id") { row.item_id = inp.value; row.design_manual = false; row.mark = ""; }
        else if (f === "position" || f === "side") { row[f] = inp.value; }
        else if (f === "mark") row.mark = inp.value.trim();
        else if (f === "design") { row.design[i] = inp.value.trim(); row.design_manual = true; }
        else if (f === "measured") row.measured[i] = inp.value.trim();
        else if (f === "cover") row.cover[i] = inp.value === "" ? null : Number(inp.value);
        else if (f === "unable") row.unable[i] = inp.checked;
        const next = document.activeElement && el.contains(document.activeElement) ? document.activeElement : null;
        save(rows, next && next !== inp ? { id, f: next.dataset.f, i: next.dataset.i } : null);
      }));
      el.querySelector(".ss-del").addEventListener("click", () => {
        if (!confirm("이 시험을 지울까요? 뒤 시험 번호가 하나씩 당겨집니다.")) return;
        save(rowsCopy().filter((x) => x.id !== id));
      });
      el.querySelectorAll("input[data-cap]").forEach((inp) => {
        const lab = inp.closest(".ss-cap");
        if (typeof enableFileDrop === "function") enableFileDrop(lab, inp); // 캡처 끌어다 놓기
        inp.addEventListener("change", async () => {
          if (!inp.files[0]) return;
          const i = Number(inp.dataset.cap);
          lab.firstChild.textContent = "📷 읽는 중…";
          const fd = new FormData();
          fd.append("file", inp.files[0]);
          try {
            d = await apiUpload(`${URL_}/rebar/${id}/capture/${i}`, fd);
            const g = d.read || {};
            $("ss-saved").textContent = `RC 캡처 읽음 — ${g.count ? `철근 ${g.count}개 ` : ""}${g.spacing ? `간격 @${g.spacing} ` : ""}${g.cover != null ? `피복 ${g.cover}` : ""}`;
            showErr("");
            draw();
          } catch (e) { showErr(e.message); lab.firstChild.textContent = "📷 캡처"; }
        });
      });
    });
  }

  $("ss-add").addEventListener("click", () => {
    const rows = rowsCopy();
    const last = rows[rows.length - 1];
    rows.push({ kind: last ? last.kind : "기둥", floor: last ? last.floor : (d.floors[0] || {}).n ?? null, position: "중앙부", side: "단변" }); // 앞 시험과 같은 층·부재로
    save(rows).then(() => { const cards = document.querySelectorAll(".ss-card"); const c = cards[cards.length - 1]; if (c) { c.scrollIntoView({ block: "center" }); c.querySelector('[data-f="item_id"]')?.focus(); } });
  });

  async function load() {
    try { d = await api(URL_); showErr(""); } catch (e) { showErr(e.message); return; }
    draw();
  }

  if (!rid) { showErr("회차가 지정되지 않았습니다 (?report=)"); return; }
  load();
})();
