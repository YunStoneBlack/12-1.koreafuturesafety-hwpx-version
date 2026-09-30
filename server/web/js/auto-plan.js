// 지도 출장 자동 배치(2026-10-01) — 미리보기 창 + "📅 일정 없는 현장 N곳" 안내. 현장 화면·현장 목록·방문 달력이 같이 쓴다.
// 서버: server/api/routers/auto_plan.py(POST /calendar/auto-plan/preview|apply, GET /calendar/unplanned), 계산: server/api/visit_scheduler.py.
// 창 모양은 고객사 전송 창(css/mail.css)과 같은 틀, 이 기능만의 규칙은 css/auto-plan.css.

const AP_WD = "일월화수목금토";
const apEsc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const apDay = (iso) => {
  const d = new Date(`${iso}T00:00:00`);
  return `${d.getMonth() + 1}/${d.getDate()}(${AP_WD[d.getDay()]})`;
};
const apShort = (name) => (name || "").replace(/\s*현장$/, "");

// target: { siteId } 그 현장만(다른 현장 예정은 그대로, 기존 일정에 끼워 넣기) / { staffIds: [...] } 그 요원들의 진행 중 현장 전부
async function openAutoPlan(target, titleText, onDone) {
  const body = target.siteId != null ? { site_id: target.siteId } : { staff_ids: target.staffIds };
  const overlay = document.createElement("div");
  overlay.className = "mail-overlay";
  overlay.innerHTML = '<div class="mail-box ap-box" role="dialog" aria-modal="true"><div class="mail-wait">일정을 계산하는 중…</div></div>';
  document.body.appendChild(overlay);
  const box = overlay.querySelector(".mail-box");
  let busy = false;
  const close = () => { if (!busy) { overlay.remove(); document.removeEventListener("keydown", onKey); } };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  const head = `<div class="mail-head"><b>📅 지도 일정 자동 배치</b><span class="mail-sub">${apEsc(titleText)}</span></div>`;

  let pv;
  try {
    pv = await apiPost("/calendar/auto-plan/preview", body);
  } catch (err) {
    box.innerHTML = `${head}<div class="mail-msg bad">${apEsc(err.message)}</div>
      <div class="mail-foot"><button type="button" class="mail-cancel">닫기</button></div>`;
    box.querySelector(".mail-cancel").addEventListener("click", close);
    return;
  }

  // 현장별 안내(부족·배치 안 함) — 막지 않고 알려만 준다(사용자: 횟수를 다 못 채워도 큰일은 아님)
  const notes = pv.sites.filter((s) => s.note).map((s) =>
    `<div class="ap-note">ℹ️ <b>${apEsc(apShort(s.site_name))}</b> — ${apEsc(s.note)}</div>`).join("");
  const multiSite = pv.sites.length > 1;
  const byDay = new Map();
  for (const p of pv.plans) {
    if (!byDay.has(p.date)) byDay.set(p.date, []);
    byDay.get(p.date).push(p);
  }
  // 날짜 줄 — 여러 현장이면 그날 가는 현장들, 한 현장이면 "같이 가는 다른 현장"(묶였는지 보이게). 해가 바뀔 때만 연도 줄.
  let year = "";
  const rows = [...byDay.entries()].map(([date, ps]) => {
    const y = date.slice(0, 4);
    const yearHead = y !== year ? `<div class="ap-month">${Number(y)}년</div>` : "";
    year = y;
    const others = [...new Set(ps.flatMap((p) => p.with || []))].filter((n) => !ps.some((p) => p.site_name === n));
    const what = multiSite ? ps.map((p) => apEsc(apShort(p.site_name))).join(" · ") : "";
    const withText = others.length ? `<span class="ap-with">+ ${others.map((n) => apEsc(apShort(n))).join(", ")}와 함께</span>` : "";
    return `${yearHead}<div class="ap-row"><span class="ap-date">${apDay(date)}</span><span class="ap-what">${what}${withText}</span>
      ${ps[0].region ? `<span class="ap-region">${apEsc(ps[0].region)}</span>` : ""}</div>`;
  }).join("");
  const trips = byDay.size;
  const summary = pv.plans.length
    ? `<b>${pv.plans.length}회</b>를 ${multiSite ? `출장 <b>${trips}번</b>으로 ` : ""}넣습니다 — 마지막 지도는 준공 ${pv.finish_before_days}일 전까지.`
    : "넣을 일정이 없습니다(남은 회차가 없거나 공사 기간·총 횟수 정보가 없음).";
  const replaceNote = pv.replace_count
    ? `<div class="ap-sub">지금 자동으로 넣어 둔 예정 ${pv.replace_count}건은 이 일정으로 바뀝니다. 📌 사람이 정한 예정은 그대로 둡니다.</div>`
    : '<div class="ap-sub">📌 사람이 정한 예정은 그대로 두고, 같은 지역 출장이 있는 날에 맞춰 넣었습니다.</div>';

  box.innerHTML = `${head}
    <div class="ap-summary">${summary}</div>${pv.plans.length ? replaceNote : ""}${notes}
    ${pv.plans.length ? `<div class="ap-list">${rows}</div>` : ""}
    <div class="mail-msg" hidden></div>
    <div class="mail-foot"><button type="button" class="mail-cancel">취소</button>
      ${pv.plans.length ? '<button type="button" class="mail-primary ap-apply">이대로 넣기</button>' : ""}</div>`;
  box.querySelector(".mail-cancel").addEventListener("click", close);
  const applyBtn = box.querySelector(".ap-apply");
  if (!applyBtn) return;
  applyBtn.addEventListener("click", async () => {
    const msg = box.querySelector(".mail-msg");
    busy = true;
    applyBtn.disabled = true;
    applyBtn.textContent = "넣는 중…";
    try {
      const res = await apiPost("/calendar/auto-plan/apply", body);
      busy = false;
      close();
      if (onDone) onDone(res);
    } catch (err) {
      busy = false;
      applyBtn.disabled = false;
      applyBtn.textContent = "이대로 넣기";
      msg.hidden = false;
      msg.className = "mail-msg bad";
      msg.textContent = err.message;
    }
  });
}

