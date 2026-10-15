// report.html 스크립트 — 10번 TBM·계측자료(AI 인원 세기·값 읽기), 11번 제공자료(라이브러리·추천).
// report.html에서 순서대로 불러오는 5개 파일 중 하나(core → photos → work → support → main). 파일끼리는
// 전역 함수/상수를 공유하고, 페이지 시작 시 실행하는 호출은 전부 report-main.js 맨 아래에 모아 두었다
// (앞 파일이 뒤 파일 함수를 불러오는 시점 문제를 없애려고 — 여기엔 정의만 둔다).

// --- 10-1. TBM 교육 ---
async function setupTbm() {
  const base = `${BASE}/api/reports/${reportId}/tbm`;
  let data;
  try {
    data = await api(base);
  } catch (err) {
    showError(errorEl, err);
    return;
  }
  document.getElementById("tbm-attendee").value = data.attendee_count ?? "";
  document.getElementById("tbm-location").value = data.location || "";
  document.getElementById("tbm-content").value = data.content || "";
  document.getElementById("tbm-material").value = data.material || "";
  if (data.has_photo) {
    const thumb = document.getElementById("tbm-thumb");
    thumb.src = `${base}/photo?thumb=1`;
    thumb.style.display = "block";
    document.getElementById("tbm-del").style.display = "inline-block";
  }
  setupSinglePhotoUpload(`${base}/photo`, "tbm-file", "tbm-thumb", "tbm-del");

  // "✨ AI로 인원 세기" — 저장된 TBM 사진의 인원수(POST .../ai/tbm-people). 못 세면 지어내지 않고 안내만.
  const peopleBtn = document.getElementById("tbm-ai-people");
  peopleBtn.addEventListener("click", async () => {
    errorEl.style.display = "none";
    const statusEl = document.getElementById("tbm-status");
    if (document.getElementById("tbm-thumb").style.display === "none") {
      showError(errorEl, new Error("먼저 TBM 사진을 올려주세요."));
      return;
    }
    peopleBtn.disabled = true;
    peopleBtn.textContent = "세는 중...";
    try {
      const out = await apiPost(`${BASE}/api/reports/${reportId}/ai/tbm-people`, {});
      if (out.count == null) {
        statusEl.className = "status";
        statusEl.textContent = "사진에서 인원을 읽지 못했습니다. 참석인원을 직접 입력해주세요.";
      } else {
        document.getElementById("tbm-attendee").value = out.count;
        statusEl.className = "status ok";
        statusEl.textContent = `AI가 ${out.count}명으로 셌습니다. 확인하고 필요하면 고치세요(자동 저장됩니다).`;
        autosaveTouch(document.getElementById("tbm-attendee"));
      }
    } catch (err) {
      showError(errorEl, err);
    } finally {
      peopleBtn.disabled = false;
      peopleBtn.textContent = "✨ AI로 인원 세기";
    }
  });

  document.getElementById("tbm-save").addEventListener("click", async () => {
    errorEl.style.display = "none";
    const statusEl = document.getElementById("tbm-status");
    const attendeeVal = document.getElementById("tbm-attendee").value;
    try {
      await apiPatch(base, {
          attendee_count: attendeeVal ? Number(attendeeVal) : null,
          location: document.getElementById("tbm-location").value,
          content: document.getElementById("tbm-content").value,
          material: document.getElementById("tbm-material").value,
        });
      statusEl.textContent = "저장되었습니다.";
    } catch (err) {
      showError(errorEl, err);
    }
  });
}

