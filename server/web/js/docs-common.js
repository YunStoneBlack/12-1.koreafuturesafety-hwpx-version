// ---------- 서류 자동화 공통(2026-10-06) — 계약 목록·제출 현황·일정 달력이 같이 씀. GET /contracts 한 번(server/api/routers/contracts.py) ----------
// 제출 판정·단계·기한은 서버(server/contract_docs/contract_status.py) 한 곳 — 여기선 보여 주기만.

const DC_KINDS = [["start", "착수계"], ["done", "완수계"]];

async function dcLoad() {
  return api("/contracts");
}

function dcMoney(n) {
  return n == null || n === "" ? "" : `${Number(n).toLocaleString("ko-KR")}원`;
}

function dcDays(iso) { // 오늘부터 며칠(지났으면 음수)
  if (!iso) return null;
  const t = new Date(); t.setHours(0, 0, 0, 0);
  return Math.round((new Date(`${iso}T00:00:00`) - t) / 86400000);
}

// 착수계·완수계 한 칸 상태: ✓ 제출(만든 날) / 미제출 · 기한 D-n·지남 / 기한 없음
function dcDocState(c, kind) {
  const m = c.made[kind];
  if (m.submitted) return { cls: "ok", text: `✓ ${m.at.slice(5, 10).replace("-", "/")} 제출` };
  if (kind === "done" && !c.made.start.submitted) return { cls: "idle", text: "착수계 먼저" };
  const d = dcDays(c.due[kind]);
  if (d == null) return { cls: "idle", text: "미제출" };
  if (d < 0) return { cls: "bad", text: `미제출 · 기한 ${-d}일 지남` };
  if (d <= 7) return { cls: "warn", text: `미제출 · D-${d}` };
  return { cls: "idle", text: `미제출 · ${c.due[kind].slice(5).replace("-", "/")}까지` };
}

// 삭제 비밀번호 묻는 작은 창(설정 탭의 회사 공용 삭제 비밀번호 — 현장 삭제와 같음). 취소하면 null.
function dcAskPassword(message) {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "mail-overlay";
    overlay.innerHTML = `<div class="mail-box" role="dialog" aria-modal="true">
      <div class="mail-head"><b>🗑 용역 계약 삭제</b><span class="mail-sub">${mailEsc(message)}</span></div>
      <input type="password" class="mail-input" placeholder="삭제 비밀번호" autocomplete="off" />
      <div class="mail-note"><a href="docs-settings.html">설정 탭</a>에서 정한 삭제 비밀번호(현장 삭제와 같음)</div>
      <div class="mail-foot"><button type="button" class="dc-cancel">취소</button><button type="button" class="mail-primary dc-ok" style="background:var(--crit);border-color:var(--crit);">삭제</button></div></div>`;
    document.body.appendChild(overlay);
    const input = overlay.querySelector("input");
    const done = (v) => { overlay.remove(); resolve(v); };
    overlay.querySelector(".dc-cancel").addEventListener("click", () => done(null));
    overlay.querySelector(".dc-ok").addEventListener("click", () => input.value ? done(input.value) : input.focus());
    input.addEventListener("keydown", (e) => { if (e.key === "Enter" && input.value) done(input.value); if (e.key === "Escape") done(null); });
    overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) done(null); });
    input.focus();
  });
}

function dcSearchText(c) {
  return `${c.title} ${c.client} ${c.contract_no} ${c.site_label}`.toLowerCase();
}
