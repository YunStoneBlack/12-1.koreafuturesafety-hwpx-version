// 시특법 시설물 화면의 "점검 보고서" 칸(sitok-facility.html?id=, 2026-10-10 4단계) — 회차(연도·반기) 만들기·틀 올리기·보고서 만들기.
// 10/12: 틀은 늘 회사 원본 템플릿 — 전회차 보고서(직전 회차가 만든 한글 자동, 또는 올린 지난 보고서)는 데이터만. 만들기는 백그라운드(한글 PDF 몇 분) — 3초마다 진행 확인.
// 서버 server/api/routers/sitok_reports.py, 값 바꾸기 server/sitok/report_build.py.
// 10/13 회차 ↔ 계약: [+ 회차 만들기]는 그 반기를 계약기간이 덮는 계약을 붙임(GET …/contract-for). 없으면 "새 계약서를 올리세요" 칸 —
// 계약서 PDF를 올리면 읽어서 계약을 추가하고(점검 용역 계약 칸에도 생김) 그 회차에 붙임, 또는 [계약 없이 만들기](나중에 계약을 추가하면 자동으로 붙음).
// 장기·지속 시설물은 마지막 계약이 끝나기 60일 전부터 맨 위에 "다음 계약서 필요".

(function () {
  const fid = Number(new URLSearchParams(location.search).get("id")) || null;
  const panel = document.getElementById("sk-rep-panel");
  if (!fid || !panel) return;
  panel.hidden = false;
  const box = document.getElementById("sk-reps");
  const errorEl = document.getElementById("error");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const err = (e) => showError(errorEl, e);
  let data = null;
  let contracts = [];
  const polling = {};
  let flash = null; // 다시 그린 뒤 맨 위에 띄울 안내 [글, "ok"|"warn"]
  const ymdDot = (s) => (s || "?").replaceAll("-", ".");
  const CON_KEYS = ["sector", "title", "contract_no", "contract_date", "start_date", "end_date", "halves", "first_half_end", "second_half_start", "rounds",
    "amount", "rep_name", "joint_type", "joint_pct", "bid_method", "field"];

  function personOptions(selected) {
    return '<option value="">—</option>' + data.persons.map((p) => `<option value="${p.id}"${p.id === selected ? " selected" : ""}>${esc(p.name)}${p.position ? ` ${esc(p.position)}` : ""}</option>`).join("");
  }

  function card(r) {
    const el = document.createElement("div");
    el.className = `sk-rep ${r.status}`;
    const conList = data.group && data.group_contracts ? data.group_contracts : contracts; // 묶인 동이면 묶음 전체 동의 계약(한 계약서에 여러 동)
    const contractOpts = '<option value="">계약 고르기</option>' + conList.map((c) =>
      `<option value="${c.id}"${c.id === r.contract_id ? " selected" : ""}>${c.facility ? `[${esc(c.facility)}] ` : ""}${esc(c.sector)} · ${esc(c.title || "계약")} (${esc(c.start_date)}~${esc(c.end_date)})</option>`).join("");
    const parts = r.participant_ids || [];
    const g = data.group; // 같이 점검하는 동(10/12) — 만들면 묶음 한 권
    const stateText = r.status === "running" ? `<span class="sk-rep-st run">⏳ ${esc(r.message)}</span>`
      : r.status === "failed" ? `<span class="sk-rep-st bad">✗ 실패: ${esc(r.message)}</span>`
        : r.status === "done" ? `<span class="sk-rep-st ok">✓ ${esc(r.made_at)} 만듦 — ${esc(r.message)}</span>` : "";
    const kind = r.kind || "정기"; // 회차 종류(10/13) — 계약서 그 반기 줄에서 자동, 틀리면 아래 칸에서 직접
    el.innerHTML = `<div class="sk-rep-head"><b>${r.year}년 ${esc(r.half)}</b><span class="sk-kind ${kind === "정밀" ? "pre" : ""}">${kind}안전점검</span>
        <span class="sk-rep-src">${r.past ? "이미 낸 보고서" : r.has_source ? `전회차 보고서: ${esc(r.source_note)}` : '전회차 보고서 없음 — 처음 맡는 시설물(우리가 하던 시설물이면 지난 보고서 한글을 올리세요)'}</span>
        <label class="secondary-link"${r.past ? " hidden" : ""} title="이력·시설물 현황·지난 평가 같은 데이터만 가져옵니다(보고서 틀은 회사 원본)">지난 보고서 한글 올리기<input type="file" accept=".hwp,.hwpx" hidden data-kr-file="1" /></label>
        ${r.past ? "" : `<a class="secondary-link sk-rep-field" href="sitok-field.html?report=${r.id}">📱 현장 조사</a>
          ${kind === "정밀" ? `<a class="secondary-link sk-rep-tests" href="sitok-tests.html?report=${r.id}">📐 재료시험</a>
          <a class="secondary-link sk-rep-rating" href="sitok-rating.html?report=${r.id}">📊 상태평가</a>` : ""}
          <button type="button" class="secondary btn-sm sk-rep-detail">🏢 시설물 현황${r.has_detail ? " ✓" : ""}</button>
          <button type="button" class="secondary btn-sm sk-rep-survey">📝 면담·변경사항${r.has_survey ? " ✓" : ""}</button>
          <button type="button" class="secondary btn-sm sk-rep-ai">🤖 AI 초안${r.has_ai ? " ✓" : ""}</button>`}
        <button type="button" class="secondary btn-sm sk-rep-del">삭제</button></div>
      ${g && !r.past ? `<div class="sk-rep-group">📚 묶음 보고서 <b>${esc(g.name)}</b> — ${g.members.map((m, i) => `제${i + 1}장 ${esc(m.name)}`).join(" · ")}
        <span class="sk-help">점검기간·제출일·기술자는 묶인 동 회차도 같이 바뀝니다. 현장 조사·현황·AI 초안은 동마다.</span></div>` : ""}
      <div class="sk-rep-grid">
        <label>계약<select data-k="contract_id">${contractOpts}</select></label>
        <label>종류 <span class="sk-help">계약서 회차 줄에서 자동 — 틀리면 직접</span><select data-k="kind">${["정기", "정밀"].map((k) => `<option${k === kind ? " selected" : ""}>${k}</option>`).join("")}</select></label>
        <label>점검기간 시작 <span class="sk-help">민간 = 현장 간 날</span><input type="date" data-k="period_start" value="${esc(r.period_start)}" /></label>
        <label>점검기간 끝 <span class="sk-help">민간 = 보고서 낸 날</span><input type="date" data-k="period_end" value="${esc(r.period_end)}" /></label>
        <label>제출일 <span class="sk-help">표지·제출문 연월, 비우면 점검기간 끝</span><input type="date" data-k="report_date" value="${esc(r.report_date)}" /></label>
        <label>책임기술자<select data-k="chief_id">${personOptions(r.chief_id)}</select></label>
        <label>참여기술자<select data-k="p0">${personOptions(parts[0])}</select></label>
        ${g && !r.past ? `<label>이 동 점검금액(천원) <span class="sk-help">같은 계약서를 여러 동이 같이 쓰면 꼭 — 비면 계약 금액</span>
          <input data-k="amount_k" inputmode="numeric" value="${esc(r.amount_k)}" placeholder="예: 550" /></label>` : ""}
      </div>
      <div class="sk-rep-foot">${stateText}
        ${r.has_pdf ? `<a class="secondary-link" href="${BASE}/api/sitok/reports/${r.id}/file/pdf?v=${encodeURIComponent(r.made_at || "")}" target="_blank" rel="noopener">${kind === "정밀" ? "합본 PDF" : "PDF 보기"}</a>` : ""}
        ${r.has_hwpx ? `<a class="secondary-link" href="${BASE}/api/sitok/reports/${r.id}/file/hwpx?v=${encodeURIComponent(r.made_at || "")}">${kind === "정밀" ? "본문 한글" : "한글 받기"}</a>` : ""}
        ${r.has_appendix ? `<a class="secondary-link" href="${BASE}/api/sitok/reports/${r.id}/file/appendix?v=${encodeURIComponent(r.made_at || "")}">부록 한글</a>` : ""}
        ${r.past ? "" : `<button type="button" class="sk-rep-build"${r.status === "running" ? " disabled" : ""}>${r.has_pdf ? "다시 만들기" : g && kind !== "정밀" ? `묶음 보고서 만들기(${g.members.length}동)` : "보고서 만들기"}</button>`}</div>`;
    el.querySelectorAll("[data-k]").forEach((inp) => inp.addEventListener("change", async () => {
      const k = inp.dataset.k;
      const body = k === "p0" ? { participant_ids: inp.value ? [Number(inp.value)] : [] }
        : k === "amount_k" ? { amount_k: inp.value.trim() }
          : { [k]: k.endsWith("_id") ? (inp.value ? Number(inp.value) : null) : (inp.value || null) };
      try { await apiPatch(`/sitok/reports/${r.id}`, body); inp.classList.add("sk-filled"); setTimeout(() => inp.classList.remove("sk-filled"), 1200); } catch (e) { err(e); }
    }));
    const file = el.querySelector('input[type="file"]');
    file.addEventListener("change", async () => {
      if (!file.files[0]) return;
      el.classList.add("busy");
      el.querySelector(".sk-rep-src").textContent = `${file.files[0].name} 올리는 중…(hwp는 한글로 바꾸느라 20~40초)`;
      try {
        const fd = new FormData();
        fd.append("file", file.files[0]);
        await apiUpload(`/sitok/reports/${r.id}/source`, fd);
        load();
      } catch (e) { err(e); load(); }
    });
    enableFileDrop(el.querySelector(".sk-rep-head"), file);
    el.querySelector(".sk-rep-del").addEventListener("click", async () => {
      if (!confirm(`${r.year}년 ${r.half} 보고서를 지울까요? 만든 한글·PDF도 지워집니다.`)) return;
      try { await api(`/sitok/reports/${r.id}`, { method: "DELETE" }); load(); } catch (e) { err(e); }
    });
    el.querySelector(".sk-rep-ai")?.addEventListener("click", () => openSitokAi(r.id, `${r.year}년 ${r.half}`, load));
    el.querySelector(".sk-rep-detail")?.addEventListener("click", () => openSitokDetail(r.id, `${r.year}년 ${r.half}`, load));
    el.querySelector(".sk-rep-survey")?.addEventListener("click", () => openSitokSurvey(r.id, `${r.year}년 ${r.half}`, load));
    el.querySelector(".sk-rep-build")?.addEventListener("click", async () => {
      try { await apiPost(`/sitok/reports/${r.id}/build`); load(); } catch (e) { err(e); }
    });
    if (r.status === "running") poll(r.id);
    return el;
  }

  function poll(id) {
    if (polling[id]) return;
    polling[id] = setInterval(async () => {
      try {
        const r = await api(`/sitok/reports/${id}`);
        if (r.status !== "running") { clearInterval(polling[id]); delete polling[id]; load(); }
        else { const st = box.querySelector(".sk-rep.running .sk-rep-st"); if (st) st.textContent = `⏳ ${r.message}`; }
      } catch (_) { /* 다음에 다시 */ }
    }, 3000);
  }

  // 장기·지속 계약 끝나기 전·끝난 뒤 알림(서버 renew_info)
  function renewNote() {
    const r = data.renew;
    if (!r) return null;
    const el = document.createElement("div");
    el.className = `sk-renew${r.days < 0 ? " over" : ""}`;
    el.textContent = r.days < 0
      ? `⚠ 장기·지속 계약이 ${ymdDot(r.end)}에 끝났습니다 — 다음 계약서를 올려야 다음 회차 보고서에 들어갑니다(아래 [+ 회차 만들기] 때 올려도 됨).`
      : `⏳ 장기·지속 계약이 ${ymdDot(r.end)}에 끝납니다(${r.days}일 남음) — 다음 계약서를 준비하세요. 다음 회차를 만들 때 올리면 그 회차에 붙습니다.`;
    return el;
  }

  async function createReport(year, half, contractId, kind) {
    const body = { year, half, contract_id: contractId };
    if (kind) body.kind = kind; // 비우면 서버가 계약서 회차 줄에서(정기/정밀)
    const chief = data.persons.find((p) => p.sitok_grade.includes("특급")) || data.persons[0];
    if (chief) body.chief_id = chief.id;
    const other = data.persons.find((p) => p.id !== chief?.id);
    if (other) body.participant_ids = [other.id];
    await apiPost(`/sitok/facilities/${fid}/reports`, body);
  }

  // 그 반기를 덮는 계약이 없을 때 — 계약서 PDF 올리기 / 계약 없이 만들기 / 취소
  function noContract(el, year, half, latest) {
    el.querySelector(".nr-nocon")?.remove();
    const box2 = document.createElement("div");
    box2.className = "nr-nocon";
    box2.innerHTML = `<b>⚠ ${year}년 ${half}를 덮는 계약이 없습니다</b>
      <span>${latest ? `마지막 계약: ${esc(latest.title || "계약")} (${ymdDot(latest.start_date)} ~ ${ymdDot(latest.end_date)})` : "등록된 계약이 없습니다"}
        — 이번 계약서를 올리면 읽어서 계약을 추가하고 이 회차에 붙입니다.</span>
      <div class="nr-nocon-acts">
        <label class="sk-drop nr-con-drop"><input type="file" accept="application/pdf,.pdf" hidden data-kr-file="skip" />
          <b>📄 이번 계약서 PDF 올리기</b><span class="sk-drop-msg">눌러서 고르거나 끌어다 놓기 — 민간 계약서(스캔도 됨)·나라장터 계약서</span></label>
        <div class="nr-nocon-btns"><button type="button" class="secondary btn-sm nr-skip">계약 없이 만들기</button>
          <button type="button" class="secondary btn-sm nr-cancel">취소</button></div>
      </div>
      <span class="sk-help">계약 없이 만들어도 나중에 [+ 계약 추가]로 이 반기를 덮는 계약을 넣으면 자동으로 붙습니다.</span>`;
    el.appendChild(box2);
    const msg = box2.querySelector(".sk-drop-msg");
    const input = box2.querySelector("input");
    enableFileDrop(box2.querySelector(".nr-con-drop"), input);
    box2.querySelector(".nr-cancel").addEventListener("click", () => box2.remove());
    box2.querySelector(".nr-skip").addEventListener("click", async () => {
      box2.classList.add("busy");
      try {
        await createReport(year, half, null, el.querySelector(".nr-kind")?.value || "");
        flash = [`${year}년 ${half} 회차를 계약 없이 만들었습니다 — 계약을 추가하면 자동으로 붙습니다.`, "warn"];
        load();
      } catch (e) { err(e); box2.classList.remove("busy"); }
    });
    input.addEventListener("change", async () => {
      const file = input.files[0];
      input.value = "";
      if (!file) return;
      box2.classList.add("busy");
      msg.textContent = `${file.name} — 읽는 중…(10~30초)`;
      try {
        const fd = new FormData();
        fd.append("kind", "contract");
        fd.append("file", file);
        const rd = await apiUpload("/sitok/read", fd);
        const fields = Object.fromEntries(CON_KEYS.filter((k) => rd.fields?.[k] !== undefined && rd.fields[k] !== "" && rd.fields[k] !== null)
          .map((k) => [k, rd.fields[k]]));
        const out = await apiPost(`/sitok/facilities/${fid}/contracts`, { ...fields, contract_token: rd.token });
        await createReport(year, half, out.new_contract_id, el.querySelector(".nr-kind")?.value || "");
        const chk = await api(`/sitok/facilities/${fid}/contract-for?year=${year}&half=${encodeURIComponent(half)}`);
        const fits = chk.contract && chk.contract.id === out.new_contract_id;
        flash = rd.error ? [`계약서를 읽지 못해 칸이 비었습니다 — 아래 "점검 용역 계약"에서 날짜·금액을 채우세요. (${rd.error})`, "warn"]
          : fits ? [`✓ 계약서를 읽어 계약을 추가하고 ${year}년 ${half} 회차에 붙였습니다 — 아래 "점검 용역 계약"에서 읽은 값을 확인하세요.`, "ok"]
            : [`계약을 추가해 이 회차에 붙였지만, 읽은 계약기간이 ${year}년 ${half}와 맞지 않습니다 — "점검 용역 계약"에서 날짜를 확인하세요.`, "warn"];
        window.dispatchEvent(new Event("sitok-contracts-changed")); // 시설물 화면 계약 칸 다시 그리기(js/sitok-facility.js)
        load();
      } catch (e) {
        err(e);
        box2.classList.remove("busy");
        msg.textContent = "눌러서 고르거나 끌어다 놓기";
      }
    });
  }

  function drawNew() {
    const d = data.defaults;
    const el = document.createElement("div");
    el.className = "sk-rep-new";
    el.innerHTML = `<b>새 회차</b>
      <input type="number" class="nr-year" value="${d.year}" min="2000" max="2100" aria-label="연도" />년
      <select class="nr-half"><option${d.half === "상반기" ? " selected" : ""}>상반기</option><option${d.half === "하반기" ? " selected" : ""}>하반기</option></select>
      <select class="nr-kind" title="회차 종류 — 계약서 그 반기 줄(정기/정밀)에서 자동, 틀리면 고르기"><option value="">계약서대로</option><option>정기</option><option>정밀</option></select>
      <button type="button" class="btn-sm nr-add">+ 회차 만들기</button>
      <label class="secondary-link nr-past" title="이미 낸 지난 반기 보고서 한글(.hwp·.hwpx) — 연도·반기·점검기간은 결과표에서 읽고, 다음 회차가 이걸 틀로 씁니다">이미 낸 보고서 등록<input type="file" accept=".hwp,.hwpx" hidden data-kr-file="1" /></label>
      <span class="sk-help nr-msg">보고서는 회사 원본 템플릿으로 만들고, 직전 회차(또는 [이미 낸 보고서 등록]으로 올린 지난 반기 한글)에서는 이력·시설물 현황·지난 평가 같은 데이터만 가져옵니다. 처음 맡는 시설물(신축·타회사 인계)은 그냥 회차를 만들면 됩니다.</span>`;
    const past = el.querySelector(".nr-past input");
    past.addEventListener("change", async () => {
      if (!past.files[0]) return;
      const msg = el.querySelector(".nr-msg");
      el.classList.add("busy");
      msg.textContent = `${past.files[0].name} 올리는 중…(큰 파일은 몇십 초)`;
      try {
        const fd = new FormData();
        fd.append("file", past.files[0]);
        await apiUpload(`/sitok/facilities/${fid}/reports/past`, fd);
        load();
      } catch (e) { err(e); el.classList.remove("busy"); msg.textContent = ""; }
    });
    enableFileDrop(el.querySelector(".nr-past"), past);
    el.querySelector(".nr-add").addEventListener("click", async () => { // 그 반기를 덮는 계약을 찾아 붙임 — 없으면 계약서 올리기 칸
      const year = Number(el.querySelector(".nr-year").value), half = el.querySelector(".nr-half").value;
      const kind = el.querySelector(".nr-kind").value || "";
      el.classList.add("busy");
      try {
        const r = await api(`/sitok/facilities/${fid}/contract-for?year=${year}&half=${encodeURIComponent(half)}`);
        if (r.contract) {
          await createReport(year, half, r.contract.id, kind);
          if (!kind && r.kind === "정밀") flash = [`${year}년 ${half} 회차를 계약서대로 정밀안전점검으로 만들었습니다 — 틀리면 회차 칸 "종류"에서 바꾸세요.`, "ok"];
          load();
        } else {
          noContract(el, year, half, r.latest);
        }
      } catch (e) { err(e); } finally { el.classList.remove("busy"); }
    });
    return el;
  }

  async function load() {
    try {
      const [r, f] = await Promise.all([api(`/sitok/facilities/${fid}/reports`), api(`/sitok/facilities/${fid}`)]);
      data = r;
      contracts = f.contracts || [];
      box.innerHTML = "";
      if (flash) {
        const f2 = document.createElement("div");
        f2.className = `sk-flash ${flash[1]}`;
        f2.textContent = flash[0];
        box.appendChild(f2);
        flash = null;
      }
      const renew = renewNote();
      if (renew) box.appendChild(renew);
      box.appendChild(drawNew());
      data.reports.forEach((x) => box.appendChild(card(x)));
      if (!data.reports.length) box.insertAdjacentHTML("beforeend", '<div class="empty-note">아직 회차가 없습니다.</div>');
    } catch (e) { err(e); }
  }
  window.addEventListener("sitok-group-changed", load); // 같이 점검하는 동이 바뀌면(js/sitok-group.js)
  load();
})();
