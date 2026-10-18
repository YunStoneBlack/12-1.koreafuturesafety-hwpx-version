// 시특법 회차 [🏢 시설물 현황] 창(2026-10-11) — 보고서 시설물편 1.1 건축물 현황표·1.2.1~1.2.3 체크·1.2.4 구조 및 마감·용도현황.
// 칸 이름은 회사 원본, 값은 저장한 것 → 없으면 시설물 칸(관리대장·직접 입력) → 전회차 보고서 값 → "-"(10/12). [🤖 관리대장·건축물대장으로 채우기] → 확인 → 저장.
// 관리대장 값과 전회차 보고서 값이 다르면 칸 아래에 둘 다 보여 주고 고르게(사용자 10/12 — 우리 점검자가 잘못 썼을 수 있음, 기본은 관리대장).
// 서버 server/api/routers/sitok_reports.py /detail, 읽고 쓰기 server/sitok/detail.py.

async function openSitokDetail(reportId, title, onSaved) {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const same = (a, b) => { // 띄어쓰기·쉼표·㎡·소수 끝 0은 같은 값으로
    const n = (s) => String(s || "").replace(/[\s,㎡ㆍ·]/g, "").replace(/(\.\d*?)0+(?=\D|$)/g, "$1").replace(/\.(?=\D|$)/g, "");
    return n(a) === n(b);
  };
  const differs = (f) => f.prior && f.prior !== "-" && f.value && f.value !== "-" && !same(f.prior, f.value);
  const overlay = document.createElement("div");
  overlay.className = "mail-overlay";
  overlay.innerHTML = '<div class="mail-box ai-box" role="dialog" aria-modal="true"><div class="mail-wait">불러오는 중…</div></div>';
  document.body.appendChild(overlay);
  const box = overlay.querySelector(".mail-box");
  const close = () => overlay.remove();
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });

  function draw(s) {
    const groups = {};
    s.fields.forEach((f) => { (groups[f.group] ||= []).push(f); });
    const nDiff = s.fields.filter(differs).length;
    const useRow = (u) => `<div class="dt-use">${[0, 1, 2, 3].map((k) => `<input value="${esc(u[k])}" placeholder="${["층", "바닥면적(㎡)", "주용도", "비고"][k]}" />`).join("")}
      <button type="button" class="sv-x" title="이 줄 지우기">✕</button></div>`;
    box.innerHTML = `<div class="mail-head"><b>🏢 시설물 현황</b><span class="mail-sub">${esc(title)} — 보고서 1.1 건축물 현황표, 1.2.1~1.2.4</span></div>
      <div class="dt-ai"><button type="button" class="secondary dt-fill">🤖 관리대장·건축물대장·도면·전회차 보고서로 채우기</button>
        <span class="sk-help">건축물대장 ${s.has_register ? "올려 둠 ✓" : "없음"} · 관리대장 ${s.has_ledger ? "올려 둠 ✓" : "없음"} — 대장·도면은 시설물 화면 "시설물 정보·서류"에서 올립니다</span>
        <span class="sk-help">${s.saved ? "저장한 값" : `지금 값 = 시설물 칸(관리대장·직접 입력)${s.has_prior ? " + 전회차 보고서 값" : ""}`}${!s.has_ledger && !s.has_register ? " — 관리대장·건축물대장이 없어 나머지 칸은 직접(없으면 \"-\")" : ""}</span></div>
      <div class="pv-box"></div>
      ${s.ai ? '<div class="mail-msg ok">🤖 AI가 채웠습니다 — 확인하고 [저장]. 자료에 없는 칸은 "-"</div>' : ""}
      ${nDiff ? `<div class="mail-msg dt-diffs">⚠ 전회차 보고서와 다른 칸 ${nDiff}개 — 지금 값은 관리대장·건축물대장 쪽입니다. 전회차 값이 맞으면 그 칸의 [이걸로]</div>` : ""}
      <div class="ai-form">
        ${Object.entries(groups).map(([g, fs]) => `<h4>${esc(g)}</h4><div class="dt-grid">${fs.map((f) => `<label${differs(f) ? ' class="diff"' : ""}>${esc(f.label)}${differs(f) ? " ⚠" : ""}
          <textarea data-k="${esc(f.key)}" rows="${Math.min(3, (f.value.match(/\n/g) || []).length + 1)}">${esc(f.value)}</textarea>
          ${differs(f) ? `<span class="dt-prior">전회차 보고서: <b>${esc(f.prior)}</b> <button type="button" class="link-btn" data-prior="${esc(f.prior)}">이걸로</button></span>` : ""}</label>`).join("")}</div>`).join("")}
        <h4>1.2.1 ~ 1.2.3 보관·관리 실태 <span class="sk-help">하나씩 고르기</span></h4>
        <div class="dt-checks">${s.checks.map((c) => `<div class="dt-check" data-k="${esc(c.key)}"><span>${esc(c.label)}</span>
          ${c.options.map((o, i) => `<button type="button" data-i="${i}" class="${c.selected === i ? "on" : ""}">${esc(o)}</button>`).join("")}</div>`).join("")}</div>
        <h4>대상시설물의 용도현황 <span class="sk-help">층마다 한 줄</span></h4>
        <div id="dt-uses">${s.uses.map(useRow).join("")}</div>
        <button type="button" class="secondary btn-sm dt-add">+ 층 줄 더하기</button>
        <label>연면적 합계<input class="dt-total" value="${esc(s.uses_total)}" /></label>
      </div>
      <div class="mail-msg dt-msg" hidden></div>
      <div class="mail-foot"><button type="button" class="mail-cancel">닫기</button><button type="button" class="mail-primary dt-save">저장</button></div>`;
    sitokPrevSlot(box.querySelector(".pv-box"), reportId); // 전회차 보고서 PDF(10/18 민재형, js/sitok-prev.js) — [🤖 채우기]가 같이 읽음
    const uses = box.querySelector("#dt-uses");
    const bindX = () => uses.querySelectorAll(".sv-x").forEach((b) => { b.onclick = () => b.closest(".dt-use").remove(); });
    bindX();
    box.querySelector(".dt-add").addEventListener("click", () => { uses.insertAdjacentHTML("beforeend", useRow(["", "", "", "-"])); bindX(); });
    box.querySelectorAll(".dt-check").forEach((row) => row.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
      row.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
    })));
    box.querySelector(".mail-cancel").addEventListener("click", close);
    box.querySelectorAll(".dt-prior button").forEach((b) => b.addEventListener("click", (e) => {
      e.preventDefault();
      const label = b.closest("label");
      label.querySelector("textarea").value = b.dataset.prior;
      label.classList.remove("diff");
      b.closest(".dt-prior").textContent = "전회차 보고서 값으로 바꿨습니다";
    }));
    const msg = box.querySelector(".dt-msg");
    box.querySelector(".dt-fill").addEventListener("click", async (e) => {
      e.target.disabled = true;
      e.target.textContent = "🤖 채우는 중…(20~90초 — 전회차 보고서 PDF는 처음 한 번 더 읽음)";
      try {
        draw(await apiUpload(`/sitok/reports/${reportId}/detail/ai`, new FormData())); // 건축물대장·도면은 시설물에 올려 둔 것(10/14), 전회차 보고서 PDF는 이 회차(10/18)
      } catch (err) { msg.hidden = false; msg.className = "mail-msg dt-msg bad"; msg.textContent = err.message; e.target.disabled = false; e.target.textContent = "🤖 관리대장·건축물대장·도면·전회차 보고서로 채우기"; }
    });
    const save = async () => { // [저장]·[✓ 작성 완료](먼저 저장) 같이 씀 — 성공하면 true
      const body = { fields: {}, checks: {}, uses: [], uses_total: box.querySelector(".dt-total").value.trim() };
      box.querySelectorAll("textarea[data-k]").forEach((t) => { body.fields[t.dataset.k] = t.value.trim(); });
      box.querySelectorAll(".dt-check").forEach((row) => {
        const on = row.querySelector("button.on");
        body.checks[row.dataset.k] = on ? Number(on.dataset.i) : null;
      });
      body.uses = [...uses.querySelectorAll(".dt-use")].map((row) => [...row.querySelectorAll("input")].map((i) => i.value.trim()));
      try {
        await api(`/sitok/reports/${reportId}/detail`, { method: "PUT", body: JSON.stringify(body) });
        msg.hidden = false; msg.className = "mail-msg dt-msg ok"; msg.textContent = "저장했습니다 — [보고서 만들기]를 누르면 들어갑니다.";
        if (onSaved) onSaved();
        return true;
      } catch (err) { msg.hidden = false; msg.className = "mail-msg dt-msg bad"; msg.textContent = err.message; return false; }
    };
    box.querySelector(".dt-save").addEventListener("click", save);
    sitokStepFoot(box, reportId, "detail", save, onSaved); // [✓ 작성 완료](10/18 민재형, js/sitok-steps.js)
  }

  // 도면·건축물대장 올리기는 10/14부터 시설물 화면 "시설물 정보·서류"(js/sitok-drawings.js) — 여기선 [🤖 채우기]만

  try { draw(await api(`/sitok/reports/${reportId}/detail`)); } catch (e) { box.innerHTML = `<div class="mail-msg bad">${esc(e.message)}</div><div class="mail-foot"><button type="button" class="mail-cancel">닫기</button></div>`; box.querySelector(".mail-cancel").onclick = close; }
}
