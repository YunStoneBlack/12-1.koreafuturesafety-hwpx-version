// ---------- 설정 탭 "착수계·완수계 서류"(2026-10-06 — server/api/routers/contract_library.py) ----------
// 갑지 담당 이름, 완수계 회사 서류 6장(발급일·유효기간), 착수계 기술자 명단(재직증명서 값 + 자격증·교육수료증·경력증명서 그림).
// 서류 한 줄 = 이름 · 상태(✓ ~까지 / ⚠ 기간 지남 / 없음) · [보기] 발급일 유효기간 [파일 올리기] [날짜 저장] [지우기].
// 화면 규칙은 css/contract-docs.css(.cl-*).

(function () {
  const root = document.getElementById("contract-library");
  if (!root) return;
  const err = document.getElementById("error");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let lib = null;

  async function load() {
    try {
      lib = await api("/contract-docs/library");
      document.getElementById("cl-contact").value = lib.contact_name;
      drawCompany();
      drawPersons();
      if (location.hash === "#contract-library") root.scrollIntoView({ block: "start" });
    } catch (e) {
      showError(err, e);
    }
  }

  function stateHtml(doc) {
    if (doc.status === "ok") return `<span class="cd-ok">✓ ${doc.valid_until ? `${esc(doc.valid_until)}까지` : "있음"}</span>`;
    if (doc.status === "expired") return `<span class="cd-bad">⚠ 기간 지남(${esc(doc.valid_until)})</span>`;
    return '<span class="cd-bad">없음</span>';
  }

  // 서류 한 줄. base = 올리기·지우기 주소(/contract-docs/company/{kind} | /contract-docs/persons/{id}/docs/{kind})
  function docRow(doc, base, onChanged) {
    const row = document.createElement("div");
    row.className = "cl-row";
    row.innerHTML = `
      <div class="cl-name">${esc(doc.label)}</div>
      <div class="cl-state">${stateHtml(doc)}${doc.updated_at ? `<div class="mail-note">${esc(doc.updated_at)} 올림</div>` : ""}</div>
      <div class="cl-actions">
        ${doc.id ? `<a href="${BASE}/api/contract-docs/docs/${doc.id}/image?ts=${doc.ts}" target="_blank" rel="noopener"><img class="cl-thumb" alt="${esc(doc.label)}" src="${BASE}/api/contract-docs/docs/${doc.id}/image?ts=${doc.ts}" /></a>` : ""}
        <label class="cl-date">발급일 <input type="date" class="cl-issued" value="${esc(doc.issued_on)}" /></label>
        <label class="cl-date">유효기간 <input type="date" class="cl-valid" value="${esc(doc.valid_until)}" /></label>
        <label class="cl-file">${doc.id ? "바꿔 올리기" : "파일 올리기"}<input type="file" accept="image/*,application/pdf,.pdf" hidden data-kr-file="skip" /></label>
        ${doc.id ? '<button type="button" class="secondary cl-save-dates">날짜 저장</button><button type="button" class="secondary cl-del" style="color:var(--crit);">지우기</button>' : ""}
        <span class="cl-msg mail-note"></span>
      </div>`;
    const msg = row.querySelector(".cl-msg");
    const dates = () => ({ issued_on: row.querySelector(".cl-issued").value, valid_until: row.querySelector(".cl-valid").value });
    row.querySelector("input[type=file]").addEventListener("change", async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      msg.textContent = "올리는 중…";
      try {
        const fd = new FormData();
        fd.append("file", file);
        const d = dates();
        fd.append("issued_on", d.issued_on);
        fd.append("valid_until", d.valid_until);
        await apiUpload(base, fd);
        onChanged();
      } catch (e2) {
        msg.textContent = e2.message;
        msg.classList.add("cd-bad");
        e.target.value = "";
      }
    });
    row.querySelector(".cl-save-dates")?.addEventListener("click", async () => {
      try {
        await apiPatch(`/contract-docs/docs/${doc.id}`, dates());
        onChanged();
      } catch (e2) {
        msg.textContent = e2.message;
        msg.classList.add("cd-bad");
      }
    });
    row.querySelector(".cl-del")?.addEventListener("click", async () => {
      if (!confirm(`${doc.label}를 지울까요?`)) return;
      try {
        await api(base, { method: "DELETE" });
        onChanged();
      } catch (e2) {
        showError(err, e2);
      }
    });
    return row;
  }

  function drawCompany() {
    const box = document.getElementById("cl-company");
    box.innerHTML = "";
    for (const doc of lib.company_docs) box.appendChild(docRow(doc, `/contract-docs/company/${doc.kind}`, load));
  }

  const PERSON_FIELDS = [
    ["name", "이름", "text"], ["position", "직책", "text"], ["birth_date", "생년월일", "date"], ["join_date", "입사일(재직증명서)", "date"],
    ["grade", "기술등급", "text"], ["address", "주소", "text"],
  ];

  function personCard(p) {
    const card = document.createElement("div");
    card.className = `cl-person${p.active === false ? " inactive" : ""}`;
    card.innerHTML = `
      <div class="cl-person-head"><b>${esc(p.name || "새 기술자")}</b>${p.active === false ? '<span class="status-pill rejected">안 씀</span>' : ""}</div>
      <div class="field-grid">
        ${PERSON_FIELDS.map(([k, label, type]) => `<div${k === "address" ? ' style="grid-column:1/-1;"' : ""}><label>${label}</label><input class="cl-p" data-key="${k}" type="${type}" value="${esc(p[k] ?? "")}" ${k === "grade" ? 'placeholder="예: 특급기술자"' : ""} /></div>`).join("")}
        <div style="grid-column:1/-1;"><label>기술자격 <span style="font-weight:400;color:var(--muted);">(여러 개면 줄바꿈)</span></label><textarea class="cl-p" data-key="qualification">${esc(p.qualification ?? "")}</textarea></div>
      </div>
      <div class="cl-foot">
        <button type="button" class="cl-psave">저장</button>
        ${p.id ? `<button type="button" class="secondary cl-ptoggle">${p.active === false ? "다시 쓰기" : "안 씀(목록에서 숨김)"}</button>
        <button type="button" class="secondary cl-pdel" style="color:var(--crit);">삭제</button>` : '<button type="button" class="secondary cl-pcancel">취소</button>'}
        <span class="cl-pmsg status" style="margin:0;"></span>
      </div>`;
    if (p.id) {
      const table = document.createElement("div");
      table.className = "cl-table";
      for (const doc of p.docs) table.appendChild(docRow(doc, `/contract-docs/persons/${p.id}/docs/${doc.kind}`, load));
      card.appendChild(table);
    }
    const msg = card.querySelector(".cl-pmsg");
    card.querySelector(".cl-psave").addEventListener("click", async () => {
      const body = {};
      card.querySelectorAll(".cl-p").forEach((el) => { body[el.dataset.key] = el.value; });
      try {
        if (p.id) await apiPatch(`/contract-docs/persons/${p.id}`, body);
        else await apiPost("/contract-docs/persons", body);
        load();
      } catch (e) {
        msg.textContent = e.message;
        msg.className = "cl-pmsg status bad";
      }
    });
    card.querySelector(".cl-pcancel")?.addEventListener("click", () => card.remove());
    card.querySelector(".cl-ptoggle")?.addEventListener("click", async () => {
      await apiPatch(`/contract-docs/persons/${p.id}`, { active: p.active === false }).catch((e) => showError(err, e));
      load();
    });
    card.querySelector(".cl-pdel")?.addEventListener("click", async () => {
      if (!confirm(`${p.name} 님과 올린 서류를 모두 지울까요? (그만둔 사람이면 "안 씀"도 됩니다)`)) return;
      await api(`/contract-docs/persons/${p.id}`, { method: "DELETE" }).catch((e) => showError(err, e));
      load();
    });
    return card;
  }

  function drawPersons() {
    const box = document.getElementById("cl-persons");
    box.innerHTML = lib.persons.length ? "" : '<div class="empty-note" style="margin-bottom:10px;">아직 기술자가 없습니다.</div>';
    for (const p of lib.persons) box.appendChild(personCard(p));
  }

  document.getElementById("cl-person-add").addEventListener("click", () => {
    const card = personCard({ name: "", docs: [] });
    document.getElementById("cl-persons").appendChild(card);
    card.querySelector('[data-key="name"]').focus();
  });

  document.getElementById("cl-contact-save").addEventListener("click", async () => {
    const msg = document.getElementById("cl-contact-msg");
    try {
      const out = await api("/contract-docs/contact", { method: "PUT", body: JSON.stringify({ name: document.getElementById("cl-contact").value }) });
      document.getElementById("cl-contact").value = out.contact_name;
      msg.textContent = "✓ 저장했습니다";
      msg.className = "status ok";
    } catch (e) {
      msg.textContent = e.message;
      msg.className = "status bad";
    }
  });

  load();
})();
