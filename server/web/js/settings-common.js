// ---------- 설정 칸 공통 — 보고서 자동화 설정(settings.html)과 서류 자동화 설정(docs-settings.html)이 같이 씀(2026-10-06) ----------
// 회사 설정은 하나라(Claude API 키·삭제 비밀번호) 어느 화면에서 바꿔도 양쪽에 같이 반영된다. 칸 HTML의 id는 두 화면이 같다.
// Claude API 키: 계약서 PDF 자동 인식(현장 등록·용역계약서). 삭제 비밀번호: 현장·용역 계약 삭제 때 입력.

// 기술자 이름·직책·기술등급 고치기(10/30 사용자 "기술자 이름 변경이 안 됨") — 산안법·시특법·건축물관리법이 같은 명단(tech_person)이라 어디서 고쳐도 같이.
// head = 카드 머리(이름 옆에 ✏️), p = {id, name, position, grade}, onSaved = 저장 뒤 다시 그리기. 서버 PATCH /contract-docs/persons/{id}.
function techPersonEdit(head, p, onSaved) {
  const e = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "secondary btn-sm tp-edit";
  btn.textContent = "✏️ 고치기";
  btn.title = "이름·직책·기술등급 — 산안법·시특법·건축물관리법 같은 명단이라 어디서 고쳐도 같이 바뀜";
  head.appendChild(btn);
  btn.addEventListener("click", () => {
    if (head.nextElementSibling && head.nextElementSibling.classList.contains("tp-form")) { head.nextElementSibling.remove(); return; }
    const f = document.createElement("div");
    f.className = "tp-form field-grid";
    f.innerHTML = `<div class="sk-f"><label>이름</label><input class="tp-name" value="${e(p.name)}" maxlength="30" /></div>
      <div class="sk-f"><label>직책</label><input class="tp-pos" value="${e(p.position)}" placeholder="예: 과장" maxlength="30" /></div>
      <div class="sk-f"><label>기술등급</label><input class="tp-grade" value="${e(p.grade)}" placeholder="예: 중급기술자" maxlength="30" /></div>
      <div class="tp-act"><button type="button" class="secondary tp-cancel">취소</button><button type="button" class="tp-save">저장</button>
        <span class="mail-note">산안법·시특법·건축물관리법 같은 명단 — 이미 만든 서류·보고서는 그대로(다시 만들면 새 이름)</span></div>`;
    head.after(f);
    f.querySelector(".tp-name").focus();
    f.querySelector(".tp-cancel").addEventListener("click", () => f.remove());
    f.querySelector(".tp-save").addEventListener("click", async (ev) => {
      const sb = ev.currentTarget; // await 뒤엔 currentTarget이 비므로 먼저 잡아 둠
      const name = f.querySelector(".tp-name").value.trim();
      if (!name) { alert("이름을 넣으세요."); return; }
      sb.disabled = true;
      try {
        await apiPatch(`/contract-docs/persons/${p.id}`, { name, position: f.querySelector(".tp-pos").value.trim(), grade: f.querySelector(".tp-grade").value.trim() });
        onSaved();
      } catch (x) { alert(x.message); sb.disabled = false; }
    });
  });
}

function initApiKeyPanel(errorEl) {
  async function loadStatus() {
    const statusEl = document.getElementById("current-status");
    try {
      const status = await api("/settings/api-key");
      statusEl.textContent = status.has_key
        ? `현재 등록된 키: ${status.masked} (새 키를 입력하면 교체됩니다)`
        : "아직 등록된 키가 없습니다.";
    } catch (err) {
      showError(errorEl, err);
    }
  }

  document.getElementById("key-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    errorEl.style.display = "none";
    const input = document.getElementById("api-key");
    try {
      await apiPost("/settings/api-key", { api_key: input.value });
      input.value = "";
      await loadStatus();
    } catch (err) {
      showError(errorEl, err);
    }
  });
  loadStatus();
}

// 삭제 비밀번호 — 이미 정해져 있으면 바꿀 때 지금 비밀번호가 필요
function initDeletePasswordPanel(errorEl) {
  async function loadDeletePasswordStatus() {
    try {
      const st = await api("/settings/delete-password");
      const statusEl = document.getElementById("delpw-status");
      statusEl.className = st.is_set ? "status ok" : "status bad";
      statusEl.textContent = st.is_set
        ? "✓ 설정되어 있습니다. 바꾸려면 지금 비밀번호와 새 비밀번호를 입력하세요."
        : "아직 없습니다. 정해야 현장·용역 계약을 삭제할 수 있습니다.";
      document.getElementById("delpw-current-wrap").hidden = !st.is_set;
    } catch (err) {
      showError(errorEl, err);
    }
  }

  document.getElementById("delpw-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    errorEl.style.display = "none";
    const msg = document.getElementById("delpw-msg");
    const next = document.getElementById("delpw-new").value;
    msg.className = "status";
    msg.textContent = "";
    if (next !== document.getElementById("delpw-new2").value) {
      msg.className = "status bad";
      msg.textContent = "새 비밀번호와 확인이 서로 다릅니다.";
      return;
    }
    try {
      await apiPost("/settings/delete-password", {
        current_password: document.getElementById("delpw-current").value,
        new_password: next,
      });
      for (const id of ["delpw-current", "delpw-new", "delpw-new2"]) document.getElementById(id).value = "";
      msg.className = "status ok";
      msg.textContent = "저장되었습니다.";
      await loadDeletePasswordStatus();
    } catch (err) {
      msg.className = "status bad";
      msg.textContent = err.message;
    }
  });
  loadDeletePasswordStatus();
}
