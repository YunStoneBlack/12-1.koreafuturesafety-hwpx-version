// 방문 달력 그날 목록의 두 창(2026-10-02 — 출장자와 보고서 담당자를 나눔, server/api/report_staff.py):
// [출장 담당자 변경] 요원 상자 머리줄 — 그날 그 사람의 출장 여러 곳을 한 번에 다른 사람에게(휴가·병가 대타). 출장자만 바뀌고 보고서 담당자는 그대로, 📌 고정.
//   현장 하나만 넘기는 건 카드의 [📅 일정 변경] → 대신 갈 요원(js/plan-change.js).
// [📝 보고서 담당 다시 나누기] 목록 위 — 그날 보고서가 아직 없는 예정의 보고서 담당자를 규칙대로 다시(바뀌는 것만 미리 보여 주고 적용).
// 서버: POST /calendar/day/{date}/move, POST /calendar/day/{date}/report-staff. 창 틀은 css/mail.css, 이 창 규칙은 css/day-staff.css. 글자는 auto-plan.js의 apEsc.

function dsOverlay(title) {
  const overlay = document.createElement("div");
  overlay.className = "mail-overlay";
  overlay.innerHTML = `<div class="mail-box ds-box" role="dialog" aria-modal="true"><div class="mail-head"><b>${apEsc(title)}</b></div>
    <div class="ds-body"><div class="mail-wait">불러오는 중…</div></div></div>`;
  document.body.appendChild(overlay);
  const close = () => { overlay.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  return { box: overlay.querySelector(".mail-box"), body: overlay.querySelector(".ds-body"), close };
}

// items: [{ planId, siteName, reportName }] — 그날 그 사람의 예정(보고서를 만든 다녀온 방문은 빼고)
function openMoveTraveler(date, fromId, fromName, items, staff, onDone) {
  const { body, close } = dsOverlay(`출장 담당자 변경 — ${apDay(date)} ${fromName || "담당 없음"}`);
  const others = staff.filter((s) => s.active && s.id !== fromId);
  body.innerHTML = `
    <label class="ds-field">누구에게 넘길까요?<select class="ds-to">${others.map((s) => `<option value="${s.id}">${apEsc(s.name)}</option>`).join("")}</select></label>
    <div class="ds-hint">넘길 현장 — 출장만 바뀌고 <b>보고서 담당자는 그대로</b>입니다. 넘긴 예정은 📌 고정(자동 배치가 안 바꿈).</div>
    <div class="ds-list">${items.map((it) => `<label class="ds-row"><input type="checkbox" value="${it.planId}" checked />
      <b>${apEsc(it.siteName)}</b><span>보고서: ${apEsc(it.reportName || "미정")}</span></label>`).join("")}</div>
    <div class="mail-msg bad ds-msg" hidden></div>
    <div class="mail-foot"><button type="button" class="ds-cancel">취소</button><button type="button" class="mail-primary ds-go">바꾸기</button></div>`;
  body.querySelector(".ds-cancel").addEventListener("click", close);
  body.querySelector(".ds-go").addEventListener("click", async (ev) => {
    const ids = [...body.querySelectorAll(".ds-list input:checked")].map((x) => Number(x.value));
    const to = Number(body.querySelector(".ds-to").value);
    const msg = body.querySelector(".ds-msg");
    if (!ids.length || !to) { msg.hidden = false; msg.textContent = "넘길 현장과 사람을 고르세요."; return; }
    ev.target.disabled = true;
    try {
      await apiPost(`/calendar/day/${date}/move`, { from_staff_id: fromId, to_staff_id: to, plan_ids: ids });
      close();
      if (onDone) onDone();
    } catch (err) {
      msg.hidden = false;
      msg.textContent = err.message;
      ev.target.disabled = false;
    }
  });
}

async function openRedistribute(date, onDone) {
  const { body, close } = dsOverlay(`📝 보고서 담당 다시 나누기 — ${apDay(date)}`);
  let r;
  try {
    r = await apiPost(`/calendar/day/${date}/report-staff`, { dry_run: true });
  } catch (err) {
    body.innerHTML = `<div class="mail-msg bad">${apEsc(err.message)}</div><div class="mail-foot"><button type="button" class="ds-cancel">닫기</button></div>`;
    body.querySelector(".ds-cancel").addEventListener("click", close);
    return;
  }
  const rows = r.rows;
  body.innerHTML = `
    <div class="ds-hint">직전 회차 보고서 담당 → (1회차면) 현장 담당이 기본, 그 사람이 그날 보고서 4곳이면 보고서 담당 순서대로 여유 있는 사람.
      보고서를 이미 만든 현장은 그대로입니다.</div>
    ${rows.length ? `<div class="ds-list">${rows.map((x) => `<div class="ds-row${x.changed ? " changed" : ""}${x.after ? "" : " none"}">
      <b>${apEsc(x.site_name)}</b><span>${x.changed ? `${apEsc(x.before || "미정")} → ${apEsc(x.after || "자리 없음")}` : apEsc(x.after || "자리 없음")}</span></div>`).join("")}</div>`
      : '<div class="ds-hint">이 날 보고서를 아직 안 만든 예정이 없습니다.</div>'}
    <div class="ds-hint">${r.changed ? `바뀌는 곳 ${r.changed}곳` : "바뀌는 곳이 없습니다"}${r.unassigned ? ` · 모두 4곳이 차서 정하지 못한 곳 ${r.unassigned}곳` : ""}</div>
    <div class="mail-msg bad ds-msg" hidden></div>
    <div class="mail-foot"><button type="button" class="ds-cancel">닫기</button>${r.changed ? '<button type="button" class="mail-primary ds-go">이대로 나누기</button>' : ""}</div>`;
  body.querySelector(".ds-cancel").addEventListener("click", close);
  body.querySelector(".ds-go")?.addEventListener("click", async (ev) => {
    ev.target.disabled = true;
    try {
      await apiPost(`/calendar/day/${date}/report-staff`, { dry_run: false });
      close();
      if (onDone) onDone();
    } catch (err) {
      const msg = body.querySelector(".ds-msg");
      msg.hidden = false;
      msg.textContent = err.message;
      ev.target.disabled = false;
    }
  });
}
