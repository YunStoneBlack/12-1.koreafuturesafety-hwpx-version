// 결함조사만(defect-survey.html, 2026-10-21 사용자) — 보고서 틀이 아직 없는 시설물도 현장 결함조사를.
// [＋ 새 결함조사] 이름·구분·지상/지하 층수·옥상층·추가 탭(외부·정면·배면…) → 탭 미리보기 → [만들고 조사 시작] = 현장 조사 화면(결함 조사 탭만).
// 목록 카드: [🔍 조사 열기] [📊 결함현황표(엑셀)] [📕 사진첩(PDF)] [🗑]. 서버 server/api/routers/sitok_survey_only.py.

(function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const errorEl = document.getElementById("error");
  const $ = (id) => document.getElementById(id);
  const PRESETS = ["외부", "정면", "배면", "좌측면", "우측면", "측면", "내부"];
  const WALL_PARTS = ["지반 및 기초부", "전면부", "상부", "배수시설", "기타"]; // 서버 kinds.WALL_PARTS
  const BRIDGE_PARTS = ["상부구조", "하부구조", "받침", "케이블", "2차부재", "기타부재"]; // 서버 kinds.BRIDGE_PARTS(10/29)
  const picked = new Set();
  const custom = [];

  const say = (text, ok) => { const m = $("ds-msg"); m.hidden = !text; m.className = `mail-msg${ok ? "" : " bad"}`; m.textContent = text || ""; };
  const isWall = () => ["옹벽", "교량"].includes($("ds-kind").value); // 층 대신 부위 탭(교량 10/29)
  const num = (el) => Math.max(0, Math.min(Number(el.max) || 99, Math.floor(Number(el.value) || 0)));

  function units() { // 서버 facility_floors와 같은 순서 — 옥상 → 지상 위층부터 → 지하 → 추가 탭
    const extra = [...PRESETS.filter((p) => picked.has(p)), ...custom.filter((c) => picked.has(c))];
    if (isWall()) return [...($("ds-kind").value === "교량" ? BRIDGE_PARTS : WALL_PARTS), ...extra];
    const a = num($("ds-above")), b = num($("ds-below"));
    const floors = [...Array(a)].map((_, i) => `지상${a - i}층`).concat([...Array(b)].map((_, i) => `지하${i + 1}층`));
    return [...(floors.length && $("ds-roof").checked ? ["옥상층"] : []), ...floors, ...extra];
  }

  function drawForm() {
    document.querySelectorAll(".ds-floor-f, .ds-roof-f").forEach((el) => { el.hidden = isWall(); });
    $("ds-chips").innerHTML = [...PRESETS, ...custom].map((p) => `<button type="button" class="ds-chip${picked.has(p) ? " on" : ""}" data-p="${esc(p)}">${esc(p)}</button>`).join("")
      + '<input class="ds-chip-in" id="ds-chip-in" placeholder="＋ 직접 쓰기" maxlength="30" />';
    $("ds-chips").querySelectorAll(".ds-chip").forEach((b) => b.addEventListener("click", () => {
      if (picked.has(b.dataset.p)) picked.delete(b.dataset.p); else picked.add(b.dataset.p);
      drawForm();
    }));
    $("ds-chip-in").addEventListener("keydown", (e) => {
      if (e.key !== "Enter" || e.isComposing) return;
      e.preventDefault();
      const v = e.target.value.trim().replace(/\s+/g, " ");
      if (!v) return;
      if (!PRESETS.includes(v) && !custom.includes(v)) custom.push(v);
      picked.add(v);
      drawForm();
      $("ds-chip-in").focus();
    });
    const u = units();
    $("ds-preview").innerHTML = u.length ? u.map((x) => `<span class="ds-tab">${esc(x)}</span>`).join("")
      : '<span class="sk-help">지상·지하 층수를 넣거나 추가 탭을 고르세요</span>';
  }

  ["ds-above", "ds-below", "ds-roof", "ds-kind"].forEach((id) => ["input", "change"].forEach((ev) => $(id).addEventListener(ev, drawForm)));

  $("ds-create").addEventListener("click", async () => {
    const name = $("ds-name").value.trim();
    if (!name) { say("시설물 이름을 넣으세요."); $("ds-name").focus(); return; }
    if (!units().length) { say("지상·지하 층수를 넣거나 추가 탭을 하나 이상 고르세요."); return; }
    const body = { name, kind: $("ds-kind").value, floors_above: isWall() ? 0 : num($("ds-above")), floors_below: isWall() ? 0 : num($("ds-below")),
      roof: $("ds-roof").checked, units: [...PRESETS, ...custom].filter((p) => picked.has(p)) };
    $("ds-create").disabled = true;
    try {
      const r = await apiPost("/sitok/survey-only", body);
      location.href = `sitok-field.html?report=${r.report_id}&so=1`;
    } catch (e) { say(e.message); $("ds-create").disabled = false; }
  });

  async function download(path, fallback, btn) { // 내려받기 — 결함이 없으면 서버 400 글을 그대로
    const old = btn.textContent;
    btn.disabled = true;
    btn.textContent = "만드는 중…";
    try {
      const res = await fetch(apiUrl(path), { credentials: "include" });
      if (!res.ok) { const b = await res.json().catch(() => ({})); throw new Error(b.detail || `내려받지 못했습니다 (${res.status})`); }
      const cd = res.headers.get("Content-Disposition") || "";
      const m = cd.match(/filename\*=UTF-8''([^;]+)/i) || cd.match(/filename="?([^";]+)"?/i);
      const name = m ? decodeURIComponent(m[1]) : fallback;
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch (e) { alert(e.message); }
    btn.disabled = false;
    btn.textContent = old;
  }

  function askPassword(name) {
    return new Promise((resolve) => {
      const ov = document.createElement("div");
      ov.className = "mail-overlay";
      ov.innerHTML = `<div class="mail-box" role="dialog" aria-modal="true">
        <div class="mail-head"><b>🗑 결함조사 지우기</b><span class="mail-sub">"${esc(name)}"의 결함·사진이 모두 지워집니다.</span></div>
        <input type="password" class="mail-input" placeholder="삭제 비밀번호" autocomplete="off" />
        <div class="mail-note">보고서 자동화 설정에서 정한 삭제 비밀번호(현장·시설물 삭제와 같음)</div>
        <div class="mail-foot"><button type="button" class="ds-cancel">취소</button><button type="button" class="mail-primary ds-ok" style="background:var(--crit);border-color:var(--crit);">지우기</button></div></div>`;
      document.body.appendChild(ov);
      const input = ov.querySelector("input");
      const done = (v) => { ov.remove(); resolve(v); };
      ov.querySelector(".ds-cancel").addEventListener("click", () => done(null));
      ov.querySelector(".ds-ok").addEventListener("click", () => (input.value ? done(input.value) : input.focus()));
      input.addEventListener("keydown", (e) => { if (e.key === "Enter" && input.value) done(input.value); if (e.key === "Escape") done(null); });
      input.focus();
    });
  }

  function card(s) {
    const el = document.createElement("div");
    el.className = "ds-card";
    const tabs = s.units.length > 8 ? `${s.units.slice(0, 8).join(" · ")} 외 ${s.units.length - 8}` : s.units.join(" · ");
    el.innerHTML = `<div class="ds-card-main">
        <div class="ds-card-title"><b>${esc(s.name)}</b><span class="ds-kind">${esc(s.kind || "기타")}</span>${s.done ? '<span class="ds-done">✓ 조사 완료</span>' : ""}</div>
        <div class="ds-card-sub">${esc(tabs) || "탭 없음"}</div>
        <div class="ds-card-meta">결함 ${s.defects}개 · 사진 ${s.photos}장${s.defects ? ` · 확인 ${s.checked}/${s.defects}` : ""}${s.created_at ? ` · ${esc(s.created_at)}` : ""}${s.created_by ? ` ${esc(s.created_by)}` : ""}</div>
      </div>
      <div class="ds-card-btns">
        <a class="secondary-link ds-open" href="sitok-field.html?report=${s.report_id}&so=1">🔍 조사 열기</a>
        <button type="button" class="secondary ds-xlsx" title="층·탭별 결함현황표(번호·부재·결함유형·크기·원인·진행유무·비고·사진번호) — 엑셀">📊 결함현황표</button>
        <button type="button" class="secondary ds-pdf" title="층·탭마다 결함 현황표 쪽 + 결함사진표(한 쪽 6장) — PDF">📕 사진첩</button>
        <button type="button" class="secondary ds-del" title="지우기(삭제 비밀번호)">🗑</button>
      </div>`;
    el.querySelector(".ds-xlsx").addEventListener("click", (e) => download(`/sitok/survey-only/${s.id}/table`, `${s.name}_결함현황표.xlsx`, e.currentTarget));
    el.querySelector(".ds-pdf").addEventListener("click", (e) => download(`/sitok/survey-only/${s.id}/album`, `${s.name}_결함사진첩.pdf`, e.currentTarget));
    el.querySelector(".ds-del").addEventListener("click", async () => {
      const pw = await askPassword(s.name);
      if (!pw) return;
      try {
        await api(`/sitok/survey-only/${s.id}`, { method: "DELETE", body: JSON.stringify({ password: pw }) });
        load();
      } catch (e) { alert(e.message); }
    });
    return el;
  }

  async function load() {
    try {
      const d = await api("/sitok/survey-only");
      if (!$("ds-kind").options.length) {
        $("ds-kind").innerHTML = d.kinds.map((k) => `<option>${esc(k)}</option>`).join("");
        drawForm();
      }
      $("ds-count").textContent = d.surveys.length ? `${d.surveys.length}건` : "";
      const box = $("ds-list");
      box.innerHTML = d.surveys.length ? "" : '<div class="ds-empty">아직 결함조사가 없습니다 — 위에서 이름과 층수를 넣고 [만들고 조사 시작]을 누르세요.</div>';
      d.surveys.forEach((s) => box.appendChild(card(s)));
    } catch (e) { showError(errorEl, e); }
  }

  load();
})();
