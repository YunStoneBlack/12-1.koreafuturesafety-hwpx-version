// 시특법 회차 화면 "📤 FMS 제출" 칸(2026-10-15 — 시특법 7단계). 서버 server/api/routers/sitok_fms.py, 작업 프로그램 server/worker/fms_worker.py.
// 흐름(형 PPT): 계약 등록 → 승인요청 → 관리주체 승인 → 실적보고·e-보고서 → 승인요청 → 관리주체 승인. 관리주체 계정이 있으면 승인까지 자동(민재형 10/15).
// [연습] = 채워 보기만(저장 안 함, FMS 대표자 읽기). 계약 번호가 생긴 뒤엔 [실적 연습] — 실적 화면 채워 찍기·e-보고서 폴더 확인(10/25). 실제 단계는 확인 창 뒤 대기열 → 3초마다 상태. "승인요청 전에 멈추기"(처음 몇 번 — 형이 FMS에서 보고 직접 승인요청).
(function () {
  const rid = new URLSearchParams(location.search).get("report");
  const box = document.getElementById("rd-fms");
  if (!rid || !box) return;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const won = (n) => Number(n || 0).toLocaleString();
  let info = null, poll = null, stop = true, editing = "";
  const sched = (j) => j.status === "queued" && j.run_at && new Date(j.run_at.replace(" ", "T")) > new Date(); // 예약(10/25) — 시각 전이면 기다리는 중
  const running = (j) => (j.status === "queued" && !sched(j)) || j.status === "running";
  const ST = { queued: "대기", running: "진행 중", done: "완료", failed: "멈춤", cancelled: "취소" };
  const mmdd = (iso) => { const d = new Date(`${iso}T00:00:00`); return `${d.getMonth() + 1}/${d.getDate()}`; };

  async function load(quiet) {
    try {
      info = await api(`/sitok/reports/${rid}/fms`);
      draw();
      if (info.jobs.some(running)) { if (!poll) poll = setInterval(() => load(true), 3000); } else if (poll) { clearInterval(poll); poll = null; }
    } catch (err) {
      if (!quiet) box.innerHTML = `<div class="mail-msg bad">${esc(err.message)}</div>`;
    }
  }

  function stateLine() {
    const s = info.state || {}, one = (k) => s[k] ? `${ST[s[k].status] || s[k].status} · ${esc(s[k].step || "")} <small>${esc(s[k].at || "")}</small>` : "아직";
    const dl = info.deadline, done = s.result && s.result.status === "done";
    const due = dl && !done ? `<span class="fms-due${dl.days_left <= 7 ? " near" : ""}"><b>실적보고 기한</b> ${mmdd(dl.start)}~${mmdd(dl.end)} ${dl.days_left >= 0 ? `(D-${dl.days_left})` : `(${-dl.days_left}일 지남 — 과태료)`}</span>` : "";
    return `<div class="fms-state"><span><b>FMS 계약 번호</b> ${esc(s.project_no || "없음")}</span><span><b>계약</b> ${one("contract")}</span><span><b>실적</b> ${one("result")}</span>${due}</div>`;
  }

  function accounts() {
    const a = info.accounts;
    const comp = editing === "company"
      ? `<span class="fms-cred"><input class="fc-id" placeholder="FMS 아이디" value="${esc(a.company_id)}" /><input class="fc-pw" type="password" placeholder="비밀번호" autocomplete="new-password" /><button type="button" class="secondary fms-mini fms-eye" aria-label="비밀번호 보기" title="비밀번호 보기">👁</button>
         <button type="button" class="fc-save">저장</button><button type="button" class="secondary fc-cancel">취소</button></span>`
      : `${a.company ? `✓ ${esc(a.company_id)}` : '<span class="fms-bad">없음</span>'} ${a.is_admin ? `<button type="button" class="secondary fms-mini fc-edit">${a.company ? "바꾸기" : "넣기"}</button>` : (a.company ? "" : "<small>— 그룹웨어 관리자가 넣습니다</small>")}`;
    // 발주처(관리주체) 계정 — 같이 내는 묶음(또는 회차)마다 한 줄, 저장하면 그 동 전부(10/25 민재형 "묶음이면 발주처 아이디는 무조건 1개"),
    // 같은 카드 다른 보고서(보고서 1·2)에 넣은 계정은 골라 쓰기(사용자 "아이디가 같을 때가 있어서 선택할 수 있게")
    const o = info.owner || {}, n = info.reports.length;
    const label = `발주처(관리주체) 계정${n > 1 ? ` <small>— 묶음 ${n}동 공통</small>` : ""}`;
    const pick = (o.choices || []).length ? `<select class="fo-pick"><option value="">같은 카드 다른 보고서 계정 쓰기…</option>${o.choices.map((c) => `<option value="${c.facility_id}">${esc(c.facility)} — ${esc(c.owner_id)}</option>`).join("")}</select>` : "";
    const owners = editing === "owner"
      ? `<div class="fms-owner"><b>${label}</b> <span class="fms-cred"><input class="fo-id" placeholder="관리주체 FMS 아이디" value="${esc(o.id || "")}" /><input class="fo-pw" type="password" placeholder="비밀번호" autocomplete="new-password" /><button type="button" class="secondary fms-mini fms-eye" aria-label="비밀번호 보기" title="비밀번호 보기">👁</button>
          <button type="button" class="fo-save">저장</button><button type="button" class="secondary fc-cancel">취소</button></span>${pick}</div>`
      : `<div class="fms-owner"><b>${label}</b> ${o.id ? `✓ ${esc(o.id)}${o.mixed ? ' <span class="fms-warn">동마다 다른 아이디가 있음 — 다시 넣으면 하나로</span>' : ""}` : '<span class="fms-warn">없음 — 승인요청까지만</span>'}
          <button type="button" class="secondary fms-mini fo-edit">${o.id ? "바꾸기" : "넣기"}</button>${pick}</div>`;
    return `<div class="fms-acc"><div><b>회사 FMS 계정</b> ${comp}</div>${owners}</div>`;
  }

  function checks() {
    const items = [...info.notes];
    const rep = info.rep || {};
    let repHtml = "";
    if (rep.differs) repHtml = `<li class="fms-warn">대표자: FMS는 <b>${esc(rep.fms)}</b>, 우리 계약은 <b>${esc(rep.ours)}</b> <button type="button" class="secondary fms-mini fms-rep">FMS 값으로 바꾸기</button></li>`;
    else if (!rep.fms) items.push("대표자: [연습]을 한 번 하면 FMS 대표자와 비교합니다");
    const pe = (info.jobs.find((j) => j.stage === "practice" && j.status === "done" && (j.result || {}).target !== "result") || {}).result || {};
    for (const d of pe.engineer_diffs || []) items.push(`기술자 ${d}`);
    if (!items.length && !repHtml) return "";
    return `<div class="fms-checks"><b>확인할 것</b><ul>${repHtml}${items.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></div>`;
  }

  function preview() {
    const p = info.payload, c = p.contract;
    const sel = (k) => ({ divide_gbn: { "01": "독자수행", "02": "공동이행", "03": "분담이행" }, bid_method: { "01": "일반경쟁", "02": "제한경쟁", "05": "지명경쟁", "03": "수의계약", "04": "기타" },
      eval_method: { "04": "기타" }, contract_method: { "01": "총액계약" }, price_method: { "01": "공사비요율방식", "02": "실비정액가산방식" }, tech_field: { 1: "교량 및 터널", 2: "건축", 3: "항만", 4: "수리시설" } }[k] || {})[c[k]] || c[k];
    const gen = [["용역명", c.project_nm], ["점검진단기간", `${c.start_ymd} ~ ${c.end_ymd}`], ["계약일", c.contract_ymd], ["관리주체", c.mng_main_nm], ["계약·설계금액(천원)", won(c.const_amt)],
      ["공동수급", `${sel("divide_gbn")} ${c.financing_ratio}%`], ["입찰방식", sel("bid_method")], ["선정방식", sel("eval_method")], ["계약방식", sel("contract_method")], ["대가산출", sel("price_method")], ["수행분야", sel("tech_field")]];
    const facs = p.facilities.map((f) => `<tr><td>${esc(f.name)}</td><td>${esc(f.fms_no)}</td><td>${esc(f.dign_label)} ${esc(f.half)}</td><td class="r">${won(f.dign_amt)}</td><td>${esc(f.overall_grade || "-")}</td></tr>`).join("");
    const engs = p.engineers.map((e) => `<tr><td>${e.rep_yn === "Y" ? "책임" : "참여"}</td><td>${esc(e.name)}</td><td>${esc(e.start)} ~ ${esc(e.end)}</td><td class="r">${e.days}</td><td>${esc(e.parti_field)}</td></tr>`).join("");
    const res = p.facilities.map((f) => `<div class="fms-res"><b>${esc(f.name)}</b> <small>안전등급 ${esc(f.overall_grade || "-")} · 중대결함 ${f.serious_defect_yn ? "있음" : "없음"} · 환기구 ${f.vent && f.vent.has ? `${esc(f.vent.has)}·${esc(f.vent.repair)}` : "현장 [공중이용] 탭에 없음(FMS 칸 그대로)"}</small>
        <div class="fms-two"><pre>${esc(f.dign_content || "(보고서를 만들면 결과표에서 채움)")}</pre><pre>${esc(f.amend_content || "-")}</pre></div></div>`).join("");
    const furl = (x, dl) => `${BASE}/api/sitok/reports/${rid}/fms/file?folder=${encodeURIComponent(x.folder)}&name=${encodeURIComponent(x.name)}${dl ? "&dl=1" : ""}`;
    const files = info.files.map((x) => `<tr><td>${esc(x.folder)}</td><td><a href="${furl(x)}" target="_blank" rel="noopener" title="눌러서 미리보기">${esc(x.name)}.pdf</a>
      <a class="fms-dl" href="${furl(x, true)}" title="내려받기">⬇</a></td><td class="r">${x.pages}</td></tr>`).join(""); // 눌러 미리보기·⬇ 내려받기(10/25 민재형)
    return `<details class="fms-prev"><summary>넣을 값 보기 — 계약·시설물·기술자·실적·e-보고서 파일</summary>
      <table class="fms-tbl"><tbody>${gen.map(([k, v]) => `<tr><th>${k}</th><td>${esc(v)}</td></tr>`).join("")}</tbody></table>
      <table class="fms-tbl"><thead><tr><th>시설물</th><th>FMS 번호</th><th>분야</th><th>금액(천원)</th><th>안전등급</th></tr></thead><tbody>${facs}</tbody></table>
      <table class="fms-tbl"><thead><tr><th>구분</th><th>기술자</th><th>참여기간</th><th>일수</th><th>직무분야(FMS 기준으로 맞춤)</th></tr></thead><tbody>${engs}</tbody></table>
      <div class="fms-sub">실적 — 주요 점검진단결과 · 주요 보수보강(안) (보고서 결과표에서 그대로)</div>${res}
      <table class="fms-tbl"><thead><tr><th>e-보고서 폴더</th><th>파일 <small>(눌러서 미리보기 · ⬇ 내려받기)</small></th><th>쪽</th></tr></thead><tbody>${files || '<tr><td colspan="3">보고서를 만들면 나눕니다</td></tr>'}</tbody></table></details>`;
  }

  // 실적 연습 결과 한 줄 — 시설물마다 채운 등급 ✓/✗, e-보고서 폴더(10/25)
  function practiceSum(j) {
    const r = j.result || {};
    if (r.target !== "result" || !r.editable) return "";
    const facs = Object.entries(r.facilities || {}).map(([n, v]) => `<span class="${v.ok ? "fms-ok" : "fms-bad"}">${v.ok ? "✓" : "✗"} ${esc(n)}${v.grade ? ` ${esc(v.grade)}등급` : ""}</span>`).join(" ");
    const eb = r.eboard || {};
    const ebTxt = !eb.found ? '<span class="fms-bad">e-보고서 용역 못 찾음</span>'
      : eb.missing && eb.missing.length ? `<span class="fms-bad">e-보고서 폴더 없음: ${eb.missing.map(esc).join(", ")}</span>`
      : `<span class="fms-ok">✓ e-보고서 폴더 ${(eb.folders || []).length}개</span>`;
    return `<div class="fms-job-sum">${facs} ${ebTxt}</div>`;
  }

  function jobs() {
    if (!info.jobs.length) return "";
    return `<div class="fms-jobs"><b>작업 기록</b>${info.jobs.map((j) => `<div class="fms-job ${j.status}">
        <div class="fms-job-h"><span class="fms-tag ${sched(j) ? "sched" : j.status}">${sched(j) ? `⏰ 예약 ${esc(j.run_at.slice(5))}` : ST[j.status] || j.status}</span> <b>${esc(j.stage_label)}</b>${j.retry ? " <small>(다시 시도)</small>" : ""} <small>${esc(j.created_at)} ${esc(j.created_by)}${j.finished_at ? ` → ${esc(j.finished_at)}` : ""}</small>
          ${j.status === "queued" ? `<button type="button" class="secondary fms-mini fms-cancel" data-j="${j.id}">${sched(j) ? "예약 취소" : "취소"}</button>` : ""}
          ${j.project_no ? `<small>FMS ${esc(j.project_no)}</small>` : ""}</div>
        ${j.message ? `<div class="fms-job-m">${esc(String(j.message).split(/\s*={3,}/)[0].split("\n")[0])}</div>` : ""}
        ${practiceSum(j)}
        ${running(j) && j.log.length ? `<div class="fms-job-log">${j.log.slice(-3).map(esc).join("<br>")}</div>` : ""}
        ${j.shots ? `<div class="fms-shots">${Array.from({ length: j.shots }, (_, k) => `<a href="${BASE}/api/sitok/fms-jobs/${j.id}/shot?n=${k + 1}" target="_blank" rel="noopener">화면 ${k + 1}</a>`).join("")}</div>` : ""}
        ${!running(j) && j.log.length ? `<details class="fms-log"><summary>기록 ${j.log.length}줄</summary><div>${j.log.map(esc).join("<br>")}</div></details>` : ""}</div>`).join("")}</div>`;
  }

  function draw() {
    const busy = info.jobs.some(running), hasNo = !!(info.state || {}).project_no;
    box.innerHTML = `${stateLine()}${accounts()}${checks()}${preview()}
      <div class="fms-acts">
        <button type="button" class="secondary fms-go" data-stage="practice"${busy ? " disabled" : ""} title="${hasNo
          ? "계약 승인 뒤 실적보고 화면에 기간·시설물 실적 값을 채워 찍고, e-보고서 창은 폴더까지만 확인 — FMS에 아무것도 저장 안 함"
          : "새 계약 일반현황만 채워 찍고, 시설물·기술자를 FMS와 대조 — FMS에 아무것도 저장 안 함"}">🔍 ${hasNo ? "실적 연습" : "연습"}(채워 보기)</button>
        <button type="button" class="fms-go" data-stage="contract"${busy ? " disabled" : ""}>📤 FMS 계약 등록</button>
        <button type="button" class="fms-go" data-stage="result"${busy || !hasNo ? " disabled" : ""} title="${hasNo ? "" : "먼저 계약 등록"}">📤 FMS 실적 보고</button>
        <button type="button" class="secondary fms-sched-btn" title="계약 등록·실적 보고를 정한 날짜·시각에 — 실적보고는 점검기간 마지막 날부터 30일 안">⏰ 예약 등록</button>
        <label class="fms-stop"><input type="checkbox" class="fms-stop-chk"${stop ? " checked" : ""} /> 승인요청 전에 멈추기 <small>(처음 몇 번 — FMS에서 확인 후 직접 승인요청)</small></label>
      </div>
      <div class="fms-sched" hidden></div>
      <div class="fms-note">FMS 회사 계정으로 로그인하면 같은 계정으로 FMS를 쓰던 사람은 로그아웃됩니다. 작업은 1~5분 걸립니다(이 화면을 닫아도 계속).</div>
      ${jobs()}<div class="mail-msg fms-msg" hidden></div>`;
    wire();
  }

  const msg = (t, tone) => { const el = box.querySelector(".fms-msg"); el.innerHTML = t; el.className = `mail-msg fms-msg ${tone || ""}`; el.hidden = !t; };

  // 예약 등록(10/25 사용자·민재형) — 계약 등록은 계약일 이후 아무 때, 실적보고는 점검기간 마지막 날부터 30일 안(과태료). 기본 = 아침 7시(같은 FMS 계정 쓰던 사람 로그아웃 — 근무 시간 밖)
  function schedForm() {
    const el = box.querySelector(".fms-sched");
    const pad = (n) => String(n).padStart(2, "0");
    const local = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T07:00`;
    const tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate() + 1);
    const dl = info.deadline;
    const resultDay = dl && new Date(`${dl.start}T00:00:00`) > tomorrow ? new Date(`${dl.start}T00:00:00`) : tomorrow;
    const hasNo = !!(info.state || {}).project_no;
    el.innerHTML = `<div class="fms-sched-h"><b>⏰ 예약 등록</b> <small>— 정한 시각에 작업 프로그램이 FMS에 올립니다(서버 PC가 켜져 있어야). 실패하면 다음 날 아침 7시에 한 번 더.</small></div>
      <div class="fms-sched-row"><select class="fs-stage"><option value="contract"${hasNo ? "" : " selected"}>계약 등록</option><option value="result"${hasNo ? " selected" : ""}>실적 보고</option></select>
        <input type="datetime-local" class="fs-at" /><button type="button" class="fs-ok">예약</button><button type="button" class="secondary fs-cancel">닫기</button></div>
      <div class="sk-help fs-hint"></div>`;
    const stageEl = el.querySelector(".fs-stage"), at = el.querySelector(".fs-at"), hint = el.querySelector(".fs-hint");
    const fill = () => {
      const r = stageEl.value === "result";
      at.value = local(r ? resultDay : tomorrow);
      at.min = r && dl ? `${dl.start}T00:00` : "";
      hint.textContent = r ? (dl ? `실적보고는 점검기간 마지막 날 ${dl.start}부터 ${dl.end}까지(30일 안 — 넘으면 과태료).${hasNo ? "" : " 계약 등록이 먼저 끝나야 합니다 — 계약 등록도 그보다 앞선 시각으로 예약하세요."}` : "")
        : "계약 등록은 계약일 이후 아무 때나 됩니다.";
    };
    stageEl.addEventListener("change", fill);
    fill();
    el.querySelector(".fs-cancel").addEventListener("click", () => { el.hidden = true; });
    el.querySelector(".fs-ok").addEventListener("click", async () => {
      const stage = stageEl.value;
      if (!at.value) { msg("날짜·시각을 고르세요.", "bad"); return; }
      const what = stage === "contract" ? "점검진단계약" : "실적보고와 e-보고서 파일";
      if (!confirm(`${at.value.replace("T", " ")}에 ${what}을(를) FMS에 실제로 저장하도록 예약합니다. ${stop ? "승인요청 전에 멈춥니다." : "승인요청하고, 관리주체 계정이 있으면 승인까지 합니다."}\n예약할까요?`)) return;
      try {
        await apiPost(`/sitok/reports/${rid}/fms`, { stage, stop_before_request: stop, run_at: at.value });
        el.hidden = true; await load(); msg(`⏰ ${at.value.replace("T", " ")}에 ${stage === "contract" ? "계약 등록" : "실적 보고"}을(를) 예약했습니다 — 아래 작업 기록에서 취소할 수 있습니다.`, "ok");
      } catch (err) { msg(esc(err.message), "bad"); }
    });
    el.hidden = false;
  }

  function wire() {
    box.querySelector(".fms-stop-chk").addEventListener("change", (e) => { stop = e.target.checked; });
    box.querySelector(".fms-sched-btn")?.addEventListener("click", () => { const el = box.querySelector(".fms-sched"); if (el.hidden) schedForm(); else el.hidden = true; });
    box.querySelectorAll(".fms-cancel").forEach((b) => b.addEventListener("click", async () => {
      if (!confirm("이 예약(대기) 작업을 취소할까요?")) return;
      try { await api(`/sitok/fms-jobs/${b.dataset.j}`, { method: "DELETE" }); await load(); msg("예약을 취소했습니다.", "ok"); } catch (err) { msg(esc(err.message), "bad"); }
    }));
    box.querySelectorAll(".fms-go").forEach((b) => b.addEventListener("click", async () => {
      const stage = b.dataset.stage;
      if (stage !== "practice") {
        const what = stage === "contract" ? "점검진단계약을 FMS에 실제로 저장" : "실적보고와 e-보고서 파일을 FMS에 실제로 저장";
        const after = stop ? "승인요청 전에 멈춥니다." : "승인요청하고, 관리주체 계정이 있으면 승인까지 합니다.";
        if (!confirm(`${what}합니다. ${after}\n계속할까요?`)) return;
      }
      try {
        await apiPost(`/sitok/reports/${rid}/fms`, { stage, stop_before_request: stop });
        await load();
        msg(stage === "practice" ? `${(info.state || {}).project_no ? "실적 연습" : "연습"}을 시작했습니다 — 1~2분 걸립니다.` : "FMS 작업을 시작했습니다 — 아래 기록에서 진행을 봅니다.", "ok");
      } catch (err) { msg(esc(err.message), "bad"); }
    }));
    const rep = box.querySelector(".fms-rep");
    if (rep) rep.addEventListener("click", async () => {
      try { const out = await apiPost(`/sitok/reports/${rid}/fms/rep`, {}); await load(); msg(`✓ 계약 대표자를 "${esc(out.rep_name)}"(FMS 기준)로 바꿨습니다 — 보고서를 다시 만들면 반영됩니다.`, "ok"); } catch (err) { msg(esc(err.message), "bad"); }
    });
    const ce = box.querySelector(".fc-edit");
    if (ce) ce.addEventListener("click", () => { editing = "company"; draw(); });
    box.querySelectorAll(".fo-edit").forEach((b) => b.addEventListener("click", () => { editing = "owner"; draw(); }));
    box.querySelectorAll(".fms-eye").forEach((b) => b.addEventListener("click", () => { // 👁 비밀번호 보기·숨기기(10/25 민재형 "점점점으로만 되어 있어 등록 시 불편")
      const inp = b.previousElementSibling;
      const show = inp.type === "password";
      inp.type = show ? "text" : "password";
      b.textContent = show ? "🙈" : "👁";
      b.title = b.ariaLabel = show ? "비밀번호 숨기기" : "비밀번호 보기";
      inp.focus();
    }));
    box.querySelector(".fo-pick")?.addEventListener("change", async (e) => { // 같은 카드 다른 보고서 계정 그대로(비밀번호는 서버 안에서만)
      if (!e.target.value) return;
      try {
        const out = await api(`/sitok/reports/${rid}/fms/owner`, { method: "PUT", body: JSON.stringify({ from_facility_id: Number(e.target.value) }) });
        editing = ""; await load(); msg(`✓ 발주처 계정 ${esc(out.owner_id)}을(를) ${out.facilities}동에 넣었습니다 — 이제 승인까지 자동입니다.`, "ok");
      } catch (err) { msg(esc(err.message), "bad"); }
    });
    box.querySelectorAll(".fc-cancel").forEach((b) => b.addEventListener("click", () => { editing = ""; draw(); }));
    const cs = box.querySelector(".fc-save");
    if (cs) cs.addEventListener("click", async () => {
      try {
        await api("/sitok/fms/account", { method: "PUT", body: JSON.stringify({ user_id: box.querySelector(".fc-id").value, password: box.querySelector(".fc-pw").value }) });
        editing = ""; await load(); msg("✓ 회사 FMS 계정을 저장했습니다(비밀번호는 암호화).", "ok");
      } catch (err) { msg(esc(err.message), "bad"); }
    });
    const os = box.querySelector(".fo-save");
    if (os) os.addEventListener("click", async () => {
      try {
        const out = await api(`/sitok/reports/${rid}/fms/owner`, { method: "PUT", body: JSON.stringify({ user_id: box.querySelector(".fo-id").value, password: box.querySelector(".fo-pw").value }) });
        editing = ""; await load(); msg(out.owner_id ? `✓ 발주처 FMS 계정을 저장했습니다(비밀번호는 암호화${out.facilities > 1 ? ` — ${out.facilities}동 공통` : ""}) — 이제 승인까지 자동입니다.` : "발주처 계정을 지웠습니다.", "ok");
      } catch (err) { msg(esc(err.message), "bad"); }
    });
  }

  load();
})();