// "📅 일정 없는 현장 N곳" — 누르면 펼쳐져 현장마다 [자동 배치]. 없으면 아무것도 안 그린다. onChanged: 넣은 뒤 화면 새로고침.
async function renderUnplannedNotice(container, onChanged) {
  let list;
  try {
    list = await api("/calendar/unplanned");
  } catch (_) {
    return; // 안내일 뿐 — 실패하면 조용히 넘어간다
  }
  container.innerHTML = "";
  if (!list.length) return;
  const wrap = document.createElement("div");
  wrap.className = "ap-notice";
  wrap.innerHTML = `<button type="button" class="ap-notice-head"><b>📅 일정 없는 현장 ${list.length}곳</b>
      <span>앞으로 갈 방문 예정이 하나도 없습니다 — 눌러서 자동 배치</span><i>▾</i></button><div class="ap-notice-list" hidden></div>`;
  const listEl = wrap.querySelector(".ap-notice-list");
  for (const s of list) {
    const row = document.createElement("div");
    row.className = "ap-notice-row";
    row.innerHTML = `<div><a></a><small></small></div><button type="button" class="secondary">📅 자동 배치</button>`;
    row.querySelector("a").textContent = s.site_name;
    row.querySelector("a").href = `site.html?id=${s.site_id}`;
    row.querySelector("small").textContent = `${s.staff_name || "담당 미지정"} · 남은 ${s.remaining}회`;
    row.querySelector("button").addEventListener("click", () =>
      openAutoPlan({ siteId: s.site_id }, s.site_name, () => { renderUnplannedNotice(container, onChanged); if (onChanged) onChanged(); }));
    listEl.appendChild(row);
  }
  wrap.querySelector(".ap-notice-head").addEventListener("click", () => {
    listEl.hidden = !listEl.hidden;
    wrap.classList.toggle("open", !listEl.hidden);
  });
  container.appendChild(wrap);
}
