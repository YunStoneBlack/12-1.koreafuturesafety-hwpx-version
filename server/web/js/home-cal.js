// 그룹웨어 홈 통합 달력 + 오늘 중요 일정 띠(2026-10-31 민재형 "홈화면을 패드처럼 — 바로가기 + 대형 달력, 산안/시특 현장·서류 일정 통합, 사람마다 골라서",
// 시안 3 확정: 위·아래 남색 줄만 두고 왼쪽 메뉴 없음, 달력 위 가로로 큰 "오늘 중요 일정").
// 그룹웨어 home.html이 <div id="home-today"></div>(오늘 띠)·<div id="home-cal" data-user="이름"></div>(달력)와 이 파일(/report/js/home-cal.js)·css/home-cal.css를 불러온다.
// 네 달력의 일정을 **읽어서 보여주기만** 한다(저장·수정은 원래 달력에서) — 데이터를 옮기거나 합치지 않음:
//   시특법 현장 = GET /sitok/calendar (방문 일정 범위) · 산안법 현장 = GET /calendar (예정 plans + 다녀온 visits, day_total = 그날 회사 현장 수)
//   산안법 서류 = GET /contracts (dates.start·done 착수계·완수계) · 시특법 서류 = GET /sitok/docs/contracts (관급 start_date·end_date)
// 어떤 일정을 볼지는 사람마다(브라우저 localStorage, 키에 이름). 날짜 칸의 "산안 N" = 그날 산안법 현장 수(시특법 날을 정할 때 적은 날 보려고, 현장 칸이 하나라도 켜졌을 때만).
// **달력 하나를 더하는 법**(건축물관리점검·내진성능평가 등): ① LAYERS에 한 줄(key·name·page·color) ② LOADERS에 같은 key로 읽는 함수 한 개(그 달력의 GET API → {events:[{date,name,text,done?,tag?}], daily?}) —
// 칩·색·달력 칸·오늘 띠·폰 점/목록·클릭 이동(?date=)은 전부 자동. 그 달력 JS가 `?date=`를 받게(initialDate)만 해 두면 됨. 날짜별 개수(daily)를 주면 칸에 "산안 N·시특 N"처럼 작게 표시.
// 일정을 누르면 그 원래 달력의 그 날짜로(?date=). 폰(폭 760px 이하)은 칸에 점만 찍고 날짜를 누르면 그날 일정을 아래 목록으로.
(function () {
  const root = document.getElementById("home-cal");
  if (!root) return;
  const todayEl = document.getElementById("home-today");
  const API = "/report/api";
  const PAGE = "/report/";
  const LAYERS = [
    { key: "sitok", name: "시특법 현장", page: "sitok-calendar.html", color: "#2A7DE1" },
    { key: "sanan", name: "산안법 현장", page: "calendar.html", color: "#2E9E5B" },
    { key: "dsitok", name: "시특법 서류", page: "sitok-docs-calendar.html", color: "#6D4BD1" },
    { key: "dsanan", name: "산안법 서류", page: "docs-calendar.html", color: "#B8720F" },
  ];
  const WEEK = ["일", "월", "화", "수", "목", "금", "토"];
  const TILE_ORDER = ["sanan", "sitok", "dsanan", "dsitok"];
  const user = root.dataset.user || "";
  const KEY = `kfsc-home-cal:${user}`;
  const pad = (n) => String(n).padStart(2, "0");
  const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const addDay = (s, n) => { const d = new Date(`${s}T00:00:00`); d.setDate(d.getDate() + n); return ymd(d); };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const phone = () => matchMedia("(max-width: 760px)").matches;
  const layerOf = (k) => LAYERS.find((l) => l.key === k);
  const href = (e) => `${PAGE}${layerOf(e.layer).page}?date=${e.date}`;

  let on = new Set(LAYERS.map((l) => l.key));
  try { const saved = JSON.parse(localStorage.getItem(KEY) || "null"); if (Array.isArray(saved)) on = new Set(saved.filter((k) => LAYERS.some((l) => l.key === k))); } catch (_) { /* 저장 못 읽으면 전부 */ }
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify([...on])); } catch (_) { /* 저장 못 해도 이번엔 동작 */ } };

  let month = new Date(); month.setDate(1);
  let data = { events: {}, daily: {}, failed: new Set(), pending: new Set(), stale: false };
  let strip = null; // 오늘 띠 데이터(오늘~7일 뒤)
  let holidays = {};
  let selected = ymd(new Date()); // 눌러 본 날(폰은 늘 아래 목록, PC는 날짜를 눌러야 목록이 열림)
  let listOpen = false; // PC: 달력 아래 "그날 일정" 목록이 열려 있는지(10/31 민재형 "달력 아래로 목록이 뜨게, 그쪽으로 화면 이동")
  let scrollToList = false;
  const expanded = new Set(); // "더 보기"를 누른 날
  let seq = 0;
  let maxShown = 3; // 한 칸에 보일 일정 수 — PC는 칸 높이에 맞춰 늘림(달력이 화면 남은 높이를 채움, 10/31 민재형 "빈 공간은 달력을 늘려서")
  let fitting = false;

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

  const add = (ev, date, e) => { (ev[date] ||= []).push({ ...e, date: e.date || date }); };

  // 달력마다 하나씩: (s, e) 기간의 일정을 읽어 {events:[{date, layer, ...}], daily?:{label, counts:{날짜:개수}, cap, kind}} 로 돌려줌. 새 달력은 여기에 함수 하나만 더하면 됨.
  const LOADERS = {
    sitok: async (s, e) => {
      const d = await get(`/sitok/calendar?start=${s}&end=${e}`);
      const events = [];
      for (const v of d.visits || []) {
        const last = v.end || v.date;
        for (let day = v.date; day <= last && day < e; day = addDay(day, 1)) {
          if (day < s) continue;
          const f = v.facility || {};
          const done = v.state === "done" || v.state === "field";
          events.push({ date: day, jump: v.date, name: `${f.mgmt_no || ""} ${f.name || ""}`.trim(), text: `${done ? "✓ " : ""}${f.mgmt_no || ""} ${f.name || ""}`.trim(), done });
        }
      }
      return { events, daily: { label: "시특", counts: d.day_load || {}, cap: d.day_cap || 0, kind: "over" } }; // 하루 건물 수(한도 넘으면 빨강)
    },
    sanan: async (s, e) => {
      const d = await get(`/calendar?start=${s}&end=${e}`);
      const short = (n) => String(n || "").replace(/^[\w-]+\)_/, "");
      const events = [];
      for (const p of d.plans || []) events.push({ date: p.date, name: short(p.site_name), text: `${p.state === "missed" ? "지난 예정 " : p.source === "manual" ? "📌" : ""}${short(p.site_name)}`, missed: p.state === "missed" });
      for (const v of d.visits || []) events.push({ date: v.date, name: short(v.site_name), text: `${v.state === "submitted" ? "✓ " : ""}${short(v.site_name)}`, done: v.state === "submitted" });
      return { events, daily: { label: "산안", counts: d.day_total || {}, cap: d.day_cap || 0, kind: "level" } }; // 그날 현장 수(적을수록 연한 초록)
    },
    dsanan: async (s, e) => {
      const d = await get("/contracts");
      const events = [];
      for (const c of d.contracts || []) {
        for (const [k, name] of [["start", "착수계"], ["done", "완수계"]]) {
          const day = c.dates && c.dates[k];
          if (!day || day < s || day >= e) continue;
          const ok = !!(c.made && c.made[k] && c.made[k].submitted);
          events.push({ date: day, tag: name, name: c.label || c.title || "", text: `${ok ? "✓ " : ""}${name} · ${c.label || c.title || ""}`, done: ok });
        }
      }
      return { events };
    },
    dsitok: async (s, e) => {
      const d = await get("/sitok/docs/contracts");
      const events = [];
      for (const c of (d.contracts || []).filter((x) => x.sector === "관급")) {
        for (const [k, name, day] of [["start", "착수계", c.start_date], ["done", "완수계", c.end_date]]) {
          if (!day || day < s || day >= e) continue;
          const g = c.gov && c.gov[k];
          const ok = !!(g && g.pdf);
          events.push({ date: day, tag: name, name: c.title || c.client || "", text: `${ok ? "✓ " : ""}${name} · ${c.title || c.client || ""}`, done: ok });
        }
      }
      return { events };
    },
  };

  // 모든 달력에서 [s, e) 기간의 일정을 받아 날짜별로 모음 → {ev, daily, failed}. 한 달력이 실패해도 나머지는 그대로(칩에 ⚠).
  async function fetchEvents(s, e, onPart) {
    const ev = {};
    const daily = {};
    const failed = new Set();
    const pending = new Set(LAYERS.map((l) => l.key));
    await Promise.all(LAYERS.map((l) => LOADERS[l.key](s, e).then((res) => {
      for (const x of res.events || []) add(ev, x.date, { ...x, layer: l.key, date: x.jump || x.date });
      if (res.daily) daily[l.key] = res.daily;
    }).catch(() => failed.add(l.key)).then(() => { pending.delete(l.key); if (onPart) onPart({ ev, daily, failed, pending }); })));
    return { ev, daily, failed, pending };
  }

  // 직전에 본 데이터(같은 기간)를 브라우저에 두었다가 먼저 보여 주고 새로 받아 바꿈(10/31 민재형 "달력 불러오는 시간이 너무 길다")
  const CACHE = `kfsc-home-cal-cache:${user}`;
  const readCache = (rk) => { try { const c = JSON.parse(localStorage.getItem(`${CACHE}:${rk}`) || "null"); return c && Date.now() - c.at < 6 * 3600 * 1000 ? c : null; } catch (_) { return null; } };
  const writeCache = (rk, got) => { try { localStorage.setItem(`${CACHE}:${rk}`, JSON.stringify({ at: Date.now(), ev: got.ev, daily: got.daily })); } catch (_) { /* 저장 못 해도 동작 */ } };

  async function load() {
    const my = ++seq;
    const [start, end] = gridRange();
    const t = ymd(new Date());
    // 이번 달을 볼 때는 오늘 띠가 쓸 오늘~8일 뒤도 같은 요청에 넣어(요청을 두 번 보내지 않음), 다른 달이면 그 달 격자만
    const todayIn = ymd(start) <= t && t < ymd(end);
    const s0 = todayIn && t < ymd(start) ? t : ymd(start);
    const e0 = todayIn && addDay(t, 8) > ymd(end) ? addDay(t, 8) : ymd(end);
    const rk = `${s0}~${e0}`;
    const cached = readCache(rk);
    const holi = loadHolidays(start, end);
    const keep = (got) => { if (todayIn) { strip = { ...got, today: t }; } };
    if (cached) { // 직전 데이터를 바로 보여 주고(“새로 확인하는 중”), 다 받으면 통째로 바꿈
      data = { events: cached.ev, daily: cached.daily, failed: new Set(), pending: new Set(), stale: true };
      keep({ ev: cached.ev, daily: cached.daily, failed: new Set() }); await holi; if (my !== seq) return; render(); renderStrip();
    }
    let raf = 0;
    const part = cached ? null : (p) => { // 처음 보는 기간: 먼저 온 달력부터 그림(느린 서류 일정을 기다리지 않음)
      data = { events: p.ev, daily: p.daily, failed: p.failed, pending: p.pending, stale: false };
      keep(p);
      if (!raf) raf = requestAnimationFrame(() => { raf = 0; if (my === seq) { render(); renderStrip(); } });
    };
    const got = await fetchEvents(s0, e0, part);
    await holi;
    if (my !== seq) return; // 그 사이 달을 또 옮김
    data = { events: got.ev, daily: got.daily, failed: got.failed, pending: new Set(), stale: false };
    keep(got);
    if (!got.failed.size) writeCache(rk, got);
    render();
    renderStrip();
  }

  async function loadStrip() {
    if (strip) return; // 이번 달 요청에 이미 들어 있음
    const t = ymd(new Date());
    try {
      const got = await fetchEvents(t, addDay(t, 8));
      strip = { ...got, today: t };
    } catch (_) { strip = null; }
    renderStrip();
  }

  // 날짜별 개수 표시(layer.daily): level = 적을수록 연한 초록(산안 현장), over = 한도 넘으면 빨강(시특 건물)
  const dailyOf = (k, day) => (data.daily[k] && data.daily[k].counts[day]) || 0;
  const lvOf = (k, n) => { const d = data.daily[k]; if (!d || !n) return ""; if (d.kind === "over") return d.cap && n > d.cap ? "over" : ""; return d.cap && n / d.cap < 0.35 ? "lo" : d.cap && n / d.cap < 0.7 ? "mid" : "hi"; };
  const pillsOf = (day) => Object.keys(data.daily).map((k) => { const n = dailyOf(k, day); return n ? `<span class="hc-cnt k-${k} ${lvOf(k, n)}" title="그날 ${data.daily[k].label} ${n}${k === "sanan" ? "곳" : "개"}${data.daily[k].cap ? ` (하루 한도 ${data.daily[k].cap})` : ""}"><i>${data.daily[k].label}</i>${n}</span>` : ""; }).join("");

  // ---------- 오늘 중요 일정 띠 ----------
  function renderStrip() {
    if (!todayEl) return;
    const layers = TILE_ORDER.map(layerOf).filter((l) => on.has(l.key)); // 시안 3 순서: 산안 출장·시특 방문·산안 서류·시특 서류
    if (!strip || !layers.length) { todayEl.innerHTML = ""; todayEl.hidden = true; return; }
    todayEl.hidden = false;
    const t = strip.today, tm = addDay(t, 1);
    const d = new Date(`${t}T00:00:00`);
    const mdw = (s) => { const x = new Date(`${s}T00:00:00`); return `${x.getMonth() + 1}/${x.getDate()}`; };
    const at = (day, k) => (strip.ev[day] || []).filter((e) => e.layer === k);
    const TILE = {
      sanan: ["산안법 출장", "곳", "곳"], sitok: ["시특법 방문", "곳", "곳"], dsanan: ["산안법 서류", "건 제출", "건"], dsitok: ["시특법 서류", "건 제출", "건"],
    };
    const tiles = layers.map((l) => {
      const list = at(t, l.key);
      const [title, unit] = TILE[l.key];
      const names = list.slice(0, 2).map((e) => `<li title="${esc(e.text)}">${e.tag ? `<em>${e.tag}</em>` : ""}${esc(e.name)}${e.done ? " ✓" : ""}</li>`).join("");
      const more = list.length > 2 ? `<li class="ht-more">외 ${list.length - 2}${unit.startsWith("건") ? "건" : "곳"}</li>` : "";
      const link = list.length ? `href="${PAGE}${l.page}?date=${t}"` : "";
      return `<a class="ht-tile k-${l.key}${list.length ? "" : " empty"}" ${link} title="${l.name}"><div class="ht-t"><i style="background:${l.color}"></i>${title}${strip.failed.has(l.key) ? " ⚠" : ""}</div>
        <div class="ht-num">${list.length}<small>${list.length ? unit : unit.startsWith("건") ? "건" : "곳"}</small></div>
        <ul>${list.length ? names + more : `<li class="ht-none">${l.key.startsWith("d") ? "오늘 제출할 서류가 없습니다" : "오늘 일정이 없습니다"}</li>`}</ul></a>`;
    }).join("");
    // 내일 한 줄 + 이번 주 마감(서류 중 아직 안 낸 것, 오늘 포함 7일)
    const parts = [];
    for (const l of layers) {
      const list = at(tm, l.key);
      if (!list.length) continue;
      if (l.key === "sanan") parts.push(`산안 현장 ${list.length}곳`);
      else if (l.key === "sitok") parts.push(`시특법 방문 ${list.slice(0, 2).map((e) => e.name).join(", ")}${list.length > 2 ? ` 외 ${list.length - 2}곳` : ""}`);
      else parts.push(`${list[0].tag} 제출 ${list.slice(0, 2).map((e) => e.name).join(", ")}${list.length > 2 ? ` 외 ${list.length - 2}건` : ""}`);
    }
    let week = 0;
    for (let i = 0; i < 7; i++) for (const e of strip.ev[addDay(t, i)] || []) if ((e.layer === "dsanan" || e.layer === "dsitok") && on.has(e.layer) && !e.done) week++;
    todayEl.innerHTML = `<div class="ht-head"><b>오늘 중요 일정</b><span>${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())} (${WEEK[d.getDay()]})</span></div>
      <div class="ht-tiles ht-n${layers.length}">${tiles}</div>
      <div class="ht-tmr"><b>내일(${mdw(tm)})</b>${parts.length ? parts.map((p) => `<span>${esc(p)}</span>`).join('<span class="ht-sep">·</span>') : "<span>일정이 없습니다</span>"}
        ${week ? `<span class="ht-week" title="오늘부터 7일 안에 제출할 착수계·완수계(아직 안 낸 것)">이번 주 서류 ${week}건</span>` : ""}</div>`;
  }

  // ---------- 달력 ----------
  function render() {
    const [start, end] = gridRange();
    const today = ymd(new Date());
    const showCnt = LAYERS.some((l) => data.daily[l.key] && on.has(l.key)); // 날짜별 개수(산안 N·시특 N)는 개수를 주는 달력(현장)이 하나라도 켜졌을 때만
    const counts = {};
    for (const day of Object.keys(data.events)) for (const e of data.events[day]) counts[e.layer] = (counts[e.layer] || 0) + 1;
    const isPhone = phone();
    const max = isPhone ? 3 : maxShown;
    const weeks = Math.round((end - start) / 86400000 / 7);
    let cells = "";
    for (let d = new Date(start); d < end; d.setDate(d.getDate() + 1)) {
      const day = ymd(d);
      const other = d.getMonth() !== month.getMonth();
      const evs = (data.events[day] || []).filter((e) => on.has(e.layer));
      const open = expanded.has(day);
      const shown = open ? evs : evs.slice(0, max);
      const sn = showCnt ? dailyOf("sanan", day) : 0; // 칸 색조 = 그날 산안 현장 수(적은 날 연하게)
      const pills = showCnt ? pillsOf(day) : "";
      const hol = holidays[day];
      const cls = `hc-day${other ? " dim" : ""}${day === today ? " today" : ""}${(isPhone || listOpen) && day === selected ? " sel" : ""}${hol || d.getDay() === 0 ? " red" : d.getDay() === 6 ? " blue" : ""}${sn ? ` san-${lvOf("sanan", sn)}` : ""}`;
      if (isPhone) { // 칸이 좁아 점만 — 눌러서 아래 목록으로
        const dots = LAYERS.filter((l) => evs.some((e) => e.layer === l.key)).map((l) => `<i style="background:${l.color}"></i>`).join(""); // 일정 종류마다 점 하나(산안 현장이 많아도 다른 일정이 가려지지 않게)
        cells += `<div class="${cls}" data-pick="${day}" title="${esc(hol || "")}"><span class="hc-n">${d.getDate()}</span><div class="hc-cnts">${pills}</div><div class="hc-dots">${dots}</div></div>`;
        continue;
      }
      cells += `<div class="${cls}" data-pick="${day}" title="${esc(hol || "")}">
        <div class="hc-top"><span class="hc-n">${d.getDate()}</span>${hol ? `<span class="hc-hol">${esc(hol)}</span>` : ""}<span class="hc-cnts">${pills}</span></div>
        ${shown.map((e) => `<a class="hc-ev e-${e.layer}" href="${href(e)}" title="${esc(e.text)}">${esc(e.text)}</a>`).join("")}
        ${evs.length > shown.length ? `<button type="button" class="hc-more" data-day="${day}">+${evs.length - shown.length}건</button>` : open && evs.length > max ? `<button type="button" class="hc-more" data-day="${day}">접기</button>` : ""}
      </div>`;
    }
    let list = "";
    if (isPhone || listOpen) { // 그날 일정 목록 — 폰은 달력 아래 늘, PC는 날짜를 눌렀을 때(두 줄, 제목 옆에 총 건수)
      const sd = new Date(`${selected}T00:00:00`);
      const evs = (data.events[selected] || []).filter((e) => on.has(e.layer));
      const li = evs.map((e) => `<a class="hc-li" href="${href(e)}"><i style="background:${layerOf(e.layer).color}"></i><span>${esc(e.text)}</span><small>${layerOf(e.layer).name}</small></a>`).join("");
      list = `<div class="hc-list" id="hc-list"><h3>${sd.getMonth() + 1}월 ${sd.getDate()}일 (${WEEK[sd.getDay()]}) 일정${showCnt ? ` <span class="hc-cnts">${pillsOf(selected)}</span>` : ""}${isPhone ? "" : `<small class="hc-listnote">총 ${evs.length}건 — 누르면 그 달력의 그 날짜로 · 같은 날짜를 한 번 더 누르면 닫힘</small>`}</h3>
        ${evs.length ? `<div class="${isPhone ? "" : "hc-cols"}">${li}</div>` : '<div class="hc-none">이 날은 일정이 없습니다.</div>'}</div>`;
    }
    root.innerHTML = `<div class="hc-head"><h2>${month.getFullYear()}년 ${month.getMonth() + 1}월</h2>
        <div class="hc-nav"><button type="button" data-nav="-1" aria-label="이전 달">◀</button><button type="button" data-nav="0" class="hc-today">오늘</button><button type="button" data-nav="1" aria-label="다음 달">▶</button></div>
        <div class="hc-chips" role="group" aria-label="보일 일정">${LAYERS.map((l) => `<button type="button" class="hc-chip c-${l.key}${on.has(l.key) ? "" : " off"}" data-layer="${l.key}" aria-pressed="${on.has(l.key)}" title="${data.failed.has(l.key) ? "불러오지 못했습니다" : "누르면 켜고 끕니다 — 내 화면에만 저장"}"><i></i>${l.name}${data.pending.has(l.key) ? " <small>…</small>" : counts[l.key] ? ` <small>${counts[l.key]}</small>` : ""}${data.failed.has(l.key) ? " ⚠" : ""}</button>`).join("")}</div></div>
      <div class="hc-grid" style="--hc-weeks:${weeks}">${WEEK.map((w, i) => `<div class="hc-dow${i === 0 ? " red" : i === 6 ? " blue" : ""}">${w}</div>`).join("")}${cells}</div>${list}
      <div class="hc-foot">${!isPhone && listOpen ? '<button type="button" class="hc-up" aria-label="달력 맨 위로">▲ 달력으로</button>' : ""}${data.stale ? '<b class="hc-sync">이전에 본 내용입니다 — 새로 확인하는 중…</b> · ' : data.pending.size ? '<b class="hc-sync">불러오는 중…</b> · ' : ""}${isPhone ? "날짜를 누르면 그날 일정이 아래에 나옵니다" : "일정을 누르면 그 달력의 그 날짜로 갑니다"} · 보기만 하는 화면(일정 입력·수정은 각 달력에서)${showCnt ? " · \"산안 N\" = 그날 산안법 현장 수(적을수록 연한 초록), \"시특 N\" = 시특법 건물 수" : ""}</div>`;
    root.querySelectorAll("[data-nav]").forEach((b) => b.addEventListener("click", () => {
      const n = Number(b.dataset.nav);
      if (n === 0) { month = new Date(); month.setDate(1); selected = ymd(new Date()); } else month = new Date(month.getFullYear(), month.getMonth() + n, 1);
      expanded.clear();
      listOpen = false;
      load();
    }));
    root.querySelectorAll("[data-layer]").forEach((b) => b.addEventListener("click", () => {
      const k = b.dataset.layer;
      if (on.has(k)) on.delete(k); else on.add(k);
      save();
      render();
      renderStrip();
    }));
    root.querySelectorAll(".hc-more").forEach((b) => b.addEventListener("click", () => {
      const day = b.dataset.day;
      if (expanded.has(day)) expanded.delete(day); else expanded.add(day);
      render();
    }));
    root.querySelectorAll("[data-pick]").forEach((c) => c.addEventListener("click", (ev) => {
      if (ev.target.closest("a, button")) return; // 일정 제목·"+N건"은 자기 동작대로
      const day = c.dataset.pick;
      if (!phone()) { // PC: 날짜를 누르면 달력 아래에 그날 목록이 열리고 그쪽으로 이동, 같은 날짜를 또 누르면 닫음
        if (listOpen && selected === day) { listOpen = false; }
        else {
          if (!listOpen) { const g = root.querySelector(".hc-grid"); if (g) root.style.setProperty("--hc-grid-h", `${Math.round(g.getBoundingClientRect().height)}px`); } // 열기 전 격자 높이를 고정(달력 크기는 그대로, 아래로 늘어남 → 가운데 영역에 스크롤)
          selected = day; listOpen = true; scrollToList = true;
        }
      } else { selected = day; scrollToList = true; }
      render();
    }));
    const upBtn = root.querySelector(".hc-up");
    if (upBtn) upBtn.addEventListener("click", () => { const m = document.querySelector(".home-main"); if (m) m.scrollTo({ top: 0, behavior: "smooth" }); });
    root.classList.toggle("hc-open", !isPhone && listOpen);
    if (root.parentElement) root.parentElement.classList.toggle("hc-open", !isPhone && listOpen);
    if (scrollToList) { scrollToList = false; const l = root.querySelector("#hc-list"); if (l) requestAnimationFrame(() => l.scrollIntoView({ behavior: "smooth", block: "start" })); }
    fitCells();
    if (ro) { ro.disconnect(); const g = root.querySelector(".hc-grid"); if (g) ro.observe(g); } // 격자 크기가 바뀌면(오늘 띠가 나중에 그려져 달력이 밀리거나 창 크기가 바뀜) 다시 맞춤
  }

  // PC: 칸 높이에 맞춰 한 칸에 보일 일정 수를 정함(칸 높이는 일정 수가 아니라 남은 화면 높이로 정해지므로 다시 그려도 안정, 값이 달라질 때만 다시 그림)
  function fitCells() {
    if (phone() || fitting) return;
    const g = root.querySelector(".hc-grid"), dow = g && g.querySelector(".hc-dow");
    if (!g || !dow) return;
    const weeks = Number(getComputedStyle(g).getPropertyValue("--hc-weeks")) || 5;
    const cellH = (g.clientHeight - dow.offsetHeight) / weeks;
    const want = Math.max(3, Math.min(12, Math.floor((cellH - 46) / 22))); // 날짜 줄 20 + "+N건" 줄 16 + 여유 → 일정 한 줄 약 22px
    if (want !== maxShown) { maxShown = want; fitting = true; try { render(); } finally { fitting = false; } }
  }
  const ro = typeof ResizeObserver === "function" ? new ResizeObserver(() => requestAnimationFrame(fitCells)) : null;

  let wasPhone = phone();
  let rt = null;
  addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => { wasPhone = phone(); render(); }, 150); }); // 폭이 바뀌면(폰↔PC·창 크기) 다시 그림
  root.innerHTML = '<div class="hc-loading">달력을 불러오는 중…</div>';
  load().then(loadStrip); // 이번 달을 보는 중이면 띠 데이터는 이미 있음 — 다른 이유로 못 받았을 때만 따로
})();
