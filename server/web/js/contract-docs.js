// ---------- 착수계·완수계 창(2026-10-06 — server/api/routers/contracts.py) ----------
// 용역 계약 하나 기준(계약은 현장보다 먼저 생김 — 형). 서류 자동화 계약 목록(docs.html)과 현장 화면 버튼(연결된 계약)이 연다.
// contractId가 비면 [+ 새 계약] — 빈 화면(GET /contracts/blank)으로 열고, 처음 무언가 할 때(계약서·붙임 올리기·현장 연결·만들기) 계약을 만든다(ensure)
// — 아무것도 안 하고 닫으면 빈 계약이 남지 않게(10/6 사용자).
// 1) 용역계약서 PDF 올리기 → 발주처·용역명·계약번호·금액·날짜가 채워짐(고칠 수 있음, 착수계 때 넣으면 완수계 때 그대로)
// 2) 문서번호·인사말("귀 ○의")·(완수계) 발송일·정산금액·실제준공일 3) (착수계) 현장대리인 1명 + 참여기술자 0~N명
// 4) 붙임 서류(받아 온 파일) 올리기 5) 도장 넣기/빼기 → [만들기] → 엑셀 + 합본 PDF 받기. 빠진 서류·유효기간 지난 서류는 막지 않고 경고(사용자 10/6).
// 완수계: 붙임에 완수내역서가 있을 때만 "검사 및 납품조서"(한글 양식) 표 칸이 보이고 합본에 들어감 — 값은 완수내역서에서 읽음(10/8 형·사용자).
// 창 틀은 css/mail.css(mail.js의 mailEsc도 씀), 이 창 규칙은 css/contract-docs.css.

const CD_LABEL = { start: "착수계", done: "완수계" };

