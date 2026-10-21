// 시특법 시설물 화면의 "점검 회차" 칸(sitok-facility.html?id=, 2026-10-10 4단계 → 10/14 형 피드백 ⑦ 3층 구조) — 회차(연도·반기) 만들기 + 회차 목록(한 줄씩).
// 회차 줄을 누르면 회차 화면(sitok-round.html?report= — js/sitok-round.js: 현장 조사·재료시험·상태평가·면담·현황·AI 초안·보고서 만들기·회차 정보)로 간다.
// 올해 회차만 펼치고 지난 회차는 "지난 회차 N개 보기"로 접음. 만드는 중(한글 PDF 몇 분)은 3초마다 진행 확인.
// 서버 server/api/routers/sitok_reports.py. 10/13 회차 ↔ 계약: [+ 회차 만들기]는 그 반기를 계약기간이 덮는 계약을 붙임(GET …/contract-for). 없으면 "새 계약서를 올리세요" 칸 —
// 계약서 PDF를 올리면 읽어서 계약을 추가하고(계약 칸에도 생김) 그 회차에 붙임, 또는 [계약 없이 만들기](나중에 계약을 추가하면 자동으로 붙음).
// 장기·지속 시설물은 마지막 계약이 끝나기 60일 전부터 맨 위에 "다음 계약서 필요".

