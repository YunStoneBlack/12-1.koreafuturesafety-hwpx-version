// 시특법 설정 탭 "사진 분류 교정 기록"(sitok-settings.html, 2026-10-12 사용자) — (AI 추천 → 점검자 값) 묶음별 사진, ✕로 지우기.
// 서버 server/api/routers/sitok_settings.py /corrections, 쌓기·쓰기 server/sitok/learn.py.

(function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const box = document.getElementById("ss-learn");
  if (!box) return;

  function draw(groups) {
    if (!groups.length) {
      box.innerHTML = '<div class="empty-note">아직 쌓인 교정 기록이 없습니다.</div>';
      return;
    }
    box.innerHTML = groups.map((g) => `<div class="ss-learn-g">
      <div class="ss-learn-h"><span class="ss-learn-ai">AI: ${esc(g.ai)}</span> → <b>${esc(g.to)}</b> <span class="sk-help">${g.items.length}건</span></div>
      <div class="ss-learn-items">${g.items.map((it) => `<figure class="ss-learn-it">
        ${it.has_photo ? `<img src="${BASE}/api/sitok/settings/corrections/${it.id}/photo" alt="" loading="lazy" />` : '<div class="ss-learn-nophoto">사진 없음</div>'}
        <figcaption>${esc(it.at)} ${esc(it.by)}<button type="button" data-id="${it.id}" title="이 기록 지우기">✕</button></figcaption></figure>`).join("")}</div></div>`).join("");
    box.querySelectorAll("figcaption button").forEach((b) => b.addEventListener("click", async () => {
      if (!confirm("이 교정 기록을 지울까요? 다음 사진 분석에 더 안 씁니다(결함은 그대로).")) return;
      try { draw((await api(`/sitok/settings/corrections/${b.dataset.id}`, { method: "DELETE" })).groups); } catch (e) { alert(e.message); }
    }));
    box.querySelectorAll("img").forEach((im) => im.addEventListener("click", () => window.open(im.src, "_blank")));
  }

  api("/sitok/settings/corrections").then((d) => draw(d.groups || [])).catch((e) => { box.innerHTML = `<div class="error" style="display:block">${esc(e.message)}</div>`; });
})();
