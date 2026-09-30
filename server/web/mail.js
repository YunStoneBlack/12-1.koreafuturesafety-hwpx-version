// ---------- 고객사에 보고서 PDF 메일 보내기(현장 화면 보고서 목록 "📧 고객사 전송", server/api/routers/report_mail.py) ----------
// 1단계 창: 받는 사람 — 현장책임자·발주처·감리단(현장 정보, 체크 + [고치기]) + 직접 입력 여러 칸(→ [발주처로 저장]·[감리단으로 저장]),
//   모두 한 통으로(서로 보임) → [전송]. 처음엔 이 현장에서 지난번에 보낸 받는 사람들대로 골라 둔다(서버 last_recipients).
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

  const last = info.history[0];
  const maxTo = info.max_recipients || 10;
  const sameAddr = (a, b) => a.toLowerCase() === b.toLowerCase();
  // 체크 항목 — 현장책임자 + 발주처·감리단(현장 정보, 2026-09-30). 각각 [고치기]로 그 자리에서 고치면 현장 정보에도 저장.
  const ROLES = [["manager", "현장책임자"], ["owner", "발주처"], ["supervisor", "감리단"]];
  const roleOf = (key) => ({
    name: info[`${key}_name`] || "",
    emails: key === "manager" ? (info.manager_email ? [info.manager_email] : []) : (info[`${key}_emails`] || []),
  });
  const roleEmails = () => ROLES.flatMap(([k]) => roleOf(k).emails);
  // 처음 채울 값 — 이 현장에서 지난번에 보낸 받는 사람들. 등록된 곳은 지난번에 받았으면 체크(처음 보내면 전부 체크),
  // 나머지 주소는 직접 입력 칸으로.
  const lastTo = info.last_recipients || [];
  const state = { checked: {}, extras: [], editing: null };
  for (const [k] of ROLES) {
    const em = roleOf(k).emails;
    // 서버가 정해 준 값 우선(주소가 바뀐 곳도 지난번에 옛 주소로 받았으면 체크), 없으면 지난번 받는 사람과 비교
    state.checked[k] = info.role_checked ? !!info.role_checked[k]
      : em.length > 0 && (!lastTo.length || em.some((a) => lastTo.some((l) => sameAddr(l, a))));
  }
  state.extras = lastTo.filter((a) => !roleEmails().some((r) => sameAddr(r, a)));
  if (!roleEmails().length && !state.extras.length) state.extras = [""];
  const recipients = () => {
    const out = [];
    const picked = ROLES.flatMap(([k]) => (state.checked[k] ? roleOf(k).emails : []));
    for (const a of [...picked, ...state.extras.map((x) => x.trim())]) {
      if (a && !out.some((o) => sameAddr(o, a))) out.push(a); // 같은 주소 두 번은 하나로
    }
    return out;
  };
  const sendLabel = (n) => `최종 제출${n > 1 ? ` (${n}곳)` : ""}`;

  // 현장 연락처 저장(PATCH /sites/{id}/contacts) → 창 정보에 반영. 현장책임자가 바뀌면 표지가 바뀌어 PDF를 다시 만들어야 보낼 수 있다.
  const saveContacts = async (body) => {
    const out = await apiPatch(`/sites/${info.site_id}/contacts`, body);
    const before = roleEmails();
    info.manager_name = out.manager_name;
    info.manager_email = out.manager_email;
    for (const k of ["owner", "supervisor"]) {
      info[`${k}_name`] = out[`${k}_name`];
      info[`${k}_emails`] = out[`${k}_email`].split(",").map((a) => a.trim()).filter(Boolean);
    }
    // 등록된 주소가 된 것은 직접 입력 칸에서 빼고, 빠진 옛 주소도 직접 입력 칸에 남기지 않는다
    const now = roleEmails();
    state.extras = state.extras.filter((x) => !now.some((r) => sameAddr(r, x.trim())) && !before.some((r) => sameAddr(r, x.trim())));
    return out;
  };

  // ---- 1단계: 받는 사람(체크 항목 + 직접 입력 여러 칸) ----
  const showStep1 = () => {
    box.innerHTML = `
      <div class="mail-head"><b>고객사에 보고서 보내기</b><span class="mail-sub">${mailEsc(titleText)}</span></div>
      ${info.configured ? "" : '<div class="mail-msg bad">⚠ 메일 보내기 설정이 아직 안 됐습니다(회사 네이버 메일 연결 필요). 관리자에게 알려 주세요.</div>'}
      ${last ? `<div class="mail-msg warn">이미 보낸 보고서입니다 — ${mailEsc(last.sent_at)} ${mailEsc(last.to)}${last.by ? ` (${mailEsc(last.by)})` : ""}</div>` : ""}
      <div class="mail-label">받는 사람 <span class="mail-note">모두에게 한 통으로 보냅니다(서로 보임)</span></div>
      ${lastTo.length ? '<div class="mail-note">이 현장에서 지난번에 보낸 받는 사람대로 골라 두었습니다.</div>' : ""}
      <div class="mail-roles"></div>
      <div class="mail-label">직접 입력 <span class="mail-note">그 밖의 주소 — 발주처·감리단이면 [발주처로 저장]·[감리단으로 저장]으로 현장 정보에 넣어 두세요</span></div>
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
    const rolesEl = box.querySelector(".mail-roles");
    const extrasEl = box.querySelector(".mail-extras");
    const addBtn = box.querySelector(".mail-add");
    const errBox = box.querySelector(".mail-err");
    const showErr = (msg) => { errBox.hidden = !msg; errBox.textContent = msg || ""; };

    const renderRoles = () => {
      rolesEl.innerHTML = "";
      for (const [k, label] of ROLES) {
        const r = roleOf(k);
        const row = document.createElement("div");
        row.className = "mail-role";
        if (state.editing === k) {
          row.innerHTML = `<div class="mail-edit">
              <div class="mail-edit-title">${label} ${r.emails.length || r.name ? "고치기" : "등록"}</div>
              <input class="mail-input e-name" placeholder="${k === "manager" ? "이름" : "이름 또는 기관명 (예: ○○시청 건설과)"}" />
              <input class="mail-input e-email" type="${k === "manager" ? "email" : "text"}" placeholder="${k === "manager" ? "메일" : "메일 (여러 개면 쉼표로)"}" />
              ${k === "manager" ? '<div class="mail-note">현장책임자는 보고서 표지에 들어갑니다. 바꾸면 이 현장 보고서 PDF를 다시 만든 뒤 보낼 수 있습니다. 이번만 다른 주소로 보내려면 아래 직접 입력을 쓰세요.</div>' : ""}
              <div class="mail-edit-acts"><button type="button" class="mail-primary e-save">저장</button><button type="button" class="e-cancel">취소</button></div>
            </div>`;
          row.querySelector(".e-name").value = r.name;
          row.querySelector(".e-email").value = r.emails.join(", ");
          row.querySelector(".e-cancel").addEventListener("click", () => { state.editing = null; renderRoles(); });
          row.querySelector(".e-save").addEventListener("click", async (e) => {
            const name = row.querySelector(".e-name").value.trim();
            const emails = row.querySelector(".e-email").value.split(/[,;]/).map((a) => a.trim()).filter(Boolean);
            const bad = emails.filter((a) => !MAIL_RE.test(a));
            if (bad.length) { showErr(`메일 주소를 확인하세요: ${bad.join(", ")}`); return; }
            if (k === "manager" && emails.length > 1) { showErr("현장책임자 메일은 한 개만 넣을 수 있습니다."); return; }
            e.target.disabled = true;
            try {
              const out = await saveContacts({ [`${k}_name`]: name, [`${k}_email`]: emails.join(", ") });
              state.editing = null;
              state.checked[k] = emails.length > 0;
              showErr("");
              if (out.manager_changed) {
                // 표지가 바뀌어 지금 PDF로는 못 보냄 — 창을 다시 열어 안내("PDF를 다시 만든 뒤 보내세요")
                overlay.remove();
                document.removeEventListener("keydown", onKey);
                openMailModal(reportId, titleText, onSent);
                return;
              }
              renderRoles();
              renderExtras();
            } catch (err) {
              e.target.disabled = false;
              showErr(err.message);
            }
          });
          rolesEl.appendChild(row);
          row.querySelector(".e-email").focus();
          continue;
        }
        const has = r.emails.length > 0;
        row.innerHTML = `<label class="mail-opt${has ? "" : " disabled"}">
            <input type="checkbox" ${has ? "" : "disabled"} ${state.checked[k] ? "checked" : ""} />
            <span><b class="mail-role-label">${label}</b>${r.name ? ` ${mailEsc(r.name)}` : ""}
              <span class="mail-addr">${has ? r.emails.map(mailEsc).join(", ") : "(현장 정보에 메일이 없습니다)"}</span></span>
          </label>
          <button type="button" class="mail-fix">${has || r.name ? "고치기" : "등록"}</button>`;
        row.querySelector("input").addEventListener("change", (e) => { state.checked[k] = e.target.checked; renderExtras(); });
        row.querySelector(".mail-fix").addEventListener("click", () => { state.editing = k; showErr(""); renderRoles(); });
        rolesEl.appendChild(row);
      }
    };

    // 직접 입력 칸의 주소를 발주처/감리단으로 저장 — 이미 주소가 있으면 [추가]/[바꾸기]를 고른다
    const saveAsRole = async (i, k, mode) => {
      const addr = state.extras[i].trim();
      const cur = roleOf(k).emails;
      const emails = mode === "replace" ? [addr] : [...cur.filter((a) => !sameAddr(a, addr)), addr];
      try {
        await saveContacts({ [`${k}_email`]: emails.join(", ") });
        state.checked[k] = true;
        showErr("");
        renderRoles();
        renderExtras();
      } catch (err) {
        showErr(err.message);
      }
    };

    const renderExtras = (focusIdx) => {
      extrasEl.innerHTML = "";
      state.extras.forEach((val, i) => {
        const row = document.createElement("div");
        row.className = "mail-extra-wrap";
        row.innerHTML = `<div class="mail-extra"><input type="email" class="mail-input" placeholder="예: name@company.com" autocomplete="email" />
            <button type="button" class="mail-x" title="이 주소 빼기" aria-label="이 주소 빼기">✕</button></div>
          <div class="mail-save-as">
            <button type="button" data-role="owner">발주처로 저장</button><button type="button" data-role="supervisor">감리단으로 저장</button>
          </div>
          <div class="mail-choose" hidden></div>`;
        const input = row.querySelector("input");
        const saveAs = row.querySelector(".mail-save-as");
        const choose = row.querySelector(".mail-choose");
        const syncSaveAs = () => { saveAs.hidden = !MAIL_RE.test(input.value.trim()); };
        input.value = val;
        syncSaveAs();
        input.addEventListener("input", () => { state.extras[i] = input.value; syncSaveAs(); choose.hidden = true; });
        input.addEventListener("keydown", (e) => { if (e.key === "Enter") box.querySelector(".mail-next").click(); });
        row.querySelector(".mail-x").addEventListener("click", () => {
          state.extras.splice(i, 1);
          renderExtras();
        });
        saveAs.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
          const k = b.dataset.role;
          const label = k === "owner" ? "발주처" : "감리단";
          const cur = roleOf(k).emails;
          if (!cur.length) { saveAsRole(i, k, "add"); return; }
          choose.hidden = false;
          choose.innerHTML = `<span>${label}에 이미 <b>${cur.map(mailEsc).join(", ")}</b>가 있습니다.</span>
            <button type="button" data-m="add">추가</button><button type="button" data-m="replace">바꾸기</button><button type="button" data-m="no">취소</button>`;
          choose.querySelectorAll("button").forEach((c) => c.addEventListener("click", () => {
            if (c.dataset.m === "no") { choose.hidden = true; return; }
            saveAsRole(i, k, c.dataset.m);
          }));
        }));
        extrasEl.appendChild(row);
        if (i === focusIdx) input.focus();
      });
      addBtn.hidden = recipients().length + state.extras.filter((x) => !x.trim()).length >= maxTo;
    };
    renderRoles();
    renderExtras();
    addBtn.addEventListener("click", () => {
      state.extras.push("");
      renderExtras(state.extras.length - 1);
    });
    box.querySelector(".mail-cancel").addEventListener("click", close);
    box.querySelector(".mail-next").addEventListener("click", () => {
      if (state.editing) { showErr("고치던 연락처를 먼저 저장하거나 취소하세요."); return; }
      const bad = state.extras.map((x) => x.trim()).filter((a) => a && !MAIL_RE.test(a));
      const to = recipients();
      if (bad.length) { showErr(`메일 주소를 확인하세요: ${bad.join(", ")}`); return; }
      if (!to.length) { showErr("받는 사람을 한 곳 이상 넣으세요."); return; }
      if (to.length > maxTo) { showErr(`받는 사람은 ${maxTo}곳까지 넣을 수 있습니다.`); return; }
      showErr("");
      showStep2(to);
    });
    if (!roleEmails().length && state.extras.length === 1 && !state.extras[0]) extrasEl.querySelector("input").focus();
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
