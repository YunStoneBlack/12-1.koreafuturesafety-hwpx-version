// 보고서 자동화 · 시특법 — 합본 PDF 인쇄 → 제출 현황 "합본 출력" 표시 (2026-10-31 민재형 "인쇄 버튼을 누르면 실제로 연동되게는 못하나?")
// 브라우저는 새 탭 PDF 보기의 인쇄 버튼이 눌렸는지 알려 주지 않아서: [🖨 인쇄]를 누르면 합본 PDF를 새 탭으로 열고, 이 화면으로 돌아오면
// "출력하셨나요? [출력함 표시] [아직]"을 한 번 묻는다(인쇄창이 닫혀도 인쇄했는지 취소했는지는 알 수 없으므로 사람이 확인).
// 쓰는 곳: sitok-round.js(회차 화면 [🖨 인쇄]), sitok-status.js(제출 현황 합본 출력 칸 🖨). 표시 API = POST /sitok/status/reports/{id}/mark {item:"print"}.
(function () {
  let pending = null; // {reportId, label, onDone, hidden, at}
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };

  // 합본 PDF를 새 탭으로 열고, 이 화면으로 돌아오면 물어봄. 팝업이 막혔으면 안내.
  window.openPrintMerged = function (reportId, label, onDone) {
    const w = window.open(`${BASE}/api/sitok/reports/${reportId}/file/pdf`, "_blank");
    if (!w) { alert("새 탭이 막혔습니다 — 주소창 오른쪽 팝업 허용을 누른 뒤 다시 누르세요."); return; }
    pending = { reportId, label: label || "", onDone, hidden: false, at: Date.now() };
  };

  function ask() {
    const p = pending;
    pending = null;
    if (!p) return;
    const overlay = document.createElement("div");
    overlay.className = "mail-overlay";
    overlay.innerHTML = `<div class="mail-box ss-mark" role="dialog" aria-modal="true">
      <div class="mail-head"><b>합본 출력</b><span class="mail-sub">${esc(p.label)}</span></div>
      <div class="mail-note">합본 PDF를 출력하셨나요? 출력했으면 제출 현황 "합본 출력" 칸이 오늘 날짜로 표시됩니다.</div>
      <label class="cd-field"><span>날짜</span><input type="date" class="pm-date" value="${today()}" /></label>
      <div class="mail-msg" hidden></div>
      <div class="mail-foot"><button type="button" class="m-close">아직</button><button type="button" class="mail-primary m-done">✓ 출력함 표시</button></div></div>`;
    document.body.appendChild(overlay);
    const close = () => overlay.remove();
    overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });
    overlay.querySelector(".m-close").addEventListener("click", close);
    overlay.querySelector(".m-done").addEventListener("click", async () => {
      try {
        await apiPost(`/sitok/status/reports/${p.reportId}/mark`, { item: "print", action: "done", date: overlay.querySelector(".pm-date").value || today() });
        close();
        if (typeof p.onDone === "function") p.onDone();
      } catch (err) {
        const m = overlay.querySelector(".mail-msg");
        m.hidden = false;
        m.className = "mail-msg bad";
        m.textContent = err.message;
      }
    });
  }

  // 새 탭으로 갔다가(숨김) 돌아오면(보임) 물어봄 — 탭을 안 바꿨으면(바로 돌아옴) 묻지 않음
  document.addEventListener("visibilitychange", () => {
    if (!pending) return;
    if (document.visibilityState === "hidden") { pending.hidden = true; return; }
    if (pending.hidden && Date.now() - pending.at > 3000) setTimeout(ask, 400);
  });
})();
