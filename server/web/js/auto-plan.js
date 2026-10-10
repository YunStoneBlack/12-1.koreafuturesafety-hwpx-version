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
// "고모지구(1.3km), 초가팔리천" — 같이 가는 현장 이름 + 거리(현장 좌표 server/api/geocode.py, 모르면 이름만). plan-change.js도 쓴다.
const apWithKm = (names, kms) => names.map((n, i) => (kms && kms[i] != null ? `${apShort(n)}(${kms[i]}km)` : apShort(n))).join(", ");

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
    `<div class="ap-note">ℹ️ <b>${apEsc(apShort(s.site_name))}</b>${s.staff_name ? ` (${apEsc(s.staff_name)})` : ""} — ${apEsc(s.note)}</div>`).join("");
  const multiSite = pv.sites.length > 1;
  const multiStaff = new Set(pv.plans.filter((p) => !p.need_sub).map((p) => p.staff_id)).size > 1; // 달력 요원 단위(여러 명) — 줄마다 요원 이름
  const byDay = new Map(); // 날짜(+요원) → 그날 넣는 것들 = 출장 한 번. "⚠ 대타 필요"(담당 없음)는 따로 한 줄씩
  for (const p of pv.plans) {
    const key = p.need_sub ? `${p.date}|sub|${p.site_id}` : multiStaff ? `${p.date}|${p.staff_id}` : p.date;
    if (!byDay.has(key)) byDay.set(key, []);
    byDay.get(key).push(p);
  }
  // 날짜 줄 — 여러 현장이면 그날 가는 현장들, 한 현장이면 "같이 가는 다른 현장"(묶였는지 보이게). 해가 바뀔 때만 연도 줄.
  let year = "";
  const rows = [...byDay.values()].map((ps) => {
    const date = ps[0].date;
    const y = date.slice(0, 4);
    const yearHead = y !== year ? `<div class="ap-month">${Number(y)}년</div>` : "";
    year = y;
    const others = [...new Set(ps.flatMap((p) => p.with || []))].filter((n) => !ps.some((p) => p.site_name === n));
    const who = multiStaff && ps[0].staff_name ? `<b class="ap-who">${apEsc(ps[0].staff_name)}</b> ` : "";
    const what = ps[0].need_sub
      ? `<b class="ap-subtag">⚠ 대타 필요</b> ${multiSite ? apEsc(apShort(ps[0].site_name)) + " " : ""}<span class="ap-subnote">거리가 멀어 ${apEsc(ps[0].owner_name || "담당 요원")}님이 못 가는 날</span>`
      : multiSite ? who + ps.map((p) => apEsc(apShort(p.site_name))).join(" · ") : "";
    const kmOf = Object.fromEntries(ps.flatMap((p) => (p.with || []).map((n, i) => [n, (p.with_km || [])[i]])));
    const withText = others.length ? `<span class="ap-with">+ ${apEsc(apWithKm(others, others.map((n) => kmOf[n])))}와 함께</span>` : "";
    return `${yearHead}<div class="ap-row"><span class="ap-date">${apDay(date)}</span><span class="ap-what">${what}${withText}</span>
      ${ps[0].region ? `<span class="ap-region">${apEsc(ps[0].region)}</span>` : ""}</div>`;
  }).join("");
  const subCount = pv.plans.filter((p) => p.need_sub).length;
  const trips = [...byDay.values()].filter((ps) => !ps[0].need_sub).length;
  const summary = pv.plans.length
    ? `<b>${pv.plans.length}회</b>를 ${multiSite ? `출장 <b>${trips}번</b>으로 ` : ""}넣습니다 — 마지막 지도는 준공 ${pv.finish_before_days}일 전까지.` +
      (subCount ? `<div class="ap-subsum">⚠ 그중 <b>${subCount}건</b>은 거리가 멀어 담당 요원이 갈 날이 없어 <b>대타 필요</b>로 넣습니다 — 넣은 뒤 달력에서 [📅 일정 변경] → [대신 갈 요원]으로 정해 주세요.</div>` : "")
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

