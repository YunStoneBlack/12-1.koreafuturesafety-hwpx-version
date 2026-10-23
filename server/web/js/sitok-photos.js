// 시특법 현장 조사 사진 크게 보기·돌리기(2026-10-23 형 "세로로 찍힌 사진이 핸드폰에서 확인 불가 → 확인 가능하게 + 사진 돌리기(산안법에 있는 기능)").
// 사진(결함 이번·전회차, 전경, 상태양호, 내진보강, 공중이용·기타시설)을 누르면 크게 보기 창(js/photo-viewer.js — 사진 전체, ◀▶로 같은 탭 사진 넘기기)에
// [↻ 돌리기](서버 POST /sitok/rotate — 원본을 오른쪽 90도, server/api/routers/sitok_rotate.py)와, 찍기 칸 사진이면 [📷 다시 찍기].
// 전엔 결함 이번 사진을 누르면 바로 다시 찍기였음 — 이제 크게 본 뒤 [📷 다시 찍기]. 폰에 보관 중인(아직 안 올라간) 사진은 예전처럼 누르면 다시 찍기.

(function () {
  const PAT = /\/api\/sitok\/(defects\/\d+\/photo\/(now|prev)|reports\/\d+\/(overview\/\w+\/photo|good\/photo|seismic\/photo|parts\/photo))(\?|$)/;
  const isPhoto = (el) => el instanceof HTMLImageElement && PAT.test(el.getAttribute("src") || "") && !el.closest(".pv-overlay");
  const shown = (el) => el.offsetParent !== null;
  const key = (src) => { // 같은 사진인지 — 새로 읽기 꼬리(t·v)는 빼고
    const u = new URL(src, location.href);
    u.searchParams.delete("t");
    u.searchParams.delete("v");
    return u.pathname + u.search;
  };
  const fresh = (src) => { const u = new URL(src, location.href); u.searchParams.set("t", Date.now()); return u.pathname + u.search; };

  const turned = new Map(); // 돌린 사진 → 새 꼬리 — 탭이 카드를 다시 그려도(옛 ?t=로) 돌린 사진을 받게
  const apply = (im) => {
    const v = isPhoto(im) && turned.get(key(im.src));
    if (v && new URL(im.src, location.href).searchParams.get("t") !== v) {
      const u = new URL(im.src, location.href);
      u.searchParams.set("t", v);
      im.src = u.pathname + u.search;
    }
  };
  new MutationObserver((muts) => {
    for (const m of muts) {
      for (const n of m.addedNodes) {
        if (n instanceof HTMLImageElement) apply(n);
        else if (n.querySelectorAll) n.querySelectorAll("img").forEach(apply);
      }
    }
  }).observe(document.body, { childList: true, subtree: true });

  async function rotate(item) {
    const k = key(item.src);
    await apiPost("/sitok/rotate", { src: k.replace(/^.*?\/api(?=\/sitok\/)/, "") });
    turned.set(k, String(Date.now()));
    document.querySelectorAll("img").forEach(apply); // 화면의 같은 사진(카드 미리보기)도 새로
    return fresh(item.src);
  }

  const rid = new URLSearchParams(location.search).get("report");
  function itemOf(img) {
    const own = /\/sitok\/defects\//.test(img.src) || img.src.includes(`/sitok/reports/${rid}/`); // 전회차 사진 보기 칸(직전 회차 주소)은 못 돌림
    const actions = own ? [{ label: "↻ 돌리기", run: (it) => rotate(it) }] : [];
    const input = img.closest("label")?.querySelector('input[type="file"]');
    if (input) actions.push({ label: "📷 다시 찍기", run: (it, close) => { close(); input.click(); } });
    const card = img.closest("[data-id]");
    const head = card?.querySelector(".sf-card-head b, .ov-title input");
    const no = card?.querySelector(".sf-no")?.textContent || "";
    const title = [no, head ? (head.value || head.textContent || "").trim() : ""].filter(Boolean).join(". ");
    return { src: img.src, orig: img.src, caption: [title, img.alt].filter(Boolean).join(" · "), actions };
  }

  document.addEventListener("click", (e) => {
    const img = e.target;
    if (!isPhoto(img) || !shown(img) || !window.openPhotoViewer) return;
    e.preventDefault(); // 찍기 칸(label) 안 사진이어도 바로 다시 찍지 않고 크게 보기
    e.stopPropagation(); // 예전 "새 탭으로 열기"보다 먼저
    const pane = img.closest('[id^="sf-"]') || document.querySelector(".main") || document;
    const imgs = [...pane.querySelectorAll("img")].filter((x) => isPhoto(x) && shown(x));
    window.openPhotoViewer(imgs.map(itemOf), Math.max(0, imgs.indexOf(img)));
  }, true);
})();
