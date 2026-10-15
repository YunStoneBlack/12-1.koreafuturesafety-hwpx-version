// ---------- 서류 자동화 — 제출 현황(docs-status.html, 2026-10-06) ----------
// 칸: 착수계 미제출 · 완수계 미제출 · 전체(기한은 없음 — 사용자 10/6) — 누르면 아래 표를 거름. 표 한 줄 = 계약(용역명·현장) · 착수계 · 완수계(누르면 그 창).
// "제출" = 제출 기록(E-mail·직접·우편, 서버 contract_status.submitted). 완수계는 착수계를 낸 계약만 셈.
// 10/15 사용자 "산안법 일부수정안": 칸을 누르면 작은 창 — [서류 창 열기] 또는 [직접 제출함](날짜 — 프로그램 쓰기 전에 낸 것도, 착수계 없이 완수계도),
// 계산서 발행 칸(날짜 달력 → POST /contracts/{id}/invoice), 번호는 파란 번호표.

(function () {
  const errorEl = document.getElementById("error");
  let contracts = [];
  let filter = "start";
  const FILTERS = {
    start: ["착수계 미제출", (c) => !c.made.start.submitted, "착수계를 아직 안 만든 계약"],
    done: ["완수계 미제출", (c) => c.made.start.submitted && !c.made.done.submitted, "착수계는 냈고 완수계가 남은 계약"],
    invoice: ["계산서 미발행", (c) => c.made.done.submitted && !c.invoice_date, "완수계는 냈고 계산서 발행일이 없는 계약"],
    all: ["전체", () => true, "모든 용역 계약"],
  };

  async function load() {
    try {
      contracts = (await dcLoad()).contracts;
      render();
    } catch (err) {
      showError(errorEl, err);
    }
  }

  function render() {
    const cards = document.getElementById("ds-cards");
    cards.innerHTML = Object.entries(FILTERS).map(([key, [label, fn, sub]]) => {
      const n = contracts.filter(fn).length;
      return `<button type="button" class="st-card${filter === key ? " active" : ""}" data-f="${key}">
        <span class="l">${label}</span><span class="n">${n}건</span><span class="s">${sub}</span></button>`;
    }).join("");
    cards.querySelectorAll(".st-card").forEach((b) => b.addEventListener("click", () => { filter = b.dataset.f; render(); }));
    const [label, fn] = FILTERS[filter];
    const shown = contracts.filter(fn);
    document.getElementById("ds-title").textContent = label;
    document.getElementById("ds-count").textContent = `${shown.length}건`;
    const list = document.getElementById("ds-list");
    if (!shown.length) {
      list.innerHTML = '<div class="empty-note">해당하는 계약이 없습니다.</div>';
      return;
    }
    list.innerHTML = `<div class="ds-head"><span>용역 계약</span><span>착수계</span><span>완수계</span><span>계산서 발행</span></div>` + shown.map((c) => `
      <div class="ds-row" data-id="${c.id}">
        <div class="ds-name"><b>${c.short_no ? `<span class="site-no">${mailEsc(c.short_no)}</span>` : ""}${mailEsc(c.title || "(용역명 없음)")}</b>
          <span class="mail-note">${mailEsc([c.client, c.site_label ? `현장 ${c.site_label}` : "현장 연결 안 됨"].join(" · "))}</span></div>
        ${DC_KINDS.map(([k, kl]) => {
          const s = dcDocState(c, k);
          return `<div class="ds-cell"><button type="button" class="ds-doc tone-${s.tone}" data-kind="${k}" title="${kl} 창 열기">` +
            `<b class="ds-kl">${kl}</b><span class="ds-txt">${mailEsc(s.text)}</span><span class="ds-go">열기 ›</span></button></div>`;
        }).join("")}
        <div class="ds-cell"><button type="button" class="ds-doc ds-inv tone-${c.invoice_date ? "ok" : "todo"}" title="계산서 발행일">
          <b class="ds-kl">계산서</b><span class="ds-txt">${c.invoice_date ? `✓ ${c.invoice_date.slice(5).replace("-", "/")} 발행` : "미발행"}</span><span class="ds-go">날짜 ›</span></button></div>
      </div>`).join("");
    list.querySelectorAll(".ds-row").forEach((r) => {
      const c = contracts.find((x) => x.id === Number(r.dataset.id));
      r.querySelectorAll(".ds-doc[data-kind]").forEach((b) => b.addEventListener("click", () => openCell(c, b.dataset.kind)));
      r.querySelector(".ds-inv").addEventListener("click", () => openInvoice(c));
    });
  }

  const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
  function dialog(html) {
    const overlay = document.createElement("div");
    overlay.className = "mail-overlay";
    overlay.innerHTML = `<div class="mail-box ds-mini" role="dialog" aria-modal="true">${html}<div class="mail-msg" hidden></div></div>`;
    document.body.appendChild(overlay);
    overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) overlay.remove(); });
    const bad = (err) => { const m = overlay.querySelector(".mail-msg"); m.hidden = false; m.className = "mail-msg bad"; m.textContent = err.message; };
    return { overlay, close: () => overlay.remove(), bad, q: (s) => overlay.querySelector(s) };
  }
  // 착수계·완수계 칸 — 서류 창 열기 / 직접 제출함(날짜, PDF 없이도 — 프로그램 쓰기 전에 낸 것)
  function openCell(c, kind) {
    const label = DC_KINDS.find(([k]) => k === kind)[1];
    const s = dcDocState(c, kind);
    const d = dialog(`<div class="mail-head"><b>${label}</b><span class="mail-sub">${mailEsc(c.label)}</span></div>
      <div class="mail-note">지금: ${mailEsc(s.text)}</div>
      <button type="button" class="secondary dm-open">📑 ${label} 창 열기(만들기·E-mail·제출 기록 지우기)</button>
      <label class="cd-field"><span>직접 제출한 날 <em>프로그램 쓰기 전에 낸 것도</em></span><input type="date" class="dm-date" value="${today()}" /></label>
      <div class="mail-foot"><button type="button" class="dm-close">닫기</button><button type="button" class="mail-primary dm-direct">✓ 직접 제출함</button></div>`);
    d.q(".dm-close").addEventListener("click", d.close);
    d.q(".dm-open").addEventListener("click", () => { d.close(); openContractDocs(c.id, kind, load); });
    d.q(".dm-direct").addEventListener("click", async () => {
      try {
        await apiPost(`/contracts/${c.id}/submit/${kind}`, { method: "direct", submitted_on: d.q(".dm-date").value || "" });
        d.close();
        load();
      } catch (err) { d.bad(err); }
    });
  }
  // 계산서 발행일(달력)
  function openInvoice(c) {
    const d = dialog(`<div class="mail-head"><b>계산서 발행</b><span class="mail-sub">${mailEsc(c.label)}</span></div>
      <div class="mail-note">${c.invoice_date ? `지금: ${c.invoice_date} 발행` : "아직 발행일 없음"}</div>
      <label class="cd-field"><span>발행일</span><input type="date" class="dm-date" value="${c.invoice_date || today()}" /></label>
      <div class="mail-foot"><button type="button" class="dm-close">닫기</button>${c.invoice_date ? '<button type="button" class="dm-clear">지우기</button>' : ""}
        <button type="button" class="mail-primary dm-save">✓ 발행일 저장</button></div>`);
    d.q(".dm-close").addEventListener("click", d.close);
    const send = async (date) => {
      try {
        await apiPost(`/contracts/${c.id}/invoice`, { date });
        d.close();
        load();
      } catch (err) { d.bad(err); }
    };
    d.q(".dm-save").addEventListener("click", () => send(d.q(".dm-date").value || null));
    const cl = d.q(".dm-clear");
    if (cl) cl.addEventListener("click", () => send(null));
  }

  load();
})();
