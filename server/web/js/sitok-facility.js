// 시특법 시설물 등록·고치기(sitok-facility.html, 2026-10-10 2단계). ?id= 없으면 새 등록(시설물 + 첫 계약을 한 번에 저장).
// PDF 칸: 관리대장 → 시설물 칸(+ 보고서 틀 추정, 관리주체 대표자는 계약 칸에), 계약서 → 계약 칸(민간/관급 구분, 비어 있는 시설물 칸도 채움).
// 민간/관급 기본값(인수인계 10/10): 민간 = 독자수행 100%·수의계약·건축. 관급 1년 계약이면 "상반기 완료일·하반기 시작일"을 직접 정함.
// 서버 server/api/routers/sitok.py, PDF 읽기 server/sitok/reader.py.

(function () {
  const errorEl = document.getElementById("error");
  const id = Number(new URLSearchParams(location.search).get("id")) || null;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let opts = null;
  let fac = null; // 저장된 시설물(고치기 화면)
  let ledgerToken = null;
  let ledgerExtra = null;
  const conTokens = {}; // 계약 카드 키 → 올린 계약서 token
  let ownerRep = ""; // 관리대장에서 읽은 관리주체 대표자(민간 계약 대표자 칸이 비면 채움)

  // [키, 이름, 종류, 도움말]
  const FAC = [
    ["name", "시설물명", "text", ""], ["fms_no", "시설물번호(FMS)", "text", "예: AR2004-0004955"],
    ["template", "보고서 틀", "template", "2종 / 3종 일반(+안전등급 평가) / 3종 학교(+치장벽돌·내진보강 점검)"],
    ["kind", "시설물 구분", "text", "결과표 — 보통 건축물"], ["use_type", "종류", "text", "결과표 — 종교시설·교육연구시설 등"],
    ["main_use", "주용도(관리대장)", "text", ""], ["address", "시설물 위치", "text", ""],
    ["owner_name", "관리주체명", "text", ""], ["owner_type", "관리주체구분", "text", "민간·공공"], ["owner_phone", "관리주체 전화", "text", ""],
    ["completion_date", "준공일", "date", ""], ["structure", "구조형식", "text", "예: 철근콘크리트구조"],
    ["floors_above", "지상 층수", "int", ""], ["floors_below", "지하 층수", "int", ""], ["floors_roof", "옥탑 층수", "int", ""],
    ["max_height", "최고높이(m)", "num", ""], ["total_area", "연면적(㎡)", "num", ""], ["building_area", "건축면적(㎡)", "num", ""],
    ["memo", "메모", "text", "보고서엔 안 나감"],
  ];
  const CON = [
    ["sector", "계약 구분", "sector", ""], ["title", "계약건명", "text", ""], ["contract_no", "계약번호", "text", "관급(나라장터)"],
    ["contract_date", "계약일", "date", ""], ["start_date", "계약기간 시작(착수일)", "date", ""], ["end_date", "계약기간 끝(완수일)", "date", ""],
    ["halves", "점검 반기", "halves", "연간 = 상·하반기 둘 다"],
    ["first_half_end", "상반기 완료일", "date", "관급 1년 계약 — 직접 정함"], ["second_half_start", "하반기 시작일", "date", "관급 1년 계약 — 직접 정함"],
    ["amount", "계약금액(원, VAT 포함)", "int", "민간은 반기 한 번 금액"], ["rep_name", "관리주체 대표자", "text", "결과표 대표자"],
    ["joint_type", "공동수급", "joint_types", ""], ["joint_pct", "지분(%)", "int", ""],
    ["bid_method", "입찰방식", "bid_methods", ""], ["field", "수행분야", "fields", ""],
  ];
  const TEMPLATE_LABEL = { "2종": "2종", "3종일반": "3종 일반", "3종학교": "3종 학교" };

  function input(prefix, [key, label, type, help]) {
    const idAttr = `${prefix}-${key}`;
    let field;
    if (type === "template" || type === "sector" || type === "halves" || type.endsWith("s")) {
      const list = { template: opts.templates, sector: opts.sectors, halves: opts.halves }[type] || opts[type];
      field = `<select id="${idAttr}" data-key="${key}">${list.map((v) => `<option value="${esc(v)}">${esc(TEMPLATE_LABEL[v] || v)}</option>`).join("")}</select>`;
    } else {
      const t = type === "date" ? "date" : type === "int" || type === "num" ? "number" : "text";
      field = `<input id="${idAttr}" data-key="${key}" data-type="${type}" type="${t}"${type === "num" ? ' step="any"' : ""} />`;
    }
    return `<div class="sk-f sk-f-${key}"><label for="${idAttr}">${esc(label)}${help ? ` <span class="sk-help">${esc(help)}</span>` : ""}</label>${field}</div>`;
  }

  function setValues(box, data, onlyEmpty) {
    for (const el of box.querySelectorAll("[data-key]")) {
      const v = data[el.dataset.key];
      if (v === undefined || v === null || v === "") continue;
      if (onlyEmpty && el.value && el.tagName !== "SELECT") continue;
      el.value = v;
      el.classList.add("sk-filled");
      setTimeout(() => el.classList.remove("sk-filled"), 2500);
    }
  }

  function values(box) {
    const out = {};
    for (const el of box.querySelectorAll("[data-key]")) {
      const v = el.value.trim();
      const t = el.dataset.type;
      out[el.dataset.key] = t === "int" ? (v === "" ? null : parseInt(v, 10)) : t === "num" ? (v === "" ? null : parseFloat(v))
        : t === "date" ? (v || null) : v;
    }
    return out;
  }

  // ---------- 계약 카드 ----------
  function conCard(c) {
    const key = c?.id ? `c${c.id}` : `new${Math.random().toString(36).slice(2, 7)}`;
    const card = document.createElement("div");
    card.className = "sk-con";
    card.dataset.key = key;
    if (c?.id) card.dataset.id = c.id;
    card.innerHTML = `<div class="sk-con-head"><b>${c?.id ? esc(c.title || "계약") : "새 계약"}</b>
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
        fac = await apiPatch(`/sitok/contracts/${c.id}`, { ...values(card), contract_token: conTokens[key] || null });
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
    const cons = document.getElementById("sk-cons");
    cons.innerHTML = "";
    if (fac) {
      document.getElementById("sk-crumb").textContent = fac.name;
      document.title = `${fac.name} - 시특법`;
      (fac.contracts || []).forEach((c) => cons.appendChild(conCard(c)));
      if (!fac.contracts?.length) cons.innerHTML = '<div class="empty-note">계약이 없습니다. [+ 계약 추가]로 넣으세요.</div>';
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
        fac = await apiPost(`/sitok/facilities/${id}/contracts`, { ...values(card), contract_token: conTokens[card.dataset.key] || null });
        flash("계약을 추가했습니다.");
        draw();
      } catch (err) { showError(errorEl, err); }
    });
    card.querySelector(".sk-con-head").appendChild(save);
    cons.prepend(card);
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
        const contract = { ...values(card), contract_token: conTokens[card.dataset.key] || null };
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
  document.querySelectorAll(".sk-drop").forEach((zone) => {
    const inputEl = zone.querySelector("input");
    inputEl.addEventListener("change", () => readPdf(zone.dataset.kind, inputEl.files[0], null));
    enableFileDrop(zone, inputEl);
  });

  (async () => {
    try {
      opts = await api("/sitok/options");
      if (id) fac = await api(`/sitok/facilities/${id}`);
      // 고치기 화면의 맨 위 PDF 칸은 관리대장만(계약서는 계약 카드마다)
      if (id) document.querySelector('.sk-drop[data-kind="contract"]').hidden = true;
      draw();
    } catch (err) {
      showError(errorEl, err);
    }
  })();
})();
