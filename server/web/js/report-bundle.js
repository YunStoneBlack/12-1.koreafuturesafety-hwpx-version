// ---------- 보고서 합본 창(2026-10-08 사용자 — server/api/routers/report_bundle.py) ----------
// [📚 보고서 합본 만들기]를 누르면 바로 만들지 않고 이 창: 회차 현황 → (시스템 첫 보고서가 1회차가 아니면) 그 전 회차 예전 보고서 올리기 →
// "1~15회차 합본을 만드시겠습니까?" [취소] [합본 만들기]. 예전 보고서는 파일 이름이 아니라 내용("총 ( )회차 중 ( N )회")으로 회차를 읽고,
// 못 읽으면 회차를 적게 함. 겹치는 회차는 시스템 보고서 우선. 창 틀은 css/mail.css(mail.js mailEsc), 이 창 규칙은 css/report-bundle.css.

const RB_KIND = {
  system: ["시스템", "rb-sys"], outdated: ["수정 전 버전", "rb-outdated"], old: ["올린 보고서", "rb-old"],
  nopdf: ["PDF 없음", "rb-nopdf"], missing: ["없음", "rb-missing"],
};

async function openReportBundle(siteId, siteName, onDone) {
  const overlay = document.createElement("div");
  overlay.className = "mail-overlay";
  overlay.innerHTML = '<div class="mail-box rb-box" role="dialog" aria-modal="true"><div class="mail-wait">불러오는 중…</div></div>';
  document.body.appendChild(overlay);
  const box = overlay.querySelector(".mail-box");
  let busy = false;
  const close = () => {
    if (busy) return;
    overlay.remove();
    document.removeEventListener("keydown", onKey);
  };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });

  let plan;
  try {
    plan = (await api(`/sites/${siteId}/report-bundle`)).plan;
  } catch (err) {
    box.innerHTML = `<div class="mail-msg bad">${mailEsc(err.message)}</div><div class="mail-foot"><button type="button" class="rb-close">닫기</button></div>`;
    box.querySelector(".rb-close").addEventListener("click", close);
    return;
  }
  let note = "";
  draw();

  function range(list) {
    return list.length ? (list.length === 1 ? `${list[0]}회차` : `${list[0]}~${list[list.length - 1]}회차`) : "";
  }

  function draw() {
    const rows = plan.rows;
    const first = plan.first_system;
    const hasOld = rows.some((r) => r.old) || plan.unknown.length;
    const needOld = (first && first > 1) || hasOld || !first;
    const gaps = rows.filter((r) => r.kind === "missing" || r.kind === "nopdf").map((r) => r.visit_no);
    const inc = plan.included;
    const chips = rows.map((r) => {
      const [text, cls] = RB_KIND[r.kind];
      return `<span class="rb-chip ${cls}" title="${r.visit_no}회차 — ${text}${r.old_title ? ` (${mailEsc(r.old_title)})` : ""}"><b>${r.visit_no}</b><small>${text}</small></span>`;
    }).join("");
    const oldRows = rows.filter((r) => r.old).map((r) => `<div class="rb-file">
        <a href="${BASE}/api/sites/${siteId}/report-bundle/old/${encodeURIComponent(r.old)}" target="_blank" rel="noopener">📄 ${r.visit_no}회차 · ${mailEsc(r.old_title)}</a>
        <span class="mail-note">${r.old_pages}쪽${r.old_hidden ? " · 시스템 보고서가 있어 이건 빠짐" : ""}</span>
        <button type="button" class="cd-x rb-del" data-name="${mailEsc(r.old)}" title="빼기">✕</button></div>`).join("");
    const unknownRows = plan.unknown.map((u) => `<div class="rb-file rb-unknown">
        <a href="${BASE}/api/sites/${siteId}/report-bundle/old/${encodeURIComponent(u.name)}" target="_blank" rel="noopener">📄 ${mailEsc(u.title)}</a>
        <span class="mail-note cd-bad">${u.pages}쪽 · 회차를 못 읽었습니다</span>
        <span class="rb-visit"><input type="number" min="1" inputmode="numeric" aria-label="회차" />회차 <button type="button" class="rb-set" data-name="${mailEsc(u.name)}">저장</button></span>
        <button type="button" class="cd-x rb-del" data-name="${mailEsc(u.name)}" title="빼기">✕</button></div>`).join("");
    box.innerHTML = `<div class="mail-head"><b>📚 보고서 합본</b><span class="mail-sub">${mailEsc(siteName || "")}</span></div>
      <div class="mail-label">회차 현황 <span class="mail-note">${plan.total_visits ? `— 기술지도 총 ${plan.total_visits}회` : ""}</span></div>
      ${rows.length ? `<div class="rb-grid">${chips}</div>` : '<div class="mail-note">아직 보고서가 없습니다.</div>'}
      ${needOld ? `
        ${first && first > 1 ? `<div class="mail-msg warn">이 현장은 <b>${first}회차</b>가 첫 보고서예요. <b>1~${first - 1}회차</b> 보고서를 올리면 같이 합칩니다.</div>` : ""}
        <div class="mail-label">예전 보고서 올리기 <span class="mail-note">— 파일 이름은 상관없어요. 보고서 안의 "총 ( )회차 중 ( N )회"를 읽어 회차를 정합니다(여러 회차를 합친 파일도 나눠 줌)</span></div>
        <label class="drop-box rb-drop"><span class="drop-ico">📎</span>
          <span class="drop-txt"><b class="drop-pc">예전 보고서 파일을 여기에 끌어다 놓으세요(여러 개 가능)</b><b class="drop-touch">눌러서 예전 보고서 고르기</b>
            <span class="drop-pc">눌러서 고를 수도 있어요 · PDF·한글·그림</span></span>
          <input type="file" multiple hidden data-kr-file="skip" accept=".pdf,.hwp,.hwpx,.jpg,.jpeg,.png,.docx,.doc,.xlsx,.xls" /></label>
        <div class="rb-files">${unknownRows}${oldRows}</div>` : ""}
      <div class="rb-msg-in">${note}</div>
      <div class="mail-foot rb-foot">
        <span class="rb-ask">${inc.length ? `<b>${range(inc)}</b> 합본을 만드시겠습니까?${gaps.length ? `<br><span class="cd-bad">빠지는 회차: ${gaps.join("·")}회차</span>` : ""}` : "합칠 보고서가 없습니다."}</span>
        <button type="button" class="rb-close">취소</button>
        <button type="button" class="mail-primary rb-go" ${inc.length ? "" : "disabled"}>합본 만들기</button></div>`;
    box.querySelector(".rb-close").addEventListener("click", close);
    box.querySelector(".rb-go").addEventListener("click", make);
    const input = box.querySelector(".rb-drop input");
    if (input) {
      enableFileDrop(box, () => box.querySelector(".rb-drop input")); // 창 어디에 놓아도(다시 그려도 지금 칸으로)
      input.addEventListener("change", () => upload([...input.files]));
    }
    box.querySelectorAll(".rb-del").forEach((b) => b.addEventListener("click", async () => {
      if (!confirm(`${b.dataset.name.replace(/^(\d+회차|미확인_\d+)_/, "")} 파일을 뺄까요?`)) return;
      try {
        plan = (await api(`/sites/${siteId}/report-bundle/old/${encodeURIComponent(b.dataset.name)}`, { method: "DELETE" })).plan;
        note = "";
        draw();
      } catch (err) { say(err.message, true); }
    }));
    box.querySelectorAll(".rb-set").forEach((b) => b.addEventListener("click", async () => {
      const n = Number(b.parentElement.querySelector("input").value);
      if (!n) { say("회차를 숫자로 적으세요.", true); return; }
      try {
        plan = (await apiPost(`/sites/${siteId}/report-bundle/old/${encodeURIComponent(b.dataset.name)}/visit`, { visit_no: n })).plan;
        note = "";
        draw();
      } catch (err) { say(err.message, true); }
    }));
  }

  function say(text, bad) {
    note = `<div class="mail-msg ${bad ? "bad" : "ok"}">${mailEsc(text)}</div>`;
    box.querySelector(".rb-msg-in").innerHTML = note;
  }

  async function upload(list) {
    if (!list.length) return;
    busy = true;
    const read = [], dup = [];
    let unknown = 0, failed = [];
    for (const [i, f] of list.entries()) {
      say(`올리는 중 ${list.length > 1 ? `${i + 1}/${list.length} ` : ""}— ${f.name}${/\.hwpx?$/i.test(f.name) ? " (한글 파일은 PDF로 바꾸느라 1분쯤 걸릴 수 있음)" : ""}`);
      try {
        const fd = new FormData();
        fd.append("file", f);
        const out = await apiUpload(`/sites/${siteId}/report-bundle/old`, fd);
        plan = out.plan;
        read.push(...out.read);
        dup.push(...out.dup_system);
        if (out.unknown) unknown++;
      } catch (err) {
        failed.push(`${f.name}: ${err.message}`);
      }
    }
    busy = false;
    const parts = [];
    if (read.length) parts.push(`✓ ${[...new Set(read)].sort((a, b) => a - b).join("·")}회차를 읽었습니다`);
    if (dup.length) parts.push(`${[...new Set(dup)].join("·")}회차는 시스템 보고서가 있어 그걸 씁니다`);
    if (unknown) parts.push(`회차를 못 읽은 파일 ${unknown}개 — 아래에서 회차를 적으세요`);
    if (failed.length) parts.push(`못 올린 파일: ${failed.join(" / ")}`);
    note = `<div class="mail-msg ${failed.length || unknown ? "warn" : "ok"}">${parts.map(mailEsc).join("<br>")}</div>`;
    draw();
  }

  async function make() {
    const btn = box.querySelector(".rb-go");
    busy = true;
    btn.disabled = true;
    let sec = 0;
    btn.textContent = "합치는 중…";
    const timer = setInterval(() => { btn.textContent = `합치는 중… ${++sec}초`; }, 1000);
    try {
      const out = await apiPost(`/sites/${siteId}/report-bundle`, {});
      busy = false;
      close();
      if (onDone) onDone(out);
    } catch (err) {
      busy = false;
      btn.disabled = false;
      btn.textContent = "합본 만들기";
      say(err.message, true);
    } finally {
      clearInterval(timer);
    }
  }
}
