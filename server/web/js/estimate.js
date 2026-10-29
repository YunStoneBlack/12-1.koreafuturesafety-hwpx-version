// 견적 한 건(2026-10-29 사용자 "그룹웨어 통합 견적서") — 머리·발주처·금액 줄·합계·조건. 고치면 0.6초 뒤 PATCH /estimates/{id} → 서버 계산(rows_out·totals)으로 결과만 다시 그림.
// 줄 입력 칸은 data-p="경로"(예: travel.days, tasks.0.lines.1.persons) — 글자를 치는 동안 칸은 그대로 두고 산출 내역·합계만 바꿈.
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const won = (n) => (n == null || n === "" || isNaN(Number(n)) ? "-" : Math.round(Number(n)).toLocaleString("ko-KR"));
  const pct = (x) => `${Math.round(Number(x || 0) * 1000) / 10}%`;
  const errorEl = $("error");
  const eid = Number(new URLSearchParams(location.search).get("id")) || 0;
  const P = `/estimates/${eid}`;
  let meta = null, est = null, kind = null, saveTimer = null, saving = Promise.resolve();
  const PROJECT_KINDS = ["health_ledger", "impl_check", "tech_guide", "site_safety"];
  const SITOK_KINDS = ["sitok_regular", "sitok_precision", "survey"];

  // ---------- 저장 ----------
  function save(body, now, adopt = false) {
    clearTimeout(saveTimer);
    const go = () => {
      const b = typeof body === "function" ? body() : body;
      $("es-saved").textContent = "저장 중…";
      saving = saving.then(() => apiPatch(P, b)).then((out) => {
        est = { ...est, ...out, rows: adopt ? out.rows : est.rows };  // 입력 중인 줄은 화면 값 그대로(줄을 더했을 땐 서버 기본값을 받음)
        est.rows_out = out.rows_out;
        if (adopt) drawRows(); else drawResults();
        drawHeadBits();
        $("es-saved").textContent = `✓ 저장 ${new Date().toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}`;
      }).catch((err) => { $("es-saved").textContent = ""; showError(errorEl, err); });
    };
    if (now) go(); else saveTimer = setTimeout(go, 600);
  }
  const saveRows = (now, adopt = false) => save(() => ({ rows: est.rows }), now, adopt);

  // ---------- 머리 ----------
  function field(k, label, v, opts = {}) {
    const type = opts.type || "text";
    return `<div class="sk-f${opts.wide ? " ds-wide" : ""}"><label>${esc(label)}${opts.help ? ` <span class="sk-help">${esc(opts.help)}</span>` : ""}</label>
      <input data-k="${k}" type="${type}" value="${esc(v ?? "")}"${opts.ph ? ` placeholder="${esc(opts.ph)}"` : ""}${opts.num ? ' inputmode="numeric"' : ""} /></div>`;
  }
  function drawHead() {
    $("es-title").textContent = est.no;
    $("es-crumb").textContent = `${est.no} ${est.subject || ""}`;
    document.title = `${est.no} - 견적`;
    $("es-kind").textContent = est.kind_label;
    $("es-head").innerHTML = field("no", "견적 번호", est.no, { help: "공유 파일 번호와 맞추려면 바꾸기" }) + field("issued_on", "견적일자", est.issued_on, { type: "date" })
      + field("title", "과업내용(표지)", est.title, { wide: true });
    $("es-head").querySelectorAll("input").forEach((i) => i.addEventListener("change", () => save({ [i.dataset.k]: i.value.trim() }, true)));
    $("es-status").innerHTML = Object.entries(meta.status).map(([k, v]) => `<button type="button" data-v="${k}" class="${k === est.status ? "on" : ""}">${esc(v)}</button>`).join("");
    $("es-status").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
      $("es-status").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
      save({ status: b.dataset.v }, true);
    }));
    const c = est.client || {}, p = est.project || {}, s = est.staff || {};
    $("es-client").innerHTML = field("name", "상호명(발주처)", c.name) + field("rep", "대표자", c.rep, { ph: "예: 학교장" }) + field("ref", "참조", c.ref, { ph: "예: 행정실장님" })
      + field("phone", "연락처", c.phone) + field("email", "메일", c.email, { type: "email" });
    const subj = (kind && kind.subject) || "공사명";
    let pf = field("name", subj, p.name, { wide: true }) + field("address", PROJECT_KINDS.includes(est.kind) ? "현장소재지" : "시설물 주소", p.address, { wide: true });
    if (PROJECT_KINDS.includes(est.kind)) pf += field("amount", "공사금액(원)", p.amount, { num: true, help: "기술지도·이행점검 구간" }) + field("period", "공사기간", p.period, { ph: "예: 2027.01.01.~2027.02.28" });
    if (SITOK_KINDS.includes(est.kind)) pf += field("floors", "층수", p.floors, { ph: "예: 지상4층/지하1층" }) + field("area", "연면적", p.area, { ph: "예: 10,816.17㎡" });
    $("es-project").innerHTML = pf;
    $("es-staff").innerHTML = `<div class="sk-f"><label>견적담당</label><input data-k="name" list="es-staff-list" value="${esc(s.name || "")}" />
      <datalist id="es-staff-list">${(meta.staff || []).map((x) => `<option value="${esc(x.name)}">${esc(x.phone)}</option>`).join("")}</datalist></div>` + field("phone", "담당 연락처", s.phone);
    const bind = (box, key) => box.querySelectorAll("input").forEach((i) => {
      i.addEventListener("input", () => save(() => ({ [key]: Object.fromEntries([...box.querySelectorAll("input")].map((x) => [x.dataset.k, x.value.trim()])) }), false));
      i.addEventListener("change", () => {
        if (key === "staff" && i.dataset.k === "name") {
          const hit = (meta.staff || []).find((x) => x.name === i.value.trim());
          const ph = box.querySelector('input[data-k="phone"]');
          if (hit && ph && !ph.value.trim()) ph.value = hit.phone;
        }
        save(() => ({ [key]: Object.fromEntries([...box.querySelectorAll("input")].map((x) => [x.dataset.k, x.value.trim()])) }), true);
      });
    });
    bind($("es-client"), "client"); bind($("es-project"), "project"); bind($("es-staff"), "staff");
    const o = est.options || {};
    $("es-cond").value = (o.conditions || []).join("\n");
    $("es-note").value = o.note || "";
  }
  // 이 견적의 노임 기준(만들 때 연도·보조인부 — 새 공표가 들어와도 지난 견적은 그대로) + [노임 연도 바꾸기]
  function drawBasis() {
    const o = est.options || {};
    const y = o.labor_year || meta.rates.labor_year;
    const years = Object.keys(meta.rates.labor).sort().reverse();
    $("es-basis").innerHTML = `노임단가 <select id="es-basis-year">${years.map((x) => `<option${x === y ? " selected" : ""}>${x}</option>`).join("")}</select>년
      · 보조인부 ${Number(o.helper_rate || meta.rates.helper_rate).toLocaleString("ko-KR")}원${o.helper_rate && Number(o.helper_rate) !== Number(meta.rates.helper_rate)
        ? ` <button type="button" class="secondary es-mini" id="es-helper-now">지금 단가 ${Number(meta.rates.helper_rate).toLocaleString("ko-KR")}원으로</button>` : ""}`;
    $("es-basis-year").addEventListener("change", (e) => save({ options: { labor_year: e.target.value } }, true));
    const hb = $("es-helper-now");
    if (hb) hb.addEventListener("click", () => save({ options: { helper_now: true } }, true));
  }
  function drawHeadBits() {
    drawBasis();
    $("es-title").textContent = est.no;
    $("es-crumb").textContent = `${est.no} ${(est.project || {}).name || ""}`;
  }
  $("es-cond").addEventListener("change", (e) => save({ options: { conditions: e.target.value.split("\n") } }, true));
  $("es-note").addEventListener("change", (e) => save({ options: { note: e.target.value } }, true));

  // ---------- 줄 입력 ----------
  const getPath = (o, path) => path.split(".").reduce((a, k) => (a == null ? a : a[k]), o);
  function setPath(o, path, v) {
    const ks = path.split(".");
    let cur = o;
    ks.slice(0, -1).forEach((k, i) => { if (cur[k] == null) cur[k] = /^\d+$/.test(ks[i + 1]) ? [] : {}; cur = cur[k]; });
    cur[ks[ks.length - 1]] = v;
  }
  const num = (v) => { const s = String(v ?? "").replace(/,/g, "").trim(); return s === "" ? null : Number(s); };
  function inp(i, path, label, opts = {}) {
    const r = est.rows[i];
    const v = getPath(r, path);
    const shown = opts.pct ? (v == null ? "" : Math.round(v * 1000) / 10) : (v ?? "");
    return `<label class="es-f${opts.w ? ` w${opts.w}` : ""}"><span>${esc(label)}</span><input data-i="${i}" data-p="${path}" data-t="${opts.text ? "text" : opts.pct ? "pct" : "num"}"
      value="${esc(shown)}"${opts.ph ? ` placeholder="${esc(opts.ph)}"` : ""}${opts.text ? "" : ' inputmode="decimal"'} />${opts.unit ? `<em>${esc(opts.unit)}</em>` : ""}</label>`;
  }
  function sel(i, path, label, options, opts = {}) {
    const v = String(getPath(est.rows[i], path) ?? "");
    return `<label class="es-f${opts.w ? ` w${opts.w}` : ""}"><span>${esc(label)}</span><select data-i="${i}" data-p="${path}" data-t="text">
      ${options.map(([k, t]) => `<option value="${esc(k)}"${String(k) === v ? " selected" : ""}>${esc(t)}</option>`).join("")}</select></label>`;
  }
  const gradeOpts = () => meta.grades.map((g) => [g, g]);
  const yearOpts = () => [["", `견적 기준(${(est.options || {}).labor_year || meta.rates.labor_year})`], ...Object.keys(meta.rates.labor).sort().reverse().map((y) => [y, `${y}년`])];

  function rowInputs(i) {
    const r = est.rows[i];
    const t = r.type;
    if (t === "sitok") {
      return `<div class="es-fs">${sel(i, "grade", "기술자 등급", gradeOpts())}${inp(i, "mandays", "전체 인·일", { unit: "인·일" })}${inp(i, "field_mandays", "외업 인·일", { unit: "인·일" })}${sel(i, "year", "노임 연도", yearOpts())}</div>
        <div class="es-fs">${inp(i, "travel.days", "여비 일수", { unit: "일" })}${inp(i, "travel.persons", "인원", { unit: "인" })}${inp(i, "travel.price", "1인 1일", { unit: "원" })}
          ${inp(i, "car.days", "차량 일수", { unit: "일" })}${inp(i, "car.count", "대수", { unit: "대" })}${inp(i, "car.price", "1대 1일", { unit: "원" })}</div>
        <div class="es-fs">${inp(i, "helper.days", "보조인부 일수", { unit: "일" })}${inp(i, "helper.persons", "인원", { unit: "인" })}${inp(i, "helper.price", "노임", { unit: "원", ph: String(meta.rates.helper_rate) })}
          ${inp(i, "danger_pct", "위험수당", { pct: true, unit: "%" })}${inp(i, "machine_pct", "기계·기구손료", { pct: true, unit: "%", ph: "정밀 5" })}</div>
        <div class="es-fs">${inp(i, "report.count", "보고서", { unit: "부" })}${inp(i, "report.price", "1부", { unit: "원" })}${inp(i, "extra", "추가조사비", { unit: "원" })}</div>`;
    }
    if (t === "blcm") {
      return `<div class="es-fs">${inp(i, "area", "연면적", { unit: "㎡" })}${inp(i, "built_year", "사용승인 연도", { ph: "예: 2011" })}${sel(i, "use", "주용도", meta.uses.map((u) => [u, u]))}
        ${sel(i, "mode", "점검", [["regular", "정기점검"], ["urgent", "긴급점검"]])}${sel(i, "structure", "구조안전 책임자", [["auto", "자동(20년 이상)"], ["yes", "넣기"], ["no", "빼기"]])}</div>
        <div class="es-fs">${inp(i, "expense", "직접경비(일괄)", { unit: "원" })}${sel(i, "year", "노임 연도", yearOpts())}</div>`;
    }
    if (t === "eng") {
      return (r.tasks || []).map((tk, ti) => `<div class="es-task"><div class="es-task-h">${inp(i, `tasks.${ti}.name`, `업무 ${ti + 1}`, { text: true, w: 3 })}
          <button type="button" class="secondary es-lineadd" data-i="${i}" data-t="${ti}">＋ 등급</button></div>
        ${(tk.lines || []).map((ln, li) => `<div class="es-fs">${sel(i, `tasks.${ti}.lines.${li}.grade`, "등급", gradeOpts())}${inp(i, `tasks.${ti}.lines.${li}.persons`, "인원", { unit: "인" })}
          ${inp(i, `tasks.${ti}.lines.${li}.days`, "일수", { unit: "일" })}<button type="button" class="es-x es-linedel" data-i="${i}" data-t="${ti}" data-l="${li}" title="빼기">✕</button></div>`).join("")}</div>`).join("")
        + `<div class="es-fs">${inp(i, "expense_pct", "직접경비(인건비의)", { pct: true, unit: "%" })}${inp(i, "report", "보고서 제작", { unit: "원" })}${sel(i, "year", "노임 연도", yearOpts())}</div>`;
    }
    if (t === "visit") {
      const bands = meta.rates.visit_bands.map((b, k) => [String(k), `${b.label} ${Number(b.rate).toLocaleString("ko-KR")}원`]);
      return `<div class="es-fs">${sel(i, "band", "공사금액 구간", [["auto", "자동(공사금액으로)"], ...bands], { w: 2 })}${inp(i, "persons", "인원", { unit: "인" })}${inp(i, "days", "일수", { unit: "일" })}</div>
        <div class="es-fs">${inp(i, "expense", "직접경비", { unit: "원" })}${inp(i, "report", "보고서 제작", { unit: "원" })}${inp(i, "period_days", "공사기간", { unit: "일", ph: "횟수 자동" })}</div>`;
    }
    return `<div class="es-fs">${inp(i, "unit", "단가(회당)", { unit: "원" })}${inp(i, "note", "비고", { text: true, w: 2 })}</div>`;
  }

  function rowCard(i) {
    const r = est.rows[i];
    const typeLabel = (meta.row_types.find((x) => x.key === r.type) || {}).label || r.type;
    return `<div class="es-rowcard" data-i="${i}">
      <div class="es-rowhead"><span class="es-no">${i + 1}</span>${inp(i, "name", kind && SITOK_KINDS.includes(est.kind) ? "시설물·조사 이름" : "구분(대상)", { text: true, w: 3, ph: "예: 교사1호동" })}
        ${inp(i, "check", "점검종류·내용", { text: true, w: 2, ph: kind ? kind.check : "" })}${inp(i, "times", "횟수", { unit: "회", ph: r.type === "visit" ? "자동" : "1" })}
        <span class="es-type">${esc(typeLabel)}</span><button type="button" class="es-x es-rowdel" data-i="${i}" title="이 줄 빼기">✕</button></div>
      <div class="es-rowbody"><div class="es-inputs">${rowInputs(i)}</div><div class="es-res" id="es-res-${i}"></div></div></div>`;
  }

  function drawRows() {
    $("es-rows").innerHTML = est.rows.map((_, i) => rowCard(i)).join("") || '<div class="empty-note">줄이 없습니다 — [＋ 줄 더하기]</div>';
    $("es-rows").querySelectorAll("[data-p]").forEach((el) => {
      const handler = (now) => {
        const i = Number(el.dataset.i);
        const v = el.dataset.t === "text" ? el.value : el.dataset.t === "pct" ? (num(el.value) == null ? null : num(el.value) / 100) : num(el.value);
        setPath(est.rows[i], el.dataset.p, v);
        saveRows(now);
      };
      if (el.tagName === "SELECT") el.addEventListener("change", () => handler(true));
      else { el.addEventListener("input", () => handler(false)); el.addEventListener("change", () => handler(true)); }
    });
    $("es-rows").querySelectorAll(".es-rowdel").forEach((b) => b.addEventListener("click", () => {
      if (!confirm("이 줄을 뺄까요?")) return;
      est.rows.splice(Number(b.dataset.i), 1);
      drawRows(); saveRows(true);
    }));
    $("es-rows").querySelectorAll(".es-lineadd").forEach((b) => b.addEventListener("click", () => {
      const r = est.rows[Number(b.dataset.i)];
      r.tasks[Number(b.dataset.t)].lines.push({ grade: "고급기술자", persons: 1, days: 1 });
      drawRows(); saveRows(true);
    }));
    $("es-rows").querySelectorAll(".es-linedel").forEach((b) => b.addEventListener("click", () => {
      est.rows[Number(b.dataset.i)].tasks[Number(b.dataset.t)].lines.splice(Number(b.dataset.l), 1);
      drawRows(); saveRows(true);
    }));
    drawResults();
  }

  // ---------- 산출 내역·합계 ----------
  function resultHtml(i) {
    const o = (est.rows_out || [])[i];
    const r = est.rows[i];
    if (!o) return "";
    const tr = (a, b, c, cls = "") => `<tr class="${cls}"><td>${esc(a)}</td><td>${esc(b)}</td><td>${won(c)}</td></tr>`;
    let body = "";
    if (r.type !== "item") {
      body += (o.lines || []).map((x) => tr(x.name, x.detail + (x.missing ? " ⚠ 노임 없음" : ""), x.amount)).join("");
      body += (o.expenses || []).map((x) => tr(x.name, x.detail, x.amount)).join("");
      body += tr("제경비", `직접인건비 × ${pct(o.overhead_rate)}`, o.overhead);
      body += tr("기술료", `(직접인건비 + 제경비) × ${pct(o.tech_rate)}`, o.tech);
      if (o.adjust) body += tr("조정비", `${o.adjust_detail} = ${o.adjust}`, o.sum * o.adjust, "es-sub");
      body += tr("산출", "만원 미만 절사" + (o.band ? ` · ${o.band}` : "") + (o.persons ? ` · 책임자 ${o.persons[0]}인·점검자 ${o.persons[1]}인` : ""), o.calc, "es-calc");
    }
    const nego = o.calc ? Math.round(o.nego * 1000) / 10 : 0;
    return `${body ? `<table class="es-tbl">${body}</table>` : ""}
      <div class="es-price"><label class="es-f w2"><span>견적 금액(회당, VAT 별도)</span><input data-i="${i}" data-p="price" data-t="num" class="es-price-in" inputmode="numeric"
        value="${r.price == null ? "" : r.price}" placeholder="${won(o.calc)}" /></label>
        <span class="es-nego">${r.price == null ? "산출 그대로" : `네고 ${nego}%`}</span>
        <span class="es-supply">× ${o.times}회 = <b>${won(o.supply)}원</b></span></div>`;
  }
  function drawResults() {
    (est.rows_out || []).forEach((_, i) => {
      const box = $(`es-res-${i}`);
      if (!box) return;
      const focused = document.activeElement && box.contains(document.activeElement);
      if (focused) { // 견적 금액 칸에 쓰는 중이면 표만
        const tbl = box.querySelector(".es-tbl");
        const tmp = document.createElement("div");
        tmp.innerHTML = resultHtml(i);
        if (tbl && tmp.querySelector(".es-tbl")) tbl.replaceWith(tmp.querySelector(".es-tbl"));
        box.querySelector(".es-nego").replaceWith(tmp.querySelector(".es-nego"));
        box.querySelector(".es-supply").replaceWith(tmp.querySelector(".es-supply"));
        return;
      }
      box.innerHTML = resultHtml(i);
      const pin = box.querySelector(".es-price-in");
      if (pin) {
        pin.addEventListener("input", () => { est.rows[i].price = num(pin.value); saveRows(false); });
        pin.addEventListener("change", () => { est.rows[i].price = num(pin.value); saveRows(true); });
      }
    });
    const t = est.totals || {};
    $("es-total").innerHTML = `<div class="es-sum"><span>산출 합 <b>${won(t.calc)}</b></span><span>견적 공급가 <b>${won(t.supply)}</b></span><span>부가세 <b>${won(t.vat)}</b></span>
        <span class="es-grand">합계(VAT 포함) <b>${won(t.total)}원</b></span></div>
      <div class="es-korean">일금 ${esc(est.korean || "")} 원 整 (VAT 포함)</div>`;
    $("es-warns").innerHTML = (est.warnings || []).map((w) => `<div class="es-warn">⚠ ${esc(w)} <a href="estimates.html#rates">기준표 열기</a></div>`).join("");
  }

  // 합계 맞추기 — 칸은 한 번만 그림(저장 응답마다 다시 그리면 치던 금액이 지워짐, 10/29 시험)
  $("es-fit-go").addEventListener("click", async () => {
    const v = num($("es-fit").value);
    if (!v) return;
    clearTimeout(saveTimer);
    await saving;
    try { est = await apiPost(`${P}/fit`, { total: v }); drawRows(); $("es-saved").textContent = "✓ 합계를 맞췄습니다"; } catch (err) { showError(errorEl, err); }
  });
  $("es-fit-clear").addEventListener("click", () => { est.rows.forEach((r) => { r.price = null; }); drawRows(); saveRows(true); });

  $("es-add").addEventListener("click", () => {
    const t = $("es-addtype").value;
    est.rows.push(newRow(t));
    drawRows(); saveRows(true, true);
  });
  function newRow(t) {
    const base = { type: t, name: "", check: kind ? kind.check : "", times: t === "visit" ? null : 1, price: null };
    const first = est.rows.find((r) => r.type === t);
    if (first) { const c = JSON.parse(JSON.stringify(first)); return { ...c, name: "", price: null }; }  // 같은 방식 줄을 본뜸(단가·인원 그대로)
    if (t === "item") return { ...base, unit: 0, note: "" };
    return base;  // 나머지 칸은 서버 기본값(clean_row)
  }

  // ---------- 엑셀·PDF ----------
  function drawFiles() {
    const f = est.files || {};
    $("es-files").innerHTML = f.xlsx ? `<div class="es-made">✓ ${esc(f.at)} 만듦${f.pages ? ` · PDF ${f.pages}쪽` : ""} · 시트 ${esc((f.sheets || []).join(", "))}
        <span class="es-links">${f.pdf ? `<a class="secondary-link" target="_blank" rel="noopener" href="${BASE}/api${P}/file/pdf?v=${encodeURIComponent(f.at)}">📄 PDF 보기</a>` : ""}
        <a class="secondary-link" href="${BASE}/api${P}/file/xlsx?v=${encodeURIComponent(f.at)}">📥 엑셀 받기</a></span>
        ${(f.notes || []).length ? `<ul>${f.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}</div>` : "";
  }
  $("es-export").addEventListener("click", async (ev) => {
    const btn = ev.currentTarget;
    clearTimeout(saveTimer);
    btn.disabled = true;
    $("es-export-msg").textContent = "저장하고 만드는 중…(PDF까지 5~15초)";
    try {
      await saving;
      await apiPatch(P, { rows: est.rows });
      const out = await apiPost(`${P}/export`, {});
      est = { ...est, ...out };
      drawFiles(); drawResults();
      $("es-export-msg").textContent = "✓ 다 만들었습니다";
    } catch (err) { $("es-export-msg").textContent = err.message; }
    btn.disabled = false;
  });

  $("es-copy").addEventListener("click", async (e) => {
    e.currentTarget.disabled = true;
    try { const n = await apiPost(`${P}/copy`, {}); location.href = `estimate.html?id=${n.id}`; } catch (err) { showError(errorEl, err); e.currentTarget.disabled = false; }
  });
  $("es-del").addEventListener("click", async () => {
    const pw = prompt(`견적 ${est.no}을(를) 지웁니다(되돌릴 수 없음) — 삭제 비밀번호`);
    if (!pw) return;
    try { await api(P, { method: "DELETE", body: JSON.stringify({ password: pw }) }); location.href = "estimates.html"; } catch (err) { showError(errorEl, err); }
  });

  (async () => {
    if (!eid) { showError(errorEl, new Error("견적 번호가 없습니다 — 목록에서 여세요.")); return; }
    try {
      [meta, est] = await Promise.all([api("/estimates/meta"), api(P)]);
      kind = meta.kinds.find((k) => k.key === est.kind) || null;
      $("es-addtype").innerHTML = meta.row_types.map((t) => `<option value="${t.key}"${kind && t.key === kind.row ? " selected" : ""}>${esc(t.label)}</option>`).join("");
      drawHead(); drawRows(); drawFiles(); drawBasis();
    } catch (err) { showError(errorEl, err); }
  })();
})();
