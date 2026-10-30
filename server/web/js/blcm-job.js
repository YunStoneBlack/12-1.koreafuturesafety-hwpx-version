// 건축물관리점검 건 화면(2026-10-29 사용자 "적합을 누르면 양호사진, 부적합을 누르고 사진을 넣으면 변경유형 판단해 체크, 기준면적은 대장·도면에서,
// 개선사항·방안근거·비고(사진설명)가 자동으로 — AI 분석은 덧붙여 다시 쓰기"). 항목표 = GET /blcm/items(매뉴얼 25.02 소항목 50개).
// 카드마다 고치면 0.6초 뒤 저장(PUT /blcm/jobs/{id}/items/{code}) → 서버가 판정(건수·점수) 계산해 돌려줌. 사진 = 신호 약하면 폰 보관(apiUploadSafe).
// 10/30 사용자(우리프라자 시험 뒤): 사진 끌어 놓기(버튼 위 = 그 종류, 빈 곳 = 판정대로), [장소별] 보기(외부·옥상·실내·지하·서류 — 보고서는 항목 순서 그대로),
// 카드 머리 ⚠ 빠진 것(서버 items.missing)·[✓ 점검 완료](빠진 것 목록 → 누르면 그 항목), 카드마다 📎 참고(우리프라자 보고서 사진·글, server/blcm/samples.json).
// 10/30 재구성(사용자 "서류검토 → 해당없음 분류·이유, 그대로 현장 점검 세팅, 사진 칸 = 적합 견본 + 부적합 유형별 견본, 도면은 관리사무소에서 한꺼번에"):
// ① 서류검토(법령 판정·질문·[서류검토 확정]) ② 관리사무소 — 도면(같은 도면은 한 줄, 쓰는 항목 모두에) ③ 현장 점검(해당없음은 맨 끝 탭, 부적합 칸에 찍으면 판정 자동 — 서버 items.apply_photos).
// 10/30 사용자 "개수에 따라 정해지는 판정은 손으로 못 바꾸게(사이트도 기준을 벗어나면 클릭이 안 됨)": 서버 items.normalize·ui_locks — 잠긴 단추는 🔒 까닭,
// 하나만 고르는 점검현황 줄은 라디오(다시 누르면 지움), 설계도서 적합여부는 판정과 맞는 쪽 + 도면없음만. 📱 현장 모드(폰 기본) = 점검현황·사진만(판정·글·AI·서류는 PC에서).
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const errorEl = $("error");
  const jid = Number(new URLSearchParams(location.search).get("id")) || 0;
  const P = `/blcm/jobs/${jid}`;
  let job = null, table = null;
  const openCards = new Set();
  let tab = (() => { try { return localStorage.getItem("bj-tab") || ""; } catch (_) { return ""; } })();
  let view = (() => { try { return localStorage.getItem("bj-view") === "big" ? "big" : "place"; } catch (_) { return "place"; } })(); // 장소별(기본) / 항목 순서(10/30)
  const narrow = () => window.matchMedia("(max-width: 760px)").matches;
  let field = (() => { try { const v = localStorage.getItem("bj-field"); return v ? v === "1" : narrow(); } catch (_) { return narrow(); } })(); // 📱 현장 모드(10/30) — 폰은 처음부터
  function setField(on, keep) {
    field = on;
    document.body.classList.toggle("bj-field", on);
    const b = $("bj-mode");
    if (b) { b.textContent = on ? "🖥 전체 보기" : "📱 현장 모드"; b.title = on ? "판정·글·AI·서류까지 모두 보기(PC 화면)" : "현장에서 — 점검현황 고르기·사진 찍기만"; }
    if (keep) { try { localStorage.setItem("bj-field", on ? "1" : "0"); } catch (_) { /* 저장 못 해도 이번엔 바뀜 */ } }
  }
  setField(field, false);
  $("bj-mode")?.addEventListener("click", () => { setField(!field, true); window.scrollTo(0, 0); });
  const RATING = ["양호", "보통", "미흡", "불량", "해당없음"], FIT = ["적합", "부적합", "해당없음"], CERT = ["인증", "재인증", "만료", "해당없음"];
  const CMP = ["개선필요", "해당없음"], DESIGN = ["적합", "부적합", "도면없음", "해당없음"];
  const TEXTS = [["ilglt", "개선사항(위법)"], ["perf", "성능개선사항"], ["basis", "개선방안에 대한 근거 및 관련법령 등"], ["rm", "비고"]];
  const B_FIELDS = [["name", "명칭"], ["address", "위치(도로명)"], ["site_area", "대지면적(㎡)"], ["building_area", "건축면적(㎡)"], ["total_area", "연면적(㎡)"],
    ["far_area", "용적률산정용 연면적(㎡)"], ["coverage", "건폐율(%)"], ["far", "용적률(%)"], ["landscape_area", "조경면적(㎡)"], ["open_space_area", "공개공지·공간 면적(㎡)"],
    ["use", "주용도"], ["zone", "용도지역"], ["district", "용도지구"], ["area_zone", "구역"], ["structure", "구조"], ["above", "지상 층수"], ["below", "지하 층수"],
    ["height", "높이(m)"], ["households", "호수/가구수/세대수"], ["permit_date", "허가일"], ["approval_date", "사용승인일"], ["seismic_design", "내진설계 적용 여부"]];
  const O_FIELDS = [["name", "성명"], ["phone", "전화번호"], ["company", "회사명"], ["address", "주소"], ["email", "전자우편"]];
  const C_FIELDS = [["amount", "점검금액(원, 부가세 포함)"], ["start", "점검기간 시작"], ["end", "점검기간 끝"], ["chief", "점검책임자"], ["inspector", "점검자"], ["inspector_phone", "점검자 전화"]];

  // ---------- 위: 개요·진행 ----------
  function drawTop() {
    $("bj-title").textContent = job.name;
    $("bj-crumb").textContent = job.name;
    document.title = `${job.name} - 건축물관리점검`;
    const b = job.building || {};
    $("bj-sub").textContent = [job.address, b.use, b.approval_date ? `사용승인 ${b.approval_date}` : ""].filter(Boolean).join(" · ");
    const pct = job.total ? Math.round((100 * job.done) / job.total) : 0;
    $("bj-bar").style.width = `${pct}%`;
    $("bj-prog-t").textContent = `항목 ${job.done}/${job.total} 작성 · 부적합·미흡 ${job.bad} · 사진 ${job.photos}장`;
    const reg = (job.files || {}).register;
    $("bj-reg-view").hidden = !reg;
    if (reg) $("bj-reg-view").href = `${BASE}/api${P}/file/register?v=${encodeURIComponent(reg.at || "")}`;
    const land = (job.files || {}).landuse;
    $("bj-land-view").hidden = !land;
    if (land) $("bj-land-view").href = `${BASE}/api${P}/file/landuse?v=${encodeURIComponent(land.at || "")}`;
    drawRecap();
  }

  function drawRecap() {
    $("bj-recap").innerHTML = (job.recap || []).map((r) => {
      const cls = !r.text ? "empty" : (r.kind === "count" && r.value > 0) || ["D", "E"].includes(r.text) ? "bad" : r.text === "C" ? "mid" : "";
      return `<div class="bj-rc ${cls}" title="${esc(r.label)} — 소항목 ${r.done}/${r.total}${r.value != null && r.kind === "grade" ? ` · ${r.value}점` : ""}"><small>${esc(r.label)}</small><b>${esc(r.text || "·")}</b></div>`;
    }).join("");
  }

  function fieldGrid(el, fields, values, prefix) {
    el.innerHTML = fields.map(([k, label]) => {
      const v = prefix === "b" && k === "name" ? job.name : prefix === "b" && k === "address" ? (job.address || values.address || "") : values[k];
      const type = /date|start|end/.test(k) ? "date" : "text";
      return `<div class="sk-f"><label>${esc(label)}</label><input data-k="${k}" type="${type}" value="${esc(v ?? "")}" /></div>`;
    }).join("");
  }
  function drawInfo() {
    fieldGrid($("bj-building"), B_FIELDS, job.building || {}, "b");
    fieldGrid($("bj-owner"), O_FIELDS, job.owner || {}, "o");
    fieldGrid($("bj-contract"), C_FIELDS, job.contract || {}, "c");
  }
  $("bj-info-save").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    const vals = (el) => Object.fromEntries([...el.querySelectorAll("input[data-k]")].map((i) => [i.dataset.k, i.value.trim()]));
    const b = vals($("bj-building"));
    const num = (v) => (v === "" || isNaN(Number(v.replace(/,/g, ""))) ? v : Number(v.replace(/,/g, "")));
    const building = Object.fromEntries(Object.entries(b).filter(([k]) => k !== "name" && k !== "address").map(([k, v]) => [k, /area|coverage|far|height|above|below/.test(k) ? num(v) : v]));
    const m = $("bj-info-msg");
    btn.disabled = true;
    try {
      job = await apiPatch(P, { name: b.name, address: b.address, building, owner: vals($("bj-owner")), contract: vals($("bj-contract")) });
      drawTop();
      m.hidden = false; m.className = "mail-msg ok"; m.textContent = "✓ 저장했습니다.";
      setTimeout(() => { m.hidden = true; }, 2000);
    } catch (err) { m.hidden = false; m.className = "mail-msg bad"; m.textContent = err.message; }
    btn.disabled = false;
  });

  const regIn = $("bj-reg");
  regIn.addEventListener("change", async () => {
    const f = regIn.files[0];
    regIn.value = "";
    if (!f) return;
    const msg = $("bj-reg-msg");
    msg.textContent = "대장 읽는 중…";
    const send = async (ai) => {
      const fd = new FormData();
      fd.append("file", f);
      fd.append("ai", ai ? "true" : "false");
      return apiUpload(`${P}/register`, fd);
    };
    try {
      let out = await send(false);
      if (out.read && !out.read.text_ok && confirm("대장에 글자가 없습니다(스캔본) — AI로 읽을까요? (약 30원)")) {
        msg.textContent = "AI로 읽는 중…(20초쯤)";
        out = await send(true);
      }
      job = out;
      drawTop(); drawInfo();
      msg.textContent = out.read && out.read.text_ok ? `✓ ${out.read.keys ? out.read.keys.length : ""}칸 읽음 — 아래 [건축물 개요]에서 확인` : "읽은 칸이 없습니다 — 직접 넣으세요";
    } catch (err) { msg.textContent = err.message; }
  });

  // 토지이용계획확인원(10/30 — 방화지구·가로구역 높이·지구단위계획을 점검 목록 답으로, 쪽은 도면 모음에)
  const landIn = $("bj-land");
  landIn.addEventListener("change", async () => {
    const f = landIn.files[0];
    landIn.value = "";
    if (!f) return;
    const msg = $("bj-reg-msg");
    msg.textContent = "확인원 읽는 중…";
    try {
      const fd = new FormData();
      fd.append("file", f);
      const out = await apiUpload(`${P}/landuse`, fd);
      plan = out.plan;
      delete out.plan;
      job = { ...job, ...out };
      drawTop(); onDrawings(out); drawReview(); drawTabs(); drawItems();
      const lu = (plan.docs || {}).landuse;
      msg.textContent = lu && lu.text_ok ? "✓ 확인원 읽음 — ① 서류검토에 답이 채워졌습니다" : "확인원에 글자가 없습니다(그림) — ① 서류검토 질문에 직접 답해 주세요";
    } catch (err) { msg.textContent = err.message; }
  });

  // ---------- 탭·카드 ----------
  const EXTRA = [["_plan", "관리계획"], ["_other", "그 밖의 항목"], ["_opinion", "개선방안·종합의견"]];
  function extraCount(k) {
    const op = job.opinion || {};
    if (k === "_plan") return [Object.keys(op.plan || {}).length, table.plan_rows.length];
    if (k === "_other") return [Object.values(op.other || {}).filter((x) => x && x.v).length, table.other_rows.length];
    return [table.opinion_keys.filter(([key]) => ((op.texts || {})[key] || "").trim()).length, table.opinion_keys.length];
  }
  // 탭 묶음 — 항목 순서 = 대항목(법규유지…), 장소별 = 현장에서 찍는 자리(@out·@roof…, 서버 items.ITEM_PLACES — 한 항목이 여러 자리에 나올 수 있음)
  // 해당없음 = 점검자가 해당없음으로 넣었거나, 법령상 해당없음이고 아직 손대지 않은 항목(① 서류검토) — 현장 탭에서 빼고 맨 끝 [해당없음] 탭에
  const isNa = (code) => { const r = (job.results || {})[code] || {}; if (r.na) return true; const p = plan && plan.items[code]; return !!(p && p.state === "na" && !p.touched); };
  function tabGroups() {
    const base = view !== "place" ? table.groups
      : (table.places || []).map(([k, label]) => ({ key: `@${k}`, label, items: table.items.map((x) => x.code).filter((c) => ((table.item_places || {})[c] || ["out"]).includes(k)) }));
    const out = base.map((g) => ({ ...g, items: g.items.filter((c) => !isNa(c)) })).filter((g) => g.items.length);
    const na = table.items.map((x) => x.code).filter(isNa);
    return na.length ? [...out, { key: "@na", label: "해당없음", items: na }] : out;
  }
  const missOf = (c) => { const e = job.eval[c] || {}; return e.state === "empty" ? [] : e.miss || []; }; // 미작성은 "미작성" 칩이 이미 말함
  function tabSmall(g) {
    const done = g.items.filter((c) => ["done", "na"].includes((job.eval[c] || {}).state)).length;
    const warn = g.items.filter((c) => missOf(c).length).length;
    return `${done}/${g.items.length}${warn ? ` <span class="bj-tab-miss" title="빠진 것이 있는 항목">⚠${warn}</span>` : ""}`;
  }
  function drawTabs() {
    const groups = tabGroups();
    if (!tab || !(groups.some((g) => g.key === tab) || EXTRA.some(([k]) => k === tab))) tab = groups[0].key;
    document.querySelectorAll(".bj-view button").forEach((b) => { const on = b.dataset.v === view; b.classList.toggle("on", on); b.setAttribute("aria-pressed", on); });
    $("bj-view-note").textContent = view === "place" ? "현장에서 찍는 자리대로 — 해당없음 항목은 맨 끝 [해당없음] 탭 · 보고서에는 항목 순서 그대로" : "매뉴얼(국토교통부 2025.2) 항목 순서 — 해당없음 항목은 맨 끝 [해당없음] 탭";
    $("bj-tabs").innerHTML = groups.map((g) => `<button type="button" class="bj-tab${g.key === tab ? " on" : ""}" data-k="${esc(g.key)}" role="tab">${esc(g.label)} <small>${tabSmall(g)}</small></button>`).join("") + EXTRA.map(([k, label]) => {
      const [n, t] = extraCount(k);
      return `<button type="button" class="bj-tab extra${k === tab ? " on" : ""}" data-k="${k}" role="tab">${esc(label)} <small>${n}/${t}</small></button>`;
    }).join("");
    $("bj-tabs").querySelectorAll(".bj-tab").forEach((b) => b.addEventListener("click", () => {
      tab = b.dataset.k;
      try { localStorage.setItem("bj-tab", tab); } catch (_) { /* */ }
      drawTabs(); drawItems();
    }));
  }
  document.querySelectorAll(".bj-view button").forEach((b) => b.addEventListener("click", () => {
    if (view === b.dataset.v) return;
    view = b.dataset.v;
    try { localStorage.setItem("bj-view", view); } catch (_) { /* */ }
    if (!tab.startsWith("_")) tab = "";
    drawTabs(); drawItems();
  }));

  // ---------- 빠진 것·[✓ 점검 완료](10/30 — 시특법 조사 완료처럼: 누를 때마다 빠진 것을 보여 주고 [이어서 점검하기]·[점검 완료], 항목을 누르면 그 자리로) ----------
  function drawDone() {
    const d = job.field_done;
    const warn = table.items.filter((x) => (job.eval[x.code] || {}).miss && (job.eval[x.code].miss || []).length).length;
    $("bj-done").classList.toggle("on", !!d);
    $("bj-done").innerHTML = d
      ? `<b class="bj-done-ok">✓ 점검 완료</b><span>${esc(d.at)} ${esc(d.by)}${d.left ? ` · 그때 빠진 것 ${d.left}곳` : ""}</span>
        <button type="button" class="secondary btn-sm bj-miss-show">빠진 것 보기</button><button type="button" class="secondary btn-sm bj-done-undo">완료 취소</button>`
      : `<button type="button" class="bj-done-btn">✓ 점검 완료</button><span>현장 점검을 다 마쳤으면 누르세요 — 빠진 항목(판정·사진·의견)이 있으면 알려 드립니다${warn ? ` · 지금 ⚠ ${warn}곳` : ""}</span>
        ${warn ? '<button type="button" class="secondary btn-sm bj-miss-show">빠진 것 보기</button>' : ""}`;
    $("bj-done").querySelector(".bj-done-btn")?.addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      try {
        await new Promise((r) => setTimeout(r, 700)); // 방금 고친 칸 저장이 먼저
        const st = await api(`${P}/check`);
        if (st.missing.length && !(await askMissing(st.missing, true))) { btn.disabled = false; return; }
        const out = await apiPost(`${P}/done`, { done: true });
        job.field_done = out.done;
        drawDone();
      } catch (err) { showError(errorEl, err); btn.disabled = false; }
    });
    $("bj-done").querySelector(".bj-done-undo")?.addEventListener("click", async () => {
      if (!confirm("점검 완료를 취소할까요?")) return;
      try { const out = await apiPost(`${P}/done`, { done: false }); job.field_done = out.done; drawDone(); } catch (err) { showError(errorEl, err); }
    });
    $("bj-done").querySelector(".bj-miss-show")?.addEventListener("click", async () => {
      try { const st = await api(`${P}/check`); if (st.missing.length) askMissing(st.missing, false); else alert("빠진 것이 없습니다."); } catch (err) { showError(errorEl, err); }
    });
  }
  function askMissing(items, finishing) { // → true = 그래도 완료
    return new Promise((resolve) => {
      const ov = document.createElement("div");
      ov.className = "mail-overlay";
      ov.innerHTML = `<div class="mail-box" role="dialog" aria-modal="true"><div class="mail-head"><b>⚠ 빠진 것 ${items.length}곳</b>
        <span class="mail-sub">해당이 없어서 비운 것인지, 아직 안 한 것인지 확인해 주세요. 항목을 누르면 그 자리로 갑니다.</span></div>
        <div class="bj-miss-list">${items.map((m, i) => `<button type="button" class="bj-miss-it" data-i="${i}"><b>${esc(m.title)}</b><span>${esc(m.text)}</span></button>`).join("")}</div>
        <div class="mail-foot"><button type="button" class="mail-cancel">${finishing ? "이어서 점검하기" : "닫기"}</button>${finishing ? '<button type="button" class="mail-primary bj-miss-ok">그래도 점검 완료</button>' : ""}</div></div>`;
      document.body.appendChild(ov);
      const done = (v) => { ov.remove(); resolve(v); };
      ov.querySelector(".mail-cancel").addEventListener("click", () => done(false));
      ov.querySelector(".bj-miss-ok")?.addEventListener("click", () => done(true));
      ov.addEventListener("mousedown", (e) => { if (e.target === ov) done(false); });
      ov.querySelectorAll(".bj-miss-it").forEach((b) => b.addEventListener("click", () => { done(false); jumpTo(items[Number(b.dataset.i)]); }));
    });
  }
  function jumpTo(m) { // 빠진 항목 → 그 탭(장소별이면 그 항목의 첫 자리) + 카드 펼치고 거기로
    if (m.code) {
      tab = isNa(m.code) ? "@na" : view === "place" ? `@${((table.item_places || {})[m.code] || ["out"])[0]}` : m.tab;
      openCards.add(m.code);
    } else tab = m.tab;
    drawTabs(); drawItems();
    const el = m.code ? document.querySelector(`.bj-card[data-code="${CSS.escape(m.code)}"]`) : $("bj-items");
    el?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function chip(ev) {
    if (!ev || ev.state === "empty") return '<span class="bj-chip empty">미작성</span>';
    if (ev.state === "na") return '<span class="bj-chip na">해당없음</span>';
    if (ev.judge) return `<span class="bj-chip ${ev.judge === "적합" ? "ok" : "bad"}">${esc(ev.summary)}</span>`;
    const worst = (ev.details || []).map((d) => d.judge).filter(Boolean);
    const bad = worst.some((j) => BAD.includes(j));
    const mid = worst.includes("보통");
    return `<span class="bj-chip ${bad ? "bad" : mid ? "mid" : "ok"}">${esc(ev.summary || "작성 중")}</span>${ev.state === "part" ? '<span class="bj-chip empty">일부</span>' : ""}`;
  }

  const BAD = ["미흡", "불량", "부적합"];
  const isBadEval = (e) => !!e && (e.judge === "부적합" || (e.details || []).some((d) => BAD.includes(d.judge))); // 지적 사진 쪽(끌어 놓기·견본 칸 📷)
  // allow = 고를 수 있는 것(서버 ui_locks — 없으면 다), always = 늘 고를 수 있는 것(해당없음), 지금 켜진 것은 끌 수 있게 둠
  const seg = (name, opts, cur, allow, always = []) => `<span class="bj-seg" data-name="${esc(name)}">${opts.map((o) => {
    const off = allow && !allow.includes(o) && !always.includes(o) && o !== cur;
    return `<button type="button" data-v="${esc(o)}" class="${o === cur ? "on" : ""}"${off ? " disabled" : ""}>${esc(o)}</button>`;
  }).join("")}</span>`;
  const lockNote = (lk) => lk ? `<small class="bj-lock" title="매뉴얼 점검기준대로 점검현황에서 정해짐 — 사이트도 기준을 벗어나면 고를 수 없음">🔒 ${esc(lk.why)}</small>` : "";

  function judgeHtml(it, r, ev) {
    const L = (ev && ev.locks) || { rt: {} };
    if (it.kind === "count") {
      const cnt = ev && ev.count != null ? ev.count : "";
      return `<div class="bj-row"><span class="bj-lab">점검 판단결과</span>${seg("judge", FIT, r.judge || (ev && ev.judge) || "", L.judge && L.judge.allow, ["해당없음"])}${lockNote(L.judge)}
        <span class="bj-cnt">건수 <input class="bj-count" type="number" min="0" max="99" value="${esc(r.count ?? "")}" placeholder="${esc(cnt)}" title="비우면 아래 변경 유형 체크 수" />건</span></div>`;
    }
    if (it.kind === "cert") {
      const c = r.cert || {};
      return it.details.map((d, i) => `<div class="bj-row"><span class="bj-lab">${esc(d.name)}</span>${seg(`cert:d${i}`, CERT, c[`d${i}`] || "")}</div>`).join("");
    }
    const rt = r.ratings || {};
    return it.details.map((d, i) => {
      const dv = (ev && ev.details && ev.details[i]) || {};
      const opts = d.judge === "fit" ? FIT : RATING;
      const one = (key, lab, pts, o) => { const lk = L.rt[key]; return `<div class="bj-sub${lk ? " locked" : ""}"><span class="bj-lab">${esc(lab)} <small>배점 ${pts}점</small></span>${seg(`rt:${key}`, o, rt[key] || "", lk && lk.allow, ["해당없음"])}${lockNote(lk)}</div>`; };
      const subs = (d.subs || []).length ? d.subs.map((s, k) => one(`d${i}.s${k}`, s.name, s.points, s.judge === "fit" ? FIT : RATING)).join("")
        : one(`d${i}`, "판정", d.points, opts);
      return `<div class="bj-det"><div class="bj-det-h"><b>${esc(d.name)}</b> <small>(${d.points ?? ""}점)</small>${dv.judge ? ` <span class="bj-chip ${BAD.includes(dv.judge) ? "bad" : dv.judge === "보통" ? "mid" : dv.judge === "해당없음" ? "na" : "ok"}">${esc(dv.judge)}${dv.score != null ? ` ${dv.score}/${dv.full}점` : ""}</span>` : ""}</div>${subs}</div>`;
    }).join("");
  }

  function statusHtml(it, r) {
    const st = r.status || {};
    if (!(it.status || []).length) return "";
    const grp = {}; // 하나만 고르는 칸(사이트 라디오, 10/30) → 묶음 번호
    (it.radios || []).forEach((g, gi) => g.forEach((k) => { grp[k] = gi; }));
    const ruled = Object.keys(it.rules || {}).length;
    return `<div class="bj-status"><div class="bj-lab">세부항목 점검현황${ruled ? ' <small>— 개수·거리·숫자를 고르면 판정이 자동(🔒)</small>' : ""}</div>${it.status.map((ln, li) => `<div class="bj-sline">${ln.map((t, ti) => {
      const key = `l${li}t${ti}`;
      if (t.t === "check" && grp[key] != null) return `<label class="bj-ck bj-rd"><input type="radio" name="st-${esc(it.code)}-${grp[key]}" data-st="${key}" ${st[key] === true ? "checked" : ""} /> ${esc(t.v)}</label>`;
      if (t.t === "check") return `<label class="bj-ck"><input type="checkbox" data-st="${key}" ${st[key] === true ? "checked" : ""} /> ${esc(t.v)}</label>`;
      if (t.t === "blank") return `<input class="bj-blank" data-st="${key}" value="${esc(st[key] === true ? "" : st[key] || "")}" />${t.unit ? `<span class="bj-unit">${esc(t.unit)}</span>` : ""}`;
      return `<span class="bj-txt">${esc(t.v)}</span>`;
    }).join("")}</div>`).join("")}</div>`;
  }

  const sampleSrc = (file) => `${BASE}/api/blcm/samples/${encodeURIComponent(file)}`;
  const slotsOf = (code) => (table.slots || {})[code] || { photo: [], draw: [] };
  const badTypes = (code) => (table.bad_types || {})[code] || [];
  const isDrawPhoto = (code, p) => !!(p.is_draw || p.drawing || (p.slot != null && slotsOf(code).draw.some((s) => s.n === p.slot)));
  function photoOne(it, p) { // 사진 한 장 — 아래 고르기 = 적합(양호)인지 어떤 부적합인지(바꾸면 판정도 바뀜)
    const bt = badTypes(it.code);
    const val = p.kind === "bad" ? ((p.bad || {}).key || "__bad") : "";
    return `<div class="bj-ph ${p.kind === "bad" ? "bad" : "good"}${p.evidence ? " ev" : ""}" data-pid="${esc(p.id)}">
      <a href="${BASE}/api${P}/photo/${esc(p.id)}" target="_blank" rel="noopener"><img loading="lazy" src="${BASE}/api${P}/photo/${esc(p.id)}" alt="" /></a>
      <div class="bj-ph-b">${p.evidence ? `<span class="bj-ph-ev" title="① 서류검토 확정 때 넣은 해당없음 근거 그림">📄 근거·${esc(p.evidence)}</span>` : `<select class="bj-ph-type" title="적합(양호) 사진인지, 어떤 부적합인지 — 바꾸면 판정도 바뀝니다">
        <option value=""${val === "" ? " selected" : ""}>✅ 적합·양호</option>${bt.map((t) => `<option value="${esc(t.key)}"${val === t.key ? " selected" : ""}>⚠ ${esc(t.label)}</option>`).join("")}
        ${val === "__bad" || !bt.length ? `<option value="__bad"${val === "__bad" ? " selected" : ""}>⚠ 지적(유형 없음)</option>` : ""}</select>`}
        ${p.slot != null && p.kind !== "bad" ? `<label class="bj-ph-redo" title="다시 찍기">📷<input type="file" accept="image/*" capture="environment" hidden data-kr-file="skip" data-slot="${p.slot}" /></label>` : ""}
        <button type="button" class="bj-ph-del" title="지우기">✕</button></div>
      <input class="bj-ph-cap" value="${esc(p.caption || "")}" placeholder="사진 설명" maxlength="60" /></div>`;
  }
  function photosHtml(it, r) { // 10/30 사용자: ✅ 적합 = 견본 칸(왼쪽 견본 | 오른쪽 이번 사진) + 더 찍기, ⚠ 부적합 = 유형 칸마다 견본 + 📷(찍으면 판정·변경 유형 체크 자동), 도면은 ②에서
    const all = r.photos || [];
    const ph = all.filter((p) => !isDrawPhoto(it.code, p));
    if (r.na) { // 해당없음 — 견본 칸 없이 근거 그림(① 서류검토 확정)·넣은 사진만
      return `<div class="bj-photos"><div class="bj-lab">📄 해당없음 근거 <small>① 서류검토 확정 때 넣은 그림(대장 칸·확인원·법령 조문 빨간 네모) — 보고서 현황사진으로 들어갑니다</small></div>
        <div class="bj-ph-grid">${all.map((p) => photoOne(it, p)).join("") || '<div class="mail-note">근거 그림 없음 — 현장 조사로 해당없음이면 현장 사진을 넣어도 됩니다</div>'}</div>
        <div class="bj-ph-add"><label class="secondary bj-file-btn">📷 사진 더하기<input type="file" accept="image/*" multiple hidden data-kr-file="skip" data-kind="good" /></label><span class="mail-note bj-ph-msg"></span></div></div>`;
    }
    const sl = slotsOf(it.code), bt = badTypes(it.code);
    const nums = new Set(sl.photo.map((s) => s.n));
    const okSlot = (s) => {
      const p = ph.find((x) => x.slot === s.n && x.kind !== "bad");
      return `<div class="bj-slot" data-slot="${s.n}">
        <div class="bj-slot-ex"><span class="bj-slot-tag">견본</span>${s.file ? `<a href="${sampleSrc(s.file)}" target="_blank" rel="noopener"><img loading="lazy" src="${sampleSrc(s.file)}" alt="" /></a>` : ""}<small>${esc(s.caption || "(설명 없음)")}${s.from ? ` <span class="bj-slot-from">· ${esc(s.from)}</span>` : ""}</small></div>
        <div class="bj-slot-now">${p ? photoOne(it, p) : `<label class="bj-slot-shot">📷 이렇게 찍기<small>${esc(s.caption || "")}</small><input type="file" accept="image/*" capture="environment" hidden data-kr-file="skip" data-slot="${s.n}" /></label>`}</div></div>`;
    };
    const goodExtra = ph.filter((p) => p.kind !== "bad" && (p.slot == null || !nums.has(p.slot)));
    const badRow = (t) => {
      const mine = ph.filter((p) => p.kind === "bad" && (p.bad || {}).key === t.key);
      const s0 = (t.samples || [])[0];
      return `<div class="bj-bad-row${mine.length ? " has" : ""}" data-bad="${esc(t.key)}">
        <div class="bj-bad-ex">${s0 ? `<a href="${sampleSrc(s0.file)}" target="_blank" rel="noopener"><img loading="lazy" src="${sampleSrc(s0.file)}" alt="" /></a>` : '<span class="bj-bad-none">견본<br>준비 중</span>'}</div>
        <div class="bj-bad-t"><b>⚠ ${esc(t.label)}</b>${s0 ? `<small>${esc(s0.caption || "")}${s0.from ? ` · ${esc(s0.from)}` : ""}${s0.ok === false ? ' <span class="bs-st todo">견본 검토 전</span>' : ""}</small>` : ""}
          <label class="bj-bad-shot">📷 찍기${mine.length ? ` · ${mine.length}장` : ""}<input type="file" accept="image/*" multiple hidden data-kr-file="skip" data-bad="${esc(t.key)}" /></label></div>
        ${mine.length ? `<div class="bj-ph-grid bj-bad-ph">${mine.map((p) => photoOne(it, p)).join("")}</div>` : ""}</div>`;
    };
    const nBad = ph.filter((p) => p.kind === "bad").length;
    const loose = ph.filter((p) => p.kind === "bad" && !(p.bad && bt.some((t) => t.key === p.bad.key)));
    const nDraw = sl.draw.length, gotDraw = new Set(all.filter((p) => isDrawPhoto(it.code, p)).map((p) => p.slot)).size;
    return `<div class="bj-photos">
      <div class="bj-ok-box"><div class="bj-lab">✅ 적합 <small>${sl.photo.length ? "왼쪽 견본(회사 제출 보고서)처럼 찍으세요 — 더 찍어도, 덜 찍어도 됩니다" : "현장 사진"}</small></div>
        ${sl.photo.length ? `<div class="bj-slots">${sl.photo.map(okSlot).join("")}</div>` : ""}
        <div class="bj-ph-add"><label class="secondary bj-file-btn">📷 ${sl.photo.length ? "＋ 더 찍기" : "사진 찍기"}<input type="file" accept="image/*" multiple hidden data-kr-file="skip" data-kind="good" /></label><span class="mail-note bj-ph-msg">장수 제한 없음 · 끌어 놓아도 됩니다</span></div>
        ${goodExtra.length ? `<div class="bj-ph-grid">${goodExtra.map((p) => photoOne(it, p)).join("")}</div>` : ""}</div>
      ${bt.length ? `<details class="bj-bad-box"${nBad ? " open" : ""}><summary>⚠ 부적합이 있으면 — 해당 칸에 찍으면 판정이 자동으로 <small>${bt.length}칸${nBad ? ` · 지적 ${nBad}장` : ""} ▾</small></summary>
        <div class="bj-bad-rows">${bt.map(badRow).join("")}</div>
        <div class="mail-note bj-bs-link">견본 = 회사 제출 보고서 부적합 사진 · <a href="blcm-samples.html#${encodeURIComponent(it.code)}" target="_blank" rel="noopener">🖼 부적합 견본 고르기</a></div></details>` : ""}
      ${loose.length ? `<div class="bj-lab">⚠ 유형 없는 지적 사진 <small>사진 아래에서 유형을 고르면 판정에 들어갑니다</small></div><div class="bj-ph-grid">${loose.map((p) => photoOne(it, p)).join("")}</div>` : ""}
      ${nDraw ? `<div class="mail-note bj-draw-note">📐 도면 ${gotDraw}/${nDraw} — 도면은 위 [② 관리사무소 — 도면]에서 한꺼번에 넣습니다</div>` : ""}</div>`;
  }

  function aiNote(r, ev) { // 판정을 비워 두고 사진만 넣었으면 AI가 사진을 보고 판정까지(10/30 사용자 "사진을 보고 선택하고 AI 작성까지")
    if (r.ai && r.ai.made_at) return `<span class="mail-note bj-ai-msg">AI ${esc(r.ai.made_at)}</span>`;
    if ((r.photos || []).length && (!ev || ev.state === "empty" || ev.state === "part")) return '<span class="mail-note bj-ai-msg warn">판정이 비어 있음 — [🤖 AI로 채우기]를 누르면 사진을 보고 판정·점검현황 체크·글까지 제안합니다</span>';
    return '<span class="mail-note bj-ai-msg">판정을 비워 두면 사진을 보고 판정까지 · 사진·대장·견본으로 점검현황·글을 채움(약 30~60원)</span>';
  }

  function refHtml(it) { // 📎 참고 — 우리프라자 보고서 같은 항목 현황사진·글(10/30 사용자 "전회차 사진처럼 샘플 참고사진 — 더 찍을 수도, 덜 찍을 수도 있지만 일단 보여주기")
    const s = (table.samples || {})[it.code];
    if (!s) return "";
    const ph = s.photos || [];
    const tx = Object.entries(table.text_keys || {}).filter(([k]) => (s[k] || "").trim() && s[k].trim() !== "-");
    if (!tx.length) return ""; // 사진은 위 견본 칸에 — 여기는 글만
    return `<details class="bj-ref"><summary>📎 견본 글 — ${esc(s.from)} 보고서 <small class="mail-note">(이 항목을 이렇게 썼음 — 펼치기${ph.length ? ` · 사진 ${ph.length}장은 위 견본 칸` : ""})</small></summary>
      <div class="bj-ref-tx">${tx.map(([k, lab]) => `<div><b>${esc(lab)}</b> ${esc(s[k])}</div>`).join("")}</div></details>`;
  }

  function cardHtml(it) {
    const r = (job.results || {})[it.code] || {};
    const ev = job.eval[it.code];
    const tx = r.texts || {};
    const nPh = (r.photos || []).length;
    const miss = missOf(it.code);
    const pl = ((table.item_places || {})[it.code] || []).map((k) => ((table.places || []).find((x) => x[0] === k) || [k, k])[1]);
    const th = (slotsOf(it.code).photo[0] || {}).file;
    const pi = plan && plan.items[it.code];
    const ask = pi && pi.state === "ask" && pi.cat === "present" ? pi.asks : [];
    const naWhy = pi && pi.state === "na" && !r.na ? `<div class="mail-note bj-na-why">법령상 해당없음 — ${esc(pi.reason)} <small>([① 서류검토 확정]을 누르면 해당없음·사유가 들어갑니다)</small></div>` : "";
    return `<summary class="bj-card-h">${th ? `<img class="bj-card-th" loading="lazy" src="${sampleSrc(th)}" alt="" />` : ""}<span class="bj-code">${esc(it.code)}</span><b>${esc(it.name)}</b><span class="bj-mid">${esc(view === "place" ? it.big : it.mid)}</span>${chip(ev)}${planChip(it.code)}${miss.length ? `<span class="bj-miss" title="${esc(miss.join(" · "))}">⚠ ${esc(miss[0])}${miss.length > 1 ? ` 외 ${miss.length - 1}` : ""}</span>` : ""}${nPh ? `<span class="bj-nph">📷${nPh}</span>` : ""}${r.ai ? '<span class="bj-nph" title="AI로 채움">🤖</span>' : ""}${view === "place" && pl.length > 1 ? `<span class="bj-places" title="이 항목을 찍는 자리">${esc(pl.join("·"))}</span>` : ""}<span class="sk-fold-arrow">▾</span></summary>
      <div class="bj-card-b">${naWhy}
        ${ask.map((k) => { const q = (plan.questions || []).find((x) => x.key === k) || { label: k };
          return `<div class="bj-pl-q bj-ask"><span>📍 ${esc(q.label)} <small>법령상 의무는 아니지만 있으면 점검 — 없으면 해당없음으로 넘어갑니다</small></span>
            <span class="bj-seg bj-fact" data-key="${esc(k)}" data-user="">${["있음", "없음"].map((v) => `<button type="button" data-v="${v}">${v}</button>`).join("")}</span></div>`; }).join("")}
        <label class="bj-na"><input type="checkbox" class="bj-na-in" ${r.na ? "checked" : ""} /> 이 항목 해당없음(적용 대상 아님 — 비고에 사유)</label>
        <div class="bj-judge"${r.na ? " hidden" : ""}>${judgeHtml(it, r, ev)}
          <div class="bj-row"><span class="bj-lab">현행기준과의 비교·검토</span>${seg("cmp", CMP, r.cmp || "")}</div>
          <div class="bj-row"><span class="bj-lab">설계도서(사용승인도면 등)와의 적합여부</span>${seg("design", DESIGN, r.design || "", ev && ev.locks && ev.locks.design)}<small class="bj-lock" title="생애이력시스템과 같은 규칙 — 판정이 적합·양호·보통이면 적합, 미흡·불량·부적합이면 부적합, 해당없음이면 해당없음, 도면없음은 늘">판정과 맞는 쪽 + 도면없음만</small></div>
          ${statusHtml(it, r)}</div>
        ${photosHtml(it, r)}
        ${refHtml(it)}
        <div class="bj-ai"><input class="bj-ai-note" maxlength="600" placeholder="AI에 덧붙일 내용 — 실측 면적·도면 비교 결과·위치·개수(예: 실측 조경면적 120.80㎡, 1층 우측 실외기 2대)" />
          <button type="button" class="bj-ai-go">🤖 AI로 채우기</button>${aiNote(r, ev)}</div>
        <div class="bj-texts">${TEXTS.map(([k, lab]) => `<div class="sk-f"><label>${esc(lab)}</label><textarea data-tx="${k}" rows="${k === "basis" ? 3 : 2}" maxlength="3000">${esc(tx[k] || "")}</textarea></div>`).join("")}</div>
        <details class="bj-man"><summary>📘 매뉴얼 점검기준 · 개선방안 안내 · 관련법규</summary>
          <div class="bj-man-b">${(it.criteria || []).map((x) => `<div>${esc(x)}</div>`).join("")}<div class="bj-law">※관련법규: ${esc(it.laws || "-")}</div></div></details>
      </div>`;
  }

  function drawItems() {
    if (tab.startsWith("_")) { drawExtra(); return; }
    const g = tabGroups().find((x) => x.key === tab);
    const box = $("bj-items");
    box.innerHTML = "";
    for (const code of g.items) {
      const it = table.byCode[code];
      const el = document.createElement("details");
      el.className = "bj-card";
      el.dataset.code = code;
      el.open = openCards.has(code);
      el.innerHTML = cardHtml(it);
      el.addEventListener("toggle", () => { if (el.open) openCards.add(code); else openCards.delete(code); });
      wire(el, it);
      box.appendChild(el);
    }
  }

  function redraw(el, it) {
    const open = el.open;
    el.innerHTML = cardHtml(it);
    el.open = open;
    wire(el, it);
    drawTop();
    const done = job.done;
    refreshTabCounts();
    drawDone();
    drawReview();
    return done;
  }

  function refreshTabCounts() {
    $("bj-tabs").querySelectorAll(".bj-tab").forEach((b) => {
      const k = b.dataset.k;
      if (k.startsWith("_")) { const [n, t] = extraCount(k); b.querySelector("small").textContent = `${n}/${t}`; return; }
      const gg = tabGroups().find((x) => x.key === k);
      if (gg) b.querySelector("small").innerHTML = tabSmall(gg);
    });
  }

  function apply(code, out) {
    job.results = { ...(job.results || {}), [code]: out.result };
    job.eval = { ...job.eval, [code]: out.eval };
    if (out.progress) Object.assign(job, out.progress);
    if (out.recap) job.recap = out.recap;
  }

  // ---------- 관리계획·그 밖의 항목·개선방안 의견(탭 셋) ----------
  let opTimer = null, opSaving = Promise.resolve();
  function saveOpinion(body, now) {
    clearTimeout(opTimer);
    const go = () => {
      opSaving = opSaving.then(() => api(`${P}/opinion`, { method: "PUT", body: JSON.stringify(body()) })).then((out) => {
        job.opinion = out.opinion;
        job.plan_grade = out.plan_grade;
        refreshTabCounts();
        const g = document.querySelector(".bj-plan-grade");
        if (g) g.outerHTML = planGradeHtml();
      }).catch((err) => showError(errorEl, err));
    };
    if (now) go(); else opTimer = setTimeout(go, 600);
  }
  const planGradeHtml = () => `<span class="bj-chip bj-plan-grade ${job.plan_grade === "적합" ? "ok" : job.plan_grade === "부적합" ? "bad" : "empty"}">${esc(job.plan_grade || "미작성")}</span>`;

  function drawExtra() {
    const box = $("bj-items");
    const op = job.opinion || {};
    if (tab === "_plan") {
      const plan = op.plan || {};
      box.innerHTML = `<div class="bj-pane"><div class="bj-pane-h">건축물관리계획의 수립 및 이행이 적합한지 여부 ${planGradeHtml()} — 하나라도 부적합이면 부적합(매뉴얼 2.5.3, 관리계획서·장기수선계획 근거)
          <button type="button" class="secondary" id="bj-plan-all">모두 적합</button></div>
        ${table.plan_rows.map(([code, label]) => `<div class="bj-prow"><span class="bj-lab">${esc(label)}</span>${seg(`plan:${code}`, ["적합", "부적합"], plan[code] || "")}</div>`).join("")}</div>`;
      const body = () => ({ plan: Object.fromEntries([...box.querySelectorAll(".bj-seg")].map((s) => [s.dataset.name.slice(5), (s.querySelector("button.on") || {}).dataset?.v || ""]).filter(([, v]) => v)) });
      box.querySelectorAll(".bj-seg button").forEach((b) => b.addEventListener("click", () => {
        const was = b.classList.contains("on");
        b.parentElement.querySelectorAll("button").forEach((x) => x.classList.remove("on"));
        if (!was) b.classList.add("on");
        saveOpinion(body, true);
      }));
      $("bj-plan-all").addEventListener("click", () => {
        box.querySelectorAll(".bj-seg").forEach((s) => s.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x.dataset.v === "적합")));
        saveOpinion(body, true);
      });
      return;
    }
    if (tab === "_other") {
      const other = op.other || {};
      box.innerHTML = `<div class="bj-pane"><div class="bj-pane-h">그 밖의 항목에 대한 이행 여부 — 점검 당시 검사 완료 '예', 기한 내 미이행 '아니오', 진행 중·그 외 '기타'(사유), 해당없음.
          일자 칸 = 점검·검사 받은 날 또는 사유</div>
        ${table.other_rows.map(([code, label, hint]) => {
          const v = other[code] || {};
          return `<div class="bj-prow" data-code="${code}"><span class="bj-lab">${esc(label)}</span>${seg(`other:${code}`, table.other_values, v.v || "")}
            <input class="bj-onote" maxlength="100" value="${esc(v.note || "")}" placeholder="${esc(hint || "점검·검사 일자 또는 사유")}" /></div>`;
        }).join("")}</div>`;
      const body = () => ({ other: Object.fromEntries([...box.querySelectorAll(".bj-prow")].map((r) => [r.dataset.code, { v: (r.querySelector("button.on") || {}).dataset?.v || "", note: r.querySelector(".bj-onote").value.trim() }])) });
      box.querySelectorAll(".bj-seg button").forEach((b) => b.addEventListener("click", () => {
        const was = b.classList.contains("on");
        b.parentElement.querySelectorAll("button").forEach((x) => x.classList.remove("on"));
        if (!was) b.classList.add("on");
        saveOpinion(body, true);
      }));
      box.querySelectorAll(".bj-onote").forEach((i) => { i.addEventListener("input", () => saveOpinion(body, false)); i.addEventListener("change", () => saveOpinion(body, true)); });
      return;
    }
    const tx = op.texts || {};
    box.innerHTML = `<div class="bj-pane"><div class="bj-pane-h">주요 개선방안에 대한 의견 · 종합의견(2000자 내외) — 3장 점검 결과·관리계획·그 밖의 항목을 모아 AI가 씀(매뉴얼 2.5.4·2.5.5)</div>
        <div class="bj-ai"><input class="bj-ai-note" id="bj-op-note" maxlength="600" placeholder="AI에 덧붙일 내용(예: 옥상 방수 보수 이력 있음, 복도 적치물 시정조치함)" />
          <button type="button" id="bj-op-ai">🤖 AI로 의견 쓰기</button><span class="mail-note" id="bj-op-msg">${op.ai && op.ai.made_at ? `AI ${esc(op.ai.made_at)}` : "점검 결과 전부로 여섯 칸을 씀(약 50~100원)"}</span></div>
        <div class="bj-op">${table.opinion_keys.map(([k, lab]) => `<div class="sk-f${k === "total" ? " total" : ""}"><label>${esc(lab)}</label>
          <textarea data-op="${k}" rows="${k === "total" ? 7 : 4}" maxlength="2500">${esc(tx[k] || "")}</textarea></div>`).join("")}</div></div>`;
    const body = () => ({ texts: Object.fromEntries([...box.querySelectorAll("[data-op]")].map((t) => [t.dataset.op, t.value])) });
    box.querySelectorAll("[data-op]").forEach((t) => {
      t.addEventListener("input", () => saveOpinion(body, false));
      t.addEventListener("change", () => saveOpinion(body, true));
      if (typeof aiRewrite === "function") aiRewrite(t, `${P}/ai/rewrite`, `주요 개선방안 의견 — ${table.opinion_keys.find((x) => x[0] === t.dataset.op)[1]}`);
    });
    $("bj-op-ai").addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      if (Object.values(body().texts).some((v) => v.trim()) && !confirm("지금 적힌 의견 칸을 AI 글로 바꿉니다 — 계속할까요?")) return;
      clearTimeout(opTimer);
      await opSaving;
      btn.disabled = true;
      $("bj-op-msg").textContent = "AI가 점검 결과를 모아 쓰는 중…(30~60초)";
      try {
        await api(`${P}/opinion`, { method: "PUT", body: JSON.stringify(body()) });
        const out = await apiPost(`${P}/opinion/ai`, { extra: $("bj-op-note").value.trim() });
        job.opinion = out.opinion;
        job.plan_grade = out.plan_grade;
        drawExtra();
        refreshTabCounts();
        $("bj-op-msg").textContent = "✓ AI로 썼습니다 — 확인하고 고치세요";
      } catch (err) { $("bj-op-msg").textContent = err.message; btn.disabled = false; }
    });
  }

  // ---------- 보고서 만들기(표지·명단·서류·최종 PDF) ----------
  let persons = [], people = [];
  const ROLE0 = "과업 책임기술자", ROLE1 = "현장조사 및 보고서 작성";
  function drawReportInfo() {
    const c = job.contract || {};
    const end = String(c.end || "");
    const ym = c.report_ym || (/^\d{4}-\d{2}/.test(end) ? end.slice(0, 7) : "");
    $("bj-rp-info").innerHTML = `<div class="sk-f"><label>과업명</label><input data-rk="title" value="${esc(c.title || "")}" placeholder="${esc(`${job.name} 건축물관리법 정기안전점검 용역`)}" /></div>
      <div class="sk-f"><label>보고 연월(표지·제출문)</label><input data-rk="report_ym" type="month" value="${esc(ym)}" /></div>
      <div class="sk-f"><label>분야(명단)</label><input data-rk="field" value="${esc(c.field || "건축")}" /></div>`;
  }
  function personRow(x, i) {
    const opts = persons.map((p) => `<option value="${p.id}"${x.person_id === p.id ? " selected" : ""}>${esc(p.name)}</option>`).join("");
    const pp = persons.find((p) => p.id === x.person_id);
    const edu = !x.person_id ? '<span class="mail-note">기술자 목록에 없음</span>'
      : pp && pp.edu ? `<a class="secondary-link" target="_blank" rel="noopener" href="${BASE}/api/blcm/persons/${x.person_id}/edu?v=${pp.edu_ts}">✓ 이수증</a>`
        : `<label class="secondary bj-file-btn bad">📎 이수증<input type="file" accept="image/*,.pdf,application/pdf" hidden data-kr-file="skip" data-edu="${x.person_id}" /></label>`;
    return `<div class="bj-person" data-i="${i}"><select data-pk="person_id"><option value="">직접 입력</option>${opts}</select>
      <input data-pk="role" value="${esc(x.role || (i ? ROLE1 : ROLE0))}" placeholder="참여세부 과업내용" />
      ${x.person_id ? `<input data-pk="position" value="${esc(x.position || "")}" placeholder="직위" />` : `<input data-pk="name" value="${esc(x.name || "")}" placeholder="성명" />`}
      ${x.person_id ? `<input data-pk="grade" value="${esc(x.grade || "")}" placeholder="자격 및 등급" />` : `<input data-pk="position" value="${esc(x.position || "")}" placeholder="직위" />`}
      ${x.person_id ? `<span class="bj-p-edu">${edu}</span>` : `<input data-pk="grade" value="${esc(x.grade || "")}" placeholder="자격 및 등급" />`}
      <input data-pk="note" value="${esc(x.note || "-")}" placeholder="비고" />
      <button type="button" class="secondary bj-p-del" title="빼기">✕</button></div>`;
  }
  function readPeople() {
    return [...$("bj-people").querySelectorAll(".bj-person[data-i]")].map((row) => {
      const v = (k) => { const el = row.querySelector(`[data-pk="${k}"]`); return el ? el.value.trim() : ""; };
      const pid = Number(v("person_id")) || null;
      const pp = persons.find((p) => p.id === pid);
      const old = people[Number(row.dataset.i)] || {};
      return { person_id: pid, role: v("role"), name: pp ? pp.name : (v("name") || old.name || ""), position: v("position"), grade: v("grade") || (pid ? old.grade || "" : ""), note: v("note") || "-" };
    });
  }
  function drawPeople() {
    $("bj-people").innerHTML = `<div class="bj-person bj-person-h"><span>기술자</span><span>참여세부 과업내용</span><span>직위 / 성명</span><span>자격 및 등급 / 직위</span><span>이수증 / 등급</span><span>비고</span><span></span></div>`
      + (people.map(personRow).join("") || '<div class="mail-note">명단이 비었습니다 — [＋ 기술자 더하기]</div>');
    $("bj-people").querySelectorAll(".bj-person[data-i]").forEach((row) => {
      const i = Number(row.dataset.i);
      row.querySelector('[data-pk="person_id"]').addEventListener("change", (e) => {
        people = readPeople();
        const pp = persons.find((p) => p.id === Number(e.target.value));
        people[i] = pp ? { ...people[i], person_id: pp.id, name: pp.name, position: pp.position, grade: pp.grade } : { ...people[i], person_id: null };
        drawPeople();
      });
      row.querySelector(".bj-p-del").addEventListener("click", () => { people = readPeople(); people.splice(i, 1); drawPeople(); });
      const f = row.querySelector("input[data-edu]");
      if (f) f.addEventListener("change", async () => {
        const file = f.files[0];
        if (!file) return;
        const fd = new FormData();
        fd.append("file", file);
        try { persons = (await apiUpload(`/blcm/persons/${f.dataset.edu}/edu`, fd)).persons; people = readPeople(); drawPeople(); } catch (err) { showError(errorEl, err); }
      });
    });
  }
  $("bj-person-add").addEventListener("click", () => {
    people = readPeople();
    const used = new Set(people.map((x) => x.person_id));
    const pp = persons.find((p) => !used.has(p.id));
    people.push(pp ? { person_id: pp.id, name: pp.name, position: pp.position, grade: pp.grade, role: people.length ? ROLE1 : ROLE0, note: "-" } : { person_id: null, role: ROLE1, note: "-" });
    drawPeople();
  });
  async function saveReportInfo() {
    const vals = Object.fromEntries([...$("bj-rp-info").querySelectorAll("[data-rk]")].map((i) => [i.dataset.rk, i.value.trim()]));
    people = readPeople();
    job = { ...job, ...(await apiPatch(P, { contract: { ...vals, people: people.filter((x) => x.person_id || x.name) } })) };  // 이름 없는 줄은 저장 안 함
  }
  $("bj-rp-save").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    try { await saveReportInfo(); $("bj-rp-msg").textContent = "✓ 저장했습니다"; setTimeout(() => { $("bj-rp-msg").textContent = ""; }, 2000); } catch (err) { $("bj-rp-msg").textContent = err.message; }
    btn.disabled = false;
  });

  const DOCS = [["cover", "📷 표지 사진", "건물 전경 — 표지 사진 틀에 맞춰 가운데를 잘라 넣음", "image/*"],
    ["contract_doc", "📄 계약서", "부록.1 — PDF 또는 사진(여러 쪽이면 PDF)", "image/*,.pdf,application/pdf"],
    ["site_pdf", "📄 생애이력시스템 보고서", "사이트 보고서작성 → [점검보고서 출력] → PDF로 저장한 파일(본문, 목차 쪽 번호를 여기서 찾음)", ".pdf,application/pdf"]];
  function drawDocs() {
    const fl = job.files || {};
    $("bj-docs").innerHTML = DOCS.map(([k, label, hint, accept]) => {
      const f = fl[k];
      const url = f ? `${BASE}/api${P}/file/${k}?v=${encodeURIComponent(f.at || "")}` : "";
      const info = f ? (k === "site_pdf" && f.pages ? `${f.pages}쪽 · 목차 ${Object.keys(f.toc || {}).length}/9 찾음 · ${esc(f.at)}` : `${esc(f.name || "")} · ${esc(f.at || "")}`) : esc(hint);
      return `<div class="bj-doc" data-k="${k}"><b>${label}</b>${f && k === "cover" ? `<img src="${url}" alt="" />` : ""}<span class="mail-note">${info}</span>
        <div class="bj-doc-btns"><label class="secondary bj-file-btn">${f ? "바꾸기" : "올리기"}<input type="file" accept="${accept}" hidden data-kr-file="skip" /></label>
          ${f ? `<a class="secondary-link" target="_blank" rel="noopener" href="${url}">보기</a><button type="button" class="secondary bj-doc-del">✕</button>` : ""}</div></div>`;
    }).join("");
    $("bj-docs").querySelectorAll(".bj-doc").forEach((d) => {
      const k = d.dataset.k;
      d.querySelector("input[type=file]").addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const fd = new FormData();
        fd.append("file", file);
        d.querySelector(".mail-note").textContent = "올리는 중…";
        try { job = { ...job, ...(await apiUpload(`${P}/doc/${k}`, fd)) }; drawDocs(); } catch (err) { d.querySelector(".mail-note").textContent = err.message; }
      });
      const del = d.querySelector(".bj-doc-del");
      if (del) del.addEventListener("click", async () => {
        if (!confirm("이 서류를 뺄까요?")) return;
        try { job = { ...job, ...(await api(`${P}/doc/${k}`, { method: "DELETE" })) }; drawDocs(); } catch (err) { showError(errorEl, err); }
      });
    });
    drawMade();
  }
  function drawMade() {
    const r = (job.files || {}).report;
    $("bj-made").innerHTML = r ? `<div class="bj-made">✓ ${esc(r.at)} 만듦 — ${r.pages}쪽(앞부분 ${r.front} · 본문 ${r.site} · 계약서 ${r.contract} · 이수증 ${r.edu}) · ${r.mb}MB
        <a class="secondary-link" target="_blank" rel="noopener" href="${BASE}/api${P}/file/report?v=${encodeURIComponent(r.at || "")}">📄 보고서 보기·받기</a>
        ${(r.notes || []).length ? `<ul>${r.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}</div>` : "";
  }
  $("bj-make").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    const msg = $("bj-make-msg");
    if (!(job.files || {}).site_pdf) { msg.textContent = "생애이력시스템 보고서 PDF를 먼저 올려 주세요."; return; }
    btn.disabled = true;
    msg.textContent = "저장하고 만드는 중…(한글로 표지를 그려 20~60초)";
    try {
      await saveReportInfo();
      job = { ...job, ...(await apiPost(`${P}/report`, {})) };
      msg.textContent = "✓ 다 만들었습니다";
      drawMade();
    } catch (err) { msg.textContent = err.message; }
    btn.disabled = false;
  });
  // ---------- 생애이력시스템 입력(봇) ----------
  let runTimer = null;
  const ST = { ok: "✓", warn: "⚠", fail: "✗", skip: "·" };
  const MODE = { list: "사이트 목록 읽기", practice: "연습(채워 보기)", save: "입력·저장" };
  async function drawAccount() {
    try {
      const a = await api("/blcm/account");
      $("bj-acc").innerHTML = a.has ? `생애이력시스템 계정 <b>${esc(a.user_id)}</b> 등록됨` : '생애이력시스템 계정이 없습니다 — <a href="blcm.html">건축물관리점검 목록</a>에서 넣으세요(관리자).';
    } catch (err) { $("bj-acc").textContent = err.message; }
  }
  function addrKey(s) { return String(s || "").replace(/\s/g, ""); }
  function drawSite() {
    const site = job.site || {};
    const t = site.target;
    $("bj-target").innerHTML = t ? `<div class="bj-tg"><b>${esc(t.address)}</b><span>${esc(t.kind)} · 통보일 ${esc(t.notice)}</span><span class="bj-chip ${t.prog === "02" ? "ok" : "empty"}">${esc(t.status)}</span></div>`
      : '<div class="mail-note">아직 안 골랐습니다 — [🔎 사이트 목록 읽기] 뒤 이 건축물 줄의 [고르기]</div>';
    const rows = ((site.list || {}).rows || []);
    const mine = addrKey(job.address || (job.building || {}).address);
    $("bj-list").innerHTML = rows.length ? `<div class="mail-note">목록 ${esc(site.list.at)} 읽음 · ${rows.length}줄 — 작성중만 고를 수 있음(미실시는 사이트에서 [보고서 작성]을 먼저)</div>
      <div class="bj-list">${rows.map((r) => {
        const hint = mine && (addrKey(r.address).includes(mine.slice(-8)) || mine.includes(addrKey(r.address).slice(-8)));
        return `<div class="bj-lrow${hint ? " hint" : ""}"><span>${esc(r.address)}</span><span>${esc(r.status)}</span><span>${esc(r.notice)}</span>
          ${r.prog === "02" ? `<button type="button" class="secondary" data-op="${esc(r.oprtn)}">${t && t.oprtn === r.oprtn ? "✓ 고름" : "고르기"}</button>` : "<span></span>"}</div>`;
      }).join("")}</div>` : "";
    $("bj-list").querySelectorAll("button[data-op]").forEach((b) => b.addEventListener("click", async () => {
      try { job.site = (await api(`${P}/site/target`, { method: "PUT", body: JSON.stringify({ oprtn: b.dataset.op }) })).site; drawSite(); } catch (err) { showError(errorEl, err); }
    }));
    drawRun();
  }
  function drawRun() {
    const run = (job.site || {}).run;
    const box = $("bj-run");
    const busy = run && ["queued", "running"].includes(run.status);
    ["bj-list-go", "bj-practice", "bj-save"].forEach((id) => { $(id).disabled = !!busy; });
    if (!run) { box.innerHTML = ""; return; }
    const r = run.result || {};
    const items = Object.entries(r.items || {});
    const cnt = (s) => items.filter(([, v]) => v.state === s).length;
    const head = busy ? `⏳ ${MODE[run.mode] || run.mode} ${run.status === "queued" ? "기다리는 중" : "도는 중"}… (${esc(run.started || run.at)}) — 몇 분 걸립니다`
      : `${run.status === "done" ? "✓" : "✗"} ${MODE[run.mode] || run.mode} ${run.status === "done" ? "끝" : "멈춤"} · ${esc(run.ended || "")} · ${esc(run.by || "")}`;
    box.innerHTML = `<div class="bj-runbox ${busy ? "" : run.status === "done" ? "ok" : "bad"}"><b>${head}</b>
      ${r.error ? `<div class="bj-bad" style="display:inline-block;margin-top:6px">${esc(r.error)}</div>` : ""}
      ${run.mode === "practice" && !busy ? `<div class="mail-note">끊은 쓰기 요청 ${r.blocked || 0}개 — 사이트에 아무것도 저장하지 않았습니다</div>` : ""}
      ${items.length ? `<div class="mail-note">항목 ✓${cnt("ok")} ⚠${cnt("warn")} ✗${cnt("fail")} ·${cnt("skip")}(안 씀)</div>
        <table class="bj-itbl">${items.filter(([, v]) => v.state !== "skip").map(([k, v]) => `<tr class="st-${v.state}"><td>${ST[v.state] || ""} ${esc(k === "main" ? "본 화면(관리계획·그 밖의 항목·의견)" : k)}</td><td>${esc(v.msg || (v.state === "ok" ? "채움" : ""))}${v.photos ? ` · 사진 ${v.uploaded != null && run.mode === "save" ? `${v.uploaded}/` : ""}${v.photos}` : ""}</td></tr>`).join("")}</table>` : ""}
      ${(r.alerts || []).length ? `<details><summary class="mail-note">사이트 알림 ${r.alerts.length}개</summary><div class="bj-log">${esc(r.alerts.join("\n"))}</div></details>` : ""}
      ${(r.shots || []).length ? `<div class="bj-shots">${r.shots.map((n) => `<a class="secondary-link" target="_blank" rel="noopener" href="${BASE}/api${P}/site/shot/${encodeURIComponent(n)}">🖼 ${esc(n.replace(/\.png$/, ""))}</a>`).join("")}</div>` : ""}
      ${(r.log || []).length ? `<details><summary class="mail-note">기록</summary><div class="bj-log">${esc(r.log.join("\n"))}</div></details>` : ""}</div>`;
    clearTimeout(runTimer);
    if (busy) runTimer = setTimeout(async () => { try { job.site = (await api(`${P}/site`)).site; drawSite(); } catch (_) { drawRun(); } }, 3000);
  }
  async function startRun(mode, msgEl) {
    const body = { mode };
    if (mode === "save") {
      const t = (job.site || {}).target || {};
      if (!confirm(`생애이력시스템 보고서(${t.address || ""})에 실제로 저장합니다.\n\n· 소항목 상세 창마다 [저장](사진 올리기 포함) + 관리계획·그 밖의 항목·의견 [전체저장]\n· [점검보고서 제출]은 누르지 않습니다 — 사이트에서 보고 직접\n· 같은 아이디로 들어가 있는 다른 화면은 끊길 수 있습니다\n\n처음 몇 번은 형이 사이트를 같이 볼 때 하세요. 계속할까요?`)) return;
      body.confirm = true;
    }
    try {
      job.site = (await apiPost(`${P}/site/run`, body)).site;
      if (msgEl) msgEl.textContent = "";
      drawSite();
    } catch (err) { if (msgEl) msgEl.textContent = err.message; else showError(errorEl, err); }
  }
  $("bj-list-go").addEventListener("click", () => startRun("list", $("bj-list-msg")));
  $("bj-practice").addEventListener("click", () => startRun("practice", $("bj-list-msg")));
  $("bj-save").addEventListener("click", () => startRun("save", $("bj-list-msg")));

  async function loadReport() {
    drawAccount(); drawSite();
    try { persons = (await api("/blcm/persons")).persons; } catch (err) { persons = []; }
    const c = job.contract || {};
    people = (c.people && c.people.length ? c.people : job.people_default || []).map((x) => ({ ...x }));
    drawReportInfo(); drawPeople(); drawDocs();
  }

  // 카드의 지금 값 → 저장 몸통
  function collect(el, it) {
    const body = { na: el.querySelector(".bj-na-in").checked, status: {}, texts: {} };
    el.querySelectorAll(".bj-seg:not(.bj-fact)").forEach((s) => { // 있음/없음(현장 질문)은 판정이 아님 — setFact로 따로
      const on = s.querySelector("button.on");
      const v = on ? on.dataset.v : "";
      const n = s.dataset.name;
      if (n === "judge" || n === "cmp" || n === "design") body[n] = v;
      else if (n.startsWith("rt:")) { body.ratings = body.ratings || {}; if (v) body.ratings[n.slice(3)] = v; }
      else if (n.startsWith("cert:")) { body.cert = body.cert || {}; if (v) body.cert[n.slice(5)] = v; }
    });
    const cnt = el.querySelector(".bj-count");
    if (cnt) body.count = cnt.value === "" ? null : Number(cnt.value);
    el.querySelectorAll("[data-st]").forEach((i) => {
      if (i.type === "checkbox" || i.type === "radio") { if (i.checked) body.status[i.dataset.st] = true; } else if (i.value.trim()) body.status[i.dataset.st] = i.value.trim();
    });
    el.querySelectorAll("[data-tx]").forEach((t) => { body.texts[t.dataset.tx] = t.value; });
    return body;
  }

  function wire(el, it) {
    const code = it.code;
    let timer = null, saving = Promise.resolve();
    const save = (now, redrawAfter = true) => {
      clearTimeout(timer);
      const go = () => {
        const body = collect(el, it);
        saving = saving.then(() => api(`${P}/items/${encodeURIComponent(code)}`, { method: "PUT", body: JSON.stringify(body) })).then((out) => {
          apply(code, out);
          if (redrawAfter) { const fo = document.activeElement; const keep = fo && el.contains(fo) && (fo.matches("textarea, input:not([type=checkbox]):not([type=radio])")) ? fo : null; if (!keep) redraw(el, it); else updateHead(el, it); }
        }).catch((err) => showError(errorEl, err));
      };
      if (now) go(); else timer = setTimeout(go, 600);
    };
    el.querySelectorAll(".bj-seg:not(.bj-fact) button").forEach((b) => b.addEventListener("click", () => {
      const was = b.classList.contains("on");
      b.parentElement.querySelectorAll("button").forEach((x) => x.classList.remove("on"));
      if (!was) b.classList.add("on");
      save(true);
    }));
    el.querySelector(".bj-na-in").addEventListener("change", () => save(true));
    el.querySelectorAll("input[type=checkbox][data-st]").forEach((i) => i.addEventListener("change", () => save(true)));
    el.querySelectorAll("input[type=radio][data-st]").forEach((i) => { // 하나만 고르는 줄(10/30) — 고른 것을 다시 누르면 지움
      i.dataset.was = i.checked ? "1" : "";
      i.addEventListener("click", () => {
        if (i.dataset.was === "1") i.checked = false;
        el.querySelectorAll(`input[type=radio][data-st]`).forEach((x) => { if (x.name === i.name) x.dataset.was = x.checked ? "1" : ""; });
        save(true);
      });
    });
    el.querySelectorAll("input.bj-blank, input.bj-count").forEach((i) => i.addEventListener("input", () => save(false, false)));
    el.querySelectorAll("input.bj-blank, input.bj-count").forEach((i) => i.addEventListener("change", () => save(true)));
    el.querySelectorAll("[data-tx]").forEach((t) => {
      t.addEventListener("input", () => save(false, false));
      t.addEventListener("change", () => save(true, false));
      if (typeof aiRewrite === "function") aiRewrite(t, `${P}/ai/rewrite`, `${it.code} ${it.name} — ${TEXTS.find((x) => x[0] === t.dataset.tx)[1]}`);
    });
    // 사진(10/30): 적합 = 견본 칸·더 찍기, 부적합 = 유형 칸(판정 자동), 끌어 놓기 = 놓은 칸대로
    const upload = async (files, extra, label) => {
      const msg = el.querySelector(".bj-ph-msg");
      let n = 0;
      for (const f of files) {
        if (msg) msg.textContent = `올리는 중… ${n + 1}/${files.length}`;
        const fd = new FormData();
        fd.append("file", f);
        Object.entries(extra).forEach(([k, v]) => fd.append(k, v));
        try { apply(code, await apiUploadSafe(`${P}/items/${encodeURIComponent(code)}/photos`, fd, { label: `${it.code} ${it.name} ${label}` })); n += 1; }
        catch (err) { if (msg) msg.textContent = err.message; if (!err.queued) showError(errorEl, err); }
      }
      if (n) redraw(el, it);
    };
    const drop = (zone, inp) => { if (zone && inp && typeof enableFileDrop === "function") enableFileDrop(zone, inp); };
    el.querySelectorAll("input[type=file][data-kind]").forEach((inp) => {
      drop(inp.closest("label"), inp);
      inp.addEventListener("change", () => { const fs = [...inp.files]; inp.value = ""; if (fs.length) upload(fs, { kind: "good" }, "적합 사진"); });
    });
    el.querySelectorAll("input[type=file][data-bad]").forEach((inp) => {
      const row = inp.closest(".bj-bad-row");
      drop(row, inp);
      inp.addEventListener("change", () => { const fs = [...inp.files]; inp.value = ""; if (fs.length) upload(fs, { kind: "bad", bad: inp.dataset.bad }, `부적합 ${row.querySelector("b").textContent.replace("⚠ ", "")}`); });
    });
    el.querySelectorAll("input[type=file][data-slot]").forEach((inp) => {
      drop(inp.closest(".bj-slot-shot"), inp);
      inp.addEventListener("change", () => { const f = inp.files[0]; inp.value = ""; if (f) upload([f], { kind: "good", slot: inp.dataset.slot }, "견본 칸 사진"); });
    });
    drop(el.querySelector(".bj-ok-box"), el.querySelector("input[type=file][data-kind]"));
    wireFacts(el);
    el.querySelectorAll(".bj-ph").forEach((ph) => {
      const pid = ph.dataset.pid;
      ph.querySelector(".bj-ph-cap").addEventListener("change", async (e) => {
        try { const out = await apiPatch(`${P}/items/${encodeURIComponent(code)}/photos/${pid}`, { caption: e.target.value }); apply(code, out); } catch (err) { showError(errorEl, err); }
      });
      ph.querySelector(".bj-ph-type")?.addEventListener("change", async (e) => {
        const v = e.target.value;
        const body = v === "" ? { kind: "good", bad: "" } : v === "__bad" ? { kind: "bad", bad: "" } : { kind: "bad", bad: v };
        try { apply(code, await apiPatch(`${P}/items/${encodeURIComponent(code)}/photos/${pid}`, body)); redraw(el, it); } catch (err) { showError(errorEl, err); }
      });
      ph.querySelector(".bj-ph-del").addEventListener("click", async () => {
        if (!confirm("이 사진을 지울까요?")) return;
        try { const out = await api(`${P}/items/${encodeURIComponent(code)}/photos/${pid}`, { method: "DELETE" }); apply(code, out); redraw(el, it); } catch (err) { showError(errorEl, err); }
      });
    });
    // AI
    el.querySelector(".bj-ai-go").addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      const tx = collect(el, it).texts;
      if (Object.values(tx).some((v) => v && v.trim() && v.trim() !== "-") && !confirm("지금 적힌 글 칸을 AI 글로 바꿉니다(판정·체크는 그대로) — 계속할까요?")) return;
      clearTimeout(timer);
      await saving;
      btn.disabled = true;
      const msg = el.querySelector(".bj-ai-msg");
      msg.textContent = "AI가 사진·대장을 보는 중…(20~40초)";
      try {
        await api(`${P}/items/${encodeURIComponent(code)}`, { method: "PUT", body: JSON.stringify(collect(el, it)) }).then((out) => apply(code, out));
        const out = await apiPost(`${P}/items/${encodeURIComponent(code)}/ai`, { extra: el.querySelector(".bj-ai-note").value.trim() });
        apply(code, out);
        redraw(el, it);
        el.querySelector(".bj-ai-msg").textContent = "✓ AI로 채웠습니다 — 확인하고 고치세요";
      } catch (err) { msg.textContent = err.message; btn.disabled = false; }
    });
  }

  // ---------- 📋 이 건물 점검 목록(10/30 사용자 "반드시 찍을 사진 / 해당없음이지만 현장에 있으면 찍을 사진 / 면담으로 반드시 확인할 것 — 현장마다, 항목 옆에 예시 사진") ----------
  let plan = null;
  async function loadPlan() {
    try { plan = await api(`${P}/plan`); drawReview(); drawTabs(); drawItems(); drawPool(); } catch (err) { $("bj-review-body").innerHTML = `<div class="mail-msg bad">${esc(err.message)}</div>`; }
  }
  const groupOf = (code) => (table.groups.find((g) => g.items.includes(code)) || {}).key;
  function setFact(key, v) {
    return api(`${P}/facts`, { method: "PUT", body: JSON.stringify({ facts: { [key]: v } }) }).then((p) => { plan = p; drawReview(); drawTabs(); drawItems(); drawPool(); })
      .catch((err) => showError(errorEl, err));
  }
  function wireFacts(root) { // 있음/없음 — 한 번 더 누르면 지움(서류에서 읽은 답이 있으면 그것으로), 서류 답만 있는 줄의 같은 답은 그대로
    root.querySelectorAll(".bj-fact button").forEach((b) => b.addEventListener("click", (e) => {
      e.preventDefault();
      const seg = b.closest(".bj-fact"), key = seg.dataset.key;
      if (b.classList.contains("on") && seg.dataset.user === "" && ((plan.questions || []).find((q) => q.key === key) || {}).auto) return;
      setFact(key, b.classList.contains("on") ? "" : b.dataset.v);
    }));
  }
  function drawReview() { // ① 서류검토(10/30 사용자 "서류검토 → 해당없음 분류하고 이유 작성 — 자동이든 버튼이든")
    if (!plan) return;
    const items = plan.items;
    const nm = (code) => (table.byCode[code] || {}).name || code;
    const codes = (f) => Object.keys(items).filter((k) => f(items[k]));
    const qOf = (key) => plan.questions.find((x) => x.key === key) || { key, answer: "", label: key, items: [] };
    const qRow = (key) => { const q = qOf(key);
      return `<div class="bj-pl-q"><span>${esc(q.label)}${q.items.length ? ` <small>· ${esc(q.items.join(", "))}</small>` : ""}</span>
        <span class="bj-seg bj-fact" data-key="${esc(key)}" data-user="${esc(q.user || "")}">${["있음", "없음"].map((v) => `<button type="button" data-v="${v}" class="${q.answer === v ? "on" : ""}">${v}</button>`).join("")}</span></div>`; };
    const na = codes((x) => x.state === "na"), chk = codes((x) => x.state === "check");
    const naLeft = na.filter((k) => (!items[k].marked_na && !items[k].touched) || (items[k].marked_na && !items[k].evidence && !items[k].ev_done)); // 아직 안 넣음 + 넣었는데 근거 그림을 아직 안 만듦
    const site = codes((x) => x.state === "ask" && x.cat === "present");
    const nSite = Object.keys(items).length - na.length;
    const docQ = plan.questions.filter((q) => (q.kind === "land" || q.kind === "talk") && !q.answer);
    const siteQ = plan.questions.filter((q) => q.kind === "site" && !q.answer && q.items.length);
    const answered = plan.questions.filter((q) => q.answer);
    const srcOf = (q) => q.user ? (q.auto && q.auto.v !== q.user ? `점검자 답(서류는 ${q.auto.v})` : "점검자 답") : q.auto ? `📄 ${q.auto.src}` : "";
    const docs = plan.docs || {}, lu = docs.landuse;
    $("bj-review-sub").textContent = `현장 점검 ${nSite}항목 · 해당없음 ${na.length}${naLeft.length ? ` (아직 안 넣음 ${naLeft.length})` : " ✓"}`;
    $("bj-review-body").innerHTML = `<div class="bj-pl-sum"><span class="must">현장 점검 ${nSite - site.length}</span>${site.length ? `<span class="present">있으면 찍기 ${site.length}</span>` : ""}<span class="na">해당없음 ${na.length}</span>${chk.length ? `<span class="check">확인 필요 ${chk.length}</span>` : ""}</div>
      <div class="bj-rv-docs">🏢 건축물대장 ${docs.register ? "✓" : "— 맨 위 [🏢 건축물대장 올리기]"} · 🗺️ 토지이용계획확인원 ${lu ? (lu.text_ok ? "✓" : "글자 없는 그림 — 아래 질문에 직접 답") : "— 맨 위 [🗺️ 토지이용계획확인원 올리기]로 올리면 아래 질문이 자동으로"}</div>
      ${docQ.length ? `<div class="bj-pl-sec">서류·면담으로 답할 것 <small>답에 따라 해당없음이 바뀝니다</small></div>${docQ.map((q) => qRow(q.key)).join("")}` : ""}
      ${siteQ.length ? `<div class="mail-note">현장에서 볼 것 ${siteQ.length}개(${esc(siteQ.map((q) => q.label.replace(/가 있나요\?|이 있나요\?|있나요\?/, "")).join(" · "))}) — ③ 현장 점검 카드에서 있음/없음</div>` : ""}
      ${answered.length ? `<details class="bj-pl-na"><summary>📄 서류에서 읽은 답·답한 것 ${answered.length}개 ▾ <small class="mail-note">틀리면 다른 답을 누르세요(점검자 답이 서류보다 앞섬)</small></summary>
        ${answered.map((q) => `<div class="bj-pl-q"><span>${esc(q.label)} <small>· ${esc((q.uses || []).join(", "))}</small><br><small class="bj-pl-src">${esc(srcOf(q))}</small></span>
          <span class="bj-seg bj-fact" data-key="${esc(q.key)}" data-user="${esc(q.user || "")}">${["있음", "없음"].map((v) => `<button type="button" data-v="${v}" class="${q.answer === v ? "on" : ""}">${v}</button>`).join("")}</span></div>`).join("")}</details>` : ""}
      ${chk.length ? `<div class="bj-pl-sec">확인 필요 <small>대장 값이 모자라거나 기준일 경계 — 현장 점검 목록에 남겨 둠</small></div>${chk.map((k) => `<button type="button" class="bj-pl-row" data-code="${esc(k)}"><span class="bj-pl-t"><b>${esc(k)} ${esc(nm(k))}</b><small>${esc(items[k].why || "")}</small></span></button>`).join("")}` : ""}
      <div class="bj-pl-sec">해당없음 ${na.length}개 <small>법령상 적용대상이 아님 — 사유는 비고에 들어갑니다</small></div>
      <details class="bj-pl-na"><summary>사유 보기 ▾</summary><ul>${na.map((k) => `<li><b>${esc(k)} ${esc(nm(k))}</b>${items[k].marked_na ? ` ✓${items[k].evidence ? ` · 근거 그림 ${items[k].evidence}장` : ""}` : ""} — ${esc(items[k].reason)}</li>`).join("")}</ul></details>
      <div class="bj-rv-go">${naLeft.length ? `<button type="button" class="bj-pl-na-go">✓ 서류검토 확정 — 해당없음 ${naLeft.length}개에 사유·근거 그림 넣기</button>
        <span class="mail-note">아래 ③ 현장 점검은 이 판정대로 나옵니다(해당없음은 맨 끝 탭) · 현장 답(있음/없음)에 따라 바뀌면 다시 누르세요</span>`
        : `<b class="bj-done-ok">✓ 서류검토 확정</b><span class="mail-note">해당없음 ${na.length}개 모두 사유·근거 그림(대장 칸·확인원·법령 조문 빨간 네모)을 넣었습니다 — [해당없음] 탭 카드에서 확인</span>`}</div>`;
    const body = $("bj-review-body");
    body.querySelectorAll(".bj-pl-row").forEach((b) => b.addEventListener("click", () => jumpTo({ code: b.dataset.code, tab: groupOf(b.dataset.code) })));
    wireFacts(body);
    body.querySelector(".bj-pl-na-go")?.addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      if (!confirm(`법령상 해당없음 ${naLeft.length}개를 해당없음으로 넣고 비고에 사유, 현황사진에 근거 그림(대장 칸·확인원·법령 조문)을 넣을까요?\n(판정·사진을 넣은 항목은 건드리지 않습니다)`)) return;
      btn.disabled = true;
      try {
        const out = await apiPost(`${P}/plan/na`, {});
        plan = out.plan;
        job = { ...job, ...out };
        drawTop(); drawTabs(); drawItems(); drawDone(); drawReview(); drawPool();
      } catch (err) { showError(errorEl, err); btn.disabled = false; }
    });
  }
  function planChip(code) { // 카드 머리 — 법령 판정(해당없음·현장 확인·확인 필요)
    const p = plan && plan.items[code];
    if (!p || p.state === "apply") return "";
    const r = (job.results || {})[code] || {};
    if (p.state === "na") return r.na ? "" : `<span class="bj-plchip na" title="${esc(p.reason)}">법령상 해당없음</span>`;
    return `<span class="bj-plchip ${p.state === "ask" ? "ask" : "check"}" title="${esc(p.why)}">${p.state === "ask" ? "현장·면담 확인" : "확인 필요"}</span>`;
  }

  // ---------- 📐 도면·서류 그림(10/30 사용자 "도면 넣는 칸은 따로 빼서 한꺼번에 넣고 해당 위치로") ----------
  const pool = () => ((job.files || {}).drawings || []);
  const drawSrc = (d) => `${BASE}/api${P}/drawings/${encodeURIComponent(d.id)}/img`;
  const drawLabel = (d) => `${d.name}${d.page ? ` ${d.page}쪽` : ""}`;
  const keyOf = (s) => String(s || "").replace(/\s/g, "").replace(/(도면|표기)/g, ""); // "1층 조경표기도면" → "1층조경", "정면도" → "정면도"
  function hintFor(caption) { // 쪽 글에서 찾은 도면 이름(또는 올린 서류 이름 — 토지이용계획확인원)이 견본 설명과 맞는 그림(추천)
    const k = keyOf(caption);
    if (!k) return null;
    return pool().find((d) => [...(d.hint || "").split(" "), d.name || ""].some((h) => h && (keyOf(h) === k || (k.length >= 3 && keyOf(h).includes(k))))) || null;
  }
  function onDrawings(out) {
    job.files = { ...(job.files || {}), drawings: out.drawings };
    if (out.results) job.results = out.results;
    if (out.eval) job.eval = out.eval;
    drawPool();
    refreshTabCounts(); drawDone();
  }
  function drawNeeds() { // 이 건물에 필요한 도면(10/30 사용자 "도면 자리가 복잡 — 현장 카드에서 빼고 관리사무소에서 한꺼번에") — 같은 도면은 한 줄, 해당없음 항목 것은 뺌
    const m = new Map();
    for (const it of table.items) {
      if (isNa(it.code)) continue;
      for (const s of slotsOf(it.code).draw) {
        const k = keyOf(s.caption) || s.caption;
        if (!m.has(k)) m.set(k, { key: k, caption: s.caption, file: s.file, uses: [] });
        m.get(k).uses.push({ code: it.code, n: s.n, p: (((job.results || {})[it.code] || {}).photos || []).find((x) => x.slot === s.n) });
      }
    }
    return [...m.values()];
  }
  async function putAll(x, drawing) { for (const u of x.uses) await putSlot(u.code, u.n, drawing, true); drawPool(); drawItems(); }
  function drawPool() {
    if (!table) return;
    const list = pool(), needs = drawNeeds();
    const got = (x) => (x.uses.find((u) => u.p) || {}).p;
    const done = needs.filter((x) => x.uses.every((u) => u.p)).length;
    $("bj-draw-sub").textContent = needs.length ? `이 건물에 필요한 도면 ${needs.length}가지 · 넣음 ${done}` : "넣을 도면이 없습니다(도면 쓰는 항목이 모두 해당없음)";
    const sugg = needs.filter((x) => !got(x) && hintFor(x.caption));
    $("bj-draw-needs").innerHTML = needs.map((x, i) => {
      const p = got(x);
      return `<div class="bj-dn${p ? " ok" : ""}" data-i="${i}">
        <div class="bj-dn-ex">${x.file ? `<a href="${sampleSrc(x.file)}" target="_blank" rel="noopener"><img loading="lazy" src="${sampleSrc(x.file)}" alt="" /></a>` : ""}<span class="bj-slot-tag">견본</span></div>
        <div class="bj-dn-t"><b>${esc(x.caption)}</b><small>쓰는 항목 ${esc(x.uses.map((u) => u.code).join(" · "))}</small>${!p && hintFor(x.caption) ? '<small class="bj-hint-tag">올린 PDF에 같은 이름 쪽이 있음</small>' : ""}</div>
        <div class="bj-dn-now">${p ? `<a href="${BASE}/api${P}/photo/${esc(p.id)}" target="_blank" rel="noopener"><img loading="lazy" src="${BASE}/api${P}/photo/${esc(p.id)}" alt="" /></a>` : '<span class="bj-dn-none">아직</span>'}</div>
        <div class="bj-dn-btns"><label class="secondary bj-file-btn">📷 찍기<input type="file" accept="image/*" capture="environment" hidden data-kr-file="skip" class="bj-dn-cam" /></label>
          <button type="button" class="secondary bj-dn-pick">📄 올린 PDF에서</button>${p ? '<button type="button" class="secondary bj-dn-clear" title="비우기">✕</button>' : ""}</div></div>`;
    }).join("") + (sugg.length ? `<div class="bj-top-btns"><button type="button" class="secondary" id="bj-draw-auto">✨ 같은 이름 쪽 ${sugg.length}줄 한꺼번에 넣기</button></div>` : "");
    $("bj-pool-n").textContent = list.length;
    $("bj-pool").innerHTML = list.map((d) => `<div class="bj-pool-it" data-id="${esc(d.id)}"><a href="${drawSrc(d)}" target="_blank" rel="noopener"><img loading="lazy" src="${drawSrc(d)}" alt="" /></a>
      <b title="${esc(drawLabel(d))}">${esc(drawLabel(d))}</b><small title="${esc(d.hint || "")}">${esc(d.hint || "")}</small>${(d.used || []).length ? `<small>넣은 곳 ${esc(d.used.join(", "))}</small>` : ""}
      <button type="button" class="bj-pool-del" title="모음에서 지우기(항목에 넣은 것은 그대로)">✕</button></div>`).join("") || '<div class="mail-note">아직 올린 그림이 없습니다.</div>';
    $("bj-pool").querySelectorAll(".bj-pool-del").forEach((b) => b.addEventListener("click", async () => {
      if (!confirm("이 그림을 모음에서 지울까요? (항목에 이미 넣은 것은 그대로)")) return;
      try { onDrawings(await api(`${P}/drawings/${encodeURIComponent(b.closest(".bj-pool-it").dataset.id)}`, { method: "DELETE" })); } catch (err) { showError(errorEl, err); }
    }));
    $("bj-draw-needs").querySelectorAll(".bj-dn").forEach((row) => {
      const x = needs[Number(row.dataset.i)];
      const cam = row.querySelector(".bj-dn-cam");
      cam.addEventListener("change", async () => {
        const f = cam.files[0];
        cam.value = "";
        if (!f) return;
        $("bj-draw-msg").textContent = `${x.caption} 올리는 중…`;
        const before = new Set(pool().map((d) => d.id));
        const fd = new FormData();
        fd.append("file", f);
        try {
          onDrawings(await apiUpload(`${P}/drawings`, fd));
          const d = pool().find((y) => !before.has(y.id));
          if (d) await putAll(x, d.id);
          $("bj-draw-msg").textContent = `✓ ${x.caption} — ${x.uses.map((u) => u.code).join(" · ")}에 넣었습니다`;
        } catch (err) { $("bj-draw-msg").textContent = err.message; }
      });
      row.querySelector(".bj-dn-pick").addEventListener("click", () => pickFor(x));
      row.querySelector(".bj-dn-clear")?.addEventListener("click", async () => { if (confirm(`${x.caption}을(를) 비울까요? (${x.uses.map((u) => u.code).join(" · ")} 현황사진에서 빠집니다)`)) await putAll(x, null); });
    });
    $("bj-draw-auto")?.addEventListener("click", async (e) => {
      e.currentTarget.disabled = true;
      for (const x of sugg) await putAll(x, hintFor(x.caption).id);
    });
  }
  function drawRows() { // 견본 도면 자리 [{it, s, p(넣은 사진)}] — 항목 순서
    return table.items.flatMap((it) => slotsOf(it.code).draw.map((s) => ({ it, s, p: (((job.results || {})[it.code] || {}).photos || []).find((x) => x.slot === s.n) })));
  }
  async function putSlot(code, n, drawing, quiet) {
    try {
      const out = await api(`${P}/items/${encodeURIComponent(code)}/slot/${n}`, { method: "PUT", body: JSON.stringify({ drawing }) });
      apply(code, out);
      job.files = { ...(job.files || {}), drawings: pool().map((d) => ({ ...d, used: Object.entries(job.results || {}).filter(([, r]) => ((r || {}).photos || []).some((p) => p.drawing === d.id)).map(([c]) => c) })) };
      if (!quiet) { drawPool(); drawItems(); }
      refreshTabCounts(); drawDone();
    } catch (err) { showError(errorEl, err); }
  }
  async function uploadDrawings(files) {
    const msg = $("bj-draw-msg");
    let n = 0;
    for (const f of files) {
      msg.textContent = `올리는 중… ${n + 1}/${files.length} ${f.name}`;
      const fd = new FormData();
      fd.append("file", f);
      try { onDrawings(await apiUpload(`${P}/drawings`, fd)); n += 1; } catch (err) { msg.textContent = `${f.name}: ${err.message}`; return; }
    }
    const auto = drawNeeds().filter((x) => !x.uses.some((u) => u.p) && hintFor(x.caption)); // 쪽 이름이 같은 줄은 바로 넣음(사람은 확인만)
    for (const x of auto) await putAll(x, hintFor(x.caption).id);
    msg.textContent = `✓ ${n}개 올림${auto.length ? ` · 같은 이름 쪽 ${auto.length}줄 자동으로 넣음 — 확인하세요` : " — 줄마다 [📄 올린 PDF에서] 고르세요"}`;
  }
  const drawIn = $("bj-draw-in");
  drawIn.addEventListener("change", () => { const fs = [...drawIn.files]; drawIn.value = ""; if (fs.length) uploadDrawings(fs); });
  if (typeof enableFileDrop === "function") enableFileDrop($("bj-draw-drop"), drawIn);
  function pickFor(x) { // ② 도면 줄 [📄 올린 PDF에서] — 모음에서 고르면 쓰는 항목 모두에
    const ov = document.createElement("div");
    ov.className = "mail-overlay";
    const draw = () => {
      const h = hintFor(x.caption);
      ov.innerHTML = `<div class="mail-box" role="dialog" aria-modal="true"><div class="mail-head"><b>📐 ${esc(x.caption)} <small>· ${esc(x.uses.map((u) => u.code).join(" · "))}</small></b>
        <span class="mail-sub">올린 그림에서 고르세요${h ? " — 노란 테두리 = 쪽 글의 도면 이름이 같은 것" : ""}</span></div>
        <div class="bj-pick-grid">${pool().map((d) => `<div class="bj-pool-it pick${h && h.id === d.id ? " hint" : ""}" data-id="${esc(d.id)}"><img loading="lazy" src="${drawSrc(d)}" alt="" />
          <b>${esc(drawLabel(d))}</b><small>${h && h.id === d.id ? '<span class="bj-hint-tag">추천 · </span>' : ""}${esc(d.hint || "")}</small></div>`).join("") || '<div class="mail-note">아직 올린 그림이 없습니다 — 아래에서 올리세요.</div>'}</div>
        <div class="mail-foot"><label class="secondary bj-file-btn">📄 도면 PDF·그림 올리기<input type="file" accept=".pdf,application/pdf,image/*" multiple hidden data-kr-file="skip" class="bj-pick-up" /></label>
          <button type="button" class="mail-cancel">닫기</button></div></div>`;
      ov.querySelector(".mail-cancel").addEventListener("click", () => ov.remove());
      ov.querySelectorAll(".bj-pool-it.pick").forEach((c) => c.addEventListener("click", async () => { ov.remove(); await putAll(x, c.dataset.id); }));
      const up = ov.querySelector(".bj-pick-up");
      up.addEventListener("change", async () => { const fs = [...up.files]; up.value = ""; if (fs.length) { await uploadDrawings(fs); draw(); } });
    };
    draw();
    ov.addEventListener("mousedown", (e) => { if (e.target === ov) ov.remove(); });
    document.body.appendChild(ov);
  }

  function updateHead(el, it) { // 글 칸에 쓰는 중이면 카드는 그대로 두고 머리 칩만
    const h = el.querySelector(".bj-card-h");
    const old = h.querySelectorAll(".bj-chip");
    old.forEach((x) => x.remove());
    h.querySelector(".bj-mid").insertAdjacentHTML("afterend", chip(job.eval[it.code]));
    drawTop();
  }

  async function load() {
    if (!jid) { showError(errorEl, new Error("건 번호가 없습니다 — 목록에서 여세요.")); return; }
    try {
      const [t, j] = await Promise.all([api("/blcm/items"), api(P)]);
      table = { ...t, byCode: Object.fromEntries(t.items.map((x) => [x.code, x])) };
      job = j;
      drawTop(); drawInfo(); drawTabs(); drawItems(); drawDone(); drawPool();
      loadPlan();
      loadReport();
    } catch (err) { showError(errorEl, err); }
  }
  load();
})();
