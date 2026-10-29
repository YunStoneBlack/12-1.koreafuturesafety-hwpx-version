// 시특법 정밀안전점검 재료시험(sitok-tests.html, 2026-10-13 ② 단계) — 표본층·부재 규격·강도·탄산화·기울기·부등침하.
// 값을 바꾸면(change) 입력 전체를 PATCH /sitok/reports/{id}/tests 로 저장하고, 서버가 계산한 값(등급·1/N·잔존수명)으로 다시 그림.
// 계산은 server/sitok/tests.py — 다산은혜교회 보고서 값으로 검증.
// 10/14 형 피드백(작업내용 46차): 표본층을 고르면 기준 수량만큼 줄이 자동(서버 sync_defaults), 부재는 선택(기둥·큰보·작은보·슬래브·벽체)·강도는 부위(중앙부·단부) 따로,
// 규격 치수는 기둥·보 가로·세로 두 칸 / 슬래브·벽체 두께 한 칸(숫자 키패드), 조사결과는 일치/다름, 기울기 8줄(모서리 4 × X·Y), 부등침하 4구간 + 구간마다 측점 추가,
// [🤖 일람표에서 설계 치수 채우기](시설물 도면 "구조 일람표"를 AI가 읽음).
// 10/14 전회차 가져오기(view.prev = 지난 정밀 회차 입력): 표본층은 서버가 자동, 표마다 [전회차 그대로](규격 전부 / 강도 부재·부위·손상·설계강도 / 탄산화 부재 / 기울기·부등침하 전부), 줄마다 "전회차: …" 힌트.

