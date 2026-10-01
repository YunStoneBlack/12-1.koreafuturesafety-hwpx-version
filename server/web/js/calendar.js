// 방문 달력(calendar.html, 2026-09-30 시안 (나)) — 다녀온 방문(보고서 지도일) + 방문 예정 + 지난 예정 + 요원·날짜별 하루 4곳 딱지.
// 색은 요원별이 아니라 상태별(2026-10-01 사용자 — 요원이 20~30명이면 색으로 구분 못 함, 이름은 칸에 적혀 있음):
// 예정 = 파란 테두리만, 지난 예정 = 빨간 점선 테두리, 작성 중(PDF 전·후 포함) = 연한 파랑, 제출 완료 = 진한 파랑(css/calendar.css .ev-*). (2026-10-01 "마지막 지도일 + 15일" 기한 ⏰·⚠ 예정없음은 없앰 — 실제 규칙이 아니었음.) 날짜를 누르면 오른쪽(폰은 아래)에 그날 목록과
// "방문 예정 넣기". 볼 사람: 나만(그룹웨어 로그인 ↔ 담당요원 연결) / 고른 요원(여러 명) / 전체 — 고른 것은 이 브라우저에 기억.
// 달력 모양·공휴일은 그룹웨어 달력과 같은 FullCalendar 6.1.15 + 그룹웨어 app.css `.fc` 규칙 + 그룹웨어 /api/holidays.
// 데이터: GET /calendar?start=&end= (server/api/routers/calendar.py), 예정 넣기·고치기·지우기: /calendar/plans.

const errorEl = document.getElementById("error");
const STATE_LABEL = { writing: "작성 중", pdf_ready: "PDF 만듦", outdated: "PDF 다시 만들어야 함", submitted: "제출 완료" };
const PREF_KEY = "kfsc-report:calendar-view";
const isPhone = () => matchMedia("(max-width: 760px)").matches;
const pad2 = (n) => String(n).padStart(2, "0");
const ymd = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
const WEEK = ["일", "월", "화", "수", "목", "금", "토"];

let data = null; // 마지막으로 받은 달력 데이터
let dataKey = "";
let selected = ymd(new Date());
let holidays = {};
const holidayYears = {};
let view = loadPref();

function loadPref() {
  try {
    const v = JSON.parse(localStorage.getItem(PREF_KEY) || "{}");
    return { mode: ["me", "pick", "all"].includes(v.mode) ? v.mode : null, picked: Array.isArray(v.picked) ? v.picked : null };
  } catch (_) {
    return { mode: null, picked: null };
  }
}
function savePref() {
  try { localStorage.setItem(PREF_KEY, JSON.stringify(view)); } catch (_) { /* 저장 못 해도 동작엔 지장 없음 */ }
}

const staffById = () => Object.fromEntries((data?.staff || []).map((s) => [s.id, s]));
const visitClass = (state) => (state === "submitted" ? "ev-submitted" : "ev-writing");
// "⚠ 대타 필요"(source=sub) — 자동 배치가 담당 요원은 먼 현장과 섞어야만 갈 수 있는 회차를 담당 없이 넣은 것(사람이 [일정 변경] → [대신 갈 요원])
const planClass = (p) => (p.state === "missed" ? "ev-missed" : p.source === "sub" ? "ev-sub" : "ev-plan");
const planOwner = (p) => p.staff_id ?? p.owner_staff_id; // 대타 필요는 요원이 비어 있으니 현장 담당자 기준으로 보이기
const shortName = (name) => (name && name.length >= 3 ? name.slice(1) : name || "");
const shortSite = (name) => (name || "").replace(/\s*현장$/, "");

// 볼 사람 — 나만이면 내 요원 하나, 고른 요원이면 체크한 요원들, 전체면 null(모두, 요원 없는 것 포함)
function shownStaff() {
  if (view.mode === "all") return null;
  if (view.mode === "me") return new Set(data?.me_staff_id ? [data.me_staff_id] : []);
  return new Set(view.picked || []);
}
function visible(staffId) {
  const s = shownStaff();
  return s === null || s.has(staffId);
}