// --- 10-2. 계측자료 (7종 고정) ---
// 실제로 쓰는 건 가스농도측정기·조도계뿐이라 나머지 5종은 숨김(사용자 2026-10-02). 단, 이 보고서에 이미 값·사진이 있으면
// 고치거나 지울 수 있게 보여 준다(서버 목록·보고서 양식은 7종 그대로).
const MEASUREMENT_SHOWN = ["가스농도측정기", "조도계"];
async function setupMeasurements() {
  const container = document.getElementById("measurement-list");
  const base = `${BASE}/api/reports/${reportId}/measurements`;
  let rows;
  try {
    rows = await api(base);
  } catch (err) {
    showError(errorEl, err);
    return;
  }
  for (const data of rows) {
    const type = data.instrument_type;
    if (!MEASUREMENT_SHOWN.includes(type) && !data.value && !data.has_photo && !data.manual_verdict && !data.manual_action) continue;
    const row = document.createElement("div");
    row.className = "sub-card";
    row.innerHTML = `
      <h3>${type} (${data.unit})</h3>
      <label>측정값</label>
      <input id="ms-value-${type}" value="${(data.value || "").replace(/"/g, "&quot;")}" />
      <label>판정</label>
      <select id="ms-verdict-${type}">
        <option value="">자동판정</option><option value="양호">양호</option><option value="불량">불량</option>
      </select>
      <label>조치사항</label>
      <input id="ms-action-${type}" value="${(data.manual_action || "").replace(/"/g, "&quot;")}" />
      <div class="photo-slot">
        <img class="thumb" id="ms-thumb-${type}" style="display:${data.has_photo ? "block" : "none"};"
             ${data.has_photo ? `src="${base}/${encodeURIComponent(type)}/photo?thumb=1"` : ""} />
        <div class="slot-controls">
          <div class="slot-label">측정 사진 (선택하면 바로 저장)</div>
          <input type="file" accept="image/*" id="ms-file-${type}" />
          <button type="button" class="secondary" id="ms-del-${type}" style="display:${data.has_photo ? "inline-block" : "none"};">삭제</button>
        </div>
        <button type="button" id="ms-ai-${type}" style="margin-top:0;">✨ AI로 읽기</button>
      </div>
      <button type="button" class="autosave" id="ms-save-${type}">저장</button>
      <div id="ms-status-${type}" class="status"></div>
    `;
    container.appendChild(row);
    document.getElementById(`ms-verdict-${type}`).value = data.manual_verdict || "";

    document.getElementById(`ms-save-${type}`).addEventListener("click", async () => {
      errorEl.style.display = "none";
      const statusEl = document.getElementById(`ms-status-${type}`);
      try {
        await apiPatch(`${base}/${encodeURIComponent(type)}`, {
            value: document.getElementById(`ms-value-${type}`).value,
            manual_verdict: document.getElementById(`ms-verdict-${type}`).value,
            manual_action: document.getElementById(`ms-action-${type}`).value,
          });
        statusEl.textContent = "저장되었습니다.";
      } catch (err) {
        showError(errorEl, err);
      }
    });

    setupSinglePhotoUpload(`${base}/${encodeURIComponent(type)}/photo`, `ms-file-${type}`, `ms-thumb-${type}`, `ms-del-${type}`);

    // "✨ AI로 읽기" — 저장된 계측장비 사진에서 측정값(POST .../ai/measurement/{종류}). 읽은 값으로
    // 다시 자동판정되게 판정은 "자동판정"으로 되돌린다(데스크톱과 동일, 2026-09-21 사용자 확인).
    const readBtn = document.getElementById(`ms-ai-${type}`);
    readBtn.addEventListener("click", async () => {
      errorEl.style.display = "none";
      const statusEl = document.getElementById(`ms-status-${type}`);
      if (document.getElementById(`ms-thumb-${type}`).style.display === "none") {
        showError(errorEl, new Error(`${type}: 먼저 계측장비 사진을 올려주세요.`));
        return;
      }
      readBtn.disabled = true;
      readBtn.textContent = "읽는 중...";
      try {
        const out = await apiPost(`${BASE}/api/reports/${reportId}/ai/measurement/${encodeURIComponent(type)}`, {});
        if (out.value == null) {
          statusEl.className = "status";
          statusEl.textContent = "사진에서 측정값을 읽지 못했습니다. 직접 입력해주세요.";
        } else {
          document.getElementById(`ms-value-${type}`).value = out.value;
          document.getElementById(`ms-verdict-${type}`).value = "";
          statusEl.className = "status ok";
          statusEl.textContent = `AI가 "${out.value}"로 읽었습니다. 확인하고 필요하면 고치세요(자동 저장됩니다).`;
          autosaveTouch(document.getElementById(`ms-value-${type}`));
        }
      } catch (err) {
        showError(errorEl, err);
      } finally {
        readBtn.disabled = false;
        readBtn.textContent = "✨ AI로 읽기";
      }
    });
  }
}

// --- 11. 제공자료 — 라이브러리 선택 / 직접 업로드 / 지적사항 기반 추천 (server/api/routers/materials.py) ---
// 선택이 바뀌는 API는 전부 {items, education_content}를 돌려준다 — 슬롯을 다시 그리고 10-1 교육내용
// 칸도 같이 맞춘다(서버가 이미 저장함, 데스크톱 _sync_education_content_from_materials와 같은 동작).
const matBase = `${BASE}/api/reports/${reportId}/materials`;
let matLibrary = null;
let matPickerSlot = null;
// 선택이 바뀌어 슬롯을 다시 그릴 때 사진 주소를 바꿔야 화면이 예전 사진을 재사용하지 않는다(처음 그릴 땐 비워 둬 폰에 받아 둔 사진을 씀).
let matPhotoVer = "";

