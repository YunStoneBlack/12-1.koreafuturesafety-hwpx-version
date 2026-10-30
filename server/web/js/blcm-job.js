// 건축물관리점검 건 화면(2026-10-29 사용자 "적합을 누르면 양호사진, 부적합을 누르고 사진을 넣으면 변경유형 판단해 체크, 기준면적은 대장·도면에서,
// 개선사항·방안근거·비고(사진설명)가 자동으로 — AI 분석은 덧붙여 다시 쓰기"). 항목표 = GET /blcm/items(매뉴얼 25.02 소항목 50개).
// 카드마다 고치면 0.6초 뒤 저장(PUT /blcm/jobs/{id}/items/{code}) → 서버가 판정(건수·점수) 계산해 돌려줌. 사진 = 신호 약하면 폰 보관(apiUploadSafe).
// 10/30 사용자(우리프라자 시험 뒤): 사진 끌어 놓기(버튼 위 = 그 종류, 빈 곳 = 판정대로), [장소별] 보기(외부·옥상·실내·지하·서류 — 보고서는 항목 순서 그대로),
// 카드 머리 ⚠ 빠진 것(서버 items.missing)·[✓ 점검 완료](빠진 것 목록 → 누르면 그 항목), 카드마다 📎 참고(우리프라자 보고서 사진·글, server/blcm/samples.json).
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const errorEl = $("error");
  const jid = Number(new URLSearchParams(location.search).get("id")) || 0;
  const P = `/blcm/jobs/${jid}`;
  let job = null, table = null;
  const openCards = new Set();
  let tab = (() => { try { return localStorage.getItem("bj-tab") || ""; } catch (_) { return ""; } })();
  let view = (() => { try { return localStorage.getItem("bj-view") === "place" ? "place" : "big"; } catch (_) { return "big"; } })(); // 항목 순서 / 장소별(10/30)
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

  // ---------- 탭·카드 ----------
  const EXTRA = [["_plan", "관리계획"], ["_other", "그 밖의 항목"], ["_opinion", "개선방안·종합의견"]];
  function extraCount(k) {
    const op = job.opinion || {};
    if (k === "_plan") return [Object.keys(op.plan || {}).length, table.plan_rows.length];
    if (k === "_other") return [Object.values(op.other || {}).filter((x) => x && x.v).length, table.other_rows.length];
    return [table.opinion_keys.filter(([key]) => ((op.texts || {})[key] || "").trim()).length, table.opinion_keys.length];
  }
  // 탭 묶음 — 항목 순서 = 대항목(법규유지…), 장소별 = 현장에서 찍는 자리(@out·@roof…, 서버 items.ITEM_PLACES — 한 항목이 여러 자리에 나올 수 있음)
  function tabGroups() {
    if (view !== "place") return table.groups;
    return (table.places || []).map(([k, label]) => ({ key: `@${k}`, label, items: table.items.map((x) => x.code).filter((c) => ((table.item_places || {})[c] || ["out"]).includes(k)) }));
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
    $("bj-view-note").textContent = view === "place" ? "현장에서 찍는 자리대로 묶어 봄 — 보고서·생애이력시스템에는 항목 순서 그대로 들어갑니다" : "매뉴얼(국토교통부 2025.2) 소항목 50개 — 판정·사진을 넣고 🤖 AI로 채우기";
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
      tab = view === "place" ? `@${((table.item_places || {})[m.code] || ["out"])[0]}` : m.tab;
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
  const seg = (name, opts, cur) => `<span class="bj-seg" data-name="${esc(name)}">${opts.map((o) => `<button type="button" data-v="${esc(o)}" class="${o === cur ? "on" : ""}">${esc(o)}</button>`).join("")}</span>`;

  function judgeHtml(it, r, ev) {
    if (it.kind === "count") {
      const cnt = ev && ev.count != null ? ev.count : "";
      return `<div class="bj-row"><span class="bj-lab">점검 판단결과</span>${seg("judge", FIT, r.judge || (ev && ev.judge) || "")}
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
      const subs = (d.subs || []).length ? d.subs.map((s, k) => `<div class="bj-sub"><span class="bj-lab">${esc(s.name)} <small>배점 ${s.points}점</small></span>${seg(`rt:d${i}.s${k}`, s.judge === "fit" ? FIT : RATING, rt[`d${i}.s${k}`] || "")}</div>`).join("")
        : `<div class="bj-sub"><span class="bj-lab">판정 <small>배점 ${d.points}점</small></span>${seg(`rt:d${i}`, opts, rt[`d${i}`] || "")}</div>`;
      return `<div class="bj-det"><div class="bj-det-h"><b>${esc(d.name)}</b> <small>(${d.points ?? ""}점)</small>${dv.judge ? ` <span class="bj-chip ${BAD.includes(dv.judge) ? "bad" : dv.judge === "보통" ? "mid" : dv.judge === "해당없음" ? "na" : "ok"}">${esc(dv.judge)}${dv.score != null ? ` ${dv.score}/${dv.full}점` : ""}</span>` : ""}</div>${subs}</div>`;
    }).join("");
  }

  function statusHtml(it, r) {
    const st = r.status || {};
    if (!(it.status || []).length) return "";
    return `<div class="bj-status"><div class="bj-lab">세부항목 점검현황</div>${it.status.map((ln, li) => `<div class="bj-sline">${ln.map((t, ti) => {
      const key = `l${li}t${ti}`;
      if (t.t === "check") return `<label class="bj-ck"><input type="checkbox" data-st="${key}" ${st[key] === true ? "checked" : ""} /> ${esc(t.v)}</label>`;
      if (t.t === "blank") return `<input class="bj-blank" data-st="${key}" value="${esc(st[key] === true ? "" : st[key] || "")}" />${t.unit ? `<span class="bj-unit">${esc(t.unit)}</span>` : ""}`;
      return `<span class="bj-txt">${esc(t.v)}</span>`;
    }).join("")}</div>`).join("")}</div>`;
  }

  const sampleSrc = (file) => `${BASE}/api/blcm/samples/${encodeURIComponent(file)}`;
  const slotsOf = (code) => (table.slots || {})[code] || { photo: [], draw: [] };
  function photosHtml(it, r) { // 10/30 사용자: 견본 칸(왼쪽 우리프라자 견본 | 오른쪽 이번 사진 — 시특법 전회차처럼, 폰도 나란히) + ＋ 더 찍기(장수 제한 없음)
    const ph = r.photos || [];
    const sl = slotsOf(it.code);
    const nums = new Set([...sl.photo, ...sl.draw].map((s) => s.n));
    const drawNs = new Set(sl.draw.map((s) => s.n));
    const one = (p) => `<div class="bj-ph ${p.kind === "bad" ? "bad" : "good"}" data-pid="${esc(p.id)}">
        <a href="${BASE}/api${P}/photo/${esc(p.id)}" target="_blank" rel="noopener"><img loading="lazy" src="${BASE}/api${P}/photo/${esc(p.id)}" alt="" /></a>
        <div class="bj-ph-b">${drawNs.has(p.slot) ? '<span class="bj-ph-kind" title="도면·서류 그림">도면</span>' : `<button type="button" class="bj-ph-kind" title="양호·지적 바꾸기">${p.kind === "bad" ? "지적" : "양호"}</button>`}${p.slot != null && nums.has(p.slot)
          ? (drawNs.has(p.slot) ? `<button type="button" class="bj-ph-redo bj-slot-pick" data-slot="${p.slot}" title="모음에서 다른 그림으로">📐 바꾸기</button>` : "")
            + `<label class="bj-ph-redo" title="다시 찍기">📷 다시<input type="file" accept="image/*" capture="environment" hidden data-kr-file="skip" data-slot="${p.slot}"${drawNs.has(p.slot) ? ' data-draw="1"' : ""} /></label>` : ""}<button type="button" class="bj-ph-del" title="지우기">✕</button></div>
        <input class="bj-ph-cap" value="${esc(p.caption || "")}" placeholder="사진 설명" maxlength="60" /></div>`;
    const slotRow = (s, draw) => {
      const p = ph.find((x) => x.slot === s.n);
      return `<div class="bj-slot${draw ? " draw" : ""}" data-slot="${s.n}">
        <div class="bj-slot-ex"><span class="bj-slot-tag">견본</span>${s.file ? `<a href="${sampleSrc(s.file)}" target="_blank" rel="noopener"><img loading="lazy" src="${sampleSrc(s.file)}" alt="" /></a>` : ""}<small>${esc(s.caption || "(설명 없음)")}${s.from ? ` <span class="bj-slot-from">· ${esc(s.from)}</span>` : ""}</small></div>
        <div class="bj-slot-now">${p ? one(p) : draw
          ? `<div class="bj-slot-btns"><button type="button" class="bj-slot-pick" data-slot="${s.n}">📐 도면 고르기<small>올린 도면에서</small></button>
              <label class="bj-slot-shot cam">📷 현장에서 찍기<small>도면 반출이 안 될 때</small><input type="file" accept="image/*" capture="environment" hidden data-kr-file="skip" data-slot="${s.n}" data-draw="1" /></label></div>`
          : `<label class="bj-slot-shot">📷 이렇게 찍기<small>${esc(s.caption || "")}</small><input type="file" accept="image/*" capture="environment" hidden data-kr-file="skip" data-slot="${s.n}" /></label>`}</div></div>`;
    };
    const extra = ph.filter((p) => p.slot == null || !nums.has(p.slot));
    const has = sl.photo.length + sl.draw.length;
    return `<div class="bj-photos"><div class="bj-lab">현황사진 <small>(적합·양호 = 양호 사진, 부적합 = 지적 사진 · 끌어 놓기 — 버튼 위 = 그 종류, 빈 곳 = 판정대로)</small></div>
      ${sl.photo.length ? `<div class="bj-slots-h">왼쪽 견본(회사 제출 보고서)처럼 찍으세요 — 더 찍어도, 덜 찍어도 됩니다</div>
        <div class="bj-slots">${sl.photo.map((s) => slotRow(s, false)).join("")}</div>` : ""}
      <div class="bj-ph-add">${has ? '<span class="bj-more">＋ 더 찍기</span>' : ""}<label class="secondary bj-file-btn">📷 양호 사진<input type="file" accept="image/*" multiple hidden data-kr-file="skip" data-kind="good" /></label>
        <label class="secondary bj-file-btn bad">📷 지적 사진<input type="file" accept="image/*" multiple hidden data-kr-file="skip" data-kind="bad" /></label><span class="mail-note bj-ph-msg">${has ? "장수 제한 없음" : ""}</span></div>
      <div class="bj-ph-grid">${extra.map(one).join("") || (has ? "" : '<div class="mail-note">사진 없음</div>')}</div>
      ${sl.draw.length ? `<div class="bj-draw-box"><div class="bj-slots-h">📐 도면·서류 ${sl.draw.length}곳 — 현장 사진이 아니라 따로 첨부(위 [📐 도면·서류 그림]에서 한꺼번에), 반출이 안 되면 현장에서 찍기</div>
        <div class="bj-slots">${sl.draw.map((s) => slotRow(s, true)).join("")}</div></div>` : ""}</div>`;
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
    return `<summary class="bj-card-h"><span class="bj-code">${esc(it.code)}</span><b>${esc(it.name)}</b><span class="bj-mid">${esc(view === "place" ? it.big : it.mid)}</span>${chip(ev)}${planChip(it.code)}${miss.length ? `<span class="bj-miss" title="${esc(miss.join(" · "))}">⚠ ${esc(miss[0])}${miss.length > 1 ? ` 외 ${miss.length - 1}` : ""}</span>` : ""}${nPh ? `<span class="bj-nph">📷${nPh}</span>` : ""}${r.ai ? '<span class="bj-nph" title="AI로 채움">🤖</span>' : ""}${view === "place" && pl.length > 1 ? `<span class="bj-places" title="이 항목을 찍는 자리">${esc(pl.join("·"))}</span>` : ""}<span class="sk-fold-arrow">▾</span></summary>
      <div class="bj-card-b">
        <label class="bj-na"><input type="checkbox" class="bj-na-in" ${r.na ? "checked" : ""} /> 이 항목 해당없음(적용 대상 아님 — 비고에 사유)</label>
        <div class="bj-judge"${r.na ? " hidden" : ""}>${judgeHtml(it, r, ev)}
          <div class="bj-row"><span class="bj-lab">현행기준과의 비교·검토</span>${seg("cmp", CMP, r.cmp || "")}</div>
          <div class="bj-row"><span class="bj-lab">설계도서(사용승인도면 등)와의 적합여부</span>${seg("design", DESIGN, r.design || "")}</div>
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
    drawPlan();
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
    el.querySelectorAll(".bj-seg").forEach((s) => {
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
      if (i.type === "checkbox") { if (i.checked) body.status[i.dataset.st] = true; } else if (i.value.trim()) body.status[i.dataset.st] = i.value.trim();
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
          if (redrawAfter) { const fo = document.activeElement; const keep = fo && el.contains(fo) && (fo.matches("textarea, input:not([type=checkbox])")) ? fo : null; if (!keep) redraw(el, it); else updateHead(el, it); }
        }).catch((err) => showError(errorEl, err));
      };
      if (now) go(); else timer = setTimeout(go, 600);
    };
    el.querySelectorAll(".bj-seg button").forEach((b) => b.addEventListener("click", () => {
      const was = b.classList.contains("on");
      b.parentElement.querySelectorAll("button").forEach((x) => x.classList.remove("on"));
      if (!was) b.classList.add("on");
      save(true);
    }));
    el.querySelector(".bj-na-in").addEventListener("change", () => save(true));
    el.querySelectorAll("input[type=checkbox][data-st]").forEach((i) => i.addEventListener("change", () => save(true)));
    el.querySelectorAll("input.bj-blank, input.bj-count").forEach((i) => i.addEventListener("input", () => save(false, false)));
    el.querySelectorAll("input.bj-blank, input.bj-count").forEach((i) => i.addEventListener("change", () => save(true)));
    el.querySelectorAll("[data-tx]").forEach((t) => {
      t.addEventListener("input", () => save(false, false));
      t.addEventListener("change", () => save(true, false));
      if (typeof aiRewrite === "function") aiRewrite(t, `${P}/ai/rewrite`, `${it.code} ${it.name} — ${TEXTS.find((x) => x[0] === t.dataset.tx)[1]}`);
    });
    // 사진 — 끌어 놓기(10/30 사용자 "드래그 안 됨"): 버튼 위 = 그 종류, 사진 칸 빈 곳 = 판정대로(부적합·미흡·불량이면 지적)
    if (typeof enableFileDrop === "function") {
      const goodIn = el.querySelector('.bj-ph-add input[data-kind="good"]'), badIn = el.querySelector('.bj-ph-add input[data-kind="bad"]');
      enableFileDrop(goodIn.closest("label"), goodIn);
      enableFileDrop(badIn.closest("label"), badIn);
      enableFileDrop(el.querySelector(".bj-photos"), () => (isBadEval(job.eval[code]) ? badIn : goodIn));
    }
    el.querySelectorAll(".bj-ph-add input[type=file]").forEach((inp) => inp.addEventListener("change", async () => {
      const files = [...inp.files];
      inp.value = "";
      const msg = el.querySelector(".bj-ph-msg");
      let n = 0;
      for (const f of files) {
        msg.textContent = `올리는 중… ${n + 1}/${files.length}`;
        const fd = new FormData();
        fd.append("file", f);
        fd.append("kind", inp.dataset.kind);
        try {
          const out = await apiUploadSafe(`${P}/items/${encodeURIComponent(code)}/photos`, fd, { label: `${it.code} ${it.name} ${inp.dataset.kind === "bad" ? "지적" : "양호"} 사진` });
          apply(code, out);
          n += 1;
        } catch (err) { msg.textContent = err.message; if (!err.queued) showError(errorEl, err); }
      }
      if (n) redraw(el, it);
    }));
    // 견본 칸 📷(10/30) — 그 칸 사진(있으면 바꿈), 양호/지적은 판정대로(사진에서 바꿀 수 있음), 설명은 견본 설명
    el.querySelectorAll("input[type=file][data-slot]").forEach((inp) => {
      const zone = inp.closest(".bj-slot-shot");
      if (zone && typeof enableFileDrop === "function") enableFileDrop(zone, inp);
      inp.addEventListener("change", async () => {
        const f = inp.files[0];
        inp.value = "";
        if (!f) return;
        const msg = el.querySelector(".bj-ph-msg");
        msg.textContent = "올리는 중…";
        const bad = isBadEval(job.eval[code]);
        const fd = new FormData();
        fd.append("file", f);
        fd.append("kind", bad && !inp.dataset.draw ? "bad" : "good");
        fd.append("slot", inp.dataset.slot);
        try {
          const out = await apiUploadSafe(`${P}/items/${encodeURIComponent(code)}/photos`, fd, { label: `${it.code} ${it.name} 견본 칸 사진` });
          apply(code, out);
          redraw(el, it);
        } catch (err) { msg.textContent = err.message; if (!err.queued) showError(errorEl, err); }
      });
    });
    el.querySelectorAll(".bj-slot-pick").forEach((b) => b.addEventListener("click", (ev) => { ev.preventDefault(); pickDrawing(it, Number(b.dataset.slot), () => redraw(el, it)); }));
    el.querySelectorAll(".bj-ph").forEach((ph) => {
      const pid = ph.dataset.pid;
      ph.querySelector(".bj-ph-cap").addEventListener("change", async (e) => {
        try { const out = await apiPatch(`${P}/items/${encodeURIComponent(code)}/photos/${pid}`, { caption: e.target.value }); apply(code, out); } catch (err) { showError(errorEl, err); }
      });
      ph.querySelector("button.bj-ph-kind")?.addEventListener("click", async () => { // 도면 칸 그림은 양호·지적 없음(span)
        const cur = (((job.results[code] || {}).photos || []).find((x) => x.id === pid) || {}).kind;
        try { const out = await apiPatch(`${P}/items/${encodeURIComponent(code)}/photos/${pid}`, { kind: cur === "bad" ? "good" : "bad" }); apply(code, out); redraw(el, it); } catch (err) { showError(errorEl, err); }
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
    try { plan = await api(`${P}/plan`); drawPlan(); drawItems(); } catch (err) { $("bj-plan-body").innerHTML = `<div class="mail-msg bad">${esc(err.message)}</div>`; }
  }
  const groupOf = (code) => (table.groups.find((g) => g.items.includes(code)) || {}).key;
  function drawPlan() {
    if (!plan) return;
    const items = plan.items, c = plan.count;
    const nm = (code) => (table.byCode[code] || {}).name || code;
    const nPh = (code) => (((job.results || {})[code] || {}).photos || []).length;
    const thumb = (code) => { const s = slotsOf(code).photo[0] || slotsOf(code).draw[0]; return s && s.file ? `<img class="bj-pl-th" loading="lazy" src="${sampleSrc(s.file)}" alt="" title="견본 — ${esc(s.caption || "")}" />` : '<span class="bj-pl-th"></span>'; };
    const row = (code) => `<button type="button" class="bj-pl-row" data-code="${esc(code)}">${thumb(code)}<span class="bj-pl-t"><b>${esc(code)} ${esc(nm(code))}</b><small>${esc(items[code].why || "")}</small></span>
      <span class="bj-pl-n ${nPh(code) ? "ok" : ""}">${nPh(code) ? `📷${nPh(code)}` : "아직"}</span></button>`;
    const qOf = (key) => plan.questions.find((x) => x.key === key) || { key, answer: "", label: key, items: [] };
    const qRow = (key, withItems) => { const q = qOf(key);
      return `<div class="bj-pl-q"><span>${esc(q.label)}${withItems && q.items.length ? ` <small>· ${esc(q.items.join(", "))}</small>` : ""}</span>
        <span class="bj-seg bj-fact" data-key="${esc(key)}">${["있음", "없음"].map((v) => `<button type="button" data-v="${v}" class="${q.answer === v ? "on" : ""}">${v}</button>`).join("")}</span></div>`; };
    const codes = (cat) => Object.keys(items).filter((k) => items[k].cat === cat);
    const must = codes("must");
    const places = (table.places || []).filter(([k]) => k !== "doc").map(([k, lab]) => [lab, must.filter((code) => ((table.item_places || {})[code] || ["out"]).includes(k))]).filter(([, l]) => l.length);
    const present = codes("present");
    const talkQ = plan.questions.filter((q) => q.kind === "talk"), landQ = plan.questions.filter((q) => q.kind === "land");
    const shown = new Set(present.flatMap((code) => items[code].asks));
    const siteRest = plan.questions.filter((q) => q.kind === "site" && !shown.has(q.key) && q.items.length); // 면담 항목에 섞인 현장 질문
    const na = codes("na"), naLeft = na.filter((k) => !items[k].marked_na && !items[k].touched), chk = codes("check");
    const sum = [["must", `반드시 찍을 사진 ${c.must}`], ["present", `있으면 찍을 사진 ${c.present}`], ["talk", `면담·서류 ${c.talk + c.doc + c.land}`], ["na", `해당없음 ${c.na}`], ["check", `확인 필요 ${c.check}`]];
    $("bj-plan-sub").textContent = "건축물대장·현장 답으로 법령상 적용대상을 가름 — 항목을 누르면 그 카드로";
    $("bj-plan-body").innerHTML = `<div class="bj-pl-sum">${sum.filter(([k]) => k !== "check" || c.check).map(([k, t]) => `<span class="${k}">${esc(t)}</span>`).join("")}</div>
      <div class="bj-pl-sec">① 반드시 찍을 사진 <small>장소별 — 왼쪽 그림은 견본</small></div>
      ${places.map(([lab, l]) => `<div class="bj-pl-place">${esc(lab)} ${l.length}</div><div class="bj-pl-grid">${l.map(row).join("")}</div>`).join("") || '<div class="mail-note">없음</div>'}
      ${present.length || siteRest.length ? `<div class="bj-pl-sec">② 있으면 찍을 사진 <small>법령상 의무는 아니지만 현장에 있으면 점검 — 있음/없음을 눌러 주세요</small></div>
        <div class="bj-pl-grid">${present.map((code) => `<div>${row(code)}${items[code].asks.map((k) => qRow(k, false)).join("")}</div>`).join("")}</div>
        ${siteRest.map((q) => qRow(q.key, true)).join("")}` : ""}
      ${talkQ.length || codes("talk").length ? `<div class="bj-pl-sec">③ 면담으로 확인 <small>관리자에게 물어 답을 눌러 주세요</small></div>
        ${codes("talk").map(row).join("")}${talkQ.map((q) => qRow(q.key, true)).join("")}
        <div class="mail-note">점검·검사 이행(소방·저수조·승강기·전기·가스 등)은 [그 밖의 항목] 탭, 관리계획 수립 여부는 [관리계획] 탭</div>` : ""}
      ${landQ.length || codes("doc").length ? `<div class="bj-pl-sec">④ 서류로 확인 <small>토지이용계획확인원(토지이음)·건축물대장</small></div>
        ${codes("doc").map(row).join("")}${landQ.map((q) => qRow(q.key, true)).join("")}` : ""}
      ${chk.length ? `<div class="bj-pl-sec">확인 필요 <small>대장 값이 모자라거나 기준일 경계</small></div><div class="bj-pl-grid">${chk.map(row).join("")}</div>` : ""}
      <div class="bj-pl-sec">⑤ 해당없음 — 안 찍어도 됨 <small>${na.length}개${naLeft.length ? ` · 아직 안 넣은 것 ${naLeft.length}` : ""}</small>
        ${naLeft.length ? `<button type="button" class="secondary btn-sm bj-pl-na-go">해당없음 ${naLeft.length}개 넣기(비고에 사유)</button>` : ""}</div>
      <details class="bj-pl-na"><summary>사유 보기 ▾</summary><ul>${na.map((k) => `<li><b>${esc(k)} ${esc(nm(k))}</b>${items[k].marked_na ? " ✓" : ""} — ${esc(items[k].reason)}</li>`).join("")}</ul></details>`;
    $("bj-plan-body").querySelectorAll(".bj-pl-row").forEach((b) => b.addEventListener("click", () => jumpTo({ code: b.dataset.code, tab: groupOf(b.dataset.code) })));
    $("bj-plan-body").querySelectorAll(".bj-fact button").forEach((b) => b.addEventListener("click", async () => {
      const key = b.closest(".bj-fact").dataset.key;
      const v = b.classList.contains("on") ? "" : b.dataset.v; // 한 번 더 = 지움
      try { plan = await api(`${P}/facts`, { method: "PUT", body: JSON.stringify({ facts: { [key]: v } }) }); drawPlan(); drawItems(); } catch (err) { showError(errorEl, err); }
    }));
    $("bj-plan-body").querySelector(".bj-pl-na-go")?.addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      if (!confirm(`법령상 해당없음 ${naLeft.length}개를 해당없음으로 넣고 비고에 사유를 적을까요?\n(판정·사진을 넣은 항목은 건드리지 않습니다)`)) return;
      btn.disabled = true;
      try {
        const out = await apiPost(`${P}/plan/na`, {});
        plan = out.plan;
        job = { ...job, ...out };
        drawTop(); drawTabs(); drawItems(); drawDone(); drawPlan();
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
  function hintFor(caption) { // 쪽 글에서 찾은 도면 이름이 견본 설명과 맞는 그림(추천) — 정면도·배치도 같은 것만 확실
    const k = keyOf(caption);
    if (!k) return null;
    return pool().find((d) => (d.hint || "").split(" ").some((h) => h && (keyOf(h) === k || (k.length >= 3 && keyOf(h).includes(k))))) || null;
  }
  function onDrawings(out) {
    job.files = { ...(job.files || {}), drawings: out.drawings };
    if (out.results) job.results = out.results;
    if (out.eval) job.eval = out.eval;
    drawPool();
    refreshTabCounts(); drawDone();
  }
  function drawPool() {
    const list = pool();
    $("bj-draw-sub").textContent = list.length ? `그림 ${list.length}장 · 넣은 자리 ${drawRows().filter((x) => x.p).length}/${drawRows().length}` : "도면 PDF를 한꺼번에 올리고 항목 자리(정면도·배치도·조경표기도면 …)에 고르기";
    $("bj-pool").innerHTML = list.map((d) => `<div class="bj-pool-it" data-id="${esc(d.id)}"><a href="${drawSrc(d)}" target="_blank" rel="noopener"><img loading="lazy" src="${drawSrc(d)}" alt="" /></a>
      <b title="${esc(drawLabel(d))}">${esc(drawLabel(d))}</b><small title="${esc(d.hint || "")}">${esc(d.hint || "")}</small>${(d.used || []).length ? `<small>넣은 곳 ${esc(d.used.join(", "))}</small>` : ""}
      <button type="button" class="bj-pool-del" title="모음에서 지우기(항목에 넣은 것은 그대로)">✕</button></div>`).join("");
    $("bj-pool").querySelectorAll(".bj-pool-del").forEach((b) => b.addEventListener("click", async () => {
      if (!confirm("이 그림을 모음에서 지울까요? (항목에 이미 넣은 것은 그대로)")) return;
      try { onDrawings(await api(`${P}/drawings/${encodeURIComponent(b.closest(".bj-pool-it").dataset.id)}`, { method: "DELETE" })); } catch (err) { showError(errorEl, err); }
    }));
    const rows = drawRows();
    const sugg = rows.filter((x) => !x.p && hintFor(x.s.caption));
    $("bj-draw-slots").innerHTML = (rows.length ? rows.map((x) => {
      const h = !x.p ? hintFor(x.s.caption) : null;
      return `<div class="bj-draw-row" data-code="${esc(x.it.code)}" data-slot="${x.s.n}"><span><span class="bj-code">${esc(x.it.code)}</span>${esc(x.it.name)}</span><span>${esc(x.s.caption)}</span>
        ${x.p ? `<img src="${BASE}/api${P}/photo/${esc(x.p.id)}" alt="" />` : x.s.file ? `<img src="${sampleSrc(x.s.file)}" alt="" title="견본" style="opacity:.45" />` : "<span></span>"}
        <select class="bj-draw-sel">${x.p ? `<option value="__keep" selected>${x.p.drawing ? `지금: ${esc(drawLabel(pool().find((d) => d.id === x.p.drawing) || { name: "고른 그림" }))}` : "지금: 📷 현장에서 찍은 사진"}</option><option value="">— 비우기 —</option>`
          : '<option value="__keep">— 고르기 —</option>'}${pool().map((d) => `<option value="${esc(d.id)}">${esc(drawLabel(d))}${h && h.id === d.id ? " (추천)" : ""}</option>`).join("")}</select></div>`;
    }).join("") : '<div class="mail-note">견본에 도면 자리가 없습니다.</div>')
      + (sugg.length ? `<div class="bj-top-btns"><button type="button" class="secondary" id="bj-draw-auto">✨ 추천 ${sugg.length}곳 한꺼번에 넣기</button><span class="mail-note">쪽 글의 도면 이름(정면도·배치도 …)이 견본 설명과 같은 것</span></div>` : "");
    $("bj-draw-slots").querySelectorAll(".bj-draw-sel").forEach((sel) => sel.addEventListener("change", async () => {
      const row = sel.closest(".bj-draw-row");
      if (sel.value === "__keep") return;
      if (!sel.value && !confirm("이 자리를 비울까요? (그 항목 현황사진에서 빠집니다)")) { drawPool(); return; }
      await putSlot(row.dataset.code, Number(row.dataset.slot), sel.value || null);
    }));
    $("bj-draw-auto")?.addEventListener("click", async (e) => {
      e.currentTarget.disabled = true;
      for (const x of sugg) await putSlot(x.it.code, x.s.n, hintFor(x.s.caption).id, true);
      drawPool(); drawItems();
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
    msg.textContent = `✓ ${n}개 올림 — 아래 자리마다 고르세요`;
  }
  const drawIn = $("bj-draw-in");
  drawIn.addEventListener("change", () => { const fs = [...drawIn.files]; drawIn.value = ""; if (fs.length) uploadDrawings(fs); });
  if (typeof enableFileDrop === "function") enableFileDrop($("bj-draw-drop"), drawIn);
  $("bj-draw-reg").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    try { onDrawings(await apiPost(`${P}/drawings/register`, {})); $("bj-draw-msg").textContent = "✓ 건축물대장 쪽을 넣었습니다"; } catch (err) { $("bj-draw-msg").textContent = err.message; }
    btn.disabled = false;
  });
  function pickDrawing(it, n, after) { // 항목 카드 [📐 도면 고르기] — 모음에서 고르거나 바로 올리기
    const s = slotsOf(it.code).draw.concat(slotsOf(it.code).photo).find((x) => x.n === n) || {};
    const ov = document.createElement("div");
    ov.className = "mail-overlay";
    const draw = () => {
      const h = hintFor(s.caption);
      ov.innerHTML = `<div class="mail-box" role="dialog" aria-modal="true"><div class="mail-head"><b>📐 ${esc(it.code)} ${esc(it.name)} — ${esc(s.caption || "도면")}</b>
        <span class="mail-sub">위 [📐 도면·서류 그림]에 올린 그림에서 고르세요${h ? " — 노란 테두리 = 쪽 글의 도면 이름이 같은 것" : ""}</span></div>
        <div class="bj-pick-grid">${pool().map((d) => `<div class="bj-pool-it pick${h && h.id === d.id ? " hint" : ""}" data-id="${esc(d.id)}"><img loading="lazy" src="${drawSrc(d)}" alt="" />
          <b>${esc(drawLabel(d))}</b><small>${h && h.id === d.id ? '<span class="bj-hint-tag">추천 · </span>' : ""}${esc(d.hint || "")}</small></div>`).join("") || '<div class="mail-note">아직 올린 그림이 없습니다 — 아래에서 올리세요.</div>'}</div>
        <div class="mail-foot"><label class="secondary bj-file-btn">📐 도면 PDF·그림 올리기<input type="file" accept=".pdf,application/pdf,image/*" multiple hidden data-kr-file="skip" class="bj-pick-up" /></label>
          <button type="button" class="mail-cancel">닫기</button></div></div>`;
      ov.querySelector(".mail-cancel").addEventListener("click", () => ov.remove());
      ov.querySelectorAll(".bj-pool-it.pick").forEach((c) => c.addEventListener("click", async () => {
        ov.remove();
        await putSlot(it.code, n, c.dataset.id, true);
        drawPool();
        after();
      }));
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
