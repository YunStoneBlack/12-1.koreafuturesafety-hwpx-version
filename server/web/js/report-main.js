// report.html 스크립트 — PDF 생성·한글 받기·로그아웃 + 페이지 시작 시 실행(맨 아래).
// report.html에서 순서대로 불러오는 5개 파일 중 하나(core → photos → work → support → main). 파일끼리는
// 전역 함수/상수를 공유하고, 페이지 시작 시 실행하는 호출은 전부 report-main.js 맨 아래에 모아 두었다
// (앞 파일이 뒤 파일 함수를 불러오는 시점 문제를 없애려고 — 여기엔 정의만 둔다).

// 데스크톱과 같이 "확인했습니다" 체크를 해야 PDF 생성 버튼이 켜진다(AI 작성 내용 재확인 안내).
document.getElementById("confirm-check").addEventListener("change", (e) => {
  document.getElementById("render-btn").disabled = !e.target.checked;
});
document.getElementById("hwpx-link").href = `${BASE}/api/reports/${reportId}/hwpx`;

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
  } catch (err) {
    btn.disabled = false;
    showError(errorEl, err);
  }
});

function pollJob(jobId) {
  const statusEl = document.getElementById("job-status");
  const btn = document.getElementById("render-btn");
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const job = await api(`/jobs/${jobId}`);
      if (job.status === "queued") {
        statusEl.textContent = "대기 중 (다른 작업 처리 중)...";
      } else if (job.status === "rendering") {
        statusEl.textContent = "한글 프로그램으로 PDF 생성 중... (몇 초~십몇 초 걸릴 수 있어요)";
      } else if (job.status === "done") {
        clearInterval(pollTimer);
        btn.disabled = false;
        statusEl.innerHTML = `완료! <a href="${BASE}/api/jobs/${jobId}/download">PDF 다운로드</a>`;
      } else if (job.status === "failed") {
        clearInterval(pollTimer);
        btn.disabled = false;
        statusEl.textContent = `생성 실패: ${job.error_message.split("\n")[0]} (다시 시도해보세요)`;
      }
    } catch (err) {
      clearInterval(pollTimer);
      btn.disabled = false;
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
      el.textContent = '1번 서명은 "서명 저장"을 눌러야 저장됩니다';
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
// PC는 화면 위 창(iframe), 폰은 창 안 PDF 표시가 잘 안 돼서 새 탭 — 팝업 차단을 피하려고 누르는 순간 빈 탭을 먼저 연다.
const isNarrowScreen = () => window.matchMedia("(max-width: 760px)").matches;

async function previewReport() {
  if (notifySigField && notifySigField.isDirty() &&
      !confirm("1번 현장책임자 서명 변경을 아직 저장하지 않았습니다. 저장하지 않은 채로 미리볼까요?")) return;
  const btn = document.getElementById("toc-preview");
  const tab = isNarrowScreen() ? window.open("", "_blank") : null;
  if (tab) tab.document.write('<p style="font-family:sans-serif;padding:24px;">보고서 미리보기를 준비하는 중입니다… (최대 30초)</p>');
  const modal = tab ? null : openPreviewModal();
  btn.disabled = true;
  try {
    await autosaveFlush();
    const st = await api(`/reports/${reportId}/pdf-status`);
    if (!st.has_pdf || st.outdated) {
      const job = await apiPost(`/reports/${reportId}/render`);
      const started = Date.now();
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500));
        const j = await api(`/jobs/${job.id}`);
        if (modal) modal.setStatus(`PDF 만드는 중… ${Math.round((Date.now() - started) / 1000)}초 (보통 20~30초)`);
        if (j.status === "done") break;
        if (j.status === "failed") throw new Error(`PDF를 만들지 못했습니다: ${(j.error_message || "").split("\n")[0]}`);
      }
    }
    const url = `${BASE}/api/reports/${reportId}/pdf?inline=true&ts=${Date.now()}`;
    if (tab) tab.location.href = url;
    else modal.show(url);
  } catch (err) {
    if (tab) tab.close();
    if (modal) modal.setStatus(`⚠ ${err.message}`, true);
    else showError(errorEl, err);
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
        <a class="secondary-link preview-dl" style="display:none;">↓ PDF 받기</a>
        <button type="button" class="preview-close">닫기</button>
      </div>
      <div class="preview-body"><div class="preview-wait">준비하는 중…</div></div>
    </div>`;
  document.body.appendChild(overlay);
  const onKey = (e) => { if (e.key === "Escape") close(); };
  const close = () => { overlay.remove(); document.removeEventListener("keydown", onKey); };
  document.addEventListener("keydown", onKey);
  overlay.querySelector(".preview-close").addEventListener("click", close);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  const statusEl = overlay.querySelector(".preview-status");
  return {
    setStatus(text, bad) {
      statusEl.textContent = text;
      statusEl.classList.toggle("bad", !!bad);
      overlay.querySelector(".preview-wait").textContent = text;
    },
    show(url) {
      statusEl.textContent = "";
      const dl = overlay.querySelector(".preview-dl");
      dl.href = url.replace("inline=true", "inline=false");
      dl.style.display = "";
      overlay.querySelector(".preview-body").innerHTML = `<iframe class="preview-frame" src="${url}" title="보고서 미리보기"></iframe>`;
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
