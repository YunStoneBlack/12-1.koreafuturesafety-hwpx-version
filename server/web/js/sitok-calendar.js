// 보고서 자동화 · 시특법 — 방문 달력(sitok-calendar.html, 2026-10-15 민재형 문서번호 일치화 문서 "보고서 달력관리").
// 시설물 카드(묶인 동은 하나)마다 반기 하루씩 — 자동 배치 규칙은 server/sitok/visit_plan.py(같은 시·군 같은 날, 하루 건물 4개, 관급 착수일 1주일 안).
// PC: 칸을 끌어 다른 날로(📌 사람이 정한 날 — 자동 배치가 안 건드림, 그날 4개 넘으면 물어봄), 날짜 누르면 오른쪽 그날 상세(날 바꾸기·지우기·이 날 일정 넣기).
// 폰: 산안법 달력처럼 달력 아래 고른 날(처음 오늘) 출장만, 날짜·막대를 누르면 그날로(10/23 사용자 — 예전엔 그달 날짜별 목록 + 작은 창).
// 위 알림 = 계약기간 안인데 일정이 없는 반기 N곳 → [자동으로 잡기](미리보기 → 잡기).
// 색: 정기 파랑·정밀 보라, ✓ = 그 반기 보고서 만듦(흐리게), 빨간 점선 = 지난 날인데 보고서 없음. API server/api/routers/sitok_calendar.py.
// 🔍 찾기(10/30 사용자 "용역명·번호 검색 시 언제인지") — GET /sitok/calendar/search, 날짜 상관없이 시설물 카드마다 점검 날 전부, 누르면 그 달·그 날로(막대 깜빡임).

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
  let preFacility = null; // 일정 없는 반기 알림에서 누른 시설물 — [이 날 일정 넣기]에 골라 둠(10/23)
  let flashId = null; // 찾기에서 고른 일정 — 그 막대를 잠깐 깜빡임(10/30)
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
    const list = data.missing_list || [];
    const md = (s) => { const x = new Date(`${s}T00:00:00`); return `${x.getMonth() + 1}/${x.getDate()}`; };
    el.innerHTML = `<span>📅 <b>일정 없는 반기 ${data.missing}개</b>(시설물 ${data.missing_units}곳) — 계약기간 안인데 점검 날이 안 잡혀 있습니다</span>
      <button type="button" class="btn-sm" id="sc-fill">자동으로 잡기</button>
      <div class="sc-miss-list">${list.map((n, i) => `<button type="button" class="sc-miss" data-i="${i}" title="누르면 그 기간 첫날로 — [이 날 일정 넣기]에 이 시설물을 골라 둡니다">
        <span class="site-no">${esc(n.facility.mgmt_no)}</span> <b>${esc(n.facility.name)}</b>${n.facility.buildings > 1 ? ` <small>(${n.facility.buildings}동)</small>` : ""}
        <span class="sc-k ${n.kind === "정밀" ? "pre" : ""}">${esc(n.kind)}</span> <small>${n.year} ${esc(n.half)} · ${md(n.start)}~${md(n.end)}${n.why ? ` · ${esc(n.why)}` : ""}</small></button>`).join("")}
        ${data.missing > list.length ? `<span class="mail-note">외 ${data.missing - list.length}개 — [자동으로 잡기]에서 전부</span>` : ""}</div>`; // 어떤 건지 바로(10/23)
    document.getElementById("sc-fill").addEventListener("click", openFill);
    el.querySelectorAll(".sc-miss").forEach((b) => b.addEventListener("click", () => { // 그 기간 첫날로 + [이 날 일정 넣기]에 그 시설물
      const n = list[Number(b.dataset.i)];
      const today = ymd(new Date());
      let day = n.start > today ? n.start : (n.end >= today ? addDay(today, 1) : n.start);
      const off = (d) => [0, 6].includes(new Date(`${d}T00:00:00`).getDay()) || holidays[d] || d.endsWith("-01-01"); // 주말·공휴일이면 다음 평일(기간 안에서)
      for (let k = 0; k < 10 && off(day) && addDay(day, 1) <= n.end; k++) day = addDay(day, 1);
      preFacility = n.facility.id;
      cal.gotoDate(day);
      selectDay(day);
    }));
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

  // 그날 상세 카드(PC 오른쪽 · 폰 달력 아래 — 10/23부터 둘 다 같은 칸)
  const STATE = { done: "✓ 그 반기 보고서 만듦", field: "✓ 현장점검 완료 — 보고서는 아직", missed: "⚠ 지난 날 — 현장점검 완료 안 됨", planned: "예정" }; // field = 현장 조사 [✓ 조사 완료]·제출 현황 [현장점검](10/18)
  function visitCard(v) {
    const f = v.facility;
    const link = v.report_id ? `sitok-round.html?report=${v.report_id}` : `sitok-facility.html?id=${f.id}`;
    return `<div class="dk-item sc-item ${vClass(v).join(" ")}" data-id="${v.id}">
      <div class="dk-item-kind">${esc(v.kind)} · ${v.year} ${esc(v.half)}${v.pinned ? " · 📌 사람이 정함" : " · 자동"}</div>
      <b><span class="site-no">${esc(f.mgmt_no)}</span> <a href="${link}">${esc(f.name)}</a>${f.buildings > 1 ? ` <small>(${f.buildings}동)</small>` : ""}</b>
      <small>${esc([f.region, f.address].filter(Boolean).join(" · "))}</small>
      ${(f.members || []).length > 1 ? `<details class="sc-members"><summary>📍 시설물 ${f.members.length}곳 위치</summary><ol>${f.members.map((m) => `<li data-addr="${esc(m.address)}" data-fid="${m.id}">
        <b>${esc(m.name)}</b><small>${esc(m.address || "주소 없음")}</small>${ledgerNote(m)}<span class="sc-m-map"></span><div class="sc-addr" hidden></div></li>`).join("")}</ol></details>` : ""}
      <div class="dk-item-state${v.state === "done" || v.state === "field" ? " ok" : ""}">${STATE[v.state] || ""}</div>
      ${v.memo ? `<small>메모: ${esc(v.memo)}</small>` : ""}
      <div class="sc-links"></div><div class="sc-contact" hidden></div>${(f.members || []).length > 1 ? "" : `${ledgerNote(f)}<div class="sc-addr" hidden></div>`}
      <div class="dk-item-act sc-act"><span class="sc-range"><input type="date" class="sc-move" value="${v.date}" aria-label="시작 날" /><span class="sc-tilde">~</span>
        <input type="date" class="sc-end" value="${endOf(v)}" min="${v.date}" aria-label="끝 날" /></span><button type="button" class="secondary sc-del">지우기</button></div>
    </div>`;
  }
  function wireCards(root) {
    root.querySelectorAll(".sc-item").forEach((card) => {
      const v = data.visits.find((x) => String(x.id) === card.dataset.id);
      wireContact(card, v);
      card.querySelectorAll(".sc-members li[data-addr]").forEach((li) => { // 묶음 안 시설물마다 지도(10/23) + ✏️ 지도용 주소(10/25)
        const m = v.facility.members.find((x) => String(x.id) === li.dataset.fid);
        const b = (li.dataset.addr ? siteLinkButtons("", li.dataset.addr) : null) || Object.assign(document.createElement("div"), { className: "site-links" });
        li.querySelector(".sc-m-map").appendChild(b);
        if (m) addrEditButton(b, li.querySelector(".sc-addr"), m);
      });
      if ((v.facility.members || []).length <= 1) addrEditButton(card.querySelector(".sc-links .site-links"), card.querySelector(":scope > .sc-addr"), v.facility); // 한 곳짜리 — 카드 지도 옆
      card.querySelector(".sc-move").addEventListener("change", (e) => { if (e.target.value) moveVisit(v, e.target.value); });
      card.querySelector(".sc-end").addEventListener("change", (e) => { if (e.target.value) setEnd(v, e.target.value); });
      card.querySelector(".sc-del").addEventListener("click", async () => {
        if (!confirm(`${v.facility.mgmt_no} ${v.facility.name} ${v.date} 일정을 지울까요?${v.pinned ? "" : "\n(자동으로 잡은 날 — 지우면 다음 [자동으로 잡기] 때 다시 잡힐 수 있어요)"}`)) return;
        try { await api(`/sitok/calendar/visits/${v.id}`, { method: "DELETE" }); reload(); } catch (err) { showError(errorEl, err); }
      });
    });
  }
  // 지도용 주소(10/25 민재형 "연락처 수정처럼 위치 수정도 — 보고서에는 관리대장 주소가 맞으니 지도 바로가기에서만") — 고치면 이 달력의 📍 지도·복사·동선만 그 주소,
  // 관리대장·보고서·위치도 주소는 그대로(서버 PATCH /sitok/calendar/facilities/{id}/map-address, 시설물 ledger.map_address). 비우면 관리대장 주소로.
  function ledgerNote(m) {
    return m.ledger_address && m.address !== m.ledger_address ? `<small class="sc-led">✏️ 지도용 주소 — 관리대장·보고서: ${esc(m.ledger_address)}</small>` : "";
  }
  function addrEditButton(links, form, m) {
    if (!links || !form) return;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "site-link sc-edit";
    btn.title = "지도용 주소 고치기 — 이 달력의 지도·복사·동선만, 관리대장·보고서 주소는 그대로";
    btn.innerHTML = '<span class="sl-ico">✏️</span>';
    links.appendChild(btn);
    btn.addEventListener("click", (e) => {
      e.preventDefault(); e.stopPropagation();
      form.hidden = !form.hidden;
      if (form.hidden) return;
      form.innerHTML = `<div class="sc-c-head">지도용 주소 <small>— 지도 바로가기·복사·동선만, 관리대장·보고서 주소(${esc(m.ledger_address || "없음")})는 그대로</small></div>
        <input type="text" class="sc-a-in" placeholder="찾아갈 주소(예: 도로명 주소·지번)" value="${esc(m.address)}" />
        <div class="sc-c-act">${m.address !== m.ledger_address ? '<button type="button" class="secondary sc-a-reset">관리대장 주소로</button>' : ""}
          <button type="button" class="secondary sc-a-cancel">취소</button><button type="button" class="btn-sm sc-a-save">저장</button></div>`;
      const inp = form.querySelector(".sc-a-in");
      inp.focus();
      const save = async (address) => {
        try { await apiPatch(`/sitok/calendar/facilities/${m.id}/map-address`, { address }); reload(); } catch (err) { alert(err.message); }
      };
      form.querySelector(".sc-a-cancel").addEventListener("click", () => { form.hidden = true; });
      form.querySelector(".sc-a-save").addEventListener("click", () => save(inp.value.trim()));
      form.querySelector(".sc-a-reset")?.addEventListener("click", () => save(""));
      inp.addEventListener("keydown", (ev) => { if (ev.key === "Enter" && !ev.isComposing) { ev.preventDefault(); save(inp.value.trim()); } });
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
        try { await apiPatch(`/sitok/calendar/visits/${v.id}/site-contact`, { phone, manager }); reload(); }
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
    const spots = new Set(items.flatMap((v) => (v.facility.members || [v.facility]).map((m) => String(m.address || v.facility.address || "").replace(/\s+/g, "")))).size; // 그날 서로 다른 주소 수(묶음은 안 시설물 전부, 같은 번지는 한 곳)
    body.innerHTML = `<h3 class="dk-day-title${h || dt.getDay() === 0 ? " red" : ""}">${dt.getMonth() + 1}월 ${dt.getDate()}일 (${WEEK[dt.getDay()]})${h ? ` · ${esc(h.name)}` : ""}
        ${n ? `<span class="sc-load${n > data.day_cap ? " over" : ""}">${n}</span>` : ""}</h3>
      ${spots >= 2 ? `<div class="sc-day-tools"><button type="button" class="secondary btn-sm sc-route" title="출발지 → 그날 시설물들 → 복귀지, 가장 짧은 순서(산안법 동선 짜기와 같음)">🚗 동선 짜기 (${spots}곳)</button></div>` : ""}
      ${items.length ? items.map(visitCard).join("") : '<div class="empty-note">이 날은 점검 일정이 없습니다.</div>'}
      <div class="sc-add"><select class="sc-add-f" aria-label="시설물"><option value="">+ 이 날 일정 넣기 — 시설물 고르기</option>
        ${data.facilities.slice().sort((a, b) => String(a.mgmt_no).localeCompare(String(b.mgmt_no), "ko", { numeric: true })).map((f) => `<option value="${f.id}">${esc(f.mgmt_no)} ${esc(f.name)}${f.region ? ` · ${esc(f.region)}` : ""}</option>`).join("")}</select>
        <button type="button" class="btn-sm sc-add-btn">넣기</button></div>`;
    wireCards(body);
    body.querySelector(".sc-route")?.addEventListener("click", () => openRoutePlan(selected, null, "시특법 점검", { url: "/sitok/calendar/route", body: {} })); // 동선(10/23)
    if (preFacility) { // 알림에서 누른 시설물을 골라 두고 눈에 띄게(10/23)
      const sel = body.querySelector(".sc-add-f");
      sel.value = String(preFacility);
      if (sel.value) { sel.classList.add("sc-pre"); sel.closest(".sc-add").scrollIntoView({ block: "nearest" }); }
    }
    body.querySelector(".sc-add-btn").addEventListener("click", async () => {
      const fid = Number(body.querySelector(".sc-add-f").value);
      if (!fid) return;
      const f = data.facilities.find((x) => x.id === fid);
      if (loadOf(selected) + (f ? f.buildings : 1) > data.day_cap && !confirm(`그날 건물이 ${data.day_cap}개를 넘습니다. 그래도 넣을까요?`)) return;
      try { await apiPost("/sitok/calendar/visits", { facility_id: fid, plan_date: selected }); preFacility = null; reload(); } catch (err) { showError(errorEl, err); }
    });
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
      if (flashId && String(v.id) === flashId) info.el.classList.add("sc-flash");
      info.el.title = `${v.facility.mgmt_no} ${v.facility.name} · ${v.kind} · ${v.year} ${v.half}${v.facility.region ? ` · ${v.facility.region}` : ""}${v.pinned ? " · 📌" : ""}`;
    },
    eventsSet: () => { decorateCells(); renderDay(); renderNotice(); },
    datesSet: () => decorateCells(),
    dateClick: (info) => selectDay(info.dateStr),
    eventClick: (info) => selectDay(ymd(info.event.start)), // 폰도 그날 상세로(10/23 — 예전엔 작은 창)
    eventDrop: (info) => moveVisit(info.event.extendedProps.v, ymd(info.event.start), info.revert),
    eventResize: (info) => setEnd(info.event.extendedProps.v, addDay(ymd(info.event.end), -1), info.revert), // 막대 끝 끌기 = 끝 날
  });
  cal.render();

  // ---------- 🔍 찾기(10/30) ----------
  const qIn = document.getElementById("sc-q"), fList = document.getElementById("sc-find-list");
  const F_STATE = { done: ["✓ 보고서 만듦", "ok"], field: ["✓ 현장점검 완료", "ok"], missed: ["⚠ 지난 날 · 완료 안 됨", "bad"], planned: ["예정", ""] };
  const mdw = (s) => { const x = new Date(`${s}T00:00:00`); return `${x.getFullYear() !== new Date().getFullYear() ? `${x.getFullYear()}.` : ""}${x.getMonth() + 1}.${x.getDate()}(${WEEK[x.getDay()]})`; };
  let fTimer = null, fSeq = 0, fFirst = null;
  function goVisit(v) {
    fList.hidden = true;
    flashId = String(v.id);
    setTimeout(() => { flashId = null; }, 4000);
    cal.gotoDate(v.date);
    selectDay(v.date);
    cal.getEventById(flashId)?.setProp("classNames", [...vClass(v), "sc-flash"]); // 이미 그 달이면 여기서, 다른 달이면 다시 받아 그릴 때(eventDidMount)
    setTimeout(() => { const e = cal.getEventById(String(v.id)); if (e) e.setProp("classNames", vClass(v)); }, 3200);
  }
  function drawFind(d, q) {
    const today = ymd(new Date());
    fFirst = null;
    const units = d.units || [];
    fList.innerHTML = units.length ? units.map((u, ui) => {
      const next = u.visits.findIndex((v) => endOf(v) >= today); // 다가오는 점검(오늘 이후 첫 일정)
      if (!fFirst && u.visits.length) fFirst = u.visits[next >= 0 ? next : u.visits.length - 1];
      return `<div class="sc-f-unit"><div class="sc-f-head"><span class="site-no">${esc(u.mgmt_no)}</span><b>${esc(u.name)}</b>${u.buildings > 1 ? `<small>(${u.buildings}동)</small>` : ""}
          ${u.region ? `<small>${esc(u.region)}</small>` : ""}${u.title ? `<small>· 용역명 ${esc(u.title)}</small>` : ""}</div>
        ${u.visits.length ? u.visits.map((v, vi) => `<button type="button" class="sc-f-v" data-u="${ui}" data-v="${vi}" title="누르면 그 날로">
            <span class="sc-k ${v.kind === "정밀" ? "pre" : ""}">${esc(v.kind)}</span><span>${v.year} ${esc(v.half)}</span>
            <span class="sc-f-date">${mdw(v.date)}${endOf(v) !== v.date ? ` ~ ${mdw(endOf(v))}` : ""}</span>${v.pinned ? "📌" : ""}${vi === next ? '<span class="sc-f-next">다가오는 점검</span>' : ""}
            <span class="sc-f-st ${F_STATE[v.state]?.[1] || ""}">${F_STATE[v.state]?.[0] || ""}</span></button>`).join("")
          : `<button type="button" class="sc-f-none" data-fid="${u.id}" title="누르면 오른쪽 [이 날 일정 넣기]에 이 시설물을 골라 둡니다">일정 없음 — 날짜를 고르고 [이 날 일정 넣기]로</button>`}</div>`;
    }).join("") + (d.more ? `<div class="sc-f-empty">외 ${d.more}곳 — 더 자세히 쳐 보세요</div>` : "")
      : `<div class="sc-f-empty">"${esc(q)}" — 맞는 시설물이 없습니다(번호 관급-22·22, 시설물 이름, 서류 계약 용역명으로 찾습니다)</div>`;
    fList.hidden = false;
    fList.querySelectorAll(".sc-f-v").forEach((b) => b.addEventListener("click", () => goVisit(units[Number(b.dataset.u)].visits[Number(b.dataset.v)])));
    fList.querySelectorAll(".sc-f-none").forEach((b) => b.addEventListener("click", () => {
      fList.hidden = true;
      preFacility = Number(b.dataset.fid);
      renderDay();
    }));
  }
  async function runFind() {
    const q = qIn.value.trim();
    if (!q) { fList.hidden = true; fFirst = null; return; }
    const my = ++fSeq;
    try {
      const d = await api(`/sitok/calendar/search?q=${encodeURIComponent(q)}`);
      if (my === fSeq && qIn.value.trim() === q) drawFind(d, q); // 늦게 온 옛 응답은 버림
    } catch (err) { showError(errorEl, err); }
  }
  qIn.addEventListener("input", () => { clearTimeout(fTimer); fTimer = setTimeout(runFind, 250); });
  qIn.addEventListener("focus", () => { if (qIn.value.trim() && fList.innerHTML) fList.hidden = false; });
  qIn.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { fList.hidden = true; qIn.blur(); }
    if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); clearTimeout(fTimer); if (fFirst && !fList.hidden) goVisit(fFirst); else runFind(); } // 엔터 = 첫 시설물의 다가오는 점검
  });
  document.addEventListener("mousedown", (e) => { if (!document.getElementById("sc-find").contains(e.target)) fList.hidden = true; });
})();