async function openContractDocs(contractId, kind, onDone, readInfo) {
  const overlay = document.createElement("div");
  overlay.className = "mail-overlay";
  overlay.innerHTML = '<div class="mail-box cd-box" role="dialog" aria-modal="true"><div class="mail-wait">불러오는 중…</div></div>';
  document.body.appendChild(overlay);
  const box = overlay.querySelector(".mail-box");
  let busy = false;
  let changed = false;
  let dirty = false; // 칸을 고쳤는데 아직 저장 안 함 — 닫을 때 저장(이미 있는 계약만, 10/6: 담당자만 적고 닫아도 남게)
  const close = async () => {
    if (busy) return;
    if (dirty && contractId) {
      try {
        await api(`/contracts/${contractId}`, { method: "PUT", body: JSON.stringify(contractBody()) });
        changed = true;
      } catch (err) {
        if (!confirm(`고친 칸을 저장하지 못했습니다(${err.message}). 그래도 닫을까요?`)) return;
      }
    }
    overlay.remove();
    document.removeEventListener("keydown", onKey);
    if (changed && onDone) onDone();
  };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });
  const label = CD_LABEL[kind];
  const head = () => `<div class="mail-head"><b>📑 ${label}</b><span class="mail-sub">${mailEsc(st?.title ? st.label : "새 용역 계약")}</span>
    ${st ? `<span class="mail-sub cd-site-line">현장: ${st.site_label ? `<a href="site.html?id=${st.site_id}">${mailEsc(st.site_label)}</a>` : "아직 연결 안 됨"}
      <button type="button" class="cd-link-btn">${st.site_label ? "바꾸기" : "현장 연결"}</button></span>` : ""}</div>`;

  let st = null;
  try {
    st = await api(contractId ? `/contracts/${contractId}` : "/contracts/blank");
  } catch (err) {
    box.innerHTML = `${head()}<div class="mail-msg bad">${mailEsc(err.message)}</div><div class="mail-foot"><button type="button" class="cd-close">닫기</button></div>`;
    box.querySelector(".cd-close").addEventListener("click", close);
    return;
  }
  // 아직 없는 계약([+ 새 계약])이면 지금까지 적은 값으로 만든다 — 붙임 올리기·현장 연결·만들기 전에
  async function ensure() {
    if (contractId) return contractId;
    const keep = { agent_id: st.agent_id, participant_ids: st.participant_ids };
    const out = await apiPost("/contracts", contractBody());
    contractId = out.id;
    changed = true;
    st = { ...out, ...keep };
    return contractId;
  }

  // 창 어디든 계약서 PDF를 끌어다 놓으면 계약서로(붙임 서류 칸에 놓으면 그 칸이 먼저 받음 — 10/6 사용자)
  enableFileDrop(box, () => box.querySelector(".cd-upload input"));
  const typed = {}; // 사람이 직접 고친 칸(문서번호·인사말) — 계약 값이 바뀌어도 덮어쓰지 않음
  let aiFilled = [];
  draw(readNote(readInfo));

  // 계약서 읽은 결과 안내 — 글자 규칙으로 못 읽은 칸을 AI가 채웠으면 노란 칸 + "확인하세요"(사용자 10/6)
  function readNote(info) {
    if (!info) return "";
    aiFilled = info.ai_filled || [];
    const names = { client: "발주처", title: "용역명", contract_no: "계약번호", amount: "계약금액", contract_date: "계약일", start_date: "착수일", end_date: "완수일" };
    const parts = [];
    const contactNames = { client_manager: "계약 담당자", client_phone: "계약 담당 연락처", client_email: "계약 담당 이메일",
      biz_manager: "사업 담당자", biz_phone: "사업 담당 연락처", biz_email: "사업 담당 이메일" }; // 못 읽어도 안내 안 함(없는 계약서가 많음)
    if (aiFilled.length) parts.push(`<div class="mail-msg warn">🤖 AI로 읽은 칸: ${aiFilled.map((k) => names[k] || contactNames[k] || k).join("·")} — 계약서와 맞는지 확인하세요(노란 칸).</div>`);
    if (info.ai_error) parts.push(`<div class="mail-msg warn">AI로 읽지 못했습니다(${mailEsc(info.ai_error)}) — 빈 칸은 직접 채우세요.</div>`);
    const left = (info.unread || []).filter((k) => !aiFilled.includes(k) && names[k]);
    if (left.length) parts.push(`<div class="mail-msg warn">못 읽은 칸: ${left.map((k) => names[k]).join("·")} — 직접 채우세요.</div>`);
    if (!parts.length) parts.push('<div class="mail-msg ok">✓ 계약서를 읽었습니다 — 칸을 확인하세요.</div>');
    return parts.join("");
  }

  // 발주처 담당자 칸(계약·사업) — 서류 값(st.contract)이 아니라 계약 자체 값(st.client_*·st.biz_*)이라 따로(관리번호와 같음)
  const CONTACT_KEYS = ["client_manager", "client_phone", "client_email", "biz_manager", "biz_phone", "biz_email"];
  function ct(key, ph, type = "text") {
    return `<input class="cd-in${aiFilled.includes(key) ? " cd-ai-in" : ""}" data-key="${key}" type="${type}" placeholder="${ph}" value="${mailEsc(st[key] || "")}" aria-label="${ph}" />`;
  }

  function field(key, text, type = "text", wide = false) {
    const v = st.contract[key] ?? "";
    return `<label class="cd-field${wide ? " cd-wide" : ""}${aiFilled.includes(key) ? " cd-ai" : ""}"><span>${text}</span><input class="cd-in" data-key="${key}" type="${type}" value="${mailEsc(v)}" /></label>`;
  }

  function draw(result) {
    const c = st.contract;
    const d = st.defaults;
    const made = st.made[kind];
    const peopleHtml = kind === "start" ? peopleBlock() : companyBlock();
    box.innerHTML = `${head()}
      <div class="mail-label">용역 계약 <span class="mail-note">— 계약서 PDF를 올리면 채워집니다(착수계·완수계 같이 씀)</span></div>
      <div class="cd-pdf">
        <label class="drop-box cd-upload"><span class="drop-ico">📎</span>
          <span class="drop-txt"><b class="drop-pc">용역계약서 PDF를 여기에 끌어다 놓으세요</b><b class="drop-touch">눌러서 용역계약서 PDF 고르기</b>
            <span class="drop-pc">눌러서 고를 수도 있어요(창 어디에 놓아도 됨)</span></span>
          <input type="file" accept="application/pdf,.pdf" hidden data-kr-file="skip" /></label>
        <span class="mail-note cd-pdf-msg">${c.has_pdf ? `✓ <a href="${BASE}/api/contracts/${contractId}/pdf" target="_blank" rel="noopener">올린 계약서</a>가 있습니다 — 다시 올리면 읽은 칸만 바뀝니다` : "아직 안 올림 — 직접 적어도 됩니다"}</span>
      </div>
      <div class="cd-grid">
        <label class="cd-field"><span>관리번호 <em>목록에 "26-3)_용역명"으로 보임</em></span>
          <span class="cd-mgmt"><input class="cd-in" data-key="management_no" value="${mailEsc(st.management_no || "")}" /><button type="button" class="cd-mgmt-auto">자동생성</button></span></label>
        <div></div>
      </div>
      <div class="mail-label">발주처 담당자 <span class="mail-note">— 사업 담당자 메일이 착수계·완수계 E-mail 기본 받는 곳</span></div>
      <div class="cd-contacts">
        <span></span><span class="cd-ct-h">이름</span><span class="cd-ct-h">연락처</span><span class="cd-ct-h">이메일</span>
        <b>계약 담당자</b>${ct("client_manager", "계약부서")}${ct("client_phone", "연락처", "tel")}${ct("client_email", "이메일", "email")}
        <b>사업 담당자</b>${ct("biz_manager", "사업부서")}${ct("biz_phone", "연락처", "tel")}${ct("biz_email", "이메일", "email")}
      </div>
      <div class="cd-grid">
        ${field("client", "발주처")}${field("contract_no", "계약번호")}
        ${field("title", "용역명", "text", true)}
        ${field("amount", "계약금액(원)", "number")}${field("contract_date", "계약일", "date")}
        ${field("start_date", "착수일", "date")}${field("end_date", kind === "done" ? "준공기한" : "완수일", "date")}
        ${kind === "done" ? `${field("settle_amount", "정산금액(원) <em>비우면 계약금액</em>", "number")}${field("actual_end_date", "실제준공일 <em>비우면 준공기한</em>", "date")}` : ""}
      </div>
      <div class="mail-label">갑지</div>
      <div class="cd-grid">
        <label class="cd-field"><span>문서번호 <em>KFSC21C_계약번호_${kind === "start" ? "착수일" : "발송일"}(월일)</em></span><input class="cd-docno" value="${mailEsc(typed.docno ?? autoDocNo())}" /></label>
        <label class="cd-field"><span>인사말</span><span class="cd-greet">1. 귀 <input class="cd-greeting" value="${mailEsc(typed.greeting ?? d.greeting)}" /> 의 무궁한 발전을…</span></label>
        ${kind === "done" ? `<label class="cd-field"><span>발송일</span><input class="cd-send" type="date" value="${mailEsc(typed.send ?? d.send_date)}" /></label>` : ""}
        <div class="cd-field"><span>담당</span><div class="cd-plain">${mailEsc(d.contact_name)} <a href="docs-settings.html#contract-library" class="mail-note">바꾸기(설정 탭)</a></div></div>
      </div>
      ${peopleHtml}
      ${attachBlock()}
      ${kind === "done" ? `<div class="cd-insp-wrap">${inspBlock()}</div>` : ""}
      <div class="mail-label">대표이사 도장</div>
      <div class="cd-radios">
        <label><input type="radio" name="cd-seal" value="1" checked /> 넣기 <span class="mail-note">(사본 제출용 — "(인)"·원본대조필 칸에)</span></label>
        <label><input type="radio" name="cd-seal" value="0" /> 빼기 <span class="mail-note">(원본 — 인쇄 뒤 직접 날인)</span></label>
      </div>
      ${result || ""}
      ${submitBlock()}
      ${made.at && !result ? `<div class="cd-made">지난번 만든 것 ${mailEsc(made.at)} — 아래 버튼으로 받기</div>` : ""}
      <div class="mail-foot cd-foot"><button type="button" class="cd-close">닫기</button>
        ${made.xlsx ? dl("xlsx", "엑셀 받기") : ""}${made.hwpx ? dl("hwpx", "한글 받기") : ""}${made.pdf ? dl("pdf", "PDF 보기", true) + dl("pdf", "PDF 받기") : ""}
        <button type="button" class="mail-primary cd-make">${label} ${made.at ? "다시 " : ""}만들기</button></div>`;
    box.querySelector(".cd-close").addEventListener("click", close);
    box.querySelector(".cd-make").addEventListener("click", make);
    box.querySelector(".cd-mgmt-auto").addEventListener("click", async () => {
      try {
        const out = await api("/contracts/next-management-no");
        const inp = box.querySelector('.cd-in[data-key="management_no"]');
        inp.value = out.management_no;
        st.management_no = out.management_no;
      } catch (err) {
        alert(err.message);
      }
    });
    box.querySelector(".cd-link-btn").addEventListener("click", async () => { await ensure(); openLinkSite(contractId, async () => {
      const keep = { agent_id: st.agent_id, participant_ids: st.participant_ids };
      st = { ...(await api(`/contracts/${contractId}`)), ...keep };
      changed = true;
      draw();
    }); });
    box.querySelector(".cd-upload input").addEventListener("change", uploadPdf);
    box.querySelector(".cd-docno").addEventListener("input", (e) => { typed.docno = e.target.value; });
    box.querySelector(".cd-greeting").addEventListener("input", (e) => { typed.greeting = e.target.value; });
    box.querySelector(".cd-send")?.addEventListener("input", (e) => { typed.send = e.target.value; refreshDocNo(); });
    box.querySelectorAll(".cd-in").forEach((el) => el.addEventListener("input", () => {
      dirty = true;
      if (el.dataset.key === "management_no" || CONTACT_KEYS.includes(el.dataset.key)) st[el.dataset.key] = el.value;
      else st.contract[el.dataset.key] = el.value;
      refreshDocNo();
    }));
    if (kind === "start") wirePeople();
    wireAttach();
    wireInsp();
    wireSubmit();
  }

  // ---------- 검사 및 납품조서(완수계 붙임 5번, 10/8) — 완수내역서가 있을 때만. 값은 완수내역서 그대로(원래 서류와 1원도 안 틀리게) ----------
  // 준공 횟수를 바꾸면 준공 금액 = 횟수 × 단가로 다시 계산(형) — 부가세 10% 버림, 계는 10원 미만 버림, 손으로 고칠 수 있음.
  // 준공 계 = 정산금액(완수계 서류끼리 같은 값). 서버 규칙은 server/contract_docs/inspection.py
  // 함수 선언으로(창을 열 때 draw가 먼저 부르므로 const 화살표 함수는 아직 없음 — 10/8)
  function insKeys() { return ["qty", "supply", "vat", "total", "done_qty", "done_supply", "done_vat", "done_total"]; }
  function hasDoneList() { return (st.attachments.done.find((s) => s.slot === "done_list")?.files || []).length > 0; }
  function insNum(v) { return v === "" || v == null || Number.isNaN(Number(v)) ? null : Number(v); }
  function won(n) { return n == null ? "" : n.toLocaleString("ko-KR"); }
  function inspBlock() {
    if (!hasDoneList()) return "";
    const d = st.inspection || {};
    const ph = { qty: "횟수", supply: "공급가액", vat: "부가세", total: "계" };
    const inp = (k) => `<label class="cd-ins-f"><span>${ph[k.replace("done_", "")]}</span><input class="cd-ins" data-ins="${k}" type="number"
      inputmode="numeric" value="${d[k] ?? ""}" aria-label="${k.startsWith("done_") ? "준공" : "계약"} ${ph[k.replace("done_", "")]}" /></label>`;
    return `<div class="mail-label">검사 및 납품조서 <span class="mail-note">— 완수내역서에서 읽은 값(고칠 수 있음) · 합본 PDF에서 완수내역서 다음</span></div>
      <div class="cd-contacts cd-insp">
        <span></span><span class="cd-ct-h">횟수</span><span class="cd-ct-h">공급가액</span><span class="cd-ct-h">부가세</span><span class="cd-ct-h">계(단수조정)</span>
        <b>계약</b>${inp("qty")}${inp("supply")}${inp("vat")}${inp("total")}
        <b>준공</b>${inp("done_qty")}${inp("done_supply")}${inp("done_vat")}${inp("done_total")}
      </div>
      <div class="mail-note cd-insp-note">${inspNote()}</div>`;
  }
  function inspNote() {
    const d = st.inspection || {};
    if (d.qty == null || d.total == null) return '<span class="cd-bad">완수내역서에서 횟수·금액을 못 읽었습니다 — 칸을 채우세요(비면 이 서류는 빠짐)</span>';
    const unit = d.supply != null && d.qty ? Math.round(d.supply / d.qty) : null;
    const dq = (d.done_qty ?? d.qty) - d.qty, dt = (d.done_total ?? d.total) - d.total;
    return `단가 ${won(unit)}원 · ${dq || dt ? `증감 ${dq ? `${dq > 0 ? "+" : ""}${dq}회, ` : ""}${won(dt)}원` : "증감 없음(공란)"} · 준공 계는 정산금액으로 들어갑니다`;
  }
  function wireInsp() {
    box.querySelectorAll(".cd-ins").forEach((el) => el.addEventListener("input", () => {
      st.inspection = { ...(st.inspection || {}), [el.dataset.ins]: insNum(el.value) };
      const d = st.inspection;
      if (el.dataset.ins === "done_qty" && d.done_qty != null && d.qty && d.supply != null) { // 준공 횟수 → 금액 다시 계산(형)
        d.done_supply = d.done_qty * Math.round(d.supply / d.qty);
        d.done_vat = Math.floor(d.done_supply / 10);
        d.done_total = Math.floor((d.done_supply + d.done_vat) / 10) * 10;
        for (const k of ["done_supply", "done_vat", "done_total"]) box.querySelector(`.cd-ins[data-ins="${k}"]`).value = d[k];
      }
      if (["done_qty", "done_total"].includes(el.dataset.ins) && d.done_total != null) { // 준공 계 = 정산금액
        st.contract.settle_amount = d.done_total;
        const s = box.querySelector('.cd-in[data-key="settle_amount"]');
        if (s) s.value = d.done_total;
      }
      dirty = true;
      box.querySelector(".cd-insp-note").innerHTML = inspNote();
    }));
  }
  function redrawInsp() {
    const wrap = box.querySelector(".cd-insp-wrap");
    if (!wrap) return;
    wrap.innerHTML = inspBlock();
    wireInsp();
  }

  // ---------- 제출(사용자 10/6) — E-mail(합본 PDF를 바로 보냄)·직접 제출·우편 제출, 여러 방식 함께. 기록이 있으면 제출 ----------
  function submitBlock() {
    const m = st.made[kind];
    if (!contractId) return '<div class="cd-submit-wrap"></div>'; // 저장된 계약이면 착수계·완수계 창 모두 늘 보임(10/6 사용자)
    const recs = m.submits.map((r) => `<div class="cd-sub-rec"><span class="cd-ok">✓ ${mailEsc(r.date.slice(5).replace("-", "/"))} ${mailEsc(r.label)} 제출</span>
      ${r.to ? `<span class="mail-note">→ ${mailEsc(r.to)}</span>` : ""}<button type="button" class="cd-x cd-sub-del" data-id="${r.id}" title="이 기록 지우기">✕</button></div>`).join("");
    return `<div class="cd-submit-wrap"><div class="mail-label">제출 <span class="mail-note">— 여러 방식을 함께 기록할 수 있어요(E-mail은 합본 PDF를 바로 보냄)</span></div>
      ${recs || `<div class="mail-note">아직 제출 기록 없음 — 아래에서 고르세요</div>`}
      ${m.pdf ? "" : `<div class="mail-note">${label} PDF를 만들면 E-mail로도 바로 보낼 수 있어요</div>`}
      <div class="cd-sub-btns">${m.pdf ? '<button type="button" data-m="email">📧 E-mail로 보내기</button>' : ""}
        <button type="button" data-m="direct">🏢 직접 제출</button><button type="button" data-m="post">📮 우편 제출</button></div>
      <div class="cd-sub-form"></div><div class="cd-sub-msg"></div></div>`;
  }

  function wireSubmit() {
    const wrap = box.querySelector(".cd-submit-wrap");
    if (!wrap) return;
    const form = wrap.querySelector(".cd-sub-form");
    const msg = wrap.querySelector(".cd-sub-msg");
    const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    wrap.querySelectorAll(".cd-sub-btns button").forEach((b) => b.addEventListener("click", () => {
      wrap.querySelectorAll(".cd-sub-btns button").forEach((x) => x.classList.toggle("on", x === b));
      const m = b.dataset.m;
      form.innerHTML = m === "email"
        ? `<input class="cd-sub-to" type="email" placeholder="받는 메일(여러 곳은 쉼표로)" value="${mailEsc(st.biz_email || st.client_email || "")}" />
           <button type="button" class="mail-primary cd-sub-go">보내기</button>`
        : `<label class="cd-sub-date">${m === "direct" ? "직접 제출" : "우편 제출"}일 <input type="date" class="cd-sub-day" value="${today}" /></label>
           <button type="button" class="mail-primary cd-sub-go">저장</button>`;
      form.querySelector(".cd-sub-go").addEventListener("click", () => save(m));
    }));
    wrap.querySelectorAll(".cd-sub-del").forEach((b) => b.addEventListener("click", async () => {
      if (!confirm("이 제출 기록을 지울까요? (E-mail은 이미 보낸 메일이 되돌려지지는 않습니다)")) return;
      try {
        const out = await api(`/contracts/${contractId}/submit/${b.dataset.id}`, { method: "DELETE" });
        st.made = out.made;
        changed = true;
        redrawSubmit();
      } catch (err) {
        msg.textContent = err.message;
      }
    }));
    async function save(m) {
      const go = form.querySelector(".cd-sub-go");
      const body = { method: m };
      if (m === "email") {
        body.to = form.querySelector(".cd-sub-to").value.trim();
        if (!body.to) { msg.textContent = "받는 메일을 적으세요."; return; }
        if (!confirm(`${label} 합본 PDF를 ${body.to}(으)로 보낼까요?`)) return;
      } else {
        body.submitted_on = form.querySelector(".cd-sub-day").value;
      }
      go.disabled = true;
      go.textContent = m === "email" ? "보내는 중…" : "저장 중…";
      busy = true;
      try {
        const out = await apiPost(`/contracts/${contractId}/submit/${kind}`, body);
        st.made = out.made;
        if (m === "email" && !st.biz_email && !st.client_email && !body.to.includes(",")) st.biz_email = body.to;
        changed = true;
        redrawSubmit(m === "email" ? "✓ 보냈습니다" : "✓ 저장했습니다");
      } catch (err) {
        go.disabled = false;
        go.textContent = m === "email" ? "보내기" : "저장";
        msg.textContent = err.message;
        msg.className = "cd-sub-msg cd-bad";
      } finally {
        busy = false;
      }
    }
  }

  function redrawSubmit(note) {
    const tmp = document.createElement("div");
    tmp.innerHTML = submitBlock();
    box.querySelector(".cd-submit-wrap").replaceWith(tmp.firstElementChild);
    wireSubmit();
    if (note) { const m = box.querySelector(".cd-sub-msg"); if (m) { m.textContent = note; m.className = "cd-sub-msg cd-ok"; } }
  }

  // 붙임 파일(받아 오는 서류 — 산출내역서·완수내역서·기술지도보고서·완료증명서): 올리면 합본 PDF에 갑지 붙임 순서대로 들어감(10/6 형)
  function attachBlock() {
    const slots = st.attachments[kind];
    return `<div class="mail-label">붙임 서류 <span class="mail-note">— 받아 온 파일을 올리거나 칸에 끌어다 놓으면 합본 PDF에 순서대로 들어갑니다(PDF·그림·엑셀·워드·한글)</span></div>
      <div class="cd-attach">${slots.map((sl) => `<div class="cd-slot" data-slot="${sl.slot}">
        <div class="cd-slot-head"><b>${mailEsc(sl.label)}</b>
          <label class="cd-add">+ 파일 올리기<input type="file" multiple hidden data-kr-file="skip"
            accept=".pdf,.jpg,.jpeg,.png,.gif,.bmp,.tif,.tiff,.webp,.xlsx,.xls,.xlsm,.docx,.doc,.pptx,.ppt,.hwp,.hwpx" /></label></div>
        ${sl.files.length ? sl.files.map((f) => `<div class="cd-file">
          <a href="${BASE}/api/contracts/${contractId}/docs/${kind}/attach/${sl.slot}/${encodeURIComponent(f.name)}" target="_blank" rel="noopener">📄 ${mailEsc(f.title)}</a>
          <span class="mail-note">${f.pages}장</span>
          <button type="button" class="cd-x" data-name="${mailEsc(f.name)}" title="빼기">✕</button></div>`).join("")
          : '<div class="mail-note cd-none">아직 없음 — 없으면 빼고 합칩니다</div>'}
        <div class="drop-box drop-sm cd-slot-drop"><b class="drop-pc">⬇ 여기에 끌어다 놓기</b><b class="drop-touch">눌러서 파일 고르기</b><span class="drop-pc">(여러 개 가능 · 눌러서 고르기)</span></div>
        <div class="mail-note cd-slot-msg"></div></div>`).join("")}</div>`;
  }

  function wireAttach() {
    box.querySelectorAll(".cd-slot").forEach((el) => {
      const slot = el.dataset.slot;
      const msg = el.querySelector(".cd-slot-msg");
      enableFileDrop(el, el.querySelector(".cd-add input"));
      el.querySelector(".cd-slot-drop").addEventListener("click", () => el.querySelector(".cd-add input").click());
      el.querySelector(".cd-add input").addEventListener("change", async (e) => {
        const picked = [...e.target.files];
        if (!picked.length) return;
        busy = true;
        try {
          await ensure();
          for (const [i, file] of picked.entries()) {
            const hwp = /\.hwpx?$/i.test(file.name);
            msg.textContent = `올리는 중 ${picked.length > 1 ? `${i + 1}/${picked.length} ` : ""}— ${file.name}${hwp ? " (한글 파일은 PDF로 바꾸느라 1분쯤 걸릴 수 있음)" : ""}`;
            const fd = new FormData();
            fd.append("file", file);
            st.attachments[kind] = await apiUpload(`/contracts/${contractId}/docs/${kind}/attach/${slot}`, fd);
          }
          if (slot === "done_list") { // 새 완수내역서 → 서버가 읽은 표 값·정산금액(10/8)
            const fresh = await api(`/contracts/${contractId}`);
            st.inspection = fresh.inspection;
            st.contract.settle_amount = fresh.contract.settle_amount;
            const s = box.querySelector('.cd-in[data-key="settle_amount"]');
            if (s) s.value = st.contract.settle_amount ?? "";
          }
          redrawAttach();
        } catch (err) {
          redrawAttach();
          const m = box.querySelector(`.cd-slot[data-slot="${slot}"] .cd-slot-msg`);
          m.textContent = err.message;
          m.classList.add("cd-bad");
        } finally {
          busy = false;
        }
      });
      el.querySelectorAll(".cd-x").forEach((btn) => btn.addEventListener("click", async () => {
        if (!confirm(`${btn.dataset.name.replace(/^\d+_/, "")} 파일을 뺄까요?`)) return;
        try {
          st.attachments[kind] = await api(`/contracts/${contractId}/docs/${kind}/attach/${slot}/${encodeURIComponent(btn.dataset.name)}`, { method: "DELETE" });
          redrawAttach();
        } catch (err) {
          msg.textContent = err.message;
        }
      }));
    });
  }

  function redrawAttach() { // 붙임 칸만 다시 그림(위에 적던 칸 값은 그대로)
    const old = box.querySelector(".cd-attach");
    const tmp = document.createElement("div");
    tmp.innerHTML = attachBlock();
    old.replaceWith(tmp.querySelector(".cd-attach"));
    wireAttach();
    redrawInsp(); // 완수내역서를 올리거나 빼면 검사 및 납품조서 칸도 보이거나 숨음
  }

  // 문서번호 = KFSC21C_계약번호_월일(사용자 10/6 회사 확인 — 착수계는 착수일, 완수계는 발송일). server build.default_doc_no와 같은 규칙.
  // 손으로 고친 뒤엔 그대로 두고, 아니면 계약번호·날짜를 고칠 때 따라 바뀐다.
  function autoDocNo() {
    const no = (st.contract.contract_no || "").trim();
    if (!no) return "";
    const day = kind === "start" ? st.contract.start_date : (typed.send ?? st.defaults.send_date);
    return `KFSC21C_${no}${day ? `_${day.slice(5, 7)}${day.slice(8, 10)}` : ""}`;
  }
  function refreshDocNo() {
    if (typed.greeting === undefined) box.querySelector(".cd-greeting").value = greetingWord(st.contract.client);
    if (typed.docno !== undefined) return;
    box.querySelector(".cd-docno").value = autoDocNo();
  }

  // "귀 ○의" — 발주처를 손으로 적을 때도 따라 바뀌게. 규칙은 server/contract_docs/build.py greeting_word와 같음(바꾸면 둘 다)
  function greetingWord(client) {
    const c = (client || "").trim();
    if (/(사단|여단|군단|연대|대대|부대|사령부)$/.test(c)) return "부대";
    if (c.slice(-4).includes("공사")) return "사";
    if (c.endsWith("공단")) return "공단";
    for (const end of ["청", "시", "군", "구", "도"]) if (c.endsWith(end)) return end;
    for (const word of c.split(/\s+/).slice(0, -1).reverse()) {
      for (const end of ["청", "시", "군", "구"]) if (word.endsWith(end)) return end;
    }
    return "기관";
  }

  function dl(ext, text, inline = false) {
    // 받을 이름 "용역명_착수계.xlsx"를 링크에 직접 — download가 비면 브라우저가 주소 끝(start.xlsx)을 이름으로 쓰기도 함(10/6 실측)
    const name = `${(st.title || "용역").replace(/[\\/:*?"<>|]/g, "_").slice(0, 40)}_${ext === "hwpx" ? "검사및납품조서" : label}.${ext}`;
    return `<a href="${BASE}/api/contracts/${contractId}/docs/${kind}.${ext}${inline ? "?inline=1" : ""}" ${inline ? 'target="_blank" rel="noopener"' : `download="${mailEsc(name)}"`}>${text}</a>`;
  }

  function personNote(p) {
    const bits = [];
    if (p.missing.length) bits.push(`<span class="cd-bad">${mailEsc(p.missing.join("·"))} 없음</span>`);
    if (p.expired.length) bits.push(`<span class="cd-bad">${mailEsc(p.expired.join("·"))} 기간 지남</span>`);
    if ((p.nodate || []).length) bits.push(`<span class="cd-bad">${mailEsc(p.nodate.join("·"))} 발급일 모름</span>`);
    return [mailEsc([p.qualification.replace(/\n/g, "·"), p.grade].filter(Boolean).join(" · ")), ...bits].filter(Boolean).join(" · ");
  }

  function peopleBlock() {
    if (!st.persons.length) {
      return `<div class="mail-label">기술자</div><div class="mail-msg warn">기술자 명단이 비어 있습니다 — <a href="docs-settings.html#contract-library">설정 탭 → 착수계·완수계 서류</a>에서 먼저 추가하세요.</div>`;
    }
    const agent = st.agent_id ?? st.persons[0].id;
    return `<div class="mail-label">현장대리인(책임기술자) <span class="mail-note">— 1명</span></div>
      <select class="cd-agent">${st.persons.map((p) => `<option value="${p.id}" ${p.id === agent ? "selected" : ""}>${mailEsc(p.name)}</option>`).join("")}</select>
      <div class="mail-label">참여기술자 <span class="mail-note">— 0명부터 여러 명, 고른 순서대로 들어감</span></div>
      <div class="cd-people">${st.persons.map((p) => `<label class="cd-person" data-id="${p.id}">
        <input type="checkbox" value="${p.id}" ${st.participant_ids.includes(p.id) ? "checked" : ""} />
        <span><b>${mailEsc(p.name)}</b><span class="mail-note">${personNote(p)}</span></span></label>`).join("")}</div>
      <div class="mail-note"><a href="docs-settings.html#contract-library">기술자 추가·서류 올리기(설정 탭)</a></div>`;
  }

  function wirePeople() {
    const sel = box.querySelector(".cd-agent");
    if (!sel) return;
    const sync = () => { // 현장대리인으로 고른 사람은 참여기술자에서 뺌
      box.querySelectorAll(".cd-person").forEach((row) => {
        const isAgent = row.dataset.id === sel.value;
        row.classList.toggle("is-agent", isAgent);
        const chk = row.querySelector("input");
        chk.disabled = isAgent;
        if (isAgent) chk.checked = false;
      });
      st.agent_id = Number(sel.value);
    };
    sel.addEventListener("change", sync);
    box.querySelectorAll(".cd-person input").forEach((chk) => chk.addEventListener("change", () => {
      const id = Number(chk.value);
      st.participant_ids = chk.checked ? [...st.participant_ids.filter((x) => x !== id), id] : st.participant_ids.filter((x) => x !== id);
    }));
    sync();
  }

  function companyBlock() {
    const rows = st.company_docs.map((doc) => {
      const s = doc.status === "ok" ? `<span class="cd-ok">✓${doc.valid_until ? ` ${mailEsc(doc.valid_until)}까지` : ""}</span>`
        : doc.status === "expired" ? `<span class="cd-bad">⚠ 기간 지남(${mailEsc(doc.valid_until)})</span>`
        : doc.status === "nodate" ? '<span class="cd-bad">⚠ 발급일 모름</span>' : '<span class="cd-bad">없음</span>';
      return `<div><span>${mailEsc(doc.label)}</span><div>${s}</div></div>`;
    }).join("");
    return `<div class="mail-label">붙는 회사 서류 <span class="mail-note">— <a href="docs-settings.html#contract-library">설정 탭에서 바꾸기</a></span></div>
      <div class="mail-info cd-docs">${rows}</div>`;
  }

  function contractBody() {
    const body = { management_no: st.management_no || "" };
    for (const k of CONTACT_KEYS) body[k] = st[k] || "";
    for (const [k, v] of Object.entries(st.contract)) {
      if (k === "has_pdf") continue;
      body[k] = ["amount", "settle_amount"].includes(k) ? (v === "" || v == null ? null : Number(v)) : (v || "");
    }
    if (kind === "done" && st.inspection) body.inspection = Object.fromEntries(insKeys().map((k) => [k, insNum(st.inspection[k])]));
    return body;
  }

  async function uploadPdf(e) {
    const file = e.target.files[0];
    if (!file) return;
    const msg = box.querySelector(".cd-pdf-msg");
    msg.textContent = "읽는 중…";
    try {
      const fd = new FormData();
      fd.append("file", file);
      const out = await apiUpload(contractId ? `/contracts/${contractId}/pdf` : "/contracts/from-pdf", fd);
      if (!contractId) contractId = out.id;
      const keepAgent = st.agent_id, keepParts = st.participant_ids;
      st = out;
      changed = true;
      st.agent_id = keepAgent ?? st.agent_id;
      st.participant_ids = keepParts;
      delete typed.docno; // 계약번호가 바뀌었을 수 있음 — 기본 문서번호를 새로
      delete typed.greeting;
      draw(readNote(out));
    } catch (err) {
      msg.textContent = err.message;
      msg.classList.add("cd-bad");
    }
  }

  async function make() {
    const btn = box.querySelector(".cd-make");
    const body = {
      contract: contractBody(),
      doc_no: box.querySelector(".cd-docno").value,
      greeting: box.querySelector(".cd-greeting").value,
      send_date: box.querySelector(".cd-send")?.value || "",
      seal: box.querySelector('input[name="cd-seal"]:checked').value === "1",
      agent_id: st.agent_id ?? null,
      participant_ids: st.participant_ids,
    };
    busy = true;
    btn.disabled = true;
    let sec = 0;
    try {
      await ensure();
    } catch (err) {
      busy = false;
      btn.disabled = false;
      alert(err.message);
      return;
    }
    btn.textContent = "만드는 중…";
    const timer = setInterval(() => { btn.textContent = `만드는 중… ${++sec}초`; }, 1000);
    try {
      const out = await apiPost(`/contracts/${contractId}/docs/${kind}`, body);
      changed = true;
      dirty = false;
      st = { ...(await api(`/contracts/${contractId}`)), agent_id: st.agent_id, participant_ids: st.participant_ids };
      const warn = out.warnings.length ? `<div class="mail-msg warn">${out.warnings.map(mailEsc).join("<br>")}</div>` : "";
      const pdfBad = out.pdf_error ? `<div class="mail-msg bad">PDF를 못 만들었습니다 — 엑셀은 받을 수 있습니다.<br>${mailEsc(out.pdf_error)}</div>` : "";
      draw(`<div class="mail-msg ok">✓ ${label}를 만들었습니다 — 아래 버튼으로 받으세요.</div>${pdfBad}${warn}`); // 받기 버튼은 만들기 옆(10/6 사용자)
    } catch (err) {
      btn.disabled = false;
      btn.textContent = `${label} 만들기`;
      const old = box.querySelector(".cd-error");
      if (old) old.remove();
      btn.closest(".mail-foot").insertAdjacentHTML("beforebegin", `<div class="mail-msg bad cd-error">${mailEsc(err.message)}</div>`);
    } finally {
      clearInterval(timer);
      busy = false;
    }
  }
}

