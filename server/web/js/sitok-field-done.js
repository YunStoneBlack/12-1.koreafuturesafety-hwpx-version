// 시특법 현장 조사 맨 아래 [✓ 조사 완료](sitok-field.html, 2026-10-18 민재형 "조사완료 버튼") — 회차 화면 "현장 조사 ✓"는 이 버튼으로만.
// 누를 때마다 빠진 항목을 탭마다 보여 주고 [이어서 점검하기]·[현장점검 완료] — 경고가 남아도 완료를 누르면 완료(형 "현장에서 누락되는 점검항목이 없도록").
// 항목을 누르면 그 탭으로. 묶음은 동마다 완료, 다 끝나면 제출 현황 [현장점검]·방문 달력 칸 채움. 서버 server/api/routers/sitok_field_done.py.

(function () {
  const rid = Number(new URLSearchParams(location.search).get("report")) || null;
  const box = document.getElementById("sf-done");
  if (!rid || !box) return;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const err = (e) => showError(document.getElementById("error"), e);
  const TAB = { defects: "🔍 결함 조사", overview: "🏢 전경사진", public: "🚶 공중이용", other: "🧱 기타시설", docs: "📋 자료수집", load: "⚖ 하중상태", survey: "📷 조사 전경" };
  const md = (s) => String(s || "").slice(5).replace("-", "/");
  let st = null;

  function draw() {
    const u = st.unit.total > 1 ? `<span class="sf-done-unit">묶음 ${st.unit.total}동 중 ${st.unit.done}동 완료${st.field ? ` · 제출 현황 [현장점검] ${md(st.field.at)}` : ""}</span>` : "";
    box.classList.toggle("on", !!st.done);
    box.innerHTML = st.done
      ? `<b class="sf-done-ok">✓ 현장 조사 완료</b><span class="sf-done-by">${md(st.done.at)} ${esc(st.done.by)}</span>${u}
        <button type="button" class="secondary btn-sm sf-done-undo">완료 취소</button>`
      : `<button type="button" class="sf-done-btn">✓ 조사 완료</button><span class="sf-done-help">모든 탭을 마쳤으면 누르세요 — 빠진 항목이 있으면 알려 드립니다.</span>${u}`;
    box.querySelector(".sf-done-btn")?.addEventListener("click", finish);
    box.querySelector(".sf-done-undo")?.addEventListener("click", undo);
  }

  function ask(items) { // → true = 그래도 완료, false = 이어서 점검(항목을 누르면 그 탭으로)
    return new Promise((resolve) => {
      const ov = document.createElement("div");
      ov.className = "mail-overlay";
      ov.innerHTML = `<div class="mail-box sf-miss-box" role="dialog" aria-modal="true"><div class="mail-head"><b>⚠ 빠진 점검 항목 ${items.length}개</b>
        <span class="mail-sub">해당이 없어서 비운 것인지, 아직 안 한 것인지 확인해 주세요. 항목을 누르면 그 탭으로 갑니다.</span></div>
        <div class="sf-miss">${items.map((m) => `<button type="button" data-tab="${esc(m.tab)}"><b>${esc(TAB[m.tab] || m.tab)}</b><span>${esc(m.text)}</span></button>`).join("")}</div>
        <div class="mail-foot"><button type="button" class="mail-cancel">이어서 점검하기</button><button type="button" class="mail-primary sf-miss-ok">현장점검 완료</button></div></div>`;
      document.body.appendChild(ov);
      const done = (v) => { ov.remove(); resolve(v); };
      ov.querySelector(".mail-cancel").addEventListener("click", () => done(false));
      ov.querySelector(".sf-miss-ok").addEventListener("click", () => done(true));
      ov.querySelectorAll(".sf-miss button").forEach((b) => b.addEventListener("click", () => {
        done(false);
        document.querySelector(`.sf-tab[data-tab="${b.dataset.tab}"]`)?.click();
        window.scrollTo({ top: 0 });
      }));
    });
  }

  async function finish(e) {
    const btn = e.currentTarget;
    btn.disabled = true;
    try {
      st = await api(`/sitok/reports/${rid}/field-check`); // 누를 때마다 새로 — 다시 찍고 눌러도 남은 것만
      if (st.missing.length && !(await ask(st.missing))) { draw(); return; }
      st = await apiPost(`/sitok/reports/${rid}/field-done`, { done: true });
      draw();
    } catch (x) { err(x); btn.disabled = false; }
  }

  async function undo() {
    const bundle = st.unit.total > 1 && st.field ? " 묶음 제출 현황 [현장점검] 날짜도 지워집니다(달력 칸은 그 자리에 빈 칸으로)." : "";
    if (!confirm(`현장 조사 완료를 취소할까요? 회차 화면의 ✓가 빠집니다.${bundle}`)) return;
    try { st = await apiPost(`/sitok/reports/${rid}/field-done`, { done: false }); draw(); } catch (x) { err(x); }
  }

  api(`/sitok/reports/${rid}/field-check`).then((d) => { st = d; draw(); }).catch(err);
})();
