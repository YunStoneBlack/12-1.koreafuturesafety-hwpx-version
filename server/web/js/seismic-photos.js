// 내진성능평가 현장 사진 칸(2026-10-27 형·민재형 — 현장조사 입력에서 외관조사 탭으로 옮김: [📷 현장 사진] [🏢 전경사진], 위치도 칸은 뺌 — 건 화면 📍 위치도 핀으로).
// 칸마다 한 장, 누르면 올리기·바꾸기, ✕ 지우기, 끌어다 놓기. 서버 /seismic/projects/{id}/field(·/photo/{칸}) — 예전 seismic-field.js drawPhotos 그대로.
// mountSeismicPhotos(상자, 회차 id, 칸 거르기(key → 참이면 보임), 장수 알림(있음, 전체)) → 다시 그리기 함수.

window.mountSeismicPhotos = function (box, id, want, onCount) {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let F = null;
  function draw() {
    const slots = F.photo_slots.filter(([k]) => want(k));
    const have = slots.filter(([k]) => F.photos[k]).length;
    if (onCount) onCount(have, slots.length);
    box.innerHTML = slots.map(([k, label, where]) => {
      const p = F.photos[k];
      return `<div class="sf2-ph${p ? " on" : ""}" data-slot="${k}">
        <label class="sf2-ph-img">${p ? `<img src="${BASE}/api/seismic/projects/${id}/field/photo/${k}?v=${encodeURIComponent(p.at)}" alt="" loading="lazy" />` : '<span class="sf2-ph-empty">＋ 사진</span>'}
          <input type="file" accept="image/*" hidden data-kr-file="1" /></label>
        <div class="sf2-ph-cap"><b>${esc(label)}</b><span class="sk-help">${esc(where)}</span>${p ? `<button type="button" class="sp-x" title="지우기">✕</button>` : ""}</div></div>`;
    }).join("");
    box.querySelectorAll(".sf2-ph").forEach((el) => {
      const slot = el.dataset.slot;
      const input = el.querySelector("input");
      if (typeof enableFileDrop === "function") enableFileDrop(el, input);
      input.addEventListener("change", async () => {
        if (!input.files[0]) return;
        el.classList.add("busy");
        const fd = new FormData();
        fd.append("file", input.files[0]);
        try { F = await apiUpload(`/seismic/projects/${id}/field/photo/${slot}`, fd); draw(); } catch (e) { alert(e.message); el.classList.remove("busy"); }
      });
      el.querySelector(".sp-x")?.addEventListener("click", async () => {
        if (!confirm("이 사진을 지울까요?")) return;
        try { F = await api(`/seismic/projects/${id}/field/photo/${slot}`, { method: "DELETE" }); draw(); } catch (e) { alert(e.message); }
      });
    });
  }
  const load = async () => {
    try { F = await api(`/seismic/projects/${id}/field`); draw(); } catch (e) { box.innerHTML = `<p class="error" style="display:block">${esc(e.message)}</p>`; }
  };
  load();
  return load;
};
