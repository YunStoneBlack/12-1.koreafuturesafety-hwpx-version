// 달력 날짜 칸의 "산안 N · 시특 N" 작은 표시(2026-10-31 민재형 "전체 달력에는 시특n 산안n 작게, 산안·시특 개별 달력에도 — 폰트 안 겹치게").
// 산안 N = 그날 산안법 현장 수(회사 전체, GET /calendar의 day_total), 시특 N = 그날 시특법 건물 수(GET /sitok/calendar의 day_load, 하루 한도 day_cap 넘으면 빨강).
// 보기만 하는 숫자. 산안법 달력(calendar.js)·시특법 방문 달력(sitok-calendar.js)이 FullCalendar 칸 위쪽에 이 조각을 붙인다(home-cal.js는 자기 칸에 같은 모양을 직접 그림).
(function () {
  const level = (n, cap) => (!n ? "" : cap && n / cap < 0.35 ? "lo" : cap && n / cap < 0.7 ? "mid" : "hi"); // 산안 현장이 적은 날 연하게
  // sananN·sitokN 둘 다 0이면 null. 칸 폭이 좁은 폰에서도 안 겹치게 CSS(css/day-counts.css)가 날짜 아래 한 줄·세로로 쌓음.
  window.dayCountsEl = function (sananN, sananCap, sitokN, sitokCap) {
    if (!sananN && !sitokN) return null;
    const el = document.createElement("div");
    el.className = "dcnt";
    if (sananN) {
      const s = document.createElement("span");
      s.className = `dc-san ${level(sananN, sananCap)}`;
      s.title = `그날 산안법 현장 ${sananN}곳${sananCap ? ` (하루 한도 ${sananCap})` : ""}`;
      s.innerHTML = `<i>산안</i>${sananN}`;
      el.appendChild(s);
    }
    if (sitokN) {
      const s = document.createElement("span");
      const over = sitokCap && sitokN > sitokCap;
      s.className = `dc-sit${over ? " over" : ""}`;
      s.title = `그날 시특법 건물 ${sitokN}개${over ? ` — 하루 ${sitokCap}개 넘음` : ""}`;
      s.innerHTML = `<i>시특</i>${sitokN}`;
      el.appendChild(s);
    }
    return el;
  };
})();
