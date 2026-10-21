// 시특법 회차 화면 [📚 분권 — 성과품 추가] 칸(sitok-round.html, 2026-10-19 민재형 — 시안 그대로).
// 묶음 보고서와 같은 내용으로 일부 동만 따로 묶은 책 — 제출 현황·FMS 없음, 디지털 파일·제본용만. 동마다 [안 함 / 1권 / 2권 …], 같은 권 = 한 책.
// 서버 server/api/routers/sitok_split.py — 묶음 만들 때 만든 동별 한글로 다시 묶음(현장 조사·AI 초안 다시 안 함). 묶음(2동 이상)만 보임(정밀 묶음도 10/21 — 본문·부록은 묶음 때 만든 동별 파일로).

(function () {
  const rid = Number(new URLSearchParams(location.search).get("report")) || null;
  const panel = document.getElementById("bk-panel");
  if (!rid || !panel) return;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const $ = (id) => document.getElementById(id);
  let d = null;
  let timer = null;

  function say(text, ok) {
    const el = $("bk-msg");
    el.hidden = !text;
    el.className = `mail-msg ${ok ? "ok" : "bad"}`;
    el.textContent = text || "";
  }

  const file = (k, kind) => `${BASE}/api/sitok/reports/${d.lead_id}/split/file?k=${k}&kind=${kind}`;

  function draw() {
    const n = d.buildings.length;
    panel.hidden = n < 2 || d.kind === "성능평가"; // 묶음만(정기·정밀 — 정밀은 10/21부터), 내진성능평가는 분권 없음
    if (panel.hidden) return;
    const intro = panel.querySelector(".bk-intro");
    if (intro && d.wall) intro.textContent = "곳마다 몇 권째에 넣을지 고르세요. 같은 권 = 한 책(표지·용역명은 곳 개수 규칙 그대로), \"안 함\" = 분권에 안 넣음. 옹벽은 원본에서 바로 묶으니 묶음 보고서를 먼저 안 만들어도 됩니다(현장 조사·AI 초안 값 그대로)."; // 10/21
    const running = d.status === "running";
    const seg = (b) => {
      const cur = Number(d.assign[String(b.id)] || 0);
      const opts = [0, ...Array.from({ length: n }, (_, i) => i + 1)];
      return `<div class="bk-seg" data-id="${b.id}">${opts.map((k) => `<button type="button" data-k="${k}" class="${k === 0 ? "off" : ""}${k === cur ? " on" : ""}"${running ? " disabled" : ""}>${k ? `${k}권` : "안 함"}</button>`).join("")}</div>`;
    };
    const books = d.books.map((b) => `<div class="bk-book"><b>${b.k}권 · ${b.names.map((x) => esc(x)).join(" · ")}</b>
        <div class="bk-cover">표지·용역명: ${esc(b.title)}</div>
        <div class="bk-files">${b.has_pdf ? `<span class="bk-st ${b.stale ? "bad" : "ok"}">${b.stale ? "⚠ 묶음 보고서를 다시 만든 뒤라 옛 내용 — [분권 만들기]로 다시" : `✓ ${esc((b.made_at || "").slice(5))} 만듦`}${b.pages ? ` · ${b.pages}쪽` : ""}</span>
          <a class="secondary-link" href="${file(b.k, "pdf")}" target="_blank" rel="noopener">PDF 보기</a>
          ${b.has_cover ? `<a class="secondary-link" href="${file(b.k, "cover")}" target="_blank" rel="noopener" title="표지 + 책등 — 제본소에 따로 보내는 파일">표지(제본용) PDF</a>` : ""}
          ${b.has_hwpx ? `<a class="secondary-link" href="${file(b.k, "hwpx")}">한글 받기</a>` : ""}` : '<span class="bk-st">아직 안 만듦</span>'}</div></div>`).join("");
    const st = running ? `⏳ ${d.message}` : d.status === "failed" ? `✗ ${d.message}` : "";
    $("bk-box").innerHTML = `
      <div class="bk-quick"><button type="button" id="bk-each"${running ? " disabled" : ""}>동마다 따로(${n}권)</button><button type="button" id="bk-none"${running ? " disabled" : ""}>모두 안 함</button></div>
      <div class="bk-rows">${d.buildings.map((b) => `<div class="bk-row"><span class="bk-name">${esc(b.name)}</span>${seg(b)}</div>`).join("")}</div>
      <div class="bk-books">${books || '<div class="empty-note">분권에 넣은 동이 없습니다 — 동마다 몇 권째에 넣을지 고르세요.</div>'}</div>
      <div class="bk-foot"><span class="sk-help">${st ? esc(st) : d.why ? `🔒 ${esc(d.why)}` : d.kind === "정밀" ? "묶음 정밀 보고서를 다시 만들면 분권도 [분권 만들기]로 다시 — 본문·부록은 묶음 때 만든 동별 파일로 묶음(합본 PDF·본문 한글)." : "묶음 보고서를 다시 만들면 분권도 [분권 만들기]로 다시 — 요약문 결언은 기본 문장(AI 다시 안 부름)."}</span>
        <button type="button" id="bk-build"${!d.available || !d.books.length || running ? " disabled" : ""}>${running ? "만드는 중…" : `분권 만들기(${d.books.length}권)`}</button></div>`;
    bind();
    clearTimeout(timer);
    if (running) timer = setTimeout(load, 5000);
  }

  async function save(assign) {
    try { d = await apiPost(`/sitok/reports/${rid}/split`, { assign }); say(""); draw(); } catch (e) { say(e.message); }
  }

  function bind() {
    panel.querySelectorAll(".bk-seg").forEach((el) => el.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
      save({ ...d.assign, [el.dataset.id]: Number(b.dataset.k) });
    })));
    $("bk-each")?.addEventListener("click", () => save(Object.fromEntries(d.buildings.map((b, i) => [String(b.id), i + 1]))));
    $("bk-none")?.addEventListener("click", () => save({}));
    $("bk-build")?.addEventListener("click", async (e) => {
      e.target.disabled = true;
      try { d = await apiPost(`/sitok/reports/${rid}/split/build`); say(`분권 ${d.books.length}권을 만드는 중입니다 — 권마다 몇 분 걸립니다.`, true); draw(); }
      catch (err) { say(err.message); e.target.disabled = false; }
    });
  }

  async function load() {
    try { d = await api(`/sitok/reports/${rid}/split`); draw(); } catch (_) { panel.hidden = true; }
  }

  window.addEventListener("sitok-report-built", load); // 묶음 보고서를 다 만들면 다시 읽음(sitok-round.js)
  load();
})();
