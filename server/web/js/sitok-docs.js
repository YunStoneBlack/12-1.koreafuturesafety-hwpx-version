// ---------- 서류 자동화 · 시특법 — 계약 목록(sitok-docs.html, 2026-10-12) ----------
// API server/api/routers/sitok_docs.py(/sitok/docs). 산안법(docs.html)처럼 보고서 쪽과 따로, 현장(시설물) 연결(민간·관급 둘 다 — 사용자 10/12).
// 위: 검색 + [+ 민간 계약서 만들기] [+ 관급 계약] + 이미 만든 민간 계약서를 끌어다 놓기(읽어서 새 계약). 칸(전체·민간·관급·현장 연결 안 됨)을 누르면 거름.
// 한 줄: 계약건명 · 관리주체·기간·금액 · 계약/현장 담당 · 현장(연결/[🔗 현장 연결]) · 계약서·날인본·보고서 쪽 상태 · [열기][삭제].
// 창: 서류 올리기(관리대장·사업자등록증·날인본) → 관리주체 → 시설물 → 계약 회차(연도·반기·정기/정밀·금액) 또는 계약 해지 시까지(매 반기 단가)
//     → 계약(계약일·기간·문서번호·계약건명) → 담당자 → [저장] [📝 계약서 만들기]. 닫으면 고친 내용 저장.
// 관급(2단계): 나라장터 계약서를 올리면 읽어서 칸 채움 → [📑 착수계] [📑 완수계] 창(js/sitok-docs-gov.js).
// 10/15 민재형 문서번호 일치화: 목록 = 시설물 카드(번호 민간-N·관급-N — 보고서 자동화 시설물과 같은 카드·번호, 묶인 동은 카드 하나).
//   카드 안에 민간은 계약서가 차례로, 관급은 착수계(계약)가 연도별로 쌓임. 계약마다 반기 표시(상반기·하반기·상·하반기·해당없음 — 기간으로 자동, 내진 = 해당없음).
//   [+ 새 시설물 카드] = 보고서 자동화에도 같은 번호로 바로 생김. 뱃지(분야·관급 종류) 칩 = 개수·거르기. 카드에 안 넣은 계약은 맨 아래.

