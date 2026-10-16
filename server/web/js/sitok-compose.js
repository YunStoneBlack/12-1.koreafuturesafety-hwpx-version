// 시특법 시설물 화면 "📚 보고서 구성"(sitok-facility.html?id=, 2026-10-16 민재형) — 카드 안 건물을 보고서 상자에 넣어 보고서를 몇 권 낼지 정함.
// 상자 하나에 건물 여럿 = 동 묶음(보고서 한 권, 동마다 제N장), 건물 하나 = 그 건물만. PC는 끌어다 놓기, 폰은 건물을 누른 뒤 상자를 누름.
// 계약이 이 반기에 둘 이상일 때만 상자마다 계약을 고름(하나면 자동). 반기마다(◀ ▶) 계약 연결이 다를 수 있음 — 저장하면 지금 구조(묶음·번호)가 바뀜.
// 서버 server/api/routers/sitok_compose.py. 저장 뒤 "sitok-group-changed" → 회차 칸(js/sitok-reports.js) 다시 읽음.

(function () {
  const fid = Number(new URLSearchParams(location.search).get("id")) || null;
  const panel = document.getElementById("sk-compose-panel");
  const box = document.getElementById("sk-compose");
  if (!fid || !panel || !box) return;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const now = new Date();
  let cur = { year: now.getFullYear(), half: now.getMonth() < 6 ? "상반기" : "하반기" };
  let d = null; // 서버 응답
  let books = []; // [{ids, name, contract_id}] — 화면에서 고치는 중
  let picked = null; // 폰: 누른 건물 id
  let dirty = false;

  const bld = (id) => d.buildings.find((b) => b.id === id);
  const common = (names) => { // 건물 이름들의 같은 앞부분 — 묶음 이름 기본값(서버 sitok_compose.default_name과 같음)
    let p = names[0] || "";
    for (const n of names) while (p && !n.startsWith(p)) p = p.slice(0, -1);
    p = p.trim();
    return p.length >= 2 ? p : names[0] || "";
  };
  const noOf = (k) => (books.filter((b) => b.ids.length).length > 1 ? `${d.card.no}-${books.filter((b, i) => b.ids.length && i <= k).length}` : d.card.no);

  async function load() {
    try {
      d = await api(`/sitok/facilities/${fid}/compose?year=${cur.year}&half=${encodeURIComponent(cur.half)}`);
      books = d.books.map((b) => ({ ...b, ids: b.ids.slice() }));
      dirty = false;
      panel.hidden = d.buildings.length < 2; // 건물이 하나면 구성할 게 없음
      draw();
    } catch (err) {
      box.innerHTML = `<div class="mail-msg bad">${esc(err.message)}</div>`;
    }
  }

  function chip(id) {
    const b = bld(id);
    const r = b.round;
    return `<span class="cp-chip${picked === id ? " on" : ""}" draggable="true" data-id="${id}" title="${esc(b.fms_no || "")}">${esc(b.name)}${r ? `<small>${esc(r.kind || "")}${r.data ? " · 조사 있음" : ""}</small>` : ""}</span>`;
  }

  function draw() {
    const multiCon = d.contracts.length > 1;
    const live = books.filter((b) => b.ids.length).length;
    box.innerHTML = `
      <div class="cp-top"><button type="button" class="secondary btn-sm cp-prev" aria-label="이전 반기">◀</button><b class="cp-half">${cur.year}년 ${esc(cur.half)}</b>
        <button type="button" class="secondary btn-sm cp-next" aria-label="다음 반기">▶</button>
        <span class="sk-help">건물 ${d.buildings.length}개 → 보고서 ${live}권 · ${d.contracts.length ? `이 반기 계약 ${d.contracts.length}건${multiCon ? " — 보고서마다 계약을 고르세요" : "(자동 연결)"}` : "이 반기 계약 없음"}</span></div>
      <div class="cp-tools"><button type="button" class="secondary btn-sm cp-one">전부 한 권</button><button type="button" class="secondary btn-sm cp-each">전부 따로</button>
        ${d.suggest ? '<button type="button" class="secondary btn-sm cp-sug" title="계약 건명·내역서에 나오는 건물 이름으로">🤖 계약대로 추천 배치</button>' : ""}
        <span class="sk-help cp-tip">PC: 건물을 끌어다 상자에 놓기 · 폰: 건물을 누른 뒤 넣을 상자를 누르기</span></div>
      <div class="cp-books">${books.map((b, k) => `<div class="cp-book${b.ids.length ? "" : " empty"}" data-k="${k}">
          <div class="cp-head"><b>보고서 ${books.slice(0, k + 1).filter((x) => x.ids.length).length || "—"}</b>${b.ids.length ? `<span class="site-no">${esc(noOf(k))}</span>` : ""}
            ${b.ids.length && !dirty ? (bld(b.ids[0]).round ? `<a class="cp-open" href="sitok-round.html?report=${bld(b.ids[0]).round.id}">회차 열기 ›</a>` : '<span class="sk-help">이 반기 회차 없음</span>') : ""}
            ${b.ids.length > 1 ? `<span class="sk-help">동 묶음 ${b.ids.length}동</span>` : ""}
            ${b.ids.length ? "" : '<button type="button" class="link-btn cp-del">상자 빼기</button>'}</div>
          ${b.ids.length > 1 ? `<label class="cp-name"><span>묶음 이름 <em>표지·제출문</em></span><input class="cp-name-in" value="${esc(b.name)}" placeholder="비우면 ${esc(common(b.ids.map((i) => bld(i).name)))}" /></label>` : ""}
          ${multiCon && b.ids.length ? `<label class="cp-con"><span>연결 계약</span><select class="cp-con-in"><option value="">— 계약 없음 —</option>${d.contracts.map((c) =>
            `<option value="${c.id}"${b.contract_id === c.id ? " selected" : ""}>${esc(c.title)}${c.period ? ` · ${esc(c.period)}` : ""}</option>`).join("")}</select></label>` : ""}
          <div class="cp-drop">${b.ids.map(chip).join("") || '<span class="sk-help">비어 있음 — 건물을 끌어다 놓으세요</span>'}</div></div>`).join("")}
        <button type="button" class="cp-add">+ 보고서 추가</button></div>
      <div class="cp-foot"><span class="cp-msg mail-note"></span><button type="button" class="secondary cp-reset"${dirty ? "" : " disabled"}>되돌리기</button><button type="button" class="cp-save"${dirty ? "" : " disabled"}>저장</button></div>`;
    wire();
  }

  function move(id, k) {
    books.forEach((b) => { b.ids = b.ids.filter((x) => x !== id); });
    books[k].ids.push(id);
    picked = null;
    dirty = true;
    draw();
  }

  function wire() {
    box.querySelector(".cp-prev").addEventListener("click", () => shift(-1));
    box.querySelector(".cp-next").addEventListener("click", () => shift(1));
    box.querySelector(".cp-one").addEventListener("click", () => { books = [{ ids: d.buildings.map((b) => b.id), name: books.find((b) => b.ids.length > 1)?.name || "", contract_id: books[0]?.contract_id ?? null }]; dirty = true; draw(); });
    box.querySelector(".cp-each").addEventListener("click", () => { books = d.buildings.map((b) => ({ ids: [b.id], name: "", contract_id: (books.find((x) => x.ids.includes(b.id)) || {}).contract_id ?? null })); dirty = true; draw(); });
    box.querySelector(".cp-sug")?.addEventListener("click", () => { books = d.suggest.map((b) => ({ ...b, ids: b.ids.slice() })); dirty = true; draw(); });
    box.querySelector(".cp-add").addEventListener("click", () => { books.push({ ids: [], name: "", contract_id: null }); draw(); });
    box.querySelectorAll(".cp-del").forEach((b) => b.addEventListener("click", () => { books.splice(Number(b.closest(".cp-book").dataset.k), 1); draw(); }));
    box.querySelectorAll(".cp-name-in").forEach((i) => i.addEventListener("input", () => { books[Number(i.closest(".cp-book").dataset.k)].name = i.value; dirty = true; syncButtons(); }));
    box.querySelectorAll(".cp-con-in").forEach((s) => s.addEventListener("change", () => { books[Number(s.closest(".cp-book").dataset.k)].contract_id = s.value ? Number(s.value) : null; dirty = true; syncButtons(); }));
    box.querySelectorAll(".cp-chip").forEach((c) => {
      c.addEventListener("dragstart", (e) => { e.dataTransfer.setData("text/plain", c.dataset.id); e.dataTransfer.effectAllowed = "move"; c.classList.add("drag"); });
      c.addEventListener("dragend", () => c.classList.remove("drag"));
      c.addEventListener("click", (e) => { e.stopPropagation(); const id = Number(c.dataset.id); picked = picked === id ? null : id; draw(); });
    });
    box.querySelectorAll(".cp-book").forEach((bk) => {
      const k = Number(bk.dataset.k);
      bk.addEventListener("dragover", (e) => { e.preventDefault(); bk.classList.add("over"); });
      bk.addEventListener("dragleave", (e) => { if (!bk.contains(e.relatedTarget)) bk.classList.remove("over"); });
      bk.addEventListener("drop", (e) => { e.preventDefault(); bk.classList.remove("over"); const id = Number(e.dataTransfer.getData("text/plain")); if (id) move(id, k); });
      bk.addEventListener("click", (e) => { if (picked && !e.target.closest("select, input, button")) move(picked, k); });
    });
    box.querySelector(".cp-reset").addEventListener("click", () => { books = d.books.map((b) => ({ ...b, ids: b.ids.slice() })); dirty = false; picked = null; draw(); });
    box.querySelector(".cp-save").addEventListener("click", save);
  }
  function syncButtons() {
    box.querySelector(".cp-save").disabled = !dirty;
    box.querySelector(".cp-reset").disabled = !dirty;
  }

  function shift(n) {
    if (dirty && !confirm("저장하지 않은 구성이 있습니다 — 버리고 다른 반기로 갈까요?")) return;
    const i = cur.year * 2 + (cur.half === "하반기" ? 1 : 0) + n;
    cur = { year: Math.floor(i / 2), half: i % 2 ? "하반기" : "상반기" };
    load();
  }

  async function save() {
    const live = books.filter((b) => b.ids.length);
    const msg = box.querySelector(".cp-msg");
    if (d.contracts.length > 1 && live.some((b) => !b.contract_id) && !confirm("계약을 안 고른 보고서가 있습니다 — 그대로 저장할까요?")) return;
    const bookOf = (list, id) => list.findIndex((b) => b.ids.includes(id));
    const moved = d.buildings.filter((b) => b.round && b.round.data && JSON.stringify(d.books[bookOf(d.books, b.id)]?.ids) !== JSON.stringify(live[bookOf(live, b.id)]?.ids)).length; // 조사 내용 있는 건물의 상자가 바뀜
    if (moved && !confirm(`이 반기 현장 조사 내용이 있는 건물이 ${moved}개 있습니다. 조사 내용은 건물마다 그대로 남고 보고서 묶음만 바뀝니다. 저장할까요?`)) return;
    const btn = box.querySelector(".cp-save");
    btn.disabled = true;
    msg.textContent = "저장하는 중…";
    try {
      const out = await apiPost(`/sitok/facilities/${fid}/compose`, { year: cur.year, half: cur.half, books: live });
      d = out;
      books = d.books.map((b) => ({ ...b, ids: b.ids.slice() }));
      dirty = false;
      draw();
      box.querySelector(".cp-msg").innerHTML = `✓ 저장했습니다 — 보고서 ${books.length}권${(out.notes || []).length ? `<br>⚠ ${out.notes.map(esc).join("<br>⚠ ")}` : ""}`;
      window.dispatchEvent(new Event("sitok-group-changed"));
      setTimeout(() => location.reload(), 1600); // 번호·묶음이 바뀌어 위 칸들도 다시
    } catch (err) {
      msg.className = "cp-msg mail-note bad";
      msg.textContent = err.message;
      btn.disabled = false;
    }
  }

  load();
})();
