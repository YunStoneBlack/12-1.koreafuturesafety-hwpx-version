// 시특법 AI 초안 창(2026-10-11 6단계) — 회차 카드 [🤖 AI 초안]. AI가 쓴 결과표·1.3 외관조사 서술·종합결론·안전등급 추천을 점검자가 고쳐 저장.
// 저장한 값(final)이 [보고서 만들기] 때 들어감. 서버 server/api/routers/sitok_reports.py(/ai/draft·/ai), AI server/sitok/ai_draft.py.

const SITOK_AI_SECTIONS = [["crack", "1) 콘크리트 구조체 균열"], ["leak", "2) 누수 및 백화"], ["spall", "3) 박리·박락·철근노출·부식"], ["steel", "4) 강재구조"],
  ["nonstruct", "5) 비구조체"], ["public", "6) 공중이 이용하는 부위·부대시설"], ["other", "7) 기타시설"]];
const SITOK_GRADES = { A: "A 우수", B: "B 양호", C: "C 보통", D: "D 미흡", E: "E 불량" };
const SITOK_GRADES2 = { B: "양호", C: "보통", D: "미흡", E: "불량" }; // 2종 — A~E·우수와 별개(형 10/16), 속은 B~E
// 3종 안전등급 평가(18항목) — 점수·등급 계산은 서버 report_build.eval_score와 같은 식(화면에서 바로 보여 주려고 여기도)
const SITOK_RATINGS = [["우수", 10], ["양호", 8], ["보통", 5], ["미흡", 2], ["불량", 0], ["해당없음", null]];
function sitokEvalScore(items) {
  const pts = Object.fromEntries(SITOK_RATINGS);
  const g = {};
  for (const it of items) {
    const p = pts[it.rating];
    if (p == null || !it.group) continue;
    (g[it.group] ||= [0, 0]);
    g[it.group][0] += p;
    g[it.group][1] += 1;
  }
  const W = { 주요: 60, 일반: 20, 부대: 20 };
  let ws = 0, sum = 0;
  const rows = {};
  for (const [k, [a, b]] of Object.entries(g)) { if (!b) continue; rows[k] = [a, b, Math.round((a / b) * 100) / 100]; ws += W[k]; sum += W[k] * rows[k][2]; }
  const total = ws ? Math.round((sum / ws) * 100) / 100 : 0;
  const grade = !ws ? "" : total >= 9 ? "A" : total >= 7 ? "B" : total >= 5 ? "C" : total >= 3 ? "D" : "E";
  return { rows, total, grade };
}

