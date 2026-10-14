// ---------- 보고서 화면 맨 아래 "K2B 제출 · 고객사 전송" 칸 왼쪽 반 K2B(2026-10-02 사용자: 현장 화면뿐 아니라 보고서 화면에서도 결과 보기) ----------
// GET /reports/{id}/k2b(현장 화면 제출 창과 같은 API)의 제출 기록으로 마지막 결과를 그린다 — 성공: 저장된 K2B 화면 사진,
// 실패: 이유 + "이렇게 하세요"(server/k2b/advice.py), 진행 중: 3초마다 다시 읽음. [📤 K2B 제출]은 js/k2b-submit.js 창 그대로.
// 지난 제출이 더 있으면 접힌 목록. 글자 넣기는 mail.js의 mailEsc, 모양은 css/k2b-submit.css(rk-*).

let k2bPanelTimer = null;

async function loadK2bPanel() {
  const stateEl = document.getElementById("k2b-state");
  if (!stateEl) return;
  clearTimeout(k2bPanelTimer);
  let info;
  try {
    info = await api(`/reports/${reportId}/k2b`);
  } catch (err) {
    stateEl.innerHTML = `<div class="mail-msg bad">K2B 기록을 못 읽었습니다: ${mailEsc(err.message)}</div>`;
    return;
  }
  const [last, ...older] = info.jobs;
  const shot = (j) => (j.has_shot
    ? `<a class="kb-shot rk-shot" href="${BASE}/api/k2b-jobs/${j.id}/shot?ts=${Date.now()}" data-k2b-job="${j.id}">
        <img src="${BASE}/api/k2b-jobs/${j.id}/shot?ts=${Date.now()}" alt="K2B 화면" loading="lazy" /><span>눌러서 크게 보기${j.shots > 1 ? ` (구역별 ${j.shots}장)` : ""}</span></a>` : "");
  const when = (j) => mailEsc((j.finished_at || j.created_at || "").slice(5).replace("-", "/"));
  const who = (j) => (j.created_by ? ` · ${mailEsc(j.created_by)}` : "");
  let html;
  if (!last) {
    html = `<div class="rk-none">아직 K2B에 제출하지 않았습니다.</div>` +
      (info.blockers.length ? `<div class="rk-block">제출 전에: ${info.blockers.map(mailEsc).join("<br>")}</div>` : "");
  } else if (last.status === "done") {
    html = `<div class="mail-msg ok">✓ ${when(last)} ${mailEsc(last.message)}${who(last)}</div>${shot(last)}`;
  } else if (last.status === "failed") {
    html = `<div class="mail-msg bad">✗ ${when(last)} 실패 — ${mailEsc(last.message)}${who(last)}</div>
      ${last.hint ? `<div class="kb-hint-do"><b>이렇게 하세요</b> ${mailEsc(last.hint)}</div>` : ""}${shot(last)}`;
  } else {
    html = `<div class="mail-msg kb-progress">K2B에 제출하는 중… (${last.status === "queued" ? "대기 중" : "입력·저장 중"}, 보통 1~2분)</div>`;
    k2bPanelTimer = setTimeout(loadK2bPanel, 3000);
  }
  if (older.length) {
    html += `<details class="rk-older"><summary>지난 제출 ${older.length}건</summary><ul>${older.map((j) => `<li>${when(j)} ${
      j.status === "done" ? `✓ ${mailEsc(j.message)}` : j.status === "failed" ? `✗ ${mailEsc(j.message)}` : "진행 중"}</li>`).join("")}</ul></details>`;
  }
  stateEl.innerHTML = html;
}

document.getElementById("k2b-open")?.addEventListener("click", () => {
  // 현장 화면 창과 같은 "현장명 N회차"(현장명은 report-core.js가 back-link에 넣어 둠)
  const site = document.getElementById("back-link")?.textContent.trim() || "";
  const visit = (document.getElementById("report-title")?.textContent || "").replace(" 보고서", "");
  openK2bModal(reportId, `${site} ${visit}`.trim(), loadK2bPanel);
});
// ---------- 오른쪽 반 "고객사 메일 전송"(2026-10-15 민재형 "반 나눠서 이메일 전송") ----------
// GET /reports/{id}/mail(현장 화면 메일 창과 같은 API)의 보낸 기록으로 마지막 전송을 그린다. [📧 고객사 전송] = mail.js 창 그대로
// (PDF가 없거나 수정 전 버전·만드는 중이면 창이 "PDF를 다시 만든 뒤 보내세요"로 막고, 서버도 한 번 더 막음).
async function loadMailPanel() {
  const stateEl = document.getElementById("mail-state");
  if (!stateEl) return;
  let info;
  try {
    info = await api(`/reports/${reportId}/mail`);
  } catch (err) {
    stateEl.innerHTML = `<div class="mail-msg bad">메일 기록을 못 읽었습니다: ${mailEsc(err.message)}</div>`;
    return;
  }
  const [last, ...older] = info.history || [];
  const day = (h) => mailEsc((h.sent_at || "").slice(5).replace("-", "/"));
  const by = (h) => (h.by ? ` · ${mailEsc(h.by)}` : "");
  let html;
  if (!info.configured) {
    html = `<div class="rk-none">메일 보내기 설정이 아직 안 됐습니다(회사 네이버 메일 연결 필요).</div>`;
  } else if (!last) {
    html = `<div class="rk-none">아직 고객사에 보내지 않았습니다.</div>` + (info.problem ? `<div class="rk-block">보내기 전에: ${mailEsc(info.problem)}</div>` : "");
  } else {
    html = `<div class="mail-msg ok">✓ ${day(last)} 보냄${by(last)}</div>
      <div class="rk-mail-to">받는 사람: ${mailEsc(last.to)}${last.cc ? `<br>참조: ${mailEsc(last.cc)}` : ""}</div>` +
      (info.problem ? `<div class="rk-block">다시 보내려면: ${mailEsc(info.problem)}</div>` : "");
  }
  if (older.length) {
    html += `<details class="rk-older"><summary>지난 전송 ${older.length}건</summary><ul>${older.map((h) => `<li>${day(h)} → ${mailEsc(h.to)}${by(h)}</li>`).join("")}</ul></details>`;
  }
  stateEl.innerHTML = html;
}

document.getElementById("mail-open")?.addEventListener("click", () => {
  const site = document.getElementById("back-link")?.textContent.trim() || "";
  const visit = (document.getElementById("report-title")?.textContent || "").replace(" 보고서", "");
  openMailModal(reportId, `${site} ${visit}`.trim(), loadMailPanel);
});
loadK2bPanel();
loadMailPanel();
