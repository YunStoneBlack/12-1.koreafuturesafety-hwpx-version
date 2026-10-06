// ---------- 서류 자동화 — 계약 목록(docs.html, 2026-10-06) ----------
// 위: 검색 + [+ 새 계약](빈 착수계 창 — 계약서 PDF를 놓거나 올리거나 직접 적기). 화면에 계약서 PDF를 끌어다 놓으면 바로 읽어서 새 계약. 단계 칸(전체·착수계 전·착수계 제출·완수계 제출)을 누르면 거름.
// 한 줄: 용역명 · 발주처·계약번호·금액·기간 · 현장(연결/연결 안 됨 [🔗 연결]) · 착수계·완수계 상태 · [📑 착수계][📑 완수계][삭제].

(function () {
  const errorEl = document.getElementById("error");
  const view = { stage: "", q: "" };
  let data = { contracts: [], stages: [] };

  async function load() {
    try {
      data = await dcLoad();
      render();
    } catch (err) {
      showError(errorEl, err);
    }
  }

  function render() {
    const all = data.contracts;
    const cards = [["", "전체", all.length, "등록된 용역 계약"]].concat(
      data.stages.map(([key, label]) => [key, label, all.filter((c) => c.stage === key).length,
        { before: "착수계 아직 안 만듦", started: "현장 진행 중", finished: "끝" }[key]]));
    const cardsEl = document.getElementById("dc-cards");
    cardsEl.innerHTML = cards.map(([key, label, n, sub]) => `<button type="button" class="st-card${view.stage === key ? " active" : ""}" data-stage="${key}">
      <span class="l">${label}</span><span class="n">${n}건</span><span class="s">${sub}</span></button>`).join("");
    cardsEl.querySelectorAll(".st-card").forEach((b) => b.addEventListener("click", () => { view.stage = b.dataset.stage; render(); }));

    const words = view.q.toLowerCase().split(/\s+/).filter(Boolean);
    const shown = all.filter((c) => (!view.stage || c.stage === view.stage) && words.every((w) => dcSearchText(c).includes(w)));
    document.getElementById("dc-count").textContent = `${shown.length}건`;
    const list = document.getElementById("dc-list");
    if (!shown.length) {
      list.innerHTML = `<div class="empty-note">${all.length ? "맞는 계약이 없습니다." : "아직 용역 계약이 없습니다 — 위 점선 상자에 계약서 PDF를 끌어다 놓거나 [+ 새 계약]으로 시작하세요."}</div>`;
      return;
    }
    list.innerHTML = "";
    for (const c of shown) list.appendChild(row(c));
  }

  // 발주처 담당자 한 줄 — "계약 담당 오성혜 · 메일 [📞]"(형 10/6: 계약·사업 담당 모두)
  function contactLine(c, who, label) {
    const name = c[`${who}_manager`], phone = c[`${who}_phone`], mail = c[`${who}_email`];
    if (!name && !phone && !mail) return "";
    return `<div class="dc-meta dc-contact" data-who="${who}">${label} <b>${mailEsc(name || "-")}</b>${mail ? ` · <a href="mailto:${mailEsc(mail)}">${mailEsc(mail)}</a>` : ""}</div>`;
  }

  function row(c) {
    const el = document.createElement("div");
    el.className = "row dc-row";
    const meta = [c.client, c.contract_no, dcMoney(c.amount), c.start_date && `${c.start_date} ~ ${c.end_date || ""}`].filter(Boolean).join(" · ");
    const docs = DC_KINDS.map(([k, label]) => {
      const s = dcDocState(c, k);
      return `<span class="dc-doc ${s.cls}"><b>${label}</b> ${mailEsc(s.text)}</span>`;
    }).join("");
    el.innerHTML = `
      <div class="dc-main">
        <div class="dc-title">${mailEsc(c.title ? c.label : "(용역명 없음 — 계약 정보를 채우세요)")}</div>
        <div class="dc-meta">${mailEsc(meta)}</div>
        ${contactLine(c, "client", "계약 담당")}${contactLine(c, "biz", "사업 담당")}
        <div class="dc-site">${c.site_id ? `현장 <a href="site.html?id=${c.site_id}">${mailEsc(c.site_label)}</a>` : '<span class="dc-nosite">현장 연결 안 됨</span>'}
          <button type="button" class="dc-link">${c.site_id ? "바꾸기" : "🔗 현장 연결"}</button></div>
      </div>
      <div class="dc-docs">${docs}</div>
      <div class="dc-actions">
        <button type="button" class="secondary dc-start">📑 착수계</button>
        <button type="button" class="secondary dc-done">📑 완수계</button>
        <button type="button" class="secondary dc-del" title="계약 지우기">삭제</button>
      </div>`;
    el.querySelectorAll(".dc-contact").forEach((line) => { // 📞 전화(폰은 바로 걸기, PC는 번호 복사 — 현장 목록과 같은 버튼)
      const call = siteLinkButtons(c[`${line.dataset.who}_phone`], "");
      if (call) line.appendChild(call);
    });
    el.querySelector(".dc-start").addEventListener("click", () => openContractDocs(c.id, "start", load));
    el.querySelector(".dc-done").addEventListener("click", () => openContractDocs(c.id, "done", load));
    el.querySelector(".dc-link").addEventListener("click", () => openLinkSite(c.id, load));
    el.querySelector(".dc-del").addEventListener("click", async () => {
      const made = c.made.start.at || c.made.done.at;
      const pw = await dcAskPassword(`"${c.title || "용역 계약"}"을(를) 지웁니다.${made ? " 만든 착수계·완수계·붙임 파일도 같이 지워집니다." : ""} 되돌릴 수 없습니다.`);
      if (pw == null) return;
      try {
        await api(`/contracts/${c.id}`, { method: "DELETE", body: JSON.stringify({ password: pw }) });
        load();
      } catch (err) {
        showError(errorEl, err);
        errorEl.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });
    return el;
  }

  document.getElementById("dc-search").addEventListener("input", (e) => { view.q = e.target.value; render(); });

  // 새 계약: 계약서 PDF → 읽어서 만들고 바로 착수계 창(같은 계약번호가 이미 있으면 알림)
  document.getElementById("dc-pdf").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    const msg = document.getElementById("dc-new-msg");
    msg.textContent = "계약서를 읽는 중… (처음 보는 양식이면 AI로 읽느라 20초쯤)";
    msg.className = "status";
    try {
      const fd = new FormData();
      fd.append("file", file);
      const out = await apiUpload("/contracts/from-pdf", fd);
      msg.textContent = out.duplicate_of ? `⚠ 같은 계약번호가 이미 있습니다: ${out.duplicate_of.title} — 필요 없으면 새로 만든 쪽을 지우세요.` : "";
      msg.className = out.duplicate_of ? "status bad" : "status";
      await load();
      openContractDocs(out.id, "start", load, out); // 읽은 결과(AI로 채운 칸) 안내와 함께
    } catch (err) {
      msg.textContent = err.message;
      msg.className = "status bad";
    }
  });
  enableFileDrop(document.querySelector("main.main"), document.getElementById("dc-pdf")); // 화면에 계약서 PDF를 끌어다 놓아도 새 계약
  // [+ 새 계약] — 빈 착수계 창(계약서 PDF를 끌어다 놓거나 올리거나 직접 적기). 계약은 창에서 처음 무언가 할 때 만들어짐
  document.getElementById("dc-new-btn").addEventListener("click", () => openContractDocs(null, "start", load));

  load();
})();
