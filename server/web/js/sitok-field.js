// 시특법 현장 조사(sitok-field.html?report=, 2026-10-10 5단계) — 폰 우선. 층을 고르면 전회차 결함이 번호 순으로, 전회차 사진 옆에 이번 사진.
// [그대로] = 전회차 크기 그대로(비고 기존) · [진행] = 크기 다시(기존) · [보수] = 보수 완료(비고 보수) · ⭐ = 비교 사진대장에 꼭 넣기. [+ 신규] = 못 보던 결함.
// 서버 server/api/routers/sitok_defects.py.
// 10/12: 부재·결함유형은 고정 목록에서만 고름(회사 목록 + 이 보고서에만 추가한 것) — 없으면 "➕ 새로 추가…" → 이 보고서에만 / 회사 전체 목록에.
// 원인은 목록 없이 AI가 사진마다 구체적으로 + 근거 한 줄(cause_note).

(function () {
  const rid = Number(new URLSearchParams(location.search).get("report")) || null;
  const errorEl = document.getElementById("error");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const err = (e) => showError(errorEl, e);
  const KIND_LABEL = { member: "부재", dtype: "결함유형" };
  const AREA_RE = /누수|백태|박리|박락|층분리|재료분리|철근|부식|파손/;
  const DEPTH_RE = /박리|박락|층분리/; // 깊이(mm) 칸 — 정밀 상태평가 기준(박리 0.5/1.0/2.5, 박락·층분리 15/20/25mm, 10/13)
  let data = null;
  let started = false; // [전회차 없이 시작]을 누름(신축·전회차 자료 없음)
  try { started = sessionStorage.getItem(`sf-started-${rid}`) === "1"; } catch (_) { /* */ }
  let floor = "";
  try { floor = sessionStorage.getItem(`sf-floor-${rid}`) || ""; } catch (_) { /* 기억 못 해도 됨 */ }

  const sizeText = (v) => {
    if (!v) return "";
    const parts = [v.count || v["개수"] ? `${v.count || v["개수"]}개` : "", v.width || v["폭"] ? `폭 ${v.width || v["폭"]}` : "",
      v.length || v["길이"] ? `길이 ${v.length || v["길이"]}m` : ""].filter(Boolean);
    return parts.join(" · ");
  };

  // ---- 부재·결함유형 고정 목록 고르기 ----
  const listOf = (kind) => (kind === "member" ? data.members : data.types) || [];
  const isRecord = (t) => /현황\s*$/.test(t || "") || (t || "").trim() === "-";
  const outOfList = (kind, v) => !!v && !listOf(kind).includes(v) && !(kind === "dtype" && isRecord(v));

  function optionsHtml(kind, value) {
    const list = listOf(kind);
    const extra = value && !list.includes(value) ? `<option value="${esc(value)}" selected>${esc(value)}${outOfList(kind, value) ? " (목록 밖)" : ""}</option>` : "";
    return `<option value="">— 고르기 —</option>${list.map((v) => `<option value="${esc(v)}"${v === value ? " selected" : ""}>${esc(v)}</option>`).join("")}`
      + `${extra}<option value="__add">➕ 새로 추가…</option>`;
  }

  function setPick(sel, kind, value) {
    sel.innerHTML = optionsHtml(kind, value);
    sel.dataset.last = sel.value;
  }

  function askScope(kind, name) { // → "report" | "company" | null
    return new Promise((resolve) => {
      const ov = document.createElement("div");
      ov.className = "mail-overlay sf-top";
      ov.innerHTML = `<div class="mail-box sf-new" role="dialog" aria-modal="true"><div class="mail-head"><b>새 ${KIND_LABEL[kind]} "${esc(name)}"</b>
        <span class="mail-sub">어디에 추가할까요? 회사 전체 목록에 넣으면 다른 보고서에서도 고를 수 있습니다(설정 탭에서 뺄 수 있음).</span></div>
        <div class="sf-scope"><button type="button" data-s="report">이 보고서에만</button><button type="button" data-s="company">회사 전체 목록에</button></div>
        <div class="mail-foot"><button type="button" class="mail-cancel">취소</button></div></div>`;
      document.body.appendChild(ov);
      const done = (v) => { ov.remove(); resolve(v); };
      ov.querySelectorAll(".sf-scope button").forEach((b) => b.addEventListener("click", () => done(b.dataset.s)));
      ov.querySelector(".mail-cancel").addEventListener("click", () => done(null));
    });
  }

  async function addVocab(kind, name, scope) { // 목록에 추가 → 추가한 이름(취소면 null)
    name = String(name ?? prompt(`새 ${KIND_LABEL[kind]} 이름(짧게 — 표 칸이 좁습니다)`) ?? "").trim().replace(/\s+/g, " ");
    if (!name) return null;
    scope = scope || await askScope(kind, name);
    if (!scope) return null;
    const v = await apiPost(`/sitok/reports/${rid}/vocab`, { kind, name, scope });
    data.vocab = v;
    data.members = v.member.map((x) => x.name);
    data.types = v.dtype.map((x) => x.name);
    return name;
  }

  function bindPicker(sel, kind, onPick) { // "➕ 새로 추가…"를 고르면 추가하고 그 값으로(취소면 원래 값)
    sel.dataset.last = sel.value;
    sel.addEventListener("change", async () => {
      if (sel.value !== "__add") { sel.dataset.last = sel.value; onPick?.(sel.value); return; }
      let name = null;
      try { name = await addVocab(kind); } catch (e) { alert(e.message); }
      setPick(sel, kind, name || sel.dataset.last);
      if (name) onPick?.(name);
    });
  }

  const partOf = (m) => (data.part_of || {})[m] || "";

  function editKinds(d) { // 카드 ✏️ — 구분·부재·결함유형 고치기(지난 보고서에서 온 목록 밖 이름도 여기서)
    const ov = document.createElement("div");
    ov.className = "mail-overlay";
    ov.innerHTML = `<div class="mail-box sf-new" role="dialog" aria-modal="true"><div class="mail-head"><b>${esc(d.floor)} ${d.seq}번 고치기</b>
      <span class="mail-sub">구분·부재·결함유형 — 목록에 없으면 "➕ 새로 추가…"</span></div>
      <div class="sf-two"><label>구분<select class="e-part"><option>비구조체</option><option>구조체</option></select></label>
        <label>부재<select class="e-member"></select></label></div>
      <label>결함유형<select class="e-dtype"></select></label>
      <div class="mail-msg" hidden></div>
      <div class="mail-foot"><button type="button" class="mail-cancel">취소</button><button type="button" class="mail-primary e-ok">저장</button></div></div>`;
    document.body.appendChild(ov);
    const q = (s) => ov.querySelector(s);
    q(".e-part").value = d.part === "구조체" ? "구조체" : "비구조체";
    setPick(q(".e-member"), "member", d.member);
    setPick(q(".e-dtype"), "dtype", d.dtype);
    bindPicker(q(".e-member"), "member", (m) => { if (partOf(m)) q(".e-part").value = partOf(m); });
    bindPicker(q(".e-dtype"), "dtype");
    q(".mail-cancel").addEventListener("click", () => ov.remove());
    q(".e-ok").addEventListener("click", async () => {
      const body = { part: q(".e-part").value, member: q(".e-member").value, dtype: q(".e-dtype").value };
      if (!body.dtype) { alert("결함유형을 고르세요."); return; }
      try {
        Object.assign(d, await apiPatch(`/sitok/defects/${d.id}`, body));
        ov.remove();
        refresh(false);
      } catch (e) { const m = q(".mail-msg"); m.hidden = false; m.className = "mail-msg bad"; m.textContent = e.message; }
    });
  }

  const floorKey = (f) => { // 옥상 → 지상 위층부터 → 지하(서버 floor_key와 같은 순서)
    const n = Number((String(f).match(/\d+/) || [0])[0]);
    if (/옥상|옥탑/.test(f)) return [0, -n];
    if (/지하/.test(f)) return [2, n];
    return [1, -n];
  };

  function floors() { // 결함이 있는 층 + 관리대장 층수로 만든 층(전회차 결함이 없는 층에도 신규를 넣을 수 있게)
    const map = new Map();
    for (const d of data.defects) {
      const f = map.get(d.floor) || { total: 0, left: 0 };
      f.total += 1;
      f.left += d.check ? 0 : 1;
      map.set(d.floor, f);
    }
    for (const f of data.floors || []) if (!map.has(f)) map.set(f, { total: 0, left: 0 });
    return new Map([...map.entries()].sort((a, b) => {
      const x = floorKey(a[0]), y = floorKey(b[0]);
      return x[0] - y[0] || x[1] - y[1];
    }));
  }

  function drawSummary() {
    const s = data.summary;
    const off = data.defects.filter((d) => outOfList("member", d.member) || outOfList("dtype", d.dtype) || !["구조체", "비구조체"].includes(d.part)).length;
    document.getElementById("sf-sum").innerHTML = `<b>${esc(data.report.facility)} · ${data.report.year}년 ${esc(data.report.half)}</b>
      <span>확인 ${s.total - s.unchecked} / ${s.total}</span>
      <span class="ok">그대로 ${s.same}</span><span class="grew">진행 ${s.grew}</span><span class="rep">보수 ${s.repaired}</span><span class="new">신규 ${s.new}</span>
      <button type="button" class="secondary sf-cause-ai" title="원인이 비었거나 뭉뚱그린 낱말인 결함만 AI가 사진을 보고 구체적으로 — 카드에서 다시 고칠 수 있음">🤖 원인 추천</button>
      ${off ? `<div class="sf-offbar">⚠ 목록에 없는 이름 ${off}건(지난 보고서 이름) <button type="button" class="secondary btn-sm sf-remap">🤖 한꺼번에 정리</button></div>` : ""}`;
    document.querySelector(".sf-cause-ai").addEventListener("click", suggestCauses);
    document.querySelector(".sf-remap")?.addEventListener("click", remapNames);
  }

  async function remapNames(e) { // 목록 밖 이름 — 조합별로 AI 제안 → 점검자가 확인·고쳐서 한꺼번에
    const btn = e.target;
    btn.disabled = true;
    btn.textContent = "🤖 제안 만드는 중…";
    let r;
    try { r = await apiPost(`/sitok/reports/${rid}/defects/remap/suggest`); } catch (x) { err(x); btn.disabled = false; btn.textContent = "🤖 한꺼번에 정리"; return; }
    btn.disabled = false;
    btn.textContent = "🤖 한꺼번에 정리";
    const ov = document.createElement("div");
    ov.className = "mail-overlay";
    ov.innerHTML = `<div class="mail-box sf-new sf-remap-box" role="dialog" aria-modal="true"><div class="mail-head"><b>목록에 없는 이름 정리 — ${r.combos.length}가지</b>
      <span class="mail-sub">AI가 고른 목록 이름입니다. 맞는지 보고 고친 뒤 [바꾸기] — 현장에서 사진을 보며 카드 ✏️로 하나씩 다시 고칠 수 있습니다.</span></div>
      <div class="sf-remap-list">${r.combos.map((c, i) => `<div class="sf-remap-row" data-i="${i}">
        <div class="sf-remap-from">${esc(c.part || "-")} · ${esc(c.member || "-")} · <b>${esc(c.dtype || "-")}</b> <small>${c.count}건</small></div>
        <div class="sf-remap-to"><span>→</span><select class="m-part"><option>구조체</option><option>비구조체</option></select>
          <select class="m-member"></select><select class="m-dtype"></select></div></div>`).join("")}</div>
      <div class="mail-msg" hidden></div>
      <div class="mail-foot"><button type="button" class="mail-cancel">취소</button><button type="button" class="mail-primary m-ok">바꾸기</button></div></div>`;
    document.body.appendChild(ov);
    ov.querySelectorAll(".sf-remap-row").forEach((row) => {
      const c = r.combos[Number(row.dataset.i)];
      const q = (s) => row.querySelector(s);
      q(".m-part").value = c.to.part;
      setPick(q(".m-member"), "member", c.to.member);
      setPick(q(".m-dtype"), "dtype", c.to.dtype);
      bindPicker(q(".m-member"), "member", (m) => { if (partOf(m)) q(".m-part").value = partOf(m); });
      bindPicker(q(".m-dtype"), "dtype");
    });
    ov.querySelector(".mail-cancel").addEventListener("click", () => ov.remove());
    ov.querySelector(".m-ok").addEventListener("click", async () => {
      const maps = [...ov.querySelectorAll(".sf-remap-row")].map((row) => {
        const c = r.combos[Number(row.dataset.i)];
        return { part: c.part, member: c.member, dtype: c.dtype,
          to: { part: row.querySelector(".m-part").value, member: row.querySelector(".m-member").value, dtype: row.querySelector(".m-dtype").value } };
      });
      if (maps.some((m) => !m.to.dtype)) { alert("결함유형을 모두 골라 주세요."); return; }
      try {
        const res = await apiPost(`/sitok/reports/${rid}/defects/remap`, { maps });
        ov.remove();
        await refresh();
        alert(`${res.changed}건 바꿨습니다.`);
      } catch (x) { const m = ov.querySelector(".mail-msg"); m.hidden = false; m.className = "mail-msg bad"; m.textContent = x.message; }
    });
  }

  function drawFloors() {
    const map = floors();
    if (!map.has(floor)) floor = [...map.keys()][0] || "";
    document.getElementById("sf-floors").innerHTML = [...map.entries()].map(([f, c]) =>
      `<button type="button" class="sf-floor${f === floor ? " on" : ""}" data-f="${esc(f)}">${esc(f)}<small>${!c.total ? "-" : c.left ? `${c.left} 남음` : "✓"}</small></button>`).join("");
    document.querySelectorAll(".sf-floor").forEach((b) => b.addEventListener("click", () => {
      floor = b.dataset.f;
      try { sessionStorage.setItem(`sf-floor-${rid}`, floor); } catch (_) { /* */ }
      drawFloors();
      drawList();
      window.scrollTo({ top: 0 });
    }));
  }

  function card(d) {
    const el = document.createElement("div");
    el.className = `sf-card c-${d.check || "none"}`;
    const prev = d.prev ? `<div class="sf-prev">전회차: ${esc(d.prev["결함유형"] || "")} ${esc(sizeText(d.prev))} <em>${esc(d.prev["비고"] || "")}</em></div>` : "";
    const off = outOfList("member", d.member) || outOfList("dtype", d.dtype);
    el.innerHTML = `<div class="sf-card-head"><span class="sf-no">${d.seq}</span>
        <b>${esc(d.member)} · ${esc(d.dtype)}</b><span class="sf-part">${esc(d.part)}</span>
        ${off ? '<span class="sf-off" title="목록에 없는 이름 — ✏️를 눌러 목록에서 고르세요">목록 밖</span>' : ""}
        <button type="button" class="sf-edit" title="구분·부재·결함유형 고치기">✏️</button>
        <button type="button" class="sf-star${d.starred ? " on" : ""}" title="비교 사진대장에 꼭 넣기">★</button></div>
      ${prev}
      <div class="sf-photos">
        <figure>${d.has_prev_photo ? `<img src="${BASE}/api/sitok/defects/${d.id}/photo/prev" alt="전회차" loading="lazy" />` : '<div class="sf-nophoto">전회차 사진 없음</div>'}<figcaption>전회차</figcaption></figure>
        <figure><label class="sf-shot">${d.has_photo ? `<img src="${BASE}/api/sitok/defects/${d.id}/photo/now?t=${d.ts}" alt="이번" />` : '<span>📷 찍기</span>'}
          <input type="file" accept="image/*" capture="environment" hidden data-kr-file="1" /></label><figcaption>이번</figcaption></figure>
      </div>
      <div class="sf-acts">
        <button type="button" data-c="same" class="${d.check === "same" ? "on" : ""}">그대로</button>
        <button type="button" data-c="grew" class="${d.check === "grew" ? "on" : ""}">진행</button>
        <button type="button" data-c="repaired" class="${d.check === "repaired" ? "on" : ""}">보수 완료</button>
      </div>
      <div class="sf-size"${d.check === "grew" || d.check === "new" ? "" : " hidden"}>
        <label>개수<input inputmode="decimal" data-k="count" value="${esc(d.count)}" /></label>
        <label>폭${d.dtype && AREA_RE.test(d.dtype) ? "(m)" : "(mm)"}<input inputmode="decimal" data-k="width" value="${esc(d.width)}" /></label>
        <label>길이(m)<input inputmode="decimal" data-k="length" value="${esc(d.length)}" /></label>
        ${d.dtype && DEPTH_RE.test(d.dtype) ? `<label>깊이(mm)<input inputmode="decimal" data-k="depth" value="${esc(d.depth)}" placeholder="파인 깊이" /></label>` : ""}
        <span class="sf-qty">${d.qty ? `물량 ${esc(d.qty)}` : ""}</span>
      </div>
      ${d.check === "repaired" || isRecord(d.dtype) ? "" : `<div class="sf-cause"><label>원인<input data-k="cause" value="${esc(d.cause)}" placeholder="결함원인(구체적으로)" /></label>
        <span class="sf-prog${d.progress === "진행성" ? " on" : ""}">${esc(d.progress || "")}</span></div>
        ${d.cause_note ? `<div class="sf-cause-note">근거: ${esc(d.cause_note)}</div>` : ""}`}
      ${d.has_photo && d.check !== "repaired" ? `<div class="sf-ai"><button type="button" class="secondary btn-sm sf-ai-btn">🤖 ${d.has_prev_photo ? "전회차와 비교" : "폭 추천"}</button><span class="sf-ai-msg"></span></div>` : ""}
      ${d.check ? `<div class="sf-by">${esc(d.checked_by)} 확인${d.check === "new" ? ' · <button type="button" class="sf-del">지우기</button>' : ""}</div>` : ""}`;
    const save = async (body) => {
      try {
        const nd = await apiPatch(`/sitok/defects/${d.id}`, body);
        Object.assign(d, nd);
        await refresh(false);
      } catch (e) { err(e); }
    };
    el.querySelectorAll(".sf-acts button").forEach((b) => b.addEventListener("click", () => save({ check: d.check === b.dataset.c ? "" : b.dataset.c })));
    el.querySelector(".sf-ai-btn")?.addEventListener("click", async (e) => {
      const btn = e.target;
      const msg = el.querySelector(".sf-ai-msg");
      btn.disabled = true;
      msg.textContent = "사진 보는 중…";
      try {
        const r = await apiPost(`/sitok/defects/${d.id}/analyze`);
        const what = r.grew === true ? "커짐(진행) 같음" : r.grew === false ? "전회차와 비슷함(그대로)" : "";
        msg.innerHTML = `${esc([what, r.width ? `폭 약 ${r.width}mm` : "", r.note].filter(Boolean).join(" · "))}
          ${r.grew === true ? '<button type="button" class="link-btn" data-a="grew">진행으로</button>' : r.grew === false ? '<button type="button" class="link-btn" data-a="same">그대로로</button>' : ""}
          ${r.width ? `<button type="button" class="link-btn" data-a="w">폭 ${r.width} 넣기</button>` : ""}`;
        msg.querySelectorAll(".link-btn").forEach((b) => b.addEventListener("click", () => {
          if (b.dataset.a === "w") save({ check: d.check === "same" || !d.check ? "grew" : d.check, width: r.width });
          else save({ check: b.dataset.a });
        }));
      } catch (err) { msg.textContent = err.message; }
      btn.disabled = false;
    });
    el.querySelector(".sf-cause input")?.addEventListener("change", (e) => save({ cause: e.target.value }));
    el.querySelectorAll(".sf-size input").forEach((inp) => inp.addEventListener("change", () => save({ [inp.dataset.k]: inp.value })));
    el.querySelector(".sf-star").addEventListener("click", () => save({ starred: !d.starred }));
    el.querySelector(".sf-edit").addEventListener("click", () => editKinds(d));
    el.querySelector(".sf-del")?.addEventListener("click", async () => {
      if (!confirm("이 신규 결함을 지울까요?")) return;
      try { await api(`/sitok/defects/${d.id}`, { method: "DELETE" }); refresh(); } catch (e) { err(e); }
    });
    const file = el.querySelector(".sf-shot input");
    file.addEventListener("change", async () => {
      if (!file.files[0]) return;
      el.classList.add("busy");
      try {
        const fd = new FormData();
        fd.append("file", file.files[0]);
        await apiUpload(`/sitok/defects/${d.id}/photo`, fd);
        refresh(false);
      } catch (e) { err(e); el.classList.remove("busy"); }
    });
    enableFileDrop(el.querySelector(".sf-shot"), file);
    el.querySelectorAll(".sf-photos img").forEach((img) => img.addEventListener("click", (e) => {
      if (img.closest(".sf-shot")) return; // 이번 사진 칸은 누르면 다시 찍기
      e.preventDefault();
      window.open(img.src, "_blank");
    }));
    return el;
  }

  function drawList() {
    const box = document.getElementById("sf-list");
    box.innerHTML = "";
    const rows = data.defects.filter((d) => d.floor === floor);
    if (!rows.length) box.innerHTML = `<div class="sf-none">${esc(floor || "이 층")}에는 아직 결함이 없습니다 — 아래 [+ 신규 결함]에서 사진을 찍으면 AI가 채웁니다.</div>`;
    rows.forEach((d) => box.appendChild(card(d)));
  }

  function newForm() {
    const overlay = document.createElement("div");
    overlay.className = "mail-overlay";
    const floorsList = [...floors().keys()];
    overlay.innerHTML = `<div class="mail-box sf-new" role="dialog" aria-modal="true">
      <div class="mail-head"><b>+ 신규 결함</b><span class="mail-sub">사진을 찍으면 AI가 부재·결함유형·원인·폭을 채웁니다 — 확인하고 개수·길이만</span></div>
      <label class="sf-newshot"><input type="file" accept="image/*" capture="environment" class="n-photo" hidden data-kr-file="1" />
        <span class="n-preview">📷 사진 찍기</span></label>
      <div class="n-ai" hidden></div>
      <label>층<input list="sf-fl" class="n-floor" value="${esc(floor)}" /></label><datalist id="sf-fl">${floorsList.map((f) => `<option value="${esc(f)}">`).join("")}</datalist>
      <div class="sf-two"><label>구분<select class="n-part"><option>비구조체</option><option>구조체</option></select></label>
        <label>부재<select class="n-member"></select></label></div>
      <label>결함유형<select class="n-dtype"></select></label>
      <div class="n-suggest" hidden></div>
      <label>원인<input class="n-cause" placeholder="사진을 찍으면 AI가 구체적으로 — 직접 써도 됩니다" /></label>
      <div class="sf-cause-note n-cause-note" hidden></div>
      <div class="n-bands"><span>균열 폭(mm)</span>${["0.1", "0.2", "0.3", "0.5", "1.0"].map((w) => `<button type="button" data-w="${w}">${w === "1.0" ? "1.0↑" : w}</button>`).join("")}</div>
      <div class="sf-size"><label>개수<input inputmode="decimal" class="n-count" value="1" /></label><label>폭<input inputmode="decimal" class="n-width" /></label>
        <label>길이(m)<input inputmode="decimal" class="n-length" /></label>
        <label class="n-depth-box" hidden>깊이(mm)<input inputmode="decimal" class="n-depth" placeholder="파인 깊이" /></label></div>
      <div class="mail-msg" hidden></div>
      <div class="mail-foot"><button type="button" class="mail-cancel">취소</button><button type="button" class="mail-primary n-ok">추가</button></div></div>`;
    document.body.appendChild(overlay);
    const q = (s) => overlay.querySelector(s);
    let ai = null; // AI 답(원인 근거는 원인을 안 고쳤을 때만 같이 저장)
    setPick(q(".n-member"), "member", "");
    setPick(q(".n-dtype"), "dtype", "");
    bindPicker(q(".n-member"), "member", (m) => { if (partOf(m)) q(".n-part").value = partOf(m); });
    bindPicker(q(".n-dtype"), "dtype");
    const depthBox = () => { q(".n-depth-box").hidden = !DEPTH_RE.test(q(".n-dtype").value || ""); }; // 박리·박락·층분리만 깊이 칸
    q(".n-dtype").addEventListener("change", depthBox);
    const suggest = (a) => { // 목록에 맞는 게 없을 때 AI 제안 → [이 보고서에만] [회사 목록에] 또는 목록에서 고르기
      const box = q(".n-suggest");
      const rows = [["member", a.new_member], ["dtype", a.new_dtype]].filter(([, v]) => v);
      box.hidden = !rows.length;
      box.innerHTML = rows.map(([k, v]) => `<div data-k="${k}" data-v="${esc(v)}">🤖 목록에 맞는 ${KIND_LABEL[k]}이 없어 AI 제안: <b>${esc(v)}</b>
        <span><button type="button" class="link-btn" data-s="report">이 보고서에만 추가</button> · <button type="button" class="link-btn" data-s="company">회사 목록에 추가</button>
        · 또는 위 목록에서 고르기</span></div>`).join("");
      box.querySelectorAll("button").forEach((b) => b.addEventListener("click", async () => {
        const row = b.closest("[data-k]");
        try {
          const name = await addVocab(row.dataset.k, row.dataset.v, b.dataset.s);
          if (!name) return;
          const sel = q(row.dataset.k === "member" ? ".n-member" : ".n-dtype");
          setPick(sel, row.dataset.k, name);
          if (row.dataset.k === "member" && partOf(name)) q(".n-part").value = partOf(name);
          row.remove();
          box.hidden = !box.children.length;
        } catch (e) { alert(e.message); }
      }));
    };
    const setBand = (w) => {
      q(".n-width").value = w;
      overlay.querySelectorAll(".n-bands button").forEach((b) => b.classList.toggle("on", b.dataset.w === w));
    };
    overlay.querySelectorAll(".n-bands button").forEach((b) => b.addEventListener("click", () => setBand(b.dataset.w)));
    q(".n-width").addEventListener("input", () => overlay.querySelectorAll(".n-bands button").forEach((b) => b.classList.toggle("on", b.dataset.w === q(".n-width").value.trim())));
    const photo = q(".n-photo");
    photo.addEventListener("change", async () => {
      const f = photo.files[0];
      if (!f) return;
      q(".n-preview").innerHTML = `<img src="${URL.createObjectURL(f)}" alt="" />`;
      const box = q(".n-ai");
      box.hidden = false;
      box.className = "n-ai busy";
      box.textContent = "🤖 AI가 사진을 보는 중…(5~15초) — 그동안 개수·길이를 넣어도 됩니다";
      try {
        const fd = new FormData();
        fd.append("file", f);
        const a = await apiUpload(`/sitok/reports/${rid}/defects/analyze?floor=${encodeURIComponent(q(".n-floor").value.trim())}`, fd);
        const fill = (sel, v) => { if (v && !q(sel).value.trim()) q(sel).value = v; };
        const pick = (sel, kind, v) => { if (v && !q(sel).value) setPick(q(sel), kind, v); };
        ai = a;
        q(".n-part").value = a.part;
        pick(".n-member", "member", a.member);
        pick(".n-dtype", "dtype", a.dtype);
        depthBox();
        suggest(a);
        fill(".n-cause", a.cause);
        if (a.cause_note && q(".n-cause").value.trim() === a.cause) {
          const note = q(".n-cause-note");
          note.hidden = false;
          note.textContent = `근거: ${a.cause_note}`;
        }
        if (a.width && !q(".n-width").value.trim()) setBand(a.width);
        if (a.count && q(".n-count").value === "1") q(".n-count").value = a.count;
        box.className = `n-ai${a.is_defect ? "" : " warn"}`;
        box.textContent = `🤖 ${a.is_defect ? "" : "결함이 아니라 기록용 사진 같습니다 — "}${a.note || "채웠습니다"} · 맞는지 확인하세요`
          + (a.learned ? `\n📚 ${a.learned}` : ""); // 회사 교정 기록을 보고 분류를 바꿨으면(10/12)
      } catch (e) { box.className = "n-ai warn"; box.textContent = `AI 분석 실패 — 직접 넣어 주세요 (${e.message})`; }
    });
    enableFileDrop(q(".sf-newshot"), photo);
    q(".mail-cancel").addEventListener("click", () => overlay.remove());
    q(".n-ok").addEventListener("click", async () => {
      const body = { floor: q(".n-floor").value.trim(), part: q(".n-part").value, member: q(".n-member").value, dtype: q(".n-dtype").value,
        cause: q(".n-cause").value.trim(), count: q(".n-count").value.trim(), width: q(".n-width").value.trim(), length: q(".n-length").value.trim(),
        depth: q(".n-depth").value.trim() };
      body.cause_note = ai && ai.cause_note && body.cause === ai.cause ? ai.cause_note : ""; // 원인을 고쳤으면 AI 근거는 안 맞음
      body.ai_guess = ai && ai.guess ? ai.guess : null; // AI 첫 분류 — 다르게 넣으면 회사 교정 기록(다음 사진 분석에 씀, 10/12)
      if (!body.floor || !body.dtype) { alert("층과 결함유형을 골라 주세요."); return; }
      q(".n-ok").disabled = true;
      try {
        const d = await apiPost(`/sitok/reports/${rid}/defects`, body);
        const f = photo.files[0];
        if (f) { const fd = new FormData(); fd.append("file", f); await apiUpload(`/sitok/defects/${d.id}/photo`, fd); }
        floor = body.floor;
        started = true;
        overlay.remove();
        refresh();
      } catch (e) { q(".n-ok").disabled = false; const m = q(".mail-msg"); m.hidden = false; m.className = "mail-msg bad"; m.textContent = e.message; }
    });
  }

  async function suggestCauses(e) {
    if (!confirm("AI가 결함 사진을 보고, 원인이 비었거나 뭉뚱그린 낱말(노후화·건조수축균열 등)인 결함만 구체적인 원인과 근거로 바꿉니다"
      + "(결함 수에 따라 1~3분, 점검자가 직접 쓴 구체적인 원인은 그대로). 할까요?")) return;
    const btn = e.target;
    btn.disabled = true;
    btn.textContent = "🤖 추천 중…";
    try {
      const r = await apiPost(`/sitok/reports/${rid}/defects/causes`);
      await refresh();
      const overlay = document.createElement("div");
      overlay.className = "mail-overlay";
      overlay.innerHTML = `<div class="mail-box sf-new" role="dialog" aria-modal="true"><div class="mail-head"><b>🤖 원인 추천 — ${r.asked ?? r.changed.length}건 중 ${r.changed.length}건 바꿈</b>
        <span class="mail-sub">맞지 않으면 그 카드의 원인 칸에서 고치세요</span></div>
        <div class="sf-cause-list">${r.changed.map((c) => `<div><b>${esc(c.floor)} ${c.seq}</b> ${esc(c.what)} — <s>${esc(c.before || "(없음)")}</s> → <em>${esc(c.after)}</em>
          ${c.note ? `<small>${esc(c.note)}</small>` : ""}</div>`).join("") || "바꿀 원인이 없습니다."}</div>
        <div class="mail-foot"><button type="button" class="mail-primary">확인</button></div></div>`;
      document.body.appendChild(overlay);
      overlay.querySelector("button").addEventListener("click", () => overlay.remove());
    } catch (err) { showError(errorEl, err); btn.disabled = false; btn.textContent = "🤖 원인 추천"; }
  }

  function pollImport() { // 타회사 PDF는 AI가 1~3분 — 4초마다 확인
    const msg = document.getElementById("sf-pdf-msg");
    const tick = async () => {
      try {
        const d = await api(`/sitok/reports/${rid}/defects`);
        if (d.importing && d.importing.state === "running") { msg.textContent = `${d.importing.msg} …`; setTimeout(tick, 4000); return; }
        if (d.importing && d.importing.state === "failed") { msg.textContent = d.importing.msg; return; }
        refresh();
      } catch (e) { msg.textContent = e.message; }
    };
    setTimeout(tick, 4000);
  }

  async function refresh(redraw = true) {
    try {
      data = await api(`/sitok/reports/${rid}/defects`);
      document.getElementById("sf-title").textContent = `${data.report.year}년 ${data.report.half} 현장 조사`;
      const link = document.getElementById("sf-fac-link");
      link.textContent = data.report.facility;
      link.href = `sitok-facility.html?id=${data.report.facility_id}`;
      const empty = !data.defects.length && !started;
      document.getElementById("sf-empty").hidden = !empty;
      document.getElementById("sf-main").hidden = empty;
      if (empty) {
        if (data.importing) {
          document.getElementById("sf-pdf-msg").textContent = data.importing.msg;
          if (data.importing.state === "running") pollImport();
        }
        return;
      }
      drawSummary();
      drawFloors();
      if (redraw) drawList();
      else { // 지금 보는 카드만 다시(스크롤 유지)
        const box = document.getElementById("sf-list");
        const cards = [...box.children];
        const rows = data.defects.filter((d) => d.floor === floor);
        if (cards.length !== rows.length) drawList();
        else rows.forEach((d, i) => box.replaceChild(card(d), cards[i]));
      }
    } catch (e) { err(e); }
  }

  const pdf = document.getElementById("sf-pdf");
  pdf.addEventListener("change", async () => {
    if (!pdf.files[0]) return;
    const msg = document.getElementById("sf-pdf-msg");
    msg.textContent = `${pdf.files[0].name} 읽는 중…`;
    try {
      const fd = new FormData();
      fd.append("file", pdf.files[0]);
      const r = await apiUpload(`/sitok/reports/${rid}/defects/import`, fd);
      if (r.importing) { msg.textContent = r.importing.msg; pollImport(); } else refresh();
    } catch (e) { msg.textContent = `읽지 못했습니다: ${e.message}`; }
  });
  enableFileDrop(pdf.closest(".sk-drop"), pdf);
  document.getElementById("sf-carry").addEventListener("click", async () => {
    try { await apiPost(`/sitok/reports/${rid}/defects/carry`); refresh(); } catch (e) { err(e); }
  });
  document.getElementById("sf-add").addEventListener("click", newForm);
  document.getElementById("sf-fresh").addEventListener("click", () => {
    started = true;
    try { sessionStorage.setItem(`sf-started-${rid}`, "1"); } catch (_) { /* */ }
    refresh();
  });
  refresh();
})();
