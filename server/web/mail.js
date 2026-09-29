// ---------- 고객사에 보고서 PDF 메일 보내기(현장 화면 보고서 목록 "📧 고객사 전송", server/api/routers/report_mail.py) ----------
// 1단계 창: 받는 사람(현장책임자 메일이 기본, 또는 직접 입력) → [전송]
// 2단계 창: "최종 확인하셨나요? 보낸 메일은 되돌릴 수 없습니다" → [최종 제출] → 회사 네이버 메일로 PDF 첨부 발송(참조: 회사 메일)
// PDF가 없거나 "수정 전 버전"·만드는 중이면 보내지 않고 "PDF를 다시 만든 뒤 보내세요"만 알린다(서버도 한 번 더 막음).

function mailEsc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function mailSizeText(bytes) {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)}MB` : `${Math.max(1, Math.round(bytes / 1024))}KB`;
}

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
  // ---- 1단계: 받는 사람 ----
  const showStep1 = (typed) => {
    box.innerHTML = `
      <div class="mail-head"><b>고객사에 보고서 보내기</b><span class="mail-sub">${mailEsc(titleText)}</span></div>
      ${info.configured ? "" : '<div class="mail-msg bad">⚠ 메일 보내기 설정이 아직 안 됐습니다(회사 네이버 메일 연결 필요). 관리자에게 알려 주세요.</div>'}
      ${last ? `<div class="mail-msg warn">이미 보낸 보고서입니다 — ${mailEsc(last.sent_at)} ${mailEsc(last.to)}${last.by ? ` (${mailEsc(last.by)})` : ""}</div>` : ""}
      <div class="mail-label">받는 사람</div>
      <label class="mail-opt${hasManager ? "" : " disabled"}">
        <input type="radio" name="mail-to" value="manager" ${hasManager ? "checked" : "disabled"} />
        <span>현장책임자${info.manager_name ? ` ${mailEsc(info.manager_name)}` : ""}
          <span class="mail-addr">${hasManager ? mailEsc(info.manager_email) : "(현장 정보에 메일이 없습니다)"}</span></span>
      </label>
      <label class="mail-opt">
        <input type="radio" name="mail-to" value="custom" ${hasManager ? "" : "checked"} />
        <span>직접 입력</span>
      </label>
      <input type="email" class="mail-input" placeholder="예: name@company.com" autocomplete="email" />
      <div class="mail-info">
        <div><span>참조</span><div>${mailEsc(info.cc || "없음")}</div></div>
        <div><span>제목</span><div>${mailEsc(info.subject)}</div></div>
        <div><span>첨부</span><div>📄 ${mailEsc(info.filename)} (${mailSizeText(info.size_bytes)})</div></div>
      </div>
      <div class="mail-msg bad" hidden></div>
      <div class="mail-foot"><button type="button" class="mail-cancel">취소</button>
        <button type="button" class="mail-primary mail-next" ${info.configured ? "" : "disabled"}>전송</button></div>`;
    const input = box.querySelector(".mail-input");
    const radios = box.querySelectorAll('input[name="mail-to"]');
    const errBox = box.querySelector(".mail-msg.bad[hidden]");
    if (typed !== undefined) {
      input.value = typed;
      box.querySelector('input[value="custom"]').checked = true;
    }
    input.addEventListener("focus", () => { box.querySelector('input[value="custom"]').checked = true; });
    radios.forEach((r) => r.addEventListener("change", () => { if (r.value === "custom" && r.checked) input.focus(); }));
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") box.querySelector(".mail-next").click(); });
    box.querySelector(".mail-cancel").addEventListener("click", close);
    box.querySelector(".mail-next").addEventListener("click", () => {
      const useManager = box.querySelector('input[value="manager"]').checked;
      const to = useManager ? info.manager_email : input.value.trim();
      if (!/^[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}$/.test(to)) {
        errBox.hidden = false;
        errBox.textContent = "받는 사람 메일 주소를 확인하세요.";
        input.focus();
        return;
      }
      showStep2(to, useManager ? undefined : input.value);
    });
    if (!hasManager) input.focus();
  };

  // ---- 2단계: 최종 확인 ----
  const showStep2 = (to, typed) => {
    const cc = info.cc && info.cc.toLowerCase() !== to.toLowerCase() ? info.cc : "";
    box.innerHTML = `
      <div class="mail-head"><b>⚠ 최종 확인하셨나요?</b></div>
      <div class="mail-msg warn">보고서 내용을 최종 확인하셨나요? 보낸 메일은 되돌릴 수 없습니다.</div>
      <div class="mail-info">
        <div><span>보고서</span><div>${mailEsc(titleText)}</div></div>
        <div><span>받는 사람</span><b>${mailEsc(to)}</b></div>
        <div><span>참조</span><div>${mailEsc(cc || "없음")}</div></div>
        <div><span>첨부</span><div>📄 ${mailEsc(info.filename)}</div></div>
      </div>
      <div class="mail-msg bad" hidden></div>
      <div class="mail-foot"><button type="button" class="mail-cancel">다시 확인할게요</button>
        <button type="button" class="mail-primary mail-send">최종 제출</button></div>`;
    const errBox = box.querySelector(".mail-msg.bad");
    box.querySelector(".mail-cancel").addEventListener("click", () => showStep1(typed));
    const sendBtn = box.querySelector(".mail-send");
    sendBtn.addEventListener("click", async () => {
      sending = true;
      sendBtn.disabled = true;
      box.querySelector(".mail-cancel").disabled = true;
      sendBtn.textContent = "보내는 중…";
      errBox.hidden = true;
      try {
        await apiPost(`/reports/${reportId}/mail`, { to });
        sending = false;
        box.innerHTML = `<div class="mail-head"><b>✓ 보냈습니다</b></div>
          <div class="mail-msg ok">${mailEsc(to)}${cc ? ` (참조 ${mailEsc(cc)})` : ""}로 보고서 PDF를 보냈습니다.</div>
          <div class="mail-foot"><button type="button" class="mail-primary mail-cancel">닫기</button></div>`;
        box.querySelector(".mail-cancel").addEventListener("click", close);
        if (onSent) onSent();
      } catch (err) {
        sending = false;
        sendBtn.disabled = false;
        box.querySelector(".mail-cancel").disabled = false;
        sendBtn.textContent = "최종 제출";
        errBox.hidden = false;
        errBox.textContent = err.message || "보내지 못했습니다. 다시 시도하세요.";
      }
    });
  };

  showStep1();
}
