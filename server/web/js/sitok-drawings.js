// 시특법 시설물 도면 칸(10/12 사용자, 10/14 3층 구조로 시설물 정보·서류 칸에 — 전엔 회차 [🏢 시설물 현황] 창 안).
// 시설물에 한 번 올리면 다음 회차에도 그대로, 증축·인테리어 등으로 바뀌면 여기서 바꿈. 서버 routers/sitok_drawings.py(/sitok/facilities/{id}/drawings…).
// 종류: struct(구조일반사항·건축개요 — 시설물 현황 AI가 읽음) · attach(첨부 도면 — 보고서 1.2.9 뒤) · schedule(구조 일람표 — 정밀 재료시험 설계 치수, 10/14).

async function sitokDrawDrawings(el, url, data) {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  try { data = data || await api(url); } catch (e) { el.innerHTML = `<div class="mail-msg bad">${esc(e.message)}</div>`; return; }
  const KIND = { struct: ["📐 구조일반사항·건축개요 도면", "시설물 현황 [🤖 채우기]가 같이 읽음(콘크리트 강도·철근 종류·기초형식·지하깊이·슬래브 두께·방수 등)"],
    attach: ["🗂 첨부 도면(평·입·단면도)", "보고서 1.2.9 관련 설계도면 쪽 뒤에 이 순서로 붙음 — 없으면 \"-\""],
    schedule: ["📏 구조 일람표(기둥·보·슬래브·벽 단면표)", "정밀 📐 재료시험 [🤖 일람표에서 설계 치수 채우기]가 읽음"] };
  el.innerHTML = `<div class="dt-dwg-note sk-help">도면은 시설물에 한 번 올리면 다음 회차에도 그대로 씁니다 — 증축·내부 인테리어 등으로 바뀌면 지우고 새로 올리세요(이미 만든 보고서는 그대로).</div>`
    + Object.entries(KIND).map(([k, [label, help]]) => `<div class="dt-dwg-k" data-k="${k}"><div class="dt-dwg-h"><b>${label}</b> <span class="sk-help">${help}</span>
      <label class="secondary-link">+ 올리기(PDF·그림, 여러 개)<input type="file" accept="application/pdf,.pdf,image/*" multiple hidden data-kr-file="1" /></label></div>
      ${(data[k] || []).length ? `<ol class="dt-dwg-list">${data[k].map((d, i) => `<li data-id="${d.id}"><a href="${BASE}/api${url}/${k}/${d.id}/file" target="_blank" rel="noopener">${esc(d.name)}</a>
        <span class="sk-help">${d.pdf ? `${d.pages}쪽` : "그림"} · ${esc(d.at)}</span>
        ${k === "attach" ? `<button type="button" class="link-btn" data-m="-1"${i ? "" : " disabled"}>▲</button><button type="button" class="link-btn" data-m="1"${i < data[k].length - 1 ? "" : " disabled"}>▼</button>` : ""}
        <button type="button" class="link-btn dt-dwg-del" title="지우기">✕</button></li>`).join("")}</ol>` : '<div class="sk-help dt-dwg-none">아직 없음</div>'}</div>`).join("");
  el.querySelectorAll(".dt-dwg-k").forEach((row) => {
    const k = row.dataset.k;
    const inp = row.querySelector("input[type=file]");
    inp.addEventListener("change", async () => {
      const files = [...inp.files];
      for (let i = 0; i < files.length; i++) {
        row.querySelector(".dt-dwg-h .sk-help").textContent = `올리는 중… ${i + 1} / ${files.length}`;
        const fd = new FormData();
        fd.append("kind", k);
        fd.append("file", files[i]);
        try { data = await apiUpload(url, fd); } catch (e) { alert(e.message); break; }
      }
      sitokDrawDrawings(el, url, data);
    });
    row.querySelectorAll("li").forEach((li) => {
      li.querySelector(".dt-dwg-del").addEventListener("click", async () => {
        if (!confirm("이 도면을 지울까요? 다음에 만드는 보고서부터 빠집니다.")) return;
        try { sitokDrawDrawings(el, url, await api(`${url}/${k}/${li.dataset.id}`, { method: "DELETE" })); } catch (e) { alert(e.message); }
      });
      li.querySelectorAll("[data-m]").forEach((b) => b.addEventListener("click", async () => {
        try { sitokDrawDrawings(el, url, await apiPost(`${url}/${k}/${li.dataset.id}/move`, { step: Number(b.dataset.m) })); } catch (e) { alert(e.message); }
      }));
    });
  });
}
