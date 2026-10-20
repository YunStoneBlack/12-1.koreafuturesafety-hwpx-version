// 시특법 현장 화면 [🏢 전경사진] 탭(sitok-field.html, 2026-10-11) — 장수 제한 없이 찍고 제목(🎤 음성·입력·지난 제목·🏷 실명판 AI)·순서.
// 보고서 10쪽 위치도 아래 = 첫 장, 11쪽 = 6장씩. 서버 server/api/routers/sitok_overview.py.

(function () {
  const rid = Number(new URLSearchParams(location.search).get("report")) || null;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const url = `/sitok/reports/${rid}/overview`;
  const msgEl = document.getElementById("ov-msg");
  const say = (text, ok) => { msgEl.hidden = !text; msgEl.className = `mail-msg ${ok ? "ok" : "bad"}`; msgEl.textContent = text || ""; };
  let data = { photos: [], titles: [] };
  let ts = Date.now();

  function draw() {
    document.getElementById("ov-count").textContent = data.photos.length ? `(${data.photos.length})` : "";
    document.getElementById("ov-titles").innerHTML = data.titles.map((t) => `<option value="${esc(t)}">`).join("");
    const box = document.getElementById("ov-list");
    if (!data.photos.length) {
      box.innerHTML = '<div class="ov-empty">아직 찍은 전경사진이 없습니다 — 보고서에는 지난 회차 사진이 그대로 들어갑니다.</div>';
      return;
    }
    box.innerHTML = data.photos.map((p, i) => `<div class="ov-card${p.ai ? " ai" : ""}" data-id="${p.id}">
      <div class="ov-no">${i + 1}${i === 0 ? " · 10쪽에도" : ""}<span>전경 ${Math.floor(i / 6) + 1}번째 쪽</span></div>
      <img src="${BASE}/api${url}/${p.id}/photo?t=${ts}" alt="" loading="lazy" />
      <div class="ov-title"><input list="ov-titles" value="${esc(p.title)}" placeholder="제목(예: ${data.wall ? "시점측 전경" : "옥상 전경사진"}) — 🎤 음성 가능" />
        <label class="ov-plate" title="실명판을 찍으면 AI가 실 이름을 읽어 제목으로"${data.wall ? " hidden" : ""}>🏷<input type="file" accept="image/*" capture="environment" hidden data-kr-file="1" /></label></div>
      ${p.ai ? '<div class="ov-ai">🤖 AI 추천 제목 — 맞으면 그대로, 아니면 고치세요</div>' : ""}
      <div class="ov-acts"><button type="button" data-m="-1"${i ? "" : " disabled"}>◀ 앞으로</button><button type="button" data-m="1"${i < data.photos.length - 1 ? "" : " disabled"}>뒤로 ▶</button>
        <button type="button" class="ov-del">지우기</button></div></div>`).join("");
    box.querySelectorAll(".ov-card").forEach((el) => {
      const id = el.dataset.id;
      const input = el.querySelector(".ov-title input");
      input.addEventListener("change", () => patch(id, { title: input.value }));
      el.querySelectorAll("[data-m]").forEach((b) => b.addEventListener("click", () => patch(id, { move: Number(b.dataset.m) })));
      el.querySelector(".ov-del").addEventListener("click", async () => {
        if (!confirm("이 전경사진을 지울까요?")) return;
        try { data = await api(`${url}/${id}`, { method: "DELETE" }); draw(); } catch (e) { say(e.message); }
      });
      const plate = el.querySelector(".ov-plate input");
      plate.addEventListener("change", async () => {
        if (!plate.files[0]) return;
        el.classList.add("busy");
        say("실명판 읽는 중…", true);
        try {
          const fd = new FormData();
          fd.append("file", plate.files[0]);
          const r = await apiUpload(`${url}/nameplate`, fd);
          await patch(id, { title: r.title });
          say(`실명판: ${r.title}`, true);
        } catch (e) { say(e.message); el.classList.remove("busy"); }
      });
      el.querySelector("img").addEventListener("click", (e) => window.open(e.target.src, "_blank"));
    });
  }

  async function patch(id, body) {
    try { data = await apiPatch(`${url}/${id}`, body); draw(); } catch (e) { say(e.message); }
  }

  async function upload(list) {
    const fl = [...list];
    for (let i = 0; i < fl.length; i++) {
      say(`올리는 중… ${i + 1} / ${fl.length}`, true);
      const fd = new FormData();
      fd.append("file", fl[i]);
      try { data = await apiUpload(url, fd); } catch (e) { say(e.message); return; }
      draw();
    }
    say("");
    const last = document.querySelector(".ov-card:last-child .ov-title input");
    if (last && fl.length === 1) last.focus();
  }

  for (const id of ["ov-cam", "ov-files"]) {
    const inp = document.getElementById(id);
    inp.addEventListener("change", () => { if (inp.files.length) upload(inp.files).then(() => { inp.value = ""; }); });
  }
  enableFileDrop(document.getElementById("ov-list"), document.getElementById("ov-files"));
  document.getElementById("ov-suggest").addEventListener("click", async (e) => {
    const n = data.photos.filter((p) => !p.title).length;
    if (!n) { say("제목 없는 사진이 없습니다.", true); return; }
    e.target.disabled = true;
    say(`AI가 사진 ${n}장을 보고 제목을 붙이는 중…(장당 5~10초)`, true);
    try { data = await apiPost(`${url}/suggest`); ts = Date.now(); draw(); say(`${data.done}장에 제목을 붙였습니다 — 확인하세요.`, true); } catch (err) { say(err.message); }
    e.target.disabled = false;
  });

  // 탭 — 결함 조사 / 전경사진 / 공중이용 / 기타시설(10/12) — 탭 data-tab="x" ↔ 칸 id="sf-x"
  const tabs = [...document.querySelectorAll(".sf-tab")].map((b) => b.dataset.tab);
  const show = (tab) => {
    if (!tabs.includes(tab)) tab = "defects";
    document.querySelectorAll(".sf-tab").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
    tabs.forEach((t) => { const pane = document.getElementById(`sf-${t}`); if (pane) pane.hidden = t !== tab; });
    try { sessionStorage.setItem(`sf-tab-${rid}`, tab); } catch (_) { /* */ }
  };
  document.querySelectorAll(".sf-tab").forEach((b) => b.addEventListener("click", () => show(b.dataset.tab)));
  let first = "defects";
  try { first = sessionStorage.getItem(`sf-tab-${rid}`) || "defects"; } catch (_) { /* */ }
  show(first);
  api(url).then((d) => { data = d; draw(); }).catch((e) => say(e.message));
})();
