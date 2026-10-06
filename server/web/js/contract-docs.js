// ---------- 현장 [📑 착수계]·[📑 완수계] 창(2026-10-06 — server/api/routers/contract_docs.py) ----------
// 1) 용역계약서 PDF 올리기 → 발주처·용역명·계약번호·금액·날짜가 채워짐(고칠 수 있음, 착수계 때 넣으면 완수계 때 그대로)
// 2) 문서번호·인사말("귀 ○의")·(완수계) 발송일·정산금액·실제준공일 3) (착수계) 현장대리인 1명 + 참여기술자 0~N명
// 4) 도장 넣기/빼기 → [만들기] → 엑셀·PDF 받기. 빠진 서류·유효기간 지난 서류는 막지 않고 경고(사용자 10/6).
// 창 틀은 css/mail.css(mail.js의 mailEsc도 씀), 이 창 규칙은 css/contract-docs.css.

const CD_LABEL = { start: "착수계", done: "완수계" };

async function openContractDocs(siteId, kind, titleText) {
  const overlay = document.createElement("div");
  overlay.className = "mail-overlay";
  overlay.innerHTML = '<div class="mail-box cd-box" role="dialog" aria-modal="true"><div class="mail-wait">불러오는 중…</div></div>';
  document.body.appendChild(overlay);
  const box = overlay.querySelector(".mail-box");
  let busy = false;
  const close = () => {
    if (busy) return;
    overlay.remove();
    document.removeEventListener("keydown", onKey);
  };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });
  const label = CD_LABEL[kind];
  const head = `<div class="mail-head"><b>📑 ${label}</b><span class="mail-sub">${mailEsc(titleText)}</span></div>`;

  let st;
  try {
    st = await api(`/sites/${siteId}/service-contract`);
  } catch (err) {
    box.innerHTML = `${head}<div class="mail-msg bad">${mailEsc(err.message)}</div><div class="mail-foot"><button type="button" class="cd-close">닫기</button></div>`;
    box.querySelector(".cd-close").addEventListener("click", close);
    return;
  }
  const typed = {}; // 사람이 직접 고친 칸(문서번호·인사말) — 계약 값이 바뀌어도 덮어쓰지 않음
  draw();

  function field(key, text, type = "text", wide = false) {
    const v = st.contract[key] ?? "";
    return `<label class="cd-field${wide ? " cd-wide" : ""}"><span>${text}</span><input class="cd-in" data-key="${key}" type="${type}" value="${mailEsc(v)}" /></label>`;
  }

  function draw(result) {
    const c = st.contract;
    const d = st.defaults;
    const made = st.made[kind];
    const peopleHtml = kind === "start" ? peopleBlock() : companyBlock();
    box.innerHTML = `${head}
      <div class="mail-label">용역 계약 <span class="mail-note">— 계약서 PDF를 올리면 채워집니다(착수계·완수계 같이 씀)</span></div>
      <div class="cd-pdf">
        <label class="cd-upload">📎 용역계약서 PDF 올리기<input type="file" accept="application/pdf,.pdf" hidden data-kr-file="skip" /></label>
        <span class="mail-note cd-pdf-msg">${c.has_pdf ? "✓ 올린 계약서가 있습니다 — 다시 올리면 읽은 칸만 바뀝니다" : "아직 안 올림 — 직접 적어도 됩니다"}</span>
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
        <div class="cd-field"><span>담당</span><div class="cd-plain">${mailEsc(d.contact_name)} <a href="settings.html#contract-library" class="mail-note">바꾸기(설정 탭)</a></div></div>
      </div>
      ${peopleHtml}
      <div class="mail-label">대표이사 도장</div>
      <div class="cd-radios">
        <label><input type="radio" name="cd-seal" value="1" checked /> 넣기 <span class="mail-note">(사본 제출용 — "(인)"·원본대조필 칸에)</span></label>
        <label><input type="radio" name="cd-seal" value="0" /> 빼기 <span class="mail-note">(원본 — 인쇄 뒤 직접 날인)</span></label>
      </div>
      ${result || ""}
      ${made.at && !result ? `<div class="cd-made">지난번 만든 것 ${mailEsc(made.at)} — ${dl("xlsx", "엑셀")}${made.pdf ? ` · ${dl("pdf", "PDF 보기", true)} · ${dl("pdf", "PDF 받기")}` : ""}</div>` : ""}
      <div class="mail-foot"><button type="button" class="cd-close">닫기</button><button type="button" class="mail-primary cd-make">${label} 만들기</button></div>`;
    box.querySelector(".cd-close").addEventListener("click", close);
    box.querySelector(".cd-make").addEventListener("click", make);
    box.querySelector(".cd-upload input").addEventListener("change", uploadPdf);
    box.querySelector(".cd-docno").addEventListener("input", (e) => { typed.docno = e.target.value; });
    box.querySelector(".cd-greeting").addEventListener("input", (e) => { typed.greeting = e.target.value; });
    box.querySelector(".cd-send")?.addEventListener("input", (e) => { typed.send = e.target.value; refreshDocNo(); });
    box.querySelectorAll(".cd-in").forEach((el) => el.addEventListener("input", () => { st.contract[el.dataset.key] = el.value; refreshDocNo(); }));
    if (kind === "start") wirePeople();
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
    if (typed.docno !== undefined) return;
    box.querySelector(".cd-docno").value = autoDocNo();
  }

  function dl(ext, text, inline = false) {
    return `<a href="${BASE}/api/sites/${siteId}/contract-docs/${kind}.${ext}${inline ? "?inline=1" : ""}" ${inline ? 'target="_blank" rel="noopener"' : "download"}>${text}</a>`;
  }

  function personNote(p) {
    const bits = [];
    if (p.missing.length) bits.push(`<span class="cd-bad">${mailEsc(p.missing.join("·"))} 없음</span>`);
    if (p.expired.length) bits.push(`<span class="cd-bad">${mailEsc(p.expired.join("·"))} 기간 지남</span>`);
    return [mailEsc([p.qualification.replace(/\n/g, "·"), p.grade].filter(Boolean).join(" · ")), ...bits].filter(Boolean).join(" · ");
  }

  function peopleBlock() {
    if (!st.persons.length) {
      return `<div class="mail-label">기술자</div><div class="mail-msg warn">기술자 명단이 비어 있습니다 — <a href="settings.html#contract-library">설정 탭 → 착수계·완수계 서류</a>에서 먼저 추가하세요.</div>`;
    }
    const agent = st.agent_id ?? st.persons[0].id;
    return `<div class="mail-label">현장대리인(책임기술자) <span class="mail-note">— 1명</span></div>
      <select class="cd-agent">${st.persons.map((p) => `<option value="${p.id}" ${p.id === agent ? "selected" : ""}>${mailEsc(p.name)}</option>`).join("")}</select>
      <div class="mail-label">참여기술자 <span class="mail-note">— 0명부터 여러 명, 고른 순서대로 들어감</span></div>
      <div class="cd-people">${st.persons.map((p) => `<label class="cd-person" data-id="${p.id}">
        <input type="checkbox" value="${p.id}" ${st.participant_ids.includes(p.id) ? "checked" : ""} />
        <span><b>${mailEsc(p.name)}</b><span class="mail-note">${personNote(p)}</span></span></label>`).join("")}</div>
      <div class="mail-note"><a href="settings.html#contract-library">기술자 추가·서류 올리기(설정 탭)</a></div>`;
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
        : doc.status === "expired" ? `<span class="cd-bad">⚠ 기간 지남(${mailEsc(doc.valid_until)})</span>` : '<span class="cd-bad">없음</span>';
      return `<div><span>${mailEsc(doc.label)}</span><div>${s}</div></div>`;
    }).join("");
    return `<div class="mail-label">붙는 회사 서류 <span class="mail-note">— <a href="settings.html#contract-library">설정 탭에서 바꾸기</a></span></div>
      <div class="mail-info cd-docs">${rows}</div>`;
  }

  function contractBody() {
    const body = {};
    for (const [k, v] of Object.entries(st.contract)) {
      if (k === "has_pdf") continue;
      body[k] = ["amount", "settle_amount"].includes(k) ? (v === "" || v == null ? null : Number(v)) : (v || "");
    }
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
      const out = await apiUpload(`/sites/${siteId}/service-contract/pdf`, fd);
      const keepAgent = st.agent_id, keepParts = st.participant_ids;
      st = out;
      st.agent_id = keepAgent ?? st.agent_id;
      st.participant_ids = keepParts;
      delete typed.docno; // 계약번호가 바뀌었을 수 있음 — 기본 문서번호를 새로
      delete typed.greeting;
      draw(out.unread && out.unread.length
        ? `<div class="mail-msg warn">계약서에서 못 읽은 칸이 있습니다 — 직접 채우세요.</div>`
        : `<div class="mail-msg ok">✓ 계약서를 읽었습니다 — 칸을 확인하세요.</div>`);
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
    btn.textContent = "만드는 중…";
    const timer = setInterval(() => { btn.textContent = `만드는 중… ${++sec}초`; }, 1000);
    try {
      const out = await apiPost(`/sites/${siteId}/contract-docs/${kind}`, body);
      st.made = out.made;
      st = { ...(await api(`/sites/${siteId}/service-contract`)), agent_id: st.agent_id, participant_ids: st.participant_ids };
      const warn = out.warnings.length ? `<div class="mail-msg warn">${out.warnings.map(mailEsc).join("<br>")}</div>` : "";
      const pdfBad = out.pdf_error ? `<div class="mail-msg bad">PDF를 못 만들었습니다 — 엑셀은 받을 수 있습니다.<br>${mailEsc(out.pdf_error)}</div>` : "";
      draw(`<div class="mail-msg ok">✓ ${label}를 만들었습니다 — ${dl("xlsx", "엑셀 받기")}${out.pdf_error ? "" : ` · ${dl("pdf", "PDF 보기", true)} · ${dl("pdf", "PDF 받기")}`}</div>${pdfBad}${warn}`);
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
