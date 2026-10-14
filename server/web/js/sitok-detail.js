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
      <div class="dt-ai"><label class="secondary-link">건축물대장 PDF ${s.has_register ? "(올려 둠 ✓ — 바꾸려면 다시)" : "(있으면 층별 용도·면적까지)"}<input type="file" accept="application/pdf,.pdf" hidden data-kr-file="1" class="dt-reg" /></label>
        <button type="button" class="secondary dt-fill">🤖 관리대장·건축물대장·도면으로 채우기</button>
        <span class="sk-help">${s.saved ? "저장한 값" : `지금 값 = 시설물 칸(관리대장·직접 입력)${s.has_prior ? " + 전회차 보고서 값" : ""}`}${!s.has_ledger && !s.has_register ? " — 관리대장·건축물대장이 없어 나머지 칸은 직접(없으면 \"-\")" : ""}</span></div>
      <div class="dt-dwg"></div>
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
    drawDwg(box.querySelector(".dt-dwg"));
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
      e.target.textContent = "🤖 채우는 중…(20~60초)";
      try {
        const fd = new FormData();
        const reg = box.querySelector(".dt-reg").files[0];
        if (reg) fd.append("file", reg);
        draw(await apiUpload(`/sitok/reports/${reportId}/detail/ai`, fd));
      } catch (err) { msg.hidden = false; msg.className = "mail-msg dt-msg bad"; msg.textContent = err.message; e.target.disabled = false; e.target.textContent = "🤖 관리대장·건축물대장·도면으로 채우기"; }
    });
    box.querySelector(".dt-reg").addEventListener("change", (e) => { if (e.target.files[0]) e.target.closest("label").firstChild.textContent = `건축물대장 PDF: ${e.target.files[0].name} `; });
    box.querySelector(".dt-save").addEventListener("click", async () => {
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
      } catch (err) { msg.hidden = false; msg.className = "mail-msg dt-msg bad"; msg.textContent = err.message; }
    });
  }

  // 시설물 도면(10/12 사용자) — 시설물에 한 번 올리면 다음 회차에도 그대로, 증축·인테리어 등으로 바뀌면 여기서 바꿈. 서버 routers/sitok_drawings.py
  async function drawDwg(el, data) {
    const url = `/sitok/reports/${reportId}/drawings`;
    try { data = data || await api(url); } catch (e) { el.innerHTML = `<div class="mail-msg bad">${esc(e.message)}</div>`; return; }
    const KIND = { struct: ["📐 구조일반사항·건축개요 도면", "[🤖 채우기]가 같이 읽음(콘크리트 강도·철근 종류·기초형식·지하깊이·슬래브 두께·방수 등)"],
      attach: ["🗂 첨부 도면(평·입·단면도)", "보고서 1.2.9 관련 설계도면 쪽 뒤에 이 순서로 붙음 — 없으면 \"-\""],
      schedule: ["📏 구조 일람표(기둥·보·슬래브·벽 단면표)", "정밀 📐 재료시험 [🤖 일람표에서 설계 치수 채우기]가 읽음(10/14)"] };
    el.innerHTML = `<div class="dt-dwg-note sk-help">도면은 시설물에 한 번 올리면 다음 회차에도 그대로 씁니다 — 증축·내부 인테리어 등으로 바뀌면 지우고 새로 올리세요(이미 만든 보고서는 그대로).</div>`
      + Object.entries(KIND).map(([k, [label, help]]) => `<div class="dt-dwg-k" data-k="${k}"><div class="dt-dwg-h"><b>${label}</b> <span class="sk-help">${help}</span>
        <label class="secondary-link">+ 올리기(PDF·그림, 여러 개)<input type="file" accept="application/pdf,.pdf,image/*" multiple hidden data-kr-file="1" /></label></div>
        ${(data[k] || []).length ? `<ol class="dt-dwg-list">${data[k].map((d, i) => `<li data-id="${d.id}"><a href="${BASE}/api${url}/${k}/${d.id}/file" target="_blank" rel="noopener">${esc(d.name)}</a>
          <span class="sk-help">${d.pdf ? `${d.pages}쪽` : "그림"} · ${esc(d.at)}</span>
          ${k === "attach" ? `<button type="button" class="link-btn" data-m="-1"${i ? "" : " disabled"}>▲</button><button type="button" class="link-btn" data-m="1"${i < data[k].length - 1 ? "" : " disabled"}>▼</button>` : ""}
          <button type="button" class="link-btn dt-dwg-del" title="지우기">✕</button></li>`).join("")}</ol>` : '<div class="sk-help dt-dwg-none">아직 없음</div>'}</div>`).join("");
    el.querySelectorAll(".dt-dwg-k").forEach((row) => {
      const k = row.dataset.k;
      const inp = row.querySelector("input[type=file]");
      inp.addEventListener("change", async () => {
        const files = [...inp.files];
        for (let i = 0; i < files.length; i++) {
          row.querySelector(".dt-dwg-h .sk-help").textContent = `올리는 중… ${i + 1} / ${files.length}`;
          const fd = new FormData();
          fd.append("kind", k);
          fd.append("file", files[i]);
          try { data = await apiUpload(url, fd); } catch (e) { alert(e.message); break; }
        }
        drawDwg(el, data);
      });
      row.querySelectorAll("li").forEach((li) => {
        li.querySelector(".dt-dwg-del").addEventListener("click", async () => {
          if (!confirm("이 도면을 지울까요? 다음에 만드는 보고서부터 빠집니다.")) return;
          try { drawDwg(el, await api(`${url}/${k}/${li.dataset.id}`, { method: "DELETE" })); } catch (e) { alert(e.message); }
        });
        li.querySelectorAll("[data-m]").forEach((b) => b.addEventListener("click", async () => {
          try { drawDwg(el, await apiPost(`${url}/${k}/${li.dataset.id}/move`, { step: Number(b.dataset.m) })); } catch (e) { alert(e.message); }
        }));
      });
    });
  }

  try { draw(await api(`/sitok/reports/${reportId}/detail`)); } catch (e) { box.innerHTML = `<div class="mail-msg bad">${esc(e.message)}</div><div class="mail-foot"><button type="button" class="mail-cancel">닫기</button></div>`; box.querySelector(".mail-cancel").onclick = close; }
}
