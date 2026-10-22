// 시특법 현장 화면 [🚶 공중이용]·[🧱 기타시설] 탭(sitok-field.html, 2026-10-12 사용자).
// 공중이용 = 추락방지시설·도로포장·도로부 신축이음부·환기구 등의 덮개 — 항목마다 사진 한 장 또는 [해당없음] → 보고서 6) 표 항목마다 한 칸.
// 기타시설 = 마감재 2장·부착물 등 2장 → 7) 표(빈 칸 "-"). AI 초안이 사진을 보고 조사항목·상태평가기준으로 판단. 서버 server/api/routers/sitok_parts.py.

(function () {
  const rid = Number(new URLSearchParams(location.search).get("report")) || null;
  if (!rid) return;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const url = `/sitok/reports/${rid}/parts`;
  let data = { public: [], other: [] };
  let ts = Date.now();

  function say(id, text, ok) {
    const el = document.getElementById(id);
    el.hidden = !text;
    el.className = `mail-msg ${ok ? "ok" : "bad"}`;
    el.textContent = text || "";
  }

  const src = (group, key, slot) => `${BASE}/api${url}/photo?group=${group}&key=${key}&slot=${slot}&t=${ts}`;
  const shot = (label) => `<label class="ov-shot pt-shot">📷 ${label}<input type="file" accept="image/*" capture="environment" hidden data-kr-file="1" /></label>
    <label class="ov-shot secondary pt-shot">🖼 고르기<input type="file" accept="image/*" hidden data-kr-file="1" /></label>`;

  window.addEventListener("kf-upload-done", (e) => { // 폰에 보관했던 사진이 나중에 올라가면(10/22)
    if (String((e.detail || {}).path || "") === `${url}/photo` && e.detail.data) { data = e.detail.data; ts = Date.now(); draw(); }
  });

  function draw() {
    const oth = document.querySelector('.sf-tab[data-tab="other"]'); // 옹벽은 기타시설(마감재·부착물) 없음(10/20) — 공중이용(펜스·점검로)만
    if (oth) oth.hidden = !!data.wall;
    const done = data.public.filter((p) => p.has || p.none).length;
    document.getElementById("pt-pub-count").textContent = `(${done}/${data.public.length})`;
    const n = data.other.reduce((a, o) => a + o.slots.filter(Boolean).length, 0);
    document.getElementById("pt-oth-count").textContent = n ? `(${n})` : "";
    document.getElementById("pt-public").innerHTML = data.public.map((p) => `<div class="pt-card${p.none ? " none" : ""}" data-group="public" data-key="${p.key}" data-slot="0">
      <div class="pt-name">${esc(p.name)}<span>${p.has ? "✓ 사진" : p.none ? "해당없음" : "아직"}</span></div>
      <div class="pt-hint">${esc(p.hint)}</div>
      ${p.has_prev ? `<div class="ov-pair"><figure><img src="${src("public", p.key, 0)}&which=prev" alt="" loading="lazy" /><figcaption>전회차</figcaption></figure>
        <figure>${p.has ? `<img src="${src("public", p.key, 0)}" alt="" loading="lazy" />` : p.none ? '<div class="pt-blank">해당없음</div>'
          : '<label class="ov-now"><span>📷 이번 찍기</span><input type="file" accept="image/*" capture="environment" hidden data-kr-file="1" /></label>'}
          <figcaption>이번${p.has || p.none ? "" : " — 안 찍으면 전회차 사진이 들어감"}</figcaption></figure></div>`
        : p.has ? `<img src="${src("public", p.key, 0)}" alt="" loading="lazy" />` : `<div class="pt-blank">${p.none ? "해당없음 — 보고서 칸에 \"해당없음\"" : "사진 없음"}</div>`}
      <div class="pt-acts">${p.none ? "" : shot(p.has ? "다시 찍기" : "찍기")}
        <button type="button" class="pt-none">${p.none ? "해당없음 풀기" : "해당없음"}</button>
        ${p.has ? '<button type="button" class="pt-del">지우기</button>' : ""}</div></div>`).join("");
    document.getElementById("pt-other").innerHTML = data.other.map((o) => `<div class="pt-group"><h3 class="sf-h">${esc(o.name)} <span class="sk-help">2장까지 — 보고서 표 ${o.key === "finish" ? "윗줄" : "아랫줄"}</span></h3>
      <div class="pt-grid">${o.slots.map((has, i) => `<div class="pt-card" data-group="other" data-key="${o.key}" data-slot="${i}">
        <div class="pt-name">${esc(o.name)} ${i + 1}<span>${has ? "✓ 사진" : "비면 \"-\""}</span></div>
        ${has ? `<img src="${src("other", o.key, i)}" alt="" loading="lazy" />` : '<div class="pt-blank">사진 없음</div>'}
        <div class="pt-acts">${shot(has ? "다시 찍기" : "찍기")}${has ? '<button type="button" class="pt-del">지우기</button>' : ""}</div></div>`).join("")}</div></div>`).join("");
    document.querySelectorAll(".pt-card").forEach((el) => {
      const { group, key, slot } = el.dataset;
      const msg = group === "public" ? "pt-msg" : "pt-msg2";
      el.querySelectorAll(".pt-shot input, .ov-now input").forEach((inp) => inp.addEventListener("change", async () => {
        if (!inp.files[0]) return;
        el.classList.add("busy");
        say(msg, "올리는 중…", true);
        const fd = new FormData();
        fd.append("group", group);
        fd.append("key", key);
        fd.append("slot", slot);
        fd.append("file", inp.files[0]);
        try { data = await apiUploadSafe(`${url}/photo`, fd, { label: group === "public" ? "공중이용 사진" : "기타시설 사진" }); ts = Date.now(); say(msg, ""); draw(); } catch (e) { say(msg, e.message); el.classList.remove("busy"); }
      }));
      el.querySelector(".pt-del")?.addEventListener("click", async () => {
        if (!confirm("이 사진을 지울까요?")) return;
        try { data = await api(`${url}/photo?group=${group}&key=${key}&slot=${slot}`, { method: "DELETE" }); draw(); } catch (e) { say(msg, e.message); }
      });
      el.querySelector(".pt-none")?.addEventListener("click", async () => {
        const p = data.public.find((x) => x.key === key);
        if (!p.none && p.has && !confirm("해당없음으로 하면 찍은 사진은 지워집니다. 할까요?")) return;
        try { data = await apiPost(`${url}/none`, { key, none: !p.none }); draw(); } catch (e) { say(msg, e.message); }
      });
      el.querySelectorAll("img").forEach((im) => im.addEventListener("click", (e) => window.open(e.target.src, "_blank")));
    });
  }

  api(url).then((d) => { data = d; draw(); }).catch((e) => say("pt-msg", e.message));
})();
