// 시특법 현장 화면 — 전회차 사진 보여 주기·이번 회차에 그대로 넣기(2026-10-23 사용자 "다음 회차 시 전회차 보여 주기 — 상태양호·내진보강·공중이용·기타시설 등
// 전회차 사진 금회차에 그대로 넣기"). 네 탭 위에 "📷 전회차(2026 상반기) 사진 N장 [보기] [빈 칸에 그대로 넣기]" — 보기 = 항목마다 사진(직전 회차 원래 주소),
// 넣기 = 이번 회차에서 비어 있는 칸에만 복사(이미 찍은 칸은 그대로) → "sitok-prev-copied" 이벤트로 그 탭이 다시 불러 그림. 서버 server/api/routers/sitok_prevphotos.py.

(function () {
  const rid = Number(new URLSearchParams(location.search).get("report")) || null;
  if (!rid) return;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const SLOT = { good: "gd-list", seismic: "se-box", public: "pt-public", other: "pt-other" }; // 줄을 그 칸 바로 앞에
  let info = null;

  function items(tab) { // [{cap, src, fill}] + 채울 칸 수
    const pid = info.prev.id;
    const g = (k, i) => `${BASE}/api/sitok/reports/${pid}/good/photo?key=${k}&idx=${i}`;
    const p = (grp, k, s, which) => `${BASE}/api/sitok/reports/${pid}/parts/photo?group=${grp}&key=${k}&slot=${s}${which === "prev" ? "&which=prev" : ""}`;
    if (tab === "good") {
      const out = info.good.flatMap((c) => c.photos.map((ph) => ({ cap: `${c.name}${ph.title && ph.title !== `${c.name} 상태양호` ? ` — ${ph.title}` : ""}`, src: g(c.key, ph.idx), fill: c.fill })));
      if (info.steel_na) out.push({ cap: "강재구조 — 해당없음", src: "", fill: false });
      return { list: out, fill: info.good.filter((c) => c.fill).length };
    }
    if (tab === "seismic") {
      const se = info.seismic;
      if (!se) return { list: [], fill: 0 };
      return { list: se.none ? [{ cap: "내진보강 — 해당없음", src: "" }] : se.photos.map((has, i) => (has ? { cap: `보강 부위 사진 ${i + 1}`, src: `${BASE}/api/sitok/reports/${pid}/seismic/photo?slot=${i}` } : null)).filter(Boolean), fill: se.fill };
    }
    if (tab === "public") return { list: info.public.map((x) => ({ cap: `${x.name}${x.none ? " — 해당없음" : ""}`, src: x.none ? "" : p("public", x.key, 0, x.which), fill: x.fill })), fill: info.public.filter((x) => x.fill).length };
    return { list: info.other.flatMap((o) => Array.from({ length: o.slots }, (_, i) => ({ cap: `${o.name} ${i + 1}`, src: p("other", o.key, i), fill: o.fill }))), fill: info.other.filter((o) => o.fill).length };
  }

  function draw() {
    for (const [tab, id] of Object.entries(SLOT)) {
      const host = document.getElementById(id);
      if (!host) continue;
      let bar = document.querySelector(`.pv-bar[data-tab="${tab}"]`);
      const it = info && info.prev ? items(tab) : { list: [] };
      if (!it.list.length) { if (bar) bar.remove(); continue; }
      if (!bar) {
        bar = document.createElement("div");
        bar.className = "pv-bar";
        bar.dataset.tab = tab;
        host.before(bar);
      }
      const open = bar.querySelector(".pv-grid") && !bar.querySelector(".pv-grid").hidden;
      const photos = it.list.filter((x) => x.src).length;
      bar.innerHTML = `<span class="pv-txt">📷 전회차(${esc(info.prev.label)}) ${photos ? `사진 <b>${photos}장</b>` : "기록"}</span>
        <button type="button" class="secondary btn-sm pv-show">${open ? "접기" : "보기"}</button>
        <button type="button" class="btn-sm pv-copy"${it.fill ? "" : " disabled"} title="${it.fill ? "이번 회차에서 비어 있는 칸에만 넣습니다 — 이미 찍은 칸은 그대로" : "이번 회차에 이미 다 들어 있습니다"}">
          ${it.fill ? `빈 칸에 그대로 넣기 (${it.fill}칸)` : "이번 회차에 다 있음"}</button>
        <span class="pv-msg"></span>
        <div class="pv-grid"${open ? "" : " hidden"}>${it.list.map((x) => `<figure class="${x.fill ? "pv-fill" : ""}">${x.src ? `<img src="${x.src}" alt="" loading="lazy" />` : '<div class="pv-none">해당없음</div>'}
          <figcaption>${esc(x.cap)}${x.fill ? " <em>· 이번에 비어 있음</em>" : ""}</figcaption></figure>`).join("")}</div>`;
      bar.querySelector(".pv-show").addEventListener("click", (e) => { const grid = bar.querySelector(".pv-grid"); grid.hidden = !grid.hidden; e.target.textContent = grid.hidden ? "보기" : "접기"; });
      bar.querySelectorAll(".pv-grid img").forEach((im) => im.addEventListener("click", () => window.open(im.src, "_blank")));
      bar.querySelector(".pv-copy").addEventListener("click", async (e) => {
        const btn = e.target.closest("button");
        btn.disabled = true;
        const msg = bar.querySelector(".pv-msg");
        msg.textContent = "넣는 중…";
        try {
          const r = await apiPost(`/sitok/reports/${rid}/prev-photos/copy`, { tab });
          window.dispatchEvent(new CustomEvent("sitok-prev-copied", { detail: { tab } })); // 그 탭이 다시 불러 그림
          await load();
          const m = document.querySelector(`.pv-bar[data-tab="${tab}"] .pv-msg`);
          if (m) m.textContent = `✓ ${r.copied}개 넣었습니다`;
        } catch (err) { msg.textContent = err.message; btn.disabled = false; }
      });
    }
  }

  async function load() {
    try { info = await api(`/sitok/reports/${rid}/prev-photos`); } catch (e) { info = null; }
    draw();
  }
  load();
})();