(function () {
  const errorEl = document.getElementById("error");
  const P = "/sitok/docs";
  // 서류 자동화 › 내진성능평가(10/28 사용자 "시특법이랑 동일하게") — 같은 화면, <body data-docs-field="seismic">면 내진 계약끼리(app.js가 요청 머리를 붙임).
  // 카드 = 내진성능평가 건(이름 누르면 건 화면), 계약은 반기 회차 없이 금액 한 칸, 민간 양식 따로, 계약서를 올려 저장하면 같은 건(없으면 새 건)에 용역 정보·용역계약서.
  const SEIS = document.body.dataset.docsField === "seismic";
  const placeUrl = (id, rid) => (SEIS ? (rid ? `seismic-project.html?id=${rid}` : "seismic.html") : `sitok-facility.html?id=${id}`);
  const PLACE_TIP = SEIS ? "보고서 자동화 · 내진성능평가 건 화면" : "보고서 자동화 · 시설물 화면";
  const view = { tab: "", q: "", field: "", kind: "" };
  let all = [];
  let cards = [];
  const SORT_KEY = "kfsc-report:sitok-docs-sort";
  let sort = { mode: "no", desc: true };
  try { sort = { ...sort, ...JSON.parse(localStorage.getItem(SORT_KEY) || "{}") }; } catch { /* 기억 못 하면 기본 */ }

  const esc = mailEsc;
  const HALF_OPTS = ["상반기", "하반기", "해빙기", "우기", "동절기"]; // 연 3회(D·E등급) = 해빙기·우기·동절기(10/16)
  const NEXT_HALF = { 상반기: ["하반기", 0], 하반기: ["상반기", 1], 해빙기: ["우기", 0], 우기: ["동절기", 0], 동절기: ["해빙기", 1] }; // [다음 시기, 해 더하기]
  // 회차 종류 — 정밀 = 정밀안전점검, 진단 = 정밀안전진단(1종, 10/20 민재형 — 도래주기는 아래 📅 칸·server/sitok/cycle.py)
  const KIND_OPTS = ["정기", "정밀", "진단"];
  const KIND_WORD = { 정기: "정기안전점검", 정밀: "정밀안전점검", 진단: "정밀안전진단" };
  const HALF_END_OF_YEAR = new Set(["하반기", "동절기"]);
  const halfStart = (y, h) => `${y}-${HALF_END_OF_YEAR.has(h) ? "07-01" : "01-01"}`;
  const halfEnd = (y, h) => `${y}-${HALF_END_OF_YEAR.has(h) ? "12-31" : "06-30"}`;
  // 카드의 가장 최근 계약(마지막 회차가 가장 늦은 것) — [+ 계약서]가 내용을 가져옴(10/20 민재형)
  const lastRoundKey = (c) => Math.max(0, ...(c.rounds || []).map((r) => (r.year || 0) * 10 + HALF_OPTS.indexOf(r.half)));
  const latestCon = (list) => list.slice().sort((a, b) => lastRoundKey(b) - lastRoundKey(a) || (b.end_date || "").localeCompare(a.end_date || "") || b.id - a.id)[0] || null;
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
  const cardOf = (c) => { // 계약이 덮는 시설물(여럿이면 아무거나 — 0052)이 든 카드
    const ids = (c.facility_ids && c.facility_ids.length ? c.facility_ids : c.facility ? [c.facility.id] : []);
    return ids.length ? cards.find((k) => k.members.some((m) => ids.includes(m.id))) || null : null;
  };
  const unitsOf = (k) => k.units || [{ id: k.id, mgmt_no: k.mgmt_no, name: k.name, members: k.members }];
  const contractsOf = (k) => all.filter((c) => cardOf(c) === k)
    .sort((a, b) => (a.start_date || a.contract_date || "9999").localeCompare(b.start_date || b.contract_date || "9999") || a.id - b.id); // 차례로 쌓임(옛것 위)
  const noKey = (k) => { // "관급-3" < "민간-1"(구분끼리, 그 안에서 번호), 그 밖 번호는 맨 뒤 — "관급-6-2"는 6으로
    const m = String(k.mgmt_no || "").match(/^(관급|민간)-0*(\d+)(?:-\d+)?$/);
    const y = String(k.mgmt_no || "").match(/^(\d{2})-0*(\d+)$/); // 내진성능평가 건 "26-1"(연도 → 번호, 10/29)
    return m ? (m[1] === "관급" ? 1e8 : 2e8) + Number(m[2]) : y ? 1e8 + Number(y[1]) * 1e4 + Number(y[2]) : 3e8 + k.id;
  };
  const byNo = (a, b) => { const x = noKey(a), y = noKey(b); return Math.floor(x / 1e8) - Math.floor(y / 1e8) || (sort.desc ? y - x : x - y); };
  const sortCards = (list) => (sort.mode === "viewed" ? list.sort((a, b) => (b.viewed_at || "").localeCompare(a.viewed_at || "") || byNo(a, b)) : list.sort(byNo));
  const cardName = (k) => { // 여러 개면 "첫 시설물 등 N개소"(10/16 민재형 — 외 몇 개 말고 전체 개수, 동·시설물 모두 셈)
    const all = unitsOf(k).flatMap((u) => u.members);
    return all.length > 1 ? `${all[0].name} 등 ${all.length}개소` : k.name;
  };
  const cardText = (k) => [k.mgmt_no, cardName(k), k.address, k.owner_name, ...k.members.map((m) => m.name),
    ...contractsOf(k).flatMap((c) => [c.title, c.auto_title, c.client, c.contract_no, c.client_manager, c.site_manager])].join(" ").toLowerCase();
  const conText = (c) => `${c.title} ${c.auto_title} ${c.client} ${c.facility_name} ${c.contract_no} ${c.client_manager} ${c.site_manager}`.toLowerCase();
  const TABS = [["", "전체", "시설물 카드", (k) => true], ["민간", "민간", "계약서를 우리가 작성", (k) => k.sector === "민간"],
    ["관급", "관급", "나라장터 계약 · 착수계", (k) => k.sector === "관급"]];
  const FIELDS = ["건축", "토목", "건축·토목"], KINDS = ["학교", "일반"]; // 내진성능평가는 따로(10/15 밤)
  const badgeOk = (k) => (!view.field || k.badge_field === view.field) && (!view.kind || k.badge_kind === view.kind);

  function render() {
    const loose = all.filter((c) => !cardOf(c));
    if (view.tab === "loose" && !loose.length) view.tab = "";
    const looseBtn = document.getElementById("sd-loose"); // 숫자 카드 4개는 목록 머리 [전체 | 민간 | 관급]과 겹쳐 뺌(10/16) — 카드에 안 넣은 계약만 있을 때 알림
    looseBtn.hidden = !loose.length && view.tab !== "loose";
    looseBtn.classList.toggle("on", view.tab === "loose");
    looseBtn.textContent = view.tab === "loose" ? "← 시설물 카드로" : `⚠ 카드에 안 넣은 계약 ${loose.length}건`;
    document.querySelectorAll(".sd-sector button").forEach((b) => b.classList.toggle("on", b.dataset.sector === view.tab));
    // 뱃지 칩 — 지금 구분 안에서 개수, 누르면 그것만(한 번 더 = 풀기)
    const inTab = cards.filter((k) => !view.tab || view.tab === "loose" || k.sector === view.tab);
    const chip = (dim, v) => {
      const n = inTab.filter((k) => (dim === "field" ? k.badge_field : k.badge_kind) === v).length;
      return `<button type="button" class="sk-badge-f b-${dim}${view[dim] === v ? " on" : ""}" data-dim="${dim}" data-v="${esc(v)}" aria-pressed="${view[dim] === v}">${esc(v)} <b>${n}</b></button>`;
    };
    const bEl = document.getElementById("sd-badges");
    bEl.hidden = SEIS; // 내진 건은 분야·관급 종류 뱃지 없음
    bEl.innerHTML = SEIS ? "" : `<span class="sk-badge-l">분야</span>${FIELDS.map((v) => chip("field", v)).join("")}` +
      (view.tab === "민간" ? "" : `<span class="sk-badge-l">관급</span>${KINDS.map((v) => chip("kind", v)).join("")}`) +
      (view.field || view.kind ? '<button type="button" class="sk-badge-f sk-badge-clear" title="분야·관급 거르기 풀기">✕ 전체 보기</button>' : "");
    bEl.querySelectorAll(".sk-badge-f[data-dim]").forEach((b) => b.addEventListener("click", () => { view[b.dataset.dim] = view[b.dataset.dim] === b.dataset.v ? "" : b.dataset.v; render(); }));
    bEl.querySelector(".sk-badge-clear")?.addEventListener("click", () => { view.field = view.kind = ""; render(); });
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
    title.textContent = SEIS ? "내진성능평가 건" : "시설물 카드";
    const ok = TABS.find((t) => t[0] === view.tab)[3];
    const shown = sortCards(cards.filter((k) => ok(k) && badgeOk(k) && words.every((w) => cardText(k).includes(w))));
    document.getElementById("sd-count").textContent = `${shown.length}곳`;
    if (!shown.length) {
      list.innerHTML = `<div class="empty-note">${SEIS ? (cards.length ? "맞는 내진성능평가 건이 없습니다." : "아직 내진성능평가 건이 없습니다 — 위 [나라장터 계약서 불러오기]로 시작하세요(같은 건이 없으면 새 건이 생깁니다).")
        : cards.length ? "맞는 시설물 카드가 없습니다." : "아직 시설물 카드가 없습니다 — 위 [계약서 불러오기]로 시작하세요."}</div>`;
      return;
    }
    for (const k of shown) list.appendChild(cardEl(k));
  }
  function setTab(tab) { // 목록 머리 [전체 | 민간 | 관급] · 위 "카드에 안 넣은 계약" 알림(10/16) 같이 씀
    view.tab = tab;
    if (view.tab === "민간") view.kind = ""; // 민간은 분야 칩만(학교·일반은 관급 구분)
    if (!view.tab) view.field = view.kind = ""; // [전체] = 칩 거르기도 풀기(10/16)
    render();
  }
  document.querySelectorAll(".sd-sector button").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.sector)));
  document.getElementById("sd-loose").addEventListener("click", () => setTab(view.tab === "loose" ? "" : "loose"));
  document.querySelectorAll(".sd-sort button").forEach((b) => b.addEventListener("click", () => {
    if (b.dataset.sort === "no" && sort.mode === "no") sort.desc = !sort.desc;
    else if (b.dataset.sort === "no") sort.desc = true;
    sort.mode = b.dataset.sort;
    try { localStorage.setItem(SORT_KEY, JSON.stringify(sort)); } catch { /* 지금은 바뀜 */ }
    render();
  }));

  const TYPE_SHORT = { "장기": "장기·지속", "1회성": "1회성·입찰", "종료": "계약 종료" };
  const openCards = new Set(); // 폰: 카드는 접힌 한 줄, 누르면 펼침(10/16 사용자 "목록이 너무 많아") — 펼친 카드 번호
  function cardEl(k) {
    const el = document.createElement("div");
    el.className = `sd-fcard${k.contract_type === "종료" ? " ended" : ""}${openCards.has(k.id) ? " open" : ""}`;
    const us = unitsOf(k);
    const many = us.length > 1; // 시설물 여럿(보고서 따로, 0052)
    const multi = !many && k.members.length > 1; // 한 시설물의 묶인 동(한 보고서)
    const cons = contractsOf(k);
    el.innerHTML = `
      <div class="sd-fhead"><div class="sd-fmain">
        <div class="sd-ftitle">${k.mgmt_no ? `<button type="button" class="site-no sd-no" title="번호 바꾸기">${esc(k.mgmt_no)}</button>` : ""}<span class="sd-chip ${k.sector === "관급" ? "gov" : "civil"}">${esc(k.sector)}</span>
          ${many ? `<b>${esc(cardName(k))}</b><span class="sk-dong-n">시설물 ${us.length}곳 · 보고서 따로</span>` : `<a href="${placeUrl(k.id, k.seismic_rid)}" title="${PLACE_TIP}"><b>${esc(cardName(k))}</b></a>`}${multi ? `<span class="sk-dong-n">${k.members.length}동</span>` : ""}
          ${k.badge_field ? `<span class="sk-badge b-field">${esc(k.badge_field)}</span>` : ""}${k.badge_kind ? `<span class="sk-badge b-kind">${esc(k.badge_kind)}</span>` : ""}
          <span class="sd-ftype">${esc(TYPE_SHORT[k.contract_type] || k.contract_type || "")}</span></div>
        <div class="sd-fsum">${cons.length ? `계약 ${cons.length}건 · ${esc(periodText(cons[cons.length - 1]) || cons[cons.length - 1].title || "")}` : "계약 없음"}<span class="sd-fchev" aria-hidden="true">▾</span></div>
        <div class="dc-meta sd-faddr">${esc([k.address, k.owner_name].filter(Boolean).join(" · "))}${multi ? ` · ${esc(k.members.map((m) => m.name).join(", "))}` : ""}</div>
        ${many ? `<div class="sd-units">${us.map((u, i) => `<a class="sd-unit" href="sitok-facility.html?id=${u.id}" title="보고서 자동화 · 시설물 화면"><span class="site-no">보고서 ${i + 1}</span>${esc(u.name)}${u.members.length > 1 ? ` <small>${u.members.length}동</small>` : ""}</a>`).join("")}</div>` : ""}</div>
        <div class="sd-facts">
          ${SEIS ? (cons.length ? '<button type="button" class="secondary sd-fchange" title="실정보고·설계변경 등 — 착수·완수일·계약금액을 바꾸고 변경 계약서를 붙임(차수마다 기록)">📝 계약변경</button>' : "") // 내진은 단발성 — 새 계약 단추 대신(10/29 민재형)
            : `<button type="button" class="secondary sd-fnew">${k.sector === "민간" ? "+ 계약서" : "+ 관급 계약(착수계)"}</button>`}
          ${SEIS ? "" : '<button type="button" class="secondary sd-fbadge" title="분야·관급 종류 뱃지 바꾸기">🏷 뱃지</button>'}
        </div>
      </div>
      <div class="sd-fbody">${cons.length ? "" : `<div class="mail-note sd-fempty">${SEIS ? "아직 계약이 없습니다 — 위 [나라장터 계약서 불러오기]·[민간 계약서 만들기]로 넣으면 이 건에 들어갑니다." : `아직 계약이 없습니다 — [${k.sector === "민간" ? "+ 계약서" : "+ 관급 계약(착수계)"}]로 넣으세요.`}</div>`}</div>`;
    const body = el.querySelector(".sd-fbody");
    for (const c of cons) body.appendChild(row(c, true));
    el.querySelector(".sd-fnew")?.addEventListener("click", () => openContract(null, k.sector, { card: k, prev: k.sector === "민간" ? latestCon(cons) : null }));
    el.querySelector(".sd-fchange")?.addEventListener("click", () => openChange(latestCon(cons)));
    el.querySelector(".sd-fbadge")?.addEventListener("click", () => editBadges(k));
    const noBtn = el.querySelector(".sd-no");
    if (noBtn) noBtn.addEventListener("click", () => editNumber(k));
    const links = siteLinkButtons(k.contact_phone, k.address);
    if (links) el.querySelector(".sd-fmain").appendChild(links);
    el.querySelector(".sd-fhead").addEventListener("click", (e) => { // 폰: 머리를 누르면 펼침·접음(버튼·링크는 그대로, 접혀 있을 땐 이름을 눌러도 먼저 펼침)
      if (!window.matchMedia("(max-width: 760px)").matches) return;
      const hit = e.target.closest("a, button, input, select");
      const nameLink = hit && hit.tagName === "A" && hit.closest(".sd-ftitle") && !el.classList.contains("open");
      if (hit && !nameLink) return;
      if (nameLink) e.preventDefault();
      if (openCards.has(k.id)) openCards.delete(k.id);
      else openCards.add(k.id);
      el.classList.toggle("open", openCards.has(k.id));
    });
    return el;
  }

  // 번호 바꾸기(10/15 민재형) — 앞 글자는 구분(관급·민간), 숫자만. 겹치면 서버가 알림, 묶인 동 같이, 다음 자동 번호는 가장 큰 번호 + 1
  function editNumber(k) {
    if (SEIS) { editSeisNumber(k); return; }
    const cur = Number((String(k.mgmt_no).match(/^(?:관급|민간)-0*(\d+)/) || [])[1]) || ""; // 앞 번호(관급-6-2 → 6)
    const overlay = document.createElement("div");
    overlay.className = "mail-overlay";
    overlay.innerHTML = `<div class="mail-box sd-badge-box" role="dialog" aria-modal="true">
      <div class="mail-head"><b># 번호 바꾸기</b><span class="mail-sub">${esc(cardName(k))} — 보고서 자동화 시설물도 같은 번호</span></div>
      <label class="cd-field"><span>번호</span><span class="sd-no-row"><b>${esc(k.sector)}-</b><input class="n-no" type="number" min="1" value="${cur}" /></span></label>
      <div class="mail-note">다른 카드가 쓰는 번호를 넣으면 그 카드의 시설물(보고서 따로 — 같은 발주처가 나눈 계약)로 합칠지 묻습니다. 새 카드는 지금 가장 큰 번호 다음부터 자동으로 붙습니다.</div>
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
      const n = Number(inp.value);
      try {
        await apiPost(`${P}/facilities/${k.id}/number`, { n });
        close();
        load();
      } catch (err) {
        const m = overlay.querySelector(".mail-msg");
        m.hidden = false;
        m.className = "mail-msg bad";
        if (err.status !== 409) { m.textContent = err.message; return; }
        // 다른 카드 번호 — 같은 발주처가 계약을 나눈 거면 그 카드의 시설물(보고서 따로)로 합침(10/15 밤 민재형 "앞 번호 9를 같이 써서 같은 발주처인 줄 알게")
        m.className = "mail-msg warn";
        m.innerHTML = `${esc(err.message)}<br>같은 발주처가 계약을 나눈 거면 이 카드를 <b>${esc(k.sector)}-${n}</b> 카드의 시설물(보고서 따로)로 넣을 수 있습니다 — 계약·보고서는 그대로 따라갑니다.
          <div class="n-merge-row"><button type="button" class="secondary n-merge">${esc(k.sector)}-${n} 카드에 시설물로 넣기</button></div>`;
        m.querySelector(".n-merge").addEventListener("click", async () => {
          try {
            const out = await apiPost(`${P}/facilities/${k.id}/number`, { n, merge: true });
            close();
            await load();
            const s = document.getElementById("sd-new-msg");
            s.className = "status ok";
            s.textContent = `✓ ${k.sector}-${n} 카드의 시설물 ${(out.merged || []).join(" · ")}(으)로 넣었습니다 — 보고서 자동화 번호도 같이 바뀌었습니다.`;
          } catch (e2) {
            m.className = "mail-msg bad";
            m.textContent = e2.message;
          }
        });
      }
    };
    overlay.querySelector(".n-save").addEventListener("click", save);
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter") save(); });
  }

  // 내진성능평가 건 번호(10/29 민재형) — 연도 두 자리-번호 "26-1"(관급·민간 구분 없이 그 해 이어서, 공유 파일번호와 같게). 겹치면 서버가 알림
  function editSeisNumber(k) {
    const overlay = document.createElement("div");
    overlay.className = "mail-overlay";
    overlay.innerHTML = `<div class="mail-box sd-badge-box" role="dialog" aria-modal="true">
      <div class="mail-head"><b># 번호 바꾸기</b><span class="mail-sub">${esc(cardName(k))} — 공유 파일번호와 같게</span></div>
      <label class="cd-field"><span>번호(연도 두 자리-번호)</span><input class="n-no" value="${esc(k.mgmt_no || "")}" placeholder="예: 26-1" maxlength="8" /></label>
      <div class="mail-note">새 건은 그 해(계약일 기준) 가장 큰 번호 다음으로 자동으로 붙습니다 — 관급·민간 구분 없이 이어서.</div>
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
        await apiPost(`${P}/facilities/${k.id}/number`, { text: inp.value.trim() });
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
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.isComposing) save(); });
  }

  // [📝 계약변경] 창(10/29 민재형 — 내진성능평가는 실정보고·설계변경이 잦음, 산안법 계약변경 창과 같은 모양): 변경 계약서를 붙이면 읽어서
  // 착수·완수일·계약금액·변경계약일·사유를 채움(저장 전 고칠 수 있음) → [변경 저장] = 바뀐 칸만 계약에(내진 건 용역 칸도 같이), 차수 기록(전·후 값, 첨부)
  async function openChange(c) {
    if (!c) return;
    let v;
    try { v = await api(`${P}/contracts/${c.id}/change`); } catch (err) { showError(errorEl, err); return; }
    let file = null;
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
    const money = (x) => (x == null || x === "" ? "-" : `${won(Number(x))}원`);
    const show = (k, x) => (k === "amount" ? money(x) : esc(x ?? "-"));
    const field = (k, val, extra = "") => `<label class="cd-field"><span>${L[k]}</span><input data-k="${k}" ${k === "amount" ? 'inputmode="numeric"' : 'type="date"'} value="${esc(val ?? "")}" ${extra} /></label>`;
    const hist = v.history.length ? `<details class="cg-hist"><summary>지난 계약변경 ${v.history.length}번</summary>${v.history.slice().reverse().map((h) => {
      const rows = Object.entries(h.after || {}).map(([k, x]) => `${L[k] || k} ${show(k, (h.before || {})[k])} → <b>${show(k, x)}</b>`);
      return `<div class="cg-h"><b>${h.no}차</b> ${esc(h.change_date ? `변경계약 ${h.change_date}` : h.at)} · ${esc(h.by)}${h.reason ? ` — ${esc(h.reason)}` : ""}<div>${rows.join("<br>") || "칸 변경 없음"}</div>
        ${(h.files || []).map((n) => `<a href="${BASE}/api${P}/contracts/${c.id}/change/${h.no}/${encodeURIComponent(n)}" target="_blank" rel="noopener">📄 ${esc(n)}</a>`).join(" ")}</div>`;
    }).join("")}</details>` : "";
    box.innerHTML = `<div class="mail-head"><b>📝 계약변경 ${v.next_no}차</b><span class="mail-sub">${esc(v.label)}${v.contract_no ? ` · ${esc(v.contract_no)}` : ""} — 바꾼 칸만 계약에 들어갑니다(착수계·완수계·내진 건 용역 칸도 바뀐 값으로)</span></div>
      ${hist}
      <div class="mail-label">변경 계약서 <span class="mail-note">— 붙이면 읽어서 아래 칸을 채움(나라장터 용역변경계약서)</span></div>
      <div class="cg-file"><label class="cd-add">PDF 붙이기<input type="file" accept="application/pdf,.pdf,.hwp,.hwpx,image/*" hidden data-kr-file="skip" /></label><span class="cg-fname"></span></div>
      <label class="cd-field"><span>사유</span><input class="cg-reason" placeholder="예: 실정보고(조사 범위 추가) · 설계변경(금액 증액) · 용역기간 연장" maxlength="300" /></label>
      <div class="cd-grid cg-grid">${["start_date", "end_date", "amount"].map((k) => field(k, v.contract[k])).join("")}${field("change_date", "", 'class="cg-cdate"')}</div>
      <div class="mail-note">원계약일 ${esc(v.contract_date || "-")} · 지금 ${esc(v.contract.start_date || "-")} ~ ${esc(v.contract.end_date || "-")} · ${money(v.contract.amount)}</div>
      <div class="mail-msg cg-msg" hidden></div>
      <div class="mail-foot cd-foot"><button type="button" class="cg-close">닫기</button><button type="button" class="mail-primary cg-save">📝 변경 저장</button></div>`;
    const msg = box.querySelector(".cg-msg");
    const say = (t, tone) => { msg.hidden = !t; msg.className = `mail-msg cg-msg ${tone || ""}`; msg.innerHTML = t; };
    box.querySelector(".cg-close").addEventListener("click", close);
    const fel = box.querySelector(".cg-file");
    const finp = fel.querySelector("input[type=file]");
    enableFileDrop(fel, finp);
    finp.addEventListener("change", async () => {
      const f = finp.files[0];
      finp.value = "";
      if (!f) return;
      file = f;
      const name = `<span class="mail-note">📄 ${esc(f.name)}</span>`;
      fel.querySelector(".cg-fname").innerHTML = `${name} <span class="mail-note">읽는 중…</span>`;
      try {
        const fd = new FormData();
        fd.append("file", f);
        const r = await apiUpload(`${P}/contracts/${c.id}/change/read`, fd);
        let n = 0;
        for (const [k, x] of Object.entries(r.values || {})) {
          const t = k === "reason" ? box.querySelector(".cg-reason") : box.querySelector(`input[data-k="${k}"]`);
          if (t && x != null && String(t.value) !== String(x)) { t.value = x; t.classList.add("sk-filled"); n += 1; }
        }
        fel.querySelector(".cg-fname").innerHTML = `${name} <span class="mail-note">${n ? `${n}칸 채움 — 확인하세요` : "읽은 칸 없음(직접 고치세요)"}</span>`;
      } catch (err) {
        fel.querySelector(".cg-fname").innerHTML = `${name} <span class="cd-bad">못 읽음: ${esc(err.message)} — 칸을 직접 고치세요(파일은 그대로 붙음)</span>`;
      }
    });
    box.querySelector(".cg-save").addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      const body = { reason: box.querySelector(".cg-reason").value, change_date: box.querySelector(".cg-cdate").value, contract: {} };
      for (const k of ["start_date", "end_date", "amount"]) body.contract[k] = box.querySelector(`input[data-k="${k}"]`).value.trim().replace(/,/g, "");
      const fd = new FormData();
      fd.append("data", JSON.stringify(body));
      if (file) fd.append("file", file);
      busy = true;
      btn.disabled = true;
      try {
        const out = await apiUpload(`${P}/contracts/${c.id}/change`, fd);
        busy = false;
        const n = Object.keys(out.saved.after || {}).length;
        say(`✓ ${out.saved.no}차 계약변경을 저장했습니다 — 바뀐 칸 ${n}개${out.saved.files.length ? ", 변경 계약서 첨부" : ""}${out.synced ? " · 내진 건 용역 칸에도 넣었습니다" : ""}.`, "ok");
        btn.textContent = "저장함";
        load();
      } catch (err) {
        busy = false;
        btn.disabled = false;
        say(esc(err.message), "bad");
      }
    });
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
    if (c.facility && SEIS) out.push(line("내진 건", !!(c.seismic && c.seismic.synced), c.seismic && c.seismic.synced ? "✓ 계약 넣음" : "안 넣음"));
    else if (c.facility) out.push(line("보고서 쪽", !!c.report_contract_id, c.report_contract_id ? "✓ 계약 넣음" : "안 넣음"));
    if (c.changes) out.push(`<span class="dc-doc dc-chg"><b>계약변경</b> ${c.changes}차</span>`); // 10/29 내진 계약변경
    if (c.sector === "관급") {
      for (const [k, lab] of [["start", "착수계"], ["done", "완수계"]]) {
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
    // 10/16 사용자: 한 줄에 다 붙이면 지저분 — 발주처·계약번호 / 기간·금액 두 줄, 날짜·번호 중간에서 안 끊김(발주처는 띄어쓰기에서만)
    const metaLine = (xs) => xs.filter((x) => x[1]).map(([cls, v]) => `<span class="${cls}">${esc(v)}</span>`).join('<span class="sd-mdot"> · </span>');
    const meta1 = metaLine([["sd-mc", c.client], ["sd-mi", c.contract_no]]), meta2 = metaLine([["sd-mi", periodText(c)], ["sd-mi", moneyText(c)]]);
    const year = c.sector === "관급" && (c.start_date || c.contract_date) ? `<span class="sd-year">${(c.start_date || c.contract_date).slice(0, 4)}년</span>` : "";
    const half = c.half && !SEIS ? `<span class="sd-half${c.half === "해당없음" ? " na" : ""}" title="${c.half_tag ? "직접 고른 반기" : "용역 기간으로 자동"}">${esc(c.half)}</span>` : "";
    const kc = inCard ? cardOf(c) : null;
    const dno = kc && unitsOf(kc).length > 1 && c.card_no ? `<span class="site-no sd-dno" title="서류 번호 — 계약이 시설물 여럿을 맡으면 카드 번호, 하나면 그 시설물 번호">서류 ${esc(c.card_no)}</span>` : ""; // 10/15 밤
    const chk = kc && unitsOf(kc).length > 1 && c.cover === "check" ? ' <span class="sd-cover-chk" title="건명·내역서로 맡는 건물을 못 정해 현장 전체(또는 남은 건물)로 넣었습니다 — [계약 정보]에서 확인">⚠ 맡는 건물 확인</span>' : "";
    const tg = kc && unitsOf(kc).length > 1 && c.targets && c.targets.length ? `<div class="dc-meta sd-targets">시설물 ${c.targets.map((t) => `${esc(t.name)}${c.amounts && c.amounts[t.id] ? ` ${won(c.amounts[t.id])}원` : ""}`).join(" · ")}${chk}</div>` : "";
    el.innerHTML = `
      <div class="dc-main">
        <div class="dc-title">${inCard ? `${dno}${year}${half}` : `<span class="sd-chip ${c.sector === "민간" ? "civil" : "gov"}">${c.sector}</span>${half}`}${esc(c.title || (c.sector === "민간" && c.auto_title) || "(계약건명 없음 — 계약 정보를 채우세요)")}</div>
        ${meta1 ? `<div class="dc-meta sd-meta">${meta1}</div>` : ""}${meta2 ? `<div class="dc-meta sd-meta">${meta2}</div>` : ""}${tg}
        ${contactLine(c, "client", "계약 담당")}${contactLine(c, "site", "현장 담당")}
        ${inCard ? "" : `<div class="dc-site">${c.facility ? `현장 <a href="${placeUrl(c.facility.id, c.facility.seismic_rid)}">${esc(c.facility.name)}</a>` : `<span class="dc-nosite">${SEIS ? "내진성능평가 건에 안 넣음" : "시설물 카드에 안 넣음"}</span>`}
          <button type="button" class="dc-link">${c.facility ? "바꾸기" : "🔗 카드에 넣기"}</button></div>`}
      </div>
      <div class="dc-docs">${docLines(c)}</div>
      <div class="dc-actions">
        ${c.sector === "관급" ? '<button type="button" class="secondary sd-gov" data-kind="start">📑 착수계</button><button type="button" class="secondary sd-gov" data-kind="done">📑 완수계</button>' : ""}
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
      const pw = await dcAskPassword(`"${c.title || c.auto_title || "점검 계약"}"을(를) 지웁니다. 올린·만든 계약서 파일과 보고서 쪽에 넣은 계약도 같이 지워집니다(회차는 남음). 되돌릴 수 없습니다.`);
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
      <input type="search" class="mail-input cd-pick-q" placeholder="${SEIS ? "건물명·발주처·주소로 찾기" : "시설물명·관리주체·주소로 찾기"}" autocomplete="off" />
      <div class="cd-pick-list"></div>
      <div class="mail-note">${SEIS ? '없으면 계약서를 올리고 저장할 때 새 건이 자동으로 생깁니다 — 또는 <a href="seismic.html">보고서 자동화 · 내진성능평가에서 새 건 만들기</a> 뒤 다시 연결하세요.'
        : '없으면 <a href="sitok-new.html">보고서 자동화 · 시특법에서 새 시설물 등록</a> 뒤 다시 연결하세요.'}</div>
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
      if (unitsOf(k).length > 1) st.facility_ids = unitsOf(k).map((u) => u.id); // 시설물 여럿 카드 — 기본 전부(계약 창에서 줄임)
    }
    if (!id && intro && intro.prev && st.sector === "민간") prefill(intro.prev); // 기존 계약 내용 + 다음 반기 회차(10/20 민재형)
    if (st.facility_ids && st.facility_ids.length) st.facility_ids = st.facility_ids.slice();
    st.amounts = { ...(st.amounts || {}) };
    if (!id && !st.rounds.length && st.sector === "민간" && !SEIS) { // 새 민간 계약: 올해·지금 반기·정기 한 줄(내진은 회차 없음)(관급은 회차 줄 없음 — 반기는 용역 기간으로, 10/15)
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
      const b = { sector: st.sector, open_ended: SEIS ? false : !!st.open_ended, unit: SEIS ? null : st.unit || null,
        rounds: st.sector === "민간" && !SEIS ? st.rounds.filter((r) => r.year) : [], half_tag: st.half_tag || "" };
      const ub = box.querySelector(".sd-ufac");
      if (ub) { // 이 계약의 시설물(0052)
        st.facility_ids = [...ub.querySelectorAll(".uf-chk:checked")].map((i) => Number(i.value));
        st.amounts = Object.fromEntries([...ub.querySelectorAll(".uf-amt")].map((i) => [i.dataset.id, num(i.value)]).filter(([, v]) => v));
      }
      if (st.facility_ids && st.facility_ids.length && (st.id || st.facility_id)) { b.facility_ids = st.facility_ids; b.amounts = st.amounts || {}; }
      if (st.cover_touched) b.cover_touched = true;
      if (st.cover_ok) b.cover_ok = true;
      if (!st.id && st.facility_id) b.facility_id = st.facility_id;
      for (const k of TEXT) b[k] = st[k] ?? "";
      for (const k of DATES) b[k] = st[k] || null;
      if (st.sector === "관급" || SEIS) b.amount = st.amount ?? null;
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
        if (st.auto_card) msg(esc(st.auto_card) + (st.report_id ? (SEIS ? ` — <a href="seismic-project.html?id=${st.report_id}">건 화면</a>` : ` — 이번 반기 회차까지 만들었습니다 <a href="sitok-round.html?report=${st.report_id}">회차 화면</a>`) : ""), "ok"); // 저장 = 카드(10/15)
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
    const estChip = () => { // 관급 내역서 = 착수계 붙임 "산출내역서" 칸(같은 곳, 10/16) — 여러 개 가능
      const names = st.estimate || [];
      const url = (n) => `${BASE}/api${P}/contracts/${st.id}/gov/start/attach/calc/${encodeURIComponent(n)}`;
      return `<div class="sd-up">
        <label class="drop-box drop-sm sd-up-box"><b>📎 내역서</b><input type="file" data-up="estimate" accept=".pdf,.hwp,.hwpx,.xlsx,.xls,.jpg,.jpeg,.png,application/pdf,image/*" hidden data-kr-file="skip" /></label>
        <span class="mail-note">${names.length ? names.map((n) => `<a href="${url(n)}" target="_blank" rel="noopener">✓ ${esc(n.replace(/^\d+_/, "").replace(/\.pdf$/, ""))}</a>`).join(" · ")
          : "산출내역서·과업내용서 → 착수계 붙임에 자동"}${(st.est_parts || []).length ? `<br>읽은 건물: ${st.est_parts.map((x) => esc(x.name)).join(" · ")}` : ""}</span></div>`;
    };
    const upChip = (kind, label, file, hint) => `<div class="sd-up">
        <label class="drop-box drop-sm sd-up-box"><b>📎 ${label}</b><input type="file" data-up="${kind}" accept=".pdf,.hwp,.hwpx,.jpg,.jpeg,.png,application/pdf,image/*" hidden data-kr-file="skip" /></label>
        <span class="mail-note">${st.files && st.files[file] ? `<a href="${fileUrl(st, file)}" target="_blank" rel="noopener">✓ 올림 · 보기</a>` : hint}</span></div>`;

    // 기존 계약 가져오기(10/20 민재형 "+계약서 누르고 시작할 때 기존 계약 내용, 26년 하반기까지면 2027년 상반기로") —
    // 관리주체·대표자·사업자·주소·시설물·위치·제원·보증·지체상금·담당자·맡는 건물·동별 금액, 회차 = 마지막 회차 다음부터(그해 마지막 반기면 다음 해 같은 반기들).
    // 계약일·계약건명·문서번호·파일은 새로(건명은 비우면 자동). 종류는 정기로 두고 📅 도래주기가 고름.
    function prefill(p) {
      const KEYS = ["client", "client_rep", "client_biz_no", "client_address", "facility_name", "location", "spec", "guarantee", "delay_rate",
        "client_manager", "client_phone", "client_email", "site_manager", "site_phone", "site_email"];
      for (const k of KEYS) if (p[k]) st[k] = p[k];
      if ((p.facility_ids || []).length) st.facility_ids = p.facility_ids.slice();
      if (p.amounts) st.amounts = { ...p.amounts };
      if ((p.buildings || []).length >= 2) st.bldgs = p.buildings.slice();
      const prev = (p.rounds || []).filter((r) => r.year);
      if (!p.open_ended && prev.length) {
        const last = prev[prev.length - 1];
        // 금액은 종류별 — 새 회차는 정기로 시작하니 같은 반기의 가장 최근 정기 금액(앞 계약 그 반기가 정밀이었으면 정밀 금액을 안 가져옴),
        // 도래주기가 정밀·진단으로 바꾸면 그 종류의 가장 최근 금액(applyCycle). 동별 금액(parts)은 그대로 복사.
        const recent = prev.slice().reverse();
        st.kind_amount = {};
        for (const r of recent) if (!r.parts && r.amount && !(r.kind in st.kind_amount)) st.kind_amount[r.kind] = r.amount;
        const amountFor = (r) => (r.parts ? r.amount
          : (recent.find((x) => x.kind === "정기" && x.half === r.half && !x.parts) || recent.find((x) => x.kind === "정기" && !x.parts) || r).amount);
        const copy = (r, year, half) => ({ year, half, kind: "정기", amount: amountFor(r), ...(r.parts ? { parts: r.parts.map((x) => ({ ...x })) } : {}) });
        st.rounds = HALF_END_OF_YEAR.has(last.half)
          ? prev.filter((r) => r.year === last.year).map((r) => copy(r, last.year + 1, r.half))
          : [copy(last, last.year + NEXT_HALF[last.half][1], NEXT_HALF[last.half][0])];
        const a = st.rounds[0], b = st.rounds[st.rounds.length - 1];
        st.start_date = st.start_date || halfStart(a.year, a.half);
        st.end_date = st.end_date || halfEnd(b.year, b.half);
      } else if (p.open_ended) {
        st.open_ended = true;
        st.unit = p.unit ? { ...p.unit } : st.unit;
      }
      st.prefill_note = `기존 계약 "${p.title || p.auto_title || ""}"에서 가져왔습니다${prev.length && !p.open_ended ? ` — 회차는 ${st.rounds.map((r) => `${r.year} ${r.half}`).join("·")}` : ""}. 계약일·건명은 새로 넣으세요.`;
    }

    // ---------- 📅 도래주기(10/20 민재형, 시행령 별표 3) — 회차 줄마다 실시할 점검. 서버 /sitok/docs/cycle(server/sitok/cycle.py) ----------
    // 전회차 기록(우리 정밀 회차·전회차 보고서 이력·넣어 둔 날짜)이 없으면: 3종 안 물음, 2종 전회차 정밀안전점검, 1종 + 정밀안전진단 — 넣은 값은 시설물에 저장.
    // 새 계약은 회차 줄 종류를 자동으로 맞춤(사람이 바꾼 줄은 그대로), 이미 있는 계약은 [회차 줄에 반영]으로.
    let cyc = null, cycKey = "";
    const manualKind = new Set(); // 사람이 종류를 바꾼 회차 "2027-하반기"
    const cycIds = () => (st.facility_ids && st.facility_ids.length ? st.facility_ids : st.facility ? [st.facility.id] : []);
    const cycHalves = () => st.rounds.filter((r) => r.year).map((r) => `${r.year}-${r.half}`);
    async function loadCycle(force) {
      const el = box.querySelector(".sd-cycle");
      if (!el) return;
      const ids = cycIds(), hs = cycHalves();
      if (!ids.length) { el.innerHTML = '<div class="mail-note">시설물 카드를 고르면 도래주기(정밀안전점검·정밀안전진단 시기)를 계산합니다.</div>'; return; }
      const key = `${ids.join(",")}|${hs.join(",")}`;
      if (force || key !== cycKey || !cyc) {
        try { cyc = await api(`${P}/cycle?ids=${ids.join(",")}&halves=${encodeURIComponent(hs.join(","))}`); cycKey = key; }
        catch (err) { el.innerHTML = `<div class="mail-msg bad">${esc(err.message)}</div>`; return; }
      }
      if (!box.contains(el)) return; // 그새 다시 그림
      if (!st.id && !cyc.rows.some((r) => r.needs.length) && applyCycle(false)) { draw(); return; } // 새 계약 — 종류 자동(전회차를 다 알 때만, 다시 그린 뒤 같은 key라 다시 안 부름)
      drawCycle(el);
    }
    function applyCycle(all) { // 회차 줄 종류를 도래주기대로 — all = 사람이 바꾼 줄까지([회차 줄에 반영])
      let changed = false;
      for (const r of st.rounds) {
        const k = `${r.year}-${r.half}`, sug = cyc && cyc.rounds[k];
        if (!sug || (!all && manualKind.has(k)) || r.kind === sug.kind) continue;
        r.kind = sug.kind;
        if (!r.parts && st.kind_amount && st.kind_amount[sug.kind]) r.amount = st.kind_amount[sug.kind]; // 가져온 계약의 그 종류 금액
        changed = true;
      }
      if (all) manualKind.clear();
      return changed;
    }
    function drawCycle(el) {
      const rows = cyc.rows;
      const mark = (s) => (s ? `<small class="cy-src">${esc(s)}</small>` : "");
      // 전회차 시기가 빠진 건물이 있으면 제안은 정기로만 나오니 [회차 줄에 반영]을 숨김(사람이 넣은 정밀 회차를 정기로 덮지 않게)
      const known = !rows.some((r) => r.needs.length);
      const diff = known && st.rounds.some((r) => { const g = cyc.rounds[`${r.year}-${r.half}`]; return g && g.kind !== r.kind; });
      const opt = (list, v, auto) => list.map((x) => `<option value="${x}"${x === v ? " selected" : ""}>${x || auto}</option>`).join("");
      const row = (r) => {
        const cls = r.class_no ? `${r.class_no}종` : "법정 외";
        const asks = r.needs.length ? ` cy-need` : "";
        const dates = r.class_no === 1 || r.class_no === 2 ? `
            <label class="cy-in">전회차 정밀안전점검 <input type="month" class="cy-lp" value="${esc(r.last_precision)}"${r.precision_first ? " disabled" : ""} />
              <span class="cy-first"><input type="checkbox" class="cy-lp-first"${r.precision_first ? " checked" : ""} /> 아직 안 함</span>${mark(r.last_precision ? r.lp_src : "")}</label>
            ${r.class_no === 1 ? `<label class="cy-in">전회차 정밀안전진단 <input type="month" class="cy-ld" value="${esc(r.last_diagnosis)}"${r.diagnosis_first ? " disabled" : ""} />
              <span class="cy-first"><input type="checkbox" class="cy-ld-first"${r.diagnosis_first ? " checked" : ""} /> 아직 안 함</span>${mark(r.last_diagnosis ? r.ld_src : "")}</label>` : ""}
            ${r.needs.includes("completion") ? `<label class="cy-in">준공일 <input type="date" class="cy-comp" value="${esc(r.completion)}" /></label>` : ""}` : "";
        return `<div class="cy-row${asks}" data-id="${r.id}">
          <div class="cy-head"><b>${esc(r.name)}</b><span class="cy-tag">${cls} · ${r.field === "건축" ? "건축물" : `토목(${esc(r.kind || "건축물 외")})`}</span>
            <select class="cy-class" aria-label="종별" title="도래주기 — 1종 정기~정밀안전진단, 2종 ~정밀안전점검, 3종 정기만">${opt(["", "1종", "2종", "3종"], r.class_src === "입력" ? `${r.class_no}종` : "", `자동(${cls})`)}</select>
            <select class="cy-grade" aria-label="안전등급" title="주기가 등급마다 다름 — 자동 = ${esc(r.grade_src)}">${opt(["", "A", "B", "C", "D", "E"], r.grade_src === "입력" ? r.grade : "", `자동(${r.grade})`)}</select>${mark(r.grade_src !== "입력" ? `등급 ${r.grade_src}` : "")}</div>
          ${dates}
          <div class="cy-next">${r.needs.length ? '<b class="cy-ask">⚠ 전회차 시기를 넣어 주세요(처음이면 "아직 안 함")</b> · ' : ""}${esc(r.next)}${r.warn.map((w) => ` · <span class="cy-warn">⚠ ${esc(w)}</span>`).join("")}</div>
        </div>`;
      };
      const many = rows.filter((r) => r.class_no === 1 || r.class_no === 2).length >= 2;
      el.innerHTML = `<div class="cy-rows">${rows.map(row).join("")}</div>
        ${many ? `<div class="cy-all">모든 건물 같게: <select class="cy-all-grade"><option value="">등급</option>${["A", "B", "C", "D", "E"].map((g) => `<option>${g}</option>`).join("")}</select>
          전회차 정밀안전점검 <input type="month" class="cy-all-lp" /> <button type="button" class="cy-all-go">적용</button></div>` : ""}
        <div class="cy-foot"><span class="mail-note">${cycHalves().map((k) => { const g = cyc.rounds[k]; return g ? `${k.replace("-", " ")} ${KIND_WORD[g.kind]}` : ""; }).filter(Boolean).join(" · ")}</span>
          ${diff ? '<button type="button" class="cy-apply">회차 줄에 반영</button>' : ""}</div>`;
      const put = async (fid, body) => {
        try { await apiPost(`${P}/cycle/facility/${fid}`, body); await loadCycle(true); } catch (err) { msg(esc(err.message), "bad"); }
      };
      el.querySelectorAll(".cy-row").forEach((rw) => {
        const fid = Number(rw.dataset.id);
        rw.querySelector(".cy-class").addEventListener("change", (e) => put(fid, { class_no: e.target.value }));
        rw.querySelector(".cy-grade").addEventListener("change", (e) => put(fid, { safety_grade: e.target.value }));
        rw.querySelector(".cy-lp")?.addEventListener("change", (e) => put(fid, { last_precision: e.target.value }));
        rw.querySelector(".cy-ld")?.addEventListener("change", (e) => put(fid, { last_diagnosis: e.target.value }));
        rw.querySelector(".cy-lp-first")?.addEventListener("change", (e) => put(fid, { precision_first: e.target.checked }));
        rw.querySelector(".cy-ld-first")?.addEventListener("change", (e) => put(fid, { diagnosis_first: e.target.checked }));
        rw.querySelector(".cy-comp")?.addEventListener("change", (e) => put(fid, { completion_date: e.target.value || null }));
      });
      el.querySelector(".cy-all-go")?.addEventListener("click", async () => {
        const g = el.querySelector(".cy-all-grade").value, lp = el.querySelector(".cy-all-lp").value;
        if (!g && !lp) return;
        const body = { ...(g ? { safety_grade: g } : {}), ...(lp ? { last_precision: lp } : {}) };
        try {
          for (const r of rows.filter((x) => x.class_no === 1 || x.class_no === 2)) await apiPost(`${P}/cycle/facility/${r.id}`, body);
          await loadCycle(true);
        } catch (err) { msg(esc(err.message), "bad"); }
      });
      el.querySelector(".cy-apply")?.addEventListener("click", () => { sync(); applyCycle(true); draw(); });
      // 회차 줄 옆에 이유(전회차 시기) — "목록에 띄우기"(10/20 민재형)
      box.querySelectorAll(".sd-round").forEach((rw) => {
        const r = st.rounds[Number(rw.dataset.i)];
        const g = r && cyc.rounds[`${r.year}-${r.half}`];
        rw.querySelector(".r-why")?.remove();
        if (!g || (g.kind === "정기" && !g.why.length)) return;
        rw.insertAdjacentHTML("beforeend", `<span class="r-why${g.kind !== r.kind ? " off" : ""}" title="${esc(g.why.join("\n"))}">${g.kind !== r.kind ? `도래주기: ${KIND_WORD[g.kind]} — ` : "📅 "}${esc(g.why[0] || "")}${g.why.length > 1 ? ` 외 ${g.why.length - 1}` : ""}</span>`);
      });
    }

    function roundsBlock() {
      if (st.open_ended) {
        const u = st.unit || { kind: "정기", amount: null };
        return `<div class="sd-unit">매 반기 <select class="sd-unit-kind">${KIND_OPTS.map((k) => `<option${u.kind === k ? " selected" : ""}>${k}</option>`).join("")}</select>
          금 <input class="sd-unit-amt sd-won" inputmode="numeric" value="${won(u.amount)}" placeholder="550,000" /> 원 <span class="mail-note">(VAT포함 · 총합은 안 씀)</span></div>`;
      }
      const multi = st.bldgs.length >= 2;
      const partOf = (r, j) => { const q = (r.parts || []).find((x) => x.name === st.bldgs[j]); return q ? q.amount : (j === 0 && !r.parts ? r.amount : null); };
      const rows = st.rounds.map((r, i) => `<div class="sd-round${multi ? " multi" : ""}" data-i="${i}">
          <input class="r-year" inputmode="numeric" value="${r.year || ""}" aria-label="연도" /><span>년</span>
          <select class="r-half" aria-label="반기·시기" title="연 3회(D·E등급)면 해빙기·우기·동절기">${HALF_OPTS.map((h) => `<option${r.half === h ? " selected" : ""}>${h}</option>`).join("")}</select>
          <select class="r-kind" aria-label="점검 종류" title="정밀 = 정밀안전점검 · 진단 = 정밀안전진단">${KIND_OPTS.map((k) => `<option${r.kind === k ? " selected" : ""}>${k}</option>`).join("")}</select>
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

    // 이 계약의 시설물(카드에 시설물 여럿 — 보고서 따로, 0052): 체크 + 둘 이상이면 시설물별 금액(합 = 계약금액)
    function unitBox() {
      const k = st.facility ? cards.find((x) => x.members.some((m) => m.id === st.facility.id)) : null;
      const us = k ? unitsOf(k) : [];
      if (us.length < 2) return "";
      const on = new Set((st.facility_ids && st.facility_ids.length ? st.facility_ids : [st.facility.id]).map(Number));
      const total = st.sector === "관급" ? st.amount : null;
      const sum = us.filter((u) => on.has(u.id)).reduce((t, u) => t + (Number((st.amounts || {})[u.id]) || 0), 0);
      const warn = st.cover === "check" && !st.cover_touched ? `<div class="sd-cover-warn">⚠ 건명·내역서로 맡는 건물을 못 정해 ${on.size === us.length ? "현장 전체" : "이 기간 다른 계약이 안 맡은 건물"}로 넣었습니다.
          맞으면 <button type="button" class="sd-cover-ok">✓ 맞음</button>, 아니면 아래 체크를 고치세요(내역서를 올리면 이름으로 다시 정함).</div>` : "";
      return `<div class="mail-label">이 계약의 시설물 <span class="mail-note">— 보고서가 따로 나오는 시설물마다 보고서 쪽 계약이 생깁니다. 둘 이상이면 시설물별 금액(보고서 표지·FMS)</span></div>
        ${warn}<div class="sd-ufac">${us.map((u) => `<label class="uf-row"><input type="checkbox" class="uf-chk" value="${u.id}"${on.has(u.id) ? " checked" : ""} />
            ${esc(u.name)}
            <span class="uf-amt-wrap">${on.has(u.id) && on.size > 1 ? `금 <input class="uf-amt sd-won" data-id="${u.id}" inputmode="numeric" value="${won((st.amounts || {})[u.id])}" placeholder="이 시설물 금액" /> 원` : ""}</span></label>`).join("")}
          ${on.size > 1 && total ? `<div class="mail-note${sum && sum !== total ? " uf-bad" : ""}">시설물별 금액 합 ${won(sum) || 0}원 / 계약금액 ${won(total)}원${sum && sum !== total ? " — 합이 계약금액과 다릅니다" : ""}</div>` : ""}</div>`;
    }

    // clean = 서버에서 막 받은 상태(닫을 때 "고친 게 있나" 비교 기준) — 화면에서만 바꾼 뒤 다시 그릴 땐 기준을 안 바꿈
    function draw(clean) {
      if (!Array.isArray(st.bldgs)) st.bldgs = (st.buildings || []).slice(); // 서버에서 막 받은 st(올리기·계약서 만들기·다른 카드로 뒤)엔 화면용 동 목록이 없음 — 10/16 "reading 'length'"
      if (!Array.isArray(st.rounds)) st.rounds = [];
      const civil = st.sector === "민간";
      const f = st.facility;
      box.innerHTML = `
        <div class="mail-head"><b>${civil ? "📝 민간 계약서" : "📑 관급 계약"}</b>
          <span class="mail-sub">${esc(st.title || (civil && st.facility_name && st.auto_title) || "새 계약")}</span>
          <div class="cd-site-line mail-sub">${SEIS ? "건" : "현장"}: ${f ? `<a href="${placeUrl(f.id, f.seismic_rid)}">${esc(f.name)}</a>` : '<span class="dc-nosite">연결 안 됨</span>'}
            <button type="button" class="cd-link-btn sd-link">${f ? (SEIS ? "다른 건으로" : "다른 카드로") : (SEIS ? "🔗 건 고르기" : "🔗 카드 고르기")}</button>
            <span class="sd-auto-note">${SEIS ? (f ? (st.seismic && st.seismic.synced ? "· 건 용역 정보·용역계약서 ✓" : "· 계약서를 올리면 저장할 때 건 용역 정보·용역계약서까지 자동")
                : "· 계약서를 올리면 저장할 때 내진성능평가 건에 자동으로 들어갑니다(같은 학교 건이 있으면 그 건, 없으면 새 건)")
              : f ? (st.report_contract_id ? "· 보고서 쪽 계약 ✓" : "· 계약서를 올리면 저장할 때 보고서 쪽 계약까지 자동")
              : "· 계약서를 올리면 저장할 때 시설물 카드에 자동으로 들어갑니다(같은 시설물 카드가 있으면 그 카드로)"}</span></div></div>
        <div class="sd-sector">${["민간", "관급"].map((s) => `<label><input type="radio" name="sd-sector" value="${s}"${st.sector === s ? " checked" : ""} /> ${s === "민간" ? "민간 — 계약서를 우리가 작성" : "관급 — 나라장터 계약서"}</label>`).join("")}</div>
        <div class="mail-label">서류 올리기 <span class="mail-note">— 읽어서 빈 칸을 채웁니다(PDF·한글·사진, 끌어다 놓아도 됨)</span></div>
        <div class="sd-ups">
          ${SEIS ? upChip("ledger", "건축물대장", "시설물관리대장.pdf", "건물명·위치·연면적") : upChip("ledger", "시설물관리대장", "시설물관리대장.pdf", "시설물명·위치·제원·관리주체")}
          ${civil ? upChip("bizreg", "사업자등록증", "사업자등록증.pdf", "관리주체·대표자·번호·주소") : ""}
          ${civil ? upChip(st.made_at ? "signed" : "existing", "날인본(도장 찍은 계약서)", "날인본.pdf", st.made_at ? "도장 찍어 받은 계약서 보관" : "이미 만든 계약서면 계약 칸까지 읽음")
            : upChip("g2b", "나라장터 계약서", "날인본.pdf", "읽어서 계약 칸을 채움(다시 올리면 읽은 칸만 바뀜)")}
          ${civil ? "" : estChip()}
        </div>
        ${unitBox()}
        <div class="mail-label">${civil ? "관리주체(갑)" : "발주처"}</div>
        <div class="cd-grid">
          ${field("client", civil ? "관리주체" : "발주처", { ph: civil ? "예: 청천영진아파트(위탁관리회사:미래티엠에스(주))" : "" })}
          ${civil ? field("client_rep", "대표자 줄", { em: "서명 칸", ph: "예: 관리사무소장 김춘화" }) : field("client_rep", "대표자")}
          ${field("client_biz_no", "사업자등록번호")}${field("client_address", "주소")}
        </div>
        <div class="mail-label">${SEIS ? "건물" : "시설물"}</div>
        <div class="cd-grid">
          ${field("facility_name", SEIS ? "건물명" : "시설물명")}${field("spec", "제원", { em: "비우면 줄을 뺌", ph: "예: 연면적 19,071.7m²" })}
          ${field("location", "위치", { wide: true })}
        </div>
        ${civil && !SEIS ? `<div class="mail-label${filled.includes("rounds") || filled.includes("unit") ? " sd-ai" : ""}">계약 회차 · 금액 <span class="mail-note">— 반기마다 한 줄(VAT포함). 계약서 "계약금액"에 회차마다 한 줄 + 총 합</span></div>
          <label class="sd-open"><input type="checkbox" class="sd-open-chk"${st.open_ended ? " checked" : ""} /> 끝 없는 계약 — 계약기간 "~ 계약 해지 시까지", 금액은 매 반기 단가만</label>
          ${roundsBlock()}
          ${st.open_ended ? "" : `<div class="mail-label">📅 도래주기 — 실시할 점검 <span class="mail-note">시행령 별표 3 · 1종 정기~정밀안전진단, 2종 ~정밀안전점검, 3종 정기만 · 건축물·토목 주기 다름</span></div>
          <div class="sd-cycle"><div class="mail-note">계산하는 중…</div></div>`}` : ""}
        <div class="mail-label">계약</div>
        <div class="cd-grid">
          ${civil && !SEIS ? "" : `${civil ? "" : field("contract_no", "계약번호")}<label class="cd-field${filled.includes("amount") ? " cd-ai" : ""}"><span>계약금액(원)${civil ? " <em>VAT포함</em>" : ""}</span><input class="sd-amount sd-won" inputmode="numeric" value="${won(st.amount)}" /></label>`}
          ${field("contract_date", "계약일", { type: "date" })}${field("start_date", "계약 시작일", { type: "date" })}
          ${civil && st.open_ended ? '<div class="cd-field"><span>계약 종료일</span><div class="cd-plain">계약 해지 시까지</div></div>' : field("end_date", "계약 종료일", { type: "date" })}
          ${civil ? field("doc_no", "문서번호", { em: "비우면 KFSC-연도-월일(계약일)", ph: st.auto_doc_no }) : ""}
          ${field("title", civil ? "계약건명" : "용역명", { wide: true, em: civil ? "비우면 자동" : "", ph: civil ? st.auto_title : "" })}
          ${SEIS ? "" : `<label class="cd-field"><span>반기 표시 <em>시설물 카드</em></span><select data-key="half_tag">
            <option value="">자동${st.half_auto ? `(${esc(st.half_auto)})` : ""}</option>${["상반기", "하반기", "상·하반기", "해당없음"].map((h) => `<option${st.half_tag === h ? " selected" : ""}>${h}</option>`).join("")}</select></label>`}
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
          ${!SEIS && st.files && st.files["대가내역서.pdf"] ? `<a href="${fileUrl(st, "대가내역서.pdf")}" target="_blank" rel="noopener">대가내역서 PDF</a>` : ""}
          ${!SEIS && st.files && st.files["대가내역서.xlsx"] ? `<a href="${fileUrl(st, "대가내역서.xlsx")}">엑셀</a>` : ""}
          ${SEIS ? "" : '<button type="button" class="sd-daega" title="계약 회차·동별 금액으로 대가내역서(형 양식) — FMS e-보고서에도 씀">📑 대가내역서</button>'}
          ${civil ? '<button type="button" class="mail-primary sd-make">📝 계약서 만들기</button>'
            : '<button type="button" class="sd-to-gov" data-kind="start">📑 착수계</button><button type="button" class="mail-primary sd-to-gov" data-kind="done">📑 완수계</button>'}
        </div>`;
      wire();
      if (clean) snapshot = JSON.stringify(body());
      if (st.prefill_note) msg(esc(st.prefill_note), "ok"); // 저장하면 st가 서버 응답으로 바뀌어 사라짐 — 그 전엔 다시 그려도 남김
      if (civil && !st.open_ended && !SEIS) loadCycle(false);
    }

    function wire() {
      box.querySelector(".sd-close").addEventListener("click", close);
      box.querySelector(".sd-save").addEventListener("click", () => save(false));
      box.querySelector(".sd-daega")?.addEventListener("click", async () => {
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
      box.querySelector(".sd-cover-ok")?.addEventListener("click", async () => { // ⚠ 맡는 건물 확인 끄기(현장 전체면 나중에 늘어난 건물까지)
        st.cover_ok = true;
        if (await save(true)) msg("✓ 맡는 건물을 확인했습니다.", "ok");
      });
      box.querySelectorAll(".uf-chk").forEach((i) => i.addEventListener("change", () => { // 시설물 체크 바꾸면 금액 칸 다시
        sync();
        st.cover_touched = true; // 사람이 고름 — 그 뒤로 자동으로 안 바꿈
        const ub = box.querySelector(".sd-ufac");
        st.facility_ids = [...ub.querySelectorAll(".uf-chk:checked")].map((x) => Number(x.value));
        st.amounts = { ...(st.amounts || {}), ...Object.fromEntries([...ub.querySelectorAll(".uf-amt")].map((x) => [x.dataset.id, num(x.value)])) };
        draw();
      }));
      box.querySelectorAll(".sd-won").forEach((i) => i.addEventListener("blur", () => { i.value = won(num(i.value)); }));
      const chk = box.querySelector(".sd-open-chk");
      if (chk) chk.addEventListener("change", () => { sync(); draw(); });
      const add = box.querySelector(".sd-add");
      if (add) add.addEventListener("click", () => {
        sync();
        const last = st.rounds[st.rounds.length - 1];
        const now = new Date();
        const nx = NEXT_HALF[last ? last.half : ""] || ["상반기", 0];
        st.rounds.push(last ? { year: (last.year || now.getFullYear()) + nx[1], half: nx[0], kind: last.kind, amount: last.amount, ...(last.parts ? { parts: last.parts.map((x) => ({ ...x })) } : {}) }
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
      box.querySelectorAll(".sd-round .r-kind").forEach((i) => i.addEventListener("change", () => { // 사람이 고른 종류 — 도래주기 자동이 안 바꿈
        const r = st.rounds[Number(i.closest(".sd-round").dataset.i)];
        if (r) manualKind.add(`${r.year}-${r.half}`);
      }));
      box.querySelectorAll(".sd-round .r-year, .sd-round .r-half").forEach((i) => i.addEventListener("change", () => { sync(); loadCycle(false); }));
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
      box.querySelectorAll(".sd-to-gov").forEach((b) => b.addEventListener("click", async () => { // 관급: 저장하고 착수계·완수계 창
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
      msg(kind === "signed" || kind === "estimate" ? "올리는 중…" : "읽는 중… (AI로 읽느라 20~40초)", "");
      try {
        const b = body();
        if (!st.id) await ensure();
        else st = await api(`${P}/contracts/${st.id}`, { method: "PUT", body: JSON.stringify(b) });
        const fd = new FormData();
        fd.append("file", file);
        const out = await apiUpload(kind === "estimate" ? `${P}/contracts/${st.id}/estimate` : `${P}/contracts/${st.id}/upload/${kind}`, fd);
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
        else if (kind === "estimate") msg(`✓ 내역서를 붙였습니다 — 착수계 붙임 "산출내역서"에 그대로 들어갑니다.${out.est_note ? `<br>${esc(out.est_note)}` : ""}${out.error ? `<br>⚠ ${esc(out.error)}` : ""}`, out.error ? "warn" : "ok");
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
  enableFileDrop(document.getElementById("sd-drop-civil"), existing);

  // 관급 — 나라장터 계약서를 읽어 새 관급 계약. 내역서를 먼저 골라 두면 계약서를 올릴 때 같이 붙임(계약서 먼저면 계약 창의 [📎 내역서])
  let pendingEst = null;
  const est = document.getElementById("sd-est"), estNote = document.getElementById("sd-est-note");
  const EST_HINT = estNote.innerHTML;
  const showEst = () => {
    estNote.innerHTML = pendingEst ? `✓ ${esc(pendingEst.name)} — 나라장터 계약서를 올리면 같이 붙습니다 <button type="button" class="sd-est-x" title="빼기">✕</button>` : EST_HINT;
    document.getElementById("sd-drop-est").classList.toggle("on", !!pendingEst);
    estNote.querySelector(".sd-est-x")?.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); pendingEst = null; showEst(); });
  };
  est.addEventListener("change", () => {
    if (est.files[0]) pendingEst = est.files[0];
    est.value = "";
    showEst();
  });
  enableFileDrop(document.getElementById("sd-drop-est"), est);
  const g2b = document.getElementById("sd-g2b");
  g2b.addEventListener("change", async () => {
    const file = g2b.files[0];
    g2b.value = "";
    if (!file) return;
    const m = document.getElementById("sd-new-msg");
    m.textContent = "나라장터 계약서를 읽는 중… (20~40초)";
    m.className = "status";
    try {
      const fd = new FormData();
      fd.append("file", file);
      let out = await apiUpload(`${P}/contracts/from-g2b`, fd);
      let estMsg = "";
      if (pendingEst) {
        try {
          const fe = new FormData();
          fe.append("file", pendingEst);
          out = { ...out, ...(await apiUpload(`${P}/contracts/${out.id}/estimate`, fe)) };
          estMsg = `<br>✓ 내역서도 붙였습니다(착수계 붙임 산출내역서).${out.est_note ? ` ${esc(out.est_note)}` : ""}`;
          pendingEst = null;
          showEst();
        } catch (err) { estMsg = `<br>⚠ 내역서는 못 붙였습니다 — 계약 창의 [📎 내역서]로 다시 올려 주세요. (${esc(err.message)})`; }
      }
      m.textContent = "";
      await load();
      openContract(out.id, "관급", { filled: out.filled, message: (out.error ? esc(out.error) : out.auto_card ? esc(out.auto_card)
        : "✓ 나라장터 계약서를 읽어 새 관급 계약으로 등록했습니다 — 노란 칸을 확인하세요.") + estMsg, tone: out.error ? "warn" : "ok" });
    } catch (err) {
      m.textContent = err.message;
      m.className = "status bad";
    }
  });
  enableFileDrop(document.getElementById("sd-drop-gov"), g2b);

  // 민간 계약서 양식 받기·올리기
  document.getElementById("sd-tpl-get").href = `${BASE}/api${P}/template${SEIS ? "?field=seismic" : ""}`; // 링크는 요청 머리를 못 붙여 주소로
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
