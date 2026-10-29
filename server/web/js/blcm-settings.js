// 보고서 자동화 설정 [건축물관리법] 칸(2026-10-30 사용자 "산안법/시특법/건축물관리법 — 교육수료증 서류가 용역별로 다름") — 기술자마다 건축물관리점검 교육 이수증
// (신규·보수교육, 한 번 올리면 모든 건 부록에). 명단은 산안법·시특법과 같은 tech_person(이름·직책·등급은 [✏️ 고치기] — 어디서 고쳐도 같이),
// 교육 서류만 용역마다 따로(산안법 = 착수계 교육수료증, 시특법 = 정밀안전진단 교육 수료증, 여기 = 건축물관리점검 교육 이수증). 서버 server/api/routers/blcm.py /blcm/persons.

(function () {
  const box = document.getElementById("bs-persons");
  if (!box) return;
  const errorEl = document.getElementById("error");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const err = (e) => showError(errorEl, e);

  function eduRow(p) {
    const row = document.createElement("div");
    row.className = "ss-doc";
    row.innerHTML = `<b>건축물관리점검 교육 이수증</b>${p.edu ? '<span class="ss-st ok">✓ 올림</span>' : '<span class="ss-st none">없음 — 건축물관리점검 보고서 부록에 빠짐</span>'}
      <span class="sk-help">신규·보수교육 이수증 — 그림(JPG·PNG)이나 PDF(첫 장), 끌어다 놓아도 됩니다</span>
      <span class="ss-acts">${p.edu ? `<a class="secondary-link" href="${BASE}/api/blcm/persons/${p.id}/edu?t=${p.edu_ts}" target="_blank" rel="noopener">보기</a>` : ""}
        <label class="secondary-link">${p.edu ? "바꾸기" : "올리기"}<input type="file" accept="image/*,application/pdf,.pdf" hidden data-kr-file="1" /></label>
        ${p.edu ? '<button type="button" class="secondary btn-sm ss-del">지우기</button>' : ""}</span>`;
    const file = row.querySelector('input[type="file"]');
    file.addEventListener("change", async () => {
      if (!file.files[0]) return;
      row.classList.add("busy");
      try {
        const fd = new FormData();
        fd.append("file", file.files[0]);
        await apiUpload(`/blcm/persons/${p.id}/edu`, fd);
        load();
      } catch (e) { err(e); row.classList.remove("busy"); }
    });
    enableFileDrop(row, file);
    row.querySelector(".ss-del")?.addEventListener("click", async () => {
      if (!confirm(`${p.name} 건축물관리점검 교육 이수증을 지울까요?`)) return;
      try { await api(`/blcm/persons/${p.id}/edu`, { method: "DELETE" }); load(); } catch (x) { err(x); }
    });
    return row;
  }

  async function load() {
    try {
      const { persons } = await api("/blcm/persons");
      box.innerHTML = persons.length ? "" : '<div class="empty-note">기술자가 없습니다 — [시특법] 칸이나 [산안법] 칸 착수계 기술자 명단에서 추가하세요.</div>';
      for (const p of persons) {
        const card = document.createElement("div");
        card.className = "ss-person";
        const last = p.position !== p.tech_position || p.grade !== (p.tech_grade || "").replace("기술자", "기술인");
        card.innerHTML = `<div class="ss-person-head"><b>${esc(p.name)}</b><span>${esc([p.tech_position, p.tech_grade].filter(Boolean).join(" · "))}</span></div>
          ${last && (p.position || p.grade) ? `<div class="sk-help bs-last">최근 건 명단에 적은 직위·등급: ${esc([p.position, p.grade].filter(Boolean).join(" · "))}(건 화면 명단에서 고치면 다음 건에 그대로)</div>` : ""}
          <div class="ss-person-docs"></div>`;
        if (typeof techPersonEdit === "function") techPersonEdit(card.querySelector(".ss-person-head"), { id: p.id, name: p.name, position: p.tech_position, grade: p.tech_grade }, load);
        card.querySelector(".ss-person-docs").appendChild(eduRow(p));
        box.appendChild(card);
      }
    } catch (e) { err(e); }
  }
  load();
})();
