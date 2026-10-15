// ---------- 서류 자동화 · 시특법 — 계약 목록(sitok-docs.html, 2026-10-12) ----------
// API server/api/routers/sitok_docs.py(/sitok/docs). 산안법(docs.html)처럼 보고서 쪽과 따로, 현장(시설물) 연결(민간·관급 둘 다 — 사용자 10/12).
// 위: 검색 + [+ 민간 계약서 만들기] [+ 관급 계약] + 이미 만든 민간 계약서를 끌어다 놓기(읽어서 새 계약). 칸(전체·민간·관급·현장 연결 안 됨)을 누르면 거름.
// 한 줄: 계약건명 · 관리주체·기간·금액 · 계약/현장 담당 · 현장(연결/[🔗 현장 연결]) · 계약서·날인본·보고서 쪽 상태 · [열기][삭제].
// 창: 서류 올리기(관리대장·사업자등록증·날인본) → 관리주체 → 시설물 → 계약 회차(연도·반기·정기/정밀·금액) 또는 계약 해지 시까지(매 반기 단가)
//     → 계약(계약일·기간·문서번호·계약건명) → 담당자 → [저장] [📝 계약서 만들기]. 닫으면 고친 내용 저장.
// 관급(2단계): 나라장터 계약서를 올리면 읽어서 칸 채움 → [📑 착수계] [📑 완료계] 창(js/sitok-docs-gov.js).
// 10/15 민재형 문서번호 일치화: 목록 = 시설물 카드(번호 민간-N·관급-N — 보고서 자동화 시설물과 같은 카드·번호, 묶인 동은 카드 하나).
//   카드 안에 민간은 계약서가 차례로, 관급은 착수계(계약)가 연도별로 쌓임. 계약마다 반기 표시(상반기·하반기·상·하반기·해당없음 — 기간으로 자동, 내진 = 해당없음).
//   [+ 새 시설물 카드] = 보고서 자동화에도 같은 번호로 바로 생김. 뱃지(분야·관급 종류) 칩 = 개수·거르기. 카드에 안 넣은 계약은 맨 아래.

