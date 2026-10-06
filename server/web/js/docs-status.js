// ---------- 서류 자동화 — 제출 현황(docs-status.html, 2026-10-06) ----------
// 칸: 착수계 미제출 · 완수계 미제출 · 전체(기한은 없음 — 사용자 10/6) — 누르면 아래 표를 거름. 표 한 줄 = 계약(용역명·현장) · 착수계 · 완수계(누르면 그 창).
// "제출" = 합본 PDF를 만들었음(서버 contract_status.submitted). 완수계는 착수계를 낸 계약만 셈.

(function () {
  const errorEl = document.getElementById("error");
  let contracts = [];
  let filter = "start";
  const FILTERS = {
    start: ["착수계 미제출", (c) => !c.made.start.submitted, "착수계를 아직 안 만든 계약"],
    done: ["완수계 미제출", (c) => c.made.start.submitted && !c.made.done.submitted, "착수계는 냈고 완수계가 남은 계약"],
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
    list.innerHTML = `<div class="ds-head"><span>용역 계약</span><span>착수계</span><span>완수계</span></div>` + shown.map((c) => `
      <div class="ds-row" data-id="${c.id}">
        <div class="ds-name"><b>${mailEsc(c.label)}</b>
          <span class="mail-note">${mailEsc([c.client, c.site_label ? `현장 ${c.site_label}` : "현장 연결 안 됨"].join(" · "))}</span></div>
        ${DC_KINDS.map(([k, kl]) => {
          const s = dcDocState(c, k);
          return `<button type="button" class="ds-doc dc-doc ${s.cls}" data-kind="${k}" title="${kl} 창 열기"><b class="ds-kl">${kl}</b> ${mailEsc(s.text)}</button>`;
        }).join("")}
      </div>`).join("");
    list.querySelectorAll(".ds-row").forEach((r) => r.querySelectorAll(".ds-doc").forEach((b) => b.addEventListener("click", () => {
      openContractDocs(Number(r.dataset.id), b.dataset.kind, load);
    })));
  }

  load();
})();
