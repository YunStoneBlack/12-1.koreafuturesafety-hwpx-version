// report.html 스크립트 — 3번 전경·점검사진, 4번 이전지적사항(자동 이월), 단일 사진 업로드 공용 헬퍼.
// report.html에서 순서대로 불러오는 5개 파일 중 하나(core → photos → work → support → main). 파일끼리는
// 전역 함수/상수를 공유하고, 페이지 시작 시 실행하는 호출은 전부 report-main.js 맨 아래에 모아 두었다
// (앞 파일이 뒤 파일 함수를 불러오는 시점 문제를 없애려고 — 여기엔 정의만 둔다).

// --- 전경/점검 사진 슬롯 (완전히 같은 모양이라 함수 하나로 둘 다 처리) ---
function setupPhotoSlots(containerId, apiPrefix, labelPrefix) {
  const container = document.getElementById(containerId);
  const slotEls = {};

  for (let slot = 1; slot <= 4; slot++) {
    const row = document.createElement("div");
    row.className = "photo-slot";
    row.innerHTML = `
      <img class="thumb" id="${containerId}-thumb-${slot}" style="display:none;" />
      <div class="slot-controls">
        <div class="slot-label">${labelPrefix} ${slot}</div>
        <input type="file" accept="image/*" id="${containerId}-file-${slot}" />
        <button type="button" class="secondary" id="${containerId}-del-${slot}" style="display:none;">삭제</button>
      </div>
    `;
    container.appendChild(row);
    slotEls[slot] = {
      thumb: row.querySelector(`#${containerId}-thumb-${slot}`),
      file: row.querySelector(`#${containerId}-file-${slot}`),
      del: row.querySelector(`#${containerId}-del-${slot}`),
    };

    const showThumb = (slotNum) => {
      const t = slotEls[slotNum].thumb;
      t.src = `${apiPrefix}/${slotNum}/image?ts=${Date.now()}`;
      t.style.display = "block";
      slotEls[slotNum].del.style.display = "inline-block";
    };
    const hideThumb = (slotNum) => {
      slotEls[slotNum].thumb.style.display = "none";
      slotEls[slotNum].del.style.display = "none";
    };

    slotEls[slot].file.addEventListener("change", async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      errorEl.style.display = "none";
      const formData = new FormData();
      formData.append("file", file);
      try {
        const res = await fetch(`${apiPrefix}/${slot}`, { method: "POST", credentials: "include", body: formData });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || `업로드 실패 (${res.status})`);
        }
        showThumb(slot);
      } catch (err) {
        showError(errorEl, err);
      }
    });

    slotEls[slot].del.addEventListener("click", async () => {
      errorEl.style.display = "none";
      try {
        await api(`${apiPrefix}/${slot}`, { method: "DELETE" });
        hideThumb(slot);
        slotEls[slot].file.value = "";
      } catch (err) {
        showError(errorEl, err);
      }
    });
  }

  // 이미 저장된 사진이 있으면 미리보기 채우기 (페이지 새로고침 후에도 보이게).
  api(apiPrefix).then((rows) => {
    for (const row of rows) {
      slotEls[row.slot].thumb.src = `${apiPrefix}/${row.slot}/image?ts=${Date.now()}`;
      slotEls[row.slot].thumb.style.display = "block";
      slotEls[row.slot].del.style.display = "inline-block";
    }
  }).catch((err) => showError(errorEl, err));
}


// --- 4. 이전지적사항 — 직전 회차 8번 지적사항 자동 이월 + 수기 입력 ---
// 목록을 불러올 때마다 서버가 직전 회차 지적사항을 다시 읽어 이월한다(server/api/carryover.py).
// 이월 항목("carried")은 제목/내용/사진/이행 전 위험성이 원본을 따라 잠기고, 조치결과와
// 이행완료 증빙사진만 입력한다. 빈 칸은 직접 입력하는 수기 항목.
const RISK_BANDS = [[1, 3, "하", "현상유지"], [4, 5, "중", "개선필요"], [6, 9, "상", "즉시개선"]];