// ---------- 볼 사람 고르기 ----------
function renderFilter() {
  const staffMap = staffById();
  const me = data?.me_staff_id;
  if (!view.mode) view.mode = me ? "me" : "all";
  if (view.mode === "me" && !me) view.mode = "all";
  if (!view.picked) view.picked = me ? [me] : [];
  document.querySelectorAll(".cal-seg button").forEach((b) => {
    b.classList.toggle("on", b.dataset.mode === view.mode);
    if (b.dataset.mode === "me") {
      b.disabled = !me;
      b.title = me ? `${staffMap[me]?.name || ""}님의 방문만` : "그룹웨어 계정과 이어진 담당요원이 아니라 '나만' 보기를 쓸 수 없습니다(담당요원 탭).";
    }
  });
  const box = document.getElementById("cal-chips");
  box.innerHTML = "";
  const shown = shownStaff();
  for (const s of data.staff.filter((s) => s.active || data.visits.some((v) => v.staff_id === s.id))) {
    const on = shown === null || shown.has(s.id);
    const chip = document.createElement("label");
    chip.className = "cal-chip" + (on ? " on" : "");
    chip.innerHTML = `<input type="checkbox" ${on ? "checked" : ""} /><span></span>`;
    chip.querySelector("span").textContent = s.name + (s.id === me ? " (나)" : "");
    chip.querySelector("input").addEventListener("change", (e) => {
      // 칩을 누르면 "고른 요원"으로 — 지금 보이는 사람들에서 이 사람을 더하거나 뺀다
      const cur = shownStaff() === null ? data.staff.map((x) => x.id) : [...shownStaff()];
      const next = new Set(cur);
      if (e.target.checked) next.add(s.id); else next.delete(s.id);
      view = { mode: "pick", picked: [...next] };
      savePref();
      refresh();
    });
    box.appendChild(chip);
  }
}

// [📅 자동 배치] — 지금 보고 있는 요원들(나만 = 나, 고른 요원 = 체크한 사람, 전체 = 활동 중인 요원 전부)의 진행 중 현장 전부(js/auto-plan.js 미리보기 창)
document.getElementById("cal-autoplan").addEventListener("click", () => {
  if (!data) return;
  const shown = shownStaff();
  const ids = shown === null ? data.staff.filter((s) => s.active).map((s) => s.id) : [...shown];
  if (!ids.length) { alert("볼 사람(요원)을 먼저 고르세요."); return; }
  const names = ids.map((id) => staffById()[id]?.name).filter(Boolean);
  const title = names.length === 1 ? `${names[0]}님의 진행 중 현장 전부` : `${names[0]} 외 ${names.length - 1}명의 진행 중 현장 전부`;
  openAutoPlan({ staffIds: ids }, title, () => {
    reload();
    renderUnplannedNotice(document.getElementById("ap-notice"), () => reload());
  });
});
document.querySelectorAll(".cal-seg button").forEach((b) => b.addEventListener("click", () => {
  view.mode = b.dataset.mode;
  if (view.mode === "pick" && !(view.picked || []).length) view.picked = data?.staff.filter((s) => s.active).map((s) => s.id) || [];
  savePref();
  refresh();
}));

// ---------- 달력 일정 ----------
function buildEvents() {
  if (!data) return [];
  const staffMap = staffById();
  const ev = [];
  for (const v of data.visits) {
    if (!visible(v.staff_id)) continue;
    const st = staffMap[v.staff_id];
    ev.push({
      title: `${v.state === "submitted" ? "✓ " : ""}${st ? shortName(st.name) + " · " : ""}${shortSite(v.site_name)} ${v.visit_no}회`,
      start: v.date, allDay: true, classNames: [visitClass(v.state)],
      extendedProps: { kind: "visit" },
    });
  }
  for (const p of data.plans) {
    if (p.state === "done" || !visible(planOwner(p))) continue;
    const st = staffMap[p.staff_id];
    ev.push({
      id: `plan-${p.id}`,
      title: p.source === "sub" && p.state !== "missed" ? `⚠ 대타 필요 · ${shortSite(p.site_name)}`
        : `${p.state === "missed" ? "지난 예정" : p.source === "manual" ? "📌" : "예정"} ${st ? shortName(st.name) + " · " : ""}${shortSite(p.site_name)}`,
      start: p.date, allDay: true, classNames: [planClass(p)], startEditable: !isPhone(),
      extendedProps: { kind: "plan", planId: p.id },
    });
  }
  return ev;
}