function applyMaterialsChange(out) {
  matPhotoVer = `&v=${Date.now()}`;
  renderMaterials(out.items);
  document.getElementById("tbm-content").value = out.education_content;
}

function renderMaterials(items) {
  matItems = items;
  const container = document.getElementById("materials-slots");
  container.innerHTML = "";
  for (const data of items) {
    const slot = data.slot;
    const card = document.createElement("div");
    card.className = "sub-card";
    const kind = data.material_id ? "라이브러리 자료" : data.has_photo ? "직접 올린 이미지" : "비어 있음";
    if (!data.material_id && !data.has_photo && !data.title) card.dataset.empty = "1";
    card.innerHTML = `
      <h3>제공자료 ${slot} <span style="font-weight:400; color:var(--muted); font-size:12px;">· ${kind}</span></h3>
      <div class="photo-slot">
        <img class="thumb" id="mat-thumb-${slot}" style="display:${data.has_photo ? "block" : "none"}; cursor:zoom-in;"
             ${data.has_photo ? `src="${matBase}/${slot}/photo?thumb=1${matPhotoVer}"` : ""} />
        <div class="slot-controls">
          <div style="display:flex; gap:6px; flex-wrap:wrap;">
            <button type="button" id="mat-pick-${slot}" style="margin-top:0;">라이브러리에서 선택</button>
            <button type="button" class="secondary" id="mat-clear-${slot}" style="margin-top:0; display:${data.has_photo || data.title ? "inline-flex" : "none"};">비우기</button>
            ${data.has_photo && !data.material_id ? `<button type="button" class="secondary rotate-btn" id="mat-rot-${slot}" style="margin-top:0;" title="오른쪽으로 90도 돌리기">↻ 돌리기</button>` : ""}
          </div>
          <div class="slot-label">또는 직접 이미지 올리기</div>
          <input type="file" accept="image/*" id="mat-file-${slot}" />
        </div>
      </div>
      <label>제목</label>
      <div style="display:flex; gap:8px; align-items:center;">
        <input id="mat-title-${slot}" />
        <button type="button" class="autosave" id="mat-save-${slot}">제목 저장</button>
      </div>
      <div id="mat-status-${slot}" class="status"></div>
    `;
    container.appendChild(card);
    document.getElementById(`mat-title-${slot}`).value = data.title;

    // 그림을 누르면 크게 보기(js/photo-viewer.js — 다른 사진 칸과 같게, 2026-10-07). 예전엔 새 탭으로 원본
    document.getElementById(`mat-pick-${slot}`).addEventListener("click", () => openMaterialPicker(slot));
    const rotBtn = document.getElementById(`mat-rot-${slot}`); // 직접 올린 이미지만(라이브러리 자료는 공용 파일)
    if (rotBtn) rotBtn.addEventListener("click", () => rotatePhoto(rotBtn, `${matBase}/${slot}/photo/rotate`, () => {
      document.getElementById(`mat-thumb-${slot}`).src = `${matBase}/${slot}/photo?thumb=1&v=${Date.now()}`;
    }));
    document.getElementById(`mat-clear-${slot}`).addEventListener("click", async () => {
      errorEl.style.display = "none";
      try {
        applyMaterialsChange(await api(`${matBase}/${slot}`, { method: "DELETE" }));
      } catch (err) {
        showError(errorEl, err);
      }
    });
    document.getElementById(`mat-file-${slot}`).addEventListener("change", (e) => {
      const file = e.target.files[0];
      e.target.value = "";
      if (!file) return;
      uploadWithStatus(e.target.closest(".photo-slot"), file, async () => {
        const form = new FormData();
        form.append("file", file);
        applyMaterialsChange(await apiUpload(`${matBase}/${slot}/photo`, form)); // 성공하면 슬롯을 다시 그림
      });
    });
    document.getElementById(`mat-save-${slot}`).addEventListener("click", async () => {
      errorEl.style.display = "none";
      try {
        const out = await apiPatch(`${matBase}/${slot}`, { title: document.getElementById(`mat-title-${slot}`).value });
        // 제목만 바뀐 것 — 자동 저장 중에 슬롯을 다시 그리면 입력하던 칸의 커서가 사라지므로 10-1 교육내용만 맞춘다
        document.getElementById("tbm-content").value = out.education_content;
        const st = document.getElementById(`mat-status-${slot}`);
        st.className = "status ok";
        st.textContent = "저장되었습니다.";
      } catch (err) {
        showError(errorEl, err);
      }
    });
  }
  collapseEmptySlots(container, (card) => card.dataset.empty === "1", "제공자료");
  renderSuggest();
}

