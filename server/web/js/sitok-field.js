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
  let data = null;
  let floor = "";
  try { floor = sessionStorage.getItem(`sf-floor-${rid}`) || ""; } catch (_) { /* 기억 못 해도 됨 */ }

  const sizeText = (v) => {
    if (!v) return "";
    const parts = [v.count || v["개수"] ? `${v.count || v["개수"]}개` : "", v.width || v["폭"] ? `폭 ${v.width || v["폭"]}` : "",
      v.length || v["길이"] ? `길이 ${v.length || v["길이"]}m` : ""].filter(Boolean);
    return parts.join(" · ");
  };

  function floors() {
    const map = new Map();
    for (const d of data.defects) {
      const f = map.get(d.floor) || { total: 0, left: 0 };
      f.total += 1;
      f.left += d.check ? 0 : 1;
      map.set(d.floor, f);
    }
    return map;
  }

  function drawSummary() {
    const s = data.summary;
    document.getElementById("sf-sum").innerHTML = `<b>${esc(data.report.facility)} · ${data.report.year}년 ${esc(data.report.half)}</b>
      <span>확인 ${s.total - s.unchecked} / ${s.total}</span>
      <span class="ok">그대로 ${s.same}</span><span class="grew">진행 ${s.grew}</span><span class="rep">보수 ${s.repaired}</span><span class="new">신규 ${s.new}</span>`;
  }

  function drawFloors() {
    const map = floors();
    if (!map.has(floor)) floor = [...map.keys()][0] || "";
    document.getElementById("sf-floors").innerHTML = [...map.entries()].map(([f, c]) =>
      `<button type="button" class="sf-floor${f === floor ? " on" : ""}" data-f="${esc(f)}">${esc(f)}<small>${c.left ? `${c.left} 남음` : "✓"}</small></button>`).join("");
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
      ${d.check ? `<div class="sf-by">${esc(d.checked_by)} 확인${d.check === "new" ? ' · <button type="button" class="sf-del">지우기</button>' : ""}</div>` : ""}`;
    const save = async (body) => {
      try {
        const nd = await apiPatch(`/sitok/defects/${d.id}`, body);
        Object.assign(d, nd);
        await refresh(false);
      } catch (e) { err(e); }
    };
    el.querySelectorAll(".sf-acts button").forEach((b) => b.addEventListener("click", () => save({ check: d.check === b.dataset.c ? "" : b.dataset.c })));
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
    data.defects.filter((d) => d.floor === floor).forEach((d) => box.appendChild(card(d)));
  }

  function newForm() {
    const overlay = document.createElement("div");
    overlay.className = "mail-overlay";
    const floorsList = [...floors().keys()];
    overlay.innerHTML = `<div class="mail-box sf-new" role="dialog" aria-modal="true">
      <div class="mail-head"><b>+ 신규 결함</b><span class="mail-sub">전회차에 없던 결함 — 번호는 그 층 마지막 다음</span></div>
      <label>층<input list="sf-fl" class="n-floor" value="${esc(floor)}" /></label><datalist id="sf-fl">${floorsList.map((f) => `<option value="${esc(f)}">`).join("")}</datalist>
      <label>구분<select class="n-part"><option>비구조체</option><option>구조체</option></select></label>
      <label>부재<input list="sf-mem" class="n-member" /></label><datalist id="sf-mem">${MEMBERS.map((m) => `<option value="${m}">`).join("")}</datalist>
      <label>결함유형<input list="sf-typ" class="n-dtype" /></label><datalist id="sf-typ">${TYPES.map((m) => `<option value="${m}">`).join("")}</datalist>
      <div class="sf-size"><label>개수<input inputmode="decimal" class="n-count" value="1" /></label><label>폭<input inputmode="decimal" class="n-width" /></label>
        <label>길이(m)<input inputmode="decimal" class="n-length" /></label></div>
      <label class="sf-newphoto">📷 사진<input type="file" accept="image/*" capture="environment" class="n-photo" /></label>
      <div class="mail-msg" hidden></div>
      <div class="mail-foot"><button type="button" class="mail-cancel">취소</button><button type="button" class="mail-primary n-ok">추가</button></div></div>`;
    document.body.appendChild(overlay);
    const q = (s) => overlay.querySelector(s);
    q(".mail-cancel").addEventListener("click", () => overlay.remove());
    q(".n-ok").addEventListener("click", async () => {
      const body = { floor: q(".n-floor").value.trim(), part: q(".n-part").value, member: q(".n-member").value.trim(), dtype: q(".n-dtype").value.trim(),
        count: q(".n-count").value.trim(), width: q(".n-width").value.trim(), length: q(".n-length").value.trim() };
      if (!body.floor || !body.dtype) { alert("층과 결함유형을 넣어 주세요."); return; }
      q(".n-ok").disabled = true;
      try {
        const d = await apiPost(`/sitok/reports/${rid}/defects`, body);
        const f = q(".n-photo").files[0];
        if (f) { const fd = new FormData(); fd.append("file", f); await apiUpload(`/sitok/defects/${d.id}/photo`, fd); }
        floor = body.floor;
        overlay.remove();
        refresh();
      } catch (e) { q(".n-ok").disabled = false; const m = q(".mail-msg"); m.hidden = false; m.className = "mail-msg bad"; m.textContent = e.message; }
    });
  }

  async function refresh(redraw = true) {
    try {
      data = await api(`/sitok/reports/${rid}/defects`);
      document.getElementById("sf-title").textContent = `${data.report.year}년 ${data.report.half} 현장 조사`;
      const link = document.getElementById("sf-fac-link");
      link.textContent = data.report.facility;
      link.href = `sitok-facility.html?id=${data.report.facility_id}`;
      const empty = !data.defects.length;
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
  refresh();
})();