(function () {
  const errorEl = document.getElementById("error");
  const P = "/sitok/docs";
  const view = { tab: "", q: "", field: "", kind: "" };
  let all = [];
  let cards = [];
  const SORT_KEY = "kfsc-report:sitok-docs-sort";
  let sort = { mode: "no", desc: true };
  try { sort = { ...sort, ...JSON.parse(localStorage.getItem(SORT_KEY) || "{}") }; } catch { /* 기억 못 하면 기본 */ }

  const esc = mailEsc;
  const won = (n) => (n || n === 0) && n !== "" ? Number(n).toLocaleString("ko-KR") : "";
  const num = (v) => { const d = String(v ?? "").replace(/[^\d]/g, ""); return d ? Number(d) : null; };
  const fileUrl = (c, name) => `${BASE}/api${P}/contracts/${c.id}/file/${encodeURIComponent(name)}?v=${encodeURIComponent(c.made_at || c.updated || "")}`;
  const TEXT = ["doc_no", "client", "client_rep", "client_biz_no", "client_address", "facility_name", "location", "spec", "title", "contract_no",
    "guarantee", "delay_rate", "client_manager", "client_phone", "client_email", "site_manager", "site_phone", "site_email", "memo"];
  const DATES = ["contract_date", "start_date", "end_date"];
  const LABEL = { client: "관리주체", client_rep: "대표자", client_biz_no: "사업자등록번호", client_address: "주소", facility_name: "시설물명", location: "위치",
    spec: "제원", title: "계약건명", doc_no: "문서번호", rounds: "계약 회차", open_ended: "계약 해지 시까지", unit: "매 반기 금액", guarantee: "계약보증액",
    delay_rate: "지체상금율", contract_date: "계약일", start_date: "시작일", end_date: "종료일", contract_no: "계약번호", amount: "계약금액",
    client_manager: "계약 담당", client_phone: "계약 담당 연락처", client_email: "계약 담당 이메일", site_manager: "현장 담당", site_phone: "현장 담당 연락처",
    site_email: "현장 담당 이메일" };

  function moneyText(c) {
    if (c.sector === "관급") return c.amount ? `${won(c.amount)}원` : "";
    if (c.open_ended) return c.unit && c.unit.amount ? `매 반기(${c.unit.kind}) ${won(c.unit.amount)}원` : "";
    return c.total ? `총 ${won(c.total)}원${c.rounds.length > 1 ? ` (${c.rounds.length}회)` : ""}` : "";
  }
  function periodText(c) {
    if (c.open_ended) return `${c.start_date || ""} ~ 계약 해지 시까지`;
    return c.start_date || c.end_date ? `${c.start_date || ""} ~ ${c.end_date || ""}` : "";
  }

  async function load() {
    try {
      const [a, b] = await Promise.all([api(`${P}/contracts`), api(`${P}/facilities`)]);
      all = a.contracts;
      cards = b.facilities;
      render();
    } catch (err) {
      showError(errorEl, err);
    }
  }

  // ---------- 시설물 카드(10/15 민재형 문서번호 일치화) ----------
  const cardOf = (c) => (c.facility ? cards.find((k) => k.members.some((m) => m.id === c.facility.id)) : null);
  const contractsOf = (k) => all.filter((c) => c.facility && k.members.some((m) => m.id === c.facility.id))
    .sort((a, b) => (a.start_date || a.contract_date || "9999").localeCompare(b.start_date || b.contract_date || "9999") || a.id - b.id); // 차례로 쌓임(옛것 위)
  const noKey = (k) => { // "관급-3" < "민간-1"(구분끼리, 그 안에서 번호), 그 밖 번호는 맨 뒤
    const m = String(k.mgmt_no || "").match(/^(관급|민간)-0*(\d+)$/);
    return m ? (m[1] === "관급" ? 1e8 : 2e8) + Number(m[2]) : 3e8 + k.id;
  };
  const byNo = (a, b) => { const x = noKey(a), y = noKey(b); return Math.floor(x / 1e8) - Math.floor(y / 1e8) || (sort.desc ? y - x : x - y); };
  const sortCards = (list) => (sort.mode === "viewed" ? list.sort((a, b) => (b.viewed_at || "").localeCompare(a.viewed_at || "") || byNo(a, b)) : list.sort(byNo));
  const cardName = (k) => (k.members.length > 1 ? k.group_name || k.name : k.name);
  const cardText = (k) => [k.mgmt_no, cardName(k), k.address, k.owner_name, ...k.members.map((m) => m.name),
    ...contractsOf(k).flatMap((c) => [c.title, c.auto_title, c.client, c.contract_no, c.client_manager, c.site_manager])].join(" ").toLowerCase();
  const conText = (c) => `${c.title} ${c.auto_title} ${c.client} ${c.facility_name} ${c.contract_no} ${c.client_manager} ${c.site_manager}`.toLowerCase();
  const TABS = [["", "전체", "시설물 카드", (k) => true], ["민간", "민간", "계약서를 우리가 작성", (k) => k.sector === "민간"],
    ["관급", "관급", "나라장터 계약 · 착수계", (k) => k.sector === "관급"]];
  const FIELDS = ["건축", "토목", "건축·토목"], KINDS = ["학교", "일반"]; // 내진성능평가는 따로(10/15 밤)
  const badgeOk = (k) => (!view.field || k.badge_field === view.field) && (!view.kind || k.badge_kind === view.kind);

  function render() {
    const loose = all.filter((c) => !cardOf(c));
    const cardsEl = document.getElementById("sd-cards");
    cardsEl.innerHTML = TABS.map(([key, label, sub, ok]) => `<button type="button" class="st-card${view.tab === key ? " active" : ""}" data-tab="${key}">
      <span class="l">${label}</span><span class="n">${cards.filter((k) => ok(k) && badgeOk(k)).length}곳</span><span class="s">${sub}</span></button>`).join("") +
      `<button type="button" class="st-card${view.tab === "loose" ? " active" : ""}" data-tab="loose"><span class="l">카드에 안 넣은 계약</span><span class="n">${loose.length}건</span><span class="s">시설물 카드와 아직 안 이음</span></button>`;
    cardsEl.querySelectorAll(".st-card").forEach((b) => b.addEventListener("click", () => { view.tab = b.dataset.tab; if (view.tab === "민간") view.kind = ""; render(); }));
    // 뱃지 칩 — 지금 구분 안에서 개수, 누르면 그것만(한 번 더 = 풀기)
    const inTab = cards.filter((k) => !view.tab || view.tab === "loose" || k.sector === view.tab);
    const chip = (dim, v) => {
      const n = inTab.filter((k) => (dim === "field" ? k.badge_field : k.badge_kind) === v).length;
      return `<button type="button" class="sk-badge-f b-${dim}${view[dim] === v ? " on" : ""}" data-dim="${dim}" data-v="${esc(v)}" aria-pressed="${view[dim] === v}">${esc(v)} <b>${n}</b></button>`;
    };
    const bEl = document.getElementById("sd-badges");
    bEl.innerHTML = `<span class="sk-badge-l">분야</span>${FIELDS.map((v) => chip("field", v)).join("")}` +
      (view.tab === "민간" ? "" : `<span class="sk-badge-l">관급</span>${KINDS.map((v) => chip("kind", v)).join("")}`);
    bEl.querySelectorAll(".sk-badge-f").forEach((b) => b.addEventListener("click", () => { view[b.dataset.dim] = view[b.dataset.dim] === b.dataset.v ? "" : b.dataset.v; render(); }));
    document.querySelectorAll(".sd-sort button").forEach((b) => {
      const on = b.dataset.sort === sort.mode;
      b.classList.toggle("on", on);
      if (b.dataset.sort === "no") b.textContent = `번호순 ${on ? (sort.desc ? "▼" : "▲") : ""}`.trim();
    });

    const words = view.q.toLowerCase().split(/\s+/).filter(Boolean);
    const list = document.getElementById("sd-list");
    const title = document.getElementById("sd-list-title");
    list.innerHTML = "";
    if (view.tab === "loose") {
      title.textContent = "카드에 안 넣은 계약";
      const shown = loose.filter((c) => words.every((w) => conText(c).includes(w)));
      document.getElementById("sd-count").textContent = `${shown.length}건`;
      if (!shown.length) { list.innerHTML = '<div class="empty-note">카드에 안 넣은 계약이 없습니다.</div>'; return; }
      for (const c of shown) list.appendChild(row(c));
      return;
    }
    title.textContent = "시설물 카드";
    const ok = TABS.find((t) => t[0] === view.tab)[3];
    const shown = sortCards(cards.filter((k) => ok(k) && badgeOk(k) && words.every((w) => cardText(k).includes(w))));
    document.getElementById("sd-count").textContent = `${shown.length}곳${loose.length ? ` · 카드에 안 넣은 계약 ${loose.length}건` : ""}`;
    if (!shown.length) {
      list.innerHTML = `<div class="empty-note">${cards.length ? "맞는 시설물 카드가 없습니다." : "아직 시설물 카드가 없습니다 — [+ 새 시설물 카드]로 시작하세요."}</div>`;
      return;
    }
    for (const k of shown) list.appendChild(cardEl(k));
  }
  document.querySelectorAll(".sd-sort button").forEach((b) => b.addEventListener("click", () => {
    if (b.dataset.sort === "no" && sort.mode === "no") sort.desc = !sort.desc;
    else if (b.dataset.sort === "no") sort.desc = true;
    sort.mode = b.dataset.sort;
    try { localStorage.setItem(SORT_KEY, JSON.stringify(sort)); } catch { /* 지금은 바뀜 */ }
    render();
  }));

  const TYPE_SHORT = { "장기": "장기·지속", "1회성": "1회성·입찰", "종료": "계약 종료" };
  function cardEl(k) {
    const el = document.createElement("div");
    el.className = `sd-fcard${k.contract_type === "종료" ? " ended" : ""}`;
    const multi = k.members.length > 1;
    const cons = contractsOf(k);
    el.innerHTML = `
      <div class="sd-fhead"><div class="sd-fmain">
        <div class="sd-ftitle">${k.mgmt_no ? `<button type="button" class="site-no sd-no" title="번호 바꾸기">${esc(k.mgmt_no)}</button>` : ""}<span class="sd-chip ${k.sector === "관급" ? "gov" : "civil"}">${esc(k.sector)}</span>
          <a href="sitok-facility.html?id=${k.id}" title="보고서 자동화 · 시설물 화면"><b>${esc(cardName(k))}</b></a>${multi ? `<span class="sk-dong-n">${k.members.length}동</span>` : ""}
          ${k.badge_field ? `<span class="sk-badge b-field">${esc(k.badge_field)}</span>` : ""}${k.badge_kind ? `<span class="sk-badge b-kind">${esc(k.badge_kind)}</span>` : ""}
          <span class="sd-ftype">${esc(TYPE_SHORT[k.contract_type] || k.contract_type || "")}</span></div>
        <div class="dc-meta">${esc([k.address, k.owner_name].filter(Boolean).join(" · "))}${multi ? ` · ${esc(k.members.map((m) => m.name).join(", "))}` : ""}</div></div>
        <div class="sd-facts">
          <button type="button" class="secondary sd-fnew">${k.sector === "민간" ? "+ 계약서" : "+ 관급 계약(착수계)"}</button>
          <button type="button" class="secondary sd-fbadge" title="분야·관급 종류 뱃지 바꾸기">🏷 뱃지</button>
        </div>
      </div>
      <div class="sd-fbody">${cons.length ? "" : `<div class="mail-note sd-fempty">아직 계약이 없습니다 — [${k.sector === "민간" ? "+ 계약서" : "+ 관급 계약(착수계)"}]로 넣으세요.</div>`}</div>`;
    const body = el.querySelector(".sd-fbody");
    for (const c of cons) body.appendChild(row(c, true));
    el.querySelector(".sd-fnew").addEventListener("click", () => openContract(null, k.sector, { card: k }));
    el.querySelector(".sd-fbadge").addEventListener("click", () => editBadges(k));
    const noBtn = el.querySelector(".sd-no");
    if (noBtn) noBtn.addEventListener("click", () => editNumber(k));
    const links = siteLinkButtons(k.contact_phone, k.address);
    if (links) el.querySelector(".sd-fmain").appendChild(links);
    return el;
  }

  // 번호 바꾸기(10/15 민재형) — 앞 글자는 구분(관급·민간), 숫자만. 겹치면 서버가 알림, 묶인 동 같이, 다음 자동 번호는 가장 큰 번호 + 1
  function editNumber(k) {
    const cur = Number((String(k.mgmt_no).match(/-(\d+)$/) || [])[1]) || "";
    const overlay = document.createElement("div");
    overlay.className = "mail-overlay";
    overlay.innerHTML = `<div class="mail-box sd-badge-box" role="dialog" aria-modal="true">
      <div class="mail-head"><b># 번호 바꾸기</b><span class="mail-sub">${esc(cardName(k))} — 보고서 자동화 시설물도 같은 번호</span></div>
      <label class="cd-field"><span>번호</span><span class="sd-no-row"><b>${esc(k.sector)}-</b><input class="n-no" type="number" min="1" value="${cur}" /></span></label>
      <div class="mail-note">다른 카드가 쓰는 번호는 안 됩니다. 새 카드는 지금 가장 큰 번호 다음부터 자동으로 붙습니다.</div>
      <div class="mail-msg" hidden></div>
      <div class="mail-foot"><button type="button" class="n-close">닫기</button><button type="button" class="mail-primary n-save">저장</button></div></div>`;
    document.body.appendChild(overlay);
    const close = () => overlay.remove();
    overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });
    overlay.querySelector(".n-close").addEventListener("click", close);
    const inp = overlay.querySelector(".n-no");
    inp.focus();
    inp.select();
    const save = async () => {
      try {
        await apiPost(`${P}/facilities/${k.id}/number`, { n: Number(inp.value) });
        close();
        load();
      } catch (err) {
        const m = overlay.querySelector(".mail-msg");
        m.hidden = false;
        m.className = "mail-msg bad";
        m.textContent = err.message;
      }
    };
    overlay.querySelector(".n-save").addEventListener("click", save);
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter") save(); });
  }

  // 뱃지 바꾸기 — 묶인 동은 같이(PATCH /sitok/facilities/{id})
  function editBadges(k) {
    const overlay = document.createElement("div");
    overlay.className = "mail-overlay";
    overlay.innerHTML = `<div class="mail-box sd-badge-box" role="dialog" aria-modal="true">
      <div class="mail-head"><b>🏷 뱃지</b><span class="mail-sub">${esc(k.mgmt_no)} ${esc(cardName(k))}</span></div>
      <label class="cd-field"><span>분야</span><select class="b-field">${FIELDS.map((v) => `<option${k.badge_field === v ? " selected" : ""}>${v}</option>`).join("")}</select></label>
      ${k.sector === "관급" ? `<label class="cd-field"><span>관급 종류</span><select class="b-kind">${KINDS.map((v) => `<option${k.badge_kind === v ? " selected" : ""}>${v}</option>`).join("")}</select></label>
        <div class="mail-note">계약서를 읽을 때 자동으로 정하는데, 여기서 바꾸면 그다음부턴 자동으로 안 바꿉니다.</div>` : '<div class="mail-note">계약서를 읽을 때 자동으로 정하는데, 여기서 바꾸면 그다음부턴 자동으로 안 바꿉니다.</div>'}
      <div class="mail-msg" hidden></div>
      <div class="mail-foot"><button type="button" class="b-close">닫기</button><button type="button" class="mail-primary b-save">저장</button></div></div>`;
    document.body.appendChild(overlay);
    const close = () => overlay.remove();
    overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });
    overlay.querySelector(".b-close").addEventListener("click", close);
    overlay.querySelector(".b-save").addEventListener("click", async () => {
      const b = { badge_field: overlay.querySelector(".b-field").value };
      const kind = overlay.querySelector(".b-kind");
      if (kind) b.badge_kind = kind.value;
      try {
        for (const m of k.members) await api(`/sitok/facilities/${m.id}`, { method: "PATCH", body: JSON.stringify(b) });
        close();
        load();
      } catch (err) {
        const m = overlay.querySelector(".mail-msg");
        m.hidden = false;
        m.className = "mail-msg bad";
        m.textContent = err.message;
      }
    });
  }

  // [+ 새 시설물 카드] — 보고서 자동화 시설물 목록에도 같은 번호로 바로 생김
  async function newCard() {
    const overlay = document.createElement("div");
    overlay.className = "mail-overlay";
    overlay.innerHTML = `<div class="mail-box sd-card-new" role="dialog" aria-modal="true">
      <div class="mail-head"><b>🏢 새 시설물 카드</b><span class="mail-sub">보고서 자동화 · 시특법 시설물 목록에도 같은 번호로 생깁니다</span></div>
      <div class="sd-sector">${["민간", "관급"].map((s) => `<label><input type="radio" name="nc-sector" value="${s}"${s === "민간" ? " checked" : ""} /> ${s}</label>`).join("")}
        <span class="nc-no mail-note"></span></div>
      <div class="cd-grid">
        <label class="cd-field cd-wide"><span>시설물명</span><input class="nc-name" placeholder="예: 동안교회" /></label>
        <label class="cd-field cd-wide"><span>주소</span><input class="nc-addr" placeholder="일정 지역 묶기에 씀" /></label>
        <label class="cd-field"><span>관리주체</span><input class="nc-owner" /></label>
        <label class="cd-field"><span>분야</span><select class="nc-field">${FIELDS.map((v) => `<option>${v}</option>`).join("")}</select></label>
        <label class="cd-field nc-kind-l" hidden><span>관급 종류</span><select class="nc-kind">${KINDS.map((v) => `<option${v === "일반" ? " selected" : ""}>${v}</option>`).join("")}</select></label>
        <label class="cd-field"><span>계약 구분</span><select class="nc-type"><option value="장기">장기·지속계약</option><option value="1회성">1회성·입찰계약</option></select></label>
      </div>
      <div class="mail-msg" hidden></div>
      <div class="mail-foot"><button type="button" class="nc-close">닫기</button><button type="button" class="mail-primary nc-save">만들기</button></div></div>`;
    document.body.appendChild(overlay);
    const q = (s) => overlay.querySelector(s);
    const close = () => overlay.remove();
    overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });
    q(".nc-close").addEventListener("click", close);
    const sectorNow = () => overlay.querySelector('input[name="nc-sector"]:checked').value;
    const onSector = async () => {
      const s = sectorNow();
      q(".nc-kind-l").hidden = s !== "관급";
      q(".nc-type").value = s === "민간" ? "장기" : "1회성";
      try { q(".nc-no").textContent = `번호 ${(await api(`/sitok/next-mgmt-no?sector=${encodeURIComponent(s)}`)).mgmt_no}`; } catch { q(".nc-no").textContent = ""; }
    };
    overlay.querySelectorAll('input[name="nc-sector"]').forEach((r) => r.addEventListener("change", onSector));
    const guess = () => { // 이름·관리주체로 뱃지 미리(서버 guess_badges와 같은 말 — 학교·유치원·교육청이면 학교)
      const t = `${q(".nc-name").value}${q(".nc-owner").value}`.replace(/\s/g, "");
      q(".nc-kind").value = /학교|유치원|교육청|교육지원청/.test(t) ? "학교" : "일반";
    };
    q(".nc-name").addEventListener("input", guess);
    q(".nc-owner").addEventListener("input", guess);
    onSector();
    q(".nc-name").focus();
    q(".nc-save").addEventListener("click", async () => {
      const s = sectorNow();
      try {
        const out = await apiPost(`${P}/facilities`, { sector: s, name: q(".nc-name").value, address: q(".nc-addr").value, owner_name: q(".nc-owner").value,
          badge_field: q(".nc-field").value, badge_kind: s === "관급" ? q(".nc-kind").value : "", contract_type: q(".nc-type").value });
        close();
        await load();
        const m = document.getElementById("sd-new-msg");
        m.className = "status ok";
        m.textContent = `✓ ${out.mgmt_no} ${out.name} 카드를 만들었습니다 — 보고서 자동화 시설물 목록에도 생겼습니다.`;
      } catch (err) {
        const m = q(".mail-msg");
        m.hidden = false;
        m.className = "mail-msg bad";
        m.textContent = err.message;
      }
    });
  }
  document.getElementById("sd-new-card").addEventListener("click", newCard);

  function contactLine(c, who, label) {
    const name = c[`${who}_manager`], phone = c[`${who}_phone`], mail = c[`${who}_email`];
    if (!name && !phone && !mail) return "";
    return `<div class="dc-meta dc-contact" data-who="${who}">${label} <b>${esc(name || "-")}</b>${mail ? ` · <a href="mailto:${esc(mail)}">${esc(mail)}</a>` : ""}</div>`;
  }

  function docLines(c) {
    const line = (label, done, text, href) => `<span class="dc-doc ${done ? "ok" : "idle"}"><b>${label}</b> ${href ? `<a href="${href}" target="_blank" rel="noopener">${esc(text)}</a>` : esc(text)}</span>`;
    const out = [];
    if (c.sector === "민간" && (c.made_at || !c.files["날인본.pdf"])) out.push(line("계약서", !!c.made_at, c.made_at ? `${c.made_at.slice(5)} 만듦` : "아직 안 만듦", c.files["계약서.pdf"] ? fileUrl(c, "계약서.pdf") : ""));
    out.push(line(c.sector === "민간" ? "날인본" : "계약서", c.files["날인본.pdf"], c.files["날인본.pdf"] ? "✓ 올림" : "안 올림", c.files["날인본.pdf"] ? fileUrl(c, "날인본.pdf") : ""));
    if (c.facility) out.push(line("보고서 쪽", !!c.report_contract_id, c.report_contract_id ? "✓ 계약 넣음" : "안 넣음"));
    if (c.sector === "관급") {
      for (const [k, lab] of [["start", "착수계"], ["done", "완료계"]]) {
        const g = c.gov[k];
        out.push(line(lab, g.pdf, g.at ? `${g.at.slice(5)} 만듦` : "아직 안 만듦",
          g.pdf ? `${BASE}/api${P}/contracts/${c.id}/gov/${k}.pdf?inline=true&v=${encodeURIComponent(g.at)}` : ""));
      }
    }
    return out.join("");
  }

  function row(c, inCard) {
    const el = document.createElement("div");
    el.className = `row dc-row${inCard ? " in-card" : ""}`;
    const meta = [c.client, c.contract_no, periodText(c), moneyText(c)].filter(Boolean).join(" · ");
    const year = c.sector === "관급" && (c.start_date || c.contract_date) ? `<span class="sd-year">${(c.start_date || c.contract_date).slice(0, 4)}년</span>` : "";
    const half = c.half ? `<span class="sd-half${c.half === "해당없음" ? " na" : ""}" title="${c.half_tag ? "직접 고른 반기" : "용역 기간으로 자동"}">${esc(c.half)}</span>` : "";
    el.innerHTML = `
      <div class="dc-main">
        <div class="dc-title">${inCard ? `${year}${half}` : `<span class="sd-chip ${c.sector === "민간" ? "civil" : "gov"}">${c.sector}</span>${half}`}${esc(c.title || (c.sector === "민간" && c.auto_title) || "(계약건명 없음 — 계약 정보를 채우세요)")}</div>
        <div class="dc-meta">${esc(meta)}</div>
        ${contactLine(c, "client", "계약 담당")}${contactLine(c, "site", "현장 담당")}
        ${inCard ? "" : `<div class="dc-site">${c.facility ? `현장 <a href="sitok-facility.html?id=${c.facility.id}">${esc(c.facility.name)}</a>` : '<span class="dc-nosite">시설물 카드에 안 넣음</span>'}
          <button type="button" class="dc-link">${c.facility ? "바꾸기" : "🔗 카드에 넣기"}</button></div>`}
      </div>
      <div class="dc-docs">${docLines(c)}</div>
      <div class="dc-actions">
        ${c.sector === "관급" ? '<button type="button" class="secondary sd-gov" data-kind="start">📑 착수계</button><button type="button" class="secondary sd-gov" data-kind="done">📑 완료계</button>' : ""}
        <button type="button" class="secondary sd-edit">${c.sector === "민간" ? "📝 계약서" : "계약 정보"}</button>
        <button type="button" class="secondary dc-del" title="계약 지우기">삭제</button>
      </div>`;
    el.querySelectorAll(".dc-contact").forEach((line) => {
      const call = siteLinkButtons(c[`${line.dataset.who}_phone`], "");
      if (call) line.appendChild(call);
    });
    el.querySelector(".sd-edit").addEventListener("click", () => openContract(c.id, c.sector));
    el.querySelectorAll(".sd-gov").forEach((b) => b.addEventListener("click", () => openSitokGov(c.id, b.dataset.kind, load)));
    const lk = el.querySelector(".dc-link");
    if (lk) lk.addEventListener("click", () => pickFacility(c, () => load()));
    el.querySelector(".dc-del").addEventListener("click", async () => {
      const pw = await dcAskPassword(`"${c.title || c.auto_title || "점검 계약"}"을(를) 지웁니다. 올린·만든 계약서 파일도 같이 지워집니다(보고서 쪽에 넣은 계약은 그대로). 되돌릴 수 없습니다.`);
      if (pw == null) return;
      try {
        await api(`${P}/contracts/${c.id}`, { method: "DELETE", body: JSON.stringify({ password: pw }) });
        load();
      } catch (err) {
        showError(errorEl, err);
        errorEl.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });
    return el;
  }

  // ---------- 현장(시설물) 연결 창 — 이름 비슷한 시설물이 위로 ----------
  async function pickFacility(c, onDone) {
    const overlay = document.createElement("div");
    overlay.className = "mail-overlay";
    overlay.style.zIndex = 1200; // 계약 창 위에
    overlay.innerHTML = '<div class="mail-box cd-pick" role="dialog" aria-modal="true"><div class="mail-wait">불러오는 중…</div></div>';
    document.body.appendChild(overlay);
    const box = overlay.querySelector(".mail-box");
    const close = () => { overlay.remove(); document.removeEventListener("keydown", onKey, true); };
    const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
    document.addEventListener("keydown", onKey, true);
    overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });
    let list;
    try {
      list = (await api(`${P}/contracts/${c.id}/candidates`)).facilities;
    } catch (err) {
      box.innerHTML = `<div class="mail-msg bad">${esc(err.message)}</div>`;
      return;
    }
    const curId = c.facility ? c.facility.id : null;
    box.innerHTML = `<div class="mail-head"><b>🔗 현장 연결</b><span class="mail-sub">${esc(c.title || c.auto_title || c.facility_name || "점검 계약")}</span></div>
      <input type="search" class="mail-input cd-pick-q" placeholder="시설물명·관리주체·주소로 찾기" autocomplete="off" />
      <div class="cd-pick-list"></div>
      <div class="mail-note">없으면 <a href="sitok-new.html">보고서 자동화 · 시특법에서 새 시설물 등록</a> 뒤 다시 연결하세요.</div>
      <div class="mail-foot">${curId ? '<button type="button" class="cd-unlink">연결 끊기</button>' : ""}<button type="button" class="cd-pick-close">닫기</button></div>`;
    const listEl = box.querySelector(".cd-pick-list");
    const draw = (q) => {
      const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
      const shown = list.filter((f) => words.every((w) => `${f.name} ${f.owner} ${f.address}`.toLowerCase().includes(w))).slice(0, 40);
      listEl.innerHTML = shown.length ? shown.map((f) => `<button type="button" class="cd-pick-item${f.id === curId ? " on" : ""}" data-id="${f.id}">
          <b>${esc(f.name)}</b><span class="mail-note">${esc([f.owner, f.address].filter(Boolean).join(" · "))}</span></button>`).join("")
        : '<div class="mail-note">맞는 시설물이 없습니다.</div>';
      listEl.querySelectorAll(".cd-pick-item").forEach((b) => b.addEventListener("click", () => link(Number(b.dataset.id))));
    };
    const link = async (fid) => {
      try {
        const out = await apiPost(`${P}/contracts/${c.id}/link`, { facility_id: fid });
        close();
        onDone(out);
      } catch (err) {
        listEl.insertAdjacentHTML("afterbegin", `<div class="mail-msg bad">${esc(err.message)}</div>`);
      }
    };
    const q = box.querySelector(".cd-pick-q");
    q.addEventListener("input", () => draw(q.value));
    box.querySelector(".cd-pick-close").addEventListener("click", close);
    const un = box.querySelector(".cd-unlink");
    if (un) un.addEventListener("click", () => link(null));
    draw("");
    q.focus();
  }

  // ---------- 계약 창 ----------
  async function openContract(id, sector, intro) {
    const overlay = document.createElement("div");
    overlay.className = "mail-overlay";
    overlay.innerHTML = '<div class="mail-box cd-box sd-box" role="dialog" aria-modal="true"><div class="mail-wait">불러오는 중…</div></div>';
    document.body.appendChild(overlay);
    const box = overlay.querySelector(".mail-box");
    let st, snapshot = "", filled = (intro && intro.filled) || [], busy = false;
    try {
      st = id ? await api(`${P}/contracts/${id}`) : await api(`${P}/contracts/blank?sector=${encodeURIComponent(sector)}`);
    } catch (err) {
      box.innerHTML = `<div class="mail-msg bad">${esc(err.message)}</div><div class="mail-foot"><button type="button" class="sd-close">닫기</button></div>`;
      box.querySelector(".sd-close").addEventListener("click", () => overlay.remove());
      return;
    }
    st.bldgs = (st.buildings || []).slice(); // 동별 금액(10/15) — 동이 둘 이상이면 회차마다 동별 금액, 회차 금액 = 합
    if (!id && intro && intro.card) { // 시설물 카드 안 [+ 계약] — 그 카드에 넣고 시설물 칸 미리 채움(10/15)
      const k = intro.card;
      st.facility_id = k.id;
      st.facility = { id: k.id, name: k.name, mgmt_no: k.mgmt_no };
      st.facility_name = st.facility_name || (k.members.length > 1 ? k.group_name || k.name : k.name);
      st.location = st.location || k.address || "";
      st.client = st.client || k.owner_name || "";
    }
    if (!id && !st.rounds.length && st.sector === "민간") { // 새 민간 계약: 올해·지금 반기·정기 한 줄(관급은 회차 줄 없음 — 반기는 용역 기간으로, 10/15)
      const now = new Date();
      st.rounds = [{ year: now.getFullYear(), half: now.getMonth() < 6 ? "상반기" : "하반기", kind: "정기", amount: null }];
    }

    const close = async () => {
      if (busy) return;
      if (JSON.stringify(body()) !== snapshot && (st.id || hasContent())) {
        const ok = await save(true);
        if (!ok) return;
      }
      overlay.remove();
      document.removeEventListener("keydown", onKey, true);
      load();
    };
    const onKey = (e) => { if (e.key === "Escape" && !document.querySelector(".cd-pick")) { e.stopPropagation(); close(); } };
    document.addEventListener("keydown", onKey, true);
    overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });

    const hasContent = () => TEXT.some((k) => k !== "guarantee" && k !== "delay_rate" && (st[k] || "").trim()) || st.rounds.some((r) => r.amount);
    const msg = (text, tone) => {
      const el = box.querySelector(".sd-msg");
      el.innerHTML = text;
      el.className = `mail-msg sd-msg ${tone || ""}`;
      el.hidden = !text;
    };

    // 화면 → st(다시 그리기 전에 늘 먼저)
    function sync() {
      box.querySelectorAll("[data-key]").forEach((i) => { st[i.dataset.key] = i.value; });
      if (box.querySelector(".sd-bldgs")) st.bldgs = [...box.querySelectorAll(".b-name")].map((i) => i.value.trim());
      if (box.querySelector(".sd-rounds")) {
        st.rounds = [...box.querySelectorAll(".sd-round")].map((r) => {
          const base = { year: num(r.querySelector(".r-year").value), half: r.querySelector(".r-half").value, kind: r.querySelector(".r-kind").value };
          const parts = [...r.querySelectorAll(".r-part")];
          if (!parts.length) return { ...base, amount: num(r.querySelector(".r-amt").value) };
          const pp = parts.map((i) => ({ name: st.bldgs[Number(i.dataset.b)] || "", amount: num(i.value) }));
          return { ...base, parts: pp, amount: pp.reduce((t, x) => t + (x.amount || 0), 0) };
        });
      }
      const chk = box.querySelector(".sd-open-chk");
      if (chk) st.open_ended = chk.checked;
      if (box.querySelector(".sd-unit-kind")) st.unit = { kind: box.querySelector(".sd-unit-kind").value, amount: num(box.querySelector(".sd-unit-amt").value) };
      const amt = box.querySelector(".sd-amount");
      if (amt) st.amount = num(amt.value);
    }
    function body() {
      sync();
      const b = { sector: st.sector, open_ended: !!st.open_ended, unit: st.unit || null, rounds: st.sector === "민간" ? st.rounds.filter((r) => r.year) : [], half_tag: st.half_tag || "" };
      if (!st.id && st.facility_id) b.facility_id = st.facility_id;
      for (const k of TEXT) b[k] = st[k] ?? "";
      for (const k of DATES) b[k] = st[k] || null;
      if (st.sector === "관급") b.amount = st.amount ?? null;
      return b;
    }
    async function ensure() { // 처음 저장·올리기 때 계약을 만듦
      if (st.id) return;
      const out = await apiPost(`${P}/contracts`, body());
      st = { ...out, rounds: out.rounds.length ? out.rounds : st.rounds };
    }
    async function save(quiet) {
      try {
        const b = body();
        if (!st.id) await ensure();
        else st = await api(`${P}/contracts/${st.id}`, { method: "PUT", body: JSON.stringify(b) });
        st.bldgs = (st.buildings || []).slice();
        draw(true);
        if (st.auto_card) msg(esc(st.auto_card) + (st.report_id ? ` — 이번 반기 회차까지 만들었습니다 <a href="sitok-round.html?report=${st.report_id}">회차 화면</a>` : ""), "ok"); // 저장 = 카드(10/15)
        else if (!quiet) msg("✓ 저장했습니다.", "ok");
        return true;
      } catch (err) {
        msg(esc(err.message), "bad");
        return false;
      }
    }

    const field = (key, text, opts = {}) => {
      const v = st[key] ?? "";
      return `<label class="cd-field${opts.wide ? " cd-wide" : ""}${filled.includes(key) ? " cd-ai" : ""}"><span>${text}${opts.em ? ` <em>${opts.em}</em>` : ""}</span>
        <input data-key="${key}" type="${opts.type || "text"}" value="${esc(v)}" placeholder="${esc(opts.ph || "")}" /></label>`;
    };
    const ct = (key, ph, type = "text") => `<input data-key="${key}" type="${type}" placeholder="${ph}" value="${esc(st[key] || "")}" aria-label="${ph}" />`;
    const upChip = (kind, label, file, hint) => `<div class="sd-up">
        <label class="drop-box drop-sm sd-up-box"><b>📎 ${label}</b><input type="file" data-up="${kind}" accept=".pdf,.hwp,.hwpx,.jpg,.jpeg,.png,application/pdf,image/*" hidden data-kr-file="skip" /></label>
        <span class="mail-note">${st.files && st.files[file] ? `<a href="${fileUrl(st, file)}" target="_blank" rel="noopener">✓ 올림 · 보기</a>` : hint}</span></div>`;

    function roundsBlock() {
      if (st.open_ended) {
        const u = st.unit || { kind: "정기", amount: null };
        return `<div class="sd-unit">매 반기 <select class="sd-unit-kind">${["정기", "정밀"].map((k) => `<option${u.kind === k ? " selected" : ""}>${k}</option>`).join("")}</select>
          금 <input class="sd-unit-amt sd-won" inputmode="numeric" value="${won(u.amount)}" placeholder="550,000" /> 원 <span class="mail-note">(VAT포함 · 총합은 안 씀)</span></div>`;
      }
      const multi = st.bldgs.length >= 2;
      const partOf = (r, j) => { const q = (r.parts || []).find((x) => x.name === st.bldgs[j]); return q ? q.amount : (j === 0 && !r.parts ? r.amount : null); };
      const rows = st.rounds.map((r, i) => `<div class="sd-round${multi ? " multi" : ""}" data-i="${i}">
          <input class="r-year" inputmode="numeric" value="${r.year || ""}" aria-label="연도" /><span>년</span>
          <select class="r-half" aria-label="반기">${["상반기", "하반기"].map((h) => `<option${r.half === h ? " selected" : ""}>${h}</option>`).join("")}</select>
          <select class="r-kind" aria-label="점검 종류">${["정기", "정밀"].map((k) => `<option${r.kind === k ? " selected" : ""}>${k}</option>`).join("")}</select>
          ${multi ? `<span class="r-parts">${st.bldgs.map((b, j) => `<label class="r-part-l"><small>${esc(b || `${j + 1}동`)}</small><input class="r-part sd-won" data-b="${j}" inputmode="numeric" value="${won(partOf(r, j))}" placeholder="금액" aria-label="${esc(b)} 금액" /></label>`).join("")}
              <span class="r-sum">= ${won(r.amount) || 0}원</span></span>`
            : `<span class="r-amt-wrap">금 <input class="r-amt sd-won" inputmode="numeric" value="${won(r.amount)}" placeholder="금액" aria-label="금액" /> 원</span>`}
          <button type="button" class="cd-x r-del" title="이 회차 빼기">✕</button></div>`).join("");
      const total = st.rounds.reduce((s, r) => s + (r.amount || 0), 0);
      const bl = multi ? `<div class="sd-bldgs"><span class="mail-note">동 이름 — 대가내역서·계약서 금액 아래 줄·FMS 동별 금액</span>
          ${st.bldgs.map((b, j) => `<span class="b-chip"><input class="b-name" value="${esc(b)}" placeholder="${j + 1}동" aria-label="동 이름" /><button type="button" class="cd-x b-del" data-b="${j}" title="이 동 빼기">✕</button></span>`).join("")}
          <button type="button" class="b-add">+ 동</button></div>`
        : `<button type="button" class="sd-multi" title="여러 동을 한 계약으로 — 회차마다 동별 금액을 적고 합계가 회차 금액이 됩니다">🏢 동이 여러 개 — 동별 금액</button>`;
      return `${bl}<div class="sd-rounds">${rows || '<div class="mail-note">회차가 없습니다 — [+ 회차]로 넣으세요.</div>'}</div>
        <div class="sd-round-acts"><button type="button" class="sd-add">+ 회차</button>
          <button type="button" class="sd-fill" title="계약 시작일~종료일 사이 반기를 전부 넣음(있는 줄은 그대로)">계약기간으로 회차 채우기</button>
          <span class="sd-total">${total ? `총 합 금 ${won(total)}원 (VAT포함)` : ""}</span></div>`;
    }

    // clean = 서버에서 막 받은 상태(닫을 때 "고친 게 있나" 비교 기준) — 화면에서만 바꾼 뒤 다시 그릴 땐 기준을 안 바꿈
    function draw(clean) {
      const civil = st.sector === "민간";
      const f = st.facility;
      box.innerHTML = `
        <div class="mail-head"><b>${civil ? "📝 민간 계약서" : "📑 관급 계약"}</b>
          <span class="mail-sub">${esc(st.title || (civil && st.facility_name && st.auto_title) || "새 계약")}</span>
          <div class="cd-site-line mail-sub">현장: ${f ? `<a href="sitok-facility.html?id=${f.id}">${esc(f.name)}</a>` : '<span class="dc-nosite">연결 안 됨</span>'}
            <button type="button" class="cd-link-btn sd-link">${f ? "다른 카드로" : "🔗 카드 고르기"}</button>
            <span class="sd-auto-note">${f ? (st.report_contract_id ? "· 보고서 쪽 계약 ✓" : "· 계약서를 올리면 저장할 때 보고서 쪽 계약까지 자동")
              : "· 계약서를 올리면 저장할 때 시설물 카드에 자동으로 들어갑니다(같은 시설물 카드가 있으면 그 카드로)"}</span></div></div>
        <div class="sd-sector">${["민간", "관급"].map((s) => `<label><input type="radio" name="sd-sector" value="${s}"${st.sector === s ? " checked" : ""} /> ${s === "민간" ? "민간 — 계약서를 우리가 작성" : "관급 — 나라장터 계약서"}</label>`).join("")}</div>
        <div class="mail-label">서류 올리기 <span class="mail-note">— 읽어서 빈 칸을 채웁니다(PDF·한글·사진, 끌어다 놓아도 됨)</span></div>
        <div class="sd-ups${civil ? "" : " two"}">
          ${upChip("ledger", "시설물관리대장", "시설물관리대장.pdf", "시설물명·위치·제원·관리주체")}
          ${civil ? upChip("bizreg", "사업자등록증", "사업자등록증.pdf", "관리주체·대표자·번호·주소") : ""}
          ${civil ? upChip(st.made_at ? "signed" : "existing", "날인본(도장 찍은 계약서)", "날인본.pdf", st.made_at ? "도장 찍어 받은 계약서 보관" : "이미 만든 계약서면 계약 칸까지 읽음")
            : upChip("g2b", "나라장터 계약서", "날인본.pdf", "읽어서 계약 칸을 채움(다시 올리면 읽은 칸만 바뀜)")}
        </div>
        <div class="mail-label">${civil ? "관리주체(갑)" : "발주처"}</div>
        <div class="cd-grid">
          ${field("client", civil ? "관리주체" : "발주처", { ph: civil ? "예: 청천영진아파트(위탁관리회사:미래티엠에스(주))" : "" })}
          ${civil ? field("client_rep", "대표자 줄", { em: "서명 칸", ph: "예: 관리사무소장 김춘화" }) : field("client_rep", "대표자")}
          ${field("client_biz_no", "사업자등록번호")}${field("client_address", "주소")}
        </div>
        <div class="mail-label">시설물</div>
        <div class="cd-grid">
          ${field("facility_name", "시설물명")}${field("spec", "제원", { em: "비우면 줄을 뺌", ph: "예: 연면적 19,071.7m²" })}
          ${field("location", "위치", { wide: true })}
        </div>
        ${civil ? `<div class="mail-label${filled.includes("rounds") || filled.includes("unit") ? " sd-ai" : ""}">계약 회차 · 금액 <span class="mail-note">— 반기마다 한 줄(VAT포함). 계약서 "계약금액"에 회차마다 한 줄 + 총 합</span></div>
          <label class="sd-open"><input type="checkbox" class="sd-open-chk"${st.open_ended ? " checked" : ""} /> 끝 없는 계약 — 계약기간 "~ 계약 해지 시까지", 금액은 매 반기 단가만</label>
          ${roundsBlock()}` : ""}
        <div class="mail-label">계약</div>
        <div class="cd-grid">
          ${civil ? "" : `${field("contract_no", "계약번호")}<label class="cd-field"><span>계약금액(원)</span><input class="sd-amount sd-won" inputmode="numeric" value="${won(st.amount)}" /></label>`}
          ${field("contract_date", "계약일", { type: "date" })}${field("start_date", "계약 시작일", { type: "date" })}
          ${civil && st.open_ended ? '<div class="cd-field"><span>계약 종료일</span><div class="cd-plain">계약 해지 시까지</div></div>' : field("end_date", "계약 종료일", { type: "date" })}
          ${civil ? field("doc_no", "문서번호", { em: "비우면 KFSC-연도-월일(계약일)", ph: st.auto_doc_no }) : ""}
          ${field("title", civil ? "계약건명" : "용역명", { wide: true, em: civil ? "비우면 자동" : "", ph: civil ? st.auto_title : "" })}
          <label class="cd-field"><span>반기 표시 <em>시설물 카드</em></span><select data-key="half_tag">
            <option value="">자동${st.half_auto ? `(${esc(st.half_auto)})` : ""}</option>${["상반기", "하반기", "상·하반기", "해당없음"].map((h) => `<option${st.half_tag === h ? " selected" : ""}>${h}</option>`).join("")}</select></label>
          ${civil ? `${field("guarantee", "계약보증액")}${field("delay_rate", "지체상금율")}` : ""}
        </div>
        <div class="mail-label">담당자 <span class="mail-note">— 계약 담당·현장 담당(관리소장 등)</span></div>
        <div class="cd-contacts">
          <span></span><span class="cd-ct-h">이름</span><span class="cd-ct-h">연락처</span><span class="cd-ct-h">이메일</span>
          <b>계약 담당</b>${ct("client_manager", "이름")}${ct("client_phone", "연락처", "tel")}${ct("client_email", "이메일", "email")}
          <b>현장 담당</b>${ct("site_manager", "이름")}${ct("site_phone", "연락처", "tel")}${ct("site_email", "이메일", "email")}
        </div>
        <div class="cd-grid">${field("memo", "메모", { wide: true })}</div>
        <div class="mail-msg sd-msg" hidden></div>
        ${civil && st.made_at ? `<div class="cd-made">계약서 만든 때 ${esc(st.made_at)} — 고친 뒤 다시 만들면 바뀝니다</div>` : ""}
        <div class="mail-foot cd-foot">
          ${civil && st.files && st.files["계약서.hwpx"] ? `<a href="${fileUrl(st, "계약서.hwpx")}">한글 받기</a>` : ""}
          ${civil && st.files && st.files["계약서.pdf"] ? `<a href="${fileUrl(st, "계약서.pdf")}" target="_blank" rel="noopener">PDF 보기</a>` : ""}
          <button type="button" class="sd-close">닫기</button>
          <button type="button" class="sd-save">저장</button>
          ${st.files && st.files["대가내역서.pdf"] ? `<a href="${fileUrl(st, "대가내역서.pdf")}" target="_blank" rel="noopener">대가내역서 PDF</a>` : ""}
          ${st.files && st.files["대가내역서.xlsx"] ? `<a href="${fileUrl(st, "대가내역서.xlsx")}">엑셀</a>` : ""}
          <button type="button" class="sd-daega" title="계약 회차·동별 금액으로 대가내역서(형 양식) — FMS e-보고서에도 씀">📑 대가내역서</button>
          ${civil ? '<button type="button" class="mail-primary sd-make">📝 계약서 만들기</button>'
            : '<button type="button" class="sd-to-gov" data-kind="start">📑 착수계</button><button type="button" class="mail-primary sd-to-gov" data-kind="done">📑 완료계</button>'}
        </div>`;
      wire();
      if (clean) snapshot = JSON.stringify(body());
    }

    function wire() {
      box.querySelector(".sd-close").addEventListener("click", close);
      box.querySelector(".sd-save").addEventListener("click", () => save(false));
      box.querySelector(".sd-daega").addEventListener("click", async () => {
        if (!(await save(true))) return;
        busy = true;
        msg("대가내역서 만드는 중…", "");
        try {
          const out = await apiPost(`${P}/contracts/${st.id}/daega`, body());
          st = out;
          st.bldgs = (st.buildings || []).slice();
          draw(true);
          msg(out.warning ? esc(out.warning) : `✓ 대가내역서를 만들었습니다 — <a href="${fileUrl(st, "대가내역서.pdf")}" target="_blank" rel="noopener">PDF 보기</a>`, out.warning ? "warn" : "ok");
        } catch (err) {
          msg(esc(err.message), "bad");
        } finally {
          busy = false;
        }
      });
      box.querySelectorAll('input[name="sd-sector"]').forEach((r) => r.addEventListener("change", () => { sync(); st.sector = r.value; filled = []; draw(); }));
      box.querySelectorAll(".sd-won").forEach((i) => i.addEventListener("blur", () => { i.value = won(num(i.value)); }));
      const chk = box.querySelector(".sd-open-chk");
      if (chk) chk.addEventListener("change", () => { sync(); draw(); });
      const add = box.querySelector(".sd-add");
      if (add) add.addEventListener("click", () => {
        sync();
        const last = st.rounds[st.rounds.length - 1];
        const now = new Date();
        st.rounds.push(last ? { year: last.half === "하반기" ? (last.year || now.getFullYear()) + 1 : last.year, half: last.half === "하반기" ? "상반기" : "하반기", kind: last.kind, amount: last.amount, ...(last.parts ? { parts: last.parts.map((x) => ({ ...x })) } : {}) }
          : { year: now.getFullYear(), half: "상반기", kind: "정기", amount: null });
        draw();
      });
      const fill = box.querySelector(".sd-fill");
      if (fill) fill.addEventListener("click", () => {
        sync();
        if (!st.start_date || !st.end_date) { msg("계약 시작일·종료일을 먼저 넣으세요(아래 [계약] 칸).", "warn"); return; }
        const [sy, sm] = st.start_date.split("-").map(Number), [ey, em] = st.end_date.split("-").map(Number);
        const last = st.rounds[st.rounds.length - 1] || { kind: "정기", amount: null };
        const out = [];
        for (let y = sy; y <= ey; y++) {
          for (const h of ["상반기", "하반기"]) {
            if ((y === sy && h === "상반기" && sm > 6) || (y === ey && h === "하반기" && em <= 6)) continue;
            out.push(st.rounds.find((r) => r.year === y && r.half === h) || { year: y, half: h, kind: last.kind, amount: last.amount, ...(last.parts ? { parts: last.parts.map((x) => ({ ...x })) } : {}) });
          }
        }
        if (out.length > 40) { msg("계약기간이 너무 깁니다(20년 넘음) — 끝 없는 계약이면 위 [끝 없는 계약]을 고르세요.", "warn"); return; }
        st.rounds = out;
        draw();
        msg(`${out.length}회차를 넣었습니다 — 정밀 회차와 금액을 확인하세요.`, "ok");
      });
      box.querySelectorAll(".r-del").forEach((b) => b.addEventListener("click", () => { sync(); st.rounds.splice(Number(b.closest(".sd-round").dataset.i), 1); draw(); }));
      box.querySelectorAll(".sd-round input, .sd-round select").forEach((i) => i.addEventListener("change", () => {
        sync();
        const total = st.rounds.reduce((s, r) => s + (r.amount || 0), 0);
        box.querySelector(".sd-total").textContent = total ? `총 합 금 ${won(total)}원 (VAT포함)` : "";
        box.querySelectorAll(".sd-round").forEach((row, k) => { const el = row.querySelector(".r-sum"); if (el) el.textContent = `= ${won(st.rounds[k].amount) || 0}원`; });
      }));
      const multiBtn = box.querySelector(".sd-multi");
      if (multiBtn) multiBtn.addEventListener("click", () => { // 동별 금액 켜기 — 묶음 동 이름(없으면 시설물명·2동), 지금 금액은 첫 동에
        sync();
        st.bldgs = (st.group_names || []).length >= 2 ? st.group_names.slice() : [st.facility_name || "1동", "2동"];
        st.rounds = st.rounds.map((r) => ({ ...r, parts: st.bldgs.map((b, j) => ({ name: b, amount: j === 0 ? r.amount : 0 })) }));
        draw();
        msg("동별 금액을 켰습니다 — 동 이름과 회차마다 동별 금액을 넣으세요(회차 금액은 합계).", "ok");
      });
      const bAdd = box.querySelector(".b-add");
      if (bAdd) bAdd.addEventListener("click", () => { sync(); st.bldgs.push(`${st.bldgs.length + 1}동`); draw(); });
      box.querySelectorAll(".b-del").forEach((b) => b.addEventListener("click", () => {
        sync();
        const j = Number(b.dataset.b), name = st.bldgs[j];
        st.bldgs.splice(j, 1);
        st.rounds = st.rounds.map((r) => {
          const parts = (r.parts || []).filter((x) => x.name !== name);
          const sum = parts.reduce((t, x) => t + (x.amount || 0), 0);
          return parts.length >= 2 ? { ...r, parts, amount: sum } : { year: r.year, half: r.half, kind: r.kind, amount: sum };
        });
        if (st.bldgs.length < 2) st.bldgs = [];
        draw();
      }));
      box.querySelectorAll(".b-name").forEach((inp) => inp.addEventListener("change", () => { // 동 이름을 바꾸면 회차 줄의 이름도
        const j = [...box.querySelectorAll(".b-name")].indexOf(inp), old = st.bldgs[j];
        sync();
        st.rounds = st.rounds.map((r) => ({ ...r, parts: (r.parts || []).map((x) => (x.name === old ? { ...x, name: st.bldgs[j] } : x)) }));
        draw();
      }));
      box.querySelectorAll("input[data-up]").forEach((inp) => {
        inp.addEventListener("change", () => upload(inp));
        enableFileDrop(inp.closest(".sd-up-box"), inp);
      });
      box.querySelector(".sd-link").addEventListener("click", async () => {
        if (!(await save(true))) return;
        pickFacility(st, (out) => { st = out; draw(true); msg(out.facility ? `✓ 현장 "${esc(out.facility.name)}"에 연결했습니다.` : "연결을 끊었습니다.", "ok"); });
      });
      box.querySelectorAll(".sd-to-gov").forEach((b) => b.addEventListener("click", async () => { // 관급: 저장하고 착수계·완료계 창
        if (!(await save(true))) return;
        openSitokGov(st.id, b.dataset.kind, async () => { st = await api(`${P}/contracts/${st.id}`); draw(true); });
      }));
      const make = box.querySelector(".sd-make");
      if (make) make.addEventListener("click", async () => {
        busy = true;
        make.disabled = true;
        make.textContent = "만드는 중… (한글 → PDF 30초쯤)";
        try {
          const b = body();
          if (!st.id) await ensure();
          const out = await apiPost(`${P}/contracts/${st.id}/make`, b);
          st = out;
          filled = [];
          draw(true);
          msg(out.warning ? esc(out.warning) : `✓ 계약서를 만들었습니다 — <a href="${fileUrl(st, "계약서.pdf")}" target="_blank" rel="noopener">PDF 보기</a> · <a href="${fileUrl(st, "계약서.hwpx")}">한글 받기</a>`,
            out.warning ? "warn" : "ok");
        } catch (err) {
          msg(esc(err.message), "bad");
          make.disabled = false;
          make.textContent = "📝 계약서 만들기";
        } finally {
          busy = false;
        }
      });
    }

    async function upload(inp) {
      const file = inp.files[0];
      inp.value = "";
      if (!file) return;
      const kind = inp.dataset.up;
      busy = true;
      msg(kind === "signed" ? "올리는 중…" : "읽는 중… (AI로 읽느라 20~40초)", "");
      try {
        const b = body();
        if (!st.id) await ensure();
        else st = await api(`${P}/contracts/${st.id}`, { method: "PUT", body: JSON.stringify(b) });
        const fd = new FormData();
        fd.append("file", file);
        const out = await apiUpload(`${P}/contracts/${st.id}/upload/${kind}`, fd);
        st = out;
        filled = out.filled || [];
        draw(true);
        const dup = out.duplicate_of; // 같은 계약번호가 이미 있음(10/15 — 창을 닫고 다시 올려 계약이 둘 생기던 것)
        if (dup) {
          msg(`⚠ 같은 계약번호 계약이 이미 있습니다 — ${dup.facility ? `<b>${esc(dup.facility.mgmt_no)} ${esc(dup.facility.name)}</b> 카드` : "카드에 안 넣은 계약"}(${esc(dup.title || "")}).
            이 계약은 지우고 그 계약을 쓰세요. <button type="button" class="sd-dup-del">🗑 이 계약 지우고 닫기</button>`, "warn");
          box.querySelector(".sd-dup-del").addEventListener("click", async () => {
            const pw = await dcAskPassword("같은 계약번호로 새로 만든 이 계약을 지웁니다(올린 파일까지). 이미 있는 계약은 그대로입니다.");
            if (pw == null) return;
            try {
              await api(`${P}/contracts/${st.id}`, { method: "DELETE", body: JSON.stringify({ password: pw }) });
              busy = false;
              overlay.remove();
              document.removeEventListener("keydown", onKey, true);
              load();
            } catch (err) { msg(esc(err.message), "bad"); }
          });
        } else if (out.error) msg(esc(out.error), "warn");
        else if (out.auto_card) msg(`${filled.length ? `✓ 읽어서 채움: ${filled.map((k) => LABEL[k] || k).join(" · ")}<br>` : ""}${esc(out.auto_card)}`, "ok");
        else if (kind === "signed") msg("✓ 올렸습니다.", "ok");
        else msg(filled.length ? `✓ 읽어서 채움: ${filled.map((k) => LABEL[k] || k).join(" · ")} — 노란 칸을 확인하세요.` : "읽었지만 새로 채울 빈 칸이 없었습니다.", filled.length ? "ok" : "");
      } catch (err) {
        msg(esc(err.message), "bad");
      } finally {
        busy = false;
      }
    }

    draw(true);
    if (intro && intro.message) msg(intro.message, intro.tone || "ok");
  }

  // ---------- 위쪽 버튼 ----------
  document.getElementById("sd-search").addEventListener("input", (e) => { view.q = e.target.value; render(); });
  document.getElementById("sd-new-civil").addEventListener("click", () => openContract(null, "민간"));
  document.getElementById("sd-new-gov").addEventListener("click", () => openContract(null, "관급"));

  // 이미 만든 민간 계약서 → 읽어서 새 계약(파일을 못 읽으면 아무것도 안 만듦)
  const existing = document.getElementById("sd-existing");
  existing.addEventListener("change", async () => {
    const file = existing.files[0];
    existing.value = "";
    if (!file) return;
    const m = document.getElementById("sd-new-msg");
    m.textContent = "계약서를 읽는 중… (AI로 읽느라 20~40초)";
    m.className = "status";
    try {
      const fd = new FormData();
      fd.append("file", file);
      const out = await apiUpload(`${P}/contracts/from-existing`, fd);
      m.textContent = out.duplicate_of ? `⚠ 같은 시설물·관리주체 계약이 이미 있습니다: ${out.duplicate_of.title} — 필요 없으면 새로 만든 쪽을 지우세요.` : "";
      m.className = out.duplicate_of ? "status bad" : "status";
      await load();
      openContract(out.id, "민간", { filled: out.filled, message: out.error ? esc(out.error)
        : `✓ 계약서를 읽어 새 계약으로 등록했습니다(날인본으로 보관) — 노란 칸을 확인하세요.`, tone: out.error ? "warn" : "ok" });
    } catch (err) {
      m.textContent = err.message;
      m.className = "status bad";
    }
  });
  enableFileDrop(document.querySelector(".sd-drop"), existing);

  // 민간 계약서 양식 받기·올리기
  document.getElementById("sd-tpl-get").href = `${BASE}/api${P}/template`;
  const tpl = document.getElementById("sd-tpl-file");
  tpl.addEventListener("change", async () => {
    const file = tpl.files[0];
    tpl.value = "";
    if (!file) return;
    const m = document.getElementById("sd-tpl-msg");
    m.textContent = "올리는 중…";
    try {
      const fd = new FormData();
      fd.append("file", file);
      const out = await apiUpload(`${P}/template`, fd);
      m.textContent = `✓ ${out.updated} 새 양식으로 바꿨습니다(예전 양식은 보관).`;
    } catch (err) {
      m.textContent = err.message;
    }
  });
  enableFileDrop(tpl.closest(".cd-upload"), tpl);

  load();
  // 새 점검 대상 등록 "계약서가 아직 없음"(sitok-new.html, 10/14)에서 오면 바로 민간 계약서 창
  const want = new URLSearchParams(location.search).get("new");
  if (want === "civil") openContract(null, "민간", { message: "계약서를 만들 시설물의 <b>시설물관리대장</b>과 발주처 <b>사업자등록증</b>을 올리면 칸이 채워집니다. 회차·금액을 넣고 [📝 계약서 만들기] → 위 [🏢 시설물 카드 만들어 넣기]를 누르면 시설물 카드와 이번 반기 회차가 생깁니다.", tone: "ok" });
})();
