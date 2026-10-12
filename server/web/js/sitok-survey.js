// 시특법 회차 [📝 면담·변경사항] 창(2026-10-11) — 1.2.7 보수·보강 이력(관리주체 면담으로 이번에 한 보수를 줄로 더함)과
// 1.2.8 변경사항 실태조사(변경 있는 항목만 체크해 입력, 나머지는 보고서에 "변경사항없음"). 서버 server/api/routers/sitok_reports.py /survey.
// 10/12: [🤖 건축물대장으로 초안] — 건축물대장 변동사항(준공 이후 전부)을 AI가 읽어 항목별로 채움(용도변경으로 활하중이 바뀌면 사용하중까지).
// 한 항목에 변동이 여러 건이면 칸 안에서 줄을 나눔(textarea, 보고서 칸에서도 줄 나눔).

async function openSitokSurvey(reportId, title, onSaved) {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const overlay = document.createElement("div");
  overlay.className = "mail-overlay";
  overlay.innerHTML = '<div class="mail-box ai-box" role="dialog" aria-modal="true"><div class="mail-wait">불러오는 중…</div></div>';
  document.body.appendChild(overlay);
  const box = overlay.querySelector(".mail-box");
  const close = () => overlay.remove();
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  let s;
  try { s = await api(`/sitok/reports/${reportId}/survey`); } catch (e) { box.innerHTML = `<div class="mail-msg bad">${esc(e.message)}</div>`; return; }
  const repRow = (x) => `<div class="sv-rep"><input data-f="period" value="${esc(x.period || s.period)}" placeholder="보수기간" />
    <input data-f="kind" value="${esc(x.kind || "보수공사")}" placeholder="공사종류" /><input data-f="method" value="${esc(x.method)}" placeholder="보수방안(예: 옥상 방수공사)" />
    <input data-f="where" value="${esc(x.where)}" placeholder="위치" /><input data-f="note" value="${esc(x.note)}" placeholder="비고" />
    <button type="button" class="sv-x" title="이 줄 지우기">✕</button></div>`;
  let group = "";
  const ta = (f, v, ph) => `<textarea data-f="${f}" rows="${Math.max(1, String(v || "").split("\n").length)}" placeholder="${ph}">${esc(v)}</textarea>`;
  const chRows = s.change_items.map((it) => {
    const c = s.changes[it.label] || {};
    const head = it.group !== group ? `<div class="sv-group">${esc(it.group || "변경사항")}</div>` : "";
    group = it.group;
    return `${head}<div class="sv-ch${c.after ? " on" : ""}" data-label="${esc(it.label)}"><label class="sv-chk"><input type="checkbox"${c.after ? " checked" : ""} /> ${esc(it.label)}</label>
      ${ta("before", c.before, "변경전")}${ta("after", c.after, "변경후")}${ta("where", c.where, "위치")}${ta("note", c.note, "비고")}</div>`;
  }).join("");
  box.innerHTML = `<div class="mail-head"><b>📝 면담·변경사항</b><span class="mail-sub">${esc(title)} — 보고서 1.2.7 보수·보강 이력, 1.2.8 변경사항 실태조사</span></div>
    <div class="ai-form">
      <h4>1.2.7 보수·보강 이력 <span class="sk-help">관리주체 면담 — 지난 회차 뒤에 한 보수만 더하면 됩니다(지난 이력은 그대로 남음)</span></h4>
      <div class="sv-old">${s.repairs_old.length ? s.repairs_old.map((r) => `<div>${r.map(esc).join(" · ")}</div>`).join("") : "지난 이력 없음"}</div>
      <div id="sv-reps">${s.repairs.map(repRow).join("")}</div>
      <button type="button" class="secondary btn-sm sv-add">+ 이번 보수 줄 더하기</button>
      <h4>1.2.8 변경사항 실태조사 <span class="sk-help">바뀐 것만 체크 — 나머지는 보고서에 "변경사항없음"</span></h4>
      ${chRows ? `<div class="sv-reg"><button type="button" class="secondary btn-sm sv-reg-ai">🤖 건축물대장으로 초안</button>
        <label class="secondary-link">${s.has_register ? "건축물대장 바꾸기" : "건축물대장 PDF 올리기"}<input type="file" accept="application/pdf,.pdf" hidden data-kr-file="1" class="sv-reg-file" /></label>
        <span class="sv-reg-msg">${s.has_register ? "올려 둔 건축물대장(시설물 현황과 같은 파일)의 변동사항 — 준공 이후 전부" : "변동사항이 있는 \"을\" 쪽까지 든 PDF를 올리면 바로 초안을 만듭니다"}</span></div>
        <div class="sv-events" hidden></div>` : ""}
      ${chRows || '<div class="sv-old">지난 보고서에 1.2.8 표가 없습니다.</div>'}
    </div>
    <div class="mail-msg" hidden></div>
    <div class="mail-foot"><button type="button" class="mail-cancel">닫기</button><button type="button" class="mail-primary sv-save">저장</button></div>`;
  const reps = box.querySelector("#sv-reps");
  const bindX = () => reps.querySelectorAll(".sv-x").forEach((b) => { b.onclick = () => b.closest(".sv-rep").remove(); });
  bindX();
  box.querySelector(".sv-add").addEventListener("click", () => { reps.insertAdjacentHTML("beforeend", repRow({})); bindX(); reps.lastElementChild.querySelector('[data-f="method"]').focus(); });
  const grow = (t) => { t.style.height = "auto"; t.style.height = `${t.scrollHeight + 2}px`; }; // 글이 접혀도(폰) 칸 높이가 따라감
  box.querySelectorAll(".sv-ch").forEach((row) => {
    const chk = row.querySelector("input[type=checkbox]");
    const tas = row.querySelectorAll("textarea");
    chk.addEventListener("change", () => {
      row.classList.toggle("on", chk.checked);
      if (chk.checked) { tas.forEach(grow); row.querySelector('[data-f="after"]').focus(); }
    });
    tas.forEach((t) => t.addEventListener("input", () => grow(t)));
    if (row.classList.contains("on")) tas.forEach(grow);
  });
  const regBtn = box.querySelector(".sv-reg-ai");
  const regFile = box.querySelector(".sv-reg-file");
  const regMsg = box.querySelector(".sv-reg-msg");
  const regDraft = async (file) => { // 건축물대장 변동사항 → 항목별로 채움(저장은 [저장]을 눌러야)
    const fd = new FormData();
    if (file) fd.append("file", file);
    regBtn.disabled = true;
    regMsg.textContent = "🤖 건축물대장 변동사항을 읽는 중…(30초~1분 30초)";
    try {
      const r = await apiUpload(`/sitok/reports/${reportId}/survey/changes/ai`, fd);
      let n = 0;
      for (const [label, c] of Object.entries(r.changes)) {
        const row = [...box.querySelectorAll(".sv-ch")].find((x) => x.dataset.label === label);
        if (!row) continue;
        row.classList.add("on");
        row.querySelector("input[type=checkbox]").checked = true;
        for (const f of ["before", "after", "where", "note"]) { const t = row.querySelector(`[data-f="${f}"]`); t.value = c[f] || ""; grow(t); }
        n += 1;
      }
      const used = r.events.filter((e) => e.kind !== "기재");
      regMsg.textContent = `변동사항 ${r.events.length}줄 읽음 — ${used.length}줄을 ${n}개 항목에 넣었습니다(건물이 안 바뀐 기재 ${r.events.length - used.length}줄은 뺌). 확인하고 [저장]`
        + (r.missing.length ? ` · 틀에 칸이 없어 못 넣은 것: ${r.missing.join(", ")}` : "");
      const ev = box.querySelector(".sv-events");
      ev.hidden = !r.events.length;
      ev.innerHTML = `<details><summary>읽은 변동사항 ${r.events.length}줄 보기</summary>${r.events.map((e) => `<div class="${e.kind === "기재" ? "skip" : ""}">
        <b>${esc(e.date)}</b> ${esc(e.kind)} · ${esc(e.where)} — ${esc(e.before ? `${e.before} → ${e.after}` : e.summary)}</div>`).join("")}</details>`;
      box.querySelector(".sv-reg label").firstChild.textContent = "건축물대장 바꾸기";
    } catch (e) { regMsg.textContent = e.message; }
    regBtn.disabled = false;
  };
  regBtn?.addEventListener("click", () => {
    if (!s.has_register && !regFile.files[0]) { regFile.click(); return; }
    regDraft(null);
  });
  regFile?.addEventListener("change", () => { if (regFile.files[0]) { s.has_register = true; regDraft(regFile.files[0]); } });
  box.querySelector(".mail-cancel").addEventListener("click", close);
  box.querySelector(".sv-save").addEventListener("click", async () => {
    const get = (row, f) => row.querySelector(`[data-f="${f}"]`).value.trim();
    const body = {
      repairs: [...reps.querySelectorAll(".sv-rep")].map((row) => ({ period: get(row, "period"), kind: get(row, "kind"), method: get(row, "method"), where: get(row, "where"), note: get(row, "note") })),
      changes: {},
    };
    box.querySelectorAll(".sv-ch.on").forEach((row) => {
      body.changes[row.dataset.label] = { before: get(row, "before"), after: get(row, "after") || "변경", where: get(row, "where"), note: get(row, "note") };
    });
    const msg = box.querySelector(".mail-msg");
    try {
      await api(`/sitok/reports/${reportId}/survey`, { method: "PUT", body: JSON.stringify(body) });
      msg.hidden = false; msg.className = "mail-msg ok"; msg.textContent = "저장했습니다 — [보고서 만들기]를 누르면 들어갑니다.";
      if (onSaved) onSaved();
    } catch (e) { msg.hidden = false; msg.className = "mail-msg bad"; msg.textContent = e.message; }
  });
}
