// report.html 스크립트 — 7·9번 현재·향후 진행공정(AI로 작성), 8번 지적사항(AI추천).
// report.html에서 순서대로 불러오는 5개 파일 중 하나(core → photos → work → support → main). 파일끼리는
// 전역 함수/상수를 공유하고, 페이지 시작 시 실행하는 호출은 전부 report-main.js 맨 아래에 모아 두었다
// (앞 파일이 뒤 파일 함수를 불러오는 시점 문제를 없애려고 — 여기엔 정의만 둔다).

// --- 7/9. 현재·향후 진행공정 (완전히 같은 모양이라 함수 하나로 둘 다 처리) ---
// "✨ AI로 작성": 공정 사진·공정명 중 하나 이상으로 항목을 채운다(POST .../ai/process-hazards,
// 데스크톱과 같은 vision_analyzer 함수). 결과는 입력칸에만 채우고 저장은 사용자가 확인 후 "저장"으로.
// 사진은 분석용으로만 쓰고 보관하지 않는다(보고서 표에 공정 사진 칸이 없음).
async function setupProcessSlots(containerId, apiPrefix) {
  const container = document.getElementById(containerId);
  let entries;
  try {
    entries = await api(apiPrefix);
  } catch (err) {
    showError(errorEl, err);
    return;
  }

  for (const entry of entries) {
    const slot = entry.slot;
    const card = document.createElement("div");
    card.className = "sub-card";
    card.innerHTML = `
      <h3>공정 ${slot}</h3>
      <label>진행공정명</label>
      <input id="${containerId}-name-${slot}" placeholder="예: 철근 콘크리트 타설" />
      <div class="photo-slot">
        <div class="slot-controls">
          <div class="slot-label">AI 분석용 공정 사진 (선택 — 공정명만 있어도 작성됩니다, 보관 안 함)</div>
          <input type="file" accept="image/*" capture="environment" id="${containerId}-aiphoto-${slot}" />
        </div>
        <button type="button" id="${containerId}-ai-${slot}" style="margin-top:0;">✨ AI로 작성</button>
      </div>
      <div id="${containerId}-items-${slot}"></div>
      <button type="button" class="secondary" id="${containerId}-add-${slot}">+ 항목 추가</button>
      <button type="button" id="${containerId}-save-${slot}">저장</button>
      <div id="${containerId}-status-${slot}" class="status"></div>
    `;
    container.appendChild(card);
    const nameInput = card.querySelector(`#${containerId}-name-${slot}`);
    nameInput.value = entry.process_name || "";
    const statusEl = card.querySelector(`#${containerId}-status-${slot}`);

    const itemsEl = card.querySelector(`#${containerId}-items-${slot}`);
    const addItemRow = (item) => {
      const row = document.createElement("div");
      row.className = "photo-slot";
      row.innerHTML = `
        <div class="slot-controls">
          <label>유해·위험요인</label>
          <input class="pi-hazard" />
          <label>예방대책 <span style="font-weight:400; color:var(--muted);">(한 줄에 하나씩)</span></label>
          <textarea class="pi-prevention" rows="3"></textarea>
          <label>위험성수준</label>
          <select class="pi-risk">
            <option value="">선택 안 함</option>
            <option value="상">상</option>
            <option value="중">중</option>
            <option value="하">하</option>
          </select>
        </div>
        <button type="button" class="secondary pi-del">삭제</button>
      `;
      row.querySelector(".pi-hazard").value = item.hazard || "";
      row.querySelector(".pi-prevention").value = item.prevention || "";
      row.querySelector(".pi-risk").value = item.risk_level || "";
      row.querySelector(".pi-del").addEventListener("click", () => row.remove());
      itemsEl.appendChild(row);
    };
    for (const item of entry.items) addItemRow(item);

    card.querySelector(`#${containerId}-add-${slot}`).addEventListener("click", () => {
      addItemRow({ hazard: "", prevention: "", risk_level: "" });
    });

    const aiBtn = card.querySelector(`#${containerId}-ai-${slot}`);
    aiBtn.addEventListener("click", async () => {
      errorEl.style.display = "none";
      const photoInput = card.querySelector(`#${containerId}-aiphoto-${slot}`);
      const processName = nameInput.value.trim();
      if (!photoInput.files[0] && !processName) {
        showError(errorEl, new Error(`공정 ${slot}: 공정 사진 또는 공정 이름 중 하나 이상을 입력해주세요.`));
        return;
      }
      if (itemsEl.children.length && !confirm("지금 입력된 항목을 AI 결과로 바꿀까요?")) return;
      const form = new FormData();
      form.append("process_name", processName);
      if (photoInput.files[0]) form.append("file", photoInput.files[0]);
      aiBtn.disabled = true;
      aiBtn.textContent = "분석 중... (20초 안팎)";
      statusEl.className = "status";
      statusEl.textContent = "";
      try {
        const out = await apiUpload(`/api/reports/${reportId}/ai/process-hazards`, form);
        if (!out.items.length) {
          statusEl.textContent = "유해·위험요인을 찾지 못했습니다. 직접 입력해주세요.";
        } else {
          itemsEl.innerHTML = "";
          for (const item of out.items) addItemRow(item);
          statusEl.className = "status ok";
          statusEl.textContent = `AI가 ${out.items.length}개 항목을 작성했습니다. 확인·수정 후 "저장"을 누르세요.`;
        }
      } catch (err) {
        showError(errorEl, err);
      } finally {
        aiBtn.disabled = false;
        aiBtn.textContent = "✨ AI로 작성";
      }
    });

    card.querySelector(`#${containerId}-save-${slot}`).addEventListener("click", async () => {
      errorEl.style.display = "none";
      const items = Array.from(itemsEl.children).map((row) => ({
        hazard: row.querySelector(".pi-hazard").value,
        prevention: row.querySelector(".pi-prevention").value,
        risk_level: row.querySelector(".pi-risk").value,
      }));
      try {
        await apiPatch(`${apiPrefix}/${slot}`, { process_name: nameInput.value, items });
        statusEl.className = "status ok";
        statusEl.textContent = "저장되었습니다.";
      } catch (err) {
        statusEl.textContent = "";
        showError(errorEl, err);
      }
    });
  }
}