// ---------- 11번 AI 추천·다른 후보·고르기 창 분류·자료 올리기 (2026-10-15 사용자·민재형) ----------
// [✨ AI 추천]을 누를 때만 AI가 지적사항·진행 공정·방문 월·지난 회차 자료를 보고 2개를 칸에 넣고, 이유와 다른 후보(최대 6개)를 돌려준다
// (서버 material_ai.py). 후보는 [칸 1]·[칸 2]로 바로 바꿔 넣고, 고르기 창에서도 ✨ AI 후보가 맨 앞에 보인다.
// 고르기 창: 분류 단추(형 Dropbox 폴더 이름 바탕) + 검색(이름·분류) + [📤 자료 올리기](여러 파일을 한 파일씩 차례로, 끌어다 놓기 가능,
// 4쪽 넘는 PDF·같은 자료는 서버가 거름, 올린 직후 이름 고치기·빼기).
let matSuggest = null;
let matItems = [];
let matCat = "";
const matEsc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const matThumb = (id) => `${BASE}/api/material-library/${id}/thumbnail`;
const matFile = (id) => `${BASE}/api/material-library/${id}/file`;

async function putMaterial(slot, id) {
  errorEl.style.display = "none";
  try {
    applyMaterialsChange(await apiPatch(`${matBase}/${slot}`, { material_id: id }));
    return true;
  } catch (err) {
    showError(errorEl, err);
    return false;
  }
}

function suggestList() {
  return matSuggest ? [...matSuggest.picks, ...matSuggest.others] : [];
}

function renderSuggest() {
  const box = document.getElementById("mat-suggest");
  const all = suggestList();
  if (!all.length) { box.style.display = "none"; box.innerHTML = ""; return; }
  const reason = new Map(all.map((x) => [x.id, x.reason]));
  const filled = new Set(matItems.map((x) => x.material_id).filter(Boolean));
  const why = matItems.filter((x) => x.material_id && reason.has(x.material_id))
    .map((x) => `<li><b>칸 ${x.slot}</b> ${matEsc(x.title)}<span> — ${matEsc(reason.get(x.material_id))}</span></li>`).join("");
  const cands = all.filter((x) => !filled.has(x.id));
  box.innerHTML = `
    ${why ? `<div class="ms-head">✨ AI가 고른 이유</div><ul class="ms-why">${why}</ul>` : ""}
    ${cands.length ? `<div class="ms-head">다른 후보 <small>[칸 1]·[칸 2]를 누르면 그 칸에 바꿔 넣습니다</small></div>
    <div class="ms-others">${cands.map((x) => `<div class="ms-card">
      <a href="${matFile(x.id)}" target="_blank" rel="noopener" title="크게 보기"><img loading="lazy" src="${matThumb(x.id)}" alt="" /></a>
      <div class="ms-body"><b>${matEsc(x.title)}</b><small>${matEsc(x.reason)}</small>
        <div class="ms-btns"><button type="button" class="secondary" data-put="1" data-id="${x.id}">칸 1</button><button type="button" class="secondary" data-put="2" data-id="${x.id}">칸 2</button></div></div></div>`).join("")}</div>` : ""}
    ${matSuggest.note ? `<div class="ms-note">${matEsc(matSuggest.note)}</div>` : ""}`;
  box.style.display = "block";
  box.querySelectorAll("[data-put]").forEach((b) => b.addEventListener("click", () => putMaterial(Number(b.dataset.put), Number(b.dataset.id))));
}