// ---------- 현장 연결 창 — 용역 계약 → 현장(아직 계약이 없는 현장, 용역명과 비슷한 순). 현장 하나에 계약 하나 ----------
async function openLinkSite(contractId, onDone) {
  const overlay = document.createElement("div");
  overlay.className = "mail-overlay";
  overlay.style.zIndex = 1200; // 착수계 창 위에
  overlay.innerHTML = '<div class="mail-box cd-pick" role="dialog" aria-modal="true"><div class="mail-wait">불러오는 중…</div></div>';
  document.body.appendChild(overlay);
  const box = overlay.querySelector(".mail-box");
  const close = () => { overlay.remove(); document.removeEventListener("keydown", onKey, true); };
  const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
  document.addEventListener("keydown", onKey, true);
  overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });
  let list = [];
  let cur = null;
  try {
    [list, cur] = await Promise.all([api(`/contracts/${contractId}/site-candidates`), api(`/contracts/${contractId}`)]);
  } catch (err) {
    box.innerHTML = `<div class="mail-msg bad">${mailEsc(err.message)}</div>`;
    return;
  }
  box.innerHTML = `<div class="mail-head"><b>🔗 현장 연결</b><span class="mail-sub">${mailEsc(cur.title || "용역 계약")}</span></div>
    <input type="search" class="mail-input cd-pick-q" placeholder="현장명·주소로 찾기" autocomplete="off" />
    <div class="cd-pick-list"></div>
    <div class="mail-foot">${cur.site_id ? '<button type="button" class="cd-unlink">연결 끊기</button>' : ""}<button type="button" class="cd-pick-close">닫기</button></div>`;
  const listEl = box.querySelector(".cd-pick-list");
  const draw = (q) => {
    const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const shown = list.filter((s) => words.every((w) => `${s.label} ${s.address}`.toLowerCase().includes(w))).slice(0, 40);
    listEl.innerHTML = shown.length ? shown.map((s) => `<button type="button" class="cd-pick-item${s.id === cur.site_id ? " on" : ""}" data-id="${s.id}">
        <b>${mailEsc(s.label)}</b>${!q && s.score >= 0.5 ? '<span class="cd-pick-tag">이름 비슷함</span>' : ""}<span class="mail-note">${mailEsc(s.address)}</span></button>`).join("")
      : '<div class="mail-note">맞는 현장이 없습니다 — 현장을 먼저 등록하세요(이미 다른 계약이 연결된 현장은 안 보임).</div>';
    listEl.querySelectorAll(".cd-pick-item").forEach((b) => b.addEventListener("click", () => link(Number(b.dataset.id))));
  };
  const link = async (siteId) => {
    try {
      await apiPost(`/contracts/${contractId}/link`, { site_id: siteId });
      close();
      if (onDone) onDone();
    } catch (err) {
      listEl.insertAdjacentHTML("afterbegin", `<div class="mail-msg bad">${mailEsc(err.message)}</div>`);
    }
  };
  box.querySelector(".cd-pick-q").addEventListener("input", (e) => draw(e.target.value));
  box.querySelector(".cd-pick-close").addEventListener("click", close);
  box.querySelector(".cd-unlink")?.addEventListener("click", () => { if (confirm("현장 연결을 끊을까요? (서류는 그대로)")) link(null); });
  draw("");
}

