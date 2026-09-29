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
