// 옹벽 전회차 가져오기 확인 창(sitok-field.html, 2026-10-20 사용자 제안) — 지난 보고서 부록 사진첩의 사진·설명을 AI가 부위·구분·부재·결함유형으로 추천,
// 점검자가 줄마다 확인(결함 / 상태양호 / 빼기)하고 [넣기]. 전경사진 6장은 전경사진 탭으로. 서버 server/api/routers/sitok_wall_import.py.
// sitok-field.js가 importing.state === "review"일 때 window.wallImport.show(rid)를 부름.

(function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const USES = [["defect", "결함"], ["good", "상태양호"], ["public", "공중이용"], ["skip", "빼기"]];

  async function show(rid) {
    const box = document.getElementById("sf-wall-review");
    if (!box) return;
    box.hidden = false;
    box.innerHTML = '<div class="page-sub">읽은 사진을 불러오는 중…</div>';
    let v;
    try { v = await api(`/sitok/reports/${rid}/defects/import/wall`); } catch (e) { box.innerHTML = `<div class="mail-msg bad">${esc(e.message)}</div>`; return; }
    const url = `${BASE}/api/sitok/reports/${rid}/defects/import/wall`;
    const sel = (cls, list, val, blank) => `<select class="${cls}">${blank ? '<option value="">— 없음 —</option>' : ""}${list.map((x) => `<option${x === val ? " selected" : ""}>${esc(x)}</option>`).join("")}</select>`;
    const typeList = (r) => (r.record || /현황\s*$/.test(r.dtype || "")) && !v.types.includes(r.dtype) ? [r.dtype, ...v.types] : v.types;
    box.innerHTML = `<h3 class="sf-h">전회차 사진 확인 — ${esc(v.facilities[v.picked] || "")} <span class="sk-help">${v.rows.length}장 · ${v.at}</span></h3>
      ${v.facilities.length > 1 ? `<label class="wi-fac">한 권에 시설물 ${v.facilities.length}곳 — 이 시설물의 장:
        <select class="wi-pick">${v.facilities.map((n, i) => `<option value="${i}"${i === v.picked ? " selected" : ""}>${i + 1}. ${esc(n)}</option>`).join("")}</select></label>` : ""}
      <p class="page-sub">🤖 설명 글을 보고 추천한 값입니다 — 틀리면 고치고, "~양호"·"~현황" 사진은 <b>상태양호</b>로(1.4 절 사진 칸), 펜스·점검로·도로포장은 <b>공중이용</b> 탭으로, 안 쓸 사진은 <b>빼기</b>.
        넣으면 모두 <b>전회차</b> 칸에 들어가고(결함 카드·전경·상태양호·공중이용) 현장에서 같은 자리를 이번에 찍습니다.</p>
      ${v.overview.length ? `<label class="wi-ov"><input type="checkbox" class="wi-ov-on" checked /> 전경사진 ${v.overview.length}장(${v.overview.map((o) => esc(o.caption)).join(" · ")})도 전경사진 탭에 넣기(제목은 설명대로)</label>` : ""}
      <div class="wi-list">${v.rows.map((r, i) => `<div class="wi-row${r.record ? " rec" : ""}" data-i="${i}">
        <img src="${url}/photo?f=${encodeURIComponent(r.file)}" alt="" loading="lazy" />
        <div class="wi-cap"><b>${esc(r.caption)}</b><small>${r.page}쪽</small></div>
        <div class="wi-fields">
          <label>넣기${sel("wi-use", USES.map((x) => x[1]), r.public ? "공중이용" : r.record ? "상태양호" : "결함")}</label>
          <label class="wi-pub">공중이용 항목<select class="wi-public">${(v.public_items || []).map(([k, n]) => `<option value="${k}"${k === (r.public || "fall") ? " selected" : ""}>${esc(n)}</option>`).join("")}</select></label>
          <label>부위${sel("wi-unit", v.units, r.unit)}</label>
          <label>구분${sel("wi-part", v.parts, r.part)}</label>
          <label>부재${sel("wi-member", v.members, r.member, true)}</label>
          <label>결함유형${sel("wi-dtype", typeList(r), r.dtype, true)}</label>
          <label>폭(mm)<input class="wi-width" inputmode="decimal" value="${esc(r.width)}" /></label>
        </div></div>`).join("")}</div>
      <div class="mail-msg wi-msg" hidden></div>
      <div class="wi-foot"><button type="button" class="secondary wi-cancel">취소(다시 올리기)</button><button type="button" class="wi-ok">넣기</button></div>`;
    const say = (t, bad) => { const m = box.querySelector(".wi-msg"); m.hidden = !t; m.className = `mail-msg wi-msg ${bad ? "bad" : "ok"}`; m.textContent = t || ""; };
    box.querySelectorAll(".wi-row").forEach((row) => {
      const q = (s) => row.querySelector(s);
      const sync = () => { // 넣기가 상태양호·빼기면 결함 칸은 흐리게, 공중이용이면 항목 고르기만
        const use = USES.find((x) => x[1] === q(".wi-use").value)[0];
        row.classList.toggle("dim", use !== "defect");
        row.classList.toggle("rec", use === "good" || use === "public");
        q(".wi-pub").hidden = use !== "public";
      };
      sync();
      q(".wi-use").addEventListener("change", sync);
      q(".wi-unit").addEventListener("change", () => { const p = v.unit_part[q(".wi-unit").value]; if (p) q(".wi-part").value = p; });
      q(".wi-member").addEventListener("change", () => { const p = v.part_of[q(".wi-member").value]; if (p) q(".wi-part").value = p; });
      q("img").addEventListener("click", (e) => window.open(e.target.src, "_blank"));
    });
    box.querySelector(".wi-pick")?.addEventListener("change", async (e) => {
      say("그 장을 읽는 중(AI 분류 10~30초)…");
      try { await apiPost(`/sitok/reports/${rid}/defects/import/wall/pick`, { idx: Number(e.target.value) }); show(rid); } catch (err) { say(err.message, true); }
    });
    box.querySelector(".wi-cancel").addEventListener("click", async () => {
      if (!confirm("읽은 사진을 버리고 가져오기 화면으로 돌아갈까요?")) return;
      try { await api(`/sitok/reports/${rid}/defects/import/wall`, { method: "DELETE" }); location.reload(); } catch (e) { say(e.message, true); }
    });
    box.querySelector(".wi-ok").addEventListener("click", async (e) => {
      const rows = [...box.querySelectorAll(".wi-row")].map((row) => {
        const q = (s) => row.querySelector(s);
        return { i: Number(row.dataset.i), use: USES.find((x) => x[1] === q(".wi-use").value)[0], unit: q(".wi-unit").value, part: q(".wi-part").value,
          member: q(".wi-member").value, dtype: q(".wi-dtype").value, width: q(".wi-width").value.trim(), public: q(".wi-public").value };
      });
      const bad = rows.filter((r) => r.use === "defect" && !r.dtype);
      if (bad.length) { say(`결함유형이 빈 줄 ${bad.length}개 — 고르거나 "빼기"로`, true); return; }
      const ovOn = box.querySelector(".wi-ov-on");
      e.target.disabled = true;
      say("넣는 중…");
      try {
        const r = await apiPost(`/sitok/reports/${rid}/defects/import/wall/confirm`, { rows, overview: !!(ovOn && ovOn.checked) });
        const m = r.imported;
        alert(`넣었습니다 — 결함 ${m.defects}개, 상태양호 ${m.good}장${m.public ? `, 공중이용 ${m.public}장` : ""}, 뺌 ${m.skipped}개${m.overview ? `, 전경사진 ${m.overview}장` : ""}(전경·상태양호·공중이용은 전회차 칸 — 탭에서 이번 사진을 찍으세요).`);
        location.reload();
      } catch (err) { e.target.disabled = false; say(err.message, true); }
    });
  }

  window.wallImport = { show };
})();