// [🔁 지난 일정 재배치](2026-10-10 사용자·민재형) — 날짜가 지났는데 보고서가 없는 예정. 현장마다 남은 횟수보다 앞으로 예정이 모자라면
// 지난 예정을 새 날짜로 옮기고(📌 고정), 넉넉하면 지운다. 넣을 날이 없으면 그대로 둔다. 서버: server/api/routers/missed_replan.py.
async function openMissedReplan(onDone) {
  const overlay = document.createElement("div");
  overlay.className = "mail-overlay";
  overlay.innerHTML = '<div class="mail-box ap-box" role="dialog" aria-modal="true"><div class="mail-wait">지난 일정을 계산하는 중…</div></div>';
  document.body.appendChild(overlay);
  const box = overlay.querySelector(".mail-box");
  let busy = false;
  const close = () => { if (!busy) { overlay.remove(); document.removeEventListener("keydown", onKey); } };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  const head = '<div class="mail-head"><b>🔁 지난 일정 재배치</b><span class="mail-sub">날짜가 지났는데 보고서가 없는 방문 예정</span></div>';

  let pv;
  try {
    pv = await apiPost("/calendar/missed/replan", { dry_run: true });
  } catch (err) {
    box.innerHTML = `${head}<div class="mail-msg bad">${apEsc(err.message)}</div>
      <div class="mail-foot"><button type="button" class="mail-cancel">닫기</button></div>`;
    box.querySelector(".mail-cancel").addEventListener("click", close);
    return;
  }
  const c = pv.counts;
  const TAG = { move: "옮김", delete: "지움", stuck: "넣을 날 부족" };
  const rows = pv.items.map((it) => {
    const to = it.action === "move" ? ` → <b>${apDay(it.new_date)}</b>` : "";
    const withText = it.with.length ? `<span class="ap-with">+ ${apEsc(apWithKm(it.with.slice(0, 3)))}${it.with.length > 3 ? ` 외 ${it.with.length - 3}곳` : ""}와 함께</span>` : "";
    return `<div class="ap-row"><span class="ap-date">${apDay(it.old_date)}</span>
      <span class="ap-what">${it.staff_name ? `<b class="ap-who">${apEsc(it.staff_name)}</b> ` : ""}${apEsc(apShort(it.site_name))}${to}${withText}
        <span class="mr-why">${apEsc(it.reason)}</span></span><span class="mr-tag ${it.action}">${TAG[it.action]}</span></div>`;
  }).join("");
  const actionable = c.move + c.delete;
  const summary = pv.items.length
    ? `지난 일정 <b>${pv.items.length}건</b> — 새 날짜로 옮김 <b>${c.move}</b> · 지움 <b>${c.delete}</b>${c.stuck ? ` · 넣을 날 부족 <b>${c.stuck}</b>(그대로 둠)` : ""}`
    : "지난 일정이 없습니다.";
  box.innerHTML = `${head}
    <div class="ap-summary">${summary}</div>
    ${pv.items.length ? `<div class="ap-sub">현장마다 남은 횟수와 앞으로의 예정 수를 비교해, 모자란 만큼만 옮기고(📌 고정) 넉넉하면 지웁니다. 다른 예정은 건드리지 않습니다.</div>
      <div class="ap-list">${rows}</div>` : ""}
    <div class="mail-msg" hidden></div>
    <div class="mail-foot"><button type="button" class="mail-cancel">${actionable ? "취소" : "닫기"}</button>
      ${actionable ? '<button type="button" class="mail-primary mr-apply">이대로 정리</button>' : ""}</div>`;
  box.querySelector(".mail-cancel").addEventListener("click", close);
  const applyBtn = box.querySelector(".mr-apply");
  if (!applyBtn) return;
  applyBtn.addEventListener("click", async () => {
    const msg = box.querySelector(".mail-msg");
    busy = true;
    applyBtn.disabled = true;
    applyBtn.textContent = "정리하는 중…";
    try {
      const res = await apiPost("/calendar/missed/replan", { dry_run: false });
      busy = false;
      close();
      if (onDone) onDone(res);
    } catch (err) {
      busy = false;
      applyBtn.disabled = false;
      applyBtn.textContent = "이대로 정리";
      msg.hidden = false;
      msg.className = "mail-msg bad";
      msg.textContent = err.message;
    }
  });
}

// [🔁 지난 일정 재배치] 버튼에 건수 — 0이면 숨김
async function refreshMissedButton(btn) {
  try {
    const { count } = await api("/calendar/missed");
    btn.hidden = !count;
    btn.innerHTML = `🔁 지난 일정 재배치<b>${count}</b>`;
  } catch (_) {
    btn.hidden = true; // 안내일 뿐 — 실패하면 조용히 숨김
  }
}

