// 시특법 시설물 화면 "같이 점검하는 동" 칸(sitok-facility.html?id=, 2026-10-12) — 한 계약에 여러 동(숭의교회 본관 + B동)을 보고서 한 권으로.
// 동마다 회차·현장 조사·현황·AI 초안은 따로, 보고서를 만들 때 합침(첫 동 = 대표·시설물편 제1장). 한 번 묶으면 다음 회차도 계속.
// 서버 server/api/routers/sitok_groups.py. 바꾸면 "sitok-group-changed" 이벤트 → 회차 칸(js/sitok-reports.js)이 다시 읽음.

(function () {
  const fid = Number(new URLSearchParams(location.search).get("id")) || null;
  const panel = document.getElementById("sk-group-panel");
  if (!fid || !panel) return;
  panel.hidden = false;
  const box = document.getElementById("sk-group");
  const errorEl = document.getElementById("error");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const changed = () => { window.dispatchEvent(new Event("sitok-group-changed")); load(); };

  function draw(d) {
    const g = d.group;
    box.innerHTML = (g ? `<div class="sg-head"><label>묶음 이름 <input class="sg-name" value="${esc(g.name)}" /></label>
        <span class="sk-help">표지·머리글·제출문에 씁니다(예: 숭의교회). 결과표 용역명은 동마다 따로.</span></div>
      <ol class="sg-list">${g.members.map((m, i) => `<li data-id="${m.id}"><span class="sg-no">제${i + 1}장</span>
        ${m.id === fid ? `<b>${esc(m.name)}</b> <em>(이 시설물)</em>` : `<a href="sitok-facility.html?id=${m.id}">${esc(m.name)}</a>`}
        <span class="sg-tpl">${esc(m.template)}</span>${i === 0 ? '<span class="sg-lead">대표</span>' : ""}
        <span class="sg-acts">${i ? '<button type="button" class="link-btn sg-up" title="앞으로(장 순서)">▲ 앞으로</button>' : ""}
        <button type="button" class="link-btn sg-del">묶음에서 빼기</button></span></li>`).join("")}</ol>`
      : '<p class="page-sub sg-none">이 시설물만 따로 보고서를 만듭니다. 한 계약에 여러 동(예: 본관 + B동)을 한 권으로 내야 하면 같이 점검하는 동을 더하세요.</p>')
      + `<div class="sg-add"><select class="sg-cand" aria-label="같이 점검하는 동"><option value="">+ 같이 점검하는 동 더하기</option>
        ${d.candidates.map((c) => `<option value="${c.id}">${esc(c.name)}${c.address ? ` — ${esc(c.address)}` : ""}</option>`).join("")}</select>
        <span class="sk-help">그 동을 먼저 시설물로 등록(관리대장)해야 고를 수 있습니다. 한 번 묶으면 다음 회차도 계속 한 권입니다.</span></div>`;
    box.querySelector(".sg-cand").addEventListener("change", async (e) => {
      const id = Number(e.target.value);
      if (!id) return;
      try { await apiPost(`/sitok/facilities/${fid}/group`, { facility_id: id }); changed(); } catch (x) { showError(errorEl, x); load(); }
    });
    if (!g) return;
    box.querySelector(".sg-name").addEventListener("change", async (e) => {
      try { await apiPatch(`/sitok/groups/${g.id}`, { name: e.target.value }); changed(); } catch (x) { showError(errorEl, x); }
    });
    box.querySelectorAll(".sg-up").forEach((b) => b.addEventListener("click", async () => {
      const ids = g.members.map((m) => m.id);
      const i = ids.indexOf(Number(b.closest("li").dataset.id));
      [ids[i - 1], ids[i]] = [ids[i], ids[i - 1]];
      try { await apiPost(`/sitok/groups/${g.id}/order`, { facility_ids: ids }); changed(); } catch (x) { showError(errorEl, x); }
    }));
    box.querySelectorAll(".sg-del").forEach((b) => b.addEventListener("click", async () => {
      const li = b.closest("li");
      if (!confirm(`${li.querySelector("b, a").textContent}을(를) 묶음에서 뺄까요? 다음에 만드는 보고서부터 따로 나옵니다.`)) return;
      try { await api(`/sitok/groups/${g.id}/members/${li.dataset.id}`, { method: "DELETE" }); changed(); } catch (x) { showError(errorEl, x); }
    }));
  }

  async function load() {
    try { draw(await api(`/sitok/facilities/${fid}/group`)); } catch (e) { showError(errorEl, e); }
  }
  load();
})();
