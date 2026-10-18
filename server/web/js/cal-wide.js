// 방문 달력 넓게(2026-10-18 민재형 "달력 가로·세로 더 크게", "위 안내 줄과 달력 오른쪽 선은 맞추고 달력은 더 늘려도 됨") —
// 산안법 calendar.html(.cal-wrap)·시특법 sitok-calendar.html(.dk-wrap) 공용. 달력 = 본문 폭 전부(위 안내·거르기 줄과 같은 오른쪽 끝),
// 그날 상세 = 본문 바깥 오른쪽 빈 곳(260~400px, 화면 오른쪽 24px 남김). 빈 곳이 모자라면(좁은 PC) 원래대로 본문 안에 나란히. 달력 그리기 전에 불러야 그 폭으로 그려짐.
(function () {
  const wrap = document.querySelector(".cal-wrap, .dk-wrap");
  if (!wrap) return;
  const fit = () => {
    wrap.style.marginRight = "";
    wrap.style.gridTemplateColumns = "";
    if (window.innerWidth <= 1100) return; // 1100 이하는 달력 아래로 상세(원래대로)
    const main = wrap.parentElement;
    const right = main.getBoundingClientRect().right - parseFloat(getComputedStyle(main).paddingRight); // 위 안내 줄 오른쪽 끝
    const width = Math.floor(right - wrap.getBoundingClientRect().left);
    const side = Math.min(400, Math.floor(document.documentElement.clientWidth - right - 24 - 16));
    if (side < 260) { wrap.style.marginRight = "0px"; return; }
    wrap.style.gridTemplateColumns = `${width}px ${side}px`;
    wrap.style.marginRight = `-${side + 16}px`;
  };
  fit();
  window.addEventListener("resize", fit);
})();
