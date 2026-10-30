// ---------- 서류 자동화 · 시특법 관급 — 착수계·완수계 창(sitok-docs.html, 2026-10-12 2단계, 완수계는 10/20까지 "완료계") ----------
// API server/api/routers/sitok_docs.py(/sitok/docs/contracts/{id}/gov…), 엑셀 양식 채우기는 server/sitok/gov_docs.py. 산안법 착수계 창(js/contract-docs.js)과 같은 흐름:
// 문서번호(KFSC연도_계약번호_월일 — 10/20 형 견본)·인사말·담당·도장 → (착수계) 현장대리인 1명 + 참여기술자(시특법 보고서 설정과 같은 명단) → 붙임(산출내역서 / 완수내역서)
// → (완수계) 결과보고서 표지(연결한 시설물 보고서 첫 쪽, 없으면 올림) + 회사 서류 6장(서류 자동화 설정 — 산안법과 같은 것, 10/20 형 견본) → [만들기] = 엑셀 + 합본 PDF.
// 10/30 사용자: 착수계 붙임 산출내역서 칸에 [📊 낙찰가 적용 내역서 만들기] — 설계(낙찰가 적용 전) 내역서 엑셀 → 계약금액에 맞게 기술자 노임단가 조정(server/sitok/est_adjust.py)
// → 맞춘 PDF가 이 칸에 들어감, 미리보기·맞춘 엑셀·설계 엑셀 받기, PDF에 넣을 시트 고르기.

