// 그룹웨어 홈 통합 달력(2026-10-31 민재형 "홈화면을 패드처럼 — 바로가기 + 대형 달력, 산안/시특 현장·서류 일정 통합, 사람마다 골라서").
// 그룹웨어 home.html이 <div id="home-cal" data-user="이름"></div>와 이 파일(/report/js/home-cal.js)·css/home-cal.css를 불러온다.
// 네 달력의 일정을 **읽어서 보여주기만** 한다(저장·수정은 원래 달력에서) — 데이터를 옮기거나 합치지 않음:
//   시특법 현장 = GET /sitok/calendar (방문 일정 범위) · 산안법 현장 = GET /calendar (예정 plans + 다녀온 visits, day_total = 그날 회사 현장 수)
//   산안법 서류 = GET /contracts (dates.start·done 착수계·완수계) · 시특법 서류 = GET /sitok/docs/contracts (관급 start_date·end_date)
// 어떤 일정을 볼지는 사람마다(브라우저 localStorage, 키에 이름). 날짜 칸의 "산안 N" = 그날 산안법 현장 수(시특법 날을 정할 때 적은 날 보려고, 현장 칸이 하나라도 켜졌을 때만).
// 일정을 누르면 그 원래 달력의 그 날짜로(?date=).
(function () {
  const root = document.getElementById("home-cal");
  if (!root) return;
  const API = "/report/api";
  const PAGE = "/report/";
  const LAYERS = [
    { key: "sitok", name: "시특법 현장", page: "sitok-calendar.html" },
    { key: "sanan", name: "산안법 현장", page: "calendar.html" },
    { key: "dsitok", name: "시특법 서류", page: "sitok-docs-calendar.html" },
    { key: "dsanan", name: "산안법 서류", page: "docs-calendar.html" },
  ];
  const WEEK = ["일", "월", "화", "수", "목", "금", "토"];
  const user = root.dataset.user || "";
  const KEY = `kfsc-home-cal:${user}`;
  const pad = (n) => String(n).padStart(2, "0");
  const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const addDay = (s, n) => { const d = new Date(`${s}T00:00:00`); d.setDate(d.getDate() + n); return ymd(d); };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const phone = () => matchMedia("(max-width: 760px)").matches;

  let on = new Set(LAYERS.map((l) => l.key));
  try { const saved = JSON.parse(localStorage.getItem(KEY) || "null"); if (Array.isArray(saved)) on = new Set(saved.filter((k) => LAYERS.some((l) => l.key === k))); } catch (_) { /* 저장 못 읽으면 전부 */ }
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify([...on])); } catch (_) { /* 저장 못 해도 이번엔 동작 */ } };

  let month = new Date(); month.setDate(1);
  let data = { events: {}, sananTotal: {}, sananCap: 0, failed: new Set() };
  let holidays = {};
  const expanded = new Set(); // "더 보기"를 누른 날
  let seq = 0;

  const gridRange = () => {
    const first = new Date(month.getFullYear(), month.getMonth(), 1);
    const start = new Date(first); start.setDate(1 - first.getDay());
    const last = new Date(month.getFullYear(), month.getMonth() + 1, 0);
    const end = new Date(last); end.setDate(last.getDate() + (6 - last.getDay()) + 1); // 끝 다음날(제외)
    return [start, end];
  };

  const get = async (path) => {
    const r = await fetch(API + path, { credentials: "include" });
    if (!r.ok) throw new Error(String(r.status));
    return r.json();
  };

  async function loadHolidays(start, end) {
    const years = [...new Set([start.getFullYear(), new Date(end.getTime() - 86400000).getFullYear()])];
    await Promise.all(years.map(async (y) => {
      if (holidays[`_${y}`]) return;
      holidays[`_${y}`] = true;
      try {
        const res = await fetch(`/api/holidays?year=${y}`, { credentials: "include", redirect: "manual" });
        if (!res.ok) return;
        for (const h of await res.json()) holidays[h.date] = h.name;
      } catch (_) { /* 공휴일 못 받으면 주말 색만 */ }
    }));
  }

  const add = (ev, date, e) => { (ev[date] ||= []).push(e); };

  async function load() {
    const my = ++seq;
    const [start, end] = gridRange();
    const s = ymd(start), e = ymd(end);
    const ev = {};
    const failed = new Set();
    let sananTotal = {}, sananCap = 0;
    const tasks = [
      get(`/sitok/calendar?start=${s}&end=${e}`).then((d) => {
        for (const v of d.visits || []) {
          const last = v.end || v.date;
          for (let day = v.date; day <= last && day < e; day = addDay(day, 1)) {
            if (day < s) continue;
            const f = v.facility || {};
            add(ev, day, { layer: "sitok", text: `${v.state === "done" || v.state === "field" ? "✓ " : ""}${f.mgmt_no || ""} ${f.name || ""}`.trim(), date: v.date });
          }
        }
      }).catch(() => failed.add("sitok")),
      get(`/calendar?start=${s}&end=${e}`).then((d) => {
        sananTotal = d.day_total || {}; sananCap = d.day_cap || 0;
        const short = (n) => String(n || "").replace(/^[\w-]+\)_/, "");
        for (const p of d.plans || []) add(ev, p.date, { layer: "sanan", text: `${p.state === "missed" ? "지난 예정 " : p.source === "manual" ? "📌" : ""}${short(p.site_name)}`, date: p.date });
        for (const v of d.visits || []) add(ev, v.date, { layer: "sanan", text: `${v.state === "submitted" ? "✓ " : ""}${short(v.site_name)}`, date: v.date });
      }).catch(() => failed.add("sanan")),
      get("/contracts").then((d) => {
        for (const c of d.contracts || []) {
          for (const [k, name] of [["start", "착수계"], ["done", "완수계"]]) {
            const day = c.dates && c.dates[k];
            if (!day || day < s || day >= e) continue;
            const ok = c.made && c.made[k] && c.made[k].submitted;
            add(ev, day, { layer: "dsanan", text: `${ok ? "✓ " : ""}${name} · ${c.label || c.title || ""}`, date: day });
          }
        }
      }).catch(() => failed.add("dsanan")),
      get("/sitok/docs/contracts").then((d) => {
        for (const c of (d.contracts || []).filter((x) => x.sector === "관급")) {
          for (const [k, name, day] of [["start", "착수계", c.start_date], ["done", "완수계", c.end_date]]) {
            if (!day || day < s || day >= e) continue;
            const g = c.gov && c.gov[k];
            add(ev, day, { layer: "dsitok", text: `${g && g.pdf ? "✓ " : ""}${name} · ${c.title || c.client || ""}`, date: day });
          }
        }
      }).catch(() => failed.add("dsitok")),
      loadHolidays(start, end),
    ];
    await Promise.all(tasks);
    if (my !== seq) return; // 그 사이 달을 또 옮김
    data = { events: ev, sananTotal, sananCap, failed };
    render();
  }

  const level = (n) => (!n ? "" : data.sananCap && n / data.sananCap < 0.35 ? "lo" : data.sananCap && n / data.sananCap < 0.7 ? "mid" : "hi");

  function render() {
    const [start, end] = gridRange();
    const today = ymd(new Date());
    const showSan = on.has("sanan") || on.has("sitok");
    const counts = {};
    for (const day of Object.keys(data.events)) for (const e of data.events[day]) counts[e.layer] = (counts[e.layer] || 0) + 1;
    const max = phone() ? 2 : 3;
    let cells = "";
    for (let d = new Date(start); d < end; d.setDate(d.getDate() + 1)) {
      const day = ymd(d);
      const other = d.getMonth() !== month.getMonth();
      const evs = (data.events[day] || []).filter((e) => on.has(e.layer));
      const open = expanded.has(day);
      const shown = open ? evs : evs.slice(0, max);
      const sn = showSan ? (data.sananTotal[day] || 0) : 0;
      const hol = holidays[day];
      cells += `<div class="hc-day${other ? " dim" : ""}${day === today ? " today" : ""}${hol || d.getDay() === 0 ? " red" : d.getDay() === 6 ? " blue" : ""}${sn ? ` san-${level(sn)}` : ""}" title="${esc(hol || "")}">
        <div class="hc-top"><span class="hc-n">${d.getDate()}</span>${hol && !phone() ? `<span class="hc-hol">${esc(hol)}</span>` : ""}${sn ? `<span class="hc-san ${level(sn)}" title="그날 산안법 현장 ${sn}곳 — 시특법은 적은 날에">산안 ${sn}</span>` : ""}</div>
        ${shown.map((e) => `<a class="hc-ev e-${e.layer}" href="${PAGE}${LAYERS.find((l) => l.key === e.layer).page}?date=${e.date}" title="${esc(e.text)}">${esc(e.text)}</a>`).join("")}
        ${evs.length > shown.length ? `<button type="button" class="hc-more" data-day="${day}">+${evs.length - shown.length}건</button>` : open && evs.length > max ? `<button type="button" class="hc-more" data-day="${day}">접기</button>` : ""}
      </div>`;
    }
    root.innerHTML = `<div class="hc-head"><h2>${month.getFullYear()}년 ${month.getMonth() + 1}월</h2>
        <div class="hc-nav"><button type="button" data-nav="-1" aria-label="이전 달">◀</button><button type="button" data-nav="0" class="hc-today">오늘</button><button type="button" data-nav="1" aria-label="다음 달">▶</button></div>
        <div class="hc-chips" role="group" aria-label="보일 일정">${LAYERS.map((l) => `<button type="button" class="hc-chip c-${l.key}${on.has(l.key) ? "" : " off"}" data-layer="${l.key}" aria-pressed="${on.has(l.key)}" title="${data.failed.has(l.key) ? "불러오지 못했습니다" : "누르면 켜고 끕니다 — 내 화면에만 저장"}"><i></i>${l.name}${counts[l.key] ? ` <small>${counts[l.key]}</small>` : ""}${data.failed.has(l.key) ? " ⚠" : ""}</button>`).join("")}</div></div>
      <div class="hc-grid">${WEEK.map((w, i) => `<div class="hc-dow${i === 0 ? " red" : i === 6 ? " blue" : ""}">${w}</div>`).join("")}${cells}</div>
      <div class="hc-foot">일정을 누르면 그 달력의 그 날짜로 갑니다 · 보기만 하는 화면(일정 입력·수정은 각 달력에서)${showSan ? " · 초록 \"산안 N\" = 그날 산안법 현장 수" : ""}</div>`;
    root.querySelectorAll("[data-nav]").forEach((b) => b.addEventListener("click", () => {
      const n = Number(b.dataset.nav);
      if (n === 0) { month = new Date(); month.setDate(1); } else month = new Date(month.getFullYear(), month.getMonth() + n, 1);
      expanded.clear();
      load();
    }));
    root.querySelectorAll("[data-layer]").forEach((b) => b.addEventListener("click", () => {
      const k = b.dataset.layer;
      if (on.has(k)) on.delete(k); else on.add(k);
      save();
      render();
    }));
    root.querySelectorAll(".hc-more").forEach((b) => b.addEventListener("click", () => {
      const day = b.dataset.day;
      if (expanded.has(day)) expanded.delete(day); else expanded.add(day);
      render();
    }));
  }

  root.innerHTML = '<div class="hc-loading">달력을 불러오는 중…</div>';
  load();
})();
