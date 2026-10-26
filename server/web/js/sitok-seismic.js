// 내진성능평가 현장시험 — 철근탐사(sitok-seismic.html, 2026-10-21). 줄 = 시험 하나(RC-n).
// 층·부재·일람표 칸·위치·변 → 서버가 설계값(구조 일람표 부재 목록)을 채움, 두 줄마다 조사값·피복·실측불가·📷 탐사기 캡처(올리면 서버가 읽어 채움).
// 고치면 줄 전체를 PATCH(설계 칸을 직접 고치면 design_manual — 일람표로 다시 안 덮음). 서버 server/api/routers/sitok_seismic.py.

(function () {
  const rid = Number(new URLSearchParams(location.search).get("report")) || null;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const $ = (id) => document.getElementById(id);
  const errorEl = $("error");
  const URL_ = `/sitok/reports/${rid}/seismic`;
  const JOINT = "보-기둥 접합부"; // 종별 항목만 따로, 조사는 보 단부(10/22 형)
  let KINDS = ["보", "기둥", JOINT, "벽체"];
  const hasResult = (r) => r.measured.some((x) => x) || r.unable.some((x) => x) || r.captures.some((x) => x);
  let d = null;
  let saving = null;
  let sFloor = ""; // 보이는 층(""= 전체) — 폰에서 길어 층만 골라 보기(10/25 민재형·사용자 "철탐 규격 동일 적용")
  try { sFloor = sessionStorage.getItem(`ss-mf-${rid}`) || ""; } catch (_) { /* */ }

  const showErr = (m) => { errorEl.textContent = m || ""; errorEl.style.display = m ? "block" : "none"; };
  const floorLabel = (n) => (d.floors.find((f) => f.n === n) || {}).label || (n == null ? "층?" : n < 0 ? `지하${-n}층` : `지상${n}층`);

  function choices(row) {
    const sk = row.kind === JOINT ? "보" : row.kind; // 접합부 = 보 단부 칸
    return d.schedule.items.filter((it) => it.kind === sk && !(row.kind === JOINT && /중앙/.test(it.position || ""))
      && (row.floor == null || !it.range || (it.range[0] <= row.floor && row.floor <= it.range[1])));
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
      ${cap ? `<span class="ss-thumb-w"><a class="ss-thumb" href="${BASE}/api${URL_}/rebar/${row.id}/capture/${i}" target="_blank" rel="noopener" title="올린 캡처"><img loading="lazy" src="${BASE}/api${URL_}/rebar/${row.id}/capture/${i}?v=${encodeURIComponent(cap)}" alt="" /></a>
        <button type="button" class="ss-cap-del" data-capdel="${i}" title="캡처 지우기">✕</button></span>` : ""}
      ${bad ? '<span class="ss-diff" title="설계와 다름 — 본문에 &quot;구조도면과 실측 상이&quot;로">≠ 설계</span>' : ""}</div>`;
  }

  function card(row) {
    const ch = choices(row);
    const sel = ch.find((c) => c.id === row.item_id);
    const opts = `<option value="">${ch.length ? "일람표 칸 고르기" : "맞는 일람표 칸 없음 — 부호 직접"}</option>` + ch.map((c) => `<option value="${c.id}"${c.id === row.item_id ? " selected" : ""}>${esc(c.marks.join(", "))}${c.position ? ` ${esc(c.position)}` : ""}${c.floors ? ` (${esc(c.floors)})` : ""}${c.confirmed ? "" : " ⚠미확인"}</option>`).join("");
    return `<div class="ss-card${hasResult(row) ? " filled" : " empty"}" data-id="${row.id}" data-floor="${row.floor ?? ""}" data-kind="${esc(row.kind)}">
      <div class="ss-card-h"><b class="ss-no">RC-${row.no}</b><span class="sk-help">${esc(floorLabel(row.floor))} · ${esc(row.kind)}${row.mark ? ` (${esc(row.mark)})` : ""}</span>
        ${blankCard(row) ? "" : '<button type="button" class="link-btn ss-del" title="이 카드 내용 비우기 — 칸은 그대로(칸 수는 위 칸 수 표에서)">비우기</button>'}</div>
      <div class="field-grid ss-pick">
        <div class="sk-f"><label>층</label><select data-f="floor"><option value="">층 고르기</option>${d.floors.map((f) => `<option value="${f.n}"${f.n === row.floor ? " selected" : ""}>${esc(f.label)}</option>`).join("")}</select></div>
        <div class="sk-f"><label>부재</label><select data-f="kind">${KINDS.map((k) => `<option${k === row.kind ? " selected" : ""}>${k}</option>`).join("")}</select></div>
        <div class="sk-f ss-wide"><label>일람표 칸 ${sel && !sel.confirmed ? '<a class="ss-warn-link" href="sitok-schedule.html?facility=' + d.report.facility_id + '" title="부재 목록에서 확인">⚠ 확인 안 한 칸</a>' : ""}</label><select data-f="item_id">${opts}</select></div>
        <div class="sk-f"><label>부호</label><input data-f="mark" value="${esc(row.mark)}" placeholder="예: C1" /></div>
        ${row.kind === "벽체" ? "" : row.kind === JOINT ? '<div class="sk-f"><label>위치</label><div class="ss-fixed">보 단부로 조사</div></div>' : `<div class="sk-f"><label>위치</label><select data-f="position">${["중앙부", "단부"].map((p) => `<option${p === row.position ? " selected" : ""}>${p}</option>`).join("")}</select></div>`}
        ${row.kind === "기둥" ? `<div class="sk-f"><label>잰 변</label><select data-f="side">${["단변", "장변"].map((p) => `<option${p === row.side ? " selected" : ""}>${p}</option>`).join("")}</select></div>` : ""}
      </div>
      <div class="ss-lines">${line(row, 0)}${line(row, 1)}</div>
      ${(row.warn || []).length ? `<div class="ss-warn">${row.warn.map((w) => `<div>⚠ ${esc(w)}</div>`).join("")}</div>` : ""}</div>`;
  }

  function drawTop() {
    const r = d.report;
    $("ss-fac-link").textContent = r.facility_name;
    $("ss-fac-link").href = `seismic-project.html?facility=${r.facility_id}`; // 내진성능평가 건 화면(10/21 — 시특법과 별개)
    $("ss-round-link").textContent = r.half === "성능평가" ? `${r.year}년 내진성능평가` : `${r.year}년 ${r.half}`;
    $("ss-round-link").href = `seismic-project.html?id=${rid}`;
    document.title = `현장시험 - ${r.facility_name}`;
    $("ss-count").textContent = d.rows.length ? `${d.counts.total}/${d.counts.slots_total}개소` : "";
    const s = d.schedule;
    $("ss-sched").innerHTML = s.count ? `📏 구조 일람표 ${s.count}칸${s.need ? ` — <b class="ss-need">확인 필요 ${s.need}칸</b>(기둥 단변·장변 점 개수 등)` : " — 모두 확인"}
        <a class="secondary-link" href="sitok-schedule.html?facility=${r.facility_id}">부재 목록 열기</a>`
      : `<div class="mail-msg bad">구조 일람표 부재 목록이 비었습니다 — <a href="sitok-schedule.html?facility=${r.facility_id}">부재 목록</a>에서 일람표를 읽으면 설계값이 자동으로 들어갑니다(없으면 설계 칸을 직접).</div>`;
    const q = d.counts;
    // 층 × 종별 칸 수 표 — 숫자를 고치면 카드가 늘고 줆(쓴 카드는 안 지움, 10/22 형 "표본층 종별마다 칸 생성, 수량 조정")
    $("ss-qty").innerHTML = q.table.length ? `<table class="ss-qty-t"><thead><tr><th>층</th>${KINDS.map((k) => `<th>${k === JOINT ? "보-기둥<br>접합부" : k}</th>`).join("")}</tr></thead><tbody>
        ${q.table.map((t) => `<tr><td><button type="button" class="sf2-fname${String(t.floor) === sFloor ? " on" : ""}" data-mf="${t.floor}" title="이 층만 보기">${esc(t.label)}</button></td>${KINDS.map((k) => { const dn = t.done[k] || 0, sl = t.slots[k] || 0;
          return `<td class="${sl && dn >= sl ? "ok" : dn ? "part" : ""}"><span>${dn}/</span><input type="number" min="0" max="40" inputmode="numeric" data-q="${t.floor}|${k}" value="${sl}" title="${esc(t.label)} ${esc(k)} 칸 수" /></td>`; }).join("")}</tr>`).join("")}</tbody></table>
        <div class="ss-qty-side"><span class="sk-help">결과/칸 — 매뉴얼 <표 3-1>: 조사단위(층)마다 보·기둥·보-기둥 접합부·벽체 ${q.per}개소 이상(접합부는 보 단부로 조사).
        숫자를 고치면 카드가 늘고 줆, 결과 없는 카드는 보고서에서 빠짐.</span><button type="button" class="secondary" id="ss-q-reset">기본 칸 수로</button></div>` : "";
    $("ss-qty").querySelectorAll("[data-q]").forEach((el) => el.addEventListener("change", () => qtyChange(el.dataset.q, Math.max(0, Math.min(40, Number(el.value) || 0)))));
    $("ss-q-reset")?.addEventListener("click", () => { if (confirm("층마다 종별 3칸으로 맞출까요? 쓴 카드는 그대로 둡니다.")) planSave({ default: true }); });
    $("ss-xlsx").href = `${BASE}/api${URL_}/rebar.xlsx`;
    $("ss-xlsx").hidden = !d.rows.length;
  }

  function draw() {
    const table = d.counts.table || [];
    if (sFloor && !table.some((t) => String(t.floor) === sFloor)) sFloor = "";
    drawTop();
    let prev;
    const byFloor = Object.fromEntries(table.map((t) => [t.floor, t]));
    const sum = (t, key) => KINDS.reduce((a, k) => a + (t[key][k] || 0), 0);
    const chips = table.length > 1 ? floorChips(table.map((t) => ({ n: t.floor, label: t.label, done: sum(t, "done"), total: sum(t, "slots") })), sFloor) : ""; // 층만 보기(app.js)
    const cur = byFloor[sFloor === "" ? NaN : Number(sFloor)];
    const kinds = `<div class="ss-kchips"><span class="sk-help">${cur ? esc(cur.label) : "보는 층"}</span>${KINDS.map((k) => `<button type="button" data-kj="${esc(k)}">${k === JOINT ? "보-기둥 접합부" : esc(k)}${cur
      ? ` <small class="${(cur.slots[k] || 0) && (cur.done[k] || 0) >= (cur.slots[k] || 0) ? "ok" : ""}">${cur.done[k] || 0}/${cur.slots[k] || 0}</small>` : ""}</button>`).join("")}</div>`;
    const nav = `<div class="ss-nav">${chips}${kinds}</div>`; // 위에 고정 — 층·부재 바로가기(10/25 민재형)
    const cards = d.rows.filter((r) => !sFloor || String(r.floor) === sFloor).map((r) => {
      let h = "";
      if (r.floor !== prev) {
        const t = byFloor[r.floor];
        const dn = t ? KINDS.reduce((a, k) => a + (t.done[k] || 0), 0) : 0, sl = t ? KINDS.reduce((a, k) => a + (t.slots[k] || 0), 0) : 0;
        h = `<h4 class="ss-floor">${esc(floorLabel(r.floor))}${t ? ` <span class="sk-help">${dn}/${sl}</span>` : ""}</h4>`;
      }
      prev = r.floor;
      return h + card(r);
    }).join("");
    $("ss-rows").innerHTML = d.rows.length ? `<section class="panel ss-rows-panel"><div class="panel-body ss-cards">${nav}${cards || '<div class="empty-note">이 층에는 시험 카드가 없습니다.</div>'}</div>
        <div class="ss-foot"><span class="sp-saved" id="ss-saved2"></span><span class="sk-help">고치는 대로 자동 저장됩니다</span><button type="button" id="ss-save">저장</button></div></section>`
      : '<section class="panel"><div class="panel-body empty-note">아직 시험 칸이 없습니다 — 위 칸 수 표에서 칸을 늘리세요</div></section>';
    bind();
    $("ss-save")?.addEventListener("click", saveAll);
    document.querySelectorAll("#ss-rows [data-mf], #ss-qty [data-mf]").forEach((b) => b.addEventListener("click", () => { // 층 단추·칸 수 표 층 이름 → 그 층만(표 층 이름을 다시 누르면 전체)
      sFloor = b.dataset.mf === sFloor && b.classList.contains("sf2-fname") ? "" : b.dataset.mf;
      try { sessionStorage.setItem(`ss-mf-${rid}`, sFloor); } catch (_) { /* */ }
      draw();
      document.querySelector("#ss-rows .ss-cards")?.scrollIntoView({ block: "start", behavior: "smooth" });
    }));
    document.querySelectorAll("#ss-rows [data-kj]").forEach((b) => b.addEventListener("click", () => jumpKind(b.dataset.kj)));
    const row = document.querySelector("#ss-rows .ss-nav .sf2-fchips"), on = row?.querySelector("button.on"); // 폰 — 한 줄로 밀리는 층 줄에서 고른 층이 보이게
    if (row && on && row.scrollWidth > row.clientWidth) row.scrollLeft = Math.max(0, on.offsetLeft - row.offsetLeft - (row.clientWidth - on.offsetWidth) / 2);
  }

  // 층·부재 바꾸기(10/26 민재형 "전체수량변경은 수량목록에서만, 보를 기둥으로 바꾸면 위치만 바꾸고 전체 수량은 그대로") —
  // 바꾼 카드와 같은 층·그 부재의 첫 빈 카드가 자리를 맞바꿈(1~3 보·4~6 기둥에서 2번을 기둥으로 → 2번 내용은 4번 자리, 4번 빈 카드는 2번 자리 보), 칸 수 표 그대로.
  // 그 부재 빈 카드가 없으면 안내(이미 쓴 카드를 다른 부재로 바꾸지 않게). 빈 카드를 바꾸면 그 부재 빈 카드로 데려다 줌.
  const blankCard = (r) => !(r.item_id || r.mark || r.note || r.design_manual || hasResult(r) || r.cover.some((x) => x != null));
  const asKind = (r, k) => { // 부재가 바뀐 카드 — 일람표 칸·부호·설계는 다시, 조사값은 벽체가 끼면 다시(줄 뜻이 다름: 벽체 = 수직·수평 간격)
    const out = { ...r, kind: k, item_id: "", mark: "", design: ["", ""], design_manual: false };
    if (r.kind === "벽체" || k === "벽체") out.measured = ["", ""];
    return out;
  };
  function flashCard(id) {
    const target = document.querySelector(`#ss-rows .ss-card[data-id="${id}"]`);
    if (!target) return;
    const navBottom = document.querySelector("#ss-rows .ss-nav")?.getBoundingClientRect().bottom || 0;
    window.scrollTo({ top: window.scrollY + target.getBoundingClientRect().top - navBottom - 8, behavior: "smooth" });
    target.classList.add("ss-flash");
    setTimeout(() => target.classList.remove("ss-flash"), 1500);
  }
  function moveCard(rows, row, f, val) {
    const nf = f === "floor" ? (val === "" ? null : Number(val)) : row.floor, nk = f === "kind" ? val : row.kind;
    const i = rows.indexOf(row), j = rows.findIndex((x) => x !== row && x.floor === nf && x.kind === nk && blankCard(x));
    if (j < 0) { draw(); showErr(`${floorLabel(nf)} ${nk} 칸이 다 찼습니다(빈 카드 없음) — 위 칸 수 표에서 ${nk} 칸을 늘린 뒤 바꾸세요.`); return; }
    showErr("");
    if (sFloor && String(nf) !== sFloor) { sFloor = String(nf); try { sessionStorage.setItem(`ss-mf-${rid}`, sFloor); } catch (_) { /* */ } } // 다른 층으로 — 그 층을 보여 줌
    if (blankCard(row)) { draw(); flashCard(rows[j].id); return; }
    const other = rows[j];
    const moved = f === "floor" ? { ...row, floor: nf, item_id: "", design_manual: false } : asKind(row, nk); // 층이 바뀌면 그 층 일람표 칸을 다시
    rows[i] = { ...other, floor: row.floor, kind: row.kind }; // 빈 카드는 바꾼 카드의 원래 층·부재로(서버가 위치·변 기본값)
    rows[j] = moved;
    save(rows).then((ok) => { if (ok) flashCard(moved.id); });
  }

  // 칸 수 표 — 늘리면 빈 카드 더함, 줄이면 고르기 창: 다른 부재로 옮기기(층 합계 그대로 — 쓴 카드면 내용도 같이) 또는 그냥 줄이기(빈 카드만)
  async function qtyChange(key, v) {
    const q = d.counts, [fs, k] = key.split("|"), fl = Number(fs);
    const plan = Object.fromEntries(q.table.flatMap((t) => KINDS.map((x) => [`${t.floor}|${x}`, t.slots[x] || 0])));
    const cur = plan[key] || 0;
    if (v >= cur) { plan[key] = v; planSave({ plan }); return; }
    const mine = d.rows.filter((r) => r.floor === fl && r.kind === k);
    const dn = cur - v, empty = mine.filter(blankCard).length, used = Math.max(0, dn - empty);
    const sum = KINDS.reduce((a, x) => a + (plan[`${fl}|${x}`] || 0), 0);
    const name = (x) => (x === JOINT ? "보-기둥 접합부" : x);
    const pick = await pickSheet({
      title: `${floorLabel(fl)} ${name(k)} ${cur} → ${v}칸`,
      sub: used ? `${name(k)} 카드 ${used}장은 쓴 내용이 있습니다 — 다른 부재로 옮기면 내용도 같이 옮겨집니다(일람표 칸·설계는 다시)` : "줄인 칸을 다른 부재로 옮기면 층 합계가 그대로입니다",
      options: [...KINDS.filter((x) => x !== k).map((x) => { const m = plan[`${fl}|${x}`] || 0; return { v: x, label: `${withRo(name(x))} 옮기기`, note: `${name(x)} ${m} → ${m + dn}칸 · 층 합계 ${sum}칸 그대로` }; }),
        { v: "", label: "그냥 줄이기", note: used ? "쓴 카드가 있어 못 줄입니다" : `층 합계 ${sum} → ${sum - dn}칸`, disabled: used > 0 }],
    });
    if (pick == null) { draw(); return; }
    if (!pick) { plan[key] = v; planSave({ plan }); return; }
    const rows = rowsCopy(), ids = new Set();
    const pool = rows.filter((r) => r.floor === fl && r.kind === k);
    for (const r of [...pool].reverse()) if (ids.size < dn && blankCard(r)) ids.add(r.id); // 빈 카드부터(뒤에서)
    for (const r of [...pool].reverse()) if (ids.size < dn) ids.add(r.id); // 모자라면 쓴 카드도(뒤에서)
    const next = rows.map((r) => (ids.has(r.id) ? (blankCard(r) ? { ...r, kind: pick } : asKind(r, pick)) : r));
    plan[key] = v;
    plan[`${fl}|${pick}`] = (plan[`${fl}|${pick}`] || 0) + dn;
    if (await save(next)) planSave({ plan }); // 부재를 바꿔 저장한 뒤 칸 수대로 차례 맞춤(층·부재 순)
  }

  // 부재 바로가기 — 층만 보는 중이면 그 층, 전체 보기면 지금 화면 맨 위에 보이는 카드의 층에서 그 부재 첫 카드로(10/25 민재형)
  function jumpKind(kind) {
    const cards = [...document.querySelectorAll("#ss-rows .ss-card")];
    if (!cards.length) return;
    let floor = sFloor;
    if (floor === "") {
      const navBottom = document.querySelector("#ss-rows .ss-nav")?.getBoundingClientRect().bottom || 0;
      const seen = cards.find((c) => c.getBoundingClientRect().bottom > navBottom + 4) || cards[0];
      floor = seen.dataset.floor;
    }
    const target = cards.find((c) => c.dataset.floor === floor && c.dataset.kind === kind);
    if (!target) { showErr(`이 층에는 ${kind} 카드가 없습니다 — 위 칸 수 표에서 칸을 늘리세요.`); setTimeout(() => showErr(""), 2500); return; }
    const navBottom = document.querySelector("#ss-rows .ss-nav")?.getBoundingClientRect().bottom || 0; // 고정 줄 높이가 폰에선 여러 줄 — 그만큼 아래로
    window.scrollTo({ top: window.scrollY + target.getBoundingClientRect().top - navBottom - 8, behavior: "smooth" });
    target.classList.add("ss-flash");
    setTimeout(() => target.classList.remove("ss-flash"), 1200);
  }

  // [저장](10/22 형 "기분상 저장 버튼 하나") — 자동 저장은 그대로. 쓰던 칸을 마저 저장(blur → change)하고, 그 저장이 끝난 뒤 전체를 한 번 더
  async function saveAll() {
    const btn = $("ss-save");
    if (btn) btn.disabled = true;
    document.activeElement?.blur?.();
    await new Promise((r) => setTimeout(r, 0));
    if (saving) await saving;
    const ok = await save(rowsCopy());
    const t = new Date();
    if (ok && $("ss-saved2")) $("ss-saved2").textContent = `✓ 저장했습니다 ${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}`;
    if ($("ss-save")) $("ss-save").disabled = false;
  }

  async function save(rows, keepFocus) { // 저장 중인 것을 saving에 — [저장]이 끝나길 기다림
    const run = saveNow(rows, keepFocus);
    saving = run;
    const ok = await run;
    if (saving === run) saving = null;
    return ok;
  }

  async function saveNow(rows, keepFocus) {
    $("ss-saved").textContent = "저장 중…";
    try {
      d = await apiPatch(`${URL_}/rebar`, { rows });
      showErr("");
      $("ss-saved").textContent = "저장됨";
    } catch (e) { showErr(e.message); $("ss-saved").textContent = ""; return false; }
    draw();
    if (keepFocus) {
      const el = document.querySelector(`.ss-card[data-id="${keepFocus.id}"] [data-f="${keepFocus.f}"]${keepFocus.i != null ? `[data-i="${keepFocus.i}"]` : ""}`);
      if (el) el.focus();
    }
    return true;
  }

  function rowsCopy() { return d.rows.map((r) => JSON.parse(JSON.stringify(r))); }

  function bind() {
    document.querySelectorAll(".ss-card").forEach((el) => {
      const id = el.dataset.id;
      el.querySelectorAll('select[data-f="item_id"]').forEach((sel) => searchSelect(sel, { placeholder: "일람표 칸 고르기 — 부호·위치로 검색" })); // 검색 고르기(app.js, 10/22)
      el.querySelectorAll("[data-f]").forEach((inp) => inp.addEventListener("change", () => {
        const rows = rowsCopy();
        const row = rows.find((x) => x.id === id);
        const f = inp.dataset.f, i = inp.dataset.i != null ? Number(inp.dataset.i) : null;
        if (f === "floor" || f === "kind") { moveCard(rows, row, f, inp.value); return; } // 칸 수 그대로 — 같은 층·부재 빈 카드와 자리 바꿈(10/26)
        if (f === "item_id") { row.item_id = inp.value; row.design_manual = false; row.mark = ""; }
        else if (f === "position" || f === "side") { row[f] = inp.value; }
        else if (f === "mark") row.mark = inp.value.trim();
        else if (f === "design") { row.design[i] = inp.value.trim(); row.design_manual = true; }
        else if (f === "measured") row.measured[i] = inp.value.trim();
        else if (f === "cover") row.cover[i] = inp.value === "" ? null : Number(inp.value);
        else if (f === "unable") row.unable[i] = inp.checked;
        const next = document.activeElement && el.contains(document.activeElement) ? document.activeElement : null;
        save(rows, next && next !== inp ? { id, f: next.dataset.f, i: next.dataset.i } : null);
      }));
      el.querySelector(".ss-del")?.addEventListener("click", async () => { // 비우기(10/26 — 전체 수량은 칸 수 표에서만, 카드 지우기·시험 추가 없앰)
        const no = el.querySelector(".ss-no")?.textContent || "";
        if (!confirm(`${no} 카드 내용을 비울까요? 일람표 칸·설계·조사값·피복·캡처가 지워지고 칸(번호)은 그대로 남습니다.`)) return;
        if (saving) await saving;
        try { d = await apiPost(`${URL_}/rebar/${id}/clear`, {}); showErr(""); $("ss-saved").textContent = `${no} 비움`; draw(); } catch (e) { showErr(e.message); }
      });
      el.querySelectorAll("[data-capdel]").forEach((btn) => btn.addEventListener("click", async () => {
        // 캡처 지우기(10/22) — 읽어 넣은 조사값·피복은 그대로
        if (!confirm("이 캡처를 지울까요? 캡처에서 읽어 넣은 조사값·피복은 그대로 둡니다(필요하면 직접 고치세요).")) return;
        try { d = await api(`${URL_}/rebar/${id}/capture/${btn.dataset.capdel}`, { method: "DELETE" }); showErr(""); $("ss-saved").textContent = "캡처 지움"; draw(); }
        catch (e) { showErr(e.message); }
      }));
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

  async function planSave(body) {
    $("ss-saved").textContent = "칸 맞추는 중…";
    try { d = await apiPost(`${URL_}/rebar/plan`, body); KINDS = d.kinds || KINDS; showErr(""); $("ss-saved").textContent = "저장됨"; } catch (e) { showErr(e.message); $("ss-saved").textContent = ""; return; }
    draw();
  }

  async function load() {
    try { d = await api(URL_); KINDS = d.kinds || KINDS; showErr(""); } catch (e) { showErr(e.message); return; }
    if (!d.seeded) { await planSave({ default: true }); return; } // 처음 열면 표본 층 × 4종 × 3 카드를 깔아 둠(쓴 카드는 그대로)
    draw();
  }

  if (!rid) { showErr("회차가 지정되지 않았습니다 (?report=)"); return; }
  load();
})();
