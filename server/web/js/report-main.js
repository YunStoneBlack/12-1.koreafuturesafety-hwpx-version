// report.html 스크립트 — PDF 생성·한글 받기·로그아웃 + 페이지 시작 시 실행(맨 아래).
// report.html에서 순서대로 불러오는 5개 파일 중 하나(core → photos → work → support → main). 파일끼리는
// 전역 함수/상수를 공유하고, 페이지 시작 시 실행하는 호출은 전부 report-main.js 맨 아래에 모아 두었다
// (앞 파일이 뒤 파일 함수를 불러오는 시점 문제를 없애려고 — 여기엔 정의만 둔다).

// 데스크톱과 같이 "확인했습니다" 체크를 해야 PDF 생성 버튼이 켜진다(AI 작성 내용 재확인 안내).
document.getElementById("confirm-check").addEventListener("change", (e) => {
  document.getElementById("render-btn").disabled = !e.target.checked;
});
document.getElementById("hwpx-link").href = `${BASE}/api/reports/${reportId}/hwpx`;
document.getElementById("hwpx-link").dataset.reportId = reportId;

// --- PDF 생성 ---
document.getElementById("render-btn").addEventListener("click", async () => {
  errorEl.style.display = "none";
  const statusEl = document.getElementById("job-status");
  const btn = document.getElementById("render-btn");
  if (notifySigField && notifySigField.isDirty() &&
      !confirm("1번 현장책임자 서명 변경을 아직 저장하지 않았습니다. 저장하지 않은 채로 PDF를 만들까요?")) return;
  btn.disabled = true;
  statusEl.textContent = "입력 내용 저장 확인 중...";
  try {
    await autosaveFlush(); // 방금 입력하고 바로 누른 경우 — 자동 저장이 끝난 뒤에 생성해야 PDF에 반영된다
    statusEl.textContent = "대기열에 등록 중...";
    const job = await apiPost(`/reports/${reportId}/render`);
    pollJob(job.id);
    document.getElementById("render-cancel").hidden = false;
  } catch (err) {
    btn.disabled = false;
    showError(errorEl, err);
  }
});

// PDF 만들기 취소 — 순서를 기다리는 중이면 작업을 취소, 이미 한글로 만드는 중이면 멈추지 않고 기다리기만 그만둔다
// (한글을 중간에 끊으면 다음 PDF까지 망가질 수 있음 — PDF는 끝까지 만들어져 현장 화면에 "PDF 생성됨"으로 나옴). server/api/routers/jobs.py cancel_job
async function cancelRenderJob(jobId) {
  try {
    const out = await apiPost(`/jobs/${jobId}/cancel`);
    return out.canceled
      ? "PDF 만들기를 취소했습니다."
      : out.status === "rendering"
        ? "이미 한글로 만드는 중이라 끝까지 만들어집니다. 기다리지 않고 닫았습니다 — 완성되면 현장 화면에 'PDF 생성됨'으로 나옵니다."
        : "";
  } catch {
    return "취소하지 못했습니다. 잠시 뒤 다시 시도하세요.";
  }
}

let currentRenderJobId = null;
document.getElementById("render-cancel").addEventListener("click", async () => {
  const cancelBtn = document.getElementById("render-cancel");
  if (!currentRenderJobId) return;
  cancelBtn.disabled = true;
  if (pollTimer) clearInterval(pollTimer);
  const msg = await cancelRenderJob(currentRenderJobId);
  currentRenderJobId = null;
  cancelBtn.disabled = false;
  cancelBtn.hidden = true;
  document.getElementById("render-btn").disabled = !document.getElementById("confirm-check").checked;
  if (msg) document.getElementById("job-status").textContent = msg;
});

