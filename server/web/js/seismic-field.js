// 내진성능평가 현장조사 입력(seismic-field.html?id=회차, 2026-10-21 사용자) — 부재 단면·코어·조적조 줄, 현장 사진 칸, 분석 글.
// 칸마다 [저장] = PATCH /seismic/projects/{id}/field {그 칸만}. 사진 = POST/DELETE …/field/photo/{slot}. 코어 [🤖 성적서에서 읽기] = POST …/field/cores/read.

(function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const errorEl = document.getElementById("error");
  const $ = (id) => document.getElementById(id);
  const id = Number(new URLSearchParams(location.search).get("id")) || 0;
  // ?part=texts = 보고서 AI 작성(분석 글만, 10/27 형 "분석 글 밖으로 따로") — 아니면 현장조사 입력(부재 단면·철근탐사·코어·조적조, 분석 글 숨김)
  const TEXTS = new URLSearchParams(location.search).get("part") === "texts";
  for (const pid of ["sf2-m-panel", "sf2-r-panel", "sf2-c-panel", "sf2-w-panel", "sf2-min", "sf2-min-help"]) { const el = document.getElementById(pid); if (el) el.hidden = TEXTS; }
  { const t = document.getElementById("sf2-t-panel"); if (t) { t.hidden = !TEXTS; t.open = TEXTS; } }
  let F = null;
  let cores = [];
  const err = (e) => showError(errorEl, e);
  const flash = (el, text) => { el.textContent = text; setTimeout(() => { if (el.textContent === text) el.textContent = ""; }, 3500); };
  const opt = (list, v) => list.map(([val, label]) => `<option value="${esc(val)}"${String(val) === String(v ?? "") ? " selected" : ""}>${esc(label)}</option>`).join("");

  // 줄 편집기 — cols: [키, 이름, 너비, 종류(text|number|select), 고르기 목록]
  function rows(box, list, cols, blank, onChange) {
    const draw = () => {
      box.innerHTML = `<div class="sf2-row sf2-row-h"><span class="sf2-no">#</span>${cols.map(([, label, w]) => `<span style="flex:${w}">${esc(label)}</span>`).join("")}<span class="sp-x-sp"></span></div>`
        + list.map((r, i) => `<div class="sf2-row"><span class="sf2-no">${i + 1}</span>${cols.map(([k, label, w, type, choices]) => {
          const c = typeof choices === "function" ? choices(r) : choices;
          return type === "select"
            ? `<select data-i="${i}" data-k="${k}" title="${esc(label)}" style="flex:${w}">${opt(c, r[k])}</select>`
            : `<input data-i="${i}" data-k="${k}" type="${type || "text"}" ${type === "number" ? 'step="any" inputmode="decimal"' : ""} placeholder="${esc(label)}" title="${esc(label)}" style="flex:${w}" value="${esc(r[k] ?? "")}" />`;
        }).join("")}<button type="button" class="sp-x" data-rm="${i}" title="줄 지우기">✕</button></div>`).join("")
        + `<button type="button" class="secondary sp-add">＋ 줄</button>`;
      box.querySelectorAll("[data-k]").forEach((el) => el.addEventListener(el.tagName === "SELECT" ? "change" : "input", () => {
        const r = list[el.dataset.i];
        r[el.dataset.k] = el.value;
        if (onChange && onChange(r, el.dataset.k)) draw();
      }));
      box.querySelectorAll("[data-rm]").forEach((b) => b.addEventListener("click", () => { list.splice(Number(b.dataset.rm), 1); draw(); }));
      box.querySelector(".sp-add").addEventListener("click", () => { const last = list[list.length - 1]; list.push({ ...blank, ...(last ? { floor: last.floor, kind: last.kind } : {}) }); draw(); });
    };
    draw();
  }

  // 부재 단면 — 표본 층 × 종별 칸을 미리 깔고(위 수량 표에서 늘리고 줄임), 일람표 칸은 그 층·그 부재 것만(철근탐사처럼) — 10/22 형.
  // 빈 칸은 저장 안 함(보고서엔 채운 줄만), 칸 수는 member_plan, 층별 칸 차례(1 보·2 기둥·3 보처럼 섞임 — 10/26)는 member_order로 저장.
  let plan = {}, slots = {}; // slots = {층: [줄…]} 화면 차례, 줄마다 kind
  const gkey = (n, k) => `${n}|${k}`;
  const filledM = (x) => !!(x.mark || x.design || x.measured || x.note); // 위치는 셈 안 함(10/27 위치 칸 없앰 — 예전에 위치만 적은 칸이 입력한 칸으로 셈)
  const blankM = (n, k) => ({ floor: n, kind: k, where: "", item_id: "", mark: "", design: "", measured: "", note: "" });
  const floorName = (n) => (F.floors.find((f) => f.n === n) || {}).label || (n < 0 ? `지하${-n}층` : `지상${n}층`);
  const itemsFor = (r) => F.schedule.filter((x) => x.kind === r.kind && (!x.range || (x.range[0] <= r.floor && r.floor <= x.range[1])));
  function memberFloors() {
    const s = new Set([...F.sample_floors, ...Object.keys(plan).map((k) => Number(k.split("|")[0])), ...Object.keys(slots).map(Number)]);
    return [...s].filter((n) => n).sort((a, b) => a - b);
  }
  function drawMembers() {
    plan = { ...F.member_plan };
    slots = {};
    const mem = {};
    for (const m of F.members) (mem[m.floor] ||= []).push({ ...m });
    const order = F.member_order || {};
    for (const n of new Set([...Object.keys(mem), ...Object.keys(order)].map(Number))) {
      const o = order[String(n)], ms = mem[n] || [];
      if (Array.isArray(o) && o.filter((x) => x.endsWith("*")).length === ms.length) { // 저장한 칸 차례 — 쓴 칸(*)은 members 차례대로
        const q = [...ms], out = [];
        const ok = o.every((x) => { const k = x.replace("*", ""); if (!x.endsWith("*")) { out.push(blankM(n, k)); return true; } const m = q.shift(); out.push(m); return m && m.kind === k; });
        if (ok) { slots[n] = out; continue; }
      }
      slots[n] = F.member_kinds.flatMap((k) => ms.filter((m) => m.kind === k)); // 차례가 없으면 예전처럼 부재 차례(빈 칸은 renderMembers가)
    }
    renderMembers();
  }
  // 실측치수 — 일치/불일치/일부 일치(10/22 민재형): 일치 = 도면치수 그대로, 불일치·일부 일치 = 두 칸(벽체는 THK 한 칸), 못 재면 □
  const matchOf = (r) => r.match || (r.measured ? (r.measured === r.design ? "일치" : "불일치") : "");
  // 비고 = 자동(10/27 형 "비고는 일치/일부일치/불일치 — 자동으로 작성되는 칸") — 실측치수에서 고른 값, 안 골랐으면 치수 비교(서버 seismic_fill.member_note와 같은 규칙)
  function sizeMatch(d, s) {
    const a = String(d || "").match(/[0-9]+|□/g) || [], b = String(s || "").match(/[0-9]+|□/g) || [];
    if (!a.length || a.length !== b.length) return "";
    const same = a.map((x, i) => [x, b[i]]).filter(([x, y]) => x !== "□" && y !== "□").map(([x, y]) => x === y);
    if (!same.length) return "";
    if (same.every(Boolean) && same.length === a.length) return "일치";
    return same.some(Boolean) ? "일부일치" : "불일치";
  }
  const autoNote = (r) => String(r.match || "").replace(/ /g, "") || sizeMatch(r.design, r.measured);
  const refreshAuto = (el, r) => { const a = el.closest(".sf2-row")?.querySelector(".sf2-auto b"); if (a) a.textContent = autoNote(r); };
  function sides(r, kind) {
    const m = String(r.measured || "");
    if (kind === "벽체") return [(m.match(/THK\s*=\s*(\S+)/i) || [, m.replace(/[^\d.□]/g, "")])[1] || ""];
    const x = m.match(/^\s*(\S*)\s*x\s*(\S*)\s*$/);
    return x ? [x[1], x[2]] : [m, ""];
  }
  function joinSides(v, kind) {
    if (kind === "벽체") return v[0] ? `THK=${v[0]}` : "";
    return v[0] || v[1] ? `${v[0]} x ${v[1]}` : "";
  }
  function measuredCell(key, j, r, kind) {
    const mt = matchOf(r);
    const sel = `<select data-g="${key}" data-j="${j}" data-k="match" title="실측치수" class="sf2-match">${opt([["", "실측 —"], ["일치", "일치"], ["불일치", "불일치"], ["일부 일치", "일부 일치"]], mt)}</select>`;
    if (mt === "일치") return `<span class="sf2-meas">${sel}<span class="sf2-same">${esc(r.design || "도면치수 없음")}</span></span>`;
    if (!mt) return `<span class="sf2-meas">${sel}</span>`;
    const v = sides(r, kind);
    const box = (i, ph) => `<span class="sf2-side"><input data-g="${key}" data-j="${j}" data-side="${i}" placeholder="${ph}" value="${esc(v[i] || "")}" inputmode="decimal" />`
      + `<button type="button" class="sf2-sq${v[i] === "□" ? " on" : ""}" data-g="${key}" data-j="${j}" data-sq="${i}" title="못 잼(□)">□</button></span>`;
    return `<span class="sf2-meas">${sel}${kind === "벽체" ? box(0, "THK") : `${box(0, "가로")}<i>x</i>${box(1, "세로")}`}</span>`;
  }

  let mFloor = ""; // 부재 단면 보이는 층(""= 전체) — 폰에서 길어 층만 골라 보기(10/25 민재형)
  try { mFloor = sessionStorage.getItem(`sf2-mf-${id}`) || ""; } catch (_) { /* */ }
  const ofKind = (n, k) => (slots[n] || []).filter((x) => x.kind === k);
  const syncPlan = (n) => { for (const k of F.member_kinds) plan[gkey(n, k)] = ofKind(n, k).length; }; // 칸 수 = 칸 차례에서 셈
  // 그 부재 칸 끼우는 자리 — 같은 부재 마지막 칸 뒤, 없으면 부재 차례(보·기둥·벽체)상 앞 부재 마지막 칸 뒤, 그것도 없으면 맨 앞
  function insertAt(n, k) {
    const s = slots[n], ord = F.member_kinds.indexOf(k);
    let at = -1;
    s.forEach((x, i) => { if (x.kind === k) at = i; });
    if (at < 0) s.forEach((x, i) => { if (F.member_kinds.indexOf(x.kind) <= ord) at = i; });
    return at + 1;
  }
  function renderMembers() {
    const floors = memberFloors(), kinds = F.member_kinds;
    if (mFloor && !floors.some((n) => String(n) === mFloor)) mFloor = "";
    for (const n of floors) { // 칸 수 맞추기 — 채운 줄은 안 지움
      const s = (slots[n] ||= []);
      for (const k of kinds) {
        const want = Math.max(plan[gkey(n, k)] ?? 0, ofKind(n, k).filter(filledM).length);
        while (ofKind(n, k).length < want) s.splice(insertAt(n, k), 0, blankM(n, k));
        for (let i = s.length - 1; i >= 0 && ofKind(n, k).length > want; i -= 1) if (s[i].kind === k && !filledM(s[i])) s.splice(i, 1);
      }
    }
    const cnt = (n, k) => ofKind(n, k).filter(filledM).length;
    let no = 0;
    const row = (n, r, j) => {
      no += 1;
      const k = r.kind, ch = itemsFor(r), nth = (slots[n] || []).slice(0, j + 1).filter((x) => x.kind === k).length; // 그 부재 몇 번째
      const opts = [["", ch.length ? "— 일람표 칸 —" : "맞는 칸 없음 — 직접"], ...ch.map((x) => [x.id, `${x.marks.join(",")}${x.size ? ` ${x.size}` : ""}${x.floors ? ` (${x.floors})` : ""}`])];
      const inp = (f, label, w) => `<input data-g="${n}" data-j="${j}" data-k="${f}" placeholder="${esc(label)}" title="${esc(label)}" style="flex:${w}" value="${esc(r[f] ?? "")}" />`;
      const kindSel = `<select class="sf2-mkind" data-g="${n}" data-j="${j}" data-mk="1" title="부재 — 바꾸면 이 칸은 그 부재로, 같은 층 그 부재 빈 칸 하나는 이 칸의 원래 부재로(칸 수 그대로)">${opt(kinds.map((x) => [x, x]), k)}</select>`;
      return `<div class="sf2-row${filledM(r) ? "" : " empty"}"><span class="sf2-no">${no}</span><span class="sf2-mk">${kindSel}<i>${nth}</i></span>
        <select data-g="${n}" data-j="${j}" data-k="item_id" title="일람표 칸" style="flex:1.5">${opt(opts, r.item_id)}</select>
        ${inp("mark", "부호", 0.7)}${inp("design", "도면치수", 1)}${measuredCell(n, j, r, k)}<span class="sf2-auto" style="flex:0.9" title="비고 — 실측치수에서 자동(일치·일부일치·불일치)"><i>비고</i><b>${esc(autoNote(r))}</b></span></div>`; // 위치 칸 없앰(10/27 형 — 보고서 조사위치 = 층만)
    };
    $("sf2-members").innerHTML = `<div class="sf2-qty"><table class="sf2-qty-t"><thead><tr><th>층</th>${kinds.map((k) => `<th>${esc(k)}</th>`).join("")}</tr></thead><tbody>
        ${floors.map((n) => `<tr><td><button type="button" class="sf2-fname${String(n) === mFloor ? " on" : ""}" data-mf="${n}" title="이 층만 보기">${esc(floorName(n))}</button></td>${kinds.map((k) => { const c = cnt(n, k), want = ofKind(n, k).length;
          return `<td class="${want && c >= want ? "ok" : c ? "part" : ""}"><span>${c}/</span><input type="number" min="0" max="40" inputmode="numeric" data-q="${gkey(n, k)}" value="${want}" title="${esc(floorName(n))} ${esc(k)} 칸 수" /></td>`; }).join("")}</tr>`).join("")}
        </tbody></table><div class="sf2-qty-side"><span class="sk-help">칸 수(입력/칸) — 표본 층 × 종별 ${F.drawings ? 3 : 9}개소가 기본, 숫자를 고치면 아래 칸이 늘고 줆(줄이면 다른 부재로 옮기거나 빈 칸만 줄이기)</span>
        <button type="button" class="secondary" id="sf2-q-reset">기본 칸 수로</button></div></div>
      <div class="sf2-mnote" id="sf2-mnote"></div>
      <div class="sf2-row sf2-row-h"><span class="sf2-no">#</span><span class="sf2-mk">부재</span><span style="flex:1.5">일람표 칸(그 층·부재만)</span><span style="flex:0.7">부호</span><span style="flex:1">도면치수</span><span class="sf2-meas-h">실측치수(일치·불일치, 못 재면 □)</span><span style="flex:0.9">비고(자동)</span></div>
      ${floorChips(floors.map((n) => ({ n, label: floorName(n), done: (slots[n] || []).filter(filledM).length, total: (slots[n] || []).length })), mFloor)}
      ${floors.map((n) => { const rs = (slots[n] || []).map((r, j) => row(n, r, j)); const c = (slots[n] || []).filter(filledM).length;
        return rs.length && (!mFloor || String(n) === mFloor) ? `<div class="sf2-mfloor"><h4>${esc(floorName(n))} <span class="sk-help" data-fc="${n}">${c}/${rs.length}</span></h4>${rs.join("")}</div>` : ""; }).join("")}`;  // 번호는 전체 차례 그대로(다른 층도 세고 안 그림)
    const box = $("sf2-members");
    box.querySelectorAll("[data-mf]").forEach((b) => b.addEventListener("click", () => { // 층 단추·칸 수 표 층 이름 → 그 층만, [전체 보기] → 전부
      mFloor = b.dataset.mf === mFloor && b.classList.contains("sf2-fname") ? "" : b.dataset.mf;
      try { sessionStorage.setItem(`sf2-mf-${id}`, mFloor); } catch (_) { /* */ }
      renderMembers();
      $("sf2-members").querySelector(".sf2-fchips")?.scrollIntoView({ block: "start", behavior: "smooth" });
    }));
    box.querySelectorAll('select[data-k="item_id"]').forEach((sel) => searchSelect(sel, { placeholder: "일람표 칸 — 부호·치수로 검색" })); // 검색 고르기(app.js, 10/22)
    box.querySelectorAll("[data-q]").forEach((el) => el.addEventListener("change", () => qtyChange(el.dataset.q, Math.max(0, Math.min(40, Number(el.value) || 0)))));
    box.querySelectorAll("select[data-mk]").forEach((el) => el.addEventListener("change", () => moveKind(Number(el.dataset.g), Number(el.dataset.j), el.value)));
    box.querySelector("#sf2-q-reset").addEventListener("click", () => { plan = { ...F.member_plan_default }; renderMembers(); });
    const rowOf = (el) => slots[el.dataset.g][Number(el.dataset.j)];
    box.querySelectorAll("[data-g][data-k]").forEach((el) => el.addEventListener(el.tagName === "SELECT" ? "change" : "input", () => {
      const r = rowOf(el);
      r[el.dataset.k] = el.value;
      if (el.dataset.k === "item_id") {
        const it = F.schedule.find((x) => x.id === r.item_id);
        if (it) { r.mark = it.marks[0] || r.mark; r.design = (it.size || "").replace(/\s*[xX×*]\s*/, " x "); }
        if (r.match === "일치") r.measured = r.design;
        renderMembers();
      } else if (el.dataset.k === "match") {
        r.measured = r.match === "일치" || r.match === "일부 일치" ? r.design || "" : ""; // 일부 일치는 도면치수를 두 칸에 미리
        renderMembers();
      } else {
        if (el.dataset.k === "design" && r.match === "일치") r.measured = r.design;
        refreshAuto(el, r);
        el.closest(".sf2-row").classList.toggle("empty", !filledM(r)); memberCounts();
      }
    }));
    box.querySelectorAll("input[data-side]").forEach((el) => el.addEventListener("input", () => { // 두 칸 → "가로 x 세로"(벽체 THK=)
      const r = rowOf(el), v = sides(r, r.kind);
      v[Number(el.dataset.side)] = el.value.trim();
      r.measured = joinSides(v, r.kind);
      refreshAuto(el, r);
      el.closest(".sf2-row").classList.toggle("empty", !filledM(r)); memberCounts();
    }));
    box.querySelectorAll("button[data-sq]").forEach((el) => el.addEventListener("click", () => { // □ = 못 잼(다시 누르면 지움)
      const r = rowOf(el), v = sides(r, r.kind), i = Number(el.dataset.sq);
      v[i] = v[i] === "□" ? "" : "□";
      r.measured = joinSides(v, r.kind);
      renderMembers();
    }));
    memberCounts();
  }
  // 부재 바꾸기(10/26 민재형 "RC-1 보를 기둥으로 바꾸면 RC-1이 기둥으로 바뀌고 RC-4가 보로 — 1번 보 2번 기둥 3번 보 4번 벽체처럼 자유롭게") —
  // 이 칸은 제자리에서 그 부재로, 같은 층 그 부재의 첫 빈 칸 하나가 이 칸의 원래 부재로(칸 수 표 그대로). 그 부재 빈 칸이 없으면 안내(이미 쓴 칸을 다른 부재로 바꾸지 않게).
  const mnote = (t) => { const el = $("sf2-mnote"); if (el) el.textContent = t || ""; };
  const dataM = (x) => !!(x.item_id || x.mark || x.design || x.measured || x.note); // 조사 내용이 있는 칸 — 위치만 적은 칸(예: 모든 칸 "장비 위치도 참조.")은 빈 칸으로 봄
  const kindChanged = (r, k2) => {
    if (!dataM(r)) return { ...r, kind: k2 }; // 빈 칸(위치만) — 부재만
    const out = { ...r, kind: k2, item_id: "", mark: "", design: "" }; // 일람표 칸·부호·도면치수는 부재마다 — 위치·비고는 그대로
    if (r.match === "일치" || r.kind === "벽체" || k2 === "벽체") { out.measured = ""; out.match = ""; } // 일치(= 도면치수)·벽체 THK는 다시
    return out;
  };
  const noOf = (n, j) => memberFloors().filter((x) => x < n).reduce((a, x) => a + (slots[x] || []).length, 0) + j + 1; // 화면 번호(전체 차례)
  function flashRow(n, j) {
    const el = $("sf2-members").querySelector(`select[data-mk][data-g="${n}"][data-j="${j}"]`)?.closest(".sf2-row");
    if (!el) return;
    el.scrollIntoView({ block: "center", behavior: "smooth" });
    el.classList.add("sf2-flash");
    setTimeout(() => el.classList.remove("sf2-flash"), 1500);
  }
  function moveKind(n, j, k2) {
    const s = slots[n], r = s[j], k = r.kind;
    if (k === k2) return;
    const e = s.findIndex((x, i) => i !== j && x.kind === k2 && !dataM(x));
    if (e < 0) { renderMembers(); mnote(`${floorName(n)} ${k2} 빈 칸이 없습니다 — 위 칸 수 표에서 ${k2} 칸을 늘린 뒤 바꾸세요`); return; }
    s[j] = kindChanged(r, k2);
    s[e] = { ...s[e], kind: k }; // 빈 칸(위치 글은 그대로)
    renderMembers();
    mnote(`${noOf(n, j)}번 → ${k2}, ${noOf(n, e)}번 → ${k}(칸 수 그대로) — [저장]`);
    flashRow(n, j);
  }
  // 칸 수 표 — 늘리면 빈 칸 더함, 줄이면 고르기 창: 다른 부재로 옮기기(그 칸들이 제자리에서 그 부재로 — 층 합계 그대로, 쓴 칸이면 내용도) 또는 그냥 줄이기(빈 칸만)
  // (10/26 민재형 "최소수량 아래로도 — 벽체 1 빼면 기둥 1 올라가기, 전체 9개는 유지")
  async function qtyChange(key, v) {
    const [ns, k] = key.split("|"), n = Number(ns), s = (slots[n] ||= []), cur = ofKind(n, k).length;
    if (v >= cur) { plan[key] = v; renderMembers(); return; }
    const d = cur - v, empty = ofKind(n, k).filter((x) => !dataM(x)).length, used = Math.max(0, d - empty);
    const sum = s.length;
    const pick = await pickSheet({
      title: `${floorName(n)} ${k} ${cur} → ${v}칸`,
      sub: used ? `${k} 칸 ${used}개는 쓴 내용이 있습니다 — 다른 부재로 옮기면 그 칸이 제자리에서 그 부재로 바뀝니다(일람표 칸·도면치수는 다시)` : "줄인 칸을 다른 부재로 옮기면 층 합계가 그대로입니다",
      options: [...F.member_kinds.filter((x) => x !== k).map((x) => { const m = ofKind(n, x).length; return { v: x, label: `${withRo(x)} 옮기기`, note: `${x} ${m} → ${m + d}칸 · 층 합계 ${sum}칸 그대로` }; }),
        { v: "", label: "그냥 줄이기", note: used ? "쓴 칸이 있어 못 줄입니다" : `층 합계 ${sum} → ${sum - d}칸`, disabled: used > 0 }],
    });
    if (pick == null) { renderMembers(); return; }
    const idx = [];
    for (let i = s.length - 1; i >= 0 && idx.length < d; i -= 1) if (s[i].kind === k && !dataM(s[i])) idx.push(i); // 빈 칸부터(뒤에서)
    for (let i = s.length - 1; i >= 0 && idx.length < d && pick; i -= 1) if (s[i].kind === k && !idx.includes(i)) idx.push(i); // 모자라면 쓴 칸도(뒤에서)
    if (pick) idx.forEach((i) => { s[i] = kindChanged(s[i], pick); });
    else idx.sort((a, b) => b - a).forEach((i) => s.splice(i, 1));
    syncPlan(n);
    renderMembers();
    mnote(pick ? `${floorName(n)} ${k} ${d}칸을 ${withRo(pick)} 바꿨습니다(층 합계 그대로) — [저장]` : "");
  }

  // 입력 수 — 위 요약·수량 표 "입력/"·층 머리(글 쓸 때마다, 다시 그리지 않고)
  function memberCounts() {
    const floors = memberFloors(), kinds = F.member_kinds;
    let done = 0, total = 0;
    for (const n of floors) {
      for (const k of kinds) {
        const g = ofKind(n, k), ck = g.filter(filledM).length;
        const td = $("sf2-members").querySelector(`input[data-q="${gkey(n, k)}"]`)?.closest("td");
        if (td) { td.className = g.length && ck >= g.length ? "ok" : ck ? "part" : ""; td.querySelector("span").textContent = `${ck}/`; }
      }
      const c = (slots[n] || []).filter(filledM).length, t = (slots[n] || []).length;
      const h = $("sf2-members").querySelector(`[data-fc="${n}"]`);
      if (h) h.textContent = `${c}/${t}`;
      const chip = $("sf2-members").querySelector(`[data-fcc="${n}"]`);
      if (chip) chip.textContent = `${c}/${t}`;
      done += c; total += t;
    }
    $("sf2-m-sum").textContent = `${done}/${total}칸 입력 (최소 ${F.min_counts.member}) — 2.2.1 부재 단면 치수 조사 결과, 일람표 칸을 고르면 도면치수`;
  }
  function membersOut() { // 보고서 줄 = 쓴 칸만, 칸 차례대로
    return memberFloors().flatMap((n) => (slots[n] || []).filter(filledM).map((x) => ({ ...x, floor: n })));
  }
  function orderOut() { // 층별 칸 차례(* = 쓴 칸) — 다시 열어도 1 보·2 기둥·3 보 그대로
    return Object.fromEntries(memberFloors().filter((n) => (slots[n] || []).length).map((n) => [String(n), slots[n].map((x) => x.kind + (filledM(x) ? "*" : ""))]));
  }

  function drawCores() {
    cores = F.cores.map((x) => ({ ...x }));
    rows($("sf2-cores"), cores, [["name", "구분(예: 4층-벽체-1)", 2], ["mpa", "압축강도 (MPa)", 1, "number"]], {});
    const s = F.core_stats;
    $("sf2-c-stats").innerHTML = s.n ? `<b>${s.n}개</b> · 평균(m) <b>${s.mean}</b> MPa · 표준편차(s) ${s.std} · 최소 ${s.min} · 최대 ${s.max}` : "";
    $("sf2-c-note").textContent = F.core_note || (F.has_core_report ? "" : "건 화면 서류 칸에 성적서를 올리면 읽을 수 있습니다");
    $("sf2-c-read").disabled = !F.has_core_report;
    $("sf2-c-design").value = F.core_design ?? "";
    $("sf2-c-sum").textContent = `${F.cores.length}개 (최소 ${F.min_counts.core})${s.n ? ` · 평균 ${s.mean}MPa` : ""} — 2.2.3·2.2.4`;
  }

  // 조적조 — ① 조적 목록(F-n 채움벽·P-n 허리벽: 크기·두께·방향·노출·마감·경계면·적용) ② 층마다 칸(기본 2)에서 목록 부재를 고르면 그 값(10/22 민재형
  // "층마다 F-1이 같은 값은 아니지만 효율을 위해 같은 사이즈와 방향·상태인 것으로 조적 리스트를 만들고 선택해서 자동 입력"). 목록을 고치면 저장 때 고른 칸도 그 값으로.
  let mtypes = [], mplan = {}, mgroups = {};
  const MCOLS = [["mid", "부재ID", 0.7], ["kind", "구분", 0.9, [["채움벽", "채움벽"], ["허리벽", "허리벽"]]], ["height", "순높이(mm)", 0.9, "number"], ["width", "순너비(mm)", 0.9, "number"],
    ["thick", "조적두께", 0.8, [["0.5B", "0.5B"], ["1.0B", "1.0B"], ["1.5B", "1.5B"], ["2.0B", "2.0B"]]], ["dir", "방향", 0.6, [["X", "X"], ["Y", "Y"]]],
    ["expose", "노출", 1.3, [["2면 모르타르", "2면 모르타르"], ["1면 모르타르", "1면 모르타르"], ["노출", "노출"]]], ["finish", "마감두께", 0.7, "number"],
    ["boundary", "경계면", 0.8, [["양호", "양호"], ["불량", "불량"]]], ["applied", "적용", 0.8, [["양호", "양호"], ["보통", "보통"], ["불량", "불량"]]]];
  const mFilled = (x) => !!(x.type_id || x.mid || x.height || x.width);
  const mText = (t) => [t.kind, t.height || t.width ? `${t.height || "?"}×${t.width || "?"}` : "", t.thick, t.dir, t.expose, t.finish != null && t.finish !== "" ? `마감 ${t.finish}` : "", `경계 ${t.boundary}`, `→ ${t.applied}`].filter(Boolean).join(" · ");
  const newId = () => Math.random().toString(36).slice(2, 10);
  function nextMid(prefix) {
    const n = Math.max(0, ...mtypes.map((t) => String(t.mid || "").toUpperCase()).filter((m) => m.startsWith(prefix)).map((m) => Number(m.replace(/\D/g, "")) || 0));
    return `${prefix}-${n + 1}`;
  }
  function drawMasonry() {
    mtypes = (F.masonry_types || []).map((x) => ({ ...x }));
    mplan = { ...(F.masonry_plan || {}) };
    mgroups = {};
    for (const m of F.masonry) (mgroups[m.floor] ||= []).push({ ...m });
    renderMasonry();
  }
  function renderMasonry() {
    const floors = [...new Set([...(F.masonry_floors || F.sample_floors), ...Object.keys(mplan).map(Number), ...Object.keys(mgroups).map(Number)])].filter((n) => n).sort((a, b) => a - b); // 조적 조사단위 층(10/26)
    for (const n of floors) {
      const g = (mgroups[n] ||= []);
      const want = Math.max(mplan[n] ?? 0, g.filter(mFilled).length);
      while (g.length < want) g.push({ floor: n, type_id: "" });
      while (g.length > want && !mFilled(g[g.length - 1])) g.pop();
    }
    const tRow = (t, i) => `<div class="sf2-row"><span class="sf2-no">${i + 1}</span>${MCOLS.map(([k, label, w, c]) => Array.isArray(c)
      ? `<select data-t="${i}" data-k="${k}" title="${esc(label)}" style="flex:${w}">${opt(c, t[k])}</select>`
      : `<input data-t="${i}" data-k="${k}" type="${c === "number" ? "number" : "text"}" ${c === "number" ? 'step="any" inputmode="decimal"' : ""} placeholder="${esc(label)}" title="${esc(label)}" style="flex:${w}" value="${esc(t[k] ?? "")}" />`).join("")}
      <button type="button" class="sp-x" data-trm="${i}" title="목록에서 지우기">✕</button></div>`;
    const choices = (m) => [["", mtypes.length ? "— 조적 부재 고르기 —" : "위 조적 목록을 먼저"], ...mtypes.map((t) => [t.id, `${t.mid || "?"} ${t.kind}`]),
      ...(m.type_id && !mtypes.some((t) => t.id === m.type_id) || (!m.type_id && mFilled(m)) ? [["__self", `${m.mid || "?"} (목록 밖)`]] : [])];
    let no = 0;
    const slot = (n, m, j) => {
      no += 1;
      const t = mtypes.find((x) => x.id === m.type_id);
      const v = m.type_id && !t || (!m.type_id && mFilled(m)) ? "__self" : m.type_id || "";
      return `<div class="sf2-row${mFilled(m) ? "" : " empty"}"><span class="sf2-no">${no}</span><span class="sf2-mk">칸 ${j + 1}</span>
        <select data-mf="${n}" data-mj="${j}" title="조적 부재" class="sf2-mpick">${opt(choices(m), v)}</select>
        <span class="sf2-msum">${mFilled(m) ? esc(mText(t || m)) : ""}</span><button type="button" class="sp-x" data-mrm="${n}|${j}" title="이 칸 비우기">✕</button></div>`;
    };
    const cnt = (n) => (mgroups[n] || []).filter(mFilled).length;
    $("sf2-masonry").innerHTML = `<div class="sf2-sub-h">조적 목록 <span class="sk-help">F = 채움벽, P = 허리벽 — 같은 크기·방향·상태끼리 한 줄, 아래 층별 칸에서 고르면 이 값이 들어감</span></div>
      <div class="sf2-row sf2-row-h"><span class="sf2-no">#</span>${MCOLS.map(([, label, w]) => `<span style="flex:${w}">${esc(label)}</span>`).join("")}<span class="sp-x-sp"></span></div>
      ${mtypes.map(tRow).join("")}
      <div class="sf2-add2"><button type="button" class="secondary" data-tadd="F">＋ 채움벽(F)</button><button type="button" class="secondary" data-tadd="P">＋ 허리벽(P)</button></div>
      <div class="sf2-sub-h">층별 조사 <span class="sk-help">층마다 칸 수(기본 2 — 조사단위별 2개소 이상), 칸에서 목록 부재를 고르기</span></div>
      ${floors.map((n) => `<div class="sf2-mfloor"><h4>${esc(floorName(n))} <span class="sk-help">${cnt(n)}/${(mgroups[n] || []).length}</span>
        <label class="sf2-mq">칸 수 <input type="number" min="0" max="20" inputmode="numeric" data-mq="${n}" value="${(mgroups[n] || []).length}" /></label></h4>
        ${(mgroups[n] || []).map((m, j) => slot(n, m, j)).join("")}</div>`).join("")}
      <button type="button" class="secondary" id="sf2-mq-reset">기본 칸 수로</button>`;
    const box = $("sf2-masonry");
    box.querySelectorAll("[data-t]").forEach((el) => el.addEventListener(el.tagName === "SELECT" ? "change" : "input", () => {
      const t = mtypes[Number(el.dataset.t)], k = el.dataset.k;
      t[k] = el.value;
      if (k === "mid") { const p = el.value.trim().toUpperCase()[0]; if (p === "F") t.kind = "채움벽"; if (p === "P") t.kind = "허리벽"; }
      if (k === "applied") t.manual = true;
      if ((k === "expose" || k === "boundary") && !t.manual) t.applied = t.boundary === "불량" || t.expose === "노출" ? "불량" : t.expose === "2면 모르타르" ? "양호" : "보통";
      if (el.tagName === "SELECT" || k === "mid") renderMasonry();
    }));
    box.querySelectorAll("[data-trm]").forEach((b) => b.addEventListener("click", () => { mtypes.splice(Number(b.dataset.trm), 1); renderMasonry(); }));
    box.querySelectorAll("[data-tadd]").forEach((b) => b.addEventListener("click", () => {
      const last = mtypes[mtypes.length - 1];
      mtypes.push({ id: newId(), mid: nextMid(b.dataset.tadd), kind: b.dataset.tadd === "F" ? "채움벽" : "허리벽", thick: last?.thick || "1.0B", dir: "X", expose: "1면 모르타르", boundary: "양호", applied: "보통", finish: 20, manual: false });
      renderMasonry();
    }));
    box.querySelectorAll("[data-mf]").forEach((el) => el.addEventListener("change", () => {
      const m = mgroups[el.dataset.mf][Number(el.dataset.mj)];
      if (el.value === "__self") return;
      const t = mtypes.find((x) => x.id === el.value);
      Object.assign(m, t ? { type_id: t.id, kind: t.kind, mid: t.mid, height: t.height, width: t.width, thick: t.thick, dir: t.dir, expose: t.expose, finish: t.finish, boundary: t.boundary, applied: t.applied, manual: t.manual }
        : { type_id: "", mid: "", height: null, width: null });
      renderMasonry();
    }));
    box.querySelectorAll("[data-mrm]").forEach((b) => b.addEventListener("click", () => {
      const [n, j] = b.dataset.mrm.split("|").map(Number);
      mgroups[n][j] = { floor: n, type_id: "" };
      renderMasonry();
    }));
    box.querySelectorAll("[data-mq]").forEach((el) => el.addEventListener("change", () => { mplan[el.dataset.mq] = Math.max(0, Math.min(20, Number(el.value) || 0)); renderMasonry(); }));
    $("sf2-mq-reset").addEventListener("click", () => { mplan = { ...(F.masonry_plan_default || {}) }; renderMasonry(); });
    const done = floors.reduce((a, n) => a + cnt(n), 0);
    $("sf2-w-sum").textContent = `${done}개 (최소 ${F.min_counts.masonry}) · 목록 ${mtypes.length}종 — 2.4.3 조적벽 치수 및 상태조사 결과표`;
  }
  function masonryOut() {
    return Object.keys(mgroups).map(Number).sort((a, b) => a - b).flatMap((n) => mgroups[n].filter(mFilled).map((m) => ({ ...m, floor: n, height: nz(m.height), width: nz(m.width), finish: nz(m.finish) })));
  }

  function drawTexts() {
    $("sf2-summary").value = F.summary || "";
    const box = (k, label) => `<div class="sk-f"><label>${esc(label)}</label><textarea data-t="${k}" rows="2" placeholder="비우면 보고서도 빈칸">${esc(F.texts[k] || "")}</textarea></div>`;
    const isSum = () => true; // 조사결과 글 — 한 글이 본문 조사결과와 요약 표에 같이(10/22 형 "결과값 연동 AI 작성"), 처음엔 빈칸
    $("sf2-texts").innerHTML = `<div class="sf2-sub-h">조사결과 글 <span class="sk-help">한 글이 본문 조사결과와 요약 표(장비조사·결함조사·비구조)에 같이 들어감 — 비우면 둘 다 빈칸, 줄마다 글머리 하나</span></div>
      <div class="sf2-core-top"><button type="button" class="secondary" id="sf2-eq-ai">🤖 입력값으로 AI가 쓰기 <span class="sk-help">약 40원</span></button><span class="sk-help" id="sf2-eq-note"></span></div>`
      + F.text_labels.map(([k, label]) => box(k, label)).join("");
    $("sf2-eq-ai").addEventListener("click", async () => {
      const filled = [...document.querySelectorAll("[data-t]")].filter((t) => isSum(t.dataset.t) && t.value.trim()).length;
      if (filled && !confirm(`조사결과 글 ${filled}칸에 이미 글이 있습니다 — AI 글로 바꿀까요?`)) return;
      const b = $("sf2-eq-ai");
      b.disabled = true;
      $("sf2-eq-note").textContent = "입력값으로 쓰는 중…(20~40초)";
      try {
        const res = await apiPost(`/seismic/projects/${id}/field/texts/ai`);
        draw(res);
        $("sf2-t-panel").open = true;
        $("sf2-eq-note").textContent = `✓ ${res.filled}칸 썼습니다 — 고치고 [저장] (자료가 없는 칸은 빈칸)`;
      } catch (e) { $("sf2-eq-note").textContent = e.message; b.disabled = false; }
    });
  }

  // 위쪽 수량 표시 — 스크롤해도 위에 고정, 누르면 그 칸으로(10/22 민재형 "셀고정, 해당 조사항목 누르면 그 항목으로 즉시 이동"). 철근배근은 철근탐사 화면으로.
  function drawMin() {
    const m = F.min_counts;
    const it = (label, n, min, go, href) => `<a class="sp-min-it${n >= min && n > 0 ? " ok" : ""}"${href ? ` href="${href}"` : ` href="#${go}" data-go="${go}"`}><b>${n}</b>/${min} ${esc(label)}</a>`;
    $("sf2-min").innerHTML = it("부재 단면", F.members.length, m.member, "sf2-m-panel") + it("철근배근", F.rebar, m.rebar, "sf2-r-panel")
      + it("코어", F.cores.length, m.core, "sf2-c-panel") + it("조적조", F.masonry.length, m.masonry, "sf2-w-panel")
;
    $("sf2-min-help").textContent = `조사단위 ${F.units}개 — 매뉴얼 <표 3-1> 최소 수량(지금/최소) · 부재 ${(m.how || {}).member || ""} · 철근 ${(m.how || {}).rebar || ""}`; // 고정 줄 밖
  }

  $("sf2-min").addEventListener("click", (e) => {
    const a = e.target.closest("[data-go]");
    if (!a) return;
    e.preventDefault();
    const p = $(a.dataset.go);
    if (p) { p.open = true; p.scrollIntoView({ behavior: "smooth", block: "start" }); }
  });

  function stickPad() { // 고정 줄 밑으로 칸이 숨지 않게 — 탭·찾기로 넘어갈 때 그만큼 띄움
    const bar = $("sf2-min");
    document.documentElement.style.scrollPaddingTop = `${bar.offsetHeight + (parseInt(getComputedStyle(bar).top, 10) || 0) + 8}px`;
  }
  window.addEventListener("resize", stickPad);

  function draw(f) {
    F = f;
    const what = TEXTS ? "보고서 AI 작성" : "현장조사 입력";
    document.title = `${what} - ${f.name}`;
    $("sf2-name").textContent = `${f.name} ${what}`;
    document.querySelector(".crumb > span:last-child").textContent = what;
    document.querySelector(".sp-head .page-sub").textContent = TEXTS ? "요약문 책임기술자 종합의견·조사결과 글(2.2 본문·요약 표·2.3 외관조사·2.4 중량물·마감재) — 견본 문장·🤖 AI로 채우고 고쳐 쓰기"
      : "보고서 차례로 2.2.1 부재 단면 → 2.2.2 철근탐사 → 2.2.3 코어 → 2.4.3 조적조 — 넣은 값은 보고서 표에 들어갑니다(현장·전경 사진은 외관조사)";
    $("sf2-proj").textContent = f.name;
    $("sf2-proj").href = `seismic-project.html?id=${id}`;
    drawMin(); stickPad(); drawMembers(); drawCores(); drawMasonry(); drawTexts(); // 사진은 외관조사 탭(10/27, js/seismic-photos.js)
  }

  async function save(part, body, savedEl) {
    try { draw(await apiPatch(`/seismic/projects/${id}/field`, body)); flash($(savedEl), "✓ 저장했습니다"); } catch (e) { err(e); }
  }
  const nz = (v) => (v === "" || v == null ? null : Number(v));
  $("sf2-m-save").addEventListener("click", () => save("members", { members: membersOut(), member_plan: plan, member_order: orderOut() }, "sf2-m-saved"));
  $("sf2-c-save").addEventListener("click", () => save("cores", { cores: cores.filter((x) => x.name || x.mpa).map((x) => ({ ...x, mpa: nz(x.mpa) })), core_design: nz($("sf2-c-design").value) }, "sf2-c-saved"));
  $("sf2-w-save").addEventListener("click", () => save("masonry", { masonry: masonryOut(), masonry_types: mtypes.map((t) => ({ ...t, height: nz(t.height), width: nz(t.width), finish: nz(t.finish) })), masonry_plan: mplan }, "sf2-w-saved"));
  $("sf2-t-save").addEventListener("click", () => save("texts", { texts: Object.fromEntries([...document.querySelectorAll("[data-t]")].map((t) => [t.dataset.t, t.value.trim()])), summary: $("sf2-summary").value.trim() }, "sf2-t-saved"));
  for (const [btn, mode, busy] of [["sf2-s-tpl", "template", "견본 문장 채우는 중…"], ["sf2-s-ai", "ai", "AI가 쓰는 중…(20~40초)"]]) {
    $(btn).addEventListener("click", async () => {
      if ($("sf2-summary").value.trim() && !confirm("지금 글을 바꿉니다. 할까요?")) return;
      $(btn).disabled = true;
      $("sf2-s-note").textContent = busy;
      try { draw(await apiPost(`/seismic/projects/${id}/field/summary/${mode}`)); $("sf2-t-panel").open = true; $("sf2-s-note").textContent = "✓ 채웠습니다 — 고치고 [저장]"; }
      catch (e) { $("sf2-s-note").textContent = e.message; }
      $(btn).disabled = false;
    });
  }
  $("sf2-c-read").addEventListener("click", async () => {
    if (cores.length && !confirm("성적서에서 다시 읽으면 지금 코어 줄이 바뀝니다. 읽을까요?")) return;
    const b = $("sf2-c-read");
    b.disabled = true;
    $("sf2-c-note").textContent = "성적서 읽는 중…(10~20초)";
    try { const res = await apiPost(`/seismic/projects/${id}/field/cores/read`); draw(res); $("sf2-c-note").textContent = `✓ ${res.read}개 읽음 — 확인하고 틀리면 고쳐 저장${F.core_note ? ` · ${F.core_note}` : ""}`; } catch (e) { $("sf2-c-note").textContent = e.message; b.disabled = false; }
  });

  (async () => {
    try {
      if (!id) throw new Error("내진성능평가 건을 찾을 수 없습니다.");
      draw(await api(`/seismic/projects/${id}/field`));
    } catch (e) { err(e); }
  })();
})();