// 하루 4곳 딱지 + 공휴일 + 고른 날 표시 — FullCalendar가 칸을 다시 그릴 때마다(달 이동·일정 갱신) 다시 칠한다.
function decorateCells() {
  const staffMap = staffById();
  const loads = {};
  for (const l of data?.day_load || []) {
    if (!visible(l.staff_id) || l.count < data.limit) continue;
    (loads[l.date] ||= []).push(l);
  }
  document.querySelectorAll("#cal .fc-daygrid-day").forEach((cell) => {
    const date = cell.getAttribute("data-date");
    const other = cell.classList.contains("fc-day-other");
    const holiday = !other ? holidays[date] : null;
    cell.classList.toggle("holiday", !!holiday);
    cell.title = holiday ? holiday.name : "";
    cell.classList.toggle("cal-selected", date === selected);
    const top = cell.querySelector(".fc-daygrid-day-top");
    if (!top) return;
    top.querySelectorAll(".holiday-label, .cal-cap").forEach((el) => el.remove());
    if (holiday && holiday.label) {
      const lab = document.createElement("div");
      lab.className = "holiday-label";
      lab.textContent = holiday.name;
      top.appendChild(lab);
    }
    for (const l of loads[date] || []) {
      const cap = document.createElement("span");
      cap.className = "cal-cap" + (l.count > data.limit ? " over" : "");
      cap.textContent = isPhone() ? `${l.count}/${data.limit}` : `${shortName(staffMap[l.staff_id]?.name || "")} ${l.count}/${data.limit}`;
      top.appendChild(cap);
    }
  });
}

async function loadHolidays(start, end) {
  const years = [...new Set([start.getFullYear(), new Date(end.getTime() - 86400000).getFullYear()])];
  await Promise.all(years.map(async (y) => {
    if (holidayYears[y]) return;
    holidayYears[y] = true;
    try {
      const res = await fetch(`/api/holidays?year=${y}`, { credentials: "include", redirect: "manual" });
      if (!res.ok) return;
      for (const h of await res.json()) holidays[h.date] = { name: h.name, label: h.label };
    } catch (_) { /* 그룹웨어 공휴일을 못 받으면 주말 색만 */ }
  }));
}

const cal = new FullCalendar.Calendar(document.getElementById("cal"), {
  initialView: "dayGridMonth",
  locale: "ko",
  height: "auto",
  fixedWeekCount: false,
  headerToolbar: { left: "title", center: "", right: "prev,next today" },
  buttonText: { today: "오늘" },
  dayMaxEvents: false,
  dayCellContent: (arg) => (isPhone() ? arg.dayNumberText.replace("일", "") : arg.dayNumberText), // 폰은 칸이 좁아 숫자만
  eventOrder: (a, b) => ["visit", "plan"].indexOf(a.extendedProps.kind) - ["visit", "plan"].indexOf(b.extendedProps.kind),
  events: async (info, success, failure) => {
    const start = ymd(info.start);
    const end = ymd(new Date(info.end.getTime() - 86400000));
    const key = `${start}~${end}`;
    try {
      if (key !== dataKey || !data) {
        const [d] = await Promise.all([api(`/calendar?start=${start}&end=${end}`), loadHolidays(info.start, info.end)]);
        data = d;
        dataKey = key;
        renderFilter();
      }
      success(buildEvents());
    } catch (err) {
      showError(errorEl, err);
      failure(err);
    }
  },
  eventsSet: () => { decorateCells(); renderDay(); },
  datesSet: () => decorateCells(),
  dateClick: (info) => selectDay(info.dateStr),
  eventClick: (info) => selectDay(ymd(info.event.start)),
  eventDrop: async (info) => {
    const p = data.plans.find((x) => x.id === info.event.extendedProps.planId);
    const date = ymd(info.event.start);
    if (!p || !confirmLoad(p.staff_id, date, p.site_id, `${shortSite(p.site_name)} 예정을 ${date}로 옮길까요?`)) {
      info.revert();
      return;
    }
    try {
      await apiPatch(`/calendar/plans/${p.id}`, { plan_date: date });
      selected = date;
      reload();
    } catch (err) {
      info.revert();
      showError(errorEl, err);
    }
  },
});
cal.render();
renderUnplannedNotice(document.getElementById("ap-notice"), () => reload());

function refresh() { // 데이터는 그대로, 볼 사람만 바뀜
  renderFilter();
  cal.refetchEvents();
}
function reload() { // 서버에서 다시
  dataKey = "";
  cal.refetchEvents();
}

