// ---------- 사진 크게 보기(2026-10-07 사용자) — 보고서 화면의 사진 칸 미리보기(<img class="thumb" src="…?thumb=1">)를 누르면 화면 위에 크게 ----------
// 모든 사진 칸(3 전경·점검, 4 이전지적·이행완료, 8 지적사항, 10 TBM·계측, 11 제공자료…)이 같은 모양이라 문서 전체에서 한 번에 잡는다(클릭 위임).
// - 보기용 크기(서버 ?view=1, 긴 쪽 1400px — 보고서 PDF에 넣는 크기)로 빠르게, [원본 보기]만 원본(폰 원본은 5~10MB라 데이터로 느림)
// - 같은 번호 칸(같은 <section class="panel">) 사진끼리 ◀ ▶·키보드 ←→·폰은 옆으로 밀기, 사진을 누르면 원래 크기로 확대(다시 누르면 맞춤)
// - 닫기: ✕·바깥·ESC. 화면 규칙은 css/photo-viewer.css.

(function () {
  const isThumb = (el) => el instanceof HTMLImageElement && el.classList.contains("thumb") && /[?&]thumb=1/.test(el.getAttribute("src") || "");
  const shown = (img) => img.getAttribute("src") && img.style.display !== "none" && img.offsetParent !== null;
  const withParam = (src, drop, add) => {
    const u = new URL(src, location.href);
    u.searchParams.delete(drop);
    if (add) u.searchParams.set(add, "1");
    return u.toString();
  };
  const caption = (img) => {
    const slot = img.closest(".photo-slot, .card, .mat-card");
    const matTitle = img.id.startsWith("mat-thumb-") ? document.getElementById(img.id.replace("mat-thumb-", "mat-title-"))?.value : ""; // 11번 제공자료는 자료 제목
    const label = matTitle || slot?.querySelector(".slot-label")?.textContent || img.alt || "";
    const head = img.closest("section.panel")?.querySelector(".panel-head h2, h2")?.textContent || "";
    return [head, label].filter(Boolean).join(" · ");
  };

  let overlay = null, list = [], idx = 0;

  function open(img) {
    const section = img.closest("section.panel") || document;
    list = [...section.querySelectorAll("img.thumb")].filter((x) => isThumb(x) && shown(x));
    idx = Math.max(0, list.indexOf(img));
    overlay = document.createElement("div");
    overlay.className = "pv-overlay";
    overlay.innerHTML = `
      <div class="pv-top"><span class="pv-cap"></span><span class="pv-count"></span>
        <a class="pv-orig" target="_blank" rel="noopener">원본 보기</a><button type="button" class="pv-close" aria-label="닫기">✕</button></div>
      <div class="pv-stage"><img class="pv-img" alt="" /><div class="pv-msg"></div></div>
      <button type="button" class="pv-nav pv-prev" aria-label="이전 사진">‹</button><button type="button" class="pv-nav pv-next" aria-label="다음 사진">›</button>`;
    document.body.appendChild(overlay);
    document.body.classList.add("pv-open");
    overlay.querySelector(".pv-close").addEventListener("click", close);
    overlay.querySelector(".pv-prev").addEventListener("click", (e) => { e.stopPropagation(); go(-1); });
    overlay.querySelector(".pv-next").addEventListener("click", (e) => { e.stopPropagation(); go(1); });
    overlay.querySelector(".pv-stage").addEventListener("click", (e) => { if (e.target.classList.contains("pv-stage")) close(); });
    const big = overlay.querySelector(".pv-img");
    big.addEventListener("click", () => overlay.classList.toggle("pv-zoom"));
    big.addEventListener("load", () => overlay.classList.remove("pv-loading"));
    big.addEventListener("error", () => {
      overlay.classList.remove("pv-loading");
      overlay.querySelector(".pv-msg").textContent = "크게 보기를 못 하는 파일입니다 — [원본 보기]로 여세요.";
    });
    // 폰: 옆으로 밀어 넘기기(확대 중엔 화면 이동이 우선)
    let x0 = null;
    overlay.addEventListener("touchstart", (e) => { x0 = e.touches.length === 1 ? e.touches[0].clientX : null; }, { passive: true });
    overlay.addEventListener("touchend", (e) => {
      if (x0 == null || overlay.classList.contains("pv-zoom")) return;
      const dx = e.changedTouches[0].clientX - x0;
      if (Math.abs(dx) > 50) go(dx < 0 ? 1 : -1);
      x0 = null;
    });
    document.addEventListener("keydown", onKey, true);
    show();
  }

  function show() {
    const img = list[idx];
    if (!img) return close();
    const src = img.getAttribute("src");
    overlay.classList.add("pv-loading");
    overlay.classList.remove("pv-zoom");
    overlay.querySelector(".pv-msg").textContent = "";
    overlay.querySelector(".pv-img").src = withParam(src, "thumb", "view");
    overlay.querySelector(".pv-orig").href = withParam(withParam(src, "thumb"), "view");
    overlay.querySelector(".pv-cap").textContent = caption(img);
    overlay.querySelector(".pv-count").textContent = list.length > 1 ? `${idx + 1} / ${list.length}` : "";
    overlay.querySelectorAll(".pv-nav").forEach((b) => { b.hidden = list.length < 2; });
  }

  function go(step) {
    if (list.length < 2) return;
    idx = (idx + step + list.length) % list.length;
    show();
  }

  function close() {
    document.removeEventListener("keydown", onKey, true);
    overlay?.remove();
    overlay = null;
    document.body.classList.remove("pv-open");
  }

  function onKey(e) {
    if (e.key === "Escape") { e.stopPropagation(); close(); }
    else if (e.key === "ArrowLeft") go(-1);
    else if (e.key === "ArrowRight") go(1);
  }

  document.addEventListener("click", (e) => {
    const img = e.target;
    if (!isThumb(img) || !shown(img)) return;
    e.preventDefault();
    e.stopPropagation(); // 칸의 다른 클릭(예전 제공자료 새 탭 열기)보다 먼저
    open(img);
  }, true);
})();
