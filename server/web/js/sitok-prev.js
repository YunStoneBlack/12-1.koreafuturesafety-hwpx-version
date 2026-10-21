// 시특법 전회차 보고서 PDF 칸(2026-10-18 민재형) — 시설물 현황 창·면담·변경사항 조사 창의 같은 칸(동 회차마다 하나).
// 회차 화면 [지난 보고서 한글 올리기] 대신 — 처음 세팅할 때 전회차가 있으면(우리 회사·타사) 그 동 쪽 PDF를 올리면 [🤖 채우기]·[🤖 지난 이력 읽기]·
// [🤖 전회차 보고서로 초안]이 읽음. 올리기만 하면 AI 안 씀, 처음 누를 때 한 번 읽어 저장. 직전 회차 한글이 있는 회차는 칸 대신 안내만.
// 서버 server/api/routers/sitok_prev.py, 읽기 server/sitok/prev_pdf.py.

async function sitokPrevSlot(el, reportId, onChange, opts = {}) {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const url = `/sitok/reports/${reportId}/prev-pdf`;
  let st = null;
  const say = (text, bad) => { const m = el.querySelector(".pv-msg"); if (m) { m.textContent = text || ""; m.classList.toggle("bad", !!bad); } };
  const draw = () => {
    if (st.has_prior) {
      el.innerHTML = `<div class="pv-slot pv-prior">📄 전회차 보고서: ${esc(st.prior_note || "직전 회차 보고서")} — 그 값을 자동으로 씁니다</div>`;
      return;
    }
    const rd = st.read;
    const c = rd ? rd.counts : {};
    el.innerHTML = `<div class="pv-slot${st.has ? " on" : ""}"><div class="pv-head"><b>📄 전회차 보고서 PDF</b>
        <span class="sk-help">${opts.wall ? "전회차 보고서(우리 회사·타사, 통째로 올려도 됨) — 1.3.1 자료수집 현황·1.4.5 요약표 전회 칸·1.2.4 도면 쪽(첨부 도면에 자동)을 읽습니다. 현장 조사에서 전회차 가져오기로 올렸으면 이미 들어 있음. 처음 점검이면 비워 두세요. 끌어다 놓아도 됩니다."
          : "전회차가 있으면(우리 회사·타사) 이 동의 결과표·1.1~1.2.8 쪽 PDF — 보고서 통째로 올려도 필요한 쪽만 읽습니다. 처음 점검이면 비워 두세요."}</span></div>
      <div class="pv-row">${st.has ? `<a class="secondary-link" href="${BASE}/api${url}/file" target="_blank" rel="noopener">${esc(st.name)}</a>
        <span class="pv-read${rd ? " ok" : ""}">${opts.wall ? "✓ 올려 둠" : rd ? `✓ ${esc(rd.at)} 읽음 — 현황 ${c.fields}칸 · 체크 ${c.checks} · 용도 ${c.uses}줄 · 점검이력 ${c.history} · 보수 ${c.repairs} · 변경 ${c.changes}${c.grade ? ` · 등급 ${esc(c.grade)}` : ""}`
          : "아직 안 읽음 — 🤖 버튼을 처음 누를 때 한 번 읽어 둡니다"}</span>` : ""}
        <label class="secondary-link pv-up">${st.has ? "바꾸기" : "＋ 올리기"}<input type="file" accept="application/pdf,.pdf" hidden data-kr-file="1" /></label>
        ${st.has ? '<button type="button" class="link-btn pv-del">빼기</button>' : ""}</div><div class="pv-msg sk-help"></div></div>`;
    const inp = el.querySelector(".pv-up input");
    inp.addEventListener("change", async () => {
      const f = inp.files[0];
      inp.value = "";
      if (!f) return;
      say(`${f.name} 올리는 중…`);
      try {
        const fd = new FormData();
        fd.append("file", f);
        st = await apiUpload(url, fd);
        draw();
        onChange?.(st);
      } catch (e) { say(e.message, true); }
    });
    enableFileDrop(el.querySelector(".pv-slot"), inp);
    el.querySelector(".pv-del")?.addEventListener("click", async () => {
      if (!confirm("올린 전회차 보고서 PDF와 읽은 값을 뺄까요? (이미 저장한 칸 값은 그대로)")) return;
      try { st = await api(url, { method: "DELETE" }); draw(); onChange?.(st); } catch (e) { say(e.message, true); }
    });
  };
  try { st = await api(url); draw(); } catch (e) { el.innerHTML = `<div class="mail-msg bad">${esc(e.message)}</div>`; }
  return { state: () => st, reload: async () => { st = await api(url); draw(); return st; } };
}