function selectDay(date) {
  selected = date;
  decorateCells();
  renderDay();
  if (isPhone()) document.getElementById("cal-day").scrollIntoView({ behavior: "smooth", block: "start" });
}

// 그날 이 요원이 맡는 현장 수(이 현장 제외) — 넣거나 옮기면 한도를 넘는지
function siteCountOn(staffId, date, exceptSiteId) {
  if (!staffId || !data) return 0;
  const sites = new Set();
  for (const v of data.visits) if (v.staff_id === staffId && v.date === date) sites.add(v.site_id);
  for (const p of data.plans) if (p.staff_id === staffId && p.date === date && p.state !== "done") sites.add(p.site_id);
  sites.delete(exceptSiteId);
  return sites.size;
}
function confirmLoad(staffId, date, siteId, question) {
  const n = siteCountOn(staffId, date, siteId);
  if (n < data.limit) return question ? confirm(question) : true;
  const name = staffById()[staffId]?.name || "";
  return confirm(`${name}님은 ${date}에 이미 ${n}곳입니다(하루 ${data.limit}곳 한도). 그래도 ${question ? question.replace(/\?$/, "") : "넣을까요"}?`);
}

// ---------- 고른 날 목록 ----------
function renderDay() {
  const body = document.getElementById("cal-day-body");
  if (!data) return;
  const staffMap = staffById();
  const d = new Date(selected + "T00:00:00");
  const visits = data.visits.filter((v) => v.date === selected && visible(v.staff_id));
  const plans = data.plans.filter((p) => p.date === selected && p.state !== "done" && visible(planOwner(p)));
  const holiday = holidays[selected];
  body.innerHTML = `<h3 class="cal-day-title"></h3><div class="cal-day-list"></div>`;
  body.querySelector(".cal-day-title").textContent =
    `${d.getMonth() + 1}월 ${d.getDate()}일 (${WEEK[d.getDay()]})${holiday ? " · " + holiday.name : ""}`;
  const list = body.querySelector(".cal-day-list");
  // 요원별 묶음(2026-10-01 사용자 — 여러 명이 출장 가는 날 누가 어디 가는지 한눈에): 머리줄 "👤 이름 · N곳" + 그 요원의 다녀온 방문·예정.
  // 담당 없는 "⚠ 대타 필요"는 맨 아래 따로. 머리줄 오른쪽은 나중에 [🚗 동선 짜기] 자리.
  const groups = new Map(); // key → { title, sites:Set, items:[] }
  const groupOf = (key) => {
    if (!groups.has(key)) groups.set(key, { key, sites: new Set(), items: [] });
    return groups.get(key);
  };
  for (const v of visits) {
    const el = document.createElement("div");
    el.className = `cal-item ${visitClass(v.state)}`;
    el.innerHTML = '<i></i><div class="cal-item-main"><b></b><small></small></div>';
    addSiteLinks(el, v.site_id);
    el.querySelector("b").textContent = `${v.site_name} ${v.visit_no}회차`;
    el.querySelector("small").textContent = STATE_LABEL[v.state] || "";
    const a = document.createElement("a");
    a.href = `report.html?id=${v.report_id}`;
    a.className = "cal-act";
    a.textContent = "보고서 열기";
    el.appendChild(a);
    const g = groupOf(v.staff_id ?? "none");
    g.sites.add(v.site_id);
    g.items.push(el);
  }
  for (const p of plans) {
    const g = groupOf(p.source === "sub" && p.state !== "missed" ? "sub" : p.staff_id ?? "none");
    g.sites.add(p.site_id);
    g.items.push(planItem(p, staffMap));
  }
  if (!groups.size) {
    list.innerHTML = '<div class="empty-note" style="padding:12px 0;">이 날은 방문·예정이 없습니다.</div>';
  }
  const order = (key) => (key === "sub" ? 1e9 : key === "none" ? 1e9 - 1 : data.staff.findIndex((s) => s.id === key));
  const loadOf = Object.fromEntries(data.day_load.filter((x) => x.date === selected).map((x) => [x.staff_id, x.count]));
  for (const g of [...groups.values()].sort((a, b) => order(a.key) - order(b.key))) {
    const box = document.createElement("section");
    box.className = `cal-group${g.key === "sub" ? " sub" : ""}`;
    box.innerHTML = '<div class="cal-group-head"><b></b><span class="cal-group-n"></span><span class="cal-group-warn"></span></div>';
    box.querySelector("b").textContent = g.key === "sub" ? "⚠ 대타 필요" : g.key === "none" ? "담당요원 없음" : `👤 ${staffMap[g.key]?.name || ""}`;
    box.querySelector(".cal-group-n").textContent = `${g.sites.size}곳`;
    const load = loadOf[g.key] || 0;
    if (load >= data.limit) box.querySelector(".cal-group-warn").textContent = load > data.limit ? "하루 한도를 넘었습니다" : "하루 4곳 다 참";
    if (typeof g.key === "number") { // [🚗 동선 짜기] — 회사 → 이 요원의 그날 현장들(최적 순서) → 회사(js/route-plan.js)
      const go = document.createElement("button");
      go.type = "button";
      go.className = "cal-route";
      go.textContent = "🚗 동선 짜기";
      go.addEventListener("click", () => openRoutePlan(selected, g.key, staffMap[g.key]?.name || ""));
      box.querySelector(".cal-group-head").appendChild(go);
    }
    for (const el of g.items) box.appendChild(el);
    list.appendChild(box);
  }
  body.appendChild(planForm());
}

