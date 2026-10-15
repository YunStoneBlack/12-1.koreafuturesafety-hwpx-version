// 시특법 시설물 등록·고치기(sitok-facility.html, 2026-10-10 2단계). ?id= 없으면 새 등록 화면(sitok-new.html, 10/12 — 서류 한 번에)으로 감.
// 10/14 형 피드백 ⑦ 3층 구조: 이 파일은 접힌 "시설물 정보·서류"(관리대장·건축물대장·도면·시설물 칸)와 "계약"(카드마다 쓰는 회차) 칸. 회차 목록은 js/sitok-reports.js.
// PDF 칸: 관리대장 → 시설물 칸(+ 보고서 틀 추정, 관리주체 대표자는 계약 칸에), 계약서 → 계약 칸(민간/관급 구분, 비어 있는 시설물 칸도 채움).
// 민간/관급 기본값(인수인계 10/10): 민간 = 독자수행 100%·수의계약·건축. 관급 1년 계약이면 "상반기 완료일·하반기 시작일"을 직접 정함.
// 서버 server/api/routers/sitok.py, PDF 읽기 server/sitok/reader.py.

(function () {
  const errorEl = document.getElementById("error");
  const id = Number(new URLSearchParams(location.search).get("id")) || null;
  if (!id) { location.replace("sitok-new.html"); return; } // 새 등록은 한 화면에서(계약서·이전 회차·동마다 관리대장·건축물대장)
  // 회차 만들기에서 계약서를 올려 계약이 늘면(js/sitok-reports.js, 10/13) 계약 칸을 다시 그림
  window.addEventListener("sitok-contracts-changed", async () => { try { fac = await api(`/sitok/facilities/${id}`); draw(); } catch (e) { showError(errorEl, e); } });
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let opts = null;
  let fac = null; // 저장된 시설물(고치기 화면)
  let ledgerToken = null;
  let ledgerExtra = null;
  const conTokens = {}; // 계약 카드 키 → 올린 계약서 token
  const conRounds = {}; // 계약 카드 키 → 계약서에서 읽은 회차 줄 [{year, half, kind, amount}] — 회차 종류(정기/정밀) 자동(10/13)
  let ownerRep = ""; // 관리대장에서 읽은 관리주체 대표자(민간 계약 대표자 칸이 비면 채움)

  // 칸 정의·그리기·읽기는 js/sitok-fields.js(새 등록 화면과 같이 씀, 10/12)
  const { FAC, CON } = SitokFields;
  const input = (prefix, f) => SitokFields.input(opts, prefix, f);
  const setValues = SitokFields.setValues;
  const values = SitokFields.values;

  // ---------- 계약 카드 ----------
  function conCard(c) {
    const key = c?.id ? `c${c.id}` : `new${Math.random().toString(36).slice(2, 7)}`;
    const card = document.createElement("div");
    card.className = "sk-con";
    card.dataset.key = key;
    if (c?.id) card.dataset.id = c.id;
    const used = c?.used_by?.length ? `<span class="sk-con-used">쓰는 회차: ${c.used_by.map(esc).join(" · ")}</span>` : c?.id ? '<span class="sk-con-used none">쓰는 회차 없음</span>' : "";
    card.innerHTML = `<div class="sk-con-head"><b>${c?.id ? esc(c.title || "계약") : "새 계약"}</b>${used}
        ${c?.has_pdf ? `<a href="${BASE}/api/sitok/files/contract/${c.id}" target="_blank" rel="noopener">계약서 PDF 보기</a>` : ""}
        ${id ? `<label class="secondary-link sk-con-pdf">계약서 PDF로 채우기<input type="file" accept="application/pdf,.pdf" hidden data-kr-file="1" /></label>` : ""}
        <span class="sk-con-msg"></span>
        ${c?.id ? '<button type="button" class="secondary btn-sm sk-con-save">이 계약 저장</button><button type="button" class="secondary btn-sm sk-con-del">삭제</button>' : ""}</div>
      <div class="field-grid">${CON.map((f) => input(`${key}`, f)).join("")}</div>`;
    const defaults = { sector: "민간", halves: "연간", joint_type: "독자수행", joint_pct: 100, bid_method: "수의계약", field: "건축" };
    setValues(card, { ...defaults, ...(c || {}) });
    card.querySelectorAll(".sk-filled").forEach((el) => el.classList.remove("sk-filled"));
    const sync = () => { // 관급 + 연간일 때만 상반기 완료일·하반기 시작일
      const gov = card.querySelector('[data-key="sector"]').value === "관급";
      const yearly = card.querySelector('[data-key="halves"]').value === "연간";
      card.querySelectorAll(".sk-f-first_half_end, .sk-f-second_half_start").forEach((el) => { el.hidden = !(gov && yearly); });
      card.querySelector(".sk-f-contract_no").hidden = !gov;
    };
    card.querySelector('[data-key="sector"]').addEventListener("change", (e) => {
      if (e.target.value === "민간") setValues(card, { joint_type: "독자수행", joint_pct: 100, bid_method: "수의계약" });
      sync();
    });
    card.querySelector('[data-key="halves"]').addEventListener("change", sync);
    sync();
    card.querySelector(".sk-con-pdf input")?.addEventListener("change", (e) => readPdf("contract", e.target.files[0], card));
    card.querySelector(".sk-con-save")?.addEventListener("click", async () => {
      try {
        fac = await apiPatch(`/sitok/contracts/${c.id}`, { ...values(card), contract_token: conTokens[key] || null, ...(conRounds[key] ? { rounds: conRounds[key] } : {}) });
        flash("계약을 저장했습니다.");
        draw();
      } catch (err) { showError(errorEl, err); }
    });
    card.querySelector(".sk-con-del")?.addEventListener("click", async () => {
      if (!confirm(`"${c.title || "이 계약"}"을 지울까요? 올린 계약서 PDF도 같이 지워집니다.`)) return;
      try { fac = await api(`/sitok/contracts/${c.id}`, { method: "DELETE" }); draw(); } catch (err) { showError(errorEl, err); }
    });
    return card;
  }

  // ---------- PDF 읽기 ----------
  async function readPdf(kind, file, card) {
    if (!file) return;
    const zone = card ? card.querySelector(".sk-con-msg") : document.querySelector(`.sk-drop[data-kind="${kind}"] .sk-drop-msg`);
    const target = card || document.querySelector(`.sk-drop[data-kind="${kind}"]`);
    target.classList.add("busy");
    zone.textContent = `${file.name} — 읽는 중…(10~30초)`;
    try {
      const fd = new FormData();
      fd.append("kind", kind);
      fd.append("file", file);
      const r = await apiUpload("/sitok/read", fd);
      const f = r.fields || {};
      if (kind === "ledger") {
        ledgerToken = r.token;
        ledgerExtra = f.ledger || null;
        ownerRep = f.owner_rep || "";
        setValues(document.getElementById("sk-fac"), f, false);
        const first = document.querySelector("#sk-cons .sk-con");
        if (first && ownerRep) setValues(first, { rep_name: ownerRep }, false); // 대표자는 글자 있는 관리대장이 스캔 계약서보다 정확
      } else {
        const box = card || document.querySelector("#sk-cons .sk-con");
        conTokens[box.dataset.key] = r.token;
        if (Array.isArray(f.rounds) && f.rounds.length) conRounds[box.dataset.key] = f.rounds;
        const rep = f.sector === "민간" && ownerRep ? ownerRep : f.rep_name;
        setValues(box, { ...f, rep_name: rep }, false);
        box.querySelector('[data-key="sector"]').dispatchEvent(new Event("change"));
        setValues(box, { joint_type: f.joint_type, bid_method: f.bid_method }, false);
        if (!id) setValues(document.getElementById("sk-fac"), { owner_name: f.owner_name, address: f.address }, true); // 시설물 칸이 비었을 때만
      }
      zone.textContent = r.error ? r.error : `✓ ${file.name} — 읽어서 채웠습니다. 저장할 때 같이 보관됩니다.`;
      zone.classList.toggle("bad", !!r.error);
    } catch (err) {
      zone.textContent = `읽지 못했습니다: ${err.message}`;
      zone.classList.add("bad");
    } finally {
      target.classList.remove("busy");
    }
  }

  function flash(msg) {
    const el = document.getElementById("sk-saved");
    el.textContent = msg;
    setTimeout(() => { el.textContent = ""; }, 3000);
  }

  // ---------- 그리기 ----------
  function draw() {
    const facBox = document.getElementById("sk-fac");
    facBox.innerHTML = `<div class="field-grid">${FAC.map((f) => input("f", f)).join("")}</div>` +
      (fac?.has_ledger_pdf ? `<p class="sk-file"><a href="${BASE}/api/sitok/files/ledger/${fac.id}" target="_blank" rel="noopener">올린 시설물관리대장 PDF 보기</a></p>` : "");
    if (fac) setValues(facBox, fac);
    facBox.querySelectorAll(".sk-filled").forEach((el) => el.classList.remove("sk-filled"));
    SitokFields.linkLegal(facBox);
    const cons = document.getElementById("sk-cons");
    cons.innerHTML = "";
    if (fac) {
      document.getElementById("sk-crumb").textContent = fac.name;
      document.title = `${fac.name} - 시특법`;
      const g = fac.group && fac.group.members.length > 1 ? fac.group : null; // 묶음이면 동 바꾸기 탭(10/15 — 목록은 묶음 카드 하나)
      const tabs = document.getElementById("sk-dong-tabs");
      tabs.hidden = !g;
      if (g) {
        document.getElementById("sk-crumb").textContent = `${g.name} › ${fac.name}`;
        tabs.innerHTML = `<span class="sk-dong-tabs-h">📚 ${esc(g.name)} <small>${g.members.length}동 한 보고서</small></span>` + g.members.map((m, i) =>
          m.id === fac.id ? `<span class="sk-dong-tab on" aria-current="page">제${i + 1}장 ${esc(m.name)}</span>`
            : `<a class="sk-dong-tab" href="sitok-facility.html?id=${m.id}">제${i + 1}장 ${esc(m.name)}</a>`).join("");
      }
      (fac.contracts || []).forEach((c) => cons.appendChild(conCard(c)));
      const lead = g && g.members[0].id !== fac.id ? g.members[0] : null; // 묶음의 다른 동 — 계약서는 보통 대표 동에(한 계약에 여러 동, 10/15)
      if (!fac.contracts?.length) {
        cons.innerHTML = lead ? `<div class="empty-note">묶음 계약을 같이 씁니다 — 계약서는 대표 동 <a href="sitok-facility.html?id=${lead.id}">제1장 ${esc(lead.name)}</a>에 있습니다.</div>`
          : '<div class="empty-note">계약이 없습니다. [+ 계약 추가]로 넣으세요.</div>';
      }
      document.getElementById("sk-con-count").textContent = fac.contracts?.length ? `${fac.contracts.length}건 — 최근 계약이 위, 카드마다 쓰는 회차`
        : lead ? `묶음 계약 — 대표 동(${lead.name})에 있음` : "계약이 없습니다 — 회차를 만들 때 계약서를 올리거나 [+ 계약 추가]";
      if (!fac.contracts?.length && !lead) document.getElementById("sk-con-panel").open = true;
      document.getElementById("sk-register-msg").textContent = fac.has_register
        ? "올려 둠 ✓ — 바꾸려면 다시 올리기 · 시설물 현황 [🤖 채우기]·면담 1.2.8 초안이 읽습니다" : "시설물 현황 [🤖 채우기]·면담 1.2.8 초안이 읽습니다(층별 용도·면적·변동사항) — 눌러서 고르거나 끌어다 놓기";
      document.getElementById("sk-register").classList.toggle("has", !!fac.has_register);
      sitokDrawDrawings(document.getElementById("sk-dwg"), `/sitok/facilities/${fac.id}/drawings`);
    } else {
      cons.appendChild(conCard(null));
    }
    document.getElementById("sk-add-con").hidden = !id;
    document.getElementById("sk-del").hidden = !id;
    document.getElementById("sk-save").textContent = id ? "시설물 저장" : "등록";
  }

  document.getElementById("sk-add-con").addEventListener("click", () => {
    const cons = document.getElementById("sk-cons");
    cons.querySelector(".empty-note")?.remove();
    const card = conCard(null);
    const save = document.createElement("button");
    save.type = "button";
    save.className = "btn-sm";
    save.textContent = "이 계약 추가";
    save.addEventListener("click", async () => {
      try {
        fac = await apiPost(`/sitok/facilities/${id}/contracts`, { ...values(card), contract_token: conTokens[card.dataset.key] || null, ...(conRounds[card.dataset.key] ? { rounds: conRounds[card.dataset.key] } : {}) });
        flash("계약을 추가했습니다.");
        draw();
      } catch (err) { showError(errorEl, err); }
    });
    card.querySelector(".sk-con-head").appendChild(save);
    cons.prepend(card);
    document.getElementById("sk-con-panel").open = true;
  });

  document.getElementById("sk-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    errorEl.style.display = "none";
    const facility = values(document.getElementById("sk-fac"));
    if (!facility.name) { alert("시설물명을 넣어 주세요."); return; }
    const btn = document.getElementById("sk-save");
    btn.disabled = true;
    try {
      if (id) {
        fac = await apiPatch(`/sitok/facilities/${id}${ledgerToken ? `?ledger_token=${ledgerToken}` : ""}`, facility);
        ledgerToken = null;
        flash("저장했습니다.");
        draw();
      } else {
        const card = document.querySelector("#sk-cons .sk-con");
        const contract = { ...values(card), contract_token: conTokens[card.dataset.key] || null, ...(conRounds[card.dataset.key] ? { rounds: conRounds[card.dataset.key] } : {}) };
        const hasContract = contract.title || contract.start_date || contract.amount || contract.contract_token;
        const res = await apiPost("/sitok/facilities", {
          facility, contract: hasContract ? contract : null, ledger_token: ledgerToken, ledger_extra: ledgerExtra,
        });
        location.href = `sitok-facility.html?id=${res.id}`;
      }
    } catch (err) {
      showError(errorEl, err);
    } finally {
      btn.disabled = false;
    }
  });

  document.getElementById("sk-del").addEventListener("click", async () => {
    const pw = await askPassword(`${fac.name} — 계약·올린 PDF까지 지워지고 되돌릴 수 없습니다.`);
    if (pw == null) return;
    try {
      await api(`/sitok/facilities/${id}`, { method: "DELETE", body: JSON.stringify({ password: pw }) });
      location.href = "sitok.html";
    } catch (err) { showError(errorEl, err); }
  });

  // 삭제 비밀번호(현장 삭제와 같은 회사 공용 — 설정 탭)
  function askPassword(message) {
    return new Promise((resolve) => {
      const overlay = document.createElement("div");
      overlay.className = "mail-overlay";
      overlay.innerHTML = `<div class="mail-box" role="dialog" aria-modal="true">
        <div class="mail-head"><b>🗑 시설물 삭제</b><span class="mail-sub">${esc(message)}</span></div>
        <input type="password" class="mail-input" placeholder="삭제 비밀번호" autocomplete="off" />
        <div class="mail-note">보고서 자동화 설정 탭에서 정한 삭제 비밀번호(현장 삭제와 같음)</div>
        <div class="mail-foot"><button type="button" class="sk-cancel">취소</button><button type="button" class="mail-primary sk-ok" style="background:var(--crit);border-color:var(--crit);">삭제</button></div></div>`;
      document.body.appendChild(overlay);
      const inputEl = overlay.querySelector("input");
      const done = (v) => { overlay.remove(); resolve(v); };
      overlay.querySelector(".sk-cancel").addEventListener("click", () => done(null));
      overlay.querySelector(".sk-ok").addEventListener("click", () => (inputEl.value ? done(inputEl.value) : inputEl.focus()));
      inputEl.addEventListener("keydown", (ev) => { if (ev.key === "Enter" && inputEl.value) done(inputEl.value); if (ev.key === "Escape") done(null); });
      inputEl.focus();
    });
  }

  // PDF 칸(맨 위) — 누르기·끌어다 놓기
  document.querySelectorAll(".sk-drop[data-kind]").forEach((zone) => {
    const inputEl = zone.querySelector("input");
    inputEl.addEventListener("change", () => readPdf(zone.dataset.kind, inputEl.files[0], null));
    enableFileDrop(zone, inputEl);
  });
  // 건축물대장 PDF(10/14 — 전엔 회차 시설물 현황 창에서) → 시설물 폴더에 하나
  const regZone = document.getElementById("sk-register");
  const regInput = regZone.querySelector("input");
  regInput.addEventListener("change", async () => {
    const f = regInput.files[0];
    regInput.value = "";
    if (!f) return;
    const msg = document.getElementById("sk-register-msg");
    regZone.classList.add("busy");
    msg.textContent = `${f.name} 올리는 중…`;
    try {
      const fd = new FormData();
      fd.append("file", f);
      await apiUpload(`/sitok/facilities/${id}/register`, fd);
      fac = await api(`/sitok/facilities/${id}`);
      draw();
      flash("건축물대장을 올렸습니다.");
    } catch (e) { msg.textContent = `올리지 못했습니다: ${e.message}`; msg.classList.add("bad"); } finally { regZone.classList.remove("busy"); }
  });
  enableFileDrop(regZone, regInput);

  (async () => {
    try {
      opts = await api("/sitok/options");
      if (id) fac = await api(`/sitok/facilities/${id}`);
      // 고치기 화면의 맨 위 PDF 칸은 관리대장만(계약서는 계약 카드마다)
      document.querySelector('.sk-drop[data-kind="contract"]')?.remove(); // 고치기 화면엔 계약서 칸이 없음(계약 카드마다, 10/14)
      draw();
    } catch (err) {
      showError(errorEl, err);
    }
  })();
})();
