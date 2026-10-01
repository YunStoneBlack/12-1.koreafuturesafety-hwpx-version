// 출장 동선 짜기 창(2026-10-01) — 방문 달력 그날 목록의 요원 머리줄 [🚗 동선 짜기]. 출발지 → 현장들(도로 거리 최적 순서) → 복귀지.
// 서버: POST /calendar/route(server/api/routers/route_plan.py). 순서는 ☰ 손잡이로 끌거나 ▲▼로 바꾸면 거리를 다시 계산한다.
// 폰 출발 버튼 두 개(사용자 안드로이드 시험 2026-10-01, 키 없이 됨):
//   [🚗 티맵으로 출발] = tmap://route?goalx·goaly·goalname(목적지 = 복귀지)&key=티맵 공식 안내 페이지 기본값
//     &startx·starty·startname(출발지)&via1x·via1y·via1name …(경유지 = 현장들) — 티맵 공식 route.jsp가 쓰는 형식에 출발·경유지를 붙임.
//     경유지는 2곳까지만 들어감 → 현장 3곳 이상이면 구간 고르기 창(openTmapRoute).
//     시험: rV1X·rStX·origx 형식과 SK 공식 주소(appKey)는 안 됨(목적지만·출발 = 지금 위치). SK 키는 결국 필요 없었음.
//   [🗺 네이버 지도] = nmap://route/car 출발·도착·경유지 v1~v5.
// 창 틀은 css/mail.css, 이 창 규칙은 css/route-plan.css.

const RP_MAX_WAYPOINTS = 5; // 네이버 지도 앱 경유지 최대(티맵도 같은 수로 — 하루 최대 4곳)
const RP_TMAP_VIA = 2; // 티맵이 바깥 앱에서 받는 경유지 최대(SK 개발자 포럼) — 넘으면 구간 나누기
const RP_TMAP_KEY = "ACDF74F09C347613"; // 티맵 공식 안내 페이지(tmap.co.kr route.jsp)가 기본으로 넣는 값