function planItem(p, staffMap) {
  const el = document.createElement("div");
  el.className = `cal-item plan ${planClass(p)}`;
  el.innerHTML = `<i></i><div class="cal-item-main"><b></b><small></small></div>
    <div class="cal-plan-acts">
      <button type="button" class="secondary p-report">보고서 만들기</button>
      <button type="button" class="secondary p-edit">고치기</button>
      <button type="button" class="secondary p-del" style="color:var(--crit);">삭제</button>
    </div>`;
  el.querySelector("b").textContent = `${p.state === "missed" ? "지난 예정" : p.source === "sub" ? "⚠ 대타 필요" : p.source === "manual" ? "📌 방문 예정(고정)" : "방문 예정"} · ${p.site_name}`;
  addSiteLinks(el, p.site_id);
  // [📅 일정 변경] — [📞 전화] [📍 지도] 오른쪽(현장에 전화해 보고 바로 옮기게, js/plan-change.js)
  const main = el.querySelector(".cal-item-main");
  let links = main.querySelector(".site-links");
  if (!links) {
    links = document.createElement("div");
    links.className = "site-links";
    main.appendChild(links);
  }
  const change = document.createElement("button");
  change.type = "button";
  change.className = "site-link plan-change";
  change.innerHTML = '<span class="sl-ico">📅</span><span class="sl-short">일정 변경</span><span class="sl-full">일정 변경</span>';
  change.addEventListener("click", () => openPlanChange(p.id, (date) => {
    selected = date;
    const { activeStart, activeEnd } = cal.view;
    if (date < ymd(activeStart) || date >= ymd(activeEnd)) cal.gotoDate(date); // 다른 달로 옮겼으면 그 달로
    reload();
  }));
  links.appendChild(change); // [📞 전화] [📍 지도] 오른쪽(2026-10-01 사용자)
  el.querySelector("small").textContent = p.source === "sub"
    ? `거리가 멀어 담당 요원(${staffMap[p.owner_staff_id]?.name || "담당 없음"})이 이날 갈 수 없습니다 — [📅 일정 변경] → [대신 갈 요원]으로 정해 주세요`
    : [p.memo, p.state === "missed" ? "이 날 보고서가 없습니다" : ""].filter(Boolean).join(" · "); // 요원 이름은 묶음 머리줄에
  el.querySelector(".p-del").addEventListener("click", async () => {
    if (!confirm(`${p.site_name} 방문 예정을 지울까요?`)) return;
    try { await api(`/calendar/plans/${p.id}`, { method: "DELETE" }); reload(); } catch (err) { showError(errorEl, err); }
  });
  el.querySelector(".p-report").addEventListener("click", async () => {
    if (!confirm(`${p.site_name} 새 보고서를 지도일 ${p.date}로 만들까요?`)) return;
    try {
      const rep = await apiPost(`/sites/${p.site_id}/reports`, { guidance_date: p.date, ...(p.staff_id ? { assigned_staff_id: p.staff_id } : {}) });
      location.href = `report.html?id=${rep.id}`;
    } catch (err) {
      showError(errorEl, err);
    }
  });
  el.querySelector(".p-edit").addEventListener("click", () => {
    if (el.querySelector(".cal-form")) return;
    el.appendChild(planForm(p));
  });
  return el;
}

