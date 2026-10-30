// 내진성능평가 건 화면(seismic-project.html?id=회차 | ?facility=건물, 2026-10-21 사용자 — 별도 용역).
// 서류 칸(올리기·바꾸기·보기·지우기, 구조 일람표·구조도면은 여러 장) · 지반조사 확인(값·사진 바꾸기) · 용역 정보 · 건물 정보(층별·변동) ·
// 현장조사(최소 수량 + 결함·일람표·철근탐사 화면) · 보고서 만들기. 서버 server/api/routers/seismic.py(+ 만들기는 /sitok/reports/{id}/build).

(function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const errorEl = document.getElementById("error");
  const $ = (id) => document.getElementById(id);
  const qs = new URLSearchParams(location.search);
  let id = Number(qs.get("id")) || 0;
  let P = null; // 건 화면 값(GET /seismic/projects/{id})
  let timer = null;
  const dot = (iso) => (iso ? String(iso).slice(0, 10).replace(/-/g, ".") : "");
  const won = (n) => (n || n === 0 ? Number(n).toLocaleString("ko-KR") : "");
  const flash = (el, text) => { el.textContent = text; setTimeout(() => { if (el.textContent === text) el.textContent = ""; }, 3500); };
  const err = (e) => showError(errorEl, e);

  // ---------- 칸 그리기 도우미 ----------
  // 빈 칸 = 서류에서 자동으로 못 채운 칸 → 노란 칸 + 표시(10/22 사용자 "자동으로 안 채워지는 것 표시 다르게, 눈에 띄게").
  // manual = 서류에 없어 늘 직접(건물 길이 X·Y) — 채워도 작은 표시는 남김
  function field(key, label, val, opt = {}) {
    const type = opt.type || "text";
    const v = val ?? "";
    const empty = !opt.optional && String(v).trim() === "";
    const tag = `<span class="sp-hand">${opt.manual ? "✍ 직접 입력" : "못 읽음 — 직접 입력"}</span>`;
    const input = opt.options
      ? `<select data-k="${key}">${opt.options.map((o) => { const [ov, ol] = Array.isArray(o) ? o : [o, o]; return `<option value="${esc(ov)}"${ov === String(v) ? " selected" : ""}>${esc(ol)}</option>`; }).join("")}</select>`
      : `<input data-k="${key}" type="${type}"${opt.step ? ` step="${opt.step}"` : ""} value="${esc(type === "date" ? String(v).slice(0, 10) : v)}"${opt.ph ? ` placeholder="${esc(opt.ph)}"` : ""} />`;
    return `<div class="sk-f sp-chk${opt.manual ? " sp-manual" : ""}${empty ? " sp-need" : ""}${opt.wide ? " ds-wide" : ""}"><label>${esc(label)}${tag}${opt.help ? ` <span class="sk-help">${esc(opt.help)}</span>` : ""}</label>${input}</div>`;
  }
  // 패널 제목 줄 "✍ 직접 넣을 칸 N개" — 접혀 있어도 보이게
  function needCount() {
    for (const [panel, pill] of [["sp-c-panel", "sp-c-need"], ["sp-b-panel", "sp-b-need"], ["sp-ground-panel", "sp-g-need"]]) {
      const n = $(panel) ? $(panel).querySelectorAll(".sp-need").length : 0;
      if (!$(pill)) continue;
      $(pill).hidden = !n;
      $(pill).textContent = `✍ 직접 넣을 칸 ${n}개`;
    }
  }
  const onFill = (e) => {
    const w = e.target.closest && e.target.closest(".sp-chk");
    if (!w || !e.target.matches("input, select")) return;
    w.classList.toggle("sp-need", !e.target.value.trim());
    needCount();
  };
  document.addEventListener("input", onFill);
  document.addEventListener("change", onFill);
  const read = (box) => Object.fromEntries([...box.querySelectorAll("[data-k]")].map((el) => [el.dataset.k, el.value.trim()]));

  // ---------- 서류 ----------
  function docRow(d) {
    const url = (item) => `${BASE}/api/seismic/projects/${id}/docs/${d.key}/file${item ? `?item=${encodeURIComponent(item)}` : ""}`;
    const files = d.items.map((it) => `<span class="sp-file"><a href="${url(it.id)}" target="_blank" rel="noopener">${esc(it.name)}</a>`
      + `${it.at ? `<em>${esc(String(it.at).slice(5, 16))}</em>` : ""}<button type="button" class="sp-x" data-del="${esc(it.id)}" title="지우기">✕</button></span>`).join("");
    const has = d.items.length > 0;
    const extra = d.key === "schedule" ? `<a class="secondary-link" href="sitok-schedule.html?facility=${P.facility_id}&seis=1">📋 부재 목록</a>`
      : d.key === "plan" ? '<button type="button" class="secondary sp-act" data-act="plan/auto" title="견본 과업수행계획서에 용역명·기간·건물·위치도·일정·기술자를 채움">📝 자동으로 만들기</button>'
        : d.key === "register" && has ? '<button type="button" class="secondary sp-act" data-act="register/ai" data-cost="1" title="글자 없는 스캔본일 때 — AI가 읽어 건물 정보에 넣음">🤖 AI로 읽기 <span class="sk-help">약 30원</span></button>' : "";
    // 층별 평면도 — 보고서 1.2 이름(도면 제목에서 읽은 것, 틀리면 고쳐 쓰기 — 10/27 사용자 "네이밍이 다르면 고칠 수 있게")
    const fps = d.key === "floorplan" && has ? P.floorplans || [] : [];
    const manyFiles = new Set(fps.map((x) => x.item)).size > 1;
    const fp = fps.length ? `<div class="sp-fp"><div class="sp-fp-h">보고서 1.2 평면도 이름 <span class="sk-help">보고서 차례대로 · 틀리면 고쳐 쓰기, 비우면 도면에서 읽은 이름</span></div>
      <div class="sp-fp-grid">${fps.map((x, n) => `<div class="sp-fp-it${x.name ? " own" : ""}">
        <a href="${url(x.item)}#page=${x.page}" target="_blank" rel="noopener" title="도면 크게 보기"><img src="${BASE}/api/seismic/projects/${id}/floorplans/${encodeURIComponent(x.item)}/${x.page}/thumb" alt="" loading="lazy" /></a>
        <div class="sk-f"><label>${n + 1}. ${manyFiles ? `${esc(x.file)} ` : ""}${x.page}쪽</label>
          <input data-fp-item="${esc(x.item)}" data-fp-page="${x.page}" value="${esc(x.name)}" placeholder="${esc(x.auto)}" maxlength="40" /></div>
        <div class="sp-fp-cap">보고서: ${esc(x.cap)}</div></div>`).join("")}</div></div>` : "";
    const el = document.createElement("div");
    el.className = `sp-doc${has ? " on" : ""}`;
    el.innerHTML = `<div class="sp-doc-main">
        <div class="sp-doc-t"><b>${esc(d.label)}</b>${has ? '<span class="sp-ok">✓</span>' : '<span class="sp-no">아직</span>'}</div>
        <div class="sp-doc-fills">${esc(d.fills)}</div>
        ${has ? `<div class="sp-doc-files">${files}</div>` : ""}
        <div class="sp-doc-note"${d.note ? "" : " hidden"}>${esc(d.note)}</div>${fp}
      </div>
      <div class="sp-doc-btns">${extra}
        <label class="secondary sp-up">${has ? (d.multi ? "＋ 더하기" : "바꾸기") : "올리기"}<input type="file" hidden data-kr-file="1" accept="${d.exts.join(",")}" /></label>
      </div>`;
    const input = el.querySelector("input[type=file]");
    if (typeof enableFileDrop === "function") enableFileDrop(el, input);
    input.addEventListener("change", async () => {
      const f = input.files[0];
      if (!f) return;
      const note = el.querySelector(".sp-doc-note");
      note.hidden = false;
      note.textContent = `${f.name} 올리는 중…${d.key === "ground" ? " (지반조사보고서 읽기 — 10초쯤)" : ""}`;
      const fd = new FormData();
      fd.append("file", f);
      try {
        const res = await apiUpload(`/seismic/projects/${id}/docs/${d.key}`, fd);
        draw(res);
        if (res.msg) { const n = [...document.querySelectorAll(".sp-doc")].find((x) => x.dataset.key === d.key)?.querySelector(".sp-doc-note"); if (n) { n.hidden = false; n.textContent = res.msg; } }
      } catch (e) { note.textContent = e.message; note.classList.add("bad"); }
    });
    el.querySelectorAll(".sp-act").forEach((b) => b.addEventListener("click", async () => {
      if (b.dataset.cost && !confirm("AI로 건축물대장을 읽습니다(약 30원). 지금 건물 정보 칸이 바뀝니다. 할까요?")) return;
      const note = el.querySelector(".sp-doc-note");
      note.hidden = false;
      note.classList.remove("bad");
      note.textContent = b.dataset.cost ? "AI가 읽는 중…(20~40초)" : "만드는 중…";
      b.disabled = true;
      try {
        const res = await apiPost(`/seismic/projects/${id}/docs/${b.dataset.act}`);
        draw(res);
        const n = [...document.querySelectorAll(".sp-doc")].find((x) => x.dataset.key === d.key)?.querySelector(".sp-doc-note");
        if (n && res.msg) { n.hidden = false; n.textContent = res.msg; }
      } catch (e) { note.textContent = e.message; note.classList.add("bad"); b.disabled = false; }
    }));
    el.querySelectorAll("[data-fp-item]").forEach((inp) => {
      inp.addEventListener("keydown", (e) => { if (e.key === "Enter") inp.blur(); });
      inp.addEventListener("change", async () => {
        try {
          draw(await apiPatch(`/seismic/projects/${id}/floorplans`, { item: inp.dataset.fpItem, page: Number(inp.dataset.fpPage), name: inp.value.trim() }));
          const n = [...document.querySelectorAll(".sp-doc")].find((x) => x.dataset.key === d.key)?.querySelector(".sp-doc-note");
          if (n) { n.hidden = false; n.classList.remove("bad"); n.textContent = "평면도 이름 저장 — 다음 [다시 만들기]부터 보고서에"; }
        } catch (e) { err(e); }
      });
    });
    el.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => {
      if (!confirm(`${d.label}을(를) 지울까요?`)) return;
      try { draw(await api(`/seismic/projects/${id}/docs/${d.key}${b.dataset.del ? `?item=${encodeURIComponent(b.dataset.del)}` : ""}`, { method: "DELETE" })); } catch (e) { err(e); }
    }));
    el.dataset.key = d.key;
    return el;
  }

  // ---------- 지반조사 확인 ----------
  function groundImg(name) { return `${BASE}/api/seismic/projects/${id}/ground/img/${encodeURIComponent(name)}`; }

  function pickPhoto(h, slot, label) {
    const ov = document.createElement("div");
    ov.className = "mail-overlay";
    const all = (P.ground.holes || []).flatMap((x) => (x.extra || []).map((e) => ({ ...e, bh: x.bh })));
    ov.innerHTML = `<div class="mail-box sp-pick" role="dialog" aria-modal="true">
      <div class="mail-head"><b>${esc(h.bh)} ${esc(label)}</b><span class="mail-sub">지반조사보고서 사진대지에서 고르기</span></div>
      <div class="sp-pick-grid">${all.map((e) => `<button type="button" class="sp-pick-it${h.photos[slot] === e.file ? " on" : ""}" data-f="${esc(e.file)}">
        <img src="${groundImg(e.file)}" alt="" loading="lazy" /><span>${esc(e.bh)} ${esc(e.caption)} · ${e.page}쪽</span></button>`).join("")}</div>
      <div class="mail-foot"><button type="button" class="sp-clear">칸 비우기</button><button type="button" class="sp-cancel">닫기</button></div></div>`;
    document.body.appendChild(ov);
    const close = () => ov.remove();
    const choose = async (file) => {
      try { draw(await apiPatch(`/seismic/projects/${id}/ground`, { bh: h.bh, slot, file })); close(); } catch (e) { alert(e.message); }
    };
    ov.querySelectorAll(".sp-pick-it").forEach((b) => b.addEventListener("click", () => choose(b.dataset.f)));
    ov.querySelector(".sp-clear").addEventListener("click", () => choose(""));
    ov.querySelector(".sp-cancel").addEventListener("click", close);
    ov.addEventListener("click", (e) => { if (e.target === ov) close(); });
  }

  function drawGround() {
    const g = P.ground;
    $("sp-ground-panel").hidden = !g;
    if (!g) return;
    const holes = g.holes || [];
    const got = holes.reduce((n, h) => n + Object.keys(h.photos || {}).length, 0);
    $("sp-g-sum").textContent = `시추공 ${holes.length}개 · 사진 ${got}/${holes.length * P.ground_slots.length} · ${holes.map((h) => `${h.bh} ${h.cls || "?"} ${h.vs ?? "?"}m/s`).join(" · ")}`
      + ((g.warn || []).length ? ` · 확인할 것 ${g.warn.length}개` : " — 눌러서 사진·값 확인");
    // 처음엔 모두 접힘(10/28 사용자 "기본 세팅은 전부 접혀있는걸로") — 알림은 머리 표시(sp-g-need)로만
    const box = $("sp-ground");
    box.innerHTML = `${(g.warn || []).length ? `<div class="mail-msg bad">${g.warn.map(esc).join("<br>")}</div>` : ""}
      ${P.ground_sentence ? `<div class="sp-sentence"><span class="sk-help">2.5 (3) 문장</span><br>${esc(P.ground_sentence)}</div>` : ""}
      <div class="sp-g-map">${g.map ? `<figure><img src="${groundImg(g.map)}" alt="" /><figcaption>지반조사 위치도</figcaption></figure>` : '<div class="sk-none">위치도 못 찾음</div>'}</div>`;
    for (const h of g.holes || []) {
      const el = document.createElement("div");
      el.className = "sp-hole";
      el.innerHTML = `<h3>${esc(h.bh)}</h3>
        <div class="field-grid sp-grid sp-g-vals">
          ${field("depth", "기반암 깊이", h.depth, { help: "KDS 17 10 00:2024" })}${field("vs", "전단파속도 (m/s)", h.vs, { type: "number", step: "0.1" })}
          ${field("cls", "지반등급", h.cls, { options: ["", "S1", "S2", "S3", "S4", "S5", "S6"] })}${field("apply_depth", "적용심도 (m)", h.apply_depth, { type: "number", step: "0.1" })}
        </div>
        <div class="sp-g-photos">${P.ground_slots.map(([slot, label]) => `<button type="button" class="sp-g-ph${h.photos[slot] ? "" : " none"}" data-slot="${slot}" data-label="${esc(label)}">
          ${h.photos[slot] ? `<img src="${groundImg(h.photos[slot])}" alt="" loading="lazy" />` : '<span class="sp-g-empty">못 찾음 — 눌러서 고르기</span>'}<span class="sp-g-cap">${esc(h.bh)} ${esc(label)}</span></button>`).join("")}</div>
        ${h.result ? `<figure class="sp-g-res"><img src="${groundImg(h.result)}" alt="" loading="lazy" /><figcaption>${esc(h.bh)} 지반조사 결과(위쪽 표)</figcaption></figure>` : ""}`;
      el.querySelectorAll(".sp-g-ph").forEach((b) => b.addEventListener("click", () => pickPhoto(h, b.dataset.slot, b.dataset.label)));
      el.querySelectorAll(".sp-g-vals [data-k]").forEach((inp) => inp.addEventListener("change", async () => {
        const k = inp.dataset.k;
        const v = k === "vs" || k === "apply_depth" ? (inp.value === "" ? null : Number(inp.value)) : inp.value.trim();
        try { draw(await apiPatch(`/seismic/projects/${id}/ground`, { bh: h.bh, [k]: v })); } catch (e) { err(e); }
      }));
      box.appendChild(el);
    }
  }

  // ---------- 용역·건물 ----------
  // 칸은 처음엔 모두 접힘(10/28 사용자 "기본 세팅은 전부 접혀있는걸로" — 전엔 빈 칸·알림이 있으면 펼쳤음), 머리 표시("아직 N"·"직접 넣을 칸 N개")로 알림, 그 뒤로는 사람이 연 대로
  function drawContract() {
    const c = P.contract || {};
    $("sp-c-sum").textContent = c.title ? [c.title, c.amount ? `${won(c.amount)}원` : "", c.start_date ? `${dot(c.start_date)} ~ ${dot(c.end_date)}` : ""].filter(Boolean).join(" · ")
      : "용역계약서에서 — 표지·제출문·결과표 가·참여기간";
    $("sp-contract").innerHTML = field("title", "용역명", c.title, { wide: true, ph: "예: 삼숭초 교사동 내진성능평가 용역" })
      + field("client", "발주처", c.client) + field("client_rep", "관리주체 대표자", c.client_rep, { ph: "예: 교육장 ○○○", help: "결과표 가. 대표자", manual: true })
      + field("amount", "계약금액 (원)", c.amount ? won(c.amount) : "", { ph: "32,118,700" })
      + field("contract_date", "계약일", c.contract_date, { type: "date" }) + field("contract_no", "계약번호", c.contract_no)
      + field("start_date", "착수일", c.start_date, { type: "date" }) + field("end_date", "완수일", c.end_date, { type: "date", help: "보고서 날짜(표지 연월)" })
      + field("method", "계약방법", c.method, { ph: "수의계약" }) + field("joint", "공동수급", c.joint, { ph: "단독계약" })
      + field("manager", "발주처 담당자", c.manager) + field("phone", "담당자 전화", c.phone);
    const rep = P.report || {};
    const opts = (sel) => `<option value="">— 고르기 —</option>` + P.persons.map((p) => `<option value="${p.id}"${p.id === sel ? " selected" : ""}>${esc(p.name)}${p.grade ? ` (${esc(p.grade)})` : ""}</option>`).join("");
    const parts = rep.participant_ids || [];
    $("sp-people").innerHTML = `<div class="sk-f sp-chk sp-manual${rep.chief_id ? "" : " sp-need"}"><label>사업책임기술자<span class="sp-hand">✍ 직접 고르기</span></label><select id="sp-chief">${opts(rep.chief_id)}</select></div>
      <div class="sk-f ds-wide sp-manual${parts.length ? "" : " sp-need"}" id="sp-parts-f"><label>분야별 참여기술자<span class="sp-hand">✍ 직접 고르기</span> <span class="sk-help">눌러서 고르기</span></label><div class="ds-chips" id="sp-parts">
      ${P.persons.map((p) => `<button type="button" class="ds-chip${parts.includes(p.id) ? " on" : ""}" data-p="${p.id}">${esc(p.name)}</button>`).join("")}</div></div>`;
    $("sp-parts").querySelectorAll(".ds-chip").forEach((b) => b.addEventListener("click", () => {
      b.classList.toggle("on");
      $("sp-parts-f").classList.toggle("sp-need", !$("sp-parts").querySelector(".on"));
      needCount();
    }));
  }

  function rowsEditor(box, rows, cols, blank) {
    const draw1 = () => {
      box.innerHTML = `<div class="sp-row sp-row-h">${cols.map(([, label, w]) => `<span style="flex:${w}">${esc(label)}</span>`).join("")}<span class="sp-x-sp"></span></div>`
        + rows.map((r, i) => `<div class="sp-row">${cols.map(([k, label, w, type]) => `<input data-i="${i}" data-k="${k}" type="${type || "text"}" placeholder="${esc(label)}" title="${esc(label)}" style="flex:${w}" value="${esc(type === "date" ? String(r[k] ?? "").slice(0, 10) : r[k] ?? "")}" />`).join("")}
        <button type="button" class="sp-x" data-rm="${i}" title="줄 지우기">✕</button></div>`).join("") + '<button type="button" class="secondary sp-add">＋ 줄</button>';
      box.querySelectorAll("input").forEach((inp) => inp.addEventListener("input", () => { rows[inp.dataset.i][inp.dataset.k] = inp.value; }));
      box.querySelectorAll("[data-rm]").forEach((b) => b.addEventListener("click", () => { rows.splice(Number(b.dataset.rm), 1); draw1(); }));
      box.querySelector(".sp-add").addEventListener("click", () => { rows.push({ ...blank }); draw1(); });
    };
    draw1();
  }

  let floors = [], changes = [];
  function drawBuilding() {
    const b = P.building || {};
    $("sp-b-sum").textContent = b.address ? [b.structure, `지하${b.below || 0}·지상${b.above || 0}층`, b.total_area ? `연면적 ${won(b.total_area)}㎡` : "", b.approval_date ? `사용승인 ${dot(b.approval_date)}` : "", b.grade].filter(Boolean).join(" · ")
      : "건축물대장에서 — 1.1 일반사항·1.2 건물규모·1.3 내진등급·1.4 구조변경 이력(기초형식·철근 Fy는 직접)";
    $("sp-building").innerHTML = field("name", "건물 이름", b.name, { help: "보고서 이름·폴더 이름" }) + field("use", "주용도", b.use)
      + field("address", "주소(도로명)", b.address, { wide: true }) + field("lot_address", "대지위치(지번)", b.lot_address) + field("structure", "주구조", b.structure)
      + field("below", "지하 층수", b.below, { type: "number" }) + field("above", "지상 층수", b.above, { type: "number" })
      + field("height", "높이 (m)", b.height, { type: "number", step: "0.01" }) + field("roof", "지붕", b.roof)
      + field("length_x", "건물 길이 장변 X (m)", b.length_x, { type: "number", step: "0.1", help: "1.2 건물규모", manual: true }) + field("length_y", "건물 길이 단변 Y (m)", b.length_y, { type: "number", step: "0.1", manual: true })
      + field("total_area", "연면적 (㎡)", b.total_area, { type: "number", step: "0.01" }) + field("building_area", "건축면적 (㎡)", b.building_area, { type: "number", step: "0.01" })
      + field("site_area", "대지면적 (㎡)", b.site_area, { type: "number", step: "0.01" }) + field("approval_date", "사용승인일", b.approval_date, { type: "date", help: "준공·경과년수" })
      + field("permit_date", "허가일", b.permit_date, { type: "date" }) + field("build_start", "착공일", b.build_start, { type: "date" })
      + field("seismic_design", "내진설계 적용", b.seismic_design, { options: ["", "적용", "비적용"] }) + field("grade", "내진등급", b.grade, { options: ["특등급", "1등급", "2등급"], help: "학교 = 특등급" })
      + field("survey_units", "조사단위 수", b.survey_units, { type: "number", help: "층마다 1 — 기본 지상 층수, 익스팬션조인트·증축은 따로" })
      + field("drawings", "도면 유무", b.drawings, { options: [["", `자동 (지금 ${P.drawings_auto ? "보유" : "미보유"})`], "보유", "미보유"], optional: true, help: "구조도면·일람표 칸에 파일이 있으면 보유 · 결과표 바. 설계도면 유/무" })
      + field("calc_doc", "구조계산서 유무", b.calc_doc, { options: [["", "— 고르기 —"], "보유", "미보유"], help: "결과표 바. 구조계산서 유/무", manual: true })
      + field("foundation", "기초형식", b.foundation, { ph: "예: 매트기초, 독립기초", help: "결과표 나. 기초형식 · 1.1 기초형식", manual: true })
      + field("rebar_fy", "철근 항복강도 Fy (MPa)", b.rebar_fy, { ph: "예: 400", help: "1.1 재료강도 Fy(설계도서) — fck는 코어시험 결정강도", manual: true });
    floors = (P.floors || []).map((x) => ({ ...x }));
    changes = (P.changes || []).map((x) => ({ ...x }));
    rowsEditor($("sp-floors"), floors, [["kind", "구분", 0.6], ["floor", "층", 0.8], ["structure", "구조", 2], ["use", "용도", 1.6], ["area", "면적(㎡)", 1.1, "number"]], { kind: "주" });
    rowsEditor($("sp-changes"), changes, [["date", "변동일", 1.1, "date"], ["text", "변동내용 및 원인", 4]], {});
  }

  $("sp-c-save").addEventListener("click", async () => {
    const c = read($("sp-contract"));
    c.amount = c.amount ? Number(c.amount.replace(/[^\d]/g, "")) : null;
    const body = { contract: c, chief_id: Number($("sp-chief").value) || 0, participant_ids: [...$("sp-parts").querySelectorAll(".ds-chip.on")].map((b) => Number(b.dataset.p)) };
    try { draw(await apiPatch(`/seismic/projects/${id}`, body)); flash($("sp-c-saved"), "✓ 저장했습니다"); } catch (e) { err(e); }
  });

  $("sp-b-save").addEventListener("click", async () => {
    const b = read($("sp-building"));
    for (const k of ["below", "above", "height", "total_area", "building_area", "site_area", "length_x", "length_y", "survey_units"]) b[k] = b[k] === "" ? null : Number(b[k]);
    const fl = floors.filter((x) => x.floor || x.area).map((x) => ({ ...x, area: x.area === "" || x.area == null ? null : Number(x.area) }));
    try { draw(await apiPatch(`/seismic/projects/${id}`, { building: b, floors: fl, changes: changes.filter((x) => x.date || x.text) })); flash($("sp-b-saved"), "✓ 저장했습니다"); } catch (e) { err(e); }
  });

  // ---------- 현장조사 ----------
  function drawField() {
    const m = P.min_counts, s = (P.report || {}).seismic || {}, f = (P.report || {}).field || {};
    const how = m.how || {};
    $("sp-units").textContent = `조사단위 ${P.units}개 · 도면 ${(P.building || {}).drawings || (P.drawings_auto ? "보유" : "미보유")} — 매뉴얼 <표 3-1> 최소 수량`;
    // 조사단위 — 전체 칸 + 항목 칩의 "× N단위" 숫자를 바로 고침(10/26 민재형 "개별적으로 가능하게 하고 전체단위수도 — 발주처 요구로 지하 포함 6 등")
    const iu = P.item_units || {}, own = P.unit_own || [];
    const unitIn = (key, u) => `<input type="number" class="sp-u-in" min="1" max="40" inputmode="numeric" data-u="${key}" value="${u}" title="${key === "all" ? "전체 조사단위" : "이 항목만 조사단위"}" />`;
    const howHtml = (key, h) => { const u = iu[key]; return key && u ? esc(h).replace(`${u}단위`, `${unitIn(key, u)}단위`) : esc(h); }; // 계산식 속 단위 숫자 자리에 칸
    $("sp-min").innerHTML = `<label class="sp-u-all">전체 조사단위 ${unitIn("all", P.units)}개</label>`
      + [["부재 규격", m.member, how.member, "member"], ["철근배근", m.rebar, how.rebar, "rebar"], ["콘크리트 코어", m.core, how.core, "core"], ["시추(지반)", m.boring, how.boring, ""], ["조적조", m.masonry, how.masonry, "masonry"]]
        .map(([k, v, h, key]) => `<span class="sp-min-it${own.includes(key) ? " own" : ""}" title="${esc(h || "")}"><b>${v}</b>${esc(k)}${own.includes(key) ? `<button type="button" class="sp-u-back" data-ub="${key}" title="이 항목도 전체 조사단위(${P.units})로">개별 ↺</button>` : ""}${h ? `<em class="sp-min-how">${howHtml(key, h)}</em>` : ""}</span>`).join("")
      + '<div class="sk-help">조사단위 — 층마다 1단위(작은 지하·옥탑은 합칠 수 있음), 익스팬션조인트·증축 부분은 따로. 항목 칸의 단위 숫자를 고치면 그 항목만(발주처 요구 등), 도면 유무는 🏢 건물 정보에서.</div>';
    const setUnits = async (body) => {
      try {
        P = await apiPost(`/seismic/projects/${id}/units`, body);
        drawField();
        const bu = $("sp-building").querySelector('[data-k="survey_units"]'); // 건물 정보 칸도 같은 값(그 칸의 다른 고친 값은 그대로)
        if (bu) bu.value = P.units;
      } catch (e) { err(e); drawField(); }
    };
    $("sp-min").querySelectorAll("[data-u]").forEach((el) => el.addEventListener("change", () => {
      const n = Math.round(Number(el.value));
      if (!el.isConnected) return; // 다시 그려 떼어진 칸에서 오는 change는 무시
      const now = el.dataset.u === "all" ? P.units : (P.item_units || {})[el.dataset.u];
      if (!(n >= 1 && n <= 40)) { el.value = now; return; }
      if (n === now) return; // 같은 값(다시 그릴 때 한 번 더 오는 change)은 안 보냄
      setUnits(el.dataset.u === "all" ? { all: n } : { item: el.dataset.u, n });
    }));
    $("sp-min").querySelectorAll("[data-ub]").forEach((b) => b.addEventListener("click", () => setUnits({ item: b.dataset.ub, n: null })));
    const big = (href, ic, label, sub, ok) => `<a class="rd-btn${ok ? " on" : ""}" href="${href}"><span class="rd-ic">${ic}</span><span class="rd-lb">${esc(label)}${ok ? ' <em class="rd-ok">✓</em>' : ""}</span><span class="rd-sub">${esc(sub)}</span></a>`;
    const fc = P.field_counts || {};
    // 바로가기 넷(10/27 형·민재형 — 현장조사 입력 / 외관조사(결함 + 현장·전경 사진) / 보고서 AI 작성 / 구조 일람표 부재 목록, 철근탐사는 현장조사 입력 안으로)
    $("sp-links").innerHTML = big(`seismic-field.html?id=${id}`, "🧱", "현장조사 입력", `부재 단면 ${fc.members || 0}/${m.member} · 철근 ${s.rebar || 0}/${m.rebar} · 코어 ${fc.cores || 0}/${m.core} · 조적 ${fc.masonry || 0}/${m.masonry}`,
      (fc.members || 0) >= m.member && (fc.cores || 0) >= m.core && (s.rebar || 0) >= m.rebar)
      + big(`sitok-field.html?report=${id}&seis=1`, "📱", "외관조사", `${f.defects ? `결함 ${f.checked}/${f.defects} 확인` : "결함 2.3 · 부록 4 사진첩"} · 사진 ${fc.photos || 0}장`, !!f.done)
      + big(`seismic-field.html?id=${id}&part=texts`, "🤖", "보고서 AI 작성", `요약문 종합의견·조사결과 글 ${fc.texts || 0}/${fc.texts_total || 0}칸`, (fc.texts || 0) > 0)
      + big(`sitok-schedule.html?facility=${P.facility_id}&seis=1`, "📏", "구조 일람표 부재 목록", s.schedule ? `${s.schedule}칸${s.schedule_need ? ` · 확인 필요 ${s.schedule_need}` : ""}` : "서류 칸에 구조 일람표를 올리고 읽기", s.schedule > 0 && !s.schedule_need);
  }

  // ---------- 보고서 ----------
  function drawReport() {
    const r = P.report || {};
    const v = encodeURIComponent(r.made_at || "");
    const lines = (r.message || "").split("\n").filter(Boolean);
    const st = r.status === "running" ? `<span class="sk-rep-st run">⏳ ${esc(r.message)}</span>`
      : r.status === "failed" ? `<span class="sk-rep-st bad">✗ 실패: ${esc(r.message)}</span>`
        : r.status === "done" ? `<div class="sp-made">✓ ${esc(r.made_at)} 만듦</div>${lines.length ? `<div class="sp-warn">${lines.map(esc).join("<br>")}</div>` : ""}` : '<span class="sk-rep-st">아직 안 만듦</span>';
    $("sp-report").innerHTML = `<div class="sp-rep">${st}</div><div class="sp-rep-btns">
      ${r.has_pdf ? `<a class="secondary-link" href="${BASE}/api/sitok/reports/${id}/file/pdf?v=${v}" target="_blank" rel="noopener">${r.has_appendix ? "합본 PDF" : "PDF 보기"}</a>` : ""}
      ${r.has_hwpx ? `<a class="secondary-link" href="${BASE}/api/sitok/reports/${id}/file/hwpx?v=${v}">본문 한글</a>` : ""}
      ${r.has_appendix ? `<a class="secondary-link" href="${BASE}/api/sitok/reports/${id}/file/appendix?v=${v}">부록 한글</a>` : ""}
      <button type="button" id="sp-build"${r.status === "running" || !r.has_field ? " disabled" : ""}>${r.has_pdf ? "다시 만들기" : "보고서 만들기"}</button></div>
      ${r.has_field ? "" : '<div class="sp-need-done">먼저 위 📱 현장조사 칸 맨 아래 <b>[✓ 조사 완료]</b>를 누르세요 — 그 뒤에 보고서를 만들 수 있습니다.</div>'}`;
    $("sp-build").addEventListener("click", async () => {
      try { await apiPost(`/sitok/reports/${id}/build`); poll(); } catch (e) { err(e); }
    });
  }

  function poll() {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      try {
        const r = await api(`/sitok/reports/${id}`);
        P.report = r;
        drawReport();
        if (r.status === "running") poll();
      } catch (e) { err(e); }
    }, 3000);
  }

  // ---------- 전체 ----------
  function draw(p) {
    P = p;
    const b = p.building || {}, c = p.contract || {};
    document.title = `${b.name} - 내진성능평가`;
    $("sp-name").textContent = b.name || "이름 없음";
    $("sp-crumb").textContent = b.name || "건";
    $("sp-sub").textContent = [c.title, c.client, c.start_date ? `${dot(c.start_date)} ~ ${dot(c.end_date)}` : ""].filter(Boolean).join(" · ");
    const box = $("sp-docs");
    box.innerHTML = "";
    p.docs.forEach((d) => box.appendChild(docRow(d)));
    const missing = p.docs.filter((d) => !(d.items || []).length).length; // 서류 칸 접기(10/28 사용자) — 처음엔 안 올린 서류가 있으면 펼침, 그 뒤로는 사람이 연 대로
    const need = $("sp-docs-need");
    if (need) { need.hidden = !missing; need.textContent = missing ? `아직 ${missing}` : ""; }
    drawGround();
    drawContract();
    drawBuilding();
    drawField();
    drawReport();
    needCount();
    if ((p.report || {}).status === "running") poll();
  }

  $("sp-delete").addEventListener("click", async () => {
    const pw = prompt(`"${(P.building || {}).name}" 건을 지웁니다 — 서류·결함·철근탐사·보고서가 모두 지워집니다.\n삭제 비밀번호(보고서 자동화 설정):`);
    if (!pw) return;
    try { await api(`/seismic/projects/${id}`, { method: "DELETE", body: JSON.stringify({ password: pw }) }); location.href = "seismic.html"; } catch (e) { alert(e.message); }
  });

  async function load() {
    try {
      if (!id && qs.get("facility")) {
        const d = await api(`/seismic/projects?facility=${encodeURIComponent(qs.get("facility"))}`);
        id = d.projects[0]?.id || 0;
      }
      if (!id) throw new Error("내진성능평가 건을 찾을 수 없습니다.");
      draw(await api(`/seismic/projects/${id}`));
      if (window.L && typeof sitokDrawLocmap === "function") sitokDrawLocmap($("sp-locmap"), P.facility_id, (P.building || {}).name || ""); // 📍 위치도 깃발(10/22) // 건물 정보 안(10/28) — 접힌 채 만들어도 sitok-locmap이 details toggle에 invalidateSize
      const done = $("sp-field-done"); // [✓ 조사 완료] — 완료·취소하면 건 화면(외관조사 ✓·보고서 만들기)도 다시
      done.dataset.report = id;
      sitokStepBar(done, async () => { try { draw(await api(`/seismic/projects/${id}`)); } catch (e) { err(e); } });
    } catch (e) { err(e); }
  }

  load();
})();
