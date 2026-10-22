// 보고서 자동화 · 시특법 — 방문 달력(sitok-calendar.html, 2026-10-15 민재형 문서번호 일치화 문서 "보고서 달력관리").
// 시설물 카드(묶인 동은 하나)마다 반기 하루씩 — 자동 배치 규칙은 server/sitok/visit_plan.py(같은 시·군 같은 날, 하루 건물 4개, 관급 착수일 1주일 안).
// PC: 칸을 끌어 다른 날로(📌 사람이 정한 날 — 자동 배치가 안 건드림, 그날 4개 넘으면 물어봄), 날짜 누르면 오른쪽 그날 상세(날 바꾸기·지우기·이 날 일정 넣기).
// 폰: 산안법 달력처럼 달력 아래 고른 날(처음 오늘) 출장만, 날짜·막대를 누르면 그날로(10/23 사용자 — 예전엔 그달 날짜별 목록 + 작은 창).
// 위 알림 = 계약기간 안인데 일정이 없는 반기 N곳 → [자동으로 잡기](미리보기 → 잡기).
// 색: 정기 파랑·정밀 보라, ✓ = 그 반기 보고서 만듦(흐리게), 빨간 점선 = 지난 날인데 보고서 없음. API server/api/routers/sitok_calendar.py.

