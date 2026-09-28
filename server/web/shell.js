// 화면 틀 — 보고서 자동화는 그룹웨어(groupware.kfsc21c.com)의 "보고서 자동화" 하위 메뉴다.
// 1) 왼쪽 사이드바: 그룹웨어가 렌더링해주는 진짜 사이드바 조각(/report-shell/sidebar — 로고·메뉴·관리자 메뉴·프로필·로그아웃)을
//    그대로 끼워 넣는다. 메뉴가 바뀌어도 자동으로 따라가고, 로그아웃도 그룹웨어 것이 그대로 동작한다.
//    그룹웨어를 거치지 않은 접속(사무실 LAN 직접 접속 등)이면 로고+보고서 메뉴만 있는 대체 사이드바를 그린다.
// 2) 본문 위 탭: 보고서 안의 하위 메뉴(현장 목록/담당요원/설정). 각 페이지 <body data-report-tab="sites|staff|settings">.
// 페이지마다 <aside class="sidebar" id="gw-sidebar"></aside> 빈 자리와 <main class="main">이 있어야 한다.

const REPORT_TABS = [
  ["sites", "현장 목록", "dashboard.html"],
  ["staff", "담당요원", "staff.html"],
  ["settings", "설정", "settings.html"],
];

function renderReportTabs() {
  const main = document.querySelector("main.main");
  if (!main) return;
  const active = document.body.dataset.reportTab || "sites";
  const nav = document.createElement("nav");
  nav.className = "report-tabs";
  for (const [key, label, href] of REPORT_TABS) {
    const a = document.createElement("a");
    a.href = href;
    a.textContent = label;
    if (key === active) a.className = "active";
    nav.appendChild(a);
  }
  main.prepend(nav);
}

function renderFallbackSidebar(aside) {
  aside.innerHTML = `
    <a class="brand" href="dashboard.html"><img src="img/logo-white.png" alt="한국미래안전" /></a>
    <nav class="nav"><a class="nav-item active" href="dashboard.html">보고서 자동화</a></nav>
    <div class="sidebar-foot">
      <div class="avatar" id="fallback-avatar">-</div>
      <div><div class="who" id="fallback-name">-</div><div class="role">직원</div></div>
    </div>`;
  api("/auth/me").then((me) => {
    const name = me.display_name || me.email || "?";
    document.getElementById("fallback-name").textContent = name;
    document.getElementById("fallback-avatar").textContent = name[0];
  }).catch(() => {});
}

async function loadGroupwareSidebar() {
  const aside = document.getElementById("gw-sidebar");
  if (!aside) return;
  try {
    const res = await fetch("/report-shell/sidebar", { credentials: "include", redirect: "manual" });
    const html = res.ok ? await res.text() : "";
    const doc = new DOMParser().parseFromString(html, "text/html");
    const fetched = doc.querySelector("aside.sidebar");
    if (!fetched) throw new Error("그룹웨어 사이드바를 받지 못함");
    fetched.id = "gw-sidebar";
    aside.replaceWith(fetched);
    // 폰에선 사이드바가 가로 메뉴 줄로 접히는데(style.css), "보고서 자동화"가 오른쪽 끝이라 화면 밖에 숨는다 → 보이게 스크롤
    const active = fetched.querySelector(".nav-item.active");
    if (active && fetched.scrollWidth > fetched.clientWidth) {
      fetched.scrollLeft = active.offsetLeft - (fetched.clientWidth - active.offsetWidth) / 2;
    }
  } catch (err) {
    renderFallbackSidebar(aside);
  }
}

renderReportTabs();
loadGroupwareSidebar();