(function () {
  const fid = Number(new URLSearchParams(location.search).get("id")) || null;
  const panel = document.getElementById("sk-rep-panel");
  if (!fid || !panel) return;
  panel.hidden = false;
  const box = document.getElementById("sk-reps");
  const errorEl = document.getElementById("error");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const err = (e) => showError(errorEl, e);
  let data = null;
  const polling = {};
  let flash = null; // 다시 그린 뒤 맨 위에 띄울 안내 [글, "ok"|"warn"]
  const ymdDot = (s) => (s || "?").replaceAll("-", ".");
  const CON_KEYS = ["sector", "title", "contract_no", "contract_date", "start_date", "end_date", "halves", "first_half_end", "second_half_start", "rounds",
    "amount", "rep_name", "joint_type", "joint_pct", "bid_method", "field"];

  // 회차 한 줄 — 진행 표시 칩(현장 조사 → 재료시험·상태평가(정밀) → 면담 → 현황 → AI → 보고서)
  function row(r) {
    const kind = r.kind || "정기";
    const el = document.createElement("a");
    el.className = `sk-round ${r.status}${r.past ? " past" : ""}`;
    el.href = `sitok-round.html?report=${r.id}`;
    const chip = (on, label) => `<span class="sk-chip${on ? " on" : ""}">${on ? "✓ " : ""}${label}</span>`;
    const report = r.status === "running" ? `<span class="sk-chip run">⏳ 만드는 중 — ${esc(r.message)}</span>`
      : r.status === "failed" ? `<span class="sk-chip bad">✗ 만들기 실패</span>`
        : r.has_pdf ? `<span class="sk-chip on">✓ 보고서 ${esc((r.made_at || "").slice(5, 10).replace("-", "."))}</span>` : chip(false, "보고서");
    const seis = kind === "성능평가", sm = r.seismic || {}; // 내진성능평가 회차(10/21)
    const chips = r.past ? '<span class="sk-chip on">✓ 이미 낸 보고서(등록)</span>'
      : seis ? chip(r.has_field, "현장 조사") + chip(sm.schedule > 0 && !sm.schedule_need, "일람표") + chip(sm.rebar > 0, "철근탐사") + report
      : chip(r.has_field, "현장 조사") + (kind === "정밀" ? chip(r.has_tests, "재료시험") + chip(r.has_rating, "상태평가") : "")
        + chip(r.has_survey, "면담") + chip(r.has_detail, "현황") + chip(r.has_ai, "AI 초안") + report;
    el.innerHTML = `<div class="sk-round-main"><div class="sk-round-title"><b>${r.year}년 ${seis ? "내진성능평가" : esc(r.half)}</b>${seis ? '<span class="sk-kind pre">내진성능평가</span>'
      : `<button type="button" class="sk-kind sk-kind-btn ${kind === "정밀" ? "pre" : ""}" title="누르면 ${kind === "정밀" ? "정기" : "정밀"}로 바꿉니다">${kind}안전점검 ▾</button>`}
        ${r.period_start ? `<span class="sk-help">${ymdDot(r.period_start)} ~ ${ymdDot(r.period_end)}</span>` : ""}</div>
      <div class="sk-round-prog">${chips}</div></div><span class="sk-round-open">열기 ›</span>`;
    el.querySelector(".sk-kind-btn")?.addEventListener("click", async (e) => { // 종류 바꾸기(10/14 형 피드백 — 회차 정보 안에만 있어 못 찾음)
      e.preventDefault();
      e.stopPropagation();
      const to = kind === "정밀" ? "정기" : "정밀";
      if (!confirm(`${r.year}년 ${r.half}를 ${to}안전점검으로 바꿀까요?`)) return;
      try { await apiPatch(`/sitok/reports/${r.id}`, { kind: to }); load(); } catch (x) { err(x); }
    });
    if (r.status === "running") poll(r.id);
    return el;
  }

  function poll(id) {
    if (polling[id]) return;
    polling[id] = setInterval(async () => {
      try {
        const r = await api(`/sitok/reports/${id}`);
        if (r.status !== "running") { clearInterval(polling[id]); delete polling[id]; load(); }
      } catch (_) { /* 다음에 다시 */ }
    }, 3000);
  }

  // 장기·지속 계약 끝나기 전·끝난 뒤 알림(서버 renew_info)
  function renewNote() {
    const r = data.renew;
    if (!r) return null;
    const el = document.createElement("div");
    el.className = `sk-renew${r.days < 0 ? " over" : ""}`;
    el.textContent = r.days < 0
      ? `⚠ 장기·지속 계약이 ${ymdDot(r.end)}에 끝났습니다 — 다음 계약서를 올려야 다음 회차 보고서에 들어갑니다(아래 [+ 회차 만들기] 때 올려도 됨).`
      : `⏳ 장기·지속 계약이 ${ymdDot(r.end)}에 끝납니다(${r.days}일 남음) — 다음 계약서를 준비하세요. 다음 회차를 만들 때 올리면 그 회차에 붙습니다.`;
    return el;
  }

  async function createReport(year, half, contractId, kind) {
    const body = { year, half, contract_id: contractId };
    if (kind) body.kind = kind; // 비우면 서버가 계약서 회차 줄에서(정기/정밀)
    const chief = data.persons.find((p) => p.sitok_grade.includes("특급")) || data.persons[0];
    if (chief) body.chief_id = chief.id;
    const other = data.persons.find((p) => p.id !== chief?.id);
    if (other) body.participant_ids = [other.id];
    return apiPost(`/sitok/facilities/${fid}/reports`, body);
  }

  // 그 반기를 덮는 계약이 없을 때 — 계약서 PDF 올리기 / 계약 없이 만들기 / 취소
  function noContract(el, year, half, latest) {
    el.querySelector(".nr-nocon")?.remove();
    const box2 = document.createElement("div");
    box2.className = "nr-nocon";
    box2.innerHTML = `<b>⚠ ${year}년 ${half}를 덮는 계약이 없습니다</b>
      <span>${latest ? `마지막 계약: ${esc(latest.title || "계약")} (${ymdDot(latest.start_date)} ~ ${ymdDot(latest.end_date)})` : "등록된 계약이 없습니다"}
        — 이번 계약서를 올리면 읽어서 계약을 추가하고 이 회차에 붙입니다.</span>
      <div class="nr-nocon-acts">
        <label class="sk-drop nr-con-drop"><input type="file" accept="application/pdf,.pdf" hidden data-kr-file="skip" />
          <b>📄 이번 계약서 PDF 올리기</b><span class="sk-drop-msg">눌러서 고르거나 끌어다 놓기 — 민간 계약서(스캔도 됨)·나라장터 계약서</span></label>
        <div class="nr-nocon-btns"><button type="button" class="secondary btn-sm nr-skip">계약 없이 만들기</button>
          <button type="button" class="secondary btn-sm nr-cancel">취소</button></div>
      </div>
      <span class="sk-help">계약 없이 만들어도 나중에 아래 "계약"에서 [+ 계약 추가]로 이 반기를 덮는 계약을 넣으면 자동으로 붙습니다.</span>`;
    el.appendChild(box2);
    const msg = box2.querySelector(".sk-drop-msg");
    const input = box2.querySelector("input");
    enableFileDrop(box2.querySelector(".nr-con-drop"), input);
    box2.querySelector(".nr-cancel").addEventListener("click", () => box2.remove());
    box2.querySelector(".nr-skip").addEventListener("click", async () => {
      box2.classList.add("busy");
      try {
        await createReport(year, half, null, el.querySelector(".nr-kind")?.value || "정기"); // 계약이 없으면 종류를 알 수 없어 정기(배지로 바꿈)
        flash = [`${year}년 ${half} 회차를 계약 없이 만들었습니다 — 계약을 추가하면 자동으로 붙습니다.`, "warn"];
        load();
      } catch (e) { err(e); box2.classList.remove("busy"); }
    });
    input.addEventListener("change", async () => {
      const file = input.files[0];
      input.value = "";
      if (!file) return;
      box2.classList.add("busy");
      msg.textContent = `${file.name} — 읽는 중…(10~30초)`;
      try {
        const fd = new FormData();
        fd.append("kind", "contract");
        fd.append("file", file);
        const rd = await apiUpload("/sitok/read", fd);
        const fields = Object.fromEntries(CON_KEYS.filter((k) => rd.fields?.[k] !== undefined && rd.fields[k] !== "" && rd.fields[k] !== null)
          .map((k) => [k, rd.fields[k]]));
        const out = await apiPost(`/sitok/facilities/${fid}/contracts`, { ...fields, contract_token: rd.token });
        try { await createReport(year, half, out.new_contract_id, el.querySelector(".nr-kind")?.value || ""); } catch (x) {
          if (x.status !== 428) throw x;
          window.dispatchEvent(new Event("sitok-contracts-changed"));
          box2.remove();
          askKind(el, year, half, out.new_contract_id);
          return;
        }
        const chk = await api(`/sitok/facilities/${fid}/contract-for?year=${year}&half=${encodeURIComponent(half)}`);
        const fits = chk.contract && chk.contract.id === out.new_contract_id;
        flash = rd.error ? [`계약서를 읽지 못해 칸이 비었습니다 — 아래 "계약"에서 날짜·금액을 채우세요. (${rd.error})`, "warn"]
          : fits ? [`✓ 계약서를 읽어 계약을 추가하고 ${year}년 ${half} 회차에 붙였습니다 — 아래 "계약"에서 읽은 값을 확인하세요.`, "ok"]
            : [`계약을 추가해 이 회차에 붙였지만, 읽은 계약기간이 ${year}년 ${half}와 맞지 않습니다 — "계약"에서 날짜를 확인하세요.`, "warn"];
        window.dispatchEvent(new Event("sitok-contracts-changed")); // 시설물 화면 계약 칸 다시 그리기(js/sitok-facility.js)
        load();
      } catch (e) {
        err(e);
        box2.classList.remove("busy");
        msg.textContent = "눌러서 고르거나 끌어다 놓기";
      }
    });
  }

  // 계약서에서 종류(정기/정밀)를 못 읽을 때 — 조용히 정기로 만들지 않고 물음(10/14 형 피드백: 꿈에블리스나인 "정기(정밀)" 스캔 계약서)
  function askKind(el, year, half, contractId) {
    el.querySelector(".nr-kind-ask")?.remove();
    const box2 = document.createElement("div");
    box2.className = "nr-nocon nr-kind-ask";
    box2.innerHTML = `<b>⚠ 계약서에서 ${year}년 ${half} 회차 종류를 못 읽었습니다</b><span>계약서에 "정기"·"정밀"이 둘 다 있거나 회차 줄이 없습니다 — 이번 회차 종류를 골라 주세요.</span>
      <div class="nr-nocon-btns"><button type="button" class="btn-sm" data-kind="정기">정기안전점검으로 만들기</button>
        <button type="button" class="btn-sm" data-kind="정밀">정밀안전점검으로 만들기</button><button type="button" class="secondary btn-sm nr-cancel">취소</button></div>`;
    el.appendChild(box2);
    box2.querySelector(".nr-cancel").addEventListener("click", () => box2.remove());
    box2.querySelectorAll("[data-kind]").forEach((b) => b.addEventListener("click", async () => {
      box2.classList.add("busy");
      try {
        const made = await createReport(year, half, contractId, b.dataset.kind);
        if (made && made.id) { location.href = `sitok-round.html?report=${made.id}`; return; }
        load();
      } catch (x) { err(x); box2.classList.remove("busy"); }
    }));
  }

  function drawNew() {
    const d = data.defaults;
    const el = document.createElement("div");
    el.className = "sk-rep-new";
    el.innerHTML = `<b>새 회차</b>
      <input type="number" class="nr-year" value="${d.year}" min="2000" max="2100" aria-label="연도" />년
      <select class="nr-half" title="연 3회(D·E등급)면 해빙기·우기·동절기">${["상반기", "하반기", "해빙기", "우기", "동절기"].map((h) => `<option${d.half === h ? " selected" : ""}>${h}</option>`).join("")}</select>
      <select class="nr-kind" title="회차 종류 — 계약서 그 반기 줄(정기/정밀)에서 자동, 틀리면 고르기. 내진성능평가는 반기 없이 해마다 하나(10/21)"><option value="">계약서대로</option><option>정기</option><option>정밀</option></select>
      <button type="button" class="btn-sm nr-add">+ 회차 만들기</button>
      <label class="secondary-link nr-past" title="이미 낸 지난 반기 보고서 한글(.hwp·.hwpx) — 연도·반기·점검기간은 결과표에서 읽고, 다음 회차가 이걸 틀로 씁니다">이미 낸 보고서 등록<input type="file" accept=".hwp,.hwpx" hidden data-kr-file="1" /></label>
      <span class="sk-help nr-msg">보고서는 회사 원본 템플릿으로 만들고, 직전 회차(또는 [이미 낸 보고서 등록]으로 올린 지난 반기 한글)에서는 이력·시설물 현황·지난 평가 같은 데이터만 가져옵니다.</span>`;
    const past = el.querySelector(".nr-past input");
    past.addEventListener("change", async () => {
      if (!past.files[0]) return;
      const msg = el.querySelector(".nr-msg");
      el.classList.add("busy");
      msg.textContent = `${past.files[0].name} 올리는 중…(큰 파일은 몇십 초)`;
      try {
        const fd = new FormData();
        fd.append("file", past.files[0]);
        await apiUpload(`/sitok/facilities/${fid}/reports/past`, fd);
        load();
      } catch (e) { err(e); el.classList.remove("busy"); msg.textContent = ""; }
    });
    enableFileDrop(el.querySelector(".nr-past"), past);
    const kindSel = el.querySelector(".nr-kind"), halfSel = el.querySelector(".nr-half"); // 내진성능평가 = 반기 칸 없음(서버가 "성능평가"로)
    kindSel.addEventListener("change", () => { halfSel.hidden = kindSel.value === "성능평가"; });
    el.querySelector(".nr-add").addEventListener("click", async () => { // 그 반기를 덮는 계약을 찾아 붙임 — 없으면 계약서 올리기 칸
      const kind = el.querySelector(".nr-kind").value || "";
      const year = Number(el.querySelector(".nr-year").value), half = kind === "성능평가" ? "성능평가" : el.querySelector(".nr-half").value;
      el.classList.add("busy");
      try {
        const r = await api(`/sitok/facilities/${fid}/contract-for?year=${year}&half=${encodeURIComponent(half)}`);
        if (r.contract) {
          let made;
          try { made = await createReport(year, half, r.contract.id, kind); } catch (x) {
            if (x.status !== 428) throw x;
            askKind(el, year, half, r.contract.id); // 계약서에서 종류를 못 읽음 → 정기/정밀 고르기(10/14)
            return;
          }
          if (made && made.id) { location.href = `sitok-round.html?report=${made.id}`; return; } // 만들자마자 회차 화면으로
          load();
        } else {
          noContract(el, year, half, r.latest);
        }
      } catch (e) { err(e); } finally { el.classList.remove("busy"); }
    });
    return el;
  }

  async function load() {
    try {
      data = await api(`/sitok/facilities/${fid}/reports`);
      box.innerHTML = "";
      if (flash) {
        const f2 = document.createElement("div");
        f2.className = `sk-flash ${flash[1]}`;
        f2.textContent = flash[0];
        box.appendChild(f2);
        flash = null;
      }
      const renew = renewNote();
      if (renew) box.appendChild(renew);
      box.appendChild(drawNew());
      const reps = data.reports; // 서버가 최신 회차부터
      const top = Math.max(data.defaults.year, ...reps.map((r) => r.year)); // 올해(또는 가장 최근 연도)만 펼침
      const cur = reps.filter((r) => r.year >= top), old = reps.filter((r) => r.year < top);
      const list = document.createElement("div");
      list.className = "sk-rounds";
      cur.forEach((x) => list.appendChild(row(x)));
      box.appendChild(list);
      if (old.length) {
        const det = document.createElement("details");
        det.className = "sk-old";
        det.innerHTML = `<summary>지난 회차 ${old.length}개 보기</summary>`;
        const l2 = document.createElement("div");
        l2.className = "sk-rounds";
        old.forEach((x) => l2.appendChild(row(x)));
        det.appendChild(l2);
        box.appendChild(det);
      }
      if (!reps.length) box.insertAdjacentHTML("beforeend", '<div class="empty-note">아직 회차가 없습니다. 위에서 [+ 회차 만들기].</div>');
    } catch (e) { err(e); }
  }
  window.addEventListener("sitok-group-changed", load); // 같이 점검하는 동이 바뀌면(js/sitok-group.js)
  load();
})();