// --- 8. 지적사항 ---
// "✨ AI추천": 이 슬롯에 올린 사진 + 간단 설명 → 제목/내용/법령/위험성 추천(POST .../ai/finding/{slot},
// 데스크톱과 같은 vision_analyzer.analyze_finding). 입력칸에만 채우고 저장은 사용자가 확인 후.
async function setupFindings() {
  const container = document.getElementById("findings-slots");
  const base = `/api/reports/${reportId}/findings`;
  let rows;
  try {
    rows = await api(base);
  } catch (err) {
    showError(errorEl, err);
    return;
  }

  for (const data of rows) {
    const slot = data.slot;
    const card = document.createElement("div");
    card.className = "sub-card";
    card.innerHTML = `
      <h3>지적사항 ${slot}</h3>
      <div class="photo-slot">
        <img class="thumb" id="fd-thumb-${slot}" style="display:${data.has_photo ? "block" : "none"};"
             ${data.has_photo ? `src="${base}/${slot}/photo?ts=${Date.now()}"` : ""} />
        <div class="slot-controls">
          <div class="slot-label">지적사항 사진 (선택하면 바로 저장)</div>
          <input type="file" accept="image/*" capture="environment" id="fd-file-${slot}" />
          <button type="button" class="secondary" id="fd-del-${slot}" style="display:${data.has_photo ? "inline-block" : "none"};">삭제</button>
        </div>
      </div>
      <label>간단 설명 <span style="font-weight:400; color:var(--muted);">(AI추천 참고용, 보고서엔 안 나감)</span></label>
      <div style="display:flex; gap:8px; align-items:center;">
        <input id="fd-desc-${slot}" placeholder="예: 3층 슬래브 단부 안전난간 없음" />
        <button type="button" id="fd-ai-${slot}" style="margin-top:0; flex:none;">✨ AI추천</button>
      </div>
      <label>제목 <span style="font-weight:400; color:var(--muted);">(30자)</span></label>
      <input id="fd-title-${slot}" maxlength="30" />
      <label>내용 <span style="font-weight:400; color:var(--muted);">(110자)</span></label>
      <textarea id="fd-content-${slot}" rows="3" maxlength="110"></textarea>
      <label>관련 법령</label>
      <input id="fd-law-${slot}" />
      <div style="display:flex; gap:8px;">
        <div style="flex:1;"><label>가능성 (1~3)</label>
          <select id="fd-likelihood-${slot}">
            <option value="">선택 안 함</option><option value="1">1</option><option value="2">2</option><option value="3">3</option>
          </select></div>
        <div style="flex:1;"><label>중대성 (1~3)</label>
          <select id="fd-severity-${slot}">
            <option value="">선택 안 함</option><option value="1">1</option><option value="2">2</option><option value="3">3</option>
          </select></div>
      </div>
      <div class="status" id="fd-risk-${slot}"></div>
      <label>조치상태</label>
      <select id="fd-status-${slot}">
        <option value="추후확인">추후확인</option>
        <option value="즉시이행">즉시이행</option>
      </select>
      <button type="button" id="fd-save-${slot}">저장</button>
      <div id="fd-status-msg-${slot}" class="status"></div>
    `;
    container.appendChild(card);
    const $ = (name) => document.getElementById(`fd-${name}-${slot}`);
    $("title").value = data.title;
    $("content").value = data.content;
    $("law").value = data.law_citation;
    $("desc").value = data.description || "";
    $("likelihood").value = data.likelihood ?? "";
    $("severity").value = data.severity ?? "";
    $("status").value = data.action_status || "추후확인";

    const updateRisk = () => {
      const l = $("likelihood").value, sv = $("severity").value;
      $("risk").textContent = l && sv ? riskText(Number(l), Number(sv)) : "";
    };
    $("likelihood").addEventListener("change", updateRisk);
    $("severity").addEventListener("change", updateRisk);
    updateRisk();

    $("ai").addEventListener("click", async () => {
      errorEl.style.display = "none";
      const msgEl = $("status-msg");
      if ($("thumb").style.display === "none") {
        showError(errorEl, new Error(`지적사항 ${slot}: 먼저 사진을 올려주세요.`));
        return;
      }
      if (($("title").value || $("content").value) && !confirm("지금 입력된 제목·내용을 AI 추천으로 바꿀까요?")) return;
      const form = new FormData();
      form.append("description", $("desc").value);
      $("ai").disabled = true;
      $("ai").textContent = "분석 중...";
      msgEl.className = "status";
      msgEl.textContent = "";
      try {
        const out = await apiUpload(`/api/reports/${reportId}/ai/finding/${slot}`, form);
        $("title").value = out.title;
        $("content").value = out.content;
        if (out.law_citation) $("law").value = out.law_citation;
        if (out.likelihood != null) $("likelihood").value = out.likelihood;
        if (out.severity != null) $("severity").value = out.severity;
        updateRisk();
        msgEl.className = "status ok";
        msgEl.textContent = 'AI 추천을 채웠습니다. 확인·수정 후 "저장"을 누르세요.';
      } catch (err) {
        showError(errorEl, err);
      } finally {
        $("ai").disabled = false;
        $("ai").textContent = "✨ AI추천";
      }
    });

    $("save").addEventListener("click", async () => {
      errorEl.style.display = "none";
      const msgEl = $("status-msg");
      try {
        await apiPatch(`${base}/${slot}`, {
          title: $("title").value,
          content: $("content").value,
          law_citation: $("law").value,
          likelihood: $("likelihood").value ? Number($("likelihood").value) : null,
          severity: $("severity").value ? Number($("severity").value) : null,
          action_status: $("status").value,
          description: $("desc").value,
        });
        msgEl.className = "status ok";
        msgEl.textContent = "저장되었습니다.";
      } catch (err) {
        msgEl.textContent = "";
        showError(errorEl, err);
      }
    });

    setupSinglePhotoUpload(`${base}/${slot}/photo`, `fd-file-${slot}`, `fd-thumb-${slot}`, `fd-del-${slot}`);
  }
}
