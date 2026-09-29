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
      t.src = `${apiPrefix}/${slotNum}/image?thumb=1&v=${Date.now()}`;
      t.style.display = "block";
      slotEls[slotNum].del.style.display = "inline-block";
    };
    const hideThumb = (slotNum) => {
      slotEls[slotNum].thumb.style.display = "none";
      slotEls[slotNum].del.style.display = "none";
    };

    slotEls[slot].file.addEventListener("change", (e) => {
      const file = e.target.files[0];
      e.target.value = ""; // 같은 파일을 다시 골라도 반응하게
      if (!file) return;
      uploadWithStatus(row, file, async () => {
        const formData = new FormData();
        formData.append("file", file);
        await apiUpload(`${apiPrefix}/${slot}`, formData);
        showThumb(slot);
      });
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
      slotEls[row.slot].thumb.src = `${apiPrefix}/${row.slot}/image?thumb=1`;
      slotEls[row.slot].thumb.style.display = "block";
      slotEls[row.slot].del.style.display = "inline-block";
    }
    collapseEmptySlots(container, (el) => el.querySelector(".thumb").style.display === "none", labelPrefix);
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
  const base = `${BASE}/api/reports/${reportId}/previous-findings`;
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
    if (!carried && !item.title && !item.content && !item.has_photo && !item.has_completion_photo && !item.result_status) {
      card.dataset.empty = "1";
    }
    card.innerHTML = `
      <h3>이전지적사항 ${slot} ${carried ? `<span class="status-pill approved" style="margin-left:6px;">${data.prev_visit_no}회차에서 이월</span>` : ""}</h3>
      <label>제목</label>
      <input id="pf-title-${slot}" ${carried ? "disabled" : ""} />
      <label>내용</label>
      <input id="pf-content-${slot}" ${carried ? "disabled" : ""} />
      <label>이행 전 위험성</label>
      ${carried
        ? `<div class="status" id="pf-before-${slot}"></div>`
        : `<div class="field-grid">
             <div><label for="pf-blike-${slot}" class="sub-label">가능성 (1~3)</label>
               <select id="pf-blike-${slot}">${RISK_OPTIONS}</select></div>
             <div><label for="pf-bsev-${slot}" class="sub-label">중대성 (1~3)</label>
               <select id="pf-bsev-${slot}">${RISK_OPTIONS}</select></div>
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
             ${item.has_photo ? `src="${base}/${slot}/photo?thumb=1"` : ""} />
        <div class="slot-controls">
          <div class="slot-label">지적사항 사진${carried ? ` (${data.prev_visit_no}회차 사진)` : ""}</div>
          ${carried ? "" : `<input type="file" accept="image/*" id="pf-file-${slot}" />
          <button type="button" class="secondary" id="pf-del-${slot}" style="display:${item.has_photo ? "inline-block" : "none"};">삭제</button>`}
        </div>
      </div>
      <div class="photo-slot">
        <img class="thumb" id="pf-cthumb-${slot}" style="display:${item.has_completion_photo ? "block" : "none"};"
             ${item.has_completion_photo ? `src="${base}/${slot}/completion-photo?thumb=1"` : ""} />
        <div class="slot-controls">
          <div class="slot-label">이행완료 증빙사진</div>
          <input type="file" accept="image/*" id="pf-cfile-${slot}" />
          <button type="button" class="secondary" id="pf-cdel-${slot}" style="display:${item.has_completion_photo ? "inline-block" : "none"};">삭제</button>
        </div>
      </div>
      <button type="button" class="autosave" id="pf-save-${slot}">저장</button>
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
    let savedStatus = item.result_status; // 사진 없이 이행완료 확인에서 "취소"하면 이 값으로 되돌린다(자동 저장이라 안 되돌리면 칸마다 다시 물음)

    document.getElementById(`pf-save-${slot}`).addEventListener("click", async () => {
      errorEl.style.display = "none";
      const msgEl = document.getElementById(`pf-status-msg-${slot}`);
      const statusVal = document.getElementById(`pf-status-${slot}`).value;
      const hasPhoto = document.getElementById(`pf-thumb-${slot}`).style.display !== "none";
      if (statusVal === "이행완료" && !hasPhoto &&
          !confirm("이 지적사항에는 사진이 없습니다. 사진 없이 이행완료로 처리하시겠습니까?")) {
        document.getElementById(`pf-status-${slot}`).value = savedStatus;
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
        savedStatus = statusVal;
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
  collapseEmptySlots(container, (card) => card.dataset.empty === "1", "이전지적사항");
}

// overview/inspection과 달리 슬롯 하나짜리 단일 사진(이전지적사항의 사진 2종, 앞으로 나올
// 지적사항 등에서도 재사용할 수 있는 공용 헬퍼).
function setupSinglePhotoUpload(url, fileInputId, thumbId, delBtnId) {
  const fileInput = document.getElementById(fileInputId);
  const thumb = document.getElementById(thumbId);
  const delBtn = document.getElementById(delBtnId);

  fileInput.addEventListener("change", (e) => {
    const file = e.target.files[0];
    e.target.value = ""; // 같은 파일을 다시 골라도 반응하게
    if (!file) return;
    uploadWithStatus(fileInput.closest(".photo-slot") || fileInput.parentElement, file, async () => {
      const formData = new FormData();
      formData.append("file", file);
      await apiUpload(url, formData);
      thumb.src = `${url}?thumb=1&v=${Date.now()}`;
      thumb.style.display = "block";
      delBtn.style.display = "inline-block";
    });
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


// 사진 업로드 상태를 그 사진 칸 안에 보여 준다 — 예전엔 실패 메시지가 페이지 맨 위에만 떠서, 아래 섹션에서 사진을 고르면
// 실패해도 몰랐다(2026-09-29 "가끔 전경·점검사진이 안 올라감" — 서버 재시작·AWS 통로 재연결 중 502 등). 올리는 동안 "올리는 중…",
// 성공하면 잠깐 "✓ 올렸습니다", 실패하면 이유 + "다시 시도"(같은 파일로 다시 보냄, 다시 고를 필요 없음).
// doUpload: 실제 업로드(+성공 후 화면 갱신)를 하는 async 함수, 실패하면 throw.
async function uploadWithStatus(slotEl, file, doUpload) {
  const host = slotEl.querySelector(".slot-controls") || slotEl;
  let st = host.querySelector(":scope > .upload-state");
  if (!st) {
    st = document.createElement("div");
    host.appendChild(st);
  }
  st.className = "upload-state busy";
  st.textContent = `올리는 중… (${file.name})`;
  slotEl.classList.add("uploading");
  try {
    await doUpload();
    st.className = "upload-state ok";
    st.textContent = "✓ 올렸습니다";
    setTimeout(() => {
      if (st.classList.contains("ok")) { st.className = "upload-state"; st.textContent = ""; }
    }, 4000);
  } catch (err) {
    st.className = "upload-state bad";
    st.textContent = "";
    const msg = document.createElement("span");
    msg.textContent = `⚠ 실패 — ${uploadErrorText(err)}`;
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "secondary upload-retry";
    retry.textContent = "다시 시도";
    retry.addEventListener("click", () => uploadWithStatus(slotEl, file, doUpload));
    st.append(msg, retry);
  } finally {
    slotEl.classList.remove("uploading");
  }
}

function uploadErrorText(err) {
  const m = (err && err.message) || String(err);
  if (err instanceof TypeError || /Failed to fetch|NetworkError|Load failed/i.test(m)) return "연결이 끊겼습니다. 잠시 후 다시 시도하세요.";
  if (/\((502|503|504)\)/.test(m)) return "서버에 잠깐 연결할 수 없습니다. 잠시 후 다시 시도하세요.";
  if (/\(413\)/.test(m)) return "사진 파일이 너무 큽니다(30MB 이하).";
  return m;
}