function renderMaterialPickerCats() {
  const el = document.getElementById("mat-picker-cats");
  const counts = new Map();
  for (const m of matLibrary) for (const c of m.categories || []) counts.set(c, (counts.get(c) || 0) + 1);
  const sugN = new Set(suggestList().map((x) => x.id)).size;
  if (matCat === "__ai" && !sugN) matCat = "";
  const chip = (key, label, n) => `<button type="button" class="mat-cat${matCat === key ? " on" : ""}" data-cat="${matEsc(key)}">${matEsc(label)} <small>${n}</small></button>`;
  el.innerHTML = chip("", "전체", matLibrary.length) + (sugN ? chip("__ai", "✨ AI 후보", sugN) : "")
    + [...counts].sort((a, b) => b[1] - a[1]).map(([c, n]) => chip(c, c, n)).join("");
  el.querySelectorAll(".mat-cat").forEach((b) => b.addEventListener("click", () => {
    matCat = b.dataset.cat;
    renderMaterialPickerCats();
    renderMaterialPickerGrid();
  }));
}

function renderMaterialPickerGrid() {
  const grid = document.getElementById("mat-picker-grid");
  const q = document.getElementById("mat-picker-search").value.trim().replace(/\s+/g, "").toLowerCase();
  const order = new Map(suggestList().map((x, i) => [x.id, i]));
  const shown = matLibrary.filter((m) => (!q || (m.title + (m.categories || []).join("")).replace(/\s+/g, "").toLowerCase().includes(q))
    && (!matCat || (matCat === "__ai" ? order.has(m.id) : (m.categories || []).includes(matCat))));
  shown.sort((a, b) => (order.has(a.id) ? order.get(a.id) : 1e9) - (order.has(b.id) ? order.get(b.id) : 1e9)); // AI 후보 먼저, 나머지는 원래 순서
  grid.innerHTML = "";
  if (!shown.length) {
    grid.innerHTML = '<div class="empty-note">검색 결과가 없습니다.</div>';
    return;
  }
  for (const m of shown) {
    const tile = document.createElement("button");
    tile.type = "button";
    tile.className = "lib-tile";
    tile.innerHTML = `<span class="lib-img"><img loading="lazy" src="${matThumb(m.id)}" alt="" />${order.has(m.id) ? '<i class="lib-ai">✨ AI</i>' : ""}${m.kind === "pdf" ? '<i class="lib-pdf">PDF</i>' : ""}</span><span class="lib-name"></span>`;
    tile.querySelector(".lib-name").textContent = m.title;
    tile.addEventListener("click", async () => {
      if (await putMaterial(matPickerSlot, m.id)) document.getElementById("mat-picker").style.display = "none";
    });
    grid.appendChild(tile);
  }
}

function setPickerTitle() {
  document.getElementById("mat-picker-title").textContent = `제공자료 ${matPickerSlot}에 넣을 자료 선택 (${matLibrary.length}개)`;
}

async function openMaterialPicker(slot) {
  errorEl.style.display = "none";
  try {
    if (!matLibrary) matLibrary = await api("/material-library");
  } catch (err) {
    showError(errorEl, err);
    return;
  }
  matPickerSlot = slot;
  setPickerTitle();
  const picker = document.getElementById("mat-picker");
  picker.style.display = "block";
  renderMaterialPickerCats();
  renderMaterialPickerGrid();
  picker.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function refreshLibrary() {
  matLibrary = await api("/material-library");
  setPickerTitle();
  renderMaterialPickerCats();
  renderMaterialPickerGrid();
}

function renderAddedRow(row, item) {
  row.className = "mu-row ok";
  row.innerHTML = `<img src="${matThumb(item.id)}" alt="" /><input aria-label="자료 이름" />
    <span class="mu-btns"><button type="button" class="secondary mu-save">이름 저장</button><button type="button" class="secondary mu-del">빼기</button></span>
    <span class="mu-state">${matEsc((item.categories || []).join(" · ") || "분류 없음")}</span>`;
  const input = row.querySelector("input");
  input.value = item.title;
  const state = row.querySelector(".mu-state");
  row.querySelector(".mu-save").addEventListener("click", async () => {
    try {
      const out = await apiPatch(`/material-library/${item.id}`, { title: input.value });
      input.value = out.title;
      state.textContent = "이름 저장됨";
      await refreshLibrary();
    } catch (err) { state.textContent = err.message; }
  });
  row.querySelector(".mu-del").addEventListener("click", async () => {
    if (!confirm(`"${input.value}" 자료를 라이브러리에서 뺄까요?`)) return;
    try {
      await api(`/material-library/${item.id}`, { method: "DELETE" });
      row.className = "mu-row skip";
      row.innerHTML = `<span class="mu-file">${matEsc(input.value)}</span><span class="mu-state">뺐습니다</span>`;
      await refreshLibrary();
    } catch (err) { state.textContent = err.message; }
  });
}

async function uploadLibraryFiles(fileList) {
  const files = [...fileList];
  if (!files.length) return;
  const box = document.getElementById("mat-upload-result");
  box.style.display = "block";
  box.innerHTML = `<div class="mu-head"><b>자료 올리기</b><span class="mu-prog"></span><button type="button" class="secondary mu-close">닫기</button></div>
    <div class="mu-rule">PDF·JPG·PNG만 넣고, PDF는 4쪽까지만 넣습니다(책자·절차서는 보고서가 길어짐). 이름은 자동으로 다듬었으니 필요하면 고쳐 주세요.</div>
    <div class="mu-list"></div>`;
  box.querySelector(".mu-close").addEventListener("click", () => { box.style.display = "none"; });
  const prog = box.querySelector(".mu-prog");
  const list = box.querySelector(".mu-list");
  let ok = 0, skip = 0;
  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    prog.textContent = `${i + 1} / ${files.length} 올리는 중…`;
    const row = document.createElement("div");
    row.className = "mu-row";
    row.innerHTML = `<span class="mu-file"></span><span class="mu-state">올리는 중…</span>`;
    row.querySelector(".mu-file").textContent = f.name;
    list.appendChild(row);
    try {
      const form = new FormData();
      form.append("file", f);
      const out = await apiUpload("/material-library", form);
      if (out.ok) { ok++; renderAddedRow(row, out.item); } else { skip++; row.classList.add("skip"); row.querySelector(".mu-state").textContent = `넣지 않음 — ${out.reason}`; }
    } catch (err) {
      skip++;
      row.classList.add("skip");
      row.querySelector(".mu-state").textContent = `실패 — ${err.message}`;
    }
  }
  prog.textContent = `넣음 ${ok} · 안 넣음 ${skip}`;
  try { await refreshLibrary(); } catch (err) { showError(errorEl, err); }
}

