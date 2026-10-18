// 시특법 회차 칸 완료(2026-10-18 민재형 "조사완료 버튼", "나머지도 마찬가지", "완료버튼 생성해서 미기재항목 말해주고 조사완료 누르면 체크") — 회차 화면 ✓는 이 버튼으로만.
// [✓ 조사 완료] = 현장 조사·재료시험·상태평가·면담·변경사항, [✓ 작성 완료] = 시설물 현황·AI 초안.
// 누를 때마다 미기재 항목을 보여 주고 [이어서 하기]·[완료] — 경고가 남아도 완료를 누르면 완료(형 "현장에서 누락되는 점검항목이 없도록"), 항목을 누르면 그 자리로.
// 화면(현장 조사·재료시험·상태평가) = 맨 아래 <div class="sf-done" data-step="…">(자동으로 그림), 창(면담·현황·AI 초안) = sitokStepFoot(창 아래 버튼).
// 서버 server/api/routers/sitok_steps.py.

const SITOK_STEP_NAME = { field: "현장 조사", tests: "재료시험", rating: "상태평가", survey: "면담·변경사항", detail: "시설물 현황", ai: "AI 초안" };
const SITOK_STEP_WORD = { field: "조사", tests: "조사", rating: "조사", survey: "조사", detail: "작성", ai: "작성" };
const sitokStepEsc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const sitokStepDay = (s) => String(s || "").slice(5).replace("-", "/");

function sitokStepJump(target) { // 미기재 항목 → 현장 조사 탭이면 그 탭, 아니면 그 칸으로
  const tab = document.querySelector(`.sf-tab[data-tab="${target}"]`);
  if (tab) { tab.click(); window.scrollTo({ top: 0 }); return; }
  document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function sitokStepAsk(step, items) { // → true = 그래도 완료, false = 이어서 하기
  const word = SITOK_STEP_WORD[step];
  const jump = items.some((m) => m.target);
  return new Promise((resolve) => {
    const ov = document.createElement("div");
    ov.className = "mail-overlay sf-step-top";
    ov.innerHTML = `<div class="mail-box sf-miss-box" role="dialog" aria-modal="true"><div class="mail-head"><b>⚠ 미기재 항목 ${items.length}개 — ${sitokStepEsc(SITOK_STEP_NAME[step])}</b>
      <span class="mail-sub">해당이 없어서 비운 것인지, 아직 안 한 것인지 확인해 주세요.${jump ? " 항목을 누르면 그 자리로 갑니다." : ""}</span></div>
      <div class="sf-miss">${items.map((m) => `<${m.target ? "button type=\"button\"" : "div"} class="sf-miss-it" data-target="${sitokStepEsc(m.target)}"><b>${sitokStepEsc(m.title)}</b><span>${sitokStepEsc(m.text)}</span></${m.target ? "button" : "div"}>`).join("")}</div>
      <div class="mail-foot"><button type="button" class="mail-cancel">이어서 ${word === "조사" ? "점검" : "작성"}하기</button>
        <button type="button" class="mail-primary sf-miss-ok">${step === "field" ? "현장점검 완료" : `${sitokStepEsc(SITOK_STEP_NAME[step])} ${word} 완료`}</button></div></div>`;
    document.body.appendChild(ov);
    const done = (v) => { ov.remove(); resolve(v); };
    ov.querySelector(".mail-cancel").addEventListener("click", () => done(false));
    ov.querySelector(".sf-miss-ok").addEventListener("click", () => done(true));
    ov.querySelectorAll("button.sf-miss-it").forEach((b) => b.addEventListener("click", () => { done(false); sitokStepJump(b.dataset.target); }));
  });
}

async function sitokStepFinish(reportId, step) { // 완료 → 상태(이어서 하기면 null)
  const st = await api(`/sitok/reports/${reportId}/steps/${step}/check`); // 누를 때마다 새로 — 다시 찍고 눌러도 남은 것만
  if (st.missing.length && !(await sitokStepAsk(step, st.missing))) return null;
  return apiPost(`/sitok/reports/${reportId}/steps/${step}/done`, { done: true });
}

async function sitokStepUndo(reportId, step, st) {
  const bundle = step === "field" && st.unit.total > 1 && st.field ? " 묶음 제출 현황 [현장점검] 날짜도 지워집니다(달력 칸은 그 자리에 빈 칸으로)." : "";
  if (!confirm(`${SITOK_STEP_NAME[step]} 완료를 취소할까요? 회차 화면의 ✓가 빠집니다.${bundle}`)) return null;
  return apiPost(`/sitok/reports/${reportId}/steps/${step}/done`, { done: false });
}

const sitokStepUnit = (st) => (st.unit.total > 1 ? `<span class="sf-done-unit">묶음 ${st.unit.total}동 중 ${st.unit.done}동 완료${st.field ? ` · 제출 현황 [현장점검] ${sitokStepDay(st.field.at)}` : ""}</span>` : "");

// 화면 맨 아래 칸(현장 조사·재료시험·상태평가)
function sitokStepBar(box) {
  const rid = Number(new URLSearchParams(location.search).get("report")) || null;
  const step = box.dataset.step;
  if (!rid || !step) return;
  const err = (e) => showError(document.getElementById("error"), e);
  const word = SITOK_STEP_WORD[step];
  let st = null;
  const draw = () => {
    box.classList.toggle("on", !!st.done);
    box.innerHTML = st.done
      ? `<b class="sf-done-ok">✓ ${sitokStepEsc(SITOK_STEP_NAME[step])} 완료</b><span class="sf-done-by">${sitokStepDay(st.done.at)} ${sitokStepEsc(st.done.by)}</span>${sitokStepUnit(st)}
        <button type="button" class="secondary btn-sm sf-done-undo">완료 취소</button>`
      : `<button type="button" class="sf-done-btn">✓ ${word} 완료</button><span class="sf-done-help">다 마쳤으면 누르세요 — 미기재 항목이 있으면 알려 드립니다.</span>${sitokStepUnit(st)}`;
    box.querySelector(".sf-done-btn")?.addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      try {
        await new Promise((r) => setTimeout(r, 400)); // 방금 고친 칸 저장(바뀜 → 바로 저장)이 먼저 끝나게
        const next = await sitokStepFinish(rid, step);
        if (next) st = next;
        draw();
      } catch (x) { err(x); btn.disabled = false; }
    });
    box.querySelector(".sf-done-undo")?.addEventListener("click", async () => {
      try { const next = await sitokStepUndo(rid, step, st); if (next) { st = next; draw(); } } catch (x) { err(x); }
    });
  };
  api(`/sitok/reports/${rid}/steps/${step}`).then((d) => { st = d; draw(); }).catch(err);
}

