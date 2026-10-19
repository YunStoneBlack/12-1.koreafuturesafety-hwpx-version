// 목록 화면 위쪽(제목·탭·반기·검색·분야·숫자 카드)을 스크롤해도 붙어 있게(2026-10-19 민재형 "해당 부분 스크롤 하더라도 고정으로") — PC만(style.css .sticky-head).
// 본문(main) 첫 목록 칸(section.panel) 앞의 것을 한 칸(.sticky-head)으로 묶음. body에 data-sticky-list가 있으면 목록 칸 머리줄(전체·민간·관급·정렬·개수)도 그 아래에 붙음.
// 폰은 display: contents로 묶음을 없앤 것처럼(탭 줄만 붙던 예전 그대로). shell.js(제목·탭 넣기) 뒤에 부름.
(function () {
  const main = document.querySelector("main.main");
  const list = main && main.querySelector(":scope > section.panel");
  if (!list) return;
  const head = document.createElement("div");
  head.className = "sticky-head";
  main.insertBefore(head, main.firstElementChild);
  while (head.nextElementSibling && head.nextElementSibling !== list) head.appendChild(head.nextElementSibling);
  if (document.body.dataset.stickyList !== undefined) list.classList.add("sticky-list");
  const setH = () => document.documentElement.style.setProperty("--sticky-h", `${head.offsetHeight}px`);
  setH();
  if (window.ResizeObserver) new ResizeObserver(setH).observe(head);
})();