function riskText(likelihood, severity) {
  if (likelihood == null || severity == null) return "-";
  const score = likelihood * severity;
  const band = RISK_BANDS.find(([lo, hi]) => lo <= score && score <= hi);
  return `가능성 ${likelihood} × 중대성 ${severity} = ${score}` + (band ? ` (${band[2]} · ${band[3]})` : "");
}

const RISK_OPTIONS = '<option value="">선택 안 함</option><option value="1">1</option><option value="2">2</option><option value="3">3</option>';

async function setupPreviousFindings() {
  const container = document.getElementById("previous-findings-slots");
  const hintEl = document.getElementById("pf-hint");
  const base = `/api/reports/${reportId}/previous-findings`;
  let data;
  try {
    data = await api(base);
  } catch (err) {
    hintEl.textContent = "";
    showError(errorEl, err);
    return;
  }

  if (data.prev_visit_no == null) {
    hintEl.textContent = "이 현장의 첫 보고서라 이월할 이전 지적사항이 없습니다. 필요하면 아래 칸에 직접 입력하세요.";
  } else if (data.carried_count > 0) {
    hintEl.textContent = `${data.prev_visit_no}회차 지적사항 ${data.carried_count}건을 자동으로 이월했습니다. 조치결과를 확인해 입력하세요. ` +
      `(제목·내용·사진은 ${data.prev_visit_no}회차 8번에서 고치면 여기도 바로 반영됩니다.)`;
  } else {
    hintEl.textContent = `${data.prev_visit_no}회차에 지적사항이 없습니다. 직접 넣을 항목이 있으면 아래 칸에 입력하세요.`;
  }

  container.innerHTML = "";
  for (const item of data.items) {
    const slot = item.slot;
    const carried = item.carried;
    const card = document.createElement("div");
    card.className = "sub-card";
    card.innerHTML = `
      <h3>이전지적사항 ${slot} ${carried ? `<span class="status-pill approved" style="margin-left:6px;">${data.prev_visit_no}회차에서 이월</span>` : ""}</h3>
      <label>제목</label>
      <input id="pf-title-${slot}" ${carried ? "disabled" : ""} />
      <label>내용</label>
      <input id="pf-content-${slot}" ${carried ? "disabled" : ""} />
      <label>이행 전 위험성</label>
      ${carried
        ? `<div class="status" id="pf-before-${slot}"></div>`
        : `<div style="display:flex; gap:8px;">
             <select id="pf-blike-${slot}" aria-label="가능성">${RISK_OPTIONS}</select>
             <select id="pf-bsev-${slot}" aria-label="중대성">${RISK_OPTIONS}</select>
           </div>
           <div class="status" id="pf-before-${slot}"></div>`}
      <label>조치결과</label>
      <select id="pf-status-${slot}">
        <option value="">선택 안 함</option>
        <option value="확인불가">확인불가</option>
        <option value="보완필요">보완필요</option>
        <option value="이행완료">이행완료</option>
      </select>
      <label>이행 후 위험성 <span style="font-weight:400; color:var(--muted);">(조치결과에 따라 자동)</span></label>
      <div class="status" id="pf-after-${slot}"></div>
      <div class="photo-slot">
        <img class="thumb" id="pf-thumb-${slot}" style="display:${item.has_photo ? "block" : "none"};"
             ${item.has_photo ? `src="${base}/${slot}/photo?ts=${Date.now()}"` : ""} />
        <div class="slot-controls">
          <div class="slot-label">지적사항 사진${carried ? ` (${data.prev_visit_no}회차 사진)` : ""}</div>
          ${carried ? "" : `<input type="file" accept="image/*" id="pf-file-${slot}" />
          <button type="button" class="secondary" id="pf-del-${slot}" style="display:${item.has_photo ? "inline-block" : "none"};">삭제</button>`}
        </div>
      </div>
      <div class="photo-slot">
        <img class="thumb" id="pf-cthumb-${slot}" style="display:${item.has_completion_photo ? "block" : "none"};"
             ${item.has_completion_photo ? `src="${base}/${slot}/completion-photo?ts=${Date.now()}"` : ""} />
        <div class="slot-controls">
          <div class="slot-label">이행완료 증빙사진</div>
          <input type="file" accept="image/*" id="pf-cfile-${slot}" />
          <button type="button" class="secondary" id="pf-cdel-${slot}" style="display:${item.has_completion_photo ? "inline-block" : "none"};">삭제</button>
        </div>
      </div>
      <button type="button" id="pf-save-${slot}">저장</button>
      <div id="pf-status-msg-${slot}" class="status"></div>
    `;
    container.appendChild(card);
    // 값은 .value로 넣는다(따옴표/꺾쇠가 들어간 제목도 안전하게)
    document.getElementById(`pf-title-${slot}`).value = item.title;
    document.getElementById(`pf-content-${slot}`).value = item.content;
    document.getElementById(`pf-status-${slot}`).value = item.result_status;
    if (!carried) {
      document.getElementById(`pf-blike-${slot}`).value = item.before_likelihood ?? "";
      document.getElementById(`pf-bsev-${slot}`).value = item.before_severity ?? "";
    }

    const showRisk = (out) => {
      document.getElementById(`pf-before-${slot}`).textContent = riskText(out.before_likelihood, out.before_severity);
      document.getElementById(`pf-after-${slot}`).textContent = riskText(out.after_likelihood, out.after_severity);
    };
    showRisk(item);

    document.getElementById(`pf-save-${slot}`).addEventListener("click", async () => {
      errorEl.style.display = "none";
      const msgEl = document.getElementById(`pf-status-msg-${slot}`);
      const statusVal = document.getElementById(`pf-status-${slot}`).value;
      const hasPhoto = document.getElementById(`pf-thumb-${slot}`).style.display !== "none";
      if (statusVal === "이행완료" && !hasPhoto &&
          !confirm("이 지적사항에는 사진이 없습니다. 사진 없이 이행완료로 처리하시겠습니까?")) {
        return;
      }
      const payload = { result_status: statusVal };
      if (!carried) {
        const like = document.getElementById(`pf-blike-${slot}`).value;
        const sev = document.getElementById(`pf-bsev-${slot}`).value;
        Object.assign(payload, {
          title: document.getElementById(`pf-title-${slot}`).value,
          content: document.getElementById(`pf-content-${slot}`).value,
          manual_likelihood: like ? Number(like) : null,
          manual_severity: sev ? Number(sev) : null,
        });
      }
      try {
        const out = await apiPatch(`${base}/${slot}`, payload);
        showRisk(out);
        msgEl.className = "status ok";
        msgEl.textContent = "저장되었습니다.";
      } catch (err) {
        msgEl.textContent = "";
        showError(errorEl, err);
      }
    });

    if (!carried) {
      setupSinglePhotoUpload(`${base}/${slot}/photo`, `pf-file-${slot}`, `pf-thumb-${slot}`, `pf-del-${slot}`);
    }
    setupSinglePhotoUpload(
      `${base}/${slot}/completion-photo`, `pf-cfile-${slot}`, `pf-cthumb-${slot}`, `pf-cdel-${slot}`
    );
  }
}

// overview/inspection과 달리 슬롯 하나짜리 단일 사진(이전지적사항의 사진 2종, 앞으로 나올
// 지적사항 등에서도 재사용할 수 있는 공용 헬퍼).
function setupSinglePhotoUpload(url, fileInputId, thumbId, delBtnId) {
  const fileInput = document.getElementById(fileInputId);
  const thumb = document.getElementById(thumbId);
  const delBtn = document.getElementById(delBtnId);

  fileInput.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    errorEl.style.display = "none";
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch(url, { method: "POST", credentials: "include", body: formData });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `업로드 실패 (${res.status})`);
      }
      thumb.src = `${url}?ts=${Date.now()}`;
      thumb.style.display = "block";
      delBtn.style.display = "inline-block";
    } catch (err) {
      showError(errorEl, err);
    }
  });

  delBtn.addEventListener("click", async () => {
    errorEl.style.display = "none";
    try {
      await api(url, { method: "DELETE" });
      thumb.style.display = "none";
      delBtn.style.display = "none";
      fileInput.value = "";
    } catch (err) {
      showError(errorEl, err);
    }
  });
}