// 그날 목록 한 줄에 진행 막대 + [📞 전화] [📍 지도](현장책임자 연락처, 지도 방문 주소 — 서버 site_links)
function addSiteLinks(el, siteId) {
  const info = siteId != null ? data.site_links?.[siteId] : null;
  const pace = info ? sitePaceBox(info.pace) : null; // 진행 막대(데스크톱 현장 카드와 같은 계산)
  if (pace) el.querySelector(".cal-item-main").appendChild(pace);
  const links = info ? siteLinkButtons(info.phone, info.map_address) : null;
  if (links) el.querySelector(".cal-item-main").appendChild(links);
}

// 예정 넣기(p 없음) / 고치기(p 있음) 칸
function planForm(p) {
  const wrap = document.createElement("div");
  wrap.className = "cal-form";
  const editing = !!p;
  if (!editing) {
    wrap.innerHTML = '<button type="button" class="secondary cal-add">+ 이 날 방문 예정 넣기</button>';
    wrap.querySelector(".cal-add").addEventListener("click", () => wrap.replaceWith(planFields(null)));
    return wrap;
  }
  return planFields(p);
}

function planFields(p) {
  const wrap = document.createElement("div");
  wrap.className = "cal-form open";
  wrap.innerHTML = `
    <label>현장</label><select class="f-site"><option value="">현장 고르기…</option></select>
    <div class="field-grid">
      <div><label>담당요원</label><select class="f-staff"><option value="">(없음)</option></select></div>
      <div><label>날짜</label><input type="date" class="f-date" /></div>
    </div>
    <label>메모 <span style="font-weight:400;color:var(--muted);">(선택, 예: 오후 2시)</span></label><input class="f-memo" maxlength="100" />
    <div class="edit-actions"><button type="button" class="f-save">${p ? "저장" : "예정 넣기"}</button>
      <button type="button" class="secondary f-cancel">취소</button></div>`;
  const siteSel = wrap.querySelector(".f-site");
  const sites = data.sites.slice();
  if (p && !sites.some((s) => s.id === p.site_id)) sites.unshift({ id: p.site_id, name: p.site_name, staff_id: p.staff_id });
  for (const s of sites) siteSel.add(new Option(s.name, s.id));
  const staffSel = wrap.querySelector(".f-staff");
  for (const s of data.staff.filter((s) => s.active || s.id === p?.staff_id)) staffSel.add(new Option(s.name, s.id));
  siteSel.value = p ? p.site_id : "";
  staffSel.value = p?.staff_id ?? (view.mode === "me" && data.me_staff_id ? data.me_staff_id : "");
  wrap.querySelector(".f-date").value = p ? p.date : selected;
  wrap.querySelector(".f-memo").value = p?.memo || "";
  siteSel.addEventListener("change", () => { // 현장을 고르면 그 현장 담당요원으로
    const s = data.sites.find((x) => String(x.id) === siteSel.value);
    if (s && s.staff_id) staffSel.value = s.staff_id;
  });
  wrap.querySelector(".f-cancel").addEventListener("click", () => renderDay());
  wrap.querySelector(".f-save").addEventListener("click", async (e) => {
    errorEl.style.display = "none";
    const body = {
      site_id: Number(siteSel.value) || null,
      staff_id: Number(staffSel.value) || null,
      plan_date: wrap.querySelector(".f-date").value || null,
      memo: wrap.querySelector(".f-memo").value,
    };
    if (!body.site_id || !body.plan_date) { alert("현장과 날짜를 고르세요."); return; }
    if (!confirmLoad(body.staff_id, body.plan_date, body.site_id, null)) return;
    e.target.disabled = true;
    try {
      if (p) await apiPatch(`/calendar/plans/${p.id}`, body); else await apiPost("/calendar/plans", body);
      selected = body.plan_date;
      const { activeStart, activeEnd } = cal.view;
      if (selected < ymd(activeStart) || selected >= ymd(activeEnd)) cal.gotoDate(selected); // 다른 달로 넣었으면 그 달로
      reload();
    } catch (err) {
      showError(errorEl, err);
      e.target.disabled = false;
    }
  });
  return wrap;
}
