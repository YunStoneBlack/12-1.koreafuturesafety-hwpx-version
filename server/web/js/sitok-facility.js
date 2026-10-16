// 시특법 시설물 등록·고치기(sitok-facility.html, 2026-10-10 2단계). ?id= 없으면 새 등록 화면(sitok-new.html, 10/12 — 서류 한 번에)으로 감.
// 10/14 형 피드백 ⑦ 3층 구조: 이 파일은 접힌 "시설물 정보·서류"(관리대장·건축물대장·도면·시설물 칸)와 "계약"(카드마다 쓰는 회차) 칸. 회차 목록은 js/sitok-reports.js.
// 10/16 형 개편 2차: 동 타일(누르면 그 동, 보는 동을 다시 누르면 시설물 칸 팝업 — 🗑 이 동 삭제), [＋ 동 추가]·[🗑 휴지통](끌어다 놓기·누르면 보는 동),
// 고른 동 서류·도면 칸, 관리대장 [다시 올리기](이 동 칸만 새 관리대장 값으로). 묶음의 동을 지우면 계약은 다음 동이 넘겨받음(server sitok._pass_contracts).
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

  function flash(msg, bad) { // 팝업이 열려 있으면 팝업 아래, 아니면 화면 아래 잠깐(시설물 칸이 팝업으로 감, 10/16)
    if (!document.getElementById("fi-modal").hidden) {
      const el = document.getElementById("sk-saved");
      el.textContent = msg;
      el.classList.toggle("bad", !!bad);
      setTimeout(() => { el.textContent = ""; el.classList.remove("bad"); }, bad ? 8000 : 3000);
      return;
    }
    const t = document.createElement("div");
    t.className = "fi-toast";
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 3000);
  }

  // ---------- 시설물 칸 팝업·동 타일·삭제(10/16 형) ----------
  const modal = document.getElementById("fi-modal");
  const openModal = () => { modal.hidden = false; modal.querySelector("input")?.focus(); };
  const closeModal = () => { modal.hidden = true; };
  document.getElementById("fi-close").addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => { if (e.target === modal) closeModal(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !modal.hidden && !document.querySelector(".mail-overlay:not(#fi-modal)")) closeModal(); });
  const group = () => (fac.group && fac.group.members.length > 1 ? fac.group : null);
  const registered = () => !!(fac.has_ledger_pdf || fac.fms_no || fac.legal === false || group() || (fac.card_units || []).length > 1); // js/sitok-register.js와 같음
  const label = (m) => { const g = group(); const i = g ? g.members.findIndex((x) => x.id === m.id) : -1; return `${i >= 0 ? `제${i + 1}장 ` : ""}${m.name}`; };

  function drawTiles() {
    const g = group();
    const members = g ? g.members.map((m) => (m.id === fac.id ? { ...m, name: fac.name } : m)) : [{ id: fac.id, name: fac.name }];
    const reg = registered();
    const pick = document.getElementById("sk-dong-pick");
    pick.innerHTML = members.map((m, i) => {
      const on = m.id === fac.id;
      const inner = `<small><span>${g ? `제${i + 1}장` : "건물"}${on ? '<i class="fi-on-t"> · 보는 중</i>' : ""}</span>${on ? '<em class="fi-edit">✎ 시설물 칸</em>' : ""}</small><b>${esc(m.name)}</b>`;
      return on ? `<button type="button" class="fi-tile on" data-id="${m.id}" draggable="true" aria-current="page" title="시설물 칸 보기·고치기">${inner}</button>`
        : `<a class="fi-tile" data-id="${m.id}" href="sitok-facility.html?id=${m.id}#info" title="${esc(m.name)}">${inner}</a>`;
    }).join("") + (reg ? `<button type="button" class="fi-tile fi-add" id="fi-add">＋ 동 추가</button>
      <div class="fi-tile fi-trash" id="fi-trash" role="button" tabindex="0" title="보는 동 지우기 — PC는 동을 끌어다 놓아도 됨"><b>🗑 휴지통</b><small>동을 끌어다 놓으면 삭제</small></div>` : "");
    pick.querySelector(".fi-tile.on").addEventListener("click", openModal);
    pick.querySelectorAll(".fi-tile[data-id]").forEach((t) => {
      t.addEventListener("dragstart", (e) => { e.dataTransfer.setData("text/plain", t.dataset.id); e.dataTransfer.effectAllowed = "move"; t.classList.add("drag"); });
      t.addEventListener("dragend", () => t.classList.remove("drag"));
    });
    document.getElementById("fi-add")?.addEventListener("click", () => window.dispatchEvent(new Event("sitok-reg-open")));
    const trash = document.getElementById("fi-trash");
    if (trash) {
      trash.addEventListener("dragover", (e) => { e.preventDefault(); trash.classList.add("over"); });
      trash.addEventListener("dragleave", () => trash.classList.remove("over"));
      trash.addEventListener("drop", (e) => { e.preventDefault(); trash.classList.remove("over"); const tid = Number(e.dataTransfer.getData("text/plain")); if (tid) removeDong(tid); });
      trash.addEventListener("click", () => removeDong(fac.id));
      trash.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); removeDong(fac.id); } });
    }
    document.getElementById("fi-dongs-t").textContent = g ? "동 고르기" : "건물";
    document.getElementById("fi-dongs-s").textContent = g ? "동을 누르면 아래 서류·도면이 그 동 것으로 바뀌고, 보는 동을 한 번 더 누르면 시설물 칸" : "누르면 시설물 칸(이름·주소·관리주체 등)이 열립니다";
    document.getElementById("fi-compose-link").hidden = !g;
    document.getElementById("fi-cur").textContent = label({ id: fac.id, name: fac.name });
    document.getElementById("fi-box-t").textContent = `📝 ${label({ id: fac.id, name: fac.name })} — 시설물 칸`;
    document.getElementById("sk-del").textContent = g ? "🗑 이 동 삭제" : "🗑 시설물 삭제";
  }

  async function removeDong(tid) { // 휴지통·팝업 [🗑 이 동 삭제] — 묶음이면 계약은 다음 동이 넘겨받음(서버)
    const g = group();
    const members = g ? g.members : [{ id: fac.id, name: fac.name }];
    const m = members.find((x) => x.id === tid) || { id: tid, name: fac.name };
    const rest = members.filter((x) => x.id !== tid);
    const name = tid === fac.id ? label({ id: fac.id, name: fac.name }) : label(m);
    const text = g && rest.length
      ? `${name} — 이 동의 회차·현장 조사·올린 PDF·만든 보고서가 지워지고 되돌릴 수 없습니다. ${members[0].id === tid ? `묶음 계약은 지우지 않고 다음 동(${rest[0].name})이 넘겨받습니다.` : `묶음 계약은 그대로입니다(제1장 ${members[0].name}).`}`
      : `${name} — 계약·회차·결함·올린 PDF·만든 보고서, 서류 자동화의 이 카드 계약까지 지워지고 되돌릴 수 없습니다.`;
    const pw = await askPassword(text, `🗑 ${name} 삭제`);
    if (pw == null) return;
    try {
      await api(`/sitok/facilities/${tid}`, { method: "DELETE", body: JSON.stringify({ password: pw }) });
      if (tid !== fac.id) { location.reload(); return; }
      location.href = rest.length ? `sitok-facility.html?id=${rest[0].id}#info` : "sitok.html";
    } catch (err) {
      if (!modal.hidden) flash(err.message, true); else showError(errorEl, err);
    }
  }

  function drawLedgerCard() { // 관리대장 카드 — [다시 올리기]: 동은 맞는데 파일을 잘못 올렸을 때 이 동 칸만 새 값으로(10/16 형 "잘못 올릴 수도 있잖아")
    const card = document.getElementById("sk-ledger-card");
    card.hidden = !registered() || fac.legal === false;
    if (card.hidden) return;
    card.className = `fi-card${fac.has_ledger_pdf ? " has" : ""}`;
    card.innerHTML = `<div class="fi-card-h"><b>📄 시설물관리대장</b><label class="fi-btn-o">${fac.has_ledger_pdf ? "다시 올리기" : "＋ 올리기"}<input type="file" accept=".pdf,.hwp,.hwpx,.jpg,.jpeg,.png,application/pdf,image/*" hidden data-kr-file="skip" /></label></div>
      <span class="sk-help fi-led-msg">잘못 올렸으면 다시 올리기 — 이 동의 칸만 새 관리대장 값으로(회차·현장 조사는 그대로)</span>
      ${fac.has_ledger_pdf ? `<span class="fi-st ok">✓ 올려 둠 · <a href="${BASE}/api/sitok/files/ledger/${fac.id}" target="_blank" rel="noopener">보기</a></span>` : '<span class="fi-st">아직 없음</span>'}`;
    const inp = card.querySelector("input");
    inp.addEventListener("change", () => { const f = inp.files[0]; inp.value = ""; if (f) reLedger(f, card); });
    enableFileDrop(card, inp);
  }

  async function reLedger(file, card) {
    const msg = card.querySelector(".fi-led-msg");
    const norm = (v) => String(v || "").replace(/[^0-9A-Za-z]/g, "").toUpperCase();
    card.classList.add("busy");
    msg.classList.remove("bad");
    msg.textContent = `${file.name} 읽는 중…(10~30초)`;
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await apiUpload(`/sitok/docs/facilities/${id}/add/read`, fd);
      const items = r.items || [r];
      if (items.length > 1) throw new Error(`건물 ${items.length}개가 든 관리대장입니다 — 이 동 것 한 장만 올리세요(다른 동은 [＋ 동 추가])`);
      const x = items[0];
      if (x.error || !x.token) throw new Error(x.error || "관리대장을 읽지 못했습니다");
      const fields = { ...(x.fields || {}) };
      delete fields.ledger;
      const other = (fac.card_fms || []).find((c) => c.id !== fac.id && norm(c.fms_no) && norm(c.fms_no) === norm(fields.fms_no));
      if (other) throw new Error(`이미 있는 ${other.mgmt_no} ${other.name}의 관리대장입니다(시설물번호 ${fields.fms_no}) — 그 동에서 올리세요`);
      const name = String(fields.name || fac.name).trim();
      if (!confirm(`읽었습니다: ${name}${fields.fms_no ? `(${fields.fms_no})` : ""} — 이 동(${fac.name})의 칸을 새 관리대장 값으로 바꿀까요? 이름도 "${name}"(으)로 바뀝니다. 회차·현장 조사는 그대로입니다.`)) {
        msg.textContent = "바꾸지 않았습니다.";
        return;
      }
      const keep = Object.fromEntries(Object.entries(fields).filter(([, v]) => v !== undefined && v !== null && v !== ""));
      fac = await apiPatch(`/sitok/facilities/${id}?ledger_token=${encodeURIComponent(x.token)}`, { ...keep, name, legal: true });
      draw();
      flash("관리대장을 바꿨습니다 — 이 동 칸을 새 값으로 채웠습니다.");
    } catch (err) {
      msg.textContent = `바꾸지 못했습니다: ${err.message}`;
      msg.classList.add("bad");
    } finally {
      card.classList.remove("busy");
    }
  }

  // ---------- 그리기 ----------
  function draw() {
    const facBox = document.getElementById("sk-fac");
    facBox.innerHTML = `<div class="field-grid">${FAC.map((f) => input("f", f)).join("")}</div>`; // 관리대장 보기·다시 올리기는 서류·도면의 관리대장 카드(10/16)
    if (fac) setValues(facBox, fac);
    facBox.querySelectorAll(".sk-filled").forEach((el) => el.classList.remove("sk-filled"));
    SitokFields.linkLegal(facBox);
    const cons = document.getElementById("sk-cons");
    cons.innerHTML = "";
    if (fac) {
      document.getElementById("sk-crumb").textContent = fac.name;
      document.title = `${fac.name} - 시특법`;
      const g = group(); // 묶음 — 동 타일로 고르기(민재형 10/15 "생성한 시설물 누르면 안에 업로드", 10/16 타일·팝업)
      drawTiles();
      drawLedgerCard();
      if (g) {
        document.getElementById("sk-crumb").textContent = `${g.name} › ${fac.name}`;
        if (location.hash === "#info") { // 다른 동에서 넘어옴 — 서류 칸을 열어 둠
          const panel = document.getElementById("sk-info-panel");
          panel.open = true;
          setTimeout(() => panel.scrollIntoView({ block: "start" }), 50);
        }
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
      if (!modal.hidden) flash(err.message, true); else showError(errorEl, err);
    } finally {
      btn.disabled = false;
    }
  });

  document.getElementById("sk-del").addEventListener("click", () => removeDong(fac.id));

  // 삭제 비밀번호(현장 삭제와 같은 회사 공용 — 설정 탭)
  function askPassword(message, title = "🗑 시설물 삭제") {
    return new Promise((resolve) => {
      const overlay = document.createElement("div");
      overlay.className = "mail-overlay";
      overlay.innerHTML = `<div class="mail-box" role="dialog" aria-modal="true">
        <div class="mail-head"><b>${esc(title)}</b><span class="mail-sub">${esc(message)}</span></div>
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
      window.dispatchEvent(new CustomEvent("sitok-facility-loaded", { detail: fac }));
    } catch (err) {
      showError(errorEl, err);
    }
  })();
})();