// "⚠ 예정이 모자란 현장 N곳"(2026-10-10 민재형) — 남은 횟수(총 − 다녀온)보다 앞으로 예정이 적은 진행 중 현장. 자동 배치가 규칙에 막히면
// 넣을 수 있는 만큼만 넣어서 생김. [채워 넣기] = 모자란 만큼만 새 자동 예정을 더함(기존 예정은 그대로). 서버: server/api/routers/missed_replan.py.
async function renderShortNotice(container, onChanged) {
  let list;
  try {
    list = await api("/calendar/short");
  } catch (_) {
    return; // 안내일 뿐
  }
  container.innerHTML = "";
  if (!list.length) return;
  const total = list.reduce((n, s) => n + s.short, 0);
  const wrap = document.createElement("div");
  wrap.className = "ap-notice ap-short";
  wrap.innerHTML = `<div class="ap-notice-headrow"><button type="button" class="ap-notice-head"><b>⚠ 예정이 모자란 현장 ${list.length}곳 (${total}회)</b>
      <span>남은 지도 횟수보다 앞으로의 방문 예정이 적습니다 — 눌러서 현장별로 보기</span><i>▾</i></button>
      <button type="button" class="secondary ap-fill-all">모두 채워 넣기</button></div><div class="ap-notice-list" hidden></div>`;
  const listEl = wrap.querySelector(".ap-notice-list");
  const done = () => { renderShortNotice(container, onChanged); if (onChanged) onChanged(); };
  for (const s of list) {
    const row = document.createElement("div");
    row.className = "ap-notice-row";
    row.innerHTML = `<div><a></a><small></small></div><span class="ap-short-num"></span><button type="button" class="secondary">채워 넣기</button>`;
    row.querySelector("a").textContent = s.site_name;
    row.querySelector("a").href = `site.html?id=${s.site_id}`;
    row.querySelector("small").textContent = `${s.staff_name || "담당 미지정"} · 남은 ${s.remaining}회 · 예정 ${s.planned}건`;
    row.querySelector(".ap-short-num").textContent = `${s.short}회 모자람`;
    row.querySelector("button").addEventListener("click", () => openShortFill([s.site_id], s.site_name, done));
    listEl.appendChild(row);
  }
  wrap.querySelector(".ap-notice-head").addEventListener("click", () => {
    listEl.hidden = !listEl.hidden;
    wrap.classList.toggle("open", !listEl.hidden);
  });
  wrap.querySelector(".ap-fill-all").addEventListener("click", () => openShortFill(null, `모자란 현장 ${list.length}곳 전부`, done));
  container.appendChild(wrap);
}

// [채워 넣기] 미리보기 창 — siteIds: [현장] 또는 null(전부)
async function openShortFill(siteIds, titleText, onDone) {
  const body = siteIds ? { site_ids: siteIds } : {};
  const overlay = document.createElement("div");
  overlay.className = "mail-overlay";
  overlay.innerHTML = '<div class="mail-box ap-box" role="dialog" aria-modal="true"><div class="mail-wait">넣을 날을 찾는 중…</div></div>';
  document.body.appendChild(overlay);
  const box = overlay.querySelector(".mail-box");
  let busy = false;
  const close = () => { if (!busy) { overlay.remove(); document.removeEventListener("keydown", onKey); } };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  const head = `<div class="mail-head"><b>⚠ 모자란 횟수 채워 넣기</b><span class="mail-sub">${apEsc(titleText)}</span></div>`;

  let pv;
  try {
    pv = await apiPost("/calendar/short/fill", { ...body, dry_run: true });
  } catch (err) {
    box.innerHTML = `${head}<div class="mail-msg bad">${apEsc(err.message)}</div>
      <div class="mail-foot"><button type="button" class="mail-cancel">닫기</button></div>`;
    box.querySelector(".mail-cancel").addEventListener("click", close);
    return;
  }
  const multi = new Set(pv.items.map((it) => it.site_id)).size > 1;
  const rows = pv.items.map((it) => {
    const withText = it.with.length ? `<span class="ap-with">+ ${apEsc(apWithKm(it.with.slice(0, 3)))}${it.with.length > 3 ? ` 외 ${it.with.length - 3}곳` : ""}와 함께</span>` : "";
    return `<div class="ap-row"><span class="ap-date">${it.date ? apDay(it.date) : "—"}</span>
      <span class="ap-what">${it.staff_name ? `<b class="ap-who">${apEsc(it.staff_name)}</b> ` : ""}${multi || !it.date ? apEsc(apShort(it.site_name)) : ""}${withText}
        ${it.date ? "" : `<span class="mr-why">${apEsc(it.reason)}</span>`}</span>
      <span class="mr-tag ${it.date ? "move" : "stuck"}">${it.date ? "넣음" : "넣을 날 부족"}</span></div>`;
  }).join("");
  const summary = pv.items.length
    ? `<b>${pv.added}회</b>를 더 넣습니다${pv.stuck ? ` · <b>${pv.stuck}회</b>는 마감 전에 넣을 날이 없습니다` : ""}.`
    : "모자란 횟수가 없습니다.";
  box.innerHTML = `${head}
    <div class="ap-summary">${summary}</div>
    ${pv.items.length ? `<div class="ap-sub">지금 있는 예정은 그대로 두고, 그 현장 다른 방문과 간격이 고르게 · 같은 지역 출장이 있는 날에 맞춰 더합니다.</div>
      <div class="ap-list">${rows}</div>` : ""}
    <div class="mail-msg" hidden></div>
    <div class="mail-foot"><button type="button" class="mail-cancel">${pv.added ? "취소" : "닫기"}</button>
      ${pv.added ? '<button type="button" class="mail-primary sf-apply">이대로 넣기</button>' : ""}</div>`;
  box.querySelector(".mail-cancel").addEventListener("click", close);
  const applyBtn = box.querySelector(".sf-apply");
  if (!applyBtn) return;
  applyBtn.addEventListener("click", async () => {
    const msg = box.querySelector(".mail-msg");
    busy = true;
    applyBtn.disabled = true;
    applyBtn.textContent = "넣는 중…";
    try {
      const res = await apiPost("/calendar/short/fill", { ...body, dry_run: false });
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
