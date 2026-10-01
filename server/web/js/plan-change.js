// 방문 예정 [📅 일정 변경] 창(2026-10-01) — 현장에 전화했더니 "내일 공사 안 해요" → 폰에서 바로 옮기기.
// ⭐ 추천 날짜(같은 지역 출장에 붙이기 / 가장 가까운 빈 평일) · 📅 작은 달력(그 요원의 날짜별 현장 수·같은 지역 출장·못 가는 날) · 👤 대신 갈 요원.
// 서버: server/api/routers/plan_change.py(options·substitutes), 저장은 PATCH /calendar/plans/{id}(옮기거나 요원을 바꾸면 📌 고정).
// 창 틀은 css/mail.css, 이 창만의 규칙은 css/plan-change.css. 날짜 글자 함수는 js/auto-plan.js(apDay·apEsc·apShort)를 같이 쓴다.

async function openPlanChange(planId, onDone) {
  const overlay = document.createElement("div");
  overlay.className = "mail-overlay";
  overlay.innerHTML = '<div class="mail-box pc-box" role="dialog" aria-modal="true"><div class="mail-wait">불러오는 중…</div></div>';
  document.body.appendChild(overlay);
  const box = overlay.querySelector(".mail-box");
  let busy = false;
  const close = () => { if (!busy) { overlay.remove(); document.removeEventListener("keydown", onKey); } };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });

  let o;
  try {
    o = await api(`/calendar/plans/${planId}/options`);
  } catch (err) {
    box.innerHTML = `<div class="mail-head"><b>📅 일정 변경</b></div><div class="mail-msg bad">${apEsc(err.message)}</div>
      <div class="mail-foot"><button type="button" class="mail-cancel">닫기</button></div>`;
    box.querySelector(".mail-cancel").addEventListener("click", close);
    return;
  }
  const plan = o.plan;
  const byDate = Object.fromEntries(o.days.map((d) => [d.date, d]));
  const months = [...new Set(o.days.map((d) => d.date.slice(0, 7)))];
  let monthIdx = Math.max(0, months.indexOf(plan.date.slice(0, 7)));
  let picked = null; // 작은 달력에서 고른 날

  const save = async (patch, question) => {
    if (!confirm(question)) return;
    busy = true;
    try {
      await apiPatch(`/calendar/plans/${plan.id}`, patch);
      busy = false;
      close();
      if (onDone) onDone(patch.plan_date || plan.date);
    } catch (err) {
      busy = false;
      const msg = box.querySelector(".pc-msg");
      msg.hidden = false;
      msg.textContent = err.message;
    }
  };
  const moveTo = (date) => save({ plan_date: date }, `${apShort(plan.site_name)} 방문을 ${apDay(date)}로 옮길까요?\n(옮긴 예정은 📌 고정 — 자동 배치가 안 바꿉니다)`);
  const dayInfo = (d) => {
    if (!d) return "";
    if (d.blocked) return d.blocked;
    const parts = [];
    if (d.same.length) parts.push(`같은 지역: ${d.same.map(apShort).join(", ")}`);
    if (d.other) parts.push("다른 지역 출장 있음");
    parts.push(d.count ? `그날 ${d.count}곳` : "그날 비어 있음");
    if (d.count >= o.limit) parts.push("한도 다 참");
    return parts.join(" · ");
  };

  box.innerHTML = `
    <div class="mail-head"><b>📅 일정 변경</b>
      <span class="mail-sub">${apEsc(plan.site_name)} · 원래 ${apDay(plan.date)}${plan.staff_name ? ` · ${apEsc(plan.staff_name)}` : ""}</span></div>
    <div class="mail-label">⭐ 추천 날짜</div>
    <div class="pc-sugs"></div>
    <div class="mail-label">📅 직접 고르기 <span class="pc-hint">초록 = 같은 지역 출장 있는 날 · 숫자 = 그날 가는 현장 수</span></div>
    <div class="pc-cal">
      <div class="pc-cal-head"><button type="button" class="pc-prev" aria-label="이전 달">‹</button><b></b><button type="button" class="pc-next" aria-label="다음 달">›</button></div>
      <div class="pc-grid"></div>
      <div class="pc-pick" hidden><span></span><button type="button" class="mail-primary pc-go">이 날로 옮기기</button></div>
    </div>
    <details class="pc-subs"><summary>👤 대신 갈 요원으로 바꾸기</summary><div class="pc-subs-body"><div class="mail-wait">불러오는 중…</div></div></details>
    <div class="mail-msg bad pc-msg" hidden></div>
    <div class="mail-foot"><button type="button" class="mail-cancel">닫기</button></div>`;
  box.querySelector(".mail-cancel").addEventListener("click", close);

  // ⭐ 추천
  const sugs = box.querySelector(".pc-sugs");
  if (!o.suggestions.length) sugs.innerHTML = '<div class="pc-none">추천할 날이 없습니다 — 아래 달력에서 고르세요.</div>';
  for (const s of o.suggestions) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = `pc-sug ${s.kind}`;
    b.innerHTML = `<b>${apDay(s.date)}</b><span></span>`;
    b.querySelector("span").textContent = s.kind === "join" ? `${s.with.map(apShort).join(", ")}와 함께` : "가장 가까운 빈 평일";
    b.addEventListener("click", () => moveTo(s.date));
    sugs.appendChild(b);
  }

  // 📅 작은 달력(월 단위, 서버가 준 석 달)
  const grid = box.querySelector(".pc-grid");
  const pickBox = box.querySelector(".pc-pick");
  const drawMonth = () => {
    const ym = months[monthIdx];
    const first = new Date(`${ym}-01T00:00:00`);
    box.querySelector(".pc-cal-head b").textContent = `${first.getFullYear()}년 ${first.getMonth() + 1}월`;
    box.querySelector(".pc-prev").disabled = monthIdx === 0;
    box.querySelector(".pc-next").disabled = monthIdx === months.length - 1;
    let html = [..."일월화수목금토"].map((w, i) => `<span class="pc-wd${i === 0 ? " sun" : i === 6 ? " sat" : ""}">${w}</span>`).join("");
    html += "<span></span>".repeat(first.getDay());
    for (const d of o.days.filter((x) => x.date.startsWith(ym))) {
      const n = Number(d.date.slice(8));
      const off = d.past || d.blocked || d.already || d.count >= o.limit;
      const cls = ["pc-day", off ? "off" : "", d.same.length && !d.other ? "same" : "", d.other ? "other" : "",
        d.date === plan.date ? "orig" : "", d.date === picked ? "picked" : "", d.blocked && d.blocked !== "주말" ? "hol" : ""].filter(Boolean).join(" ");
      html += `<button type="button" class="${cls}" data-date="${d.date}" ${off ? "disabled" : ""} title="${apEsc(dayInfo(d))}">
        <span>${n}</span>${d.count ? `<i>${d.count}</i>` : ""}</button>`;
    }
    grid.innerHTML = html;
    grid.querySelectorAll(".pc-day:not(.off)").forEach((b) => b.addEventListener("click", () => {
      picked = b.dataset.date;
      drawMonth();
      pickBox.hidden = false;
      pickBox.querySelector("span").textContent = `${apDay(picked)} — ${dayInfo(byDate[picked])}`;
      pickBox.querySelector(".pc-go").hidden = picked === plan.date;
      loadSubs();
    }));
  };
  box.querySelector(".pc-prev").addEventListener("click", () => { monthIdx -= 1; drawMonth(); });
  box.querySelector(".pc-next").addEventListener("click", () => { monthIdx += 1; drawMonth(); });
  pickBox.querySelector(".pc-go").addEventListener("click", () => picked && moveTo(picked));
  drawMonth();

  // 👤 대신 갈 요원 — 고른 날(없으면 원래 날) 기준
  const subsBody = box.querySelector(".pc-subs-body");
  const loadSubs = async () => {
    const date = picked || plan.date;
    subsBody.innerHTML = '<div class="mail-wait">불러오는 중…</div>';
    try {
      const r = await api(`/calendar/plans/${plan.id}/substitutes?date=${date}`);
      subsBody.innerHTML = `<div class="pc-hint">${apDay(date)}에 대신 갈 요원 — 같은 지역 출장이 있는 사람부터</div>`;
      for (const s of r.staff) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "pc-sub" + (s.full ? " full" : "");
        b.disabled = s.full;
        const note = s.full ? "그날 한도 다 참" : s.same.length ? `같은 지역 출장: ${s.same.map(apShort).join(", ")}`
          : s.count === 0 ? "그날 비어 있음" : `그날 ${s.count}곳 (${s.other_regions.join(", ")})`;
        b.innerHTML = "<b></b><span></span>";
        b.querySelector("b").textContent = s.name;
        b.querySelector("span").textContent = note;
        b.addEventListener("click", () => save({ staff_id: s.staff_id, plan_date: date },
          `${apShort(plan.site_name)} ${apDay(date)} 방문을 ${s.name}님이 가는 것으로 바꿀까요?\n(📌 고정 — 이 회차만, 현장 담당요원은 그대로)`));
        subsBody.appendChild(b);
      }
      if (!r.staff.length) subsBody.insertAdjacentHTML("beforeend", '<div class="pc-none">다른 요원이 없습니다.</div>');
    } catch (err) {
      subsBody.innerHTML = `<div class="pc-none">${apEsc(err.message)}</div>`;
    }
  };
  box.querySelector(".pc-subs").addEventListener("toggle", (e) => { if (e.target.open) loadSubs(); });
}