// 창 아래(면담·현황·AI 초안) — save() = 창의 [저장](성공하면 true), onChange = 회차 화면 다시 그리기
async function sitokStepFoot(box, reportId, step, save, onChange) {
  const foot = box.querySelector(".mail-foot");
  if (!foot) return;
  const word = SITOK_STEP_WORD[step];
  const el = document.createElement("span");
  el.className = "sf-step-foot";
  foot.prepend(el);
  let st = null;
  const msg = (text, bad) => {
    const m = box.querySelector(".mail-msg");
    if (!m) return;
    m.hidden = !text;
    m.className = `mail-msg${bad ? " bad" : " ok"}`;
    m.textContent = text || "";
  };
  const draw = () => {
    el.innerHTML = st.done
      ? `<b class="sf-done-ok">✓ ${word} 완료</b> <small>${sitokStepDay(st.done.at)} ${sitokStepEsc(st.done.by)}</small> <button type="button" class="link-btn sf-step-undo">완료 취소</button>`
      : `<button type="button" class="sf-step-btn">✓ ${word} 완료</button>`;
    el.querySelector(".sf-step-btn")?.addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      try {
        if (save && !(await save())) { btn.disabled = false; return; } // 먼저 지금 칸을 저장
        const next = await sitokStepFinish(reportId, step);
        if (next) { st = next; draw(); msg(`${SITOK_STEP_NAME[step]} ${word} 완료 — 회차 화면에 ✓`); onChange?.(); } else btn.disabled = false;
      } catch (x) { msg(x.message, true); btn.disabled = false; }
    });
    el.querySelector(".sf-step-undo")?.addEventListener("click", async () => {
      try { const next = await sitokStepUndo(reportId, step, st); if (next) { st = next; draw(); onChange?.(); } } catch (x) { msg(x.message, true); }
    });
  };
  try { st = await api(`/sitok/reports/${reportId}/steps/${step}`); draw(); } catch (_) { el.remove(); }
}

document.querySelectorAll(".sf-done[data-step]").forEach(sitokStepBar);
