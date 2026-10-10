// 시특법 AI 초안 창(2026-10-11 6단계) — 회차 카드 [🤖 AI 초안]. AI가 쓴 결과표·1.3 외관조사 서술·종합결론·안전등급 추천을 점검자가 고쳐 저장.
// 저장한 값(final)이 [보고서 만들기] 때 들어감. 서버 server/api/routers/sitok_reports.py(/ai/draft·/ai), AI server/sitok/ai_draft.py.

const SITOK_AI_SECTIONS = [["crack", "1) 콘크리트 구조체 균열"], ["leak", "2) 누수 및 백화"], ["spall", "3) 박리·박락·철근노출·부식"], ["steel", "4) 강재구조"],
  ["nonstruct", "5) 비구조체"], ["public", "6) 공중이 이용하는 부위·부대시설"], ["other", "7) 기타시설"]];
const SITOK_GRADES = { A: "A 우수", B: "B 양호", C: "C 보통", D: "D 미흡", E: "E 불량" };
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

  async function makeDraft() {
    busy = true;
    box.innerHTML = `${head}<div class="mail-wait">현장 조사 결함으로 초안을 쓰는 중…(30~90초)</div>`;
    try {
      const ai = await apiPost(`/sitok/reports/${reportId}/ai/draft`);
      busy = false;
      draw(ai);
    } catch (e) {
      busy = false;
      box.innerHTML = `${head}<div class="mail-msg bad">${esc(e.message)}</div><div class="mail-foot"><button type="button" class="mail-cancel">닫기</button></div>`;
      box.querySelector(".mail-cancel").addEventListener("click", close);
    }
  }

  function draw(ai) {
    const f = ai.final || {};
    const d = ai.draft || {};
    if (!ai.final) {
      box.innerHTML = `${head}<p class="ai-intro">아직 초안이 없습니다. 현장 조사 결함(개수·크기·진행/신규/보수)과 지난 회차 문장(말투 참고)으로 결과표·외관조사 서술·종합결론·안전등급 추천을 씁니다.</p>
        <div class="mail-foot"><button type="button" class="mail-cancel">닫기</button><button type="button" class="mail-primary ai-make">AI 초안 만들기</button></div>`;
      box.querySelector(".mail-cancel").addEventListener("click", close);
      box.querySelector(".ai-make").addEventListener("click", makeDraft);
      return;
    }
    const lines = (a) => esc((a || []).join("\n"));
    const st = d.stats || {};
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
          : `<label>안전등급 <span class="sk-help">AI 추천 ${esc(SITOK_GRADES[d.grade] || "-")} — ${esc(d.grade_reason || "")}</span>
          <select data-k="grade"><option value="">바꾸지 않음(지난 보고서 그대로)</option>${Object.entries(SITOK_GRADES).map(([k, v]) => `<option value="${k}"${f.grade === k ? " selected" : ""}>${v}</option>`).join("")}</select></label>`}
        <h4>1.3 외관조사 실시결과(항목별 서술 — 결과의 분석 표에도 같은 글)</h4>
        ${SITOK_AI_SECTIONS.map(([k, label]) => `<label>${label} <span class="sk-help">결함 ${st[k]?.count ?? 0}건${st[k]?.grew ? ` · 진행 ${st[k].grew}` : ""}${st[k]?.new ? ` · 신규 ${st[k].new}` : ""}${st[k]?.repaired ? ` · 보수 ${st[k].repaired}` : ""}</span>
          <textarea data-k="sections.${k}" rows="3">${esc((f.sections || {})[k])}</textarea></label>`).join("")}
        ${(f.items || []).length ? `<h4>안전등급 평가(3종, 18항목)</h4>
          <div class="ai-items">${f.items.map((it, i) => `<div class="ai-item" data-i="${i}"><span class="ai-no">${it.no}</span>
            <span class="ai-name"><small>${esc(it.group)}</small>${esc(it.name)}</span>
            <select class="ai-rating">${SITOK_RATINGS.map(([n]) => `<option${it.rating === n ? " selected" : ""}>${n}</option>`).join("")}</select>
            <select class="ai-repair"><option${it.repair === "×" ? " selected" : ""}>×</option><option${it.repair === "○" ? " selected" : ""}>○</option></select>
            <input class="ai-op" value="${esc(it.opinion)}" placeholder="점검자 의견" /></div>`).join("")}</div>
          <label>안전등급 평가 종합의견<textarea data-k="eval_opinion" rows="2">${esc(f.eval_opinion)}</textarea></label>` : ""}
        <h4>종합결론</h4>
        <label>종합결론 글머리 <span class="sk-help">한 줄에 하나</span><textarea data-k="conclusion" data-lines rows="7">${lines(f.conclusion)}</textarea></label>
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
    calc();
    box.querySelector(".mail-cancel").addEventListener("click", close);
    box.querySelector(".ai-redo").addEventListener("click", () => { if (confirm("AI가 처음부터 다시 씁니다. 고친 글은 사라집니다. 할까요?")) makeDraft(); });
    box.querySelector(".ai-save").addEventListener("click", async () => {
      const body = { sections: {} };
      box.querySelectorAll("[data-k]").forEach((el) => {
        const k = el.dataset.k;
        const v = el.hasAttribute("data-lines") ? el.value.split("\n").map((x) => x.trim()).filter(Boolean) : el.value.trim();
        if (k.startsWith("sections.")) body.sections[k.slice(9)] = v; else body[k] = v;
      });
      if (items.length) { calc(); body.items = items; }
      const msg = box.querySelector(".mail-msg");
      try {
        await api(`/sitok/reports/${reportId}/ai`, { method: "PUT", body: JSON.stringify(body) });
        msg.hidden = false; msg.className = "mail-msg ok"; msg.textContent = "저장했습니다 — [보고서 만들기]를 누르면 들어갑니다.";
        if (onSaved) onSaved();
      } catch (e) { msg.hidden = false; msg.className = "mail-msg bad"; msg.textContent = e.message; }
    });
  }

  try { draw(await api(`/sitok/reports/${reportId}/ai`)); } catch (e) { box.innerHTML = `${head}<div class="mail-msg bad">${esc(e.message)}</div>`; }
}