async function openSitokGov(contractId, kind, onDone) {
  const P = `/sitok/docs/contracts/${contractId}/gov`;
  const LABEL = { start: "착수계", done: "완수계" }[kind];
  const esc = mailEsc;
  const overlay = document.createElement("div");
  overlay.className = "mail-overlay";
  overlay.style.zIndex = 1150; // 계약 창 위에
  overlay.innerHTML = '<div class="mail-box cd-box sd-box sd-gov" role="dialog" aria-modal="true"><div class="mail-wait">불러오는 중…</div></div>';
  document.body.appendChild(overlay);
  const box = overlay.querySelector(".mail-box");
  let st, busy = false, result = null;
  const typed = {};
  const close = () => {
    if (busy) return;
    overlay.remove();
    document.removeEventListener("keydown", onKey, true);
    if (onDone) onDone();
  };
  const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
  document.addEventListener("keydown", onKey, true);
  overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });
  try {
    st = await api(P);
  } catch (err) {
    box.innerHTML = `<div class="mail-msg bad">${esc(err.message)}</div><div class="mail-foot"><button type="button" class="sd-g-close">닫기</button></div>`;
    box.querySelector(".sd-g-close").addEventListener("click", close);
    return;
  }
  if (st.agent_id == null && st.persons.length) st.agent_id = st.persons[0].id;
  const A = `/sitok/docs/contracts/${contractId}/est-adjust`;
  let adj = null; // 낙찰가 적용 내역서(10/30) {adjust: meta|null, amount, attachments}
  if (kind === "start") { try { adj = await api(A); } catch (_) { adj = null; } }
  const won = (n) => (n || n === 0) ? `${Number(n).toLocaleString("ko-KR")}원` : "";
  const fileUrl = (ext, inline) => `${BASE}/api${P}/${kind}.${ext}?v=${encodeURIComponent(st.gov[kind].at)}${inline ? "&inline=true" : ""}`;

  function personNote(p) {
    const bits = [esc([(p.qualification || "").replace(/\n/g, "·"), p.grade].filter(Boolean).join(" · "))];
    if (p.missing.length) bits.push(`<span class="cd-bad">${esc(p.missing.join("·"))} 없음</span>`);
    if (p.expired.length) bits.push(`<span class="cd-bad">${esc(p.expired.join("·"))} 기간 지남</span>`);
    return bits.filter(Boolean).join(" · ");
  }

  function peopleBlock() {
    if (!st.persons.length) return '<div class="mail-msg warn">기술자 명단이 비어 있습니다 — <a href="docs-settings.html#contract-library">서류 자동화 설정</a>에서 추가하세요.</div>';
    return `<div class="mail-label">현장대리인(책임기술자) <span class="mail-note">— 1명</span></div>
      <select class="sd-agent">${st.persons.map((p) => `<option value="${p.id}"${p.id === st.agent_id ? " selected" : ""}>${esc(p.name)}</option>`).join("")}</select>
      <div class="mail-label">참여기술자 <span class="mail-note">— 0명부터 여러 명, 고른 순서대로(사람마다 서류 4장 + 보안각서)</span></div>
      <div class="cd-people">${st.persons.map((p) => `<label class="cd-person${p.id === st.agent_id ? " is-agent" : ""}" data-id="${p.id}">
        <input type="checkbox" value="${p.id}"${st.participant_ids.includes(p.id) && p.id !== st.agent_id ? " checked" : ""}${p.id === st.agent_id ? " disabled" : ""} />
        <span><b>${esc(p.name)}</b><span class="mail-note">${personNote(p)}</span></span></label>`).join("")}</div>
      <div class="mail-note">자격증·경력증명서 = <a href="docs-settings.html#contract-library">서류 자동화 설정</a>, 정밀안전진단 교육 수료증·서명·도장 = <a href="settings.html?law=sitok">보고서 자동화 설정(시특법)</a></div>`;
  }

  function attachBlock() {
    return `<div class="mail-label">붙임 서류 <span class="mail-note">— 받아 온 견적서 파일(PDF·그림·엑셀·한글)을 올리면 합본 PDF에 갑지 붙임 순서대로</span></div>
      <div class="cd-attach">${st.attachments[kind].map((sl) => `<div class="cd-slot" data-slot="${sl.slot}">
        <div class="cd-slot-head"><b>${esc(sl.label)}</b>
          <label class="cd-add">+ 파일 올리기<input type="file" multiple hidden data-kr-file="skip"
            accept=".pdf,.jpg,.jpeg,.png,.gif,.bmp,.tif,.tiff,.webp,.xlsx,.xls,.xlsm,.docx,.doc,.hwp,.hwpx" /></label></div>
        ${kind === "start" && sl.slot === "calc" ? adjBlock() : ""}
        ${sl.files.length ? sl.files.map((f) => `<div class="cd-file">
          <a href="${BASE}/api${P}/${kind}/attach/${sl.slot}/${encodeURIComponent(f.name)}" target="_blank" rel="noopener">📄 ${esc(f.title)}</a>
          <span class="mail-note">${f.pages}장</span>
          <button type="button" class="cd-x" data-name="${esc(f.name)}" title="빼기">✕</button></div>`).join("")
          : '<div class="mail-note cd-none">아직 없음 — 없으면 빼고 합칩니다</div>'}
        <div class="drop-box drop-sm cd-slot-drop"><b class="drop-pc">⬇ 여기에 끌어다 놓기</b><b class="drop-touch">눌러서 파일 고르기</b></div>
        <div class="mail-note cd-slot-msg"></div></div>`).join("")}</div>`;
  }

  const UNIT = { "-4": "만원", "-3": "천원", "-2": "백원", "-1": "십원", "0": "원" };
  const digits = (f) => ((/[;,]\s*(-?\d+)\)$/.exec(f || "") || [])[1]);
  function adjBlock() { // 📊 낙찰가 적용 내역서(10/30 사용자 "낙찰가 적용 전 내역서를 첨부하면 계약금액에 맞게 노임단가를 조정해 착수계에 — 내려받기·미리보기")
    const m = adj && adj.adjust;
    const amt = adj ? adj.amount : st.amount;
    const v = encodeURIComponent((m && (m.pdf_at || m.at)) || "");
    const f = (w, inline) => `${BASE}/api${A}/file/${w}?v=${v}${inline ? "&inline=true" : ""}`;
    const rnd = m && m.rounding.length ? ` · 끝자리 절사 ${[...new Set(m.rounding.map((r) => `${UNIT[digits(r.before)] || ""}→${UNIT[digits(r.after)] || ""}`))].join(", ")}` : "";
    return `<div class="sd-adj">
      <div class="sd-adj-h"><b>📊 낙찰가 적용 내역서 만들기</b>
        <span class="mail-note">설계(낙찰가 적용 전) 내역서 엑셀을 올리면 계약금액 ${amt ? won(amt) : "(계약금액 없음)"}에 맞게 기술자 노임단가를 조정해 이 칸에 넣습니다 — 30초쯤</span>
        <label class="cd-add">${m ? "다시 맞추기" : "설계 내역서 엑셀 올리기"}<input type="file" hidden data-kr-file="skip" class="sd-adj-in" accept=".xlsx,.xls,.xlsm" /></label></div>
      ${m ? `<div class="sd-adj-r">✓ <b>${esc(m.filename)}</b> — 설계 ${won(m.before)} → <b>${won(m.after)}</b>${m.after === m.target ? " (계약금액과 같음)" : ""}
          <br>${m.rates.map((r) => `${esc(r.label.replace(/노임단가$/, ""))} ${won(r.before)} → ${Number(r.after).toLocaleString("ko-KR", { maximumFractionDigits: 2 })}원(${esc(r.pct)}%)`).join(" · ")}${rnd}${m.texts.length ? " · 표지 한글 금액" : ""}
          <span class="mail-note">· ${esc(m.at)} ${esc(m.by || "")}</span></div>
        <div class="sd-adj-b"><a href="${f("pdf", true)}" target="_blank" rel="noopener">👁 미리보기(PDF ${m.pages || "?"}쪽)</a><a href="${f("xlsx")}">⬇ 맞춘 엑셀</a><a href="${f("before")}">⬇ 설계 엑셀</a>
          <button type="button" class="sd-adj-sheets">PDF 시트 고르기 ▾</button><button type="button" class="cd-x sd-adj-del" title="맞춘 내역서 빼기">✕</button></div>
        <div class="sd-adj-pick" hidden><div class="sd-adj-list">${m.sheets.map((x) => `<label><input type="checkbox" value="${esc(x.name)}"${m.chosen.includes(x.name) ? " checked" : ""} /> ${esc(x.name)}${x.hidden ? ' <span class="mail-note">(숨긴 시트)</span>' : ""}</label>`).join("")}</div>
          <button type="button" class="sd-adj-go">고른 시트로 PDF 다시 만들기</button></div>` : ""}
      <div class="mail-note sd-adj-msg"></div></div>`;
  }

  function coverBlock() {
    return `<div class="mail-label">결과보고서 <span class="mail-note">— 표지 한 장(견본처럼)</span></div>
      <div class="sd-cover">${st.cover ? `<span class="cd-ok">✓ ${esc(st.cover)}</span>` : '<span class="cd-bad">표지 없음 — 현장 연결한 시설물의 보고서를 만들거나 표지를 올리세요</span>'}
        <label class="cd-add">${st.cover === "올린 표지" ? "표지 바꾸기" : "표지 올리기"}<input type="file" class="sd-cover-in" hidden data-kr-file="skip" accept=".pdf,.jpg,.jpeg,.png,.hwp,.hwpx" /></label></div>`;
  }

  function companyBlock() { // 완수계 끝 6장(10/20 — 산안법 완수계와 같은 회사 서류)
    const rows = (st.company_docs || []).map((doc) => {
      const s = doc.status === "ok" ? `<span class="cd-ok">✓${doc.valid_until ? ` ${esc(doc.valid_until)}까지` : ""}</span>`
        : doc.status === "expired" ? `<span class="cd-bad">⚠ 기간 지남(${esc(doc.valid_until)})</span>`
        : doc.status === "nodate" ? '<span class="cd-bad">⚠ 발급일 모름</span>' : '<span class="cd-bad">없음</span>';
      return `<div><span>${esc(doc.label)}</span><div>${s}</div></div>`;
    }).join("");
    return `<div class="mail-label">붙는 회사 서류 <span class="mail-note">— <a href="docs-settings.html#contract-library">서류 자동화 설정에서 바꾸기</a>(산안법 완수계와 같은 서류)</span></div>
      <div class="mail-info cd-docs">${rows}</div>`;
  }

  function draw() {
    const c = st, d = st.defaults;
    const made = st.gov[kind];
    const lack = [!c.client && "발주처", !c.title && "용역명", !c.contract_no && "계약번호", !c.start_date && "착수일", !c.end_date && "완수일"].filter(Boolean);
    box.innerHTML = `
      <div class="mail-head"><b>📑 ${LABEL}</b><span class="mail-sub">${esc(c.title || "(용역명 없음)")}</span>
        <span class="mail-sub">${esc([c.client, c.contract_no, c.start_date && `${c.start_date} ~ ${c.end_date || ""}`, won(c.amount)].filter(Boolean).join(" · "))}</span></div>
      ${lack.length ? `<div class="mail-msg warn">계약 칸이 비었습니다: ${lack.join("·")} — 계약 창에서 나라장터 계약서를 올리거나 직접 채우세요.</div>` : ""}
      <div class="cd-grid">
        <label class="cd-field"><span>문서번호 <em>KFSC연도_계약번호_${kind === "start" ? "착수일" : "완수일"}(월일)</em></span><input class="sd-docno" value="${esc(typed.docno ?? d[`doc_no_${kind}`])}" /></label>
        ${kind === "done" ? `<label class="cd-field"><span>실제 준공일 <em>비우면 준공일${c.end_date ? ` ${esc(c.end_date)}` : ""}</em></span><input type="date" class="sd-actual" value="${esc(typed.actual ?? c.actual_end_date ?? "")}" /></label>
        <label class="cd-field"><span>발송일 <em>비우면 실제 준공일(없으면 준공일) — 문서번호 끝 월일</em></span><input type="date" class="sd-send" value="${esc(sendDay())}" /></label>` : ""}
        <label class="cd-field"><span>인사말</span><span class="cd-greet">1. 귀 <input class="cd-greeting" value="${esc(typed.greeting ?? d.greeting)}" /> 의 무궁한 발전을…</span></label>
        <label class="cd-field"><span>담당 <em>갑지 아래</em></span><input class="sd-contact" value="${esc(typed.contact ?? d.contact_name)}" /></label>
        <label class="cd-field sd-seal"><span>도장</span><span class="cd-greet"><input type="checkbox" class="sd-seal-in"${(typed.seal ?? true) ? " checked" : ""} /> 대표이사 도장${kind === "start" ? "·보안각서 기술자 서명" : ""} 넣기(빼면 인쇄 뒤 직접)</span></label>
      </div>
      ${kind === "start" ? peopleBlock() : coverBlock() + companyBlock()}
      ${attachBlock()}
      ${result ? `<div class="mail-msg ${result.pdf_error ? "bad" : result.warnings.length ? "warn" : "ok"}">
          ${result.pdf_error ? `PDF를 만들지 못했습니다(엑셀은 받을 수 있음): ${esc(result.pdf_error)}` : `✓ ${LABEL}를 만들었습니다.`}
          ${result.warnings.length ? `<ul class="sd-warn">${result.warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}</div>` : ""}
      ${made.at && !result ? `<div class="cd-made">지난번 만든 것 ${esc(made.at)} — 아래 버튼으로 받기</div>` : ""}
      <div class="mail-msg sd-g-msg" hidden></div>
      <div class="mail-foot cd-foot">
        <button type="button" class="sd-g-close">닫기</button>
        ${made.xlsx ? `<a href="${fileUrl("xlsx")}">엑셀 받기</a>` : ""}
        ${made.pdf ? `<a href="${fileUrl("pdf", true)}" target="_blank" rel="noopener">PDF 보기</a><a href="${fileUrl("pdf")}">PDF 받기</a>` : ""}
        <button type="button" class="mail-primary sd-g-make">📑 ${LABEL} ${made.at ? "다시 " : ""}만들기</button>
      </div>`;
    wire();
  }

  function remember() {
    const q = (sel) => box.querySelector(sel);
    typed.docno = q(".sd-docno").value;
    typed.greeting = q(".cd-greeting").value;
    typed.contact = q(".sd-contact").value;
    typed.seal = q(".sd-seal-in").checked;
    if (q(".sd-actual")) typed.actual = q(".sd-actual").value;
  }
  // 완수계 날짜(10/22, 산안법처럼): 실제 준공일(비면 준공일) → 발송일 기본, 문서번호 끝 월일·연도 = 발송일. 손으로 고친 발송일·문서번호는 그대로
  const doneDay = () => (typed.actual ?? st.actual_end_date ?? "") || st.end_date || "";
  const sendDay = () => typed.send ?? doneDay();
  function refreshDone() {
    const send = box.querySelector(".sd-send"), docno = box.querySelector(".sd-docno");
    if (send && typed.send === undefined) send.value = doneDay();
    if (docno && !typed.docnoTouched) { docno.value = docNoFor(sendDay()); typed.docno = docno.value; }
  }
  function docNoFor(day) {
    const base = (st.defaults.doc_no_done || "").replace(/^KFSC\d{2}_/, "").replace(/_\d{4}$/, "");
    if (!base || !day) return st.defaults.doc_no_done || "";
    return `KFSC${day.slice(2, 4)}_${base}_${day.slice(5, 7)}${day.slice(8, 10)}`;
  }
  const say = (text, tone) => {
    const m = box.querySelector(".sd-g-msg");
    m.innerHTML = text;
    m.className = `mail-msg sd-g-msg ${tone || ""}`;
    m.hidden = !text;
  };

  function wire() {
    box.querySelector(".sd-g-close").addEventListener("click", close);
    const sel = box.querySelector(".sd-agent");
    const actual = box.querySelector(".sd-actual");
    if (actual) {
      actual.addEventListener("change", () => { typed.actual = actual.value; refreshDone(); });
      box.querySelector(".sd-send").addEventListener("change", (e) => { typed.send = e.target.value || undefined; refreshDone(); });
      box.querySelector(".sd-docno").addEventListener("input", () => { typed.docnoTouched = true; });
    }
    if (sel) {
      sel.addEventListener("change", () => {
        remember();
        st.agent_id = Number(sel.value);
        st.participant_ids = st.participant_ids.filter((x) => x !== st.agent_id);
        draw();
      });
      box.querySelectorAll(".cd-person input").forEach((chk) => chk.addEventListener("change", () => {
        const id = Number(chk.value);
        st.participant_ids = chk.checked ? [...st.participant_ids.filter((x) => x !== id), id] : st.participant_ids.filter((x) => x !== id);
      }));
    }
    const cover = box.querySelector(".sd-cover-in");
    if (cover) {
      enableFileDrop(cover.closest(".sd-cover"), cover);
      cover.addEventListener("change", async () => {
        const file = cover.files[0];
        cover.value = "";
        if (!file) return;
        remember();
        busy = true;
        say("올리는 중…");
        try {
          const fd = new FormData();
          fd.append("file", file);
          await apiUpload(`/sitok/docs/contracts/${contractId}/upload/report_cover`, fd);
          st = { ...st, ...(await api(P)), agent_id: st.agent_id, participant_ids: st.participant_ids };
          draw();
        } catch (err) {
          say(esc(err.message), "bad");
        } finally {
          busy = false;
        }
      });
    }
    const adjBox = box.querySelector(".sd-adj");
    if (adjBox) { // 낙찰가 적용 내역서(10/30)
      const amsg = adjBox.querySelector(".sd-adj-msg");
      const adjIn = adjBox.querySelector(".sd-adj-in");
      const after = (out) => { adj = out; st.attachments.start = out.attachments; draw(); };
      enableFileDrop(adjBox, adjIn); // 엑셀을 이 칸에 끌어 놓으면 맞추기(붙임 칸 끌어 놓기보다 먼저)
      adjIn.addEventListener("change", async () => {
        const file = adjIn.files[0];
        adjIn.value = "";
        if (!file) return;
        remember();
        busy = true;
        amsg.className = "mail-note sd-adj-msg";
        amsg.textContent = `맞추는 중 — ${file.name} (LibreOffice로 계산·PDF, 30초쯤)`;
        try {
          const fd = new FormData();
          fd.append("file", file);
          after(await apiUpload(A, fd));
        } catch (err) {
          amsg.textContent = err.message;
          amsg.classList.add("cd-bad");
        } finally { busy = false; }
      });
      adjBox.querySelector(".sd-adj-sheets")?.addEventListener("click", () => { const p = adjBox.querySelector(".sd-adj-pick"); p.hidden = !p.hidden; });
      adjBox.querySelector(".sd-adj-go")?.addEventListener("click", async (e) => {
        const sheets = [...adjBox.querySelectorAll(".sd-adj-pick input:checked")].map((x) => x.value);
        if (!sheets.length) { amsg.textContent = "시트를 하나 이상 고르세요."; return; }
        remember();
        busy = true;
        e.currentTarget.disabled = true;
        amsg.textContent = "PDF 다시 만드는 중…(20초쯤)";
        try { after(await api(`${A}/sheets`, { method: "PUT", body: JSON.stringify({ sheets }) })); } catch (err) { amsg.textContent = err.message; amsg.classList.add("cd-bad"); e.currentTarget.disabled = false; } finally { busy = false; }
      });
      adjBox.querySelector(".sd-adj-del")?.addEventListener("click", async () => {
        if (!confirm("맞춘 내역서를 뺄까요? (붙임 산출내역서 칸에서도 빠집니다)")) return;
        remember();
        try { after(await api(A, { method: "DELETE" })); } catch (err) { amsg.textContent = err.message; }
      });
    }
    box.querySelectorAll(".cd-slot").forEach((el) => {
      const slot = el.dataset.slot;
      const msg = el.querySelector(".cd-slot-msg");
      const input = el.querySelector(".cd-add input");
      enableFileDrop(el, input);
      el.querySelector(".cd-slot-drop").addEventListener("click", () => input.click());
      input.addEventListener("change", async () => {
        const picked = [...input.files];
        input.value = "";
        if (!picked.length) return;
        remember();
        busy = true;
        try {
          for (const [i, file] of picked.entries()) {
            msg.textContent = `올리는 중 ${picked.length > 1 ? `${i + 1}/${picked.length} ` : ""}— ${file.name}${/\.hwpx?$/i.test(file.name) ? " (한글은 PDF로 바꾸느라 1분쯤)" : ""}`;
            const fd = new FormData();
            fd.append("file", file);
            st.attachments[kind] = await apiUpload(`${P}/${kind}/attach/${slot}`, fd);
          }
          draw();
        } catch (err) {
          draw();
          const m = box.querySelector(`.cd-slot[data-slot="${slot}"] .cd-slot-msg`);
          m.textContent = err.message;
          m.classList.add("cd-bad");
        } finally {
          busy = false;
        }
      });
      el.querySelectorAll(".cd-file .cd-x").forEach((btn) => btn.addEventListener("click", async () => { // 붙임 파일 줄만(낙찰가 적용 ✕는 따로)
        if (!confirm(`${btn.dataset.name.replace(/^\d+_/, "")} 파일을 뺄까요?`)) return;
        remember();
        try {
          st.attachments[kind] = await api(`${P}/${kind}/attach/${slot}/${encodeURIComponent(btn.dataset.name)}`, { method: "DELETE" });
          draw();
        } catch (err) {
          msg.textContent = err.message;
        }
      }));
    });
    box.querySelector(".sd-g-make").addEventListener("click", async (e) => {
      remember();
      const btn = e.currentTarget;
      busy = true;
      btn.disabled = true;
      btn.textContent = "만드는 중… (엑셀 → PDF 30초쯤)";
      try {
        result = await apiPost(`${P}/${kind}`, { doc_no: typed.docno, greeting: typed.greeting, contact: typed.contact, seal: typed.seal,
          agent_id: st.agent_id, participant_ids: st.participant_ids,
          ...(kind === "done" ? { contract: { actual_end_date: typed.actual || "" }, send_date: typed.send || "" } : {}) });
        if (kind === "done") st.actual_end_date = typed.actual || null;
        st.gov = result.gov;
        typed.docno = result.doc_no;
        busy = false;
        draw();
      } catch (err) {
        busy = false;
        btn.disabled = false;
        btn.textContent = `📑 ${LABEL} 만들기`;
        say(esc(err.message), "bad");
      }
    });
  }

  draw();
}