// ---------- 현장 화면 [📑 착수계]·[📑 완수계] — 연결된 계약을 열고, 없으면 연결할 계약을 고른다(계약은 서류 자동화에서 먼저 만듦) ----------
async function openSiteContract(siteId, kind) {
  let info;
  try {
    info = await api(`/sites/${siteId}/contract`);
  } catch (err) {
    alert(err.message);
    return;
  }
  if (info.contract_id) return openContractDocs(info.contract_id, kind);
  const overlay = document.createElement("div");
  overlay.className = "mail-overlay";
  overlay.innerHTML = '<div class="mail-box cd-pick" role="dialog" aria-modal="true"></div>';
  document.body.appendChild(overlay);
  const box = overlay.querySelector(".mail-box");
  const close = () => { overlay.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });
  const c = info.candidates;
  box.innerHTML = `<div class="mail-head"><b>📑 ${CD_LABEL[kind]} — 용역 계약 연결</b>
      <span class="mail-sub">이 현장에 연결된 용역 계약이 없습니다. 착수계 때 만든 계약을 고르세요(이름 비슷한 순).</span></div>
    <div class="cd-pick-list">${c.length ? c.map((r) => `<button type="button" class="cd-pick-item" data-id="${r.id}">
        <b>${mailEsc(r.label)}</b>${r.score >= 0.5 ? '<span class="cd-pick-tag">이름 비슷함</span>' : ""}
        <span class="mail-note">${mailEsc([r.client, r.contract_no, r.start_date && `${r.start_date} ~ ${r.end_date}`].filter(Boolean).join(" · "))}</span></button>`).join("")
      : '<div class="mail-note">연결할 계약이 없습니다 — <a href="docs.html">서류 자동화 → 계약 목록</a>에서 계약서 PDF로 먼저 만드세요.</div>'}</div>
    <div class="mail-foot"><a href="docs.html">서류 자동화로</a><button type="button" class="cd-pick-close">닫기</button></div>`;
  box.querySelector(".cd-pick-close").addEventListener("click", close);
  box.querySelectorAll(".cd-pick-item").forEach((b) => b.addEventListener("click", async () => {
    try {
      await apiPost(`/contracts/${b.dataset.id}/link`, { site_id: Number(siteId) });
      close();
      openContractDocs(Number(b.dataset.id), kind);
    } catch (err) {
      alert(err.message);
    }
  }));
}
