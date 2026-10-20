// ---------- 서류 자동화 · 시특법 — 관급 착수·완수 일정 달력(sitok-docs-calendar.html, 2026-10-12) ----------
// 산안법 착수·완수 일정(js/docs-calendar.js)과 같은 모양: 관급 계약마다 착수일(파랑 = 착수계)·완수일(보라 = 완수계)에 한 칸, 누르면 그 서류 창(js/sitok-docs-gov.js).
// 민간은 착수계·완수계가 없어 빠짐(사용자 10/12). 시특법은 제출 기록이 아직 없어(제출 방법 확인 전) ✓ = 그 서류 PDF를 만듦.
// 폰은 달력 아래 그 달 날짜별 목록, PC는 오른쪽 "그날 상세"(산안법과 같음 — css/docs.css .dk-*). 데이터는 GET /sitok/docs/contracts 하나.

(function () {
  const errorEl = document.getElementById("error");
  const KINDS = [["start", "착수계"], ["done", "완수계"]];
  const WEEK = ["일", "월", "화", "수", "목", "금", "토"];
  const isPhone = () => matchMedia("(max-width: 760px)").matches;
  const pad = (n) => String(n).padStart(2, "0");
  const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  let contracts = null;
  let selected = ymd(new Date());
  const holidays = {};
  const holidayYears = {};

  const load = async () => (await api("/sitok/docs/contracts")).contracts.filter((c) => c.sector === "관급");
  const label = (c) => c.title || c.client || "(용역명 없음)";
  const state = (c, k) => {
    const g = c.gov[k];
    if (g.pdf) return { ok: true, text: `✓ ${g.at.slice(5)} 만듦` };
    if (g.at) return { ok: false, text: "엑셀만 만듦(PDF 실패) — 다시 만드세요" };
    return { ok: false, text: "아직 안 만듦" };
  };

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
      for (const [k, name] of KINDS) {
        const day = k === "start" ? c.start_date : c.end_date;
        if (!day) continue;
        const s = state(c, k);
        out.push({
          title: `${s.ok ? "✓ " : ""}${name} · ${label(c)}`,
          start: day, allDay: true, classNames: [`dk-${k}`, s.ok ? "dk-ok" : "dk-wait"],
          extendedProps: { id: c.id, kind: k, text: `${name} · ${label(c)} — ${s.text}` },
        });
      }
    }
    return out;
  }

  // 공휴일 칠하기 — 산안법 달력과 같음
  function decorateCells() {
    document.querySelectorAll("#dk-cal .fc-daygrid-day").forEach((cell) => {
      const date = cell.getAttribute("data-date");
      const holiday = !cell.classList.contains("fc-day-other") ? holidays[date] : null;
      cell.classList.toggle("holiday", !!holiday);
      cell.classList.toggle("dk-selected", date === selected);
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
    }).join("") : '<div class="empty-note">이 달엔 착수일·완수일인 관급 계약이 없습니다.</div>';
    list.querySelectorAll(".dk-ev").forEach((b) => b.addEventListener("click", () => openSitokGov(Number(b.dataset.id), b.dataset.kind, reload)));
  }

  // 그날 상세(PC 오른쪽 칸)
  function renderDay() {
    const body = document.getElementById("dk-day-body");
    const dt = new Date(`${selected}T00:00:00`);
    const h = holidays[selected];
    const items = events().filter((e) => e.start === selected);
    const card = (e) => {
      const c = (contracts || []).find((x) => x.id === e.extendedProps.id);
      const k = e.extendedProps.kind;
      const s = state(c, k);
      const name = KINDS.find(([key]) => key === k)[1];
      const period = c.start_date || c.end_date ? `${c.start_date || "?"} ~ ${c.end_date || "?"}` : "";
      return `<div class="dk-item ${e.classNames.join(" ")}">
        <div class="dk-item-kind">${name} · ${k === "start" ? "착수일" : "완수일"}</div>
        <b>${mailEsc(label(c))}</b>
        ${c.client ? `<small>발주처 ${mailEsc(c.client)}${c.contract_no ? ` · 계약번호 ${mailEsc(c.contract_no)}` : ""}</small>` : ""}
        ${period ? `<small>계약기간 ${period}${c.amount ? ` · ${dcMoney(c.amount)}` : ""}</small>` : ""}
        ${c.facility ? `<small>현장 <a href="sitok-facility.html?id=${c.facility.id}">${mailEsc(c.facility.name)}</a></small>` : '<small class="dc-nosite">현장 연결 안 됨</small>'}
        <div class="dk-item-state${s.ok ? " ok" : ""}">${mailEsc(s.text)}</div>
        <div class="dk-item-act"><button type="button" class="dk-open" data-id="${c.id}" data-kind="${k}">${name} 창 열기</button></div>
      </div>`;
    };
    body.innerHTML = `<h3 class="dk-day-title${h || dt.getDay() === 0 ? " red" : ""}">${dt.getMonth() + 1}월 ${dt.getDate()}일 (${WEEK[dt.getDay()]})${h ? ` · ${mailEsc(h.name)}` : ""}</h3>` +
      (items.length ? items.map(card).join("") : '<div class="empty-note">이 날은 착수일·완수일인 관급 계약이 없습니다.</div>');
    body.querySelectorAll(".dk-open").forEach((b) => b.addEventListener("click", () => openSitokGov(Number(b.dataset.id), b.dataset.kind, reload)));
  }

  function selectDay(date) {
    selected = date;
    document.querySelectorAll("#dk-cal .fc-daygrid-day").forEach((cell) => cell.classList.toggle("dk-selected", cell.getAttribute("data-date") === selected));
    renderDay();
  }

  async function reload() {
    try {
      contracts = await load();
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
        const [list] = await Promise.all([contracts ? null : load(), loadHolidays(info.start, info.end)]);
        if (list) contracts = list;
        success(events());
      } catch (err) {
        showError(errorEl, err);
        failure(err);
      }
    },
    eventDidMount: (info) => { info.el.title = info.event.extendedProps.text; },
    eventsSet: () => { decorateCells(); renderList(cal.view); renderDay(); },
    datesSet: () => decorateCells(),
    dateClick: (info) => selectDay(info.dateStr),
    eventClick: (info) => { selectDay(ymd(info.event.start)); openSitokGov(info.event.extendedProps.id, info.event.extendedProps.kind, reload); },
  });
  cal.render();
})();