document.getElementById("mat-picker-search").addEventListener("input", renderMaterialPickerGrid);
document.getElementById("mat-picker-close").addEventListener("click", () => {
  document.getElementById("mat-picker").style.display = "none";
});
document.getElementById("mat-upload-open").addEventListener("click", () => document.getElementById("mat-upload-input").click());
document.getElementById("mat-upload-input").addEventListener("change", (e) => {
  uploadLibraryFiles(e.target.files).finally(() => { e.target.value = ""; });
});
(() => {
  const picker = document.getElementById("mat-picker");
  picker.addEventListener("dragover", (e) => { e.preventDefault(); picker.classList.add("drag"); });
  picker.addEventListener("dragleave", (e) => { if (!picker.contains(e.relatedTarget)) picker.classList.remove("drag"); });
  picker.addEventListener("drop", (e) => {
    e.preventDefault();
    picker.classList.remove("drag");
    if (e.dataTransfer && e.dataTransfer.files.length) uploadLibraryFiles(e.dataTransfer.files);
  });
})();

document.getElementById("mat-recommend").addEventListener("click", async () => {
  errorEl.style.display = "none";
  const btn = document.getElementById("mat-recommend");
  const st = document.getElementById("mat-recommend-status");
  st.className = "status";
  st.textContent = "AI가 지적사항·공정을 보고 자료를 고르는 중… (몇 초)";
  btn.disabled = true;
  try {
    const out = await apiPost(`${matBase}/recommend`, {});
    matSuggest = out.suggest || null;
    if (!out.items.length) {
      st.textContent = "맞는 자료를 찾지 못했습니다. '라이브러리에서 선택'으로 직접 고르세요.";
      renderSuggest();
      return;
    }
    applyMaterialsChange(out);
    st.className = "status ok";
    st.textContent = matSuggest && matSuggest.source === "ai"
      ? "AI가 고른 자료로 칸 1·2를 채웠습니다. 10번 교육내용에도 반영했습니다."
      : "AI를 쓰지 못해 분류가 맞는 자료로 채웠습니다. 10번 교육내용에도 반영했습니다.";
    if (document.getElementById("mat-picker").style.display !== "none" && matLibrary) {
      renderMaterialPickerCats();
      renderMaterialPickerGrid();
    }
  } catch (err) {
    st.textContent = "";
    showError(errorEl, err);
  } finally {
    btn.disabled = false;
  }
});

async function setupMaterials() {
  try {
    renderMaterials(await api(matBase));
  } catch (err) {
    showError(errorEl, err);
  }
}