async function openSitokAi(reportId, title, onSaved) {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const overlay = document.createElement("div");
  overlay.className = "mail-overlay";
  overlay.innerHTML = '<div class="mail-box ai-box" role="dialog" aria-modal="true"><div class="mail-wait">불러오는 중…</div></div>';
  document.body.appendChild(overlay);
  const box = overlay.querySelector(".mail-box");
  let busy = false;
  const close = () => { if (!busy) overlay.remove(); };
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  const head = `<div class="mail-head"><b>🤖 AI 초안</b><span class="mail-sub">${esc(title)} — AI가 쓴 글을 고쳐 저장하면 보고서를 만들 때 들어갑니다</span></div>`;

  const fail = (m) => {
    busy = false;
    box.innerHTML = `${head}<div class="mail-msg bad">${esc(m)}</div><div class="mail-foot"><button type="button" class="mail-cancel">닫기</button></div>`;
    box.querySelector(".mail-cancel").addEventListener("click", close);
  };

  // AI 초안은 서버가 뒤에서 씀(10/21 — 3종은 3분 넘게 걸려 그룹웨어가 504로 끊었음) — 4초마다 상태를 묻고 끝나면 저장된 초안을 그림.
  // 창을 닫아도 뒤에서 계속 쓰고, 다시 열면 이어서 기다림.
  async function waitJob(text) {
    busy = false; // 닫기 허용
    const t0 = Date.now();
    box.innerHTML = `${head}<div class="mail-wait"><span class="ai-wait-t">${esc(text)}</span><br><small>보통 1~5분 — 창을 닫아도 뒤에서 계속 쓰고, 다시 열면 이어서 봅니다</small></div>
      <div class="mail-foot"><button type="button" class="mail-cancel">닫기</button></div>`;
    box.querySelector(".mail-cancel").addEventListener("click", close);
    for (;;) {
      await new Promise((res) => setTimeout(res, 4000));
      if (!document.body.contains(overlay)) return;
      let st;
      try { st = await api(`/sitok/reports/${reportId}/ai/draft/state`); } catch (e) { st = { state: e.status === 404 ? "idle" : "running" }; } // 잠깐 끊김(서버 재시작 등)은 계속 기다림
      const el = box.querySelector(".ai-wait-t");
      if (st.state === "running") { if (el) el.textContent = `${text} — ${Math.round((Date.now() - t0) / 1000)}초`; continue; }
      if (st.state === "failed") { fail(st.msg || "AI 초안을 만들지 못했습니다."); return; }
      try { draw(await api(`/sitok/reports/${reportId}/ai`)); } catch (e) { fail(e.message); }
      return;
    }
  }

  async function makeDraft(body) {
    body = body && body.grade ? { grade: body.grade } : {}; // [AI 초안 만들기] 단추는 클릭 이벤트를 넘김
    busy = true;
    box.innerHTML = `${head}<div class="mail-wait">AI에게 보내는 중…</div>`;
    try {
      const res = await apiPost(`/sitok/reports/${reportId}/ai/draft`, body);
      await waitJob(((res && res.job) || {}).msg || (body.grade ? "AI가 요청한 등급에 맞게 다시 쓰는 중" : "AI가 초안을 쓰는 중"));
    } catch (e) { fail(e.message); }
  }

  // 정밀안전점검(10/13 ⑤-2) — 항목 22개: 기본 글이 먼저, [AI로 다시 쓰기]로 결함·시험·상태평가 값을 보고 다시 씀, 고쳐 저장하면 본문에 들어감
  // AI 글 칸(textarea)마다 "덧붙일 내용 + 🤖 반영해 다시 쓰기"(10/28 사용자 — 내진에서 시특법까지, app.js aiRewrite) — 받은 글은 칸에 들어가고 [저장]으로 저장
  function attachRewrite() {
    if (typeof aiRewrite !== "function") return;
    box.querySelectorAll(".ai-form textarea, textarea.ai-sum").forEach((t) => {
      const lab = t.closest("label");
      const name = (lab && (lab.querySelector("b")?.textContent || lab.childNodes[0]?.textContent) || t.placeholder || t.dataset.k || "글").trim();
      aiRewrite(t, `/sitok/reports/${reportId}/ai/rewrite`, name);
    });
  }
  function drawPrecision(ai) {
    box.innerHTML = `${head}
      <div class="ai-meta">${ai.made_at ? `AI 초안 ${esc(ai.made_at)}` : "아직 AI가 쓰지 않음 — 결함·시험·상태평가 값으로 만든 기본 글입니다"}${ai.edited_at ? ` · ${esc(ai.edited_by)} 고침 ${esc(ai.edited_at)}` : ""}</div>
      <div class="ai-form ai-pre">
        ${ai.items.map((it) => `<label><b>${esc(it.label)}</b> <span class="sk-help">${esc(it.where)}</span>
          ${it.key === "diag" ? `<select data-k="${it.key}"><option${it.text === "불필요" ? " selected" : ""}>불필요</option><option${it.text === "필요" ? " selected" : ""}>필요</option></select>`
            : `<textarea data-k="${it.key}" rows="${it.text.length > 160 ? 4 : 2}">${esc(it.text)}</textarea>`}
          <span class="ai-pre-acts"><button type="button" class="link-btn ai-reset" data-k="${it.key}" title="기본 글로">기본 글</button>${it.ai ? `<button type="button" class="link-btn ai-useai" data-k="${it.key}" title="AI가 쓴 글로">AI 글</button>` : ""}</span></label>`).join("")}
      </div>
      <div class="mail-msg" hidden></div>
      <div class="mail-foot"><button type="button" class="secondary ai-redo">🤖 AI로 다시 쓰기</button><button type="button" class="mail-cancel">닫기</button>
        <button type="button" class="mail-primary ai-save">저장</button></div>`;
    attachRewrite(); // 글 칸마다 덧붙일 내용 + 🤖 반영해 다시 쓰기(10/28)
    const byKey = Object.fromEntries(ai.items.map((it) => [it.key, it]));
    box.querySelectorAll(".ai-reset").forEach((b) => b.addEventListener("click", () => { box.querySelector(`[data-k="${b.dataset.k}"]`).value = byKey[b.dataset.k].default; }));
    box.querySelectorAll(".ai-useai").forEach((b) => b.addEventListener("click", () => { box.querySelector(`[data-k="${b.dataset.k}"]`).value = byKey[b.dataset.k].ai; }));
    box.querySelector(".mail-cancel").addEventListener("click", close);
    box.querySelector(".ai-redo").addEventListener("click", async () => {
      if (!confirm("결함현황표·재료시험·상태평가 값을 AI에게 보내 22항목을 다시 씁니다(1~5분). 고친 글은 AI 글로 바뀝니다. 할까요?")) return;
      busy = true;
      box.innerHTML = `${head}<div class="mail-wait">AI에게 보내는 중…</div>`;
      try { await apiPost(`/sitok/reports/${reportId}/ai/draft`); await waitJob("AI가 정밀안전점검 문장을 쓰는 중"); } catch (e) { fail(e.message); }
    });
    const savePre = async () => { // [저장]·[✓ 작성 완료](먼저 저장) — 성공하면 true
      const precision = {};
      box.querySelectorAll("[data-k]").forEach((el) => { precision[el.dataset.k] = el.value.trim(); });
      const msg = box.querySelector(".mail-msg");
      try {
        await api(`/sitok/reports/${reportId}/ai`, { method: "PUT", body: JSON.stringify({ precision }) });
        msg.hidden = false; msg.className = "mail-msg ok"; msg.textContent = "저장했습니다 — [본문 보고서 만들기]를 누르면 들어갑니다.";
        if (onSaved) onSaved();
        return true;
      } catch (e) { msg.hidden = false; msg.className = "mail-msg bad"; msg.textContent = e.message; return false; }
    };
    box.querySelector(".ai-save").addEventListener("click", savePre);
    sitokStepFoot(box, reportId, "ai", savePre, onSaved); // [✓ 작성 완료](10/18 민재형)
  }

  function draw(ai) {
    if (ai && ai.precision) return drawPrecision(ai);
    const f = ai.final || {};
    const d = ai.draft || {};
    if (!ai.final) {
      box.innerHTML = `${head}<p class="ai-intro">아직 초안이 없습니다. 현장 조사 결함(개수·크기·진행/신규/보수)과 지난 회차 문장(말투 참고)으로 결과표·외관조사 서술·종합결론·안전등급 추천을 씁니다.</p>
        <div class="mail-foot"><button type="button" class="mail-cancel">닫기</button><button type="button" class="mail-primary ai-make">AI 초안 만들기</button></div>`;
      box.querySelector(".mail-cancel").addEventListener("click", close);
      box.querySelector(".ai-make").addEventListener("click", makeDraft);
      box.insertAdjacentHTML("beforeend", '<div class="mail-msg" hidden></div>');
      sitokStepFoot(box, reportId, "ai", null, onSaved); // 초안 없이도 완료는 됨(미기재로 알려 줌)
      return;
    }
    const lines = (a) => esc((a || []).join("\n"));
    const prevNote = (fin) => { // 전회 칸 출처(10/21 형): 전회차 회차 > 전회차 보고서 PDF > 없음(첫 회차)
      const s = fin.summary_prev_src, lb = fin.summary_prev_label ? `(${fin.summary_prev_label})` : "";
      return s === "round" ? `전회 칸은 전회차 회차${lb}에서 가져옴` : s === "pdf" ? `전회 칸은 전회차 보고서 PDF${lb}에서 읽음`
        : s === "none" ? '전회차 없음(첫 회차) — 전회 칸을 비워 두면 표에 "전회차 없음", 직접 써도 됨' : "전회 칸은 전회차 자료가 있으면 자동";
    };
    const two = !String(ai.template || "3종").startsWith("3종"); // 2종 = 양호·보통·미흡·불량
    const GR = two ? SITOK_GRADES2 : SITOK_GRADES;
    const curGrade = two && f.grade === "A" ? "B" : f.grade;
    const sum = ai.summary || {};
    const priceNames = new Set((ai.prices || []).map((p) => p.replace(/\s/g, "")));
    const known = (m) => priceNames.has(String(m || "").replace(/\s/g, ""));
    const st = d.stats || {};
    const SECS = ai.sections_list || SITOK_AI_SECTIONS; // 옹벽은 서버가 준 1.4 절 목록(10/20)
    const wall = !!ai.wall;
    const con = wall && f.conclusion && !Array.isArray(f.conclusion) ? f.conclusion : null;
    box.innerHTML = `${head}
      <div class="ai-meta">초안 ${esc(d.made_at || "")}${f.edited_at ? ` · ${esc(f.edited_by)} 고침 ${esc(f.edited_at)}` : ""}</div>
      <div class="ai-form">
        <h4>결과표</h4>
        <label>중대결함<textarea data-k="critical" rows="2">${esc(f.critical)}</textarea></label>
        <label>공중이 이용하는 부위<textarea data-k="public" rows="2">${esc(f.public)}</textarea></label>
        <label>점검 주요결과 <span class="sk-help">한 줄에 글머리 하나</span><textarea data-k="findings" data-lines rows="7">${lines(f.findings)}</textarea></label>
        <label>주요 보수·보강 <span class="sk-help">한 줄에 하나</span><textarea data-k="repairs" data-lines rows="4">${lines(f.repairs)}</textarea></label>
        <label>차기 정기점검 시 중점 점검부위<input data-k="next_focus" value="${esc(f.next_focus)}" /></label>
        ${(f.items || []).length ? `<div class="ai-grade3">안전등급 <b class="ai-calc"></b> <span class="sk-help">3종 — 아래 18항목 평가로 자동 계산(평가를 바꾸면 바로 바뀜)</span></div>`
          : `<label>${two ? "점검결과 등급 <small>(2종 — 양호·보통·미흡·불량)</small>" : "안전등급"} <span class="sk-help">AI 추천 ${esc(GR[two && d.grade === "A" ? "B" : d.grade] || "-")} — ${esc(d.grade_reason || "")}</span>
          <select data-k="grade"><option value="">바꾸지 않음(지난 보고서 그대로)</option>${Object.entries(GR).map(([k, v]) => `<option value="${k}"${curGrade === k ? " selected" : ""}>${v}</option>`).join("")}</select></label>`}
        <div class="ai-regrade"><span class="sk-help">등급이 맞지 않다고 보면 — AI가 그 등급에 맞게 등급 근거·결과표·종합결론${(f.items || []).length ? "·18항목 평가" : ""}를 다시 씁니다</span>
          <button type="button" class="secondary btn-sm ai-regrade-btn" data-g="up">▲ 한 단계 올려 다시 쓰기</button>
          <button type="button" class="secondary btn-sm ai-regrade-btn" data-g="down">▼ 한 단계 내려 다시 쓰기</button>
          ${d.requested_grade ? `<span class="sk-help">요청 ${esc(GR[d.requested_grade] || d.requested_grade)} → 나온 등급 ${esc(GR[curGrade] || curGrade || "-")}</span>` : ""}</div>
        <h4>${wall ? "1.4 현장조사 결과(절마다 서술)" : "1.3 외관조사 실시결과(항목별 서술 — 결과의 분석 표에도 같은 글)"}</h4>
        ${SECS.map(([k, label]) => `<label>${label} ${wall ? "" : `<span class="sk-help">결함 ${st[k]?.count ?? 0}건${st[k]?.grew ? ` · 진행 ${st[k].grew}` : ""}${st[k]?.new ? ` · 신규 ${st[k].new}` : ""}${st[k]?.repaired ? ` · 보수 ${st[k].repaired}` : ""}</span>`}
          <textarea data-k="sections.${k}" rows="3">${esc((f.sections || {})[k])}</textarea></label>`).join("")}
        ${wall ? `<h4>1.4.5 정기점검 실시결과 요약표 <span class="sk-help">부위마다 전회·금회·조치(줄마다 ⦁) — ${esc(prevNote(f))}</span></h4>
          <div class="ai-wsum">${(f.summary_rows || []).map((row, i) => `<div class="ai-wsum-row"><b>${esc(row.name)}</b>
            <textarea data-k="summary_rows.${i}.prev" rows="2" placeholder="전회 결과">${esc(row.prev)}</textarea>
            <textarea data-k="summary_rows.${i}.now" rows="2" placeholder="금회 결과">${esc(row.now)}</textarea>
            <textarea data-k="summary_rows.${i}.action" rows="2" placeholder="조치필요사항">${esc(row.action)}</textarea></div>`).join("")}</div>
          <label>요약표 종합의견<textarea data-k="summary_opinion" rows="2">${esc(f.summary_opinion)}</textarea></label>
          <h4>1.5 유지관리방안 <span class="sk-help">결함·상태양호 사진으로 AI가 씀 — 한 줄에 글머리 하나</span></h4>
          <label>중점 유지관리방안<textarea data-k="maint_plan" data-lines rows="6">${lines(f.maint_plan)}</textarea></label>` : ""}
        ${(f.parts || []).length ? `<h4>공중이용·기타시설 사진 판단 <span class="sk-help">현장 화면 탭 사진을 AI가 조사항목·상태평가기준(a~e)으로 본 것 — 위 6)·7) 글과 결과표 칸이 이걸로 쓰였음(글은 위에서 고치세요)</span></h4>
          <div class="ai-fac">${f.parts.map((it, i) => `<div class="ai-fac-row ai-part" data-i="${i}"><span class="ai-name"><small>${it.group === "public" ? "공중이용" : "기타시설"}</small>${esc(it.name)}</span>
            <select class="ai-pgrade">${["", "a", "b", "c", "d", "e", "해당없음"].map((g) => `<option value="${g}"${it.grade === g ? " selected" : ""}>${g || "-"}</option>`).join("")}</select>
            <input class="ai-pnote" value="${esc(it.note)}" placeholder="상태 한 줄" /></div>`).join("")}</div>` : ""}
        ${(f.items || []).length ? `<h4>안전등급 평가(3종, 18항목)</h4>
          <div class="ai-items">${f.items.map((it, i) => `<div class="ai-item" data-i="${i}"><span class="ai-no">${it.no}</span>
            <span class="ai-name"><small>${esc(it.group)}</small>${esc(it.name)}${it.basis ? `<em class="ai-basis">근거: ${esc(it.basis)}</em>` : ""}</span>
            <select class="ai-rating">${SITOK_RATINGS.map(([n]) => `<option${it.rating === n ? " selected" : ""}>${n}</option>`).join("")}</select>
            <select class="ai-repair"><option${it.repair === "×" ? " selected" : ""}>×</option><option${it.repair === "○" ? " selected" : ""}>○</option></select>
            <input class="ai-op" value="${esc(it.opinion)}" placeholder="점검자 의견" /></div>`).join("")}</div>
          <label>안전등급 평가 종합의견<textarea data-k="eval_opinion" rows="2">${esc(f.eval_opinion)}</textarea></label>` : ""}
        ${(f.facility || []).length ? `<h4>1.4 기타 부대시설 상태조사 결과표</h4>
          <div class="ai-fac">${f.facility.map((it, i) => `<div class="ai-fac-row${it.has ? " has" : ""}" data-i="${i}"><span class="ai-no">${it.no}</span>
            <span class="ai-name">${esc(it.name)}</span>
            <select class="ai-has"><option value="0"${it.has ? "" : " selected"}>없다</option><option value="1"${it.has ? " selected" : ""}>있다</option></select>
            <input class="ai-state" value="${esc(it.state)}" placeholder="상태(유형·크기·추정원인)" /><input class="ai-where" value="${esc(it.where)}" placeholder="위치·사진" /></div>`).join("")}</div>` : ""}
        ${ai.template === "3종학교" ? `<h4>1.7 외부 치장벽돌 안전점검 <span class="sk-help">${f.brick_src === "defects" ? "현장조사 치장벽돌 결함으로 AI가 씀"
            : f.brick_src === "photos" ? "치장벽돌 결함이 없어 상태양호 탭 [외부 치장벽돌] 사진으로 AI가 씀"
            : "치장벽돌 결함·상태양호 사진이 없어 비었음 — 상태양호 탭 [외부 치장벽돌]에 찍고 초안을 다시 만들거나 직접 쓰세요(비우면 보고서 칸 \"-\")"}</span></h4>
          <label>특이사항<textarea data-k="brick" rows="3">${esc(f.brick)}</textarea></label><input type="hidden" data-k="brick_src" value="${esc(f.brick_src || "")}" />` : ""}
        ${(f.methods || []).length ? `<h4>보수공법 <span class="sk-help">9쪽 조치 필요사항·보수 우선순위·개략공사비에 같이 들어감 — 단가표 공법이면 단가로 계산, 아니면 1식 금액</span></h4>
          <div class="ai-met">${f.methods.map((m, i) => `<div class="ai-met-row${known(m.method) ? " known" : ""}" data-i="${i}"><span class="ai-name"><small>${esc(m.part)}</small>${esc(m.member)} ${esc(m.dtype)}${m.wide ? " (0.3mm 이상)" : ""}
              <em>${m.count}개소 · ${m.qty}${esc(m.unit)}</em></span>
            <input class="ai-method" list="ai-prices" value="${esc(m.method)}" /><input class="ai-lump" inputmode="numeric" value="${m.lump ? Number(m.lump).toLocaleString() : ""}" placeholder="1식 금액(단가표에 없을 때)" /></div>`).join("")}</div>
          <datalist id="ai-prices">${(ai.prices || []).map((p) => `<option value="${esc(p)}">`).join("")}</datalist>` : ""}
        <h4>종합결론</h4>
        ${con ? `<label>외관조사결과 <span class="sk-help">한 줄에 하나</span><textarea data-k="conclusion.survey" data-lines rows="3">${lines(con.survey)}</textarea></label>
          <label>보수필요사항 <span class="sk-help">한 줄에 하나</span><textarea data-k="conclusion.repair" data-lines rows="3">${lines(con.repair)}</textarea></label>
          <label>긴급점검 및 정밀안전진단 필요여부<input data-k="conclusion.urgent" value="${esc(con.urgent)}" /></label>`
          : `<label>종합결론 글머리 <span class="sk-help">한 줄에 하나</span><textarea data-k="conclusion" data-lines rows="7">${lines(f.conclusion)}</textarea></label>`}
        <h4>요약문 결언 <span class="sk-help">보고서 앞 요약문 3.6 — ${ai.book > 1 ? `묶음 동 ${ai.book}개` : "이 시설물"}의 종합결론을 묶어 AI가 씀(동마다 AI 초안이 다 있으면 자동), 비우면 기본 문장</span></h4>
        <label>결언 본문 <span class="sk-help">한 줄에 문단 하나</span><textarea class="ai-sum" rows="6">${lines(sum.conclusion)}</textarea></label>
        <div class="ai-sum-acts"><button type="button" class="secondary btn-sm ai-sum-redo">🤖 요약문 결언 AI로 쓰기</button>
          <span class="sk-help ai-sum-msg">${sum.made_at ? `AI ${esc(sum.made_at)}${sum.edited_at ? ` · ${esc(sum.edited_by || "")} 고침 ${esc(sum.edited_at)}` : ""}` : "아직 없음"}</span></div>
      </div>
      <div class="mail-msg" hidden></div>
      <div class="mail-foot"><button type="button" class="secondary ai-redo">AI로 다시 쓰기</button><button type="button" class="mail-cancel">닫기</button>
        <button type="button" class="mail-primary ai-save">저장</button></div>`;
    const items = (f.items || []).map((x) => ({ ...x }));
    const calc = () => {
      const el = box.querySelector(".ai-calc");
      if (!el) return;
      box.querySelectorAll(".ai-item").forEach((row) => {
        const it = items[Number(row.dataset.i)];
        it.rating = row.querySelector(".ai-rating").value;
        it.repair = row.querySelector(".ai-repair").value;
        it.opinion = row.querySelector(".ai-op").value.trim();
      });
      const r = sitokEvalScore(items);
      el.textContent = r.grade ? `${SITOK_GRADES[r.grade]} (${r.total}점 — ${Object.entries(r.rows).map(([k, v]) => `${k} ${v[0]}/${v[1]}=${v[2]}`).join(", ")})` : "-";
    };
    box.querySelectorAll(".ai-item select, .ai-item input").forEach((el) => el.addEventListener("change", calc));
    box.querySelectorAll(".ai-method").forEach((el) => el.addEventListener("input", () => el.closest(".ai-met-row").classList.toggle("known", known(el.value))));
    box.querySelectorAll(".ai-has").forEach((el) => el.addEventListener("change", () => el.closest(".ai-fac-row").classList.toggle("has", el.value === "1")));
    calc();
    box.querySelector(".mail-cancel").addEventListener("click", close);
    box.querySelector(".ai-redo").addEventListener("click", () => { if (confirm("AI가 처음부터 다시 씁니다. 고친 글은 사라집니다. 할까요?")) makeDraft(); });
    box.querySelectorAll(".ai-regrade-btn").forEach((b) => b.addEventListener("click", () => { // 등급 재산정 요청(10/19 형 "한 단계 상향·하향 요청")
      const up = b.dataset.g === "up";
      if (!confirm(`등급을 한 단계 ${up ? "올려(좋게)" : "내려(낮게)"} AI가 등급 근거·결과표·종합결론${(f.items || []).length ? "·18항목 평가" : ""}를 다시 씁니다(1~5분). 고친 글은 사라집니다. 할까요?`)) return;
      makeDraft({ grade: up ? "up" : "down" });
    }));
    attachRewrite(); // 글 칸마다 덧붙일 내용 + 🤖 반영해 다시 쓰기(10/28)
    box.querySelector(".ai-sum-redo").addEventListener("click", async (e) => { // 요약문 결언 — 동마다 확정 AI 초안 결론을 묶어(10/16)
      const btn = e.currentTarget, m = box.querySelector(".ai-sum-msg");
      btn.disabled = true;
      m.textContent = "AI가 결언을 쓰는 중…(10~30초)";
      try {
        const next = await apiPost(`/sitok/reports/${reportId}/ai/summary`);
        box.querySelector(".ai-sum").value = ((next.summary || {}).conclusion || []).join("\n");
        m.textContent = `AI ${(next.summary || {}).made_at || ""}`;
      } catch (err) { m.textContent = err.message; } finally { btn.disabled = false; }
    });
    const save = async () => { // [저장]·[✓ 작성 완료](먼저 저장) — 성공하면 true
      const body = { sections: {} };
      if (wall) {
        body.summary_rows = (f.summary_rows || []).map((row) => ({ ...row }));
        ["summary_prev_src", "summary_prev_label", "summary_prev_grade"].forEach((k) => { body[k] = f[k] || ""; }); // 전회 칸 출처(10/21)
      }
      const put = (obj, path, v) => { // "summary_rows.0.prev"처럼 점으로 깊이 들어가 넣음(옹벽, 10/20)
        const keys = path.split(".");
        let cur = obj;
        keys.slice(0, -1).forEach((key, i) => {
          const next = keys[i + 1];
          if (cur[key] == null || typeof cur[key] !== "object") cur[key] = /^\d+$/.test(next) ? [] : {};
          cur = cur[key];
        });
        cur[keys[keys.length - 1]] = v;
      };
      box.querySelectorAll("[data-k]").forEach((el) => {
        const k = el.dataset.k;
        const v = el.hasAttribute("data-lines") ? el.value.split("\n").map((x) => x.trim()).filter(Boolean) : el.value.trim();
        put(body, k, v);
      });
      if (items.length) { calc(); body.items = items; }
      if ((f.methods || []).length) {
        body.methods = [...box.querySelectorAll(".ai-met-row")].map((row) => ({ ...f.methods[Number(row.dataset.i)], method: row.querySelector(".ai-method").value.trim(),
          lump: Number(row.querySelector(".ai-lump").value.replace(/[^0-9]/g, "")) || null }));
      }
      if ((f.parts || []).length) {
        body.parts = [...box.querySelectorAll(".ai-part")].map((row) => ({ ...f.parts[Number(row.dataset.i)], grade: row.querySelector(".ai-pgrade").value,
          note: row.querySelector(".ai-pnote").value.trim() }));
      }
      if ((f.facility || []).length) {
        // 공중이용·기타시설 사진 판단 줄(.ai-part)도 같은 모양 — 빼야 함(10/20 의정부 [✓ 작성 완료] 오류)
        body.facility = [...box.querySelectorAll(".ai-fac-row:not(.ai-part)")].map((row) => ({ ...f.facility[Number(row.dataset.i)], has: row.querySelector(".ai-has").value === "1",
          state: row.querySelector(".ai-state").value.trim(), where: row.querySelector(".ai-where").value.trim() }));
      }
      const msg = box.querySelector(".mail-msg");
      try {
        await api(`/sitok/reports/${reportId}/ai`, { method: "PUT", body: JSON.stringify(body) });
        const conc = box.querySelector(".ai-sum").value.split("\n").map((x) => x.trim()).filter(Boolean);
        if (conc.join("\n") !== (sum.conclusion || []).join("\n")) await api(`/sitok/reports/${reportId}/ai/summary`, { method: "PUT", body: JSON.stringify({ conclusion: conc }) });
        msg.hidden = false; msg.className = "mail-msg ok"; msg.textContent = "저장했습니다 — [보고서 만들기]를 누르면 들어갑니다.";
        if (onSaved) onSaved();
        return true;
      } catch (e) { msg.hidden = false; msg.className = "mail-msg bad"; msg.textContent = e.message; return false; }
    };
    box.querySelector(".ai-save").addEventListener("click", save);
    sitokStepFoot(box, reportId, "ai", save, onSaved); // [✓ 작성 완료](10/18 민재형)
  }

  try {
    const st = await api(`/sitok/reports/${reportId}/ai/draft/state`).catch(() => ({}));
    if (st.state === "running") await waitJob(st.msg || "AI가 초안을 쓰는 중"); // 열 때 이미 쓰는 중이면 이어서 기다림
    else draw(await api(`/sitok/reports/${reportId}/ai`));
  } catch (e) { box.innerHTML = `${head}<div class="mail-msg bad">${esc(e.message)}</div>`; }
}
