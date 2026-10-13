// 시특법 정밀안전점검 ④(sitok-field.html, 2026-10-13) — 정밀 회차만: [📋 자료수집](2.2 자료 보관·2.3.2 내진·2.3.4 사용·관리실태 면담·점검이력·전차 점검 검토),
// [⚖ 하중상태](3.2.6 사진 4장·결과), 공중이용·기타시설 탭 위 등급 칸(3.2.7~8, 표 6.44~6.47). 서버 server/api/routers/sitok_precision.py. 고치는 대로 저장.

(function () {
  const rid = Number(new URLSearchParams(location.search).get("report")) || null;
  if (!rid) return;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const $ = (id) => document.getElementById(id);
  const url = `/sitok/reports/${rid}/precision`;
  let data = null;
  let ts = Date.now();
  let timer = null;

  function saved(text, bad) {
    clearTimeout(timer);
    const el = $("pr-saved");
    el.textContent = text;
    el.className = `st-saved${bad ? " bad" : ""}`;
    if (!bad) timer = setTimeout(() => { el.textContent = ""; }, 2500);
  }
  async function put(body) {
    saved("저장 중…");
    try { data = await api(url, { method: "PUT", body: JSON.stringify(body) }); draw(); saved("✓ 저장됨"); } catch (e) { saved(`저장 실패: ${e.message}`, true); }
  }
  const seg = (options, value, attrs, badValues = []) => `<span class="pr-seg" ${attrs}>${options.map((o) =>
    `<button type="button" data-v="${esc(o)}" class="${o === value ? "on" : ""}${badValues.includes(o) ? " bad" : ""}">${esc(o)}</button>`).join("")}</span>`;

  // ---- 자료수집 탭 ----
  function drawDocs() {
    const d = data;
    const groups = [];
    d.docs.forEach((it) => { if (!groups.includes(it.group)) groups.push(it.group); });
    const docRows = d.docs.map((it) => `<tr><td class="g">${esc(it.group)}</td><td>${esc(it.name)}</td>
      <td>${seg(d.doc_status, it.status, `data-doc="${it.key}"`, ["미보유"])}</td>
      <td><input data-docnote="${it.key}" value="${esc(it.note)}" placeholder="자료수집 결과(예: 시설물관리대장·컴퓨터 파일 확보)" /></td></tr>`).join("");
    const m = d.manage;
    const checks = d.checklist.map((name, i) => `<label class="${m.checklist[String(i)] ? "bad" : ""}"><input type="checkbox" data-chk="${i}"${m.checklist[String(i)] ? " checked" : ""} /> ${esc(name)}</label>`).join("");
    const hist = d.history.length ? d.history : d.history_auto;
    const histRows = hist.map((h, i) => `<tr><td>${i + 1}</td><td>${esc(h.kind)}</td><td class="g">${esc(h.start)}~${esc(h.end)}</td><td>${esc(h.org)}</td><td>${esc(h.grade || "-")}</td>
      <td style="white-space:pre-wrap">${esc((h.result || "").slice(0, 300))}</td></tr>`).join("");
    const pa = d.prev_auto;
    $("pr-docs").innerHTML = `
      <div class="pr-sec"><h3>2.2 자료수집 목록</h3><p class="page-sub">관리주체에게 받은 자료 — 보관 여부와 수집 결과(표 2.1)</p>
        <div class="pr-tbl"><table><thead><tr><th>구분</th><th>자료</th><th>보관 유무</th><th>자료수집 결과</th></tr></thead><tbody>${docRows}</tbody></table></div></div>
      <div class="pr-sec"><h3>2.3.2 내진설계 및 보강 여부</h3>
        ${seg(d.seismic_options, d.seismic.status, 'data-seismic="1"', ["미적용"])}
        <label class="pr-note">검토 내용 <input id="pr-seismic-note" value="${esc(d.seismic.note)}" placeholder="예: 구조계산서·시설물관리대장 검토 결과 내진설계가 미반영되어 있는 것으로 확인됨" /></label></div>
      <div class="pr-sec"><h3>2.3.4 건축물 사용 및 관리실태</h3>
        <div class="pr-tbl"><table><tbody>
          <tr><td>1) 용도변경</td><td>${seg(d.ynu, m.use_change, 'data-manage="use_change"', ["유"])}</td></tr>
          <tr><td>2) 구조변경</td><td>${seg(d.ynu, m.struct_change, 'data-manage="struct_change"', ["유"])}</td></tr>
          <tr><td>3) 주변조건의 변경(사용하중·기초 및 지반·주변 환경)</td><td>${seg(d.ynu, m.surround_change, 'data-manage="surround_change"', ["유"])}</td></tr></tbody></table></div>
        <p class="page-sub" style="margin-top:10px">4) 부대 점검사항 — 유지관리자 면담·확인. <b>있다(불량)</b>인 것만 체크, 나머지는 "없다(양호)"로 들어갑니다.</p>
        <div class="pr-check">${checks}</div>
        <label class="pr-note">비고(위치·상태·조치내용) <textarea id="pr-manage-note" rows="2">${esc(m.note)}</textarea></label></div>
      <div class="pr-sec"><h3>2.3.1 점검이력</h3>
        <div class="pr-hist-top"><label class="sk-drop pr-fms"><input type="file" accept=".xlsx,.xlsm" hidden data-kr-file="1" id="pr-fms" />
            <b>📊 FMS 점검진단실적 엑셀 올리기</b><span class="sk-drop-msg" id="pr-fms-msg">시설물정보관리종합시스템에서 받은 점검진단실적(.xlsx) — 번호·구분·기간·기관·등급·주요결과</span></label>
          ${d.history.length ? `<span class="page-sub">📎 올린 실적 ${d.history.length}건 <button type="button" class="secondary btn-sm" id="pr-fms-del">빼기</button></span>` : `<span class="page-sub">${d.history_auto.length ? `우리 지난 회차 ${d.history_auto.length}건 자동` : "지난 회차 없음"}</span>`}</div>
        <div class="pr-tbl"><table class="hist"><thead><tr><th>번호</th><th>점검명</th><th>점검기간</th><th>점검기관</th><th>등급</th><th>주요 점검 결과</th></tr></thead><tbody>${histRows || '<tr><td colspan="6" class="g">없음</td></tr>'}</tbody></table></div></div>
      <div class="pr-sec"><h3>2.3.4 전차 점검 보고서 검토</h3>
        ${pa ? `<div class="pr-prev">자동: ${pa.year}년 ${pa.half} ${esc(pa.kind)} (${esc(pa.grade || "-")}등급)<ul>${pa.lines.map((l) => `<li>${esc(l)}</li>`).join("")}</ul></div>` : '<p class="page-sub">우리 지난 회차 AI 초안이 없어 자동 요약이 없습니다 — 아래에 직접 쓰거나, 첫 정밀이면 "준공 후 첫 회차"라고 적으세요.</p>'}
        <label class="pr-note">요약(비우면 자동 요약을 씀) <textarea id="pr-prev-text" rows="4" placeholder="※ 2022년 5월 31일 준공으로 이번 회차가 첫 회차 정밀안전점검임.">${esc(d.prev_review.text)}</textarea></label></div>`;
    const docs = () => Object.fromEntries(d.docs.map((it) => [it.key, { status: it.status, note: it.note }]));
    $("pr-docs").querySelectorAll("[data-doc] button").forEach((b) => b.addEventListener("click", () => {
      const key = b.closest("[data-doc]").dataset.doc;
      const it = d.docs.find((x) => x.key === key);
      it.status = it.status === b.dataset.v ? "" : b.dataset.v;
      put({ docs: docs() });
    }));
    $("pr-docs").querySelectorAll("[data-docnote]").forEach((inp) => inp.addEventListener("change", () => {
      d.docs.find((x) => x.key === inp.dataset.docnote).note = inp.value;
      put({ docs: docs() });
    }));
    $("pr-docs").querySelectorAll("[data-seismic] button").forEach((b) => b.addEventListener("click", () => put({ seismic: { status: b.dataset.v, note: $("pr-seismic-note").value } })));
    $("pr-seismic-note").addEventListener("change", () => put({ seismic: { status: d.seismic.status, note: $("pr-seismic-note").value } }));
    const manage = () => ({ ...m, checklist: Object.fromEntries([...$("pr-docs").querySelectorAll("[data-chk]")].filter((c) => c.checked).map((c) => [c.dataset.chk, true])), note: $("pr-manage-note").value });
    $("pr-docs").querySelectorAll("[data-manage] button").forEach((b) => b.addEventListener("click", () => { m[b.closest("[data-manage]").dataset.manage] = b.dataset.v; put({ manage: manage() }); }));
    $("pr-docs").querySelectorAll("[data-chk]").forEach((c) => c.addEventListener("change", () => put({ manage: manage() })));
    $("pr-manage-note").addEventListener("change", () => put({ manage: manage() }));
    $("pr-prev-text").addEventListener("change", (e) => put({ prev_review: { text: e.target.value } }));
    const fms = $("pr-fms");
    fms.addEventListener("change", async () => {
      const f = fms.files[0];
      fms.value = "";
      if (!f) return;
      $("pr-fms-msg").textContent = `${f.name} 읽는 중…`;
      try {
        const fd = new FormData();
        fd.append("file", f);
        data = await apiUpload(`${url}/fms`, fd);
        draw();
      } catch (e) { $("pr-fms-msg").textContent = `읽지 못했습니다: ${e.message}`; }
    });
    enableFileDrop(document.querySelector(".pr-fms"), fms);
    $("pr-fms-del")?.addEventListener("click", async () => {
      if (!confirm("올린 점검진단실적을 뺄까요?")) return;
      try { data = await api(`${url}/fms`, { method: "DELETE" }); draw(); } catch (e) { saved(e.message, true); }
    });
    const filled = d.docs.filter((x) => x.status).length;
    $("pr-docs-count").textContent = filled ? `(${filled}/${d.docs.length})` : "";
  }

  // ---- 하중상태 탭 ----
  function drawLoad() {
    const lo = data.load;
    const src = (slot) => `${BASE}/api${url}/load-photo?slot=${slot}&t=${ts}`;
    $("pr-load").innerHTML = `<div class="pr-load">${lo.photos.map((p) => `<div class="pt-card" data-slot="${p.slot}">
        <div class="pt-name">사진 ${p.slot + 1}<span>${p.has ? "✓ 사진" : "아직"}</span></div>
        <input data-title="${p.slot}" value="${esc(p.title)}" placeholder="제목(예: 옥상 사용하중 현황)" />
        ${p.has ? `<img src="${src(p.slot)}" alt="" loading="lazy" />` : '<div class="pt-blank">사진 없음</div>'}
        <div class="pt-acts"><label class="ov-shot pt-shot">📷 ${p.has ? "다시 찍기" : "찍기"}<input type="file" accept="image/*" capture="environment" hidden data-kr-file="1" /></label>
          <label class="ov-shot secondary pt-shot">🖼 고르기<input type="file" accept="image/*" hidden data-kr-file="1" /></label>
          ${p.has ? '<button type="button" class="pt-del">지우기</button>' : ""}</div></div>`).join("")}</div>
      <label class="pr-note" style="margin-top:12px">조사 결과(3.2.6 본문) <textarea id="pr-load-note" rows="2" placeholder="${esc(lo.default_note)}">${esc(lo.note)}</textarea></label>`;
    const titles = () => [...$("pr-load").querySelectorAll("[data-title]")].map((i) => i.value);
    $("pr-load").querySelectorAll("[data-title]").forEach((inp) => inp.addEventListener("change", () => put({ load: { titles: titles(), note: $("pr-load-note").value } })));
    $("pr-load-note").addEventListener("change", () => put({ load: { titles: titles(), note: $("pr-load-note").value } }));
    $("pr-load").querySelectorAll(".pt-card").forEach((el) => {
      const slot = el.dataset.slot;
      el.querySelectorAll(".pt-shot input").forEach((inp) => inp.addEventListener("change", async () => {
        if (!inp.files[0]) return;
        el.classList.add("busy");
        const fd = new FormData();
        fd.append("slot", slot);
        fd.append("file", inp.files[0]);
        try { data = await apiUpload(`${url}/load-photo`, fd); ts = Date.now(); draw(); } catch (e) { saved(e.message, true); el.classList.remove("busy"); }
      }));
      el.querySelector(".pt-del")?.addEventListener("click", async () => {
        if (!confirm("이 사진을 지울까요?")) return;
        try { data = await api(`${url}/load-photo?slot=${slot}`, { method: "DELETE" }); draw(); } catch (e) { saved(e.message, true); }
      });
      el.querySelector("img")?.addEventListener("click", (e) => window.open(e.target.src, "_blank"));
    });
    const n = lo.photos.filter((p) => p.has).length;
    $("pr-load-count").textContent = n ? `(${n}/4)` : "";
  }

  // ---- 공중이용·기타시설 등급 ----
  function drawGrades() {
    for (const [group, id, title] of [["public", "pr-grade-public", "3.2.7 공중이 이용하는 부위 — 항목마다 상태평가 등급(표 6.44~6.47)"], ["other", "pr-grade-other", "3.2.8 기타시설 — 등급"]]) {
      const box = $(id);
      box.hidden = false;
      box.innerHTML = `<div class="pr-grades-head">${esc(title)} — 정밀안전점검만. 사진은 아래 칸에.</div>` + data.grades[group].map((g) => `<div class="pr-grade"><b>${esc(g.name)}</b>
        ${seg(["a", "b", "c", "d", "e"], g.grade, `data-grade="${group}:${g.key}"`, ["d", "e"])}<div class="crit">${esc(g.criteria)}</div></div>`).join("");
      box.querySelectorAll("[data-grade] button").forEach((b) => b.addEventListener("click", async () => {
        const [grp, key] = b.closest("[data-grade]").dataset.grade.split(":");
        const cur = data.grades[grp].find((x) => x.key === key);
        try { data.grades = await apiPost(`${url}/grade`, { group: grp, key, grade: cur.grade === b.dataset.v ? "" : b.dataset.v }); drawGrades(); } catch (e) { saved(e.message, true); }
      }));
    }
  }

  function draw() {
    drawDocs();
    drawLoad();
    drawGrades();
  }

  api(url).then((d) => {
    data = d;
    if ((d.report.kind || "정기") !== "정밀") return; // 정기 회차엔 탭·등급 칸 없음
    document.querySelectorAll(".sf-tab-pre").forEach((b) => { b.hidden = false; });
    draw();
  }).catch(() => { /* 정기 회차·오류면 조용히 */ });
})();
