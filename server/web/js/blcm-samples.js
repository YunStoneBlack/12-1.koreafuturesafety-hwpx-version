// 부적합 견본 고르기(2026-10-30 사용자 "견본이 잘못되면 계속 잘못된 사진을 찍어 올 수 있음 — 형·민재형이 확인") — 칸마다 지금 견본(검토 전/✓ 확인)·회사 보고서 후보(그 칸 점수 순).
// 서버 GET|PUT /blcm/bad-samples. 고르면 바로 저장(회사 공통 bad.json) → 건 화면 ⚠ 부적합 칸 견본.
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const errorEl = $("error");
  const src = (file) => `${BASE}/api/blcm/samples/${encodeURIComponent(file)}`;
  let items = [], filter = "todo";
  const openRows = new Set(), openCards = new Set((location.hash || "").slice(1) ? [decodeURIComponent(location.hash.slice(1))] : []);

  const stateOf = (t) => (!t.pick ? "empty" : t.pick.ok ? "ok" : "todo");
  function drawCount() {
    const all = items.flatMap((x) => x.types);
    const n = (s) => all.filter((t) => stateOf(t) === s).length;
    $("bs-count").textContent = `칸 ${all.length} · ✓ 확인 ${n("ok")} · 검토 전 ${n("todo")} · 빈 칸 ${n("empty")} · 후보 ${items.reduce((a, x) => a + x.cands.length, 0)}장`;
    const f = [["todo", `검토 전 있는 항목`], ["cands", "후보 있는 항목"], ["all", "전체"]];
    $("bs-filter").innerHTML = `<span class="site-sort">${f.map(([k, l]) => `<button type="button" data-f="${k}" class="${filter === k ? "on" : ""}">${esc(l)}</button>`).join("")}</span>`;
    $("bs-filter").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { filter = b.dataset.f; draw(); }));
  }
  function candsFor(x, t) { // 그 칸 점수 높은 순, 같은 점수면 원래 차례
    return x.cands.map((c, i) => ({ c, i, s: (c.score || {})[t.key] || 0 })).sort((a, b) => b.s - a.s || a.i - b.i).map((y) => y.c);
  }
  function rowHtml(x, t) {
    const st = stateOf(t), k = `${x.code}|${t.key}`;
    const p = t.pick;
    const list = openRows.has(k) ? candsFor(x, t) : [];
    return `<div class="bs-row ${st}" data-key="${esc(t.key)}">
      <div class="bs-now">${p ? `<a href="${src(p.file)}" target="_blank" rel="noopener"><img loading="lazy" src="${src(p.file)}" alt="" /></a>` : '<span class="bj-bad-none">견본<br>없음</span>'}</div>
      <div class="bs-t"><b>⚠ ${esc(t.label)}</b>${p ? `<small>${esc(p.caption || "")}${p.from ? ` · ${esc(p.from)}` : ""}</small>` : ""}
        <span class="bs-st ${st}">${st === "ok" ? `✓ 확인${p.by ? ` · ${esc(p.by)}` : ""}` : st === "todo" ? "검토 전" : "빈 칸"}</span>
        <span class="bs-btns">${st === "todo" ? '<button type="button" class="bs-ok">✓ 맞음</button>' : ""}<button type="button" class="secondary bs-pick">${openRows.has(k) ? "닫기 ▴" : `바꾸기 ▾ <small>후보 ${x.cands.length}</small>`}</button>${p ? '<button type="button" class="secondary bs-clear" title="이 칸 견본 비우기">✕</button>' : ""}</span></div>
      ${list.length ? `<div class="bs-cands">${list.map((c) => `<button type="button" class="bs-cand${p && p.file === `후보/${c.file}` ? " on" : ""}" data-file="후보/${esc(c.file)}"><img loading="lazy" src="${src(`후보/${c.file}`)}" alt="" /><small>${esc(c.caption)}</small><i>${esc(c.from)}</i></button>`).join("")}</div>`
        : openRows.has(k) ? '<div class="mail-note">이 항목은 회사 보고서에 부적합 사진 후보가 없습니다 — 현장에서 첫 부적합 사진을 찍으면 그때 견본으로 쓰겠습니다.</div>' : ""}</div>`;
  }
  async function put(code, key, file, ok) {
    const out = await api("/blcm/bad-samples", { method: "PUT", body: JSON.stringify({ code, key, file, ok }) });
    const x = items.find((y) => y.code === code);
    x.types = out.types;
  }
  function draw() {
    drawCount();
    const show = items.filter((x) => filter === "all" || (filter === "cands" ? x.cands.length : x.types.some((t) => stateOf(t) === "todo")));
    $("bs-list").innerHTML = show.map((x) => {
      const ok = x.types.filter((t) => stateOf(t) === "ok").length, todo = x.types.filter((t) => stateOf(t) === "todo").length;
      return `<details class="panel sk-fold bs-card" data-code="${esc(x.code)}"${openCards.has(x.code) ? " open" : ""}>
        <summary class="bj-card-h"><span class="bj-code">${esc(x.code)}</span><b>${esc(x.name)}</b><span class="bj-mid">${esc(x.big)}</span>
          <span class="bj-chip ${todo ? "mid" : ok ? "ok" : "empty"}">✓ ${ok}/${x.types.length}${todo ? ` · 검토 전 ${todo}` : ""}</span><span class="bj-nph">후보 ${x.cands.length}</span><span class="sk-fold-arrow">▾</span></summary>
        <div class="bs-rows">${x.types.map((t) => rowHtml(x, t)).join("")}</div></details>`;
    }).join("") || '<div class="empty-note">해당하는 항목이 없습니다 — [전체]를 누르세요.</div>';
    $("bs-list").querySelectorAll(".bs-card").forEach((card) => {
      const code = card.dataset.code, x = items.find((y) => y.code === code);
      card.addEventListener("toggle", () => { if (card.open) openCards.add(code); else openCards.delete(code); });
      card.querySelectorAll(".bs-row").forEach((row) => {
        const key = row.dataset.key, t = x.types.find((y) => y.key === key), k = `${code}|${key}`;
        const go = async (file, ok) => { try { await put(code, key, file, ok); openRows.delete(k); draw(); } catch (err) { showError(errorEl, err); } };
        row.querySelector(".bs-ok")?.addEventListener("click", () => go(t.pick.file, true));
        row.querySelector(".bs-clear")?.addEventListener("click", () => { if (confirm(`'${t.label}' 칸 견본을 비울까요?`)) go(null, false); });
        row.querySelector(".bs-pick").addEventListener("click", () => { if (openRows.has(k)) openRows.delete(k); else openRows.add(k); draw(); });
        row.querySelectorAll(".bs-cand").forEach((b) => b.addEventListener("click", () => go(b.dataset.file, true)));
      });
    });
  }
  (async () => {
    try { items = (await api("/blcm/bad-samples")).items; if (openCards.size) filter = "all"; draw(); } catch (err) { showError(errorEl, err); }
  })();
})();