(function () {
  const errorEl = document.getElementById("error");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const WEEK = ["일", "월", "화", "수", "목", "금", "토"];
  const isPhone = () => matchMedia("(max-width: 760px)").matches;
  const pad = (n) => String(n).padStart(2, "0");
  const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const addDay = (s, n) => { const d = new Date(`${s}T00:00:00`); d.setDate(d.getDate() + n); return ymd(d); };
  const endOf = (v) => v.end || v.date; // 일정 범위(10/19 민재형 "일정을 범위 설정 가능하도록") — 끝이 없으면 하루
  const covers = (v, d) => v.date <= d && d <= endOf(v);
  let data = { visits: [], day_load: {}, day_cap: 4, facilities: [], missing: 0 };
  let selected = ymd(new Date());
  const holidays = {};
  const holidayYears = {};

  async function loadHolidays(start, end) {
    const years = [...new Set([start.getFullYear(), new Date(end.getTime() - 86400000).getFullYear()])];
    await Promise.all(years.map(async (y) => {
      if (holidayYears[y]) return;
      holidayYears[y] = true;
      try {
        const res = await fetch(`/api/holidays?year=${y}`, { credentials: "include", redirect: "manual" });
        if (!res.ok) return;
        for (const h of await res.json()) holidays[h.date] = { name: h.name, label: h.label };
      } catch (_) { /* 공휴일을 못 받으면 주말 색만 */ }
    }));
  }

  const vTitle = (v) => `${v.pinned ? "📌" : ""}${v.state === "done" || v.state === "field" ? "✓ " : ""}${v.facility.mgmt_no} ${v.facility.name}`;
  const vClass = (v) => [v.kind === "정밀" ? "k-pre" : "k-reg", `s-${v.state}`];
  function events() {
    return data.visits.map((v) => ({ id: String(v.id), title: vTitle(v), start: v.date, end: addDay(endOf(v), 1), allDay: true, classNames: vClass(v),
      startEditable: !isPhone(), durationEditable: !isPhone(), extendedProps: { v } })); // PC는 막대 끝을 끌어 범위를 늘리고 줄임
  }
  const loadOf = (date) => data.day_load[date] || 0;

  function decorateCells() {
    document.querySelectorAll("#sc-cal .fc-daygrid-day").forEach((cell) => {
      const date = cell.getAttribute("data-date");
      const holiday = !cell.classList.contains("fc-day-other") ? holidays[date] : null;
      cell.classList.toggle("holiday", !!holiday);
      cell.classList.toggle("dk-selected", date === selected);
      cell.title = holiday ? holiday.name : "";
      const top = cell.querySelector(".fc-daygrid-day-top");
      if (!top) return;
      top.querySelectorAll(".holiday-label, .sc-load").forEach((el) => el.remove());
      if (holiday && holiday.label) {
        const lab = document.createElement("div");
        lab.className = "holiday-label";
        lab.textContent = holiday.name;
        top.appendChild(lab);
      }
      const n = loadOf(date);
      if (n) {
        const b = document.createElement("span");
        b.className = `sc-load${n > data.day_cap ? " over" : ""}`;
        b.textContent = n;
        b.title = `그날 건물 ${n}개${n > data.day_cap ? ` — 하루 ${data.day_cap}개 넘음` : ""}`;
        top.appendChild(b);
      }
    });
  }

  // 일정 없는 반기 알림 + [자동으로 잡기]
  function renderNotice() {
    const el = document.getElementById("sc-notice");
    el.hidden = !data.missing;
    if (!data.missing) return;
    el.innerHTML = `<span>📅 <b>일정 없는 반기 ${data.missing}개</b>(시설물 ${data.missing_units}곳) — 계약기간 안인데 점검 날이 안 잡혀 있습니다</span>
      <button type="button" class="btn-sm" id="sc-fill">자동으로 잡기</button>`;
    document.getElementById("sc-fill").addEventListener("click", openFill);
  }
  async function openFill() {
    const overlay = document.createElement("div");
    overlay.className = "mail-overlay";
    overlay.innerHTML = '<div class="mail-box sc-fill-box" role="dialog" aria-modal="true"><div class="mail-wait">계산하는 중…</div></div>';
    document.body.appendChild(overlay);
    const box = overlay.querySelector(".mail-box");
    const close = () => overlay.remove();
    overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });
    let out;
    try {
      out = await apiPost("/sitok/calendar/fill", { dry_run: true });
    } catch (err) {
      box.innerHTML = `<div class="mail-msg bad">${esc(err.message)}</div><div class="mail-foot"><button type="button" class="f-close">닫기</button></div>`;
      box.querySelector(".f-close").addEventListener("click", close);
      return;
    }
    const rows = out.planned;
    const d = (s) => { if (!s) return "-"; const x = new Date(`${s}T00:00:00`); return `${x.getFullYear()}.${x.getMonth() + 1}.${x.getDate()} (${WEEK[x.getDay()]})`; };
    box.innerHTML = `<div class="mail-head"><b>📅 자동으로 잡기</b><span class="mail-sub">같은 시·군은 같은 날, 하루 건물 ${data.day_cap}개까지, 관급은 착수일 1주일 안 — 이미 잡힌 날은 그대로</span></div>
      <div class="sc-fill-list">${rows.map((p) => `<div class="sc-fill-row"><span class="site-no">${esc(p.facility.mgmt_no)}</span><b>${esc(p.facility.name)}</b>
          <span class="sc-k ${p.kind === "정밀" ? "pre" : ""}">${esc(p.kind)}</span><span class="mail-note">${p.year} ${esc(p.half)} · ${esc(p.facility.region || "지역 모름")}</span>
          <span class="sc-fill-date">${d(p.date)}</span>${p.note ? `<span class="mail-note sc-fill-note">${esc(p.note)}</span>` : ""}</div>`).join("") || '<div class="mail-note">잡을 일정이 없습니다.</div>'}</div>
      <div class="mail-msg" hidden></div>
      <div class="mail-foot"><button type="button" class="f-close">닫기</button>${rows.some((p) => p.date) ? `<button type="button" class="mail-primary f-apply">${rows.filter((p) => p.date).length}개 잡기</button>` : ""}</div>`;
    box.querySelector(".f-close").addEventListener("click", close);
    const ap = box.querySelector(".f-apply");
    if (ap) ap.addEventListener("click", async () => {
      ap.disabled = true;
      try {
        await apiPost("/sitok/calendar/fill", { dry_run: false });
        close();
        reload();
      } catch (err) {
        const m = box.querySelector(".mail-msg");
        m.hidden = false;
        m.className = "mail-msg bad";
        m.textContent = err.message;
        ap.disabled = false;
      }
    });
  }

  // 그날 상세(PC 오른쪽) / 폰 작은 창 — 같은 카드
  const STATE = { done: "✓ 그 반기 보고서 만듦", field: "✓ 현장점검 완료 — 보고서는 아직", missed: "⚠ 지난 날 — 현장점검 완료 안 됨", planned: "예정" }; // field = 현장 조사 [✓ 조사 완료]·제출 현황 [현장점검](10/18)
  function visitCard(v) {
    const f = v.facility;
    const link = v.report_id ? `sitok-round.html?report=${v.report_id}` : `sitok-facility.html?id=${f.id}`;
    return `<div class="dk-item sc-item ${vClass(v).join(" ")}" data-id="${v.id}">
      <div class="dk-item-kind">${esc(v.kind)} · ${v.year} ${esc(v.half)}${v.pinned ? " · 📌 사람이 정함" : " · 자동"}</div>
      <b><span class="site-no">${esc(f.mgmt_no)}</span> <a href="${link}">${esc(f.name)}</a>${f.buildings > 1 ? ` <small>(${f.buildings}동)</small>` : ""}</b>
      <small>${esc([f.region, f.address].filter(Boolean).join(" · "))}</small>
      <div class="dk-item-state${v.state === "done" || v.state === "field" ? " ok" : ""}">${STATE[v.state] || ""}</div>
      ${v.memo ? `<small>메모: ${esc(v.memo)}</small>` : ""}
      <div class="sc-links"></div><div class="sc-contact" hidden></div>
      <div class="dk-item-act sc-act"><span class="sc-range"><input type="date" class="sc-move" value="${v.date}" aria-label="시작 날" /><span class="sc-tilde">~</span>
        <input type="date" class="sc-end" value="${endOf(v)}" min="${v.date}" aria-label="끝 날" /></span><button type="button" class="secondary sc-del">지우기</button></div>
    </div>`;
  }
  function wireCards(root) {
    root.querySelectorAll(".sc-item").forEach((card) => {
      const v = data.visits.find((x) => String(x.id) === card.dataset.id);
      wireContact(card, v);
      card.querySelector(".sc-move").addEventListener("change", (e) => { if (e.target.value) moveVisit(v, e.target.value); });
      card.querySelector(".sc-end").addEventListener("change", (e) => { if (e.target.value) setEnd(v, e.target.value); });
      card.querySelector(".sc-del").addEventListener("click", async () => {
        if (!confirm(`${v.facility.mgmt_no} ${v.facility.name} ${v.date} 일정을 지울까요?${v.pinned ? "" : "\n(자동으로 잡은 날 — 지우면 다음 [자동으로 잡기] 때 다시 잡힐 수 있어요)"}`)) return;
        try { await api(`/sitok/calendar/visits/${v.id}`, { method: "DELETE" }); document.querySelector(".mail-overlay.sc-ov")?.remove(); reload(); } catch (err) { showError(errorEl, err); }
      });
    });
  }
  // 전화 = 서류 자동화 계약 정보의 "현장 담당" 연락처(10/20 민재형 — 시설물 칸 관리주체·담당자 전화는 안 씀).
  // 없으면 [📞 현장 담당 등록], 있으면 옆 [✏] — 여기서 고치면 계약 정보 현장 담당도 같이 바뀜(PATCH …/site-contact).
  function wireContact(card, v) {
    const s = v.site;
    const box = card.querySelector(".sc-links");
    const links = siteLinkButtons(v.phone, v.facility.address) || Object.assign(document.createElement("div"), { className: "site-links" }); // 현장 담당, 비면 관리주체 전화
    box.appendChild(links);
    if (!s) return; // 서류 자동화에 계약이 없으면 관리주체 전화만(현장 담당을 둘 곳 없음)
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = s.phone ? "site-link sc-edit" : "site-link sc-reg";
    btn.title = "현장 담당 연락처 — 서류 자동화 계약 정보의 현장 담당과 같은 칸";
    btn.innerHTML = s.phone ? '<span class="sl-ico">✏️</span>' : '<span class="sl-ico">📞</span><span>현장 담당 등록</span>';
    const tel = links.querySelector(".site-link.tel");
    if (tel) tel.after(btn); else links.prepend(btn);
    if (tel) tel.title = s.phone ? `현장 담당${s.manager ? ` ${s.manager}` : ""}에게 전화(PC에선 번호 복사)` : "관리주체 전화 — 현장 담당 번호를 넣으면 그 번호로 바뀜(PC에선 번호 복사)";
    const form = card.querySelector(".sc-contact");
    btn.addEventListener("click", (e) => {
      e.preventDefault(); e.stopPropagation();
      form.hidden = !form.hidden;
      if (form.hidden) return;
      form.innerHTML = `<div class="sc-c-head">현장 담당 <small>— 서류 자동화 계약 정보와 같은 칸</small></div>
        <input type="text" class="sc-c-name" placeholder="이름(관리소장 등)" value="${esc(s.manager)}" />
        <input type="tel" class="sc-c-phone" placeholder="연락처 010-0000-0000" value="${esc(s.phone)}" />
        <div class="sc-c-act"><button type="button" class="secondary sc-c-cancel">취소</button><button type="button" class="btn-sm sc-c-save">저장</button></div>`;
      form.querySelector(".sc-c-phone").focus();
      form.querySelector(".sc-c-cancel").addEventListener("click", () => { form.hidden = true; });
      form.querySelector(".sc-c-save").addEventListener("click", async () => {
        const phone = form.querySelector(".sc-c-phone").value.trim();
        const manager = form.querySelector(".sc-c-name").value.trim();
        try { await apiPatch(`/sitok/calendar/visits/${v.id}/site-contact`, { phone, manager }); document.querySelector(".mail-overlay.sc-ov")?.remove(); reload(); }
        catch (err) { alert(err.message); }
      });
    });
  }

  function renderDay() {
    const body = document.getElementById("sc-day-body");
    const dt = new Date(`${selected}T00:00:00`);
    const h = holidays[selected];
    const items = data.visits.filter((v) => covers(v, selected));
    const n = loadOf(selected);
    body.innerHTML = `<h3 class="dk-day-title${h || dt.getDay() === 0 ? " red" : ""}">${dt.getMonth() + 1}월 ${dt.getDate()}일 (${WEEK[dt.getDay()]})${h ? ` · ${esc(h.name)}` : ""}
        ${n ? `<span class="sc-load${n > data.day_cap ? " over" : ""}">${n}</span>` : ""}</h3>
      ${items.length ? items.map(visitCard).join("") : '<div class="empty-note">이 날은 점검 일정이 없습니다.</div>'}
      <div class="sc-add"><select class="sc-add-f" aria-label="시설물"><option value="">+ 이 날 일정 넣기 — 시설물 고르기</option>
        ${data.facilities.slice().sort((a, b) => String(a.mgmt_no).localeCompare(String(b.mgmt_no), "ko", { numeric: true })).map((f) => `<option value="${f.id}">${esc(f.mgmt_no)} ${esc(f.name)}${f.region ? ` · ${esc(f.region)}` : ""}</option>`).join("")}</select>
        <button type="button" class="btn-sm sc-add-btn">넣기</button></div>`;
    wireCards(body);
    body.querySelector(".sc-add-btn").addEventListener("click", async () => {
      const fid = Number(body.querySelector(".sc-add-f").value);
      if (!fid) return;
      const f = data.facilities.find((x) => x.id === fid);
      if (loadOf(selected) + (f ? f.buildings : 1) > data.day_cap && !confirm(`그날 건물이 ${data.day_cap}개를 넘습니다. 그래도 넣을까요?`)) return;
      try { await apiPost("/sitok/calendar/visits", { facility_id: fid, plan_date: selected }); reload(); } catch (err) { showError(errorEl, err); }
    });
  }
  function openVisit(v) { // 폰 — 작은 창
    const overlay = document.createElement("div");
    overlay.className = "mail-overlay sc-ov";
    overlay.innerHTML = `<div class="mail-box sc-ov-box" role="dialog" aria-modal="true">${visitCard(v)}<div class="mail-foot"><button type="button" class="o-close">닫기</button></div></div>`;
    // 본문 안에 붙임 — 입력칸·단추·전화/지도 단추가 PC 그날 칸과 같은 그룹웨어 스타일(.main …)을 받게(10/20 사용자 "투박해" — body에 붙여 기본 모양이었음)
    (document.querySelector("main.main") || document.body).appendChild(overlay);
    overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) overlay.remove(); });
    overlay.querySelector(".o-close").addEventListener("click", () => overlay.remove());
    wireCards(overlay);
  }
  function renderList(view) {
    const list = document.getElementById("sc-list");
    const from = ymd(view.currentStart), to = ymd(view.currentEnd);
    const byDay = {};
    for (const v of data.visits) for (let d = v.date; d <= endOf(v); d = addDay(d, 1)) if (d >= from && d < to) (byDay[d] ||= []).push(v); // 여러 날 일정은 날마다
    const days = Object.keys(byDay).sort();
    list.innerHTML = days.length ? days.map((d) => {
      const dt = new Date(`${d}T00:00:00`);
      const h = holidays[d];
      return `<div class="dk-lday${d === ymd(new Date()) ? " today" : ""}"><div class="dk-ldate${h || dt.getDay() === 0 ? " red" : ""}">${dt.getMonth() + 1}/${dt.getDate()} (${WEEK[dt.getDay()]})${h ? ` · ${esc(h.name)}` : ""}</div>
        ${byDay[d].map((v) => `<button type="button" class="dk-ev sc-ev ${vClass(v).join(" ")}" data-id="${v.id}">${esc(vTitle(v))} · ${esc(v.kind)}</button>`).join("")}</div>`;
    }).join("") : '<div class="empty-note">이 달엔 점검 일정이 없습니다.</div>';
    list.querySelectorAll(".sc-ev").forEach((b) => b.addEventListener("click", () => openVisit(data.visits.find((x) => String(x.id) === b.dataset.id))));
  }
  function selectDay(date) {
    selected = date;
    document.querySelectorAll("#sc-cal .fc-daygrid-day").forEach((cell) => cell.classList.toggle("dk-selected", cell.getAttribute("data-date") === selected));
    renderDay();
    if (isPhone()) document.getElementById("sc-day").scrollIntoView({ behavior: "smooth", block: "start" }); // 폰은 달력 아래 그날 칸으로(산안법 달력처럼, 10/23)
  }

  async function moveVisit(v, date, revert) {
    if (date === v.date) return;
    const add = v.facility.buildings;
    if (loadOf(date) + add > data.day_cap && !confirm(`${date} 그날 건물이 ${loadOf(date) + add}개가 됩니다(하루 ${data.day_cap}개). 그래도 옮길까요?`)) { if (revert) revert(); return; }
    try {
      await api(`/sitok/calendar/visits/${v.id}`, { method: "PATCH", body: JSON.stringify({ plan_date: date }) });
      document.querySelector(".mail-overlay.sc-ov")?.remove();
      selected = date;
      reload();
    } catch (err) {
      if (revert) revert();
      showError(errorEl, err);
    }
  }

  async function setEnd(v, end, revert) { // 끝 날(범위) — 시작과 같으면 하루
    if (end === endOf(v)) return;
    if (end < v.date) { alert("끝 날이 시작 날보다 앞입니다."); if (revert) revert(); else renderDay(); return; }
    try {
      await api(`/sitok/calendar/visits/${v.id}`, { method: "PATCH", body: JSON.stringify({ plan_end: end }) });
      document.querySelector(".mail-overlay.sc-ov")?.remove();
      reload();
    } catch (err) {
      if (revert) revert();
      showError(errorEl, err);
    }
  }

  async function fetchRange(start, end) {
    data = await api(`/sitok/calendar?start=${ymd(start)}&end=${ymd(end)}`);
  }
  const reload = () => cal.refetchEvents(); // events 콜백이 다시 받아 옴

  const cal = new FullCalendar.Calendar(document.getElementById("sc-cal"), {
    initialView: "dayGridMonth",
    locale: "ko",
    height: "auto",
    fixedWeekCount: false,
    headerToolbar: { left: "title", center: "", right: "prev,next today" },
    buttonText: { today: "오늘" },
    dayMaxEvents: false,
    eventOrder: "title",
    dayCellContent: (arg) => (isPhone() ? arg.dayNumberText.replace("일", "") : arg.dayNumberText),
    events: async (info, success, failure) => {
      try {
        await Promise.all([fetchRange(info.start, info.end), loadHolidays(info.start, info.end)]);
        success(events());
      } catch (err) {
        showError(errorEl, err);
        failure(err);
      }
    },
    eventDidMount: (info) => {
      const v = info.event.extendedProps.v;
      info.el.title = `${v.facility.mgmt_no} ${v.facility.name} · ${v.kind} · ${v.year} ${v.half}${v.facility.region ? ` · ${v.facility.region}` : ""}${v.pinned ? " · 📌" : ""}`;
    },
    eventsSet: () => { decorateCells(); renderList(cal.view); renderDay(); renderNotice(); },
    datesSet: () => decorateCells(),
    dateClick: (info) => selectDay(info.dateStr),
    eventClick: (info) => selectDay(ymd(info.event.start)), // 폰도 그날 상세로(10/23 — 예전엔 작은 창)
    eventDrop: (info) => moveVisit(info.event.extendedProps.v, ymd(info.event.start), info.revert),
    eventResize: (info) => setEnd(info.event.extendedProps.v, addDay(ymd(info.event.end), -1), info.revert), // 막대 끝 끌기 = 끝 날
  });
  cal.render();
})();
