// 담당요원 탭 "보고서 담당 순서"(2026-10-02) — 보고서 담당자가 그날 보고서 4곳이 차면 이 순서로 여유 있는 사람(server/api/report_staff.py).
// GET/POST /staff/report-order. 쉬는(비활성) 요원은 목록에 안 나옴. ▲▼로 바꾸고 [순서 저장].

(function setupReportOrder() {
  const list = document.getElementById("report-order-list");
  const saveBtn = document.getElementById("report-order-save");
  const statusEl = document.getElementById("report-order-status");
  if (!list) return;
  let order = [];

  const draw = () => {
    list.innerHTML = "";
    if (!order.length) {
      list.innerHTML = '<div class="empty-note">활성 담당요원이 없습니다.</div>';
      return;
    }
    order.forEach((s, i) => {
      const row = document.createElement("div");
      row.className = "ro-row";
      row.innerHTML = `<span class="ro-no">${i + 1}</span><span class="ro-name"></span>
        <button type="button" class="secondary ro-up" ${i === 0 ? "disabled" : ""} aria-label="위로">▲</button>
        <button type="button" class="secondary ro-down" ${i === order.length - 1 ? "disabled" : ""} aria-label="아래로">▼</button>`;
      row.querySelector(".ro-name").textContent = s.name;
      const swap = (j) => {
        [order[i], order[j]] = [order[j], order[i]];
        saveBtn.disabled = false;
        statusEl.textContent = "바뀐 순서를 저장하세요";
        draw();
      };
      row.querySelector(".ro-up").addEventListener("click", () => swap(i - 1));
      row.querySelector(".ro-down").addEventListener("click", () => swap(i + 1));
      list.appendChild(row);
    });
  };

  const load = async () => {
    try {
      order = await api("/staff/report-order");
      draw();
    } catch (err) {
      list.innerHTML = "";
      showError(errorEl, err);
    }
  };

  saveBtn.addEventListener("click", async () => {
    saveBtn.disabled = true;
    try {
      order = await apiPost("/staff/report-order", { staff_ids: order.map((s) => s.id) });
      statusEl.textContent = "저장했습니다";
      draw();
    } catch (err) {
      saveBtn.disabled = false;
      showError(errorEl, err);
    }
  });
  window.reloadReportOrder = load; // 요원을 추가·비활성화하면 staff.html이 다시 부름
  load();
})();