function pollJob(jobId) {
  const statusEl = document.getElementById("job-status");
  const btn = document.getElementById("render-btn");
  const cancelBtn = document.getElementById("render-cancel");
  currentRenderJobId = jobId;
  if (pollTimer) clearInterval(pollTimer);
  const stop = () => { clearInterval(pollTimer); currentRenderJobId = null; cancelBtn.hidden = true; btn.disabled = false; };
  pollTimer = setInterval(async () => {
    try {
      const job = await api(`/jobs/${jobId}`);
      if (job.status === "queued") {
        statusEl.textContent = "대기 중 (다른 작업 처리 중)...";
      } else if (job.status === "rendering") {
        statusEl.textContent = "한글 프로그램으로 PDF 생성 중... (몇 초~십몇 초 걸릴 수 있어요)";
      } else if (job.status === "done") {
        stop();
        statusEl.innerHTML = `완료! <a data-download="pdf" data-report-id="${reportId}" href="${BASE}/api/jobs/${jobId}/download">PDF 다운로드</a>`;
        loadK2bPanel(); // "PDF를 먼저 만드세요" 안내가 사라지게(js/report-k2b.js)
      } else if (job.status === "failed") {
        stop();
        statusEl.textContent = `생성 실패: ${job.error_message.split("\n")[0]} (다시 시도해보세요)`;
      } else if (job.status === "canceled") {
        stop();
        statusEl.textContent = "PDF 만들기를 취소했습니다.";
      }
    } catch (err) {
      stop();
      showError(errorEl, err);
    }
  }, 1500);
}


// --- 목차 줄 버튼(report-nav.js): ← 현장으로 / 저장 / 미리보기 ---
function goBackToSite() {
  // 떠날 때 저장 대기분은 report-autosave.js의 beforeunload가 바로 저장한다
  window.location.href = siteId ? `site.html?id=${siteId}` : "dashboard.html";
}

// "저장" — 자동 저장이 되고 있지만, 누르는 순간 대기 중인 저장을 바로 끝내고 결과를 보여 준다.
async function saveNow() {
  const btn = document.getElementById("toc-save");
  btn.disabled = true;
  try {
    await autosaveFlush();
    const el = document.getElementById("save-indicator");
    if (autosaveFailed) return; // 표시는 updateSaveIndicator가 "저장 실패"로
    if (notifySigField && notifySigField.isDirty()) {
      el.className = "save-indicator bad";
      el.textContent = "1번 서명 창을 먼저 완료하세요";
      return;
    }
    el.className = "save-indicator ok";
    el.textContent = "✓ 저장했습니다";
  } finally {
    btn.disabled = false;
  }
}

// "미리보기" — 실제로 나올 모양은 이 PC의 한글로 PDF를 만들어야 보인다. 최신 PDF가 있으면 바로 띄우고,
// 없거나 만든 뒤 고쳤으면(수정 전 버전) 저장을 끝내고 새로 만든 뒤 띄운다(20~30초). 새로 만든 PDF가 곧 최신 PDF.
// PC는 화면 위 창에 PDF 그대로(iframe — 확대·인쇄), 폰은 같은 창에 쪽별 이미지(폰 브라우저·카카오톡 안 브라우저는
// PDF를 화면에 못 띄우고 내려받아 버림 — 2026-09-29 사용자, 새 탭 방식에서 바꿈).
const isNarrowScreen = () => window.matchMedia("(max-width: 760px), (pointer: coarse)").matches;

async function previewReport() {
  if (notifySigField && notifySigField.isDirty() &&
      !confirm("1번 현장책임자 서명 변경을 아직 저장하지 않았습니다. 저장하지 않은 채로 미리볼까요?")) return;
  const btn = document.getElementById("toc-preview");
  const modal = openPreviewModal();
  btn.disabled = true;
  try {
    await autosaveFlush();
    const st = await api(`/reports/${reportId}/pdf-status`);
    if (!st.has_pdf || st.outdated) {
      const job = await apiPost(`/reports/${reportId}/render`);
      // 만드는 중에 [닫기]/[취소] — 대기 중이면 작업 취소, 한글로 만드는 중이면 기다리기만 그만둔다(cancelRenderJob)
      modal.onClose(() => cancelRenderJob(job.id));
      const started = Date.now();
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500));
        if (modal.closed()) return;
        const j = await api(`/jobs/${job.id}`);
        modal.setStatus(`PDF 만드는 중… ${Math.round((Date.now() - started) / 1000)}초 (보통 20~30초)`);
        if (j.status === "done") { modal.onClose(null); break; }
        if (j.status === "canceled") return;
        if (j.status === "failed") throw new Error(`PDF를 만들지 못했습니다: ${(j.error_message || "").split("\n")[0]}`);
      }
    }
    const url = `${BASE}/api/reports/${reportId}/pdf?inline=true&ts=${Date.now()}`;
    if (isNarrowScreen()) {
      modal.setStatus("쪽 이미지 준비 중…");
      const pages = await api(`/reports/${reportId}/pdf-pages`);
      modal.showPages(url, pages);
    } else {
      modal.show(url);
    }
  } catch (err) {
    modal.setStatus(`⚠ ${err.message}`, true);
  } finally {
    btn.disabled = false;
  }
}

