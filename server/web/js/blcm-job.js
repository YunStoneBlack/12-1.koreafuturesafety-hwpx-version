// 건축물관리점검 건 화면(2026-10-29 사용자 "적합을 누르면 양호사진, 부적합을 누르고 사진을 넣으면 변경유형 판단해 체크, 기준면적은 대장·도면에서,
// 개선사항·방안근거·비고(사진설명)가 자동으로 — AI 분석은 덧붙여 다시 쓰기"). 항목표 = GET /blcm/items(매뉴얼 25.02 소항목 50개).
// 카드마다 고치면 0.6초 뒤 저장(PUT /blcm/jobs/{id}/items/{code}) → 서버가 판정(건수·점수) 계산해 돌려줌. 사진 = 신호 약하면 폰 보관(apiUploadSafe).
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const errorEl = $("error");
  const jid = Number(new URLSearchParams(location.search).get("id")) || 0;
  const P = `/blcm/jobs/${jid}`;
  let job = null, table = null;
  const openCards = new Set();
  let tab = (() => { try { return localStorage.getItem("bj-tab") || ""; } catch (_) { return ""; } })();
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
  function drawTabs() {
    if (!tab || !table.groups.some((g) => g.key === tab)) tab = table.groups[0].key;
    $("bj-tabs").innerHTML = table.groups.map((g) => {
      const done = g.items.filter((c) => ["done", "na"].includes((job.eval[c] || {}).state)).length;
      return `<button type="button" class="bj-tab${g.key === tab ? " on" : ""}" data-k="${esc(g.key)}" role="tab">${esc(g.label)} <small>${done}/${g.items.length}</small></button>`;
    }).join("");
    $("bj-tabs").querySelectorAll(".bj-tab").forEach((b) => b.addEventListener("click", () => {
      tab = b.dataset.k;
      try { localStorage.setItem("bj-tab", tab); } catch (_) { /* */ }
      drawTabs(); drawItems();
    }));
  }

  function chip(ev) {
    if (!ev || ev.state === "empty") return '<span class="bj-chip empty">미작성</span>';
    if (ev.state === "na") return '<span class="bj-chip na">해당없음</span>';
    if (ev.judge) return `<span class="bj-chip ${ev.judge === "적합" ? "ok" : "bad"}">${esc(ev.summary)}</span>`;
    const worst = (ev.details || []).map((d) => d.judge).filter(Boolean);
    const bad = worst.some((j) => ["미흡", "불량", "부적합"].includes(j));
    const mid = worst.includes("보통");
    return `<span class="bj-chip ${bad ? "bad" : mid ? "mid" : "ok"}">${esc(ev.summary || "작성 중")}</span>${ev.state === "part" ? '<span class="bj-chip empty">일부</span>' : ""}`;
  }

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
      return `<div class="bj-det"><div class="bj-det-h"><b>${esc(d.name)}</b> <small>(${d.points ?? ""}점)</small>${dv.judge ? ` <span class="bj-chip ${["미흡", "불량", "부적합"].includes(dv.judge) ? "bad" : dv.judge === "보통" ? "mid" : dv.judge === "해당없음" ? "na" : "ok"}">${esc(dv.judge)}${dv.score != null ? ` ${dv.score}/${dv.full}점` : ""}</span>` : ""}</div>${subs}</div>`;
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

  function photosHtml(r) {
    const ph = r.photos || [];
    const one = (p) => `<div class="bj-ph ${p.kind === "bad" ? "bad" : "good"}" data-pid="${esc(p.id)}">
        <a href="${BASE}/api${P}/photo/${esc(p.id)}" target="_blank" rel="noopener"><img loading="lazy" src="${BASE}/api${P}/photo/${esc(p.id)}" alt="" /></a>
        <div class="bj-ph-b"><button type="button" class="bj-ph-kind" title="양호·지적 바꾸기">${p.kind === "bad" ? "지적" : "양호"}</button><button type="button" class="bj-ph-del" title="지우기">✕</button></div>
        <input class="bj-ph-cap" value="${esc(p.caption || "")}" placeholder="사진 설명" maxlength="60" /></div>`;
    return `<div class="bj-photos"><div class="bj-lab">현황사진 <small>(적합·양호 = 양호 사진, 부적합 = 지적 사진)</small></div>
      <div class="bj-ph-add"><label class="secondary bj-file-btn">📷 양호 사진<input type="file" accept="image/*" multiple hidden data-kr-file="skip" data-kind="good" /></label>
        <label class="secondary bj-file-btn bad">📷 지적 사진<input type="file" accept="image/*" multiple hidden data-kr-file="skip" data-kind="bad" /></label><span class="mail-note bj-ph-msg"></span></div>
      <div class="bj-ph-grid">${ph.map(one).join("") || '<div class="mail-note">사진 없음</div>'}</div></div>`;
  }

  function cardHtml(it) {
    const r = (job.results || {})[it.code] || {};
    const ev = job.eval[it.code];
    const tx = r.texts || {};
    const nPh = (r.photos || []).length;
    return `<summary class="bj-card-h"><span class="bj-code">${esc(it.code)}</span><b>${esc(it.name)}</b><span class="bj-mid">${esc(it.mid)}</span>${chip(ev)}${nPh ? `<span class="bj-nph">📷${nPh}</span>` : ""}${r.ai ? '<span class="bj-nph" title="AI로 채움">🤖</span>' : ""}<span class="sk-fold-arrow">▾</span></summary>
      <div class="bj-card-b">
        <label class="bj-na"><input type="checkbox" class="bj-na-in" ${r.na ? "checked" : ""} /> 이 항목 해당없음(적용 대상 아님 — 비고에 사유)</label>
        <div class="bj-judge"${r.na ? " hidden" : ""}>${judgeHtml(it, r, ev)}
          <div class="bj-row"><span class="bj-lab">현행기준과의 비교·검토</span>${seg("cmp", CMP, r.cmp || "")}</div>
          <div class="bj-row"><span class="bj-lab">설계도서(사용승인도면 등)와의 적합여부</span>${seg("design", DESIGN, r.design || "")}</div>
          ${statusHtml(it, r)}</div>
        ${photosHtml(r)}
        <div class="bj-ai"><input class="bj-ai-note" maxlength="600" placeholder="AI에 덧붙일 내용(예: 실외기 2대, 도면상 조경면적 73.21㎡)" />
          <button type="button" class="bj-ai-go">🤖 AI로 채우기</button><span class="mail-note bj-ai-msg">${r.ai && r.ai.made_at ? `AI ${esc(r.ai.made_at)}` : "사진·대장으로 점검현황·글을 채움(약 30~60원)"}</span></div>
        <div class="bj-texts">${TEXTS.map(([k, lab]) => `<div class="sk-f"><label>${esc(lab)}</label><textarea data-tx="${k}" rows="${k === "basis" ? 3 : 2}" maxlength="3000">${esc(tx[k] || "")}</textarea></div>`).join("")}</div>
        <details class="bj-man"><summary>📘 매뉴얼 점검기준 · 개선방안 안내 · 관련법규</summary>
          <div class="bj-man-b">${(it.criteria || []).map((x) => `<div>${esc(x)}</div>`).join("")}<div class="bj-law">※관련법규: ${esc(it.laws || "-")}</div></div></details>
      </div>`;
  }

  function drawItems() {
    const g = table.groups.find((x) => x.key === tab);
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
    $("bj-tabs").querySelectorAll(".bj-tab").forEach((b) => {
      const gg = table.groups.find((x) => x.key === b.dataset.k);
      const n = gg.items.filter((c) => ["done", "na"].includes((job.eval[c] || {}).state)).length;
      b.querySelector("small").textContent = `${n}/${gg.items.length}`;
    });
    return done;
  }

  function apply(code, out) {
    job.results = { ...(job.results || {}), [code]: out.result };
    job.eval = { ...job.eval, [code]: out.eval };
    if (out.progress) Object.assign(job, out.progress);
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
    // 사진
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
    el.querySelectorAll(".bj-ph").forEach((ph) => {
      const pid = ph.dataset.pid;
      ph.querySelector(".bj-ph-cap").addEventListener("change", async (e) => {
        try { const out = await apiPatch(`${P}/items/${encodeURIComponent(code)}/photos/${pid}`, { caption: e.target.value }); apply(code, out); } catch (err) { showError(errorEl, err); }
      });
      ph.querySelector(".bj-ph-kind").addEventListener("click", async () => {
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
      drawTop(); drawInfo(); drawTabs(); drawItems();
    } catch (err) { showError(errorEl, err); }
  }
  load();
})();
