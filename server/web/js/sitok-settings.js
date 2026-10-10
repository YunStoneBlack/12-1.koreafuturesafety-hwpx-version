// 시특법 설정(sitok-settings.html, 2026-10-10 3단계) — 회사 서류(등록증)·기술자 시특법 칸과 서류(수료증·책임기술자 자격)·사용 장비.
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
    const state = !d.id ? '<span class="ss-st none">없음</span>'
      : d.status === "expired" ? `<span class="ss-st bad">유효기간 지남(${esc(d.valid_until)})</span>`
        : `<span class="ss-st ok">✓ 올림${d.updated_at ? ` · ${esc(d.updated_at)}` : ""}</span>`;
    row.innerHTML = `<b>${esc(d.label)}</b>${state}
      <label class="ss-valid">유효기간 <input type="date" value="${esc(d.valid_until)}"${d.id ? "" : " disabled"} /></label>
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
    row.querySelector(".ss-valid input").addEventListener("change", async (e) => {
      try { await apiPatch(`/contract-docs/docs/${d.id}`, { issued_on: d.issued_on || "", valid_until: e.target.value }); onChanged(); } catch (x) { err(x); }
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

  document.getElementById("ss-add-eq").addEventListener("click", async () => {
    try { await apiPost("/sitok/settings/equipment", { grp: "보조기구", name: "새 장비" }); await load(); } catch (x) { err(x); }
  });

  async function load() {
    try {
      data = await api("/sitok/settings");
      drawCompany();
      drawPersons();
      drawEquip();
    } catch (e) { err(e); }
  }
  load();
})();
