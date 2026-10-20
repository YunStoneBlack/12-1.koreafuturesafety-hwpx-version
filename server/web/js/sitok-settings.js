// 시특법 설정(2026-10-10 3단계 — 10/20부터 보고서 자동화 설정 settings.html의 [시특법] 쪽) — 회사 서류(등록증)·기술자 시특법 칸과 서류(수료증·책임기술자 자격)·사용 장비.
// 서버 server/api/routers/sitok_settings.py. 서류 유효기간 고치기는 서류 자동화와 같은 PATCH /contract-docs/docs/{id}.

(function () {
  const errorEl = document.getElementById("error");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const err = (e) => showError(errorEl, e);
  let data = null;

  // 서류 한 줄: 이름 | 상태 | 유효기간 | [보기] [올리기] [지우기]
  function docRow(d, uploadPath, deletePath, onChanged) {
    const row = document.createElement("div");
    row.className = "ss-doc";
    // 유효기간은 수료증만(수료일 + 5년, 민재형 10/10) — 서버 contract_library.VALID_RULES. 나머지는 날짜 칸 없음
    const state = !d.id ? '<span class="ss-st none">없음</span>'
      : d.status === "expired" ? `<span class="ss-st bad">⚠ 유효기간 지남(${esc(d.valid_until)}) — 새로 받아 바꿔 올리세요</span>`
        : d.status === "nodate" ? '<span class="ss-st bad">⚠ 수료일을 적어 주세요</span>'
          : `<span class="ss-st ok">✓ 올림${d.valid_until ? ` · 유효기간 ~${esc(d.valid_until)}` : ""}</span>`;
    row.innerHTML = `<b>${esc(d.label)}</b>${state}
      ${d.dated ? `<label class="ss-valid">수료일 <input type="date" value="${esc(d.issued_on)}"${d.id ? "" : " disabled"} /></label>` : "<span></span>"}
      <span class="ss-acts">${d.id ? `<a class="secondary-link" href="${BASE}/api/contract-docs/docs/${d.id}/image?t=${d.ts}" target="_blank" rel="noopener">보기</a>` : ""}
        <label class="secondary-link">${d.id ? "바꾸기" : "올리기"}<input type="file" accept="image/*,application/pdf,.pdf" hidden data-kr-file="1" /></label>
        ${d.id ? '<button type="button" class="secondary btn-sm ss-del">지우기</button>' : ""}</span>`;
    const file = row.querySelector('input[type="file"]');
    file.addEventListener("change", async () => {
      if (!file.files[0]) return;
      row.classList.add("busy");
      try {
        const fd = new FormData();
        fd.append("file", file.files[0]);
        await apiUpload(uploadPath, fd);
        onChanged();
      } catch (e) { err(e); row.classList.remove("busy"); }
    });
    enableFileDrop(row, file);
    row.querySelector(".ss-valid input")?.addEventListener("change", async (e) => {
      try { await apiPatch(`/contract-docs/docs/${d.id}`, { issued_on: e.target.value, valid_until: "" }); onChanged(); } catch (x) { err(x); }
    });
    row.querySelector(".ss-del")?.addEventListener("click", async () => {
      if (!confirm(`${d.label}을(를) 지울까요?`)) return;
      try { await api(deletePath, { method: "DELETE" }); onChanged(); } catch (x) { err(x); }
    });
    return row;
  }

  function drawCompany() {
    const box = document.getElementById("ss-company");
    box.innerHTML = "";
    data.company_docs.forEach((d) => box.appendChild(docRow(d, `/sitok/settings/company/${d.kind}`, `/sitok/settings/company/${d.kind}`, load)));
  }

  function drawPersons() {
    const box = document.getElementById("ss-persons");
    box.innerHTML = data.persons.length ? "" : '<div class="empty-note">기술자가 없습니다. <a href="docs-settings.html">서류 자동화 설정</a>에서 추가하세요.</div>';
    for (const p of data.persons.filter((x) => x.active)) {
      const card = document.createElement("div");
      card.className = "ss-person";
      card.innerHTML = `<div class="ss-person-head"><b>${esc(p.name)}</b><span>${esc([p.position, p.grade].filter(Boolean).join(" · "))}</span></div>
        <div class="ss-person-fields">
          <label>분야 <input data-k="sitok_field" value="${esc(p.sitok_field)}" placeholder="건축" /></label>
          <label>결과표 기술등급 <input data-k="sitok_grade" value="${esc(p.sitok_grade)}" placeholder="예: 건축분야특급기술자" /></label>
        </div><div class="ss-person-docs"></div>`;
      card.querySelectorAll("[data-k]").forEach((inp) => inp.addEventListener("change", async () => {
        try { await apiPatch(`/sitok/settings/persons/${p.id}`, { [inp.dataset.k]: inp.value }); flash(inp); } catch (x) { err(x); }
      }));
      const docs = card.querySelector(".ss-person-docs");
      p.docs.forEach((d) => docs.appendChild(docRow(d, `/sitok/settings/persons/${p.id}/docs/${d.kind}`, `/sitok/settings/persons/${p.id}/docs/${d.kind}`, load)));
      box.appendChild(card);
    }
  }

  function flash(el) {
    el.classList.add("sk-filled");
    setTimeout(() => el.classList.remove("sk-filled"), 1200);
  }

  function drawEquip() {
    const box = document.getElementById("ss-equip");
    box.innerHTML = `<div class="ss-eq ss-eq-head"><span>구분</span><span>장비명</span><span>형식</span><span>용도</span><span>사진</span><span></span></div>`;
    for (const e of data.equipment) {
      const row = document.createElement("div");
      row.className = "ss-eq";
      const thumbs = Array.from({ length: e.photos }, (_, n) => `<img src="${BASE}/api/sitok/settings/equipment/${e.id}/photo/${n}?t=${e.ts}" alt="" />`).join("");
      row.innerHTML = `<input data-k="grp" value="${esc(e.grp)}" aria-label="구분" /><input data-k="name" value="${esc(e.name)}" aria-label="장비명" />
        <input data-k="model" value="${esc(e.model)}" aria-label="형식" /><input data-k="purpose" value="${esc(e.purpose)}" aria-label="용도" />
        <label class="ss-thumbs" title="눌러서 사진 바꾸기(끌어다 놓기도 됨)">${thumbs || '<span class="ss-nophoto">사진</span>'}<input type="file" accept="image/*" hidden data-kr-file="1" /></label>
        <button type="button" class="secondary btn-sm ss-del" title="삭제">✕</button>`;
      row.querySelectorAll("[data-k]").forEach((inp) => inp.addEventListener("change", async () => {
        try { await apiPatch(`/sitok/settings/equipment/${e.id}`, { [inp.dataset.k]: inp.value }); flash(inp); } catch (x) { err(x); }
      }));
      const file = row.querySelector('input[type="file"]');
      file.addEventListener("change", async () => {
        if (!file.files[0]) return;
        const fd = new FormData();
        fd.append("file", file.files[0]);
        fd.append("replace", "true");
        try { await apiUpload(`/sitok/settings/equipment/${e.id}/photo`, fd); load(); } catch (x) { err(x); }
      });
      enableFileDrop(row.querySelector(".ss-thumbs"), file);
      row.querySelector(".ss-del").addEventListener("click", async () => {
        if (!confirm(`${e.name || "이 장비"}를 지울까요?`)) return;
        try { await api(`/sitok/settings/equipment/${e.id}`, { method: "DELETE" }); load(); } catch (x) { err(x); }
      });
      box.appendChild(row);
    }
  }

  function drawPrices() {
    const box = document.getElementById("ss-prices");
    box.innerHTML = `<div class="ss-pr ss-eq-head"><span>공법</span><span>단위</span><span>단가(원)</span><span>출처</span><span>비고</span><span></span></div>`;
    for (const p of data.prices) {
      const row = document.createElement("div");
      row.className = `ss-pr${/확인 필요/.test(p.note) ? " check" : ""}`;
      row.innerHTML = `<input data-k="method" value="${esc(p.method)}" aria-label="공법" /><input data-k="unit" value="${esc(p.unit)}" aria-label="단위" />
        <input data-k="price" type="number" min="0" value="${p.price ?? ""}" aria-label="단가" /><input data-k="source" value="${esc(p.source)}" aria-label="출처" title="${esc(p.source)}" />
        <input data-k="note" value="${esc(p.note)}" aria-label="비고" /><button type="button" class="secondary btn-sm ss-del" title="삭제">✕</button>`;
      row.querySelectorAll("[data-k]").forEach((inp) => inp.addEventListener("change", async () => {
        const k = inp.dataset.k;
        try { await apiPatch(`/sitok/settings/prices/${p.id}`, { [k]: k === "price" ? (inp.value === "" ? null : Number(inp.value)) : inp.value }); flash(inp); }
        catch (x) { err(x); }
      }));
      row.querySelector(".ss-del").addEventListener("click", async () => {
        if (!confirm(`${p.method || "이 공법"} 단가를 지울까요?`)) return;
        try { await api(`/sitok/settings/prices/${p.id}`, { method: "DELETE" }); load(); } catch (x) { err(x); }
      });
      box.appendChild(row);
    }
  }

  function drawMaster() { // 회사 원본 템플릿(10/12) — 받기·고친 한글 올리기(서버가 채우는 자리 검사). 10/13 정밀은 본문·부록 두 파일
    const box = document.getElementById("ss-master");
    const all = data.master || {};
    const KINDS = [["정기", "정기안전점검 원본", "한 파일(본문 + 부록)"], ["정밀본문", "정밀안전점검 본문 원본", "결과표 + 시설물편 1~7장"],
      ["정밀부록", "정밀안전점검 부록 원본", "관리대장·성과표·상태평가 결과 자료"]];
    box.innerHTML = KINDS.map(([k, label, note]) => {
      const m = all[k] || {};
      return `<div class="ss-master" data-kind="${k}"><b>${label}</b><span class="sk-help">${note}</span>
        ${m.exists ? `<span class="ss-st ok">✓ ${esc(m.updated)} 바꿈 · ${m.size_mb}MB</span>` : '<span class="ss-st none">없음</span>'}
        <span class="ss-acts">${m.exists ? `<a class="secondary-link" href="${BASE}/api/sitok/settings/master/file?kind=${encodeURIComponent(k)}">한글 받기</a>` : ""}
          <label class="secondary-link">${m.exists ? "고친 한글 올리기" : "원본 올리기"}<input type="file" accept=".hwp,.hwpx" hidden data-kr-file="1" /></label></span>
        <span class="ss-master-msg"></span></div>`;
    }).join("");
    box.querySelectorAll(".ss-master").forEach((row) => {
      const k = row.dataset.kind;
      const file = row.querySelector("input[type=file]");
      const msg = row.querySelector(".ss-master-msg");
      file.addEventListener("change", async () => {
        if (!file.files[0]) return;
        if (!confirm(`${file.files[0].name}을(를) 새 ${KINDS.find((x) => x[0] === k)[1]}으로 할까요? 앞으로 만드는 보고서가 이 원본을 씁니다(지금 원본은 보관).`)) { file.value = ""; return; }
        msg.textContent = "올리는 중…(한글 .hwp는 바꾸느라 10~30초, 그림 많은 정밀 원본은 1~2분)";
        try {
          const fd = new FormData();
          fd.append("file", file.files[0]);
          fd.append("kind", k);
          data.master = await apiUpload("/sitok/settings/master", fd);
          drawMaster();
          box.querySelector(`.ss-master[data-kind="${k}"] .ss-master-msg`).textContent = "새 원본으로 바꿨습니다.";
        } catch (x) { msg.textContent = x.message; file.value = ""; }
      });
      enableFileDrop(row, file);
    });
  }

  function drawVocab() { // 결함 부재·결함유형 회사 목록(10/12) — 칩 ✕로 빼기, 칸에 써서 추가
    const box = document.getElementById("ss-vocab");
    box.innerHTML = "";
    for (const [kind, label] of [["member", "부재"], ["dtype", "결함유형"]]) {
      const row = document.createElement("div");
      row.className = "ss-voc";
      row.innerHTML = `<b>${label}</b><div class="ss-chips">${((data.vocab || {})[kind] || []).map((v) =>
        `<span class="ss-chip">${esc(v.name)}<button type="button" data-id="${v.id}" data-n="${esc(v.name)}" title="목록에서 빼기">✕</button></span>`).join("")}
        <span class="ss-chip-add"><input placeholder="+ ${label} 추가" maxlength="20" aria-label="${label} 추가" /><button type="button" class="secondary btn-sm">추가</button></span></div>`;
      row.querySelectorAll(".ss-chip button").forEach((b) => b.addEventListener("click", async () => {
        if (!confirm(`"${b.dataset.n}"을(를) 목록에서 뺄까요? 이미 적은 결함은 그대로입니다.`)) return;
        try { data.vocab = await api(`/sitok/settings/vocab/${b.dataset.id}`, { method: "DELETE" }); drawVocab(); } catch (x) { err(x); }
      }));
      const inp = row.querySelector(".ss-chip-add input");
      const add = async () => {
        if (!inp.value.trim()) return;
        try { data.vocab = await apiPost("/sitok/settings/vocab", { kind, name: inp.value }); drawVocab(); } catch (x) { err(x); }
      };
      row.querySelector(".ss-chip-add button").addEventListener("click", add);
      inp.addEventListener("keydown", (e) => { if (e.key === "Enter") add(); });
      box.appendChild(row);
    }
  }

  document.getElementById("ss-add-price").addEventListener("click", async () => {
    try { await apiPost("/sitok/settings/prices", { method: "새 공법", unit: "m" }); await load(); } catch (x) { err(x); }
  });

  document.getElementById("ss-add-eq").addEventListener("click", async () => {
    try { await apiPost("/sitok/settings/equipment", { grp: "보조기구", name: "새 장비" }); await load(); } catch (x) { err(x); }
  });

  async function load() {
    try {
      data = await api("/sitok/settings");
      drawCompany();
      drawPersons();
      drawEquip();
      drawMaster();
      drawVocab();
      drawPrices();
    } catch (e) { err(e); }
  }
  load();
})();