async function openRoutePlan(date, staffId, staffName) {
  const overlay = document.createElement("div");
  overlay.className = "mail-overlay";
  overlay.innerHTML = '<div class="mail-box rp-box" role="dialog" aria-modal="true"><div class="mail-wait">동선을 계산하는 중…</div></div>';
  document.body.appendChild(overlay);
  const box = overlay.querySelector(".mail-box");
  const close = () => { overlay.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  const isPhone = !isMousePc(); // app.js
  const state = { start: "", end: "", order: null };
  let r = null;

  const load = async () => {
    try {
      r = await apiPost("/calendar/route", { date, staff_id: staffId, start: state.start || null, end: state.end || null, order: state.order });
      state.order = r.stops.map((s) => s.site_id);
      draw();
    } catch (err) {
      box.innerHTML = `<div class="mail-head"><b>🚗 출장 동선</b></div><div class="mail-msg bad">${apEsc(err.message)}</div>
        <div class="mail-foot"><button type="button" class="mail-cancel">닫기</button></div>`;
      box.querySelector(".mail-cancel").addEventListener("click", close);
    }
  };

  const placeRow = (kind, p) => `
    <div class="rp-end">
      <span class="rp-dot ${kind}">${kind === "start" ? "출" : "복"}</span>
      <div class="rp-main"><b>${kind === "start" ? "출발" : "복귀"} · ${p.is_home ? "회사" : "다른 곳"}</b><small>${apEsc(p.address)}</small>
        <div class="rp-edit" hidden><input type="text" value="${apEsc(p.address)}" placeholder="주소 입력" />
          <button type="button" class="rp-apply">적용</button>${p.is_home ? "" : '<button type="button" class="rp-home">회사로</button>'}</div></div>
      <button type="button" class="rp-change">바꾸기</button>
    </div>`;

  function draw() {
    const date_ = new Date(`${r.date}T00:00:00`);
    const head = `${date_.getMonth() + 1}월 ${date_.getDate()}일 · ${apEsc(staffName)} · ${r.stops.length}곳`;
    const legRow = (i) => `<div class="rp-leg">↓ ${r.legs[i]}km</div>`;
    const stops = r.stops.map((s, i) => `
      ${legRow(i)}
      <div class="rp-stop" data-id="${s.site_id}">
        <span class="rp-handle" title="끌어서 순서 바꾸기">☰</span>
        <span class="rp-dot">${i + 1}</span>
        <div class="rp-main"><b>${apEsc(s.name)}</b><small>${apEsc(s.address)}</small></div>
        <span class="rp-arrows"><button type="button" class="rp-up" ${i === 0 ? "disabled" : ""} aria-label="위로">▲</button>
          <button type="button" class="rp-down" ${i === r.stops.length - 1 ? "disabled" : ""} aria-label="아래로">▼</button></span>
      </div>`).join("");
    const missing = r.missing.length
      ? `<div class="ap-note">ℹ️ 주소로 위치를 못 찾아 동선에서 뺀 현장: ${r.missing.map((s) => apEsc(s.name)).join(", ")}</div>` : "";
    const compare = r.is_best
      ? '<span class="rp-best">✓ 가장 짧은 순서</span>'
      : `<span class="rp-worse">가장 짧은 순서보다 ${(r.total_km - r.best_total_km).toFixed(1)}km 더 김</span>
         <button type="button" class="rp-tobest">가장 짧은 순서로</button>`;
    const tooMany = r.stops.length > RP_MAX_WAYPOINTS;
    box.innerHTML = `
      <div class="mail-head"><b>🚗 출장 동선</b><span class="mail-sub">${head}</span></div>
      <div class="rp-total">총 <b>${r.total_km}km</b> <span class="rp-hint">(도로 거리 — 시간은 교통에 따라 달라 안 씀)</span> ${compare}</div>
      ${missing}
      <div class="rp-list">${placeRow("start", r.start)}${stops}${legRow(r.stops.length)}${placeRow("end", r.end)}</div>
      <div class="mail-foot">
        <button type="button" class="mail-cancel">닫기</button>
        ${isPhone ? `<button type="button" class="mail-primary rp-go rp-naver" ${tooMany ? "disabled" : ""}>🗺 네이버 지도</button>
          <button type="button" class="mail-primary rp-go rp-tmap" ${tooMany ? "disabled" : ""}>🚗 티맵으로 출발</button>` : ""}
      </div>
      ${isPhone ? (tooMany ? `<div class="rp-hint">내비 앱은 경유지를 ${RP_MAX_WAYPOINTS}곳까지 받습니다.</div>`
        : "")
        : '<div class="rp-hint">폰에서 열면 [🚗 티맵으로 출발]·[🗺 네이버 지도]로 이 순서 그대로 길안내가 시작됩니다(경유지 포함).</div>'}`;
    box.querySelector(".mail-cancel").addEventListener("click", close);
    box.querySelector(".rp-tobest")?.addEventListener("click", () => { state.order = r.best_order; load(); });
    box.querySelector(".rp-naver")?.addEventListener("click", () => openNaverRoute(r));
    box.querySelector(".rp-tmap")?.addEventListener("click", () => openTmapRoute(r));
    box.querySelectorAll(".rp-end").forEach((row, idx) => {
      const kind = idx === 0 ? "start" : "end";
      const edit = row.querySelector(".rp-edit");
      row.querySelector(".rp-change").addEventListener("click", () => { edit.hidden = !edit.hidden; if (!edit.hidden) edit.querySelector("input").focus(); });
      const apply = (value) => { state[kind] = value.trim(); state.order = null; box.querySelector(".rp-list").classList.add("busy"); load(); };
      edit.querySelector(".rp-apply").addEventListener("click", () => apply(edit.querySelector("input").value));
      edit.querySelector("input").addEventListener("keydown", (e) => { if (e.key === "Enter") apply(e.target.value); });
      edit.querySelector(".rp-home")?.addEventListener("click", () => apply(""));
    });
    box.querySelectorAll(".rp-stop").forEach((row, i) => {
      const move = (to) => {
        const o = [...state.order];
        o.splice(to, 0, o.splice(i, 1)[0]);
        state.order = o;
        box.querySelector(".rp-list").classList.add("busy");
        load();
      };
      row.querySelector(".rp-up").addEventListener("click", () => move(i - 1));
      row.querySelector(".rp-down").addEventListener("click", () => move(i + 1));
      bindDrag(row);
    });
  }

  // ☰ 손잡이로 위아래 끌기(PC·폰) — 손 떼면 새 순서로 거리 다시 계산
  function bindDrag(row) {
    const handle = row.querySelector(".rp-handle");
    handle.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      const list = box.querySelector(".rp-list");
      const rows = () => [...list.querySelectorAll(".rp-stop")];
      row.classList.add("dragging");
      // 움직임·손 떼기는 window에서 받는다 — 끄는 중에 줄 자리를 옮기면(before/after) 마우스 붙잡기가 풀려 손잡이로는 못 받음(사진 순서 끌기와 같은 이유)
      const onMove = (ev) => {
        if (ev.pointerId !== e.pointerId) return;
        for (const other of rows()) {
          if (other === row) continue;
          const rect = other.getBoundingClientRect();
          const mid = rect.top + rect.height / 2;
          const idxRow = rows().indexOf(row), idxOther = rows().indexOf(other);
          if (idxOther < idxRow && ev.clientY < mid) { other.before(row); break; }
          if (idxOther > idxRow && ev.clientY > mid) { other.after(row); break; }
        }
      };
      const onUp = (ev) => {
        if (ev.pointerId !== e.pointerId) return;
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        window.removeEventListener("pointercancel", onUp);
        row.classList.remove("dragging");
        const next = rows().map((x) => Number(x.dataset.id));
        if (next.join() !== state.order.join()) {
          state.order = next;
          list.classList.add("busy");
          load();
        }
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onUp);
    });
  }

  await load();
}

