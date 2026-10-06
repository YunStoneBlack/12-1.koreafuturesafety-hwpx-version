// ---------- 서류 자동화 — 착수·완수 일정 달력(docs-calendar.html, 2026-10-06) ----------
// 계약마다 착수일·완수일에 한 칸씩(파랑 = 착수계, 보라 = 완수계 — 기한이 아니라 계약 날짜, 사용자 10/6). 제출했으면 ✓. 누르면 그 창.
// 달력 모양·공휴일은 방문 달력(js/calendar.js)과 같게 — FullCalendar 6.1.15 + 그룹웨어 app.css `.fc` 규칙 + 그룹웨어 /api/holidays(사용자 10/6).
// 폰은 칸이 좁아 색 막대만 보이므로 달력 아래에 그 달 날짜별 목록을 같이 보여 준다(css/docs.css). 날짜는 서버 contract_status.plan_dates.

(function () {
  const errorEl = document.getElementById("error");
  const WEEK = ["일", "월", "화", "수", "목", "금", "토"];
  const isPhone = () => matchMedia("(max-width: 760px)").matches;
  const pad = (n) => String(n).padStart(2, "0");
  const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  let contracts = null;
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
      } catch (_) { /* 그룹웨어 공휴일을 못 받으면 주말 색만 */ }
    }));
  }

  function events() {
    const out = [];
    for (const c of contracts || []) {
      for (const [k, label] of DC_KINDS) {
        const day = c.dates[k];
        if (!day) continue;
        const s = dcDocState(c, k);
        out.push({
          title: `${s.cls === "ok" ? "✓ " : ""}${label} · ${c.title || "(용역명 없음)"}`,
          start: day, allDay: true, classNames: [`dk-${k}`, s.cls === "ok" ? "dk-ok" : "dk-wait"],
          extendedProps: { id: c.id, kind: k, text: `${label} · ${c.title} — ${s.text}` },
        });
      }
    }
    return out;
  }

  // 공휴일 칠하기 — FullCalendar가 칸을 다시 그릴 때마다(달 이동·일정 갱신). 방문 달력 decorateCells와 같은 방식
  function decorateCells() {
    document.querySelectorAll("#dk-cal .fc-daygrid-day").forEach((cell) => {
      const date = cell.getAttribute("data-date");
      const holiday = !cell.classList.contains("fc-day-other") ? holidays[date] : null;
      cell.classList.toggle("holiday", !!holiday);
      cell.title = holiday ? holiday.name : "";
      const top = cell.querySelector(".fc-daygrid-day-top");
      if (!top) return;
      top.querySelectorAll(".holiday-label").forEach((el) => el.remove());
      if (holiday && holiday.label) {
        const lab = document.createElement("div");
        lab.className = "holiday-label";
        lab.textContent = holiday.name;
        top.appendChild(lab);
      }
    });
  }

  // 폰: 달력 아래 그 달 날짜별 목록(누르면 그 창)
  function renderList(view) {
    const list = document.getElementById("dk-list");
    const from = ymd(view.currentStart), to = ymd(view.currentEnd);
    const byDay = {};
    for (const e of events()) if (e.start >= from && e.start < to) (byDay[e.start] ||= []).push(e);
    const days = Object.keys(byDay).sort();
    list.innerHTML = days.length ? days.map((d) => {
      const dt = new Date(`${d}T00:00:00`);
      const h = holidays[d];
      return `<div class="dk-lday${d === ymd(new Date()) ? " today" : ""}"><div class="dk-ldate${h || dt.getDay() === 0 ? " red" : ""}">${dt.getMonth() + 1}/${dt.getDate()} (${WEEK[dt.getDay()]})${h ? ` · ${mailEsc(h.name)}` : ""}</div>
        ${byDay[d].map((e) => `<button type="button" class="dk-ev ${e.classNames.join(" ")}" data-id="${e.extendedProps.id}" data-kind="${e.extendedProps.kind}">${mailEsc(e.title)}</button>`).join("")}</div>`;
    }).join("") : '<div class="empty-note">이 달엔 착수일·완수일인 계약이 없습니다.</div>';
    list.querySelectorAll(".dk-ev").forEach((b) => b.addEventListener("click", () => openContractDocs(Number(b.dataset.id), b.dataset.kind, reload)));
  }

  async function reload() {
    try {
      contracts = (await dcLoad()).contracts;
      cal.refetchEvents();
    } catch (err) {
      showError(errorEl, err);
    }
  }

  const cal = new FullCalendar.Calendar(document.getElementById("dk-cal"), {
    initialView: "dayGridMonth",
    locale: "ko",
    height: "auto",
    fixedWeekCount: false,
    headerToolbar: { left: "title", center: "", right: "prev,next today" },
    buttonText: { today: "오늘" },
    dayMaxEvents: false,
    dayCellContent: (arg) => (isPhone() ? arg.dayNumberText.replace("일", "") : arg.dayNumberText),
    eventOrder: (a, b) => (a.extendedProps.kind === b.extendedProps.kind ? 0 : a.extendedProps.kind === "start" ? -1 : 1),
    events: async (info, success, failure) => {
      try {
        const [d] = await Promise.all([contracts ? null : dcLoad(), loadHolidays(info.start, info.end)]);
        if (d) contracts = d.contracts;
        success(events());
      } catch (err) {
        showError(errorEl, err);
        failure(err);
      }
    },
    eventDidMount: (info) => { info.el.title = info.event.extendedProps.text; },
    eventsSet: () => { decorateCells(); renderList(cal.view); },
    datesSet: () => decorateCells(),
    eventClick: (info) => openContractDocs(info.event.extendedProps.id, info.event.extendedProps.kind, reload),
  });
  cal.render();
})();
