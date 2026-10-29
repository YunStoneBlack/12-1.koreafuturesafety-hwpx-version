// ---------- 서류 자동화 — 계약 목록(docs.html, 2026-10-06) ----------
// 위: 검색 + [+ 새 계약](10/20 형 — 계약 카드 + 현장 카드를 함께 만드는 창: 용역계약서(선택) + 현장별 기술지도계약서 n개, 착수계는 카드의 버튼으로).
// 화면에 PDF를 끌어다 놓아도 그 창(파일 이름에 "기술지도"가 있으면 기술지도계약서 칸). 단계 칸(전체·착수계 전·착수계 제출·완수계 제출)을 누르면 거름.
// 한 줄: 용역명 · 발주처·계약번호·금액·기간 · 현장(연결/연결 안 됨 [🔗 연결]) · 착수계·완수계 상태 · [📑 착수계][📑 완수계][삭제].
// 10/15 사용자 "보고서 자동화 현장 목록처럼": 번호는 "26-68)_" 대신 파란 번호표, [최근 열람순](착수계·완수계 창을 연 때 — contract_view) [번호순 ▼▲](이 기기에 기억).

(function () {
  const errorEl = document.getElementById("error");
  const view = { stage: "", q: "" };
  let data = { contracts: [], stages: [] };
  // ---------- 정렬(현장 목록 dashboard.html과 같음) ----------
  const SORT_KEY = "kfsc-report:docs-sort";
  let sort = { mode: "no", desc: true };
  try { sort = { ...sort, ...JSON.parse(localStorage.getItem(SORT_KEY) || "{}") }; } catch { /* 기억 못 하면 기본 */ }
  const mgmtKey = (c) => { const m = String(c.management_no || "").match(/^(\d{2}|\d{4})-0*(\d+)$/); return m ? Number(m[1].slice(-2)) * 1e7 + Number(m[2]) : null; };
  const byNumber = (a, b, desc) => {
    const x = mgmtKey(a), y = mgmtKey(b);
    if (x === null || y === null) return x === null ? (y === null ? b.id - a.id : 1) : -1;
    return desc ? y - x : x - y;
  };
  const sortList = (list) => (sort.mode === "viewed"
    ? list.sort((a, b) => (b.viewed_at || "").localeCompare(a.viewed_at || "") || byNumber(a, b, true))
    : list.sort((a, b) => byNumber(a, b, sort.desc)));
  function drawSort() {
    document.querySelectorAll(".dc-sort button").forEach((b) => {
      const on = b.dataset.sort === sort.mode;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on);
      if (b.dataset.sort === "no") b.textContent = `번호순 ${on ? (sort.desc ? "▼" : "▲") : ""}`.trim();
    });
  }
  document.querySelectorAll(".dc-sort button").forEach((b) => b.addEventListener("click", () => {
    if (b.dataset.sort === "no" && sort.mode === "no") sort.desc = !sort.desc; // 번호순 한 번 더 → 방향 바꿈
    else if (b.dataset.sort === "no") sort.desc = true;
    sort.mode = b.dataset.sort;
    try { localStorage.setItem(SORT_KEY, JSON.stringify(sort)); } catch { /* 지금은 바뀜 */ }
    render();
  }));

  const wantId = Number(new URLSearchParams(location.search).get("contract")) || 0;  // 견적 [계약으로 넘기기]에서 옴(10/29)
  async function load() {
    try {
      data = await dcLoad();
      if (wantId && !load.done) { view.stage = ""; view.q = ""; }
      render();
      if (wantId && !load.done) {
        load.done = true;
        const hit = document.querySelector(`.dc-row[data-id="${wantId}"]`);
        if (hit) { hit.classList.add("dc-hit"); hit.scrollIntoView({ behavior: "smooth", block: "center" }); }
      }
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
    drawSort();
    const shown = sortList(all.filter((c) => (!view.stage || c.stage === view.stage) && words.every((w) => dcSearchText(c).includes(w))));
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

  // 현장 — 계약 하나에 현장 여럿(10/20 형, 같은 번호는 자동 연결): 하나면 이름, 여럿이면 "현장 N곳 ▾"로 펼침
  function siteLine(c) {
    const ss = c.sites || [];
    if (!ss.length) return '<span class="dc-nosite" title="기술지도계약서가 나오면 현장을 등록하고 [🔗 현장 연결]로 이으세요">⚠ 현장 카드 없음 — 현장 등록 후 연결</span>';
    if (ss.length === 1) return `현장 <a href="site.html?id=${ss[0].id}">${mailEsc(ss[0].label)}</a>`;
    return `<details class="dc-sites"><summary>현장 ${ss.length}곳</summary>${ss.map((s) => `<a href="site.html?id=${s.id}">${mailEsc(s.label)}</a>`).join("")}</details>`;
  }

  function row(c) {
    const el = document.createElement("div");
    el.className = "row dc-row";
    el.dataset.id = c.id;
    const meta = [c.client, c.contract_no, dcMoney(c.amount), c.start_date && `${c.start_date} ~ ${c.end_date || ""}`].filter(Boolean).join(" · ");
    const docs = DC_KINDS.map(([k, label]) => {
      const s = dcDocState(c, k);
      return `<span class="dc-doc ${s.cls}"><b>${label}</b> ${mailEsc(s.text)}</span>`;
    }).join("");
    el.innerHTML = `
      <div class="dc-main">
        <div class="dc-title">${c.short_no ? `<span class="site-no">${mailEsc(c.short_no)}</span>` : ""}${mailEsc(c.title || "(용역명 없음 — 계약 정보를 채우세요)")}</div>
        <div class="dc-meta">${mailEsc(meta)}</div>
        ${contactLine(c, "client", "계약 담당")}${contactLine(c, "biz", "사업 담당")}
        <div class="dc-site">${siteLine(c)}
          <button type="button" class="dc-link">${(c.sites || []).length ? "바꾸기·더하기" : "🔗 현장 연결"}</button></div>
      </div>
      <div class="dc-docs">${docs}${c.changes ? `<span class="dc-doc dc-chg"><b>계약변경</b> ${c.changes}차</span>` : ""}</div>
      <div class="dc-actions">
        <button type="button" class="secondary dc-change" title="공기연장 등 — 용역기간·금액과 현장 계약기간·공사기간을 같이 바꾸고 변경 계약서를 붙임">+ 계약변경</button>
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
    el.querySelector(".dc-change").addEventListener("click", () => openChange(c));
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

  // 새 계약: 화면에 놓은·고른 PDF → [+ 새 계약] 창에 넣어서(파일 이름에 "기술지도"가 있으면 기술지도계약서, 아니면 처음 하나는 용역계약서)
  document.getElementById("dc-pdf").addEventListener("change", (e) => {
    const picked = [...e.target.files];
    e.target.value = "";
    if (picked.length) openNewCard(picked);
  });
  enableFileDrop(document.querySelector("main.main"), document.getElementById("dc-pdf"));
  document.getElementById("dc-new-btn").addEventListener("click", () => openNewCard([]));

  // ---------- [+ 계약변경] 창(10/20 형 — 공기연장 등): 변경 용역계약서·기술지도계약서를 붙이면 읽어서 칸을 채움(저장 전 고칠 수 있음),
  // [변경 저장] = 계약 칸 + 현장 칸(계약기간·공사기간·금액·지도 횟수)을 같이 바꾸고 차수 기록(바뀐 칸 전·후, 첨부).
  // 공기 경과·자동 배치는 바뀐 우리 계약기간으로(현장 계약 시작·종료 → 용역 착수·완수 → 공사기간, 10/20).
  async function openChange(c) {
    let v;
    try { v = await api(`/contracts/${c.id}/change`); } catch (err) { showError(errorEl, err); return; }
    const files = { service: null, guides: {} };
    const L = v.labels;
    const overlay = document.createElement("div");
    overlay.className = "mail-overlay";
    overlay.innerHTML = '<div class="mail-box cd-box dc-change-box" role="dialog" aria-modal="true"></div>';
    document.body.appendChild(overlay);
    const box = overlay.querySelector(".mail-box");
    let busy = false;
    const close = () => { if (busy) return; overlay.remove(); document.removeEventListener("keydown", onKey, true); };
    const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
    document.addEventListener("keydown", onKey, true);
    overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });
    const lab = (scope, k) => (scope !== "contract" && k === "amount" ? "공사금액" : L[k]); // 현장 칸 금액 = 공사금액
    const input = (scope, k, val) => `<label class="cd-field"><span>${lab(scope, k)}</span><input data-scope="${scope}" data-k="${k}" ${["amount", "total_guidance_count"].includes(k) ? 'inputmode="numeric"' : 'type="date"'} value="${mailEsc(val ?? "")}" /></label>`;
    const fileLine = (f) => f ? `<span class="mail-note">📄 ${mailEsc(f.name)}</span>` : "";
    const hist = v.history.length ? `<details class="cg-hist"><summary>지난 계약변경 ${v.history.length}번</summary>${v.history.slice().reverse().map((h) => {
      const rows = [...Object.entries(h.after.contract).map(([k, x]) => `${L[k]} ${mailEsc(h.before.contract[k] ?? "-")} → <b>${mailEsc(x ?? "-")}</b>`),
        ...Object.entries(h.after.sites).flatMap(([sid, d]) => Object.entries(d).map(([k, x]) => `${mailEsc((v.sites.find((s) => String(s.id) === sid) || {}).label || sid)} ${lab("site", k)} ${mailEsc(h.before.sites[sid]?.[k] ?? "-")} → <b>${mailEsc(x ?? "-")}</b>`))];
      return `<div class="cg-h"><b>${h.no}차</b> ${mailEsc(h.at)} ${mailEsc(h.by)}${h.reason ? ` — ${mailEsc(h.reason)}` : ""}<div>${rows.join("<br>") || "칸 변경 없음"}</div>
        ${h.files.map((n) => `<a href="${BASE}/api/contracts/${c.id}/change/${h.no}/${encodeURIComponent(n)}" target="_blank" rel="noopener">📄 ${mailEsc(n)}</a>`).join(" ")}</div>`;
    }).join("")}</details>` : "";
    box.innerHTML = `<div class="mail-head"><b>📝 계약변경 ${v.next_no}차</b><span class="mail-sub">${mailEsc(c.label)} — 바꾼 칸만 계약·현장 카드에 들어갑니다(보고서는 현장 칸 = 기술지도계약서 기준)</span></div>
      ${hist}
      <label class="cd-field"><span>사유</span><input class="cg-reason" placeholder="예: 공기연장(우기 공사중지)" /></label>
      <div class="mail-label">용역계약서(변경) <span class="mail-note">— 붙이면 읽어서 아래 칸을 채움</span></div>
      <div class="cg-file" data-kind="service"><label class="cd-add">PDF 붙이기<input type="file" accept="application/pdf,.pdf" hidden data-kr-file="skip" /></label><span class="cg-fname"></span></div>
      <div class="cd-grid cg-grid">${["start_date", "end_date", "amount", "contract_date"].map((k) => input("contract", k, v.contract[k])).join("")}</div>
      ${v.sites.map((s) => `<div class="mail-label">현장 ${mailEsc(s.label)} <span class="mail-note">— 기술지도계약서(변경)를 붙이면 읽어서 채움(AI 20초쯤) · 계약 시작·종료가 비면 용역 기간</span></div>
        <div class="cg-file" data-kind="guide" data-site="${s.id}"><label class="cd-add">PDF 붙이기<input type="file" accept="application/pdf,.pdf" hidden data-kr-file="skip" /></label><span class="cg-fname"></span></div>
        <div class="cd-grid cg-grid">${["contract_start", "contract_end", "period_start", "period_end", "amount", "total_guidance_count"].map((k) => input(`site:${s.id}`, k, s[k])).join("")}</div>`).join("")
        || '<div class="mail-note">연결된 현장이 없습니다 — 계약 칸만 바뀝니다.</div>'}
      <div class="mail-msg cg-msg" hidden></div>
      <div class="mail-foot cd-foot"><button type="button" class="cg-close">닫기</button><button type="button" class="mail-primary cg-save">📝 변경 저장</button></div>`;
    const msg = box.querySelector(".cg-msg");
    const say = (t, tone) => { msg.hidden = !t; msg.className = `mail-msg cg-msg ${tone || ""}`; msg.innerHTML = t; };
    box.querySelector(".cg-close").addEventListener("click", close);
    // 용역 착수·완수를 바꾸면 같은 날짜였던 현장 계약 시작·종료도 따라감(현장 계약기간이 우리 계약기간 첫 기준 — 안 따라가면 자동 배치가 옛 기간으로).
    // 현장 칸이 비어 있으면 그대로(비면 용역 기간을 씀)
    const FOLLOW = { start_date: "contract_start", end_date: "contract_end" };
    box.querySelectorAll('input[data-scope="contract"]').forEach((t) => {
      if (!FOLLOW[t.dataset.k]) return;
      let prev = t.value;
      t.addEventListener("change", () => {
        box.querySelectorAll(`input[data-scope^="site:"][data-k="${FOLLOW[t.dataset.k]}"]`).forEach((s) => {
          if (s.value && s.value === prev && s.value !== t.value) { s.value = t.value; s.classList.add("sk-filled"); }
        });
        prev = t.value;
      });
    });
    box.querySelectorAll(".cg-file").forEach((el) => {
      const inp = el.querySelector("input[type=file]");
      enableFileDrop(el, inp);
      inp.addEventListener("change", async () => {
        const f = inp.files[0];
        inp.value = "";
        if (!f) return;
        const service = el.dataset.kind === "service";
        if (service) files.service = f; else files.guides[el.dataset.site] = f;
        el.querySelector(".cg-fname").innerHTML = fileLine(f) + ' <span class="mail-note">읽는 중…</span>';
        try {
          const fd = new FormData();
          fd.append("file", f);
          const r = await apiUpload(`/contracts/${c.id}/change/read/${service ? "service" : "guide"}`, fd);
          const scope = service ? "contract" : `site:${el.dataset.site}`;
          let n = 0;
          for (const [k, x] of Object.entries(r.values || {})) {
            const t = box.querySelector(`input[data-scope="${scope}"][data-k="${k}"]`);
            if (t && x != null && String(t.value) !== String(x)) { t.value = x; t.classList.add("sk-filled"); t.dispatchEvent(new Event("change")); n += 1; }
          }
          el.querySelector(".cg-fname").innerHTML = fileLine(f) + ` <span class="mail-note">${n ? `${n}칸 바뀜 — 확인하세요` : "바뀐 칸 없음(직접 고치세요)"}</span>`;
        } catch (err) {
          el.querySelector(".cg-fname").innerHTML = fileLine(f) + ` <span class="cd-bad">못 읽음: ${mailEsc(err.message)} — 칸을 직접 고치세요(파일은 그대로 붙음)</span>`;
        }
      });
    });
    box.querySelector(".cg-save").addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      const body = { reason: box.querySelector(".cg-reason").value, contract: {}, sites: {} };
      box.querySelectorAll("input[data-scope]").forEach((t) => {
        const val = t.value.trim().replace(/,/g, "");
        if (t.dataset.scope === "contract") body.contract[t.dataset.k] = val;
        else (body.sites[t.dataset.scope.split(":")[1]] ||= {})[t.dataset.k] = val;
      });
      const fd = new FormData();
      fd.append("data", JSON.stringify(body));
      if (files.service) fd.append("service", files.service);
      const gids = Object.keys(files.guides);
      for (const id of gids) fd.append("guides", files.guides[id]);
      fd.append("guide_ids", gids.join(","));
      busy = true;
      btn.disabled = true;
      try {
        const out = await apiUpload(`/contracts/${c.id}/change`, fd);
        busy = false;
        const n = Object.keys(out.saved.after.contract).length + Object.values(out.saved.after.sites).reduce((a, d) => a + Object.keys(d).length, 0);
        say(`✓ ${out.saved.no}차 계약변경을 저장했습니다 — 바뀐 칸 ${n}개${out.saved.files.length ? `, 첨부 ${out.saved.files.length}개` : ""}. 현장 카드·공기 경과에도 들어갔습니다.`, "ok");
        btn.textContent = "저장함";
        load();
      } catch (err) {
        busy = false;
        btn.disabled = false;
        say(mailEsc(err.message), "bad");
      }
    });
  }

  // ---------- [+ 새 계약] 창 — 계약 카드 + 현장 카드(10/20 형 문서) ----------
  async function openNewCard(initial) {
    const st = { service: null, guides: [] };
    for (const f of initial) {
      if (/기술지도/.test(f.name) || st.service) st.guides.push(f);
      else st.service = f;
    }
    let next = "";
    try { next = (await api("/contracts/next-management-no")).management_no; } catch { /* 비우면 서버가 정함 */ }
    const overlay = document.createElement("div");
    overlay.className = "mail-overlay";
    overlay.innerHTML = '<div class="mail-box cd-box dc-newcard" role="dialog" aria-modal="true"></div>';
    document.body.appendChild(overlay);
    const box = overlay.querySelector(".mail-box");
    let busy = false;
    const close = () => { if (busy) return; overlay.remove(); document.removeEventListener("keydown", onKey, true); };
    const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
    document.addEventListener("keydown", onKey, true);
    overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });
    const fileRow = (f, i, kind) => `<div class="cd-file"><span>📄 ${mailEsc(f.name)}</span><span class="mail-note">${(f.size / 1e6).toFixed(1)}MB</span>
      <button type="button" class="cd-x" data-kind="${kind}" data-i="${i}" title="빼기">✕</button></div>`;
    function draw(result) {
      const n = st.guides.length;
      const no = box.querySelector(".nc-no")?.value ?? next;
      box.innerHTML = `<div class="mail-head"><b>📄 새 계약</b><span class="mail-sub">계약 카드와 현장 카드를 함께 만듭니다 — 기술지도계약서가 아직 없으면 용역계약서만으로 계약 카드만(착수계를 먼저 낼 때). 착수계·완수계는 카드의 버튼으로</span></div>
        <label class="cd-field"><span>관리번호 <em>비우면 자동(마지막 번호 다음)</em></span><input class="nc-no" value="${mailEsc(no)}" placeholder="${mailEsc(next)}" /></label>
        <div class="mail-label">용역계약서 <span class="mail-note">— 나라장터·국방조달 계약서(선택, 없으면 기술지도계약서만)</span></div>
        <div class="cd-slot nc-slot" data-kind="service">${st.service ? fileRow(st.service, 0, "service") : ""}
          <label class="drop-box drop-sm"><b class="drop-pc">⬇ 용역계약서 PDF를 끌어다 놓기</b><b class="drop-touch">눌러서 용역계약서 고르기</b>
            <input type="file" accept="application/pdf,.pdf" hidden data-kr-file="skip" /></label></div>
        <div class="mail-label">K2B 기술지도계약서 <span class="mail-note">— 현장마다 하나. 없으면 계약 카드만 만들고 현장 카드는 나중에. 여럿이면 현장 카드 하나에 ${mailEsc(no || next)}-1 · -2 …</span></div>
        <div class="cd-slot nc-slot" data-kind="guides">${st.guides.map((f, i) => fileRow(f, i, "guides")).join("")}
          <label class="drop-box drop-sm"><b class="drop-pc">⬇ 기술지도계약서 PDF를 끌어다 놓기(여러 개 가능)</b><b class="drop-touch">눌러서 기술지도계약서 고르기</b>
            <input type="file" accept="application/pdf,.pdf" multiple hidden data-kr-file="skip" /></label></div>
        <div class="mail-msg nc-msg ${result ? result.tone : ""}"${result ? "" : " hidden"}>${result ? result.html : ""}</div>
        <div class="mail-foot cd-foot"><button type="button" class="nc-close">닫기</button>
          <button type="button" class="mail-primary nc-make"${n || st.service ? "" : " disabled"}>${n ? `📄 계약 카드 + 현장 ${n}곳 만들기` : st.service ? "📄 계약 카드만 만들기(현장 카드는 나중에)" : "📄 계약 카드 + 현장 만들기"}</button></div>`;
      box.querySelector(".nc-close").addEventListener("click", close);
      box.querySelectorAll(".nc-slot").forEach((slot) => {
        const input = slot.querySelector("input[type=file]");
        enableFileDrop(slot, input);
        input.addEventListener("change", () => {
          const fs = [...input.files].filter((f) => /\.pdf$/i.test(f.name) || f.type === "application/pdf");
          input.value = "";
          if (!fs.length) return;
          if (slot.dataset.kind === "service") st.service = fs[0]; else st.guides.push(...fs);
          draw();
        });
      });
      box.querySelectorAll(".cd-x").forEach((b) => b.addEventListener("click", () => {
        if (b.dataset.kind === "service") st.service = null; else st.guides.splice(Number(b.dataset.i), 1);
        draw();
      }));
      box.querySelector(".nc-make").addEventListener("click", make);
    }
    async function make() {
      const btn = box.querySelector(".nc-make");
      const msg = box.querySelector(".nc-msg");
      busy = true;
      btn.disabled = true;
      btn.textContent = st.guides.length ? `읽는 중… (기술지도계약서 ${st.guides.length}개 — AI로 20~60초)` : "용역계약서 읽는 중…";
      msg.hidden = true;
      try {
        const fd = new FormData();
        fd.append("management_no", box.querySelector(".nc-no").value.trim());
        if (st.service) fd.append("service", st.service);
        for (const f of st.guides) fd.append("guides", f);
        const out = await apiUpload("/contracts/new-card", fd);
        busy = false;
        await load();
        box.innerHTML = `<div class="mail-head"><b>✓ 만들었습니다</b><span class="mail-sub">${mailEsc(out.label)}</span></div>
          <div class="mail-info"><div><span>계약 카드</span><div>${mailEsc(out.short_no)} · ${mailEsc(out.title || "")}</div></div>
            <div><span>현장 카드</span><div>${out.created_sites.length ? out.created_sites.map((s) => `<a href="site.html?id=${s.id}">${mailEsc(s.label)}</a>`).join("<br>") : "없음"}</div></div></div>
          ${out.need_site ? '<div class="mail-msg warn">⚠ 현장 카드가 아직 없습니다 — 기술지도계약서가 나오면 현장을 등록하고 이 계약 카드의 [🔗 현장 연결]로 이으세요(같은 관리번호로 등록하면 자동 연결).</div>' : ""}
          ${(out.ai_filled || []).length ? `<div class="mail-note">용역계약서의 못 읽은 칸 ${out.ai_filled.length}개는 AI로 채웠습니다 — [📑 착수계] 창에서 확인하세요.</div>` : ""}
          <div class="mail-foot cd-foot"><button type="button" class="nc-close">닫기</button>
            <button type="button" class="mail-primary nc-start">📑 착수계 창 열기</button></div>`;
        box.querySelector(".nc-close").addEventListener("click", close);
        box.querySelector(".nc-start").addEventListener("click", () => { close(); openContractDocs(out.id, "start", load); });
      } catch (err) {
        busy = false;
        draw({ tone: "bad", html: mailEsc(err.message) });
      }
    }
    draw();
  }

  load();
})();
