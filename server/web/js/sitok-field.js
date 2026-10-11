// 시특법 현장 조사(sitok-field.html?report=, 2026-10-10 5단계) — 폰 우선. 층을 고르면 전회차 결함이 번호 순으로, 전회차 사진 옆에 이번 사진.
// [그대로] = 전회차 크기 그대로(비고 기존) · [진행] = 크기 다시(기존) · [보수] = 보수 완료(비고 보수) · ⭐ = 비교 사진대장에 꼭 넣기. [+ 신규] = 못 보던 결함.
// 서버 server/api/routers/sitok_defects.py.

(function () {
  const rid = Number(new URLSearchParams(location.search).get("report")) || null;
  const errorEl = document.getElementById("error");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const err = (e) => showError(errorEl, e);
  const MEMBERS = ["슬라브", "보", "기둥", "내력벽", "조적벽", "파라펫", "마감재", "계단", "강재", "난간", "옹벽", "바닥"];
  const TYPES = ["미장균열", "수직균열", "수평균열", "경사균열", "조적균열", "개구부균열", "누수·백태", "누수흔적", "박리", "박락", "도장박리", "철근노출", "부식", "이격", "파손"];
  const CAUSES = ["건조수축균열", "온도균열", "시공불량", "노후화", "균열부누수", "방수층 노후", "배수불량", "피복두께 부족", "중성화", "동결융해", "외력·충격", "부등침하", "과하중"];
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
    document.getElementById("sf-sum").innerHTML = `<b>${esc(data.report.facility)} · ${data.report.year}년 ${esc(data.report.half)}</b>
      <span>확인 ${s.total - s.unchecked} / ${s.total}</span>
      <span class="ok">그대로 ${s.same}</span><span class="grew">진행 ${s.grew}</span><span class="rep">보수 ${s.repaired}</span><span class="new">신규 ${s.new}</span>
      <button type="button" class="secondary sf-cause-ai" title="비었거나 결함 종류와 안 맞는 원인만 AI가 채움 — 카드에서 다시 고칠 수 있음">🤖 원인 추천</button>`;
    document.querySelector(".sf-cause-ai").addEventListener("click", suggestCauses);
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
    el.innerHTML = `<div class="sf-card-head"><span class="sf-no">${d.seq}</span>
        <b>${esc(d.member)} · ${esc(d.dtype)}</b><span class="sf-part">${esc(d.part)}</span>
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
        <label>폭${d.dtype && /누수|백태|박리|박락|철근|부식|파손/.test(d.dtype) ? "(m)" : "(mm)"}<input inputmode="decimal" data-k="width" value="${esc(d.width)}" /></label>
        <label>길이(m)<input inputmode="decimal" data-k="length" value="${esc(d.length)}" /></label>
        <span class="sf-qty">${d.qty ? `물량 ${esc(d.qty)}` : ""}</span>
      </div>
      ${d.check === "repaired" || /현황\s*$/.test(d.dtype || "") ? "" : `<div class="sf-cause"><label>원인<input list="sf-causes" data-k="cause" value="${esc(d.cause)}" placeholder="결함원인" /></label>
        <span class="sf-prog${d.progress === "진행성" ? " on" : ""}">${esc(d.progress || "")}</span></div>`}
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
        <label>부재<input list="sf-mem" class="n-member" /></label></div><datalist id="sf-mem">${(data.members || MEMBERS).map((m) => `<option value="${m}">`).join("")}</datalist>
      <div class="sf-two"><label>결함유형<input list="sf-typ" class="n-dtype" /></label>
        <label>원인<input list="sf-causes" class="n-cause" /></label></div><datalist id="sf-typ">${(data.types || TYPES).map((m) => `<option value="${m}">`).join("")}</datalist>
      <div class="n-bands"><span>균열 폭(mm)</span>${["0.1", "0.2", "0.3", "0.5", "1.0"].map((w) => `<button type="button" data-w="${w}">${w === "1.0" ? "1.0↑" : w}</button>`).join("")}</div>
      <div class="sf-size"><label>개수<input inputmode="decimal" class="n-count" value="1" /></label><label>폭<input inputmode="decimal" class="n-width" /></label>
        <label>길이(m)<input inputmode="decimal" class="n-length" /></label></div>
      <div class="mail-msg" hidden></div>
      <div class="mail-foot"><button type="button" class="mail-cancel">취소</button><button type="button" class="mail-primary n-ok">추가</button></div></div>`;
    document.body.appendChild(overlay);
    const q = (s) => overlay.querySelector(s);
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
        q(".n-part").value = a.part;
        fill(".n-member", a.member);
        fill(".n-dtype", a.dtype);
        fill(".n-cause", a.cause);
        if (a.width && !q(".n-width").value.trim()) setBand(a.width);
        if (a.count && q(".n-count").value === "1") q(".n-count").value = a.count;
        box.className = `n-ai${a.is_defect ? "" : " warn"}`;
        box.textContent = `🤖 ${a.is_defect ? "" : "결함이 아니라 기록용 사진 같습니다 — "}${a.note || "채웠습니다"} · 맞는지 확인하세요`;
      } catch (e) { box.className = "n-ai warn"; box.textContent = `AI 분석 실패 — 직접 넣어 주세요 (${e.message})`; }
    });
    enableFileDrop(q(".sf-newshot"), photo);
    q(".mail-cancel").addEventListener("click", () => overlay.remove());
    q(".n-ok").addEventListener("click", async () => {
      const body = { floor: q(".n-floor").value.trim(), part: q(".n-part").value, member: q(".n-member").value.trim(), dtype: q(".n-dtype").value.trim(),
        cause: q(".n-cause").value.trim(), count: q(".n-count").value.trim(), width: q(".n-width").value.trim(), length: q(".n-length").value.trim() };
      if (!body.floor || !body.dtype) { alert("층과 결함유형을 넣어 주세요."); return; }
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
    if (!confirm("AI가 결함 목록을 보고 비었거나 결함 종류와 안 맞는 원인을 채웁니다(20~60초). 할까요?")) return;
    const btn = e.target;
    btn.disabled = true;
    btn.textContent = "🤖 추천 중…";
    try {
      const r = await apiPost(`/sitok/reports/${rid}/defects/causes`);
      await refresh();
      const overlay = document.createElement("div");
      overlay.className = "mail-overlay";
      overlay.innerHTML = `<div class="mail-box sf-new" role="dialog" aria-modal="true"><div class="mail-head"><b>🤖 원인 추천 — ${r.changed.length}건 바꿈</b>
        <span class="mail-sub">맞지 않으면 그 카드의 원인 칸에서 고치세요</span></div>
        <div class="sf-cause-list">${r.changed.map((c) => `<div><b>${esc(c.floor)} ${c.seq}</b> ${esc(c.what)} — <s>${esc(c.before || "(없음)")}</s> → <em>${esc(c.after)}</em></div>`).join("") || "바꿀 원인이 없습니다."}</div>
        <div class="mail-foot"><button type="button" class="mail-primary">확인</button></div></div>`;
      document.body.appendChild(overlay);
      overlay.querySelector("button").addEventListener("click", () => overlay.remove());
    } catch (err) { showError(errorEl, err); btn.disabled = false; btn.textContent = "🤖 원인 추천"; }
  }

  document.body.insertAdjacentHTML("beforeend", `<datalist id="sf-causes">${CAUSES.map((c) => `<option value="${c}">`).join("")}</datalist>`);

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
      if (empty) return;
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
      await apiUpload(`/sitok/reports/${rid}/defects/import`, fd);
      refresh();
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
