// 시특법 현장 화면 [👍 상태양호]·[🏫 내진보강] 탭(sitok-field.html, 2026-10-19 민재형 요구사항 B3·B5).
// 상태양호 = 1.3 항목마다 양호한 모습 사진(4장까지) → 결함 사진 다음 빈 칸에, AI 초안이 "양호"로. 강재는 [해당없음](철근콘크리트 구조) → 강재 글 고정.
// 내진보강(학교만) = [해당없음] 또는 보강 부위 사진 2장 → [🤖 점검표 쓰기](AI 1번)로 부록 내진보강시설 육안 점검표. 서버 server/api/routers/sitok_good.py.

(function () {
  const rid = Number(new URLSearchParams(location.search).get("report")) || null;
  if (!rid) return;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const $ = (id) => document.getElementById(id);
  const url = `/sitok/reports/${rid}`;
  let data = null;
  let ts = Date.now();

  function say(id, text, ok) {
    const el = $(id);
    el.hidden = !text;
    el.className = `mail-msg ${ok ? "ok" : "bad"}`;
    el.textContent = text || "";
  }

  const shot = (label) => `<label class="ov-shot pt-shot">📷 ${label}<input type="file" accept="image/*" capture="environment" hidden data-kr-file="1" /></label>
    <label class="ov-shot secondary pt-shot">🖼 고르기<input type="file" accept="image/*" hidden data-kr-file="1" /></label>`;

  function onFile(el, send) {
    el.querySelectorAll(".pt-shot input, .ov-now input").forEach((inp) => inp.addEventListener("change", async () => {
      if (!inp.files[0]) return;
      el.classList.add("busy");
      await send(inp.files[0]); // send가 오류를 알림·busy 풂
    }));
  }

  // ── 👍 상태양호 ──
  function drawGood() {
    const n = data.cats.reduce((a, c) => a + c.photos.length, 0);
    $("gd-count").textContent = n ? `(${n})` : "";
    $("gd-list").innerHTML = data.cats.map((c) => {
      const na = c.key === "steel" && data.steel_na;
      const head = `<h3 class="sf-h">${esc(c.name)} <span class="sk-help">결함 ${c.defects}개${c.defects ? "" : " — 상태양호 사진을 찍어 두세요"}</span>
        ${c.key === "steel" ? `<button type="button" class="gd-na${na ? " on" : ""}">${na ? "해당없음 풀기" : "해당없음"}</button>` : ""}</h3>`;
      if (na) return `<div class="pt-group" data-key="${c.key}">${head}<div class="pt-card none gd-na-card"><div class="pt-name">해당없음<span>철근콘크리트 구조</span></div>
        <div class="pt-hint">보고서 1.3 강재구조 글: "${esc(data.steel_text)}" · 사진 칸 "해당없음"</div></div></div>`;
      const nowP = c.photos.filter((p) => !p.prev), prevP = c.photos.filter((p) => p.prev);
      const img = (p) => `<img src="${BASE}/api${url}/good/photo?key=${c.key}&idx=${p.idx}&t=${ts}" alt="" loading="lazy" />`;
      // 전회차(가져온 것) 사진마다 한 카드에 [전회차 | 이번](결함 조사처럼, 10/21 형) — 이번 사진은 같은 제목으로 짝지음
      const used = new Set();
      const pairs = prevP.map((pp) => {
        const m = nowP.find((n) => !used.has(n.idx) && n.title && n.title === pp.title);
        if (m) used.add(m.idx);
        return [pp, m];
      });
      const room = nowP.length < data.per;
      const pairCards = pairs.map(([pp, m]) => `<div class="pt-card gd-pair" data-prev="${pp.idx}" data-title="${esc(pp.title)}"${m ? ` data-idx="${m.idx}"` : ""}>
        <div class="pt-name">${esc(pp.title || "상태양호")}<span>${m ? "✓ 이번 사진" : "이번 사진 아직"}</span></div>
        <div class="ov-pair"><figure>${img(pp)}<figcaption>전회차</figcaption></figure>
          <figure>${m ? img(m) : room ? '<label class="ov-now"><span>📷 이번 찍기</span><input type="file" accept="image/*" capture="environment" hidden data-kr-file="1" /></label>'
            : '<div class="pt-blank">이번 사진 칸이 찼습니다</div>'}
            <figcaption>이번${m ? "" : " — 안 찍으면 전회차 사진이 들어감"}</figcaption></figure></div>
        ${m ? `<input class="gd-title" value="${esc(m.title)}" placeholder="사진 설명(보고서 사진 아래 글)" />` : ""}
        <div class="pt-acts">${m ? '<button type="button" class="pt-del">이번 사진 지우기</button>' : room ? '<label class="ov-shot secondary pt-shot">🖼 고르기<input type="file" accept="image/*" hidden data-kr-file="1" /></label>' : ""}
          <button type="button" class="gd-del-prev">전회차 빼기</button></div></div>`).join("");
      const cards = nowP.filter((p) => !used.has(p.idx)).map((p) => `<div class="pt-card" data-idx="${p.idx}">
        ${img(p)}
        <input class="gd-title" value="${esc(p.title)}" placeholder="사진 설명(보고서 사진 아래 글)" />
        <div class="pt-acts"><button type="button" class="pt-del">지우기</button></div></div>`).join("");
      const add = room ? `<div class="pt-card gd-add"><div class="pt-name">새 사진 ${nowP.length + 1}<span>${data.per}장까지</span></div>
        <div class="pt-blank">${prevP.length ? "전회차에 없던 자리" : "결함 사진 다음 빈 칸에 들어갑니다"}</div><div class="pt-acts">${shot("찍기")}</div></div>` : "";
      return `<div class="pt-group" data-key="${c.key}">${head}<div class="pt-grid">${pairCards}${cards}${add}</div></div>`;
    }).join("");
    $("gd-list").querySelectorAll(".pt-group").forEach((g) => {
      const key = g.dataset.key;
      g.querySelector(".gd-na")?.addEventListener("click", async () => {
        const c = data.cats.find((x) => x.key === key);
        if (!data.steel_na && c.photos.length && !confirm("강재를 해당없음으로 하면 찍은 강재 사진은 보고서에 안 들어갑니다. 할까요?")) return;
        try { data = await apiPost(`${url}/good/steel`, { na: !data.steel_na }); draw(); } catch (e) { say("gd-msg", e.message); }
      });
      const sendNew = (el, title) => async (file) => {
        say("gd-msg", "올리는 중…", true);
        const fd = new FormData();
        fd.append("key", key);
        fd.append("file", file);
        if (title) fd.append("title", title);
        try { data = await apiUploadSafe(`${url}/good/photo`, fd, { label: "상태양호 사진" }); ts = Date.now(); say("gd-msg", ""); draw(); } catch (e) { say("gd-msg", e.message); el.classList.remove("busy"); }
      };
      const add = g.querySelector(".gd-add");
      if (add) onFile(add, sendNew(add, ""));
      g.querySelectorAll(".gd-pair:not([data-idx])").forEach((el) => {
        onFile(el, sendNew(el, el.dataset.title));
        const lab = el.querySelector(".ov-now");
        if (lab) enableFileDrop(lab, lab.querySelector("input"));
      });
      g.querySelectorAll(".gd-del-prev").forEach((b) => b.addEventListener("click", async () => {
        const idx = Number(b.closest(".gd-pair").dataset.prev);
        if (!confirm("전회차 사진을 뺄까요? (이번 사진이 없으면 보고서 이 칸이 비게 됩니다)")) return;
        try { data = await api(`${url}/good/photo?key=${key}&idx=${idx}`, { method: "DELETE" }); ts = Date.now(); draw(); } catch (e) { say("gd-msg", e.message); }
      }));
      g.querySelectorAll(".gd-pair img").forEach((im) => im.addEventListener("click", (e) => window.open(e.target.src, "_blank")));
      g.querySelectorAll(".pt-card[data-idx]").forEach((el) => {
        const idx = Number(el.dataset.idx);
        el.querySelector(".gd-title").addEventListener("change", async (e) => {
          try { data = await apiPatch(`${url}/good/photo`, { key, idx, title: e.target.value }); say("gd-msg", "저장했습니다.", true); } catch (err) { say("gd-msg", err.message); }
        });
        el.querySelector(".pt-del").addEventListener("click", async () => {
          if (!confirm("이 사진을 지울까요?")) return;
          try { data = await api(`${url}/good/photo?key=${key}&idx=${idx}`, { method: "DELETE" }); ts = Date.now(); draw(); } catch (e) { say("gd-msg", e.message); }
        });
        if (!el.classList.contains("gd-pair")) el.querySelector("img").addEventListener("click", (e) => window.open(e.target.src, "_blank"));
      });
    });
  }

  // ── 🏫 내진보강(학교만) ──
  function drawSeismic() {
    const se = data.seismic;
    const n = se.photos.filter(Boolean).length;
    $("se-count").textContent = se.none ? "(해당없음)" : n ? `(${n}/2)` : "";
    const top = `<div class="se-top"><button type="button" class="se-none${se.none ? " on" : ""}">${se.none ? "해당없음 풀기" : "해당없음"}</button>
      <span class="page-sub">${se.none ? "부록 점검표는 회사 원본 그대로(×·해당없음, 사진·종합의견 \"-\")" : "내진보강을 안 한 건물이면 [해당없음]"}</span></div>`;
    if (se.none) { $("se-box").innerHTML = top; bindSeismic(); return; }
    const slots = se.photos.map((has, i) => `<div class="pt-card" data-slot="${i}">
      <div class="pt-name">보강 부위 사진 ${i + 1}<span>${has ? "✓ 사진" : "아직"}</span></div>
      ${has ? `<img src="${BASE}/api${url}/seismic/photo?slot=${i}&t=${ts}" alt="" loading="lazy" />` : '<div class="pt-blank">철골 가새·증설 벽·보강 기초 등</div>'}
      <div class="pt-acts">${shot(has ? "다시 찍기" : "찍기")}${has ? '<button type="button" class="pt-del">지우기</button>' : ""}</div></div>`).join("");
    const rows = se.items.map((name, i) => {
      const r = se.rows[i] || { mark: "", text: "", action: "" };
      return `<tr data-i="${i}"><td>${esc(name)}</td>
        <td><select class="se-mark"><option value="">-</option><option${r.mark === "○" ? " selected" : ""}>○</option><option${r.mark === "×" ? " selected" : ""}>×</option></select></td>
        <td><input class="se-text" value="${esc(r.text)}" placeholder="내용(위치, 상태)" /></td>
        <td><input class="se-action" value="${esc(r.action)}" placeholder="조치사항" /></td></tr>`;
    }).join("");
    $("se-box").innerHTML = `${top}<div class="pt-grid se-photos">${slots}</div>
      <div class="se-ai"><button type="button" id="se-ai"${n ? "" : " disabled"}>🤖 점검표 쓰기</button>
        <span class="page-sub">${se.at ? `AI가 ${esc(se.at)}에 썼습니다 — 고치는 대로 저장` : n ? "사진을 보고 6항목·종합의견을 씁니다(AI 1번, 10~20초)" : "사진을 먼저 찍으세요"}</span></div>
      <div class="table-wrap"><table class="se-table"><thead><tr><th>점검내용</th><th>○, ×</th><th>내용(위치, 상태)</th><th>조치사항</th></tr></thead><tbody>${rows}</tbody></table></div>
      <label class="se-op">종합의견<textarea id="se-opinion" rows="3" placeholder="[🤖 점검표 쓰기] 또는 직접 입력">${esc(se.opinion)}</textarea></label>`;
    bindSeismic();
  }

  function bindSeismic() {
    const box = $("se-box");
    box.querySelector(".se-none").addEventListener("click", async () => {
      try { data = await apiPost(`${url}/seismic`, { none: !data.seismic.none }); draw(); } catch (e) { say("se-msg", e.message); }
    });
    box.querySelectorAll(".pt-card[data-slot]").forEach((el) => {
      const slot = el.dataset.slot;
      onFile(el, async (file) => {
        say("se-msg", "올리는 중…", true);
        const fd = new FormData();
        fd.append("slot", slot);
        fd.append("file", file);
        try { data = await apiUploadSafe(`${url}/seismic/photo`, fd, { label: "내진보강 사진" }); ts = Date.now(); say("se-msg", ""); draw(); } catch (e) { say("se-msg", e.message); el.classList.remove("busy"); }
      });
      el.querySelector(".pt-del")?.addEventListener("click", async () => {
        if (!confirm("이 사진을 지울까요?")) return;
        try { data = await api(`${url}/seismic/photo?slot=${slot}`, { method: "DELETE" }); ts = Date.now(); draw(); } catch (e) { say("se-msg", e.message); }
      });
      el.querySelector("img")?.addEventListener("click", (e) => window.open(e.target.src, "_blank"));
    });
    $("se-ai")?.addEventListener("click", async (e) => {
      if (data.seismic.rows.length && !confirm("지금 점검표를 AI가 새로 씁니다(고친 글은 바뀜). 할까요?")) return;
      e.target.disabled = true;
      say("se-msg", "AI가 사진을 보고 점검표를 쓰는 중…(10~20초)", true);
      try { data = await apiPost(`${url}/seismic/ai`); say("se-msg", "썼습니다 — 확인하고 틀린 곳은 고치세요.", true); draw(); } catch (err) { say("se-msg", err.message); e.target.disabled = false; }
    });
    const save = async () => {
      const rows = [...box.querySelectorAll(".se-table tr[data-i]")].map((tr) => ({
        mark: tr.querySelector(".se-mark").value, text: tr.querySelector(".se-text").value, action: tr.querySelector(".se-action").value }));
      try { data = await apiPost(`${url}/seismic`, { rows, opinion: $("se-opinion").value }); say("se-msg", "저장했습니다.", true); } catch (e) { say("se-msg", e.message); }
    };
    box.querySelectorAll(".se-table select, .se-table input, #se-opinion").forEach((el) => el.addEventListener("change", save));
  }

  window.addEventListener("kf-upload-done", (e) => { // 폰에 보관했던 사진이 나중에 올라가면(10/22)
    const p = String((e.detail || {}).path || "");
    if ((p === `${url}/good/photo` || p === `${url}/seismic/photo`) && e.detail.data) { data = e.detail.data; ts = Date.now(); draw(); }
  });

  function draw() {
    if (data.fam === "wall") { // 옹벽(10/20): 1.4 현장조사 결과 절마다 사진 표
      const intro = document.querySelector("#sf-good .pt-intro");
      if (intro) intro.textContent = "보고서 1.4 현장조사 결과(지반 및 기초부 / 옹벽 전면부 / 기타) 사진 표 — 결함이 없거나 적은 절은 상태가 양호한 모습을 찍어 두세요. 결함 사진 다음 빈 칸에 들어가고 [🤖 AI 초안]이 \"양호\"로 씁니다.";
    }
    drawGood();
    const tab = document.querySelector('.sf-tab[data-tab="seismic"]');
    tab.hidden = !data.school;
    if (data.school) drawSeismic();
  }

  api(`${url}/good`).then((d) => { data = d; draw(); }).catch((e) => say("gd-msg", e.message));
})();
