// 시특법 정밀안전점검 상태평가(sitok-rating.html, 2026-10-13 ③ 단계) — 표본층별 부재 전체 개수 입력 → 결과(갑지 모양) → 근거.
// 서버 GET/PATCH /sitok/reports/{id}/rating(집계 server/sitok/condition.py, 계산 rating.py — SafetyMan과 맞춤).

(function () {
  const rid = Number(new URLSearchParams(location.search).get("report")) || null;
  const errorEl = document.getElementById("error");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const err = (e) => showError(errorEl, e);
  const $ = (id) => document.getElementById(id);
  const grade = (g) => (g ? `<span class="st-grade ${g.toLowerCase()}">${g.toUpperCase()}</span>` : "-");
  const f2 = (x) => (x === null || x === undefined ? "-" : Number(x).toFixed(2));
  let view = null;
  let timer = null;

  async function save(body) {
    clearTimeout(timer);
    const saved = $("sr-saved");
    saved.textContent = "저장 중…";
    saved.className = "st-saved";
    try {
      view = await apiPatch(`/sitok/reports/${rid}/rating`, body);
      draw();
      saved.textContent = "✓ 저장됨";
      timer = setTimeout(() => { saved.textContent = ""; }, 2500);
    } catch (e) { saved.textContent = `저장 실패: ${e.message}`; saved.className = "st-saved bad"; }
  }

  function drawCounts() {
    const fl = view.sample_floors;
    const warn = $("sr-warn");
    if (!fl.length) {
      warn.hidden = false;
      warn.innerHTML = `표본층이 없습니다 — 먼저 <a href="sitok-tests.html?report=${rid}">📐 재료시험</a>에서 표본층을 고르세요.`;
    } else { warn.hidden = true; }
    const rows = fl.map((f) => `<tr><td class="l"><b>${esc(f.label)}</b><br><small>${esc(f.range_label)}</small></td>
      ${view.members.map((m) => `<td><input class="n" inputmode="numeric" data-f="${f.floor}" data-m="${esc(m)}" value="${esc((view.counts[String(f.floor)] || {})[m] || "")}" /></td>`).join("")}</tr>`).join("");
    $("sr-counts-tbl").innerHTML = fl.length ? `<table><thead><tr><th>표본층</th>${view.members.map((m) => `<th>${esc(m)}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table>` : "";
    $("sr-counts-note").textContent = view.carried ? `지난 정밀 회차(${view.prev_report.year}년 ${view.prev_report.half})에서 가져온 개수 — 그대로 쓰면 저장됩니다` : "";
    $("sr-counts-tbl").querySelectorAll("input").forEach((inp) => inp.addEventListener("change", () => {
      const counts = JSON.parse(JSON.stringify(view.counts));
      const key = String(inp.dataset.f);
      counts[key] = counts[key] || {};
      counts[key][inp.dataset.m] = inp.value.trim() === "" ? 0 : Number(inp.value);
      save({ counts });
    }));
    const prev = $("sr-prev");
    prev.innerHTML = `<label>전차 점검 등급(5.2.1 비교)
        <select id="sr-prev-grade"><option value="">${view.prev_auto ? `지난 회차 자동: ${view.prev_auto}` : "없음(처음)"}</option>${["A", "B", "C", "D", "E"].map((g) => `<option${view.prev_grade === g ? " selected" : ""}>${g}</option>`).join("")}</select></label>
      <label>메모<input id="sr-note" value="${esc(view.note)}" placeholder="예: 바닥마감 시공오차로 부동침하 c" /></label>`;
    $("sr-prev-grade").addEventListener("change", (e) => save({ prev_grade: e.target.value }));
    $("sr-note").addEventListener("change", (e) => save({ note: e.target.value }));
  }

  // 강재 접합·부식 개수(10/15 형 "SafetyMan과 100% 일치") — 부록 결과자료의 용접접합상태·볼트접합상태·강재부식도 표에만, 점수엔 안 들어감(정밀점검은 강재 규격만)
  const WELD = [["a", "매우양호(결함없음)"], ["b", "전반적양호(국부적 미세결함)"], ["c", "보통(부분적 결함)"], ["d", "내력저하 우려(광범위한 결함)"], ["e", "매우불량(내력저하 심각)"]];
  const CORR = [["a", "부식 거의 없음(양호)"], ["b", "판두께 감소 5% 이내"], ["c", "판두께 감소 10% 이내"], ["d", "판두께 감소 15% 이내"], ["e", "판두께 감소 15% 이상"]];
  function drawJoints() {
    const box = $("sr-joints");
    const fl = view.steel_floors || [];
    box.hidden = !fl.length;
    if (!fl.length) { box.innerHTML = ""; return; }
    const val = (f, m, k) => ((view.joints[String(f)] || {})[m] || {})[k];
    const num = (f, m, k) => `<input class="n" inputmode="numeric" data-f="${f}" data-m="${esc(m)}" data-k="${k}" value="${esc(val(f, m, k) || "")}" />`;
    const sel = (f, m, k, opts) => `<select data-f="${f}" data-m="${esc(m)}" data-k="${k}">${opts.map(([g, t]) => `<option value="${g}"${(val(f, m, k) || "a") === g ? " selected" : ""}>${g.toUpperCase()} ${esc(t)}</option>`).join("")}</select>`;
    box.innerHTML = `<h3>강재 접합·부식 개수 <small class="page-sub">부록 결과자료(SafetyMan 표)의 용접·볼트·부식 칸에만 들어가고 점수엔 안 들어갑니다(정밀점검은 강재 규격만). 빈칸 = 표에 비움</small></h3>
      ${fl.map((f) => `<div class="sr-jfloor"><b>${esc(f.label)}</b> <small>${esc(f.range_label)} · ${f.material === "SRC" ? "철골철근콘크리트(강재 쪽)" : "철골조"}</small>
        <div class="st-tbl"><table><thead><tr><th rowspan="2">부재</th><th colspan="2">용접접합</th><th colspan="2">볼트접합</th><th colspan="2">강재부식</th></tr>
          <tr><th>개수</th><th>상태</th><th>불량</th><th>전체</th><th>개수</th><th>상태</th></tr></thead>
          <tbody>${view.joint_members.map((m) => `<tr><td class="l">${esc(m)}</td><td>${num(f.floor, m, "weld_n")}</td><td>${sel(f.floor, m, "weld_g", WELD)}</td>
            <td>${num(f.floor, m, "bolt_bad")}</td><td>${num(f.floor, m, "bolt_n")}</td><td>${num(f.floor, m, "corr_n")}</td><td>${sel(f.floor, m, "corr_g", CORR)}</td></tr>`).join("")}</tbody></table></div></div>`).join("")}`;
    box.querySelectorAll("input, select").forEach((el) => el.addEventListener("change", () => {
      const joints = {};
      box.querySelectorAll("[data-k]").forEach((x) => {
        const f = String(x.dataset.f), m = x.dataset.m;
        joints[f] = joints[f] || {};
        joints[f][m] = joints[f][m] || {};
        joints[f][m][x.dataset.k] = x.tagName === "SELECT" ? x.value : (x.value.trim() === "" ? 0 : Number(x.value));
      });
      save({ joints });
    }));
  }

  function drawResult() {
    const r = view.result;
    const note = $("sr-result-note");
    if (!r) {
      $("sr-result-tbl").innerHTML = '<p class="page-sub">평가할 부재가 아직 없습니다 — 표본층을 고르고 부재 개수를 넣으세요.</p>';
      $("sr-final").innerHTML = "";
      note.textContent = "";
      $("sr-pdf").hidden = true;
      return;
    }
    const rows = r.floors.map((fl) => {
      const sc = Object.fromEntries(fl.members.map((m) => [m.kind, m.condition]));
      return `<tr><td class="l"><b>${esc(fl.label)}</b><br><small>${esc(fl.structure)}</small></td><td>상태</td>
        ${view.members.map((m) => `<td class="score${sc[m] === null || sc[m] === undefined ? " skip" : ""}">${sc[m] === null || sc[m] === undefined ? "-" : Number(sc[m]).toFixed(2)}</td>`).join("")}
        <td class="total">${f2(fl.condition)}${fl.condition !== null ? `(${gradeOf(fl.condition)})` : ""}</td></tr>`;
    }).join("");
    $("sr-result-tbl").innerHTML = `<table><thead><tr><th>층</th><th></th>${view.members.map((m) => `<th>${esc(m)}</th>`).join("")}<th>종합</th></tr></thead><tbody>${rows}</tbody></table>`;
    const d = r.deform;
    $("sr-final").innerHTML = `<span>상태평가 <b>${f2(r.condition?.score)}</b> ${grade(r.condition?.grade)}</span>
      <span>기울기 및 침하 <b>${d ? f2(d.score) : "-"}</b> ${grade(d?.grade)} <small class="page-sub">(기울기 ${(view.deform.tilt || "-").toUpperCase()} · 부동침하 ${(view.deform.settlement || "-").toUpperCase()})</small></span>
      <span>종합평가 <b>${f2(r.total?.score)}</b> ${grade(r.total?.grade)}</span>
      ${view.prev_grade || view.prev_auto ? `<span class="page-sub">전차 점검 ${esc(view.prev_grade || view.prev_auto)} → 이번 ${esc(r.total?.grade || "-")}</span>` : ""}`;
    note.textContent = `종합 ${r.total?.grade || "-"}등급`;
    $("sr-pdf").hidden = false;
    $("sr-pdf").href = `${BASE}/api/sitok/reports/${rid}/rating/pdf?v=${Date.now()}`;
  }
  const gradeOf = (x) => (x < 2 ? "A" : x < 4 ? "B" : x < 6 ? "C" : x < 8 ? "D" : "E");

  function itemBox(label, g, body) {
    return `<div class="sr-item"><b>${esc(label)} ${grade(g)}</b>${body}</div>`;
  }
  const countsText = (c) => ["a", "b", "c", "d", "e"].map((g) => `${g.toUpperCase()} ${c[g] || 0}`).join(" · ");
  const defectList = (ds) => (ds.length ? `<ul class="sr-defects">${ds.map((d) => `<li>${esc(d.floor)} ${d.seq}번 ${esc(d.member)} ${esc(d.dtype)} ×${d.n} → ${d.grade.toUpperCase()} <small>(${esc(d.why)})</small></li>`).join("")}</ul>` : "");

  function drawDetail() {
    const L = view.labels;
    const html = view.floors.map((fl) => {
      const members = fl.members.filter((m) => !m.skip).map((m) => {
        const it = m.items;
        const boxes = [];
        if (it.DS) boxes.push(itemBox("콘크리트 강도", it.DS.grade, `<span class="cnt">${it.DS.rows.map((r) => `${esc(r.member)} ${r.est}/${r.design} → ${r.grade.toUpperCase()}`).join(", ")}</span>`));
        if (it.CA) boxes.push(itemBox("콘크리트 중성화", it.CA.grade, `<span class="cnt">${it.CA.rows.map((r) => `${esc(r.member)} ${r.depth}/${r.cover}mm → ${r.grade.toUpperCase()}`).join(", ")}</span>`));
        if (it.CR) boxes.push(itemBox(`균열 (전체 ${it.CR.total})`, it.CR.grade, `<span class="cnt">${countsText(it.CR.counts)}</span>${defectList(it.CR.defects)}`));
        if (it.SD) boxes.push(itemBox(`표면노후 (전체 ${it.SD.total})`, it.SD.grade, Object.entries(it.SD.sub).map(([k, s]) =>
          `<div><small>${esc(L.surface[k])} ${grade(s.grade)} <span class="cnt">${countsText(s.counts)}</span></small>${defectList(s.defects)}</div>`).join("")));
        const poss = m.possibility ? Object.entries(m.possibility).map(([g, p]) => `${g.toUpperCase()} ${Number(p).toFixed(2)}`).join(" · ") : "";
        return `<div class="sr-member"><h4>${esc(m.kind)} → <b>${m.score === null ? "-" : Number(m.score).toFixed(1)}</b> ${grade(m.score === null ? "" : gradeOf(m.score))}
            <span class="sr-poss">가능성 ${poss}</span></h4><div class="sr-items">${boxes.join("")}</div></div>`;
      }).join("");
      const skipped = fl.members.filter((m) => m.skip).map((m) => m.kind);
      return `<details class="sr-floor" open><summary>${esc(fl.label)} <small>${esc(fl.range_label)} · ${esc(fl.structure)}(${esc(fl.material)})</small>
          ${skipped.length ? `<small class="page-sub">평가 제외(개수·시험 없음): ${esc(skipped.join(", "))}</small>` : ""}</summary>
        <div class="sr-body">${members || '<p class="page-sub">평가할 부재가 없습니다 — 위에서 부재 개수를 넣으세요.</p>'}</div></details>`;
    }).join("");
    const ex = view.excluded, un = view.unassigned;
    const exHtml = `${ex.length ? `<details class="sr-ex"><summary>상태평가에 안 넣은 결함 ${ex.length}건(비구조체·마감층 균열·기타)</summary><ul>${ex.map((d) => `<li>${esc(d.floor)} ${d.seq}번 ${esc(d.part)} ${esc(d.member)} ${esc(d.dtype)} — ${esc(d.why)}</li>`).join("")}</ul></details>` : ""}
      ${un.length ? `<details class="sr-ex" open><summary>⚠ 표본층에 못 넣은 구조 결함 ${un.length}건</summary><ul>${un.map((d) => `<li>${esc(d.floor)} ${d.seq}번 ${esc(d.member)} ${esc(d.dtype)} — ${esc(d.why)}</li>`).join("")}</ul></details>` : ""}`;
    $("sr-detail-body").innerHTML = html + exHtml;
    $("sr-detail-note").textContent = `${view.floors.length}개 표본층 · 제외 ${ex.length} · 미배정 ${un.length}`;
  }

  function draw() {
    const r = view.report;
    $("sr-title").textContent = `${r.year}년 ${r.half} 상태평가`;
    const link = $("sr-fac-link");
    link.textContent = r.facility_name;
    link.href = `sitok-facility.html?id=${r.facility_id}`;
    $("sr-round-link").textContent = `${r.year}년 ${r.half}`; // 회차 화면(10/14 3층 구조)
    $("sr-round-link").href = `sitok-round.html?report=${rid}&one=1`;
    drawCounts();
    drawJoints();
    drawResult();
    drawDetail();
  }

  async function load() {
    try {
      view = await api(`/sitok/reports/${rid}/rating`);
      draw();
    } catch (e) { err(e); }
  }

  if (!rid) { err(new Error("회차가 없습니다 (?report=)")); return; }
  load();
})();
