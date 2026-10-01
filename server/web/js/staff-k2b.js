// staff.html — 담당요원 K2B 계정(2026-10-01). 요원 줄마다 "K2B: 아이디 ✓ 확인됨" 표시 + [K2B 계정] 창(아이디·비밀번호 저장, [로그인 확인], 지우기).
// K2B는 로그인한 계정 이름이 보고서 "점검자"로 고정 → 그 요원 본인 계정이어야 한다. 고치기는 본인 또는 그룹웨어 관리자만(서버가 can_edit로 알려 줌).
// 비밀번호는 서버가 암호화해 DB에 두고 다시 내보내지 않는다(등록 여부만). 서버: server/api/routers/staff_k2b.py. 요원 줄은 js/staff-gw.js가 그리고 끝에 decorateK2b를 부른다.

const K2B_STATUS = {
  ok: ["ok", "✓ 로그인 확인"],
  mismatch: ["warn", "⚠ 이름 확인 필요"],
  fail: ["bad", "✗ 로그인 실패"],
  "": ["", "확인 전"],
};

function k2bEsc(text) {
  const d = document.createElement("div");
  d.textContent = text ?? "";
  return d.innerHTML;
}

function k2bDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

async function decorateK2b(list) {
  let data;
  try {
    data = await api("/staff-k2b");
  } catch (_) {
    return; // 서버가 아직 예전 버전 — K2B 표시 없이
  }
  const byId = Object.fromEntries(data.staff.map((s) => [s.staff_id, s]));
  list.querySelectorAll(".staff-item[data-staff-id]").forEach((item) => {
    const info = byId[item.dataset.staffId];
    if (info) k2bRender(item, info);
  });
}

function k2bRender(item, info) {
  const chip = item.querySelector(".k2b-chip");
  const btn = item.querySelector(".k2b-btn");
  if (!chip || !btn) return;
  if (info.has_password) {
    const [cls, label] = K2B_STATUS[info.check_status] || K2B_STATUS[""];
    chip.className = `k2b-chip ${cls}`;
    chip.textContent = `K2B ${info.k2b_id} · ${label}${info.checked_at ? ` (${k2bDate(info.checked_at)})` : ""}`;
  } else {
    chip.className = "k2b-chip none";
    chip.textContent = "K2B 계정 미등록";
  }
  chip.title = info.check_message || "";
  btn.hidden = !info.can_edit;
  btn.onclick = () => k2bToggle(item, info);
}