// 네이버 지도 앱 자동차 길찾기 — 출발 → 경유지(현장들) → 도착(복귀지). 안드로이드는 intent(앱 없으면 스토어), 아이폰은 nmap://
function openNaverRoute(r) {
  const e = encodeURIComponent;
  let q = `slat=${r.start.lat}&slng=${r.start.lng}&sname=${e(r.start.is_home ? "회사" : r.start.address)}`
    + `&dlat=${r.end.lat}&dlng=${r.end.lng}&dname=${e(r.end.is_home ? "회사" : r.end.address)}`;
  r.stops.forEach((s, i) => { q += `&v${i + 1}lat=${s.lat}&v${i + 1}lng=${s.lng}&v${i + 1}name=${e(s.name)}`; });
  q += "&appname=com.kfsc21c.report";
  window.location.href = /Android/i.test(navigator.userAgent)
    ? `intent://route/car?${q}#Intent;scheme=nmap;package=com.nhn.android.nmap;end`
    : `nmap://route/car?${q}`;
}

// 티맵 자동차 길찾기 — 출발 → 경유지(현장들, 순서대로) → 목적지(복귀지).
// 티맵은 바깥 앱에서 경유지를 2곳까지만 받음(사용자 폰 2026-10-01: 4곳 넘기면 앞 2곳만, SK 개발자 포럼 답변도 같음)
// → 현장 3곳 이상이면 구간 고르기 창: 한 구간 = 경유지 2곳 + 목적지, 다음 구간은 그 목적지에서 출발.
function openTmapRoute(r) {
  if (r.stops.length <= RP_TMAP_VIA) {
    launchTmap(r.start, r.stops, r.end);
    return;
  }
  const pts = [{ ...r.start, kind: "start" }, ...r.stops.map((s, i) => ({ ...s, no: i + 1 })), { ...r.end, kind: "end" }];
  const legs = [];
  for (let i = 0; i < pts.length - 1;) {
    const j = Math.min(i + RP_TMAP_VIA + 1, pts.length - 1);
    const km = r.legs.slice(i, j).reduce((a, b) => a + b, 0);
    legs.push({ from: pts[i], vias: pts.slice(i + 1, j), to: pts[j], km: Math.round(km * 10) / 10 });
    i = j;
  }
  const label = (p) => p.kind ? `${p.kind === "start" ? "출발" : "복귀"} · ${p.is_home ? "회사" : apEsc(p.address)}` : `${p.no}. ${apEsc(p.name)}`;
  const circled = "①②③④⑤";
  const overlay = document.createElement("div");
  overlay.className = "mail-overlay";
  overlay.innerHTML = `<div class="mail-box rp-tleg-box" role="dialog" aria-modal="true">
    <div class="mail-head"><b>🚗 티맵으로 출발</b></div>
    <div class="mail-msg warn">티맵은 다른 앱에서 경유지를 <b>2곳까지만</b> 받아서 ${r.stops.length}곳을 한 번에 넣을 수 없습니다.
      ${legs.length}구간으로 나눴어요 — 한 구간이 끝난 현장에서 일을 마치면 다음 구간을 누르세요.</div>
    ${legs.map((g, k) => `<button type="button" class="rp-tleg" data-k="${k}">
      <span class="rp-dot">${circled[k] || k + 1}</span>
      <span class="rp-tleg-pts">${[g.from, ...g.vias, g.to].map((p) => `<span>${label(p)}</span>`).join("")}</span>
      <span class="rp-tleg-km">${g.km}km</span></button>`).join("")}
    <div class="rp-hint">네이버 지도는 ${r.stops.length}곳을 한 번에 넣을 수 있습니다.</div>
    <div class="mail-foot"><button type="button" class="mail-cancel">닫기</button></div></div>`;
  document.body.appendChild(overlay);
  const close = () => overlay.remove();
  overlay.addEventListener("click", (ev) => { if (ev.target === overlay) close(); });
  overlay.querySelector(".mail-cancel").addEventListener("click", close);
  overlay.querySelectorAll(".rp-tleg").forEach((btn) => btn.addEventListener("click", () => {
    const g = legs[Number(btn.dataset.k)];
    btn.classList.add("sent");
    launchTmap(g.from, g.vias, g.to);
  }));
}

// 점 이름: 출발·복귀 = "회사" 또는 주소, 현장 = 현장 이름
function rpPlaceName(p) { return "is_home" in p ? (p.is_home ? "회사" : p.address) : p.name; }

function launchTmap(from, vias, to) {
  const e = encodeURIComponent;
  let q = `goalx=${to.lng}&goaly=${to.lat}&goalname=${e(rpPlaceName(to))}&key=${RP_TMAP_KEY}`
    + `&startx=${from.lng}&starty=${from.lat}&startname=${e(rpPlaceName(from))}`;
  vias.forEach((s, i) => { q += `&via${i + 1}x=${s.lng}&via${i + 1}y=${s.lat}&via${i + 1}name=${e(rpPlaceName(s))}`; });
  if (/Android/i.test(navigator.userAgent)) {
    window.location.href = `intent://route?${q}#Intent;scheme=tmap;package=com.skt.tmap.ku;end`;
    return;
  }
  window.location.href = `tmap://route?${q}`;
}
