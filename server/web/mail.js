// ---------- 고객사에 보고서 PDF 메일 보내기(현장 화면 보고서 목록 "📧 고객사 전송", server/api/routers/report_mail.py) ----------
// 1단계 창: 받는 사람 — 현장책임자(체크) + 직접 입력 여러 칸(감리 현장은 발주처·감리단 등), 모두 한 통으로(서로 보임) → [전송]
//   처음엔 이 현장에서 지난번에 보낸 받는 사람들을 채워 둔다(서버 last_recipients).
// 2단계 창: "최종 확인하셨나요? 보낸 메일은 되돌릴 수 없습니다" → [최종 제출] → 회사 네이버 메일로 PDF 첨부 발송(참조: 회사 메일)
// PDF가 없거나 "수정 전 버전"·만드는 중이면 보내지 않고 "PDF를 다시 만든 뒤 보내세요"만 알린다(서버도 한 번 더 막음).

function mailEsc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function mailSizeText(bytes) {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)}MB` : `${Math.max(1, Math.round(bytes / 1024))}KB`;
}

const MAIL_RE = /^[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}$/;

// onSent: 보낸 뒤 호출(목록 새로고침용)
async function openMailModal(reportId, titleText, onSent) {
  const overlay = document.createElement("div");
  overlay.className = "mail-overlay";
  overlay.innerHTML = '<div class="mail-box" role="dialog" aria-modal="true"><div class="mail-wait">불러오는 중…</div></div>';
  document.body.appendChild(overlay);
  const box = overlay.querySelector(".mail-box");
  let sending = false;
  const close = () => { if (!sending) { overlay.remove(); document.removeEventListener("keydown", onKey); } };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });

  let info;
  try {
    info = await api(`/reports/${reportId}/mail`);
  } catch (err) {
    box.innerHTML = `<div class="mail-head"><b>고객사에 보고서 보내기</b></div><div class="mail-msg bad">${mailEsc(err.message)}</div>
      <div class="mail-foot"><button type="button" class="mail-cancel">닫기</button></div>`;
    box.querySelector(".mail-cancel").addEventListener("click", close);
    return;
  }

  // 보낼 수 없는 상태(PDF 없음·수정 전 버전·만드는 중) — 안내만
  if (info.problem) {
    box.innerHTML = `<div class="mail-head"><b>고객사에 보고서 보내기</b><span class="mail-sub">${mailEsc(titleText)}</span></div>
      <div class="mail-msg warn">⚠ ${mailEsc(info.problem)}</div>
      <div class="mail-foot"><button type="button" class="mail-cancel">닫기</button>
        <a class="mail-primary" href="report.html?id=${reportId}">보고서 화면으로</a></div>`;
    box.querySelector(".mail-cancel").addEventListener("click", close);
    return;
  }

  const hasManager = !!info.manager_email;
  const last = info.history[0];
  const maxTo = info.max_recipients || 10;
  const sameAddr = (a, b) => a.toLowerCase() === b.toLowerCase();
  // 처음 채울 값 — 이 현장에서 지난번에 보낸 받는 사람들(감리 현장은 매 회차 발주처·감리단이 같음). 없으면 현장책임자만.
  const lastTo = info.last_recipients || [];
  const state = {
    manager: hasManager && (!lastTo.length || lastTo.some((a) => sameAddr(a, info.manager_email))),
    extras: lastTo.filter((a) => !(hasManager && sameAddr(a, info.manager_email))),
  };
  if (!hasManager && !state.extras.length) state.extras = [""];
  const recipients = () => {
    const out = [];
    for (const a of [...(state.manager ? [info.manager_email] : []), ...state.extras.map((x) => x.trim())]) {
      if (a && !out.some((o) => sameAddr(o, a))) out.push(a); // 같은 주소 두 번은 하나로
    }
    return out;
  };
  const sendLabel = (n) => `최종 제출${n > 1 ? ` (${n}곳)` : ""}`;

  // ---- 1단계: 받는 사람(현장책임자 체크 + 직접 입력 여러 칸) ----
  const showStep1 = () => {
    box.innerHTML = `
      <div class="mail-head"><b>고객사에 보고서 보내기</b><span class="mail-sub">${mailEsc(titleText)}</span></div>
      ${info.configured ? "" : '<div class="mail-msg bad">⚠ 메일 보내기 설정이 아직 안 됐습니다(회사 네이버 메일 연결 필요). 관리자에게 알려 주세요.</div>'}
      ${last ? `<div class="mail-msg warn">이미 보낸 보고서입니다 — ${mailEsc(last.sent_at)} ${mailEsc(last.to)}${last.by ? ` (${mailEsc(last.by)})` : ""}</div>` : ""}
      <div class="mail-label">받는 사람 <span class="mail-note">모두에게 한 통으로 보냅니다(서로 보임)</span></div>
      ${lastTo.length ? '<div class="mail-note">이 현장에서 지난번에 보낸 주소를 채워 두었습니다.</div>' : ""}
      <label class="mail-opt${hasManager ? "" : " disabled"}">
        <input type="checkbox" class="mail-manager" ${hasManager ? "" : "disabled"} ${state.manager ? "checked" : ""} />
        <span>현장책임자${info.manager_name ? ` ${mailEsc(info.manager_name)}` : ""}
          <span class="mail-addr">${hasManager ? mailEsc(info.manager_email) : "(현장 정보에 메일이 없습니다)"}</span></span>
      </label>
      <div class="mail-label">직접 입력 <span class="mail-note">발주처·감리단 등</span></div>
      <div class="mail-extras"></div>
      <button type="button" class="mail-add">+ 받는 사람 추가</button>
      <div class="mail-info">
        <div><span>참조</span><div>${mailEsc(info.cc || "없음")}</div></div>
        <div><span>제목</span><div>${mailEsc(info.subject)}</div></div>
        <div><span>첨부</span><div>📄 ${mailEsc(info.filename)} (${mailSizeText(info.size_bytes)})</div></div>
      </div>
      <div class="mail-msg bad mail-err" hidden></div>
      <div class="mail-foot"><button type="button" class="mail-cancel">취소</button>
        <button type="button" class="mail-primary mail-next" ${info.configured ? "" : "disabled"}>전송</button></div>`;
    const extrasEl = box.querySelector(".mail-extras");
    const addBtn = box.querySelector(".mail-add");
    const errBox = box.querySelector(".mail-err");
    const renderExtras = (focusIdx) => {
      extrasEl.innerHTML = "";
      state.extras.forEach((val, i) => {
        const row = document.createElement("div");
        row.className = "mail-extra";
        row.innerHTML = `<input type="email" class="mail-input" placeholder="예: name@company.com" autocomplete="email" />
          <button type="button" class="mail-x" title="이 주소 빼기" aria-label="이 주소 빼기">✕</button>`;
        const input = row.querySelector("input");
        input.value = val;
        input.addEventListener("input", () => { state.extras[i] = input.value; });
        input.addEventListener("keydown", (e) => { if (e.key === "Enter") box.querySelector(".mail-next").click(); });
        row.querySelector(".mail-x").addEventListener("click", () => {
          state.extras.splice(i, 1);
          renderExtras();
        });
        extrasEl.appendChild(row);
        if (i === focusIdx) input.focus();
      });
      addBtn.hidden = state.extras.length + (state.manager ? 1 : 0) >= maxTo;
    };
    renderExtras();
    box.querySelector(".mail-manager").addEventListener("change", (e) => { state.manager = e.target.checked; renderExtras(); });
    addBtn.addEventListener("click", () => {
      state.extras.push("");
      renderExtras(state.extras.length - 1);
    });
    box.querySelector(".mail-cancel").addEventListener("click", close);
    box.querySelector(".mail-next").addEventListener("click", () => {
      const bad = state.extras.map((x) => x.trim()).filter((a) => a && !MAIL_RE.test(a));
      const to = recipients();
      errBox.hidden = false;
      if (bad.length) { errBox.textContent = `메일 주소를 확인하세요: ${bad.join(", ")}`; return; }
      if (!to.length) { errBox.textContent = "받는 사람을 한 곳 이상 넣으세요."; return; }
      if (to.length > maxTo) { errBox.textContent = `받는 사람은 ${maxTo}곳까지 넣을 수 있습니다.`; return; }
      errBox.hidden = true;
      showStep2(to);
    });
    if (!hasManager && state.extras.length === 1 && !state.extras[0]) extrasEl.querySelector("input").focus();
  };

  // ---- 2단계: 최종 확인 ----
  const showStep2 = (to) => {
    const cc = info.cc && !to.some((a) => sameAddr(a, info.cc)) ? info.cc : "";
    box.innerHTML = `
      <div class="mail-head"><b>⚠ 최종 확인하셨나요?</b></div>
      <div class="mail-msg warn">보고서 내용을 최종 확인하셨나요? 보낸 메일은 되돌릴 수 없습니다.</div>
      <div class="mail-info">
        <div><span>보고서</span><div>${mailEsc(titleText)}</div></div>
        <div><span>받는 사람</span><div>${to.map((a) => `<b>${mailEsc(a)}</b>`).join("<br>")}</div></div>
        <div><span>참조</span><div>${mailEsc(cc || "없음")}</div></div>
        <div><span>첨부</span><div>📄 ${mailEsc(info.filename)}</div></div>
      </div>
      <div class="mail-msg bad" hidden></div>
      <div class="mail-foot"><button type="button" class="mail-cancel">다시 확인할게요</button>
        <button type="button" class="mail-primary mail-send">${sendLabel(to.length)}</button></div>`;
    const errBox = box.querySelector(".mail-msg.bad");
    box.querySelector(".mail-cancel").addEventListener("click", showStep1);
    const sendBtn = box.querySelector(".mail-send");
    sendBtn.addEventListener("click", async () => {
      sending = true;
      sendBtn.disabled = true;
      box.querySelector(".mail-cancel").disabled = true;
      sendBtn.textContent = "보내는 중…";
      errBox.hidden = true;
      try {
        const out = await apiPost(`/reports/${reportId}/mail`, { to });
        sending = false;
        // 일부 주소만 메일 서버가 거부하면 나머지에겐 이미 간 것 — 거부된 주소만 따로 알린다
        const refused = out.refused || [];
        const sentTo = to.filter((a) => !refused.some((r) => sameAddr(r, a)));
        box.innerHTML = `<div class="mail-head"><b>✓ 보냈습니다</b></div>
          <div class="mail-msg ok">${sentTo.map(mailEsc).join(", ")}${cc ? ` (참조 ${mailEsc(cc)})` : ""}로 보고서 PDF를 보냈습니다.</div>
          ${refused.length ? `<div class="mail-msg bad">⚠ 메일 서버가 받지 않은 주소: ${refused.map(mailEsc).join(", ")} — 주소를 확인해 이 주소만 다시 보내세요.</div>` : ""}
          <div class="mail-foot"><button type="button" class="mail-primary mail-cancel">닫기</button></div>`;
        box.querySelector(".mail-cancel").addEventListener("click", close);
        if (onSent) onSent();
      } catch (err) {
        sending = false;
        sendBtn.disabled = false;
        box.querySelector(".mail-cancel").disabled = false;
        sendBtn.textContent = sendLabel(to.length);
        errBox.hidden = false;
        errBox.textContent = err.message || "보내지 못했습니다. 다시 시도하세요.";
      }
    });
  };

  showStep1();
}
