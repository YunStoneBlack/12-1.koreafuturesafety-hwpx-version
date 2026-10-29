// 건축물관리점검 목록(2026-10-29 사용자) — 새 건(건축물대장 PDF → 개요 읽기) + 건 카드(진행 N/50·부적합·사진). 서버 server/api/routers/blcm.py.
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const errorEl = $("error");
  const say = (t, ok) => { const m = $("bj-msg"); m.hidden = !t; m.className = `mail-msg${ok ? "" : " bad"}`; m.textContent = t || ""; };

  const fileIn = $("bj-r");
  enableFileDrop($("bj-r-drop"), fileIn);
  fileIn.addEventListener("change", () => {
    const f = fileIn.files[0];
    $("bj-r-msg").textContent = f ? `📄 ${f.name}` : "정부24 발급본(일반건축물대장 갑·을) — 끌어다 놓거나 눌러 고르기";
    $("bj-r-drop").classList.toggle("on", !!f);
  });

  $("bj-create").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    const name = $("bj-name").value.trim(), f = fileIn.files[0];
    if (!name && !f) { say("건축물 이름을 넣거나 건축물대장 PDF를 올려 주세요."); return; }
    const fd = new FormData();
    fd.append("name", name);
    if (f) fd.append("ledger", f);
    btn.disabled = true;
    btn.textContent = f ? "대장 읽는 중…" : "만드는 중…";
    try {
      const out = await apiUpload("/blcm/jobs", fd);
      if (out.read && !out.read.text_ok) {
        alert("건축물대장에 글자가 없어(스캔본) 개요를 못 읽었습니다 — 건 화면의 [🤖 AI로 읽기]로 읽을 수 있습니다(약 30원).");
      }
      location.href = `blcm-job.html?id=${out.id}`;
    } catch (err) {
      say(err.message);
      btn.disabled = false;
      btn.textContent = "만들기";
    }
  });

  function card(j) {
    const el = document.createElement("div");
    el.className = "ds-card";
    const pct = j.total ? Math.round((100 * j.done) / j.total) : 0;
    el.innerHTML = `<div class="ds-card-main">
        <div class="ds-card-title"><b>${esc(j.name)}</b>${j.use ? `<span class="ds-kind">${esc(j.use)}</span>` : ""}${j.bad ? `<span class="bj-bad">부적합·미흡 ${j.bad}</span>` : ""}</div>
        <div class="ds-card-sub">${esc(j.address || "주소 없음")}${j.approval_date ? ` · 사용승인 ${esc(j.approval_date)}` : ""}</div>
        <div class="ds-card-meta"><span class="bj-bar"><i style="width:${pct}%"></i></span> 항목 ${j.done}/${j.total} · 사진 ${j.photos}장 · ${esc(j.updated)}</div>
      </div>
      <div class="ds-card-btns"><a class="secondary-link" href="blcm-job.html?id=${j.id}">📂 열기</a></div>`;
    return el;
  }

  async function load() {
    try {
      const d = await api("/blcm/jobs");
      const box = $("bj-list");
      box.innerHTML = "";
      $("bj-count").textContent = d.jobs.length ? `${d.jobs.length}건` : "";
      if (!d.jobs.length) { box.innerHTML = '<div class="empty-note">아직 건이 없습니다 — 위에서 건축물대장 PDF로 만드세요.</div>'; return; }
      d.jobs.forEach((j) => box.appendChild(card(j)));
    } catch (err) { showError(errorEl, err); }
  }
  load();

  // 생애이력시스템 계정(10/29 4단계) — 회사 하나, 관리자만 바꿈
  async function loadAcc() {
    try {
      const a = await api("/blcm/account");
      $("bj-acc-st").textContent = a.has ? `등록됨 — ${a.user_id}` : "없음";
      $("bj-acc-id").value = a.user_id || "";
    } catch (err) { $("bj-acc-st").textContent = err.message; }
  }
  $("bj-acc-save").addEventListener("click", async (e) => {
    const btn = e.currentTarget, m = $("bj-acc-msg");
    btn.disabled = true;
    try {
      await api("/blcm/account", { method: "PUT", body: JSON.stringify({ user_id: $("bj-acc-id").value.trim(), password: $("bj-acc-pw").value }) });
      $("bj-acc-pw").value = "";
      m.hidden = false; m.className = "mail-msg ok"; m.textContent = "✓ 저장했습니다.";
      loadAcc();
    } catch (err) { m.hidden = false; m.className = "mail-msg bad"; m.textContent = err.message; }
    btn.disabled = false;
  });
  loadAcc();
})();