function k2bToggle(item, info) {
  const panel = item.querySelector(".k2b-panel");
  const btn = item.querySelector(".k2b-btn");
  if (!panel.hidden) {
    panel.hidden = true;
    panel.innerHTML = "";
    btn.textContent = "K2B 계정";
    return;
  }
  panel.hidden = false;
  btn.textContent = "닫기";
  panel.innerHTML = `
    <p class="k2b-help">K2B는 로그인한 계정 이름이 보고서 <b>점검자</b>로 들어갑니다 — <b>${k2bEsc(info.name)}</b>님 본인의 K2B 계정을 넣으세요.
      비밀번호는 잠가서 저장하고 다시 보여 주지 않습니다.</p>
    <div class="k2b-fields">
      <label>K2B 아이디<input type="text" class="k2b-id" autocomplete="off" /></label>
      <label>비밀번호<span class="k2b-pw-wrap"><input type="password" class="k2b-pw" autocomplete="new-password" />
        <button type="button" class="secondary k2b-eye" aria-label="비밀번호 보기">보기</button></span></label>
    </div>
    <div class="edit-actions">
      <button type="button" class="k2b-save">저장</button>
      <button type="button" class="secondary k2b-check">로그인 확인</button>
      ${info.has_password ? '<button type="button" class="secondary k2b-del">계정 지우기</button>' : ""}
    </div>
    <div class="k2b-result" hidden></div>`;
  const idEl = panel.querySelector(".k2b-id");
  const pwEl = panel.querySelector(".k2b-pw");
  idEl.value = info.k2b_id || "";
  pwEl.placeholder = info.has_password ? "저장돼 있음 — 바꿀 때만 입력" : "K2B 비밀번호";
  const result = panel.querySelector(".k2b-result");
  const show = (cls, html) => { result.hidden = false; result.className = `k2b-result ${cls}`; result.innerHTML = html; };
  if (info.check_message) showCheck(info);

  function showCheck(i) {
    const [cls] = K2B_STATUS[i.check_status] || K2B_STATUS[""];
    show(cls, `${k2bEsc(i.check_message)} <a href="${BASE}/api/staff-k2b/${i.staff_id}/check-shot?ts=${Date.now()}" target="_blank" rel="noopener">K2B 화면 보기</a>`);
  }

  panel.querySelector(".k2b-eye").addEventListener("click", (ev) => {
    pwEl.type = pwEl.type === "password" ? "text" : "password";
    ev.target.textContent = pwEl.type === "password" ? "보기" : "숨기기";
  });
  panel.querySelector(".k2b-save").addEventListener("click", async (ev) => {
    errorEl.style.display = "none";
    ev.target.disabled = true;
    try {
      const saved = await api(`/staff-k2b/${info.staff_id}`, { method: "PUT", body: JSON.stringify({ k2b_id: idEl.value, password: pwEl.value }) });
      Object.assign(info, saved);
      k2bRender(item, info);
      k2bToggle(item, info); // 저장된 상태로 창을 새로 그림([로그인 확인]·[계정 지우기]가 켜지게)
      k2bToggle(item, info);
      const fresh = item.querySelector(".k2b-result");
      fresh.hidden = false;
      fresh.className = "k2b-result ok";
      fresh.textContent = "저장했습니다. [로그인 확인]을 눌러 K2B에 실제로 들어가지는지 확인하세요.";
      return;
    } catch (err) {
      show("bad", k2bEsc(err.message));
    } finally {
      ev.target.disabled = false;
    }
  });
  // [로그인 확인] — 입력한 아이디·비밀번호가 있으면 먼저 저장하고 바로 확인(2026-10-01 사용자: 저장 전엔 버튼이 잠겨 눌러도 반응이 없었음)
  panel.querySelector(".k2b-check").addEventListener("click", async () => {
    const changed = pwEl.value || idEl.value.trim() !== (info.k2b_id || "");
    if (!info.has_password && !(idEl.value.trim() && pwEl.value)) {
      show("bad", "K2B 아이디와 비밀번호를 입력하세요.");
      return;
    }
    const buttons = panel.querySelectorAll("button");
    buttons.forEach((b) => { b.disabled = true; });
    const started = Date.now();
    const tick = () => show("", `K2B에 로그인해 보는 중… ${Math.round((Date.now() - started) / 1000)}초 (보통 10~40초, 아무것도 제출하지 않습니다)`);
    let timer = null;
    try {
      if (changed) {
        show("", "저장하는 중…");
        Object.assign(info, await api(`/staff-k2b/${info.staff_id}`, { method: "PUT", body: JSON.stringify({ k2b_id: idEl.value, password: pwEl.value }) }));
        pwEl.value = "";
        pwEl.placeholder = "저장돼 있음 — 바꿀 때만 입력";
        k2bRender(item, info);
      }
      tick();
      timer = setInterval(tick, 1000);
      const checked = await apiPost(`/staff-k2b/${info.staff_id}/check`, {});
      Object.assign(info, checked);
      k2bRender(item, info);
      showCheck(info);
    } catch (err) {
      show("bad", k2bEsc(err.message));
    } finally {
      if (timer) clearInterval(timer);
      buttons.forEach((b) => { b.disabled = false; });
    }
  });
  panel.querySelector(".k2b-del")?.addEventListener("click", async () => {
    if (!confirm(`${info.name}님의 K2B 계정을 지울까요? 지우면 이 요원 보고서는 K2B로 보낼 수 없습니다.`)) return;
    try {
      await api(`/staff-k2b/${info.staff_id}`, { method: "DELETE" });
      Object.assign(info, { k2b_id: "", has_password: false, check_status: "", check_message: "", checked_at: null });
      k2bToggle(item, info);
      k2bRender(item, info);
    } catch (err) {
      show("bad", k2bEsc(err.message));
    }
  });
  idEl.focus();
}