(function () {
  const rid = Number(new URLSearchParams(location.search).get("report")) || null;
  const errorEl = document.getElementById("error");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const err = (e) => showError(errorEl, e);
  const $ = (id) => document.getElementById(id);
  const num = (v) => (v === null || v === undefined || v === "" ? "" : v);
  const grade = (g) => (g ? `<span class="st-grade ${g}">${g.toUpperCase()}</span>` : "-");
  const STRUCT = ["라멘", "벽식", "무량판"], MAT = ["RC", "SRC", "철골", "조적"], DIRS = ["", "좌측", "우측", "전면", "후면"];
  const MEMBERS = ["", "기둥", "큰보", "작은보", "슬래브", "벽체", "강재"], SPOTS = ["", "중앙부", "단부"], THICK = ["슬래브", "벽체"];
  let view = null; // 서버가 준 계산값
  let prevKeep = null; // 전회차 입력(GET에만 옴 — 저장 뒤에도 유지, 10/14)
  let input = null; // 저장할 입력(view.input)
  let timer = null;

  function floorOptions(sel) {
    const fl = (view.sample.floors || []).length ? view.sample.floors : [];
    return `<option value="">층</option>${fl.map((f) => `<option value="${f.floor}"${Number(sel) === f.floor ? " selected" : ""}>${esc(f.label)}</option>`).join("")}`;
  }
  const opts = (list, sel, blank) => list.map((v) => `<option value="${esc(v)}"${v === (sel || "") ? " selected" : ""}>${esc(v) || blank || "—"}</option>`).join("");

  async function save(msg) {
    clearTimeout(timer);
    const saved = $("st-saved");
    saved.textContent = "저장 중…";
    saved.className = "st-saved";
    try {
      view = await apiPatch(`/sitok/reports/${rid}/tests`, { tests: input });
      input = view.input;
      draw();
      saved.textContent = msg || "✓ 저장됨";
      timer = setTimeout(() => { saved.textContent = ""; }, 2500);
    } catch (e) { saved.textContent = `저장 실패: ${e.message}`; saved.className = "st-saved bad"; }
  }

  const getAt = (keys) => { let o = input; for (const k of keys) o = o[/^\d+$/.test(k) ? Number(k) : k]; return o; };
  const setAt = (path, v) => {
    const keys = path.split(".");
    const o = getAt(keys.slice(0, -1));
    const last = keys[keys.length - 1];
    o[/^\d+$/.test(last) ? Number(last) : last] = v;
  };

  // 표 칸(data-path="sections.0.design")에서 input으로 값 넣기
  function bindInputs(root) {
    root.querySelectorAll("[data-path]").forEach((el) => {
      el.addEventListener("change", () => {
        setAt(el.dataset.path, el.type === "checkbox" ? el.checked : el.value);
        if (el.dataset.path.endsWith(".damaged")) { // 손상 체크 → 비고 "비건전부", 풀면 "건전부"(직접 적은 비고는 그대로, 10/14 형)
          const row = getAt(el.dataset.path.split(".").slice(0, -1));
          if (["", "건전부", "비건전부"].includes((row.note || "").trim())) row.note = el.checked ? "비건전부" : "건전부";
        }
        save();
      });
    });
    // 치수 칸(가로·세로 두 칸 또는 두께 한 칸) → "300×600" 글자 하나로(10/14)
    root.querySelectorAll("[data-dim]").forEach((el) => {
      el.addEventListener("change", () => {
        const parts = [...root.querySelectorAll(`[data-dim="${el.dataset.dim}"]`)].map((x) => x.value.trim()).filter((x) => x !== "");
        setAt(el.dataset.dim, parts.join("×"));
        save();
      });
    });
    root.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", () => {
      const [list, i] = b.dataset.del.split(".");
      const arr = list.includes("/") ? input[list.split("/")[0]][list.split("/")[1]] : input[list];
      arr.splice(Number(i), 1);
      save();
    }));
  }

  // ---- 전회차 가져오기(10/14) ----
  const prevIn = () => (view.prev && view.prev.input) || null;
  const prevLabel = () => (view.prev ? `${view.prev.report.year}년 ${view.prev.report.half}` : "");
  function prevBar(key, n, what, onCopy) {
    if (!prevIn() || !n) return "";
    return `<div class="st-prev"><span>📂 전회차(${esc(prevLabel())}) ${what} ${n}줄</span><button type="button" class="secondary btn-sm st-prev-copy" data-key="${key}">전회차 그대로 가져오기</button>
      <span class="sk-help">가져온 뒤 고칠 수 있습니다${key === "strength" || key === "carbonation" ? " — 측정값은 새로(강도는 엑셀, 탄산화는 직접)" : ""}</span></div>`;
  }
  const hint = (text) => (text ? `<div class="st-hint">전회차: ${esc(text)}</div>` : "");
  function bindPrev(root, fn) {
    root.querySelectorAll(".st-prev-copy").forEach((b) => b.addEventListener("click", () => { fn(prevIn()); save("✓ 전회차에서 가져왔습니다 — 고칠 곳을 고치세요"); }));
  }

  // ---- 1. 표본층 ----
  function drawSample() {
    const s = view.sample, b = view.building;
    $("st-sample-count").textContent = s.need ? `필요 ${s.need}개 층 · 고른 ${s.count}개` : "시설물 층수·연면적을 먼저 넣으세요";
    const picked = new Set((input.sample.floors || []).map((f) => f.floor));
    $("st-floor-pick").innerHTML = b.floors.map((f) => `<button type="button" data-k="${f.key}" class="${picked.has(f.key) ? "on" : ""}">${esc(f.label)}</button>`).join("")
      || '<span class="page-sub">시설물 현황에 지상·지하 층수가 없습니다.</span>';
    $("st-floor-pick").querySelectorAll("button").forEach((btn) => btn.addEventListener("click", () => {
      const k = Number(btn.dataset.k);
      const list = input.sample.floors;
      const i = list.findIndex((f) => f.floor === k);
      if (i >= 0) list.splice(i, 1);
      else list.push({ floor: k, start: null, end: null, structure: (view.report.structure || "").includes("벽") ? "벽식" : "라멘", material: "RC" });
      list.forEach((f) => { f.start = null; f.end = null; }); // 층이 바뀌면 범위 다시 자동
      save(i >= 0 ? "✓ 저장됨 — 그 층의 빈 줄은 뺐습니다(값 있는 줄은 남김)" : "✓ 저장됨 — 기준 수량만큼 줄을 만들었습니다");
    }));
    const rows = s.floors.map((f, i) => `<tr><td><b>${esc(f.label)}</b></td>
      <td><select data-path="sample.floors.${i}.start">${floorAll(f.start)}</select></td><td><select data-path="sample.floors.${i}.end">${floorAll(f.end)}</select></td>
      <td class="calc">${esc(f.range_label)}${f.auto && (f.auto[0] !== f.start || f.auto[1] !== f.end) ? ' <small>(자동: ' + esc(rangeText(f.auto)) + ")</small>" : ""}</td>
      <td><select data-path="sample.floors.${i}.structure">${opts(STRUCT, f.structure)}</select></td>
      <td><select data-path="sample.floors.${i}.material">${opts(MAT, f.material)}</select></td></tr>`).join("");
    $("st-sample-tbl").innerHTML = s.floors.length ? `<table><thead><tr><th>표본층</th><th>범위 시작</th><th>범위 끝</th><th>대표 범위</th><th>구조형식</th><th>구조재료</th></tr></thead><tbody>${rows}</tbody></table>` : "";
    const q = s.quantity;
    const qt = (name, x) => `<span><b>${name}</b> ${x.have}/${x.need}${x.have < x.need ? ' <span class="short">부족</span>' : ""}</span>`;
    $("st-qty").innerHTML = s.floors.length ? `<span>기준 수량(표본층 ${s.count}개):</span>${qt("부재 규격", q.section)}${qt("강도", q.strength)}${qt("탄산화", q.carbonation)}${qt("기울기", q.tilt)}${qt("부등침하 구간", q.settlement)}` : "";
    bindInputs($("st-sample-tbl"));
  }
  const floorAll = (sel) => `${view.building.floors.map((f) => `<option value="${f.key}"${Number(sel) === f.key ? " selected" : ""}>${esc(f.label)}</option>`).join("")}`;
  const rangeText = (a) => { const l = (k) => (k < 0 ? `지하${-k}층` : `지상${k}층`); return a[0] === a[1] ? l(a[0]) : `${l(a[0])}~${l(a[1])}`; };

  // ---- 2. 부재 규격 ----
  // 치수 칸: 기둥·보 = 가로 × 세로(두 칸), 슬래브·벽체 = 두께(한 칸). 폰에선 숫자 키패드(inputmode=numeric).
  function dimCell(path, value, member, sq = false) {
    const v = String(value || "");
    const sqBtn = (k, cur) => (sq ? `<button type="button" class="st-sq${cur === "□" ? " on" : ""}" data-sq="${path}|${k}" title="못 잼(□ — 보고서 조사결과에 □, 비율·평가 안 냄) · 다시 누르면 지움">□</button>` : "");
    if (member === "강재") return `<span class="st-dim"><input class="w" data-dim="${path}" value="${esc(v)}" placeholder="H-400×200×8×13" title="H형강 규격 H×B×t1×t2(mm) — 단면적은 자동. 단면적(cm²)만 적어도 됩니다" /></span>`;
    if (THICK.includes(member)) return `<span class="st-dim"><input class="n" data-dim="${path}" value="${esc(v)}" inputmode="numeric" placeholder="두께" />${sqBtn(0, v)}<small>mm</small></span>`;
    const [x = "", y = ""] = v.split("×");
    return `<span class="st-dim"><input class="n" data-dim="${path}" value="${esc(x)}" inputmode="numeric" placeholder="가로" />${sqBtn(0, x)}<small>×</small><input class="n" data-dim="${path}" value="${esc(y)}" inputmode="numeric" placeholder="세로" />${sqBtn(1, y)}</span>`;
  }
  // 2. 부재 규격(10/29 사용자 "내진 화면 기능을 정밀에도") — 구조 일람표 부재 목록에서 그 층·그 부재 칸 고르기(보 = 위층 바닥보: 1층 → 2G…, 최상층 → RG…),
  // 층만 보기, 칸 수 표(층 × 부재, 줄이면 빈 칸만 빠짐 — 서버 tests.sync_sections), 조사결과 일치·일부 일치·불일치 + 못 잰 변 □, 부재를 바꾸면 같은 층 그 부재 빈 칸과 맞바꿈(칸 수 그대로).
  const SK = { 기둥: "기둥", 큰보: "보", 작은보: "보", 벽체: "벽체" }; // 구조 일람표 종류 — 슬래브·강재는 목록 없음
  const QTY_MEMBERS = ["기둥", "큰보", "작은보", "슬래브", "벽체", "강재"];
  const MATCHES = ["일치", "일부 일치", "불일치"];
  let sFloor = "";
  try { sFloor = sessionStorage.getItem(`st-sf-${rid}`) || ""; } catch (_) { /* */ }
  const sched = () => view.schedule || { items: [], count: 0, need: 0 };
  const marksAt = (it, fl) => (fl != null && it.at && it.at[String(fl)] !== undefined ? it.at[String(fl)] : it.marks);
  const baseMark = (m) => String(m || "").replace(/^(?:PHR|PH|R|P|B\d+|n|\d+)(?:[-~](?:PHR|PH|R|P|B\d+|n|\d+))?(?=[A-Z]{1,3}\d)/, "");
  const girder = (it, fl) => marksAt(it, fl).some((m) => /G/.test(baseMark(m))); // 큰보 = G(Girder·WG·CG), 작은보 = B
  function sectionChoices(r) {
    const k = SK[r.member];
    if (!k) return [];
    let list = sched().items.filter((it) => it.kind === k && (r.floor == null || !it.at || it.at[String(r.floor)] === undefined || it.at[String(r.floor)].length > 0));
    if (k === "보") { const g = list.filter((it) => girder(it, r.floor) === (r.member === "큰보")); if (g.length) list = g; }
    return list;
  }
  const itemSize = (it, member) => (THICK.includes(member) ? (it.thickness ? String(it.thickness) : "") : String(it.size || "").replace(/\s*[xX×*]\s*/g, "×"));
  const itemLabel = (it, fl) => `${(marksAt(it, fl).length ? marksAt(it, fl) : it.marks).join(",")}${it.position ? ` ${it.position}` : ""} ${it.size || (it.thickness ? `THK=${it.thickness}` : "")}${it.floors ? ` (${it.floors})` : ""}${it.confirmed ? "" : " ⚠미확인"}`;
  const secFilled = (r) => !!(r.design || r.measured || r.position);
  const planNow = () => ({ ...(view.section_plan || {}) });
  const pkey = (k, m) => `${k}|${m}`;
  function drawSections() {
    const pvs = (prevIn() || {}).sections || [];
    const sc = sched();
    const floorsS = (view.sample.floors || []).map((f) => f.floor);
    const fl = [...new Set([...floorsS, ...view.sections.map((r) => r.floor).filter((x) => x != null)])].sort((x, y) => x - y);
    if (sFloor && !fl.some((n) => String(n) === sFloor)) sFloor = "";
    const flName = (n) => (n < 0 ? `지하${-n}층` : `지상${n}층`);
    const of = (n, m) => view.sections.filter((r) => r.floor === n && r.member === m);
    const cols = QTY_MEMBERS.filter((m) => m !== "강재" || view.sections.some((r) => r.member === "강재"));
    const qty = floorsS.length ? `<div class="st-sqty"><table class="st-qty-t"><thead><tr><th>칸 수</th>${cols.map((m) => `<th>${esc(m)}</th>`).join("")}</tr></thead><tbody>
        ${floorsS.map((n) => `<tr><td><button type="button" class="st-fname${String(n) === sFloor ? " on" : ""}" data-mf="${n}" title="이 층만 보기">${esc(flName(n))}</button></td>${cols.map((m) => {
          const all = of(n, m).length, done = of(n, m).filter(secFilled).length;
          return `<td class="${all && done >= all ? "ok" : done ? "part" : ""}"><span>${done}/</span><input type="number" min="0" max="40" inputmode="numeric" data-q="${pkey(n, m)}" value="${all}" title="${esc(flName(n))} ${esc(m)} 칸 수" /></td>`; }).join("")}</tr>`).join("")}
        </tbody></table><div class="st-sqty-side"><span class="sk-help">입력/칸 — 표본층마다 기둥 3·큰보 3이 기본(세부지침), 숫자를 고치면 아래 줄이 늘고 줆(줄여도 값 있는 칸은 남음)</span>
        <button type="button" class="secondary btn-sm" id="st-q-reset">기본 칸 수로</button></div></div>` : "";
    const schedLine = `<div class="st-sched2">${sc.count ? `📏 구조 일람표 부재 목록 <b>${sc.count}칸</b>${sc.need ? ` · <span class="short">확인 필요 ${sc.need}</span>` : ""} — 줄마다 [일람표 칸]을 고르면 기호·설계 치수가 채워집니다(그 층·그 부재 칸만, <b>보 = 위층 바닥보</b>: 1층 → 2G…, 최상층 → RG…)
        <a href="sitok-schedule.html?facility=${view.report.facility_id}">목록 보기·고치기</a>`
      : `📏 구조 일람표 부재 목록이 아직 없습니다 — <a href="sitok-schedule.html?facility=${view.report.facility_id}">부재 목록 만들기</a>(도면 칸의 구조 일람표를 쪽마다 읽음)를 하면 줄마다 일람표 칸을 고를 수 있습니다. 목록 없이도 아래 [🤖 일람표에서 설계 치수 채우기]는 그대로`}</div>`;
    const chips = floorChips(fl.map((n) => ({ n, label: flName(n), done: view.sections.filter((r) => r.floor === n && secFilled(r)).length, total: view.sections.filter((r) => r.floor === n).length })), sFloor);
    const rows = view.sections.map((r, i) => {
      if (sFloor && String(r.floor) !== sFloor) return "";
      const ch0 = sectionChoices(r), cur = r.item_id && !ch0.some((x) => x.id === r.item_id) ? sc.items.find((x) => x.id === r.item_id) : null;
      const ch = cur ? [...ch0, cur] : ch0;
      const itemCell = !SK[r.member] ? '<span class="calc">—</span>' : !sc.count ? '<span class="calc">목록 없음</span>'
        : `<select class="l st-item" data-item="${i}" title="구조 일람표 칸 — 그 층·그 부재만(보 = 위층 바닥보)"><option value="">${ch.length ? "일람표 칸" : "맞는 칸 없음 — 직접"}</option>${ch.map((x) => `<option value="${esc(x.id)}"${x.id === r.item_id ? " selected" : ""}>${esc(itemLabel(x, r.floor))}</option>`).join("")}</select>`;
      return `<tr class="${secFilled(r) ? "" : "st-empty"}"><td>B${i + 1}</td><td><select data-floor="${i}">${floorOptions(r.floor)}</select></td>
      <td class="st-itemcell">${itemCell}</td>
      <td><input class="l" data-path="sections.${i}.position" value="${esc(r.position)}" placeholder="C1 / X3-Y3" />${hint(pvs[i] && !r.design ? `${pvs[i].position || ""} ${pvs[i].member} ${pvs[i].design}${pvs[i].measured && pvs[i].measured !== pvs[i].design ? " → " + pvs[i].measured : ""}`.trim() : "")}</td>
      <td><select data-member="${i}">${opts(MEMBERS, r.member, "부재")}</select>${r.member === "강재" ? `<select data-path="sections.${i}.sub" title="강재가 어느 부재인지 — 상태평가 강재 기둥·큰보·작은보">${opts(["기둥", "큰보", "작은보"], r.sub || "기둥")}</select>` : ""}</td>
      <td>${dimCell(`sections.${i}.design`, r.design, r.member)}</td>
      <td class="st-measured"><select data-match="${i}">${MATCHES.map((m) => `<option${m === (r.match || (r.same ? "일치" : "불일치")) ? " selected" : ""}>${m}</option>`).join("")}</select>
        ${r.same ? `<span class="calc">${esc(r.design || "-")}</span>` : dimCell(`sections.${i}.measured`, r.measured, r.member, true)}</td>
      <td class="calc">${r.steel && r.area_design ? `<small>${r.area_design}${r.area_measured ? `→${r.area_measured}` : ""}cm²</small><br>` : ""}${r.ratio === null ? (String(r.measured || "").includes("□") ? "□" : "-") : `${r.ratio}%`}</td><td class="calc">${r.ok === null ? "-" : r.ok ? "<b>O.K</b>" : "N.G"}</td><td>${grade(r.grade)}</td>
      <td><button type="button" class="secondary st-del" data-sdel="${i}" title="이 칸 빼기(칸 수도 하나 줄임)">✕</button></td></tr>`;
    }).join("");
    $("st-section-count").textContent = `${view.sections.filter(secFilled).length}/${view.sections.length}개소${view.sections_grade ? ` · ${view.sections_grade.toUpperCase()}` : ""}`;
    const pv = prevIn();
    $("st-section-tbl").innerHTML = schedLine + qty + chips + prevBar("sections", pv ? pv.sections.length : 0, "부재 규격")
      + `<table><thead><tr><th>NO</th><th>표본층</th><th>일람표 칸</th><th>위치·기호</th><th>부재</th><th>설계도면(mm)</th><th>조사결과(못 재면 □)</th><th>비율</th><th>평가</th><th>등급</th><th></th></tr></thead><tbody>${rows}</tbody></table>
      <button type="button" class="secondary st-add" id="st-section-add">+ 개소 추가${sFloor ? ` (${esc(flName(Number(sFloor)))})` : ""}</button>`;
    const box = $("st-section-tbl");
    bindPrev(box, (p) => { input.sections = p.sections.map((r) => ({ ...r })); input.section_plan = {}; });
    const sec = (el, k) => input.sections[Number(el.dataset[k])];
    box.querySelectorAll("[data-mf]").forEach((b) => b.addEventListener("click", () => { // 층만 보기(다시 누르면 전체)
      sFloor = b.dataset.mf === sFloor && b.classList.contains("st-fname") ? "" : b.dataset.mf;
      try { sessionStorage.setItem(`st-sf-${rid}`, sFloor); } catch (_) { /* */ }
      drawSections();
      $("st-section-tbl").querySelector("table:not(.st-qty-t)")?.scrollIntoView({ block: "start", behavior: "smooth" });
    }));
    box.querySelectorAll("[data-q]").forEach((el) => el.addEventListener("change", () => {
      const p = planNow();
      p[el.dataset.q] = Math.max(0, Math.min(40, Number(el.value) || 0));
      input.section_plan = p;
      save("✓ 칸 수를 바꿨습니다(줄일 땐 빈 칸만 빠짐)");
    }));
    const reset = box.querySelector("#st-q-reset");
    if (reset) reset.addEventListener("click", () => { input.section_plan = { ...(view.section_plan_default || {}) }; save("✓ 기본 칸 수로(값 있는 칸은 그대로)"); });
    $("st-section-add").addEventListener("click", () => { // 칸 수 표에 하나 더(보는 층이 있으면 그 층, 아니면 마지막 줄의 층·부재)
      const pick = sFloor ? view.sections.filter((r) => String(r.floor) === sFloor) : view.sections;
      const last = pick[pick.length - 1];
      const k = sFloor ? Number(sFloor) : last ? last.floor : floorsS[0];
      if (k == null) { input.sections.push({ floor: null, position: "", member: "기둥", design: "", measured: "", same: true, match: "일치", sub: "" }); save(); return; }
      const m = last && last.floor === k ? last.member : "기둥";
      const p = planNow();
      p[pkey(k, m)] = of(k, m).length + 1;
      input.section_plan = p;
      save();
    });
    box.querySelectorAll("[data-sdel]").forEach((b) => b.addEventListener("click", () => {
      const i = Number(b.dataset.sdel), r = input.sections[i];
      if (secFilled(r) && !confirm(`B${i + 1} 칸을 뺄까요? 적은 값도 지워집니다.`)) return;
      if (r.floor != null && floorsS.includes(r.floor)) { const p = planNow(); p[pkey(r.floor, r.member)] = Math.max(0, of(r.floor, r.member).length - 1); input.section_plan = p; }
      input.sections.splice(i, 1);
      save();
    }));
    box.querySelectorAll("[data-member]").forEach((el) => el.addEventListener("change", () => { // 부재 바꾸기 — 같은 층 그 부재 빈 칸과 맞바꿈(칸 수 그대로), 없으면 칸 수를 옮김
      const i = Number(el.dataset.member), r = input.sections[i], from = r.member, to = el.value;
      const j = input.sections.findIndex((x, n) => n !== i && x.floor === r.floor && x.member === to && !secFilled(x));
      if (j >= 0) input.sections[j].member = from;
      else if (r.floor != null && floorsS.includes(r.floor)) {
        const p = planNow();
        p[pkey(r.floor, from)] = Math.max(0, of(r.floor, from).length - 1);
        p[pkey(r.floor, to)] = of(r.floor, to).length + 1;
        input.section_plan = p;
      }
      r.member = to;
      if (SK[from] !== SK[to]) r.item_id = ""; // 다른 종류면 고른 일람표 칸은 풂(치수는 그대로 — 고치세요)
      if (to === "강재" && !r.sub) r.sub = "기둥";
      save();
    }));
    box.querySelectorAll("[data-floor]").forEach((el) => el.addEventListener("change", () => { // 층 바꾸기 — 칸 수도 따라 옮김
      const r = input.sections[Number(el.dataset.floor)], to = el.value === "" ? null : Number(el.value);
      if (view.section_plan_on || Object.keys(input.section_plan || {}).length) {
        const p = planNow();
        if (r.floor != null) p[pkey(r.floor, r.member)] = Math.max(0, of(r.floor, r.member).length - 1);
        if (to != null) p[pkey(to, r.member)] = of(to, r.member).length + 1;
        input.section_plan = p;
      }
      r.floor = to;
      save();
    }));
    box.querySelectorAll("[data-item]").forEach((el) => {
      el.addEventListener("change", () => { // 일람표 칸 고르기 → 기호(위치 칸이 비었거나 전에 고른 칸 기호면)·설계 치수
        const r = sec(el, "item"), old = sc.items.find((x) => x.id === r.item_id), it = sc.items.find((x) => x.id === el.value);
        const oldMark = old ? (marksAt(old, r.floor)[0] || old.marks[0] || "") : "";
        r.item_id = el.value;
        if (it) {
          const d = itemSize(it, r.member);
          if (d) r.design = d;
          const mk = marksAt(it, r.floor)[0] || it.marks[0] || "";
          if (mk && (!r.position || r.position === oldMark)) r.position = mk;
          if (r.same) r.measured = r.design;
        }
        save();
      });
      searchSelect(el, { placeholder: "일람표 칸 — 기호·치수로 검색" });
    });
    box.querySelectorAll("[data-match]").forEach((el) => el.addEventListener("change", () => {
      const r = sec(el, "match");
      r.match = el.value;
      r.same = el.value === "일치";
      r.measured = el.value === "불일치" ? "" : r.design || ""; // 일치 = 설계 그대로, 일부 일치 = 설계를 미리(다른 변만 고침)
      save();
    }));
    box.querySelectorAll("[data-sq]").forEach((b) => b.addEventListener("click", () => { // □ = 못 잼(다시 누르면 지움)
      const [path, k] = b.dataset.sq.split("|");
      const r = input.sections[Number(path.split(".")[1])];
      const n = THICK.includes(r.member) ? 1 : 2;
      const parts = String(getAt(path.split(".")) || "").split("×");
      while (parts.length < n) parts.push("");
      parts[Number(k)] = parts[Number(k)] === "□" ? "" : "□";
      setAt(path, parts.every((x) => x === "") ? "" : parts.slice(0, n).join("×"));
      save();
    }));
    bindInputs(box);
  }

  // ---- 3. 강도 ----
  function drawStrength() {
    const st = view.strength;
    const rows = st.rows.map((r, i) => `<tr><td>S${i + 1}</td><td><select data-path="strength.rows.${i}.floor">${floorOptions(r.floor)}</select></td>
      <td><select data-path="strength.rows.${i}.member">${opts(MEMBERS, r.member, "부재")}</select></td>
      <td><select data-path="strength.rows.${i}.spot">${opts(SPOTS, r.spot, "부위")}</select></td>
      <td class="calc">${esc(r.position || "-")}</td><td class="calc">${num(r.r0) || "-"}</td><td class="calc">${num(r.fc_mat) || "-"}</td><td class="calc">${num(r.fc_arch) || "-"}</td>
      <td><input class="n" data-path="strength.rows.${i}.est" value="${num(r.est)}" inputmode="decimal" /></td>
      <td><input class="n" data-path="strength.rows.${i}.design" value="${num(r.design)}" inputmode="decimal" placeholder="27" /></td>
      <td class="calc">${r.ratio === null ? "-" : `${r.ratio}%`}</td>
      <td><label class="st-chk"><input type="checkbox" data-path="strength.rows.${i}.damaged"${r.damaged ? " checked" : ""} /> 손상</label></td>
      <td><input class="l" data-path="strength.rows.${i}.note" value="${esc(r.note)}" placeholder="건전부" /></td><td>${grade(r.grade)}</td>
      <td><button type="button" class="secondary st-del" data-del="strength/rows.${i}">✕</button></td></tr>`).join("");
    const sm = st.summary;
    $("st-strength-count").textContent = `${st.rows.length}개소${sm.count ? ` · ${sm.min}~${sm.max}MPa 평균 ${sm.mean}` : ""}${st.grade ? ` · ${st.grade.toUpperCase()}` : ""}`;
    const pvS = prevIn();
    $("st-strength-tbl").innerHTML = prevBar("strength", pvS ? pvS.strength.rows.length : 0, "강도 개소(부재·부위·손상·설계강도)")
      + `<table><thead><tr><th>구분</th><th>표본층</th><th>부재</th><th>부위</th><th>성과표 위치</th><th>보정반발경도 R0</th><th>재료학회</th><th>건축학회</th><th>추정강도(MPa)</th><th>설계기준강도</th><th>비율</th><th>손상</th><th>비고</th><th>등급</th><th></th></tr></thead><tbody>${rows}</tbody></table>
      <button type="button" class="secondary st-add" id="st-strength-add">+ 개소 추가</button>`;
    bindPrev($("st-strength-tbl"), (p) => { input.strength.rows = p.strength.rows.map((r) => ({ floor: r.floor, member: r.member, spot: r.spot, position: "", r0: null, fc_mat: null, fc_arch: null, est: null, design: r.design, damaged: r.damaged, note: r.note })); });
    $("st-strength-add").addEventListener("click", () => {
      const last = input.strength.rows[input.strength.rows.length - 1];
      input.strength.rows.push({ floor: last ? last.floor : null, member: last ? last.member : "기둥", spot: "", position: "", r0: null, fc_mat: null, fc_arch: null, est: null,
        design: last ? last.design : null, damaged: false, note: "건전부" });
      save();
    });
    $("st-xlsx-file").innerHTML = st.file ? `📎 ${esc(st.file)} <button type="button" class="secondary" id="st-xlsx-del">빼기</button>` : "";
    $("st-xlsx-del")?.addEventListener("click", async () => {
      if (!confirm("올린 성과표를 빼고 강도 값을 비울까요?")) return;
      try { view = await api(`/sitok/reports/${rid}/tests/schmidt`, { method: "DELETE" }); input = view.input; draw(); } catch (e) { err(e); }
    });
    bindInputs($("st-strength-tbl"));
  }

  // ---- 4. 탄산화 ----
  function drawCarb() {
    const c = view.carbonation, b = view.building;
    $("st-carb-top").innerHTML = `<span>경과년수 <b>${b.age ?? "?"}년</b> <small>(준공 ${esc(b.completion || "?")} ~ 점검 ${esc(b.when || "오늘")})</small></span>
      <label>물-시멘트비(W/C)<input data-path="carbonation.wc" value="${num(c.wc)}" inputmode="decimal" /></label>
      <label>탄산화 비율(R)<input data-path="carbonation.ratio" value="${num(c.ratio)}" inputmode="decimal" /></label>`;
    const rows = c.rows.map((r, i) => `<tr><td>C${i + 1}</td><td><select data-path="carbonation.rows.${i}.floor">${floorOptions(r.floor)}</select></td>
      <td><select data-path="carbonation.rows.${i}.member">${opts(MEMBERS, r.member, "부재")}</select></td>
      <td><input class="n" data-path="carbonation.rows.${i}.cover" value="${num(r.cover)}" inputmode="decimal" /></td>
      <td><input class="n" data-path="carbonation.rows.${i}.depth" value="${num(r.depth)}" inputmode="decimal" /></td>
      <td class="calc">${num(r.remain) === "" ? "-" : r.remain}</td><td class="calc">${num(r.coef) === "" ? "-" : r.coef}</td><td class="calc">${num(r.theory) === "" ? "-" : r.theory}</td>
      <td class="calc"><b>${esc(r.life_text || "-")}</b></td><td>${grade(r.grade)}</td>
      <td class="st-photo">${r.photo ? `<a href="${BASE}/api/sitok/reports/${rid}/tests/carb-photo/${i}?v=${encodeURIComponent(r.photo)}" target="_blank" rel="noopener"><img src="${BASE}/api/sitok/reports/${rid}/tests/carb-photo/${i}?v=${encodeURIComponent(r.photo)}" alt="C${i + 1}" /></a>
          <button type="button" class="secondary st-del st-photo-del" data-i="${i}" title="사진 빼기">✕</button>` : ""}
        <label class="secondary-link st-photo-add" title="부록 3-1 탄산화 사진현황에 들어갑니다">${r.photo ? "바꾸기" : "📷 사진"}<input type="file" accept="image/*" capture="environment" hidden data-kr-file="1" data-i="${i}" /></label></td>
      <td><button type="button" class="secondary st-del" data-del="carbonation/rows.${i}">✕</button></td></tr>`).join("");
    const sm = c.summary;
    $("st-carb-count").textContent = `${c.rows.length}개소${sm.count ? ` · 깊이 ${sm.min}~${sm.max}mm` : ""}${c.grade ? ` · ${c.grade.toUpperCase()}` : ""}`;
    const pvC = prevIn();
    $("st-carb-tbl").innerHTML = prevBar("carbonation", pvC ? pvC.carbonation.rows.length : 0, "탄산화 개소(부재)")
      + `<table><thead><tr><th>no</th><th>표본층</th><th>부재</th><th>철근 피복(mm)</th><th>탄산화 깊이(mm)</th><th>잔여 깊이</th><th>속도계수 A</th><th>이론치(mm)</th><th>잔존수명(년)</th><th>등급</th><th>사진</th><th></th></tr></thead><tbody>${rows}</tbody></table>
      <button type="button" class="secondary st-add" id="st-carb-add">+ 개소 추가</button>`;
    bindPrev($("st-carb-tbl"), (p) => { input.carbonation.rows = p.carbonation.rows.map((r) => ({ floor: r.floor, member: r.member, position: "", cover: null, depth: null, photo: "" })); });
    $("st-carb-add").addEventListener("click", () => {
      const last = input.carbonation.rows[input.carbonation.rows.length - 1];
      input.carbonation.rows.push({ floor: last ? last.floor : (input.sample.floors[0] || {}).floor ?? null, member: last ? last.member : "기둥", position: "", cover: null, depth: null });
      save();
    });
    // 탄산화 사진(10/14) — 줄마다 한 장, 부록 3-1 탄산화 사진현황(6장/쪽)
    $("st-carb-tbl").querySelectorAll(".st-photo-add input").forEach((inp) => inp.addEventListener("change", async () => {
      const f = inp.files[0];
      const i = inp.dataset.i;
      inp.value = "";
      if (!f) return;
      $("st-saved").textContent = "사진 올리는 중…";
      try {
        const fd = new FormData();
        fd.append("file", f);
        view = await apiUpload(`/sitok/reports/${rid}/tests/carb-photo/${i}`, fd);
        input = view.input;
        draw();
        $("st-saved").textContent = "✓ 사진 저장됨";
      } catch (e) { $("st-saved").textContent = `사진 실패: ${e.message}`; $("st-saved").className = "st-saved bad"; }
    }));
    $("st-carb-tbl").querySelectorAll(".st-photo-del").forEach((b) => b.addEventListener("click", async () => {
      if (!confirm("이 사진을 뺄까요?")) return;
      try { view = await api(`/sitok/reports/${rid}/tests/carb-photo/${b.dataset.i}`, { method: "DELETE" }); input = view.input; draw(); } catch (e) { err(e); }
    }));
    bindInputs($("st-carb-top"));
    bindInputs($("st-carb-tbl"));
  }

  // ---- 5. 기울기 ----
  function drawTilt() {
    const t = view.tilt;
    const pvT = ((prevIn() || {}).tilt || {}).rows || [];
    const rows = t.rows.map((r, i) => `<tr><td>${i + 1}</td>
      <td><input class="l" data-path="tilt.rows.${i}.label" value="${esc(r.label)}" placeholder="모서리1 X" />${hint(pvT[i] && r.disp === null && pvT[i].height ? `${pvT[i].height}mm ${pvT[i].direction || ""} 변위 ${pvT[i].disp ?? "-"}mm` : "")}</td>
      <td><input class="n" data-path="tilt.rows.${i}.height" value="${num(r.height)}" inputmode="numeric" placeholder="29200" /></td>
      <td><select data-path="tilt.rows.${i}.direction">${opts(DIRS, r.direction)}</select></td>
      <td><input class="n" data-path="tilt.rows.${i}.disp" value="${num(r.disp)}" inputmode="decimal" /></td>
      <td class="calc"><b>${esc(r.ratio_text)}</b></td><td>${grade(r.grade)}</td>
      <td><button type="button" class="secondary st-del" data-del="tilt/rows.${i}">✕</button></td></tr>`).join("");
    const rg = t.range;
    $("st-tilt-count").textContent = `${t.rows.length}개소${rg.min_n ? ` · 1/${rg.min_n.toLocaleString()} ~ 1/${rg.max_n.toLocaleString()}` : ""}${t.grade ? ` · ${t.grade.toUpperCase()}` : ""}`;
    $("st-tilt-tbl").innerHTML = prevBar("tilt", pvT.filter((x) => x.height).length, "기울기 측점(측정값까지)")
      + `<table><thead><tr><th>NO</th><th>측점</th><th>측정높이(mm)</th><th>상부 변위방향</th><th>변위량(mm)</th><th>기울기</th><th>등급</th><th></th></tr></thead><tbody>${rows}</tbody></table>
      <button type="button" class="secondary st-add" id="st-tilt-add">+ 측점 추가</button>`;
    bindPrev($("st-tilt-tbl"), (p) => { input.tilt = { note: p.tilt.note || input.tilt.note, rows: p.tilt.rows.map((r) => ({ ...r })) }; });
    $("st-tilt-add").addEventListener("click", () => {
      const last = input.tilt.rows[input.tilt.rows.length - 1];
      const n = input.tilt.rows.length;
      input.tilt.rows.push({ label: `모서리${Math.floor(n / 2) + 1} ${n % 2 ? "Y" : "X"}`, height: last ? last.height : null, direction: "", disp: null });
      save();
    });
    $("st-tilt-note").value = t.note || "";
    bindInputs($("st-tilt-tbl"));
  }

  // ---- 6. 부등침하 ----
  function drawSett() {
    const s = view.settlement;
    $("st-sett-top").innerHTML = `<label>조사 층<select data-path="settlement.floor">${floorAll(s.floor)}</select></label>
      <span class="page-sub">보통 최하층 바닥(${esc((view.building.floors[0] || {}).label || "")})</span>`;
    $("st-sett-count").textContent = `${s.sections.length}구간${s.range.max_disp !== null ? ` · 변위 ${s.range.min_disp}~${s.range.max_disp}mm` : ""}${s.grade ? ` · ${s.grade.toUpperCase()}` : ""}`;
    $("st-sett-list").innerHTML = s.sections.map((sec, j) => {
      const rows = sec.rows.map((r, i) => `<tr><td>${r.no}</td><td>위치도 참조</td>
        <td><input class="n" data-path="settlement.sections.${j}.levels.${i}" value="${num(r.level)}" inputmode="decimal" /></td>
        <td class="calc">${r.disp === null ? "" : r.disp}</td>
        <td>${i < sec.rows.length - 1 ? `<input class="n" data-path="settlement.sections.${j}.distances.${i}" value="${num(r.distance)}" inputmode="numeric" />` : ""}</td>
        <td class="calc"><b>${esc(r.ratio_text)}</b></td><td>${r.grade ? grade(r.grade) : ""}</td></tr>`).join("");
      return `<div class="st-sec"><div class="st-sec-head"><b>${esc(s.floor_label || "")} 바닥 ${esc(sec.axis)}축 방향(${sec.no}구간)</b>
          <select data-path="settlement.sections.${j}.axis">${opts(["X", "Y"], sec.axis)}</select>
          <select data-path="settlement.sections.${j}.no">${opts(["1", "2", "3", "4"], String(sec.no))}</select>
          <button type="button" class="secondary st-del" data-sett-add="${j}">+ 측점 추가</button>
          ${sec.rows.length > 2 ? `<button type="button" class="secondary st-del" data-sett-pop="${j}">마지막 측점 빼기</button>` : ""}
          <button type="button" class="secondary st-del" data-del="settlement/sections.${j}">구간 빼기</button></div>
        <div class="st-tbl"><table><thead><tr><th>NO</th><th>측정위치</th><th>측정위치값(mm)</th><th>변위(mm)</th><th>거리(mm)</th><th>기울기</th><th>등급</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
    }).join("") + '<button type="button" class="secondary st-add" id="st-sett-add">+ 구간 추가(측점 3개)</button>';
    const pvSe = (prevIn() || {}).settlement;
    if (pvSe && pvSe.sections.some((x) => x.levels.some((v) => v !== null))) {
      $("st-sett-list").insertAdjacentHTML("afterbegin", prevBar("settlement", pvSe.sections.length, "부등침하 구간(측정값까지)")
        + `<div class="st-hint">전회차: ${pvSe.sections.map((x) => `${x.axis}${x.no}구간 ${x.levels.map((v) => v ?? "-").join("/")}`).join(" · ")}</div>`);
      bindPrev($("st-sett-list"), (p) => { input.settlement = { floor: p.settlement.floor, note: p.settlement.note || input.settlement.note, sections: p.settlement.sections.map((x) => ({ ...x, levels: [...x.levels], distances: [...x.distances] })) }; });
    }
    $("st-sett-add").addEventListener("click", () => {
      const n = input.settlement.sections.length;
      input.settlement.sections.push({ axis: n < 2 ? "X" : "Y", no: (n % 2) + 1, levels: [null, null, null], distances: [null, null] });
      if (!input.settlement.floor) input.settlement.floor = (view.building.floors[0] || {}).key ?? null;
      save();
    });
    $("st-sett-list").querySelectorAll("[data-sett-add]").forEach((b) => b.addEventListener("click", () => {
      const sec = input.settlement.sections[Number(b.dataset.settAdd)];
      sec.levels.push(null);
      sec.distances.push(null);
      save();
    }));
    $("st-sett-list").querySelectorAll("[data-sett-pop]").forEach((b) => b.addEventListener("click", () => {
      const sec = input.settlement.sections[Number(b.dataset.settPop)];
      if (sec.levels.length <= 2) return;
      sec.levels.pop();
      sec.distances.pop();
      save();
    }));
    $("st-sett-note").value = s.note || "";
    bindInputs($("st-sett-top"));
    bindInputs($("st-sett-list"));
  }

  function draw() {
    if (view.prev) prevKeep = view.prev;
    else if (prevKeep) view.prev = prevKeep;
    const r = view.report;
    $("st-title").textContent = `${r.year}년 ${r.half} 재료시험`;
    const link = $("st-fac-link");
    link.textContent = r.facility_name;
    link.href = `sitok-facility.html?id=${r.facility_id}`;
    $("st-round-link").textContent = `${r.year}년 ${r.half}`; // 회차 화면(10/14 3층 구조)
    $("st-round-link").href = `sitok-round.html?report=${rid}&one=1`;
    drawSample();
    drawSections();
    drawStrength();
    drawCarb();
    drawTilt();
    drawSett();
  }

  async function load() {
    try {
      view = await api(`/sitok/reports/${rid}/tests`);
      input = view.input;
      draw();
    } catch (e) { err(e); }
  }

  $("st-tilt-note").addEventListener("change", () => { input.tilt.note = $("st-tilt-note").value; save(); });
  $("st-sett-note").addEventListener("change", () => { input.settlement.note = $("st-sett-note").value; save(); });
  // 구조 일람표(시설물 도면 "schedule") → 빈 설계도면 칸 채우기(10/14 형 피드백 ④)
  $("st-sched").addEventListener("click", async () => {
    const btn = $("st-sched"), msg = $("st-sched-msg");
    btn.disabled = true;
    msg.textContent = "일람표 읽는 중…(10~30초)";
    msg.className = "sk-help";
    try {
      view = await apiPost(`/sitok/reports/${rid}/tests/schedule`, {});
      input = view.input;
      draw();
      const miss = (view.missing || []).length ? ` 못 찾음: ${view.missing.join(", ")}` : "";
      msg.textContent = (view.filled ? `✓ ${view.filled}칸을 채웠습니다 — 틀린 치수는 고치세요.` : "채울 칸을 못 찾았습니다(일람표에 그 층·부재가 없거나, 이미 다 채워짐).") + miss + (view.notes?.length ? ` (${view.notes.join(" / ")})` : "");
    } catch (e) { msg.textContent = e.message; msg.className = "sk-help bad"; } finally { btn.disabled = false; }
  });
  const xlsx = $("st-xlsx");
  xlsx.addEventListener("change", async () => {
    const f = xlsx.files[0];
    xlsx.value = "";
    if (!f) return;
    const msg = $("st-xlsx-msg");
    msg.textContent = `${f.name} 읽는 중…`;
    try {
      const fd = new FormData();
      fd.append("file", f);
      view = await apiUpload(`/sitok/reports/${rid}/tests/schmidt`, fd);
      input = view.input;
      draw();
      msg.textContent = `✓ ${f.name} — ${view.read}개 위치를 읽어 채웠습니다. 층·부재·부위·설계기준강도를 확인하세요.`;
    } catch (e) { msg.textContent = `읽지 못했습니다: ${e.message}`; }
  });
  enableFileDrop(document.querySelector(".st-xlsx"), xlsx);

  if (!rid) { err(new Error("회차가 없습니다 (?report=)")); return; }
  load();
})();