function openPreviewModal() {
  const overlay = document.createElement("div");
  overlay.className = "preview-overlay";
  overlay.innerHTML = `
    <div class="preview-box">
      <div class="preview-head">
        <b>보고서 미리보기</b>
        <span class="preview-status">저장 확인 중…</span>
        <a class="secondary-link preview-dl" data-download="pdf" style="display:none;">↓ PDF 받기</a>
        <button type="button" class="preview-close">닫기</button>
      </div>
      <div class="preview-body"><div class="preview-wait">준비하는 중…</div></div>
    </div>`;
  document.body.appendChild(overlay);
  const prevOverflow = document.documentElement.style.overflow;
  document.documentElement.style.overflow = "hidden"; // 미리보기 중엔 뒤 화면이 대신 스크롤되지 않게
  const onKey = (e) => { if (e.key === "Escape") close(); };
  let closed = false;
  let closeHook = null;
  const close = () => {
    closed = true;
    if (closeHook) closeHook();
    overlay.remove();
    document.documentElement.style.overflow = prevOverflow;
    document.removeEventListener("keydown", onKey);
  };
  document.addEventListener("keydown", onKey);
  overlay.querySelector(".preview-close").addEventListener("click", close);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  const statusEl = overlay.querySelector(".preview-status");
  return {
    closed: () => closed,
    // 창을 닫을 때 할 일(PDF 만드는 중이면 취소) — 만들기가 끝나면 null로 푼다
    onClose(fn) {
      closeHook = fn;
      overlay.querySelector(".preview-close").textContent = fn ? "취소" : "닫기";
    },
    setStatus(text, bad) {
      statusEl.textContent = text;
      statusEl.classList.toggle("bad", !!bad);
      overlay.querySelector(".preview-wait").textContent = text;
    },
    show(url) {
      statusEl.textContent = "";
      const dl = overlay.querySelector(".preview-dl");
      dl.href = url.replace("inline=true", "inline=false");
      dl.dataset.reportId = reportId;
      dl.style.display = "";
      overlay.querySelector(".preview-body").innerHTML = `<iframe class="preview-frame" src="${url}" title="보고서 미리보기"></iframe>`;
    },
    // 폰: 쪽별 이미지를 위아래로 이어서(두 손가락 확대 가능). 판 번호(version)를 붙여 옛 이미지 캐시를 피한다.
    showPages(url, { count, version }) {
      statusEl.textContent = `${count}쪽`;
      const dl = overlay.querySelector(".preview-dl");
      dl.href = url.replace("inline=true", "inline=false");
      dl.dataset.reportId = reportId;
      dl.style.display = "";
      const body = overlay.querySelector(".preview-body");
      body.innerHTML = "";
      const list = document.createElement("div");
      list.className = "preview-pages";
      for (let i = 1; i <= count; i++) {
        const img = document.createElement("img");
        img.loading = i <= 2 ? "eager" : "lazy";
        img.alt = `${i}쪽`;
        img.src = `${BASE}/api/reports/${reportId}/pdf-pages/${i}.jpg?v=${version}`;
        list.appendChild(img);
      }
      body.appendChild(list);
    },
  };
}

// --- 페이지 시작: 각 섹션 불러오기(원래 인라인 스크립트의 실행 순서 그대로) ---
setupReportToc();
setupPhotoSlots("overview-slots", `${BASE}/api/reports/${reportId}/overview-photos`, "전경사진");
setupPhotoSlots("inspection-slots", `${BASE}/api/reports/${reportId}/inspection-photos`, "점검사진");
setupPreviousFindings();
setupProcessSlots("current-process-slots", `${BASE}/api/reports/${reportId}/current-process`);
setupProcessSlots("future-process-slots", `${BASE}/api/reports/${reportId}/future-process`);
setupFindings();
setupTbm();
setupMeasurements();
setupMaterials();
loadReport();
