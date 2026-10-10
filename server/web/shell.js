// 화면 틀 — 보고서 자동화는 그룹웨어(groupware.kfsc21c.com)의 "보고서 자동화" 하위 메뉴다.
// 1) 왼쪽 사이드바: 그룹웨어가 렌더링해주는 진짜 사이드바 조각(/report-shell/sidebar — 로고·메뉴·관리자 메뉴·프로필·로그아웃)을
//    그대로 끼워 넣는다. 메뉴가 바뀌어도 자동으로 따라가고, 로그아웃도 그룹웨어 것이 그대로 동작한다.
//    한 번 받은 조각은 이 탭(sessionStorage)에 기억해 두고 다음 화면부터는 즉시 그린 뒤 뒤에서 새로 받아 바뀐 경우만 교체한다
//    — 매 화면마다 빈 사이드바가 잠깐 보였다가 채워지면 그룹웨어의 다른 메뉴와 달리 "다른 사이트로 넘어가는" 느낌이 났다.
//    그룹웨어를 거치지 않은 접속(사무실 LAN 직접 접속 등)이면 로고+보고서 메뉴만 있는 대체 사이드바를 그린다.
// 2) 본문 머리: 목록 화면(<body data-report-tab="sites|status|calendar|staff|settings">)은 그룹웨어 화면처럼 "큰 제목 + 회색 설명" 아래
//    하위 메뉴 탭(현장 목록/제출 현황/담당요원/설정)을 두고, 상세 화면(현장·보고서 — <body data-report-tab="sites" data-tabs-only>)은 큰 제목 없이
//    탭 줄만 + 각 페이지의 경로 표시(crumb). 탭 줄은 스크롤해도 화면 위에 붙어 있다(10/8 사용자) — 그 아래 붙는 줄(현장 목록 상태 카드·보고서 목차)은
//    CSS 변수 --tabs-h(탭 줄 높이)만큼 내려 붙는다.
//    탭 아래엔 지도 기한 임박·초과 현장이 있으면 알림 띠("⏰ 임박 N곳 · ⚠ 초과 N곳 → 제출 현황")를 띄운다(제출 현황 탭 자체는 숫자 칸이 있어 생략).
// 페이지마다 <aside class="sidebar" id="gw-sidebar"></aside> 빈 자리와 <main class="main">이 있어야 한다.

const REPORT_TABS = [
  ["sites", "현장 목록", "dashboard.html"],
  ["status", "제출 현황", "status.html"],
  ["calendar", "방문 달력", "calendar.html"],
  ["staff", "담당요원", "staff.html"],
  ["settings", "설정", "settings.html"],
];
// 서류 자동화(2026-10-06) — 그룹웨어 왼쪽 메뉴 "서류 자동화"(보고서 자동화 아래)가 여는 화면들. <body data-docs-tab="contracts|status|calendar">.
// 같은 보고서 앱 안의 페이지라 로그인·DB를 같이 쓰고, 사이드바는 같은 그룹웨어 조각에서 "서류 자동화" 줄을 켜 준다(isDocsPage).
const DOCS_TABS = [
  ["contracts", "계약 목록", "docs.html"],
  ["status", "제출 현황", "docs-status.html"],
  ["calendar", "착수·완수 일정", "docs-calendar.html"],
  ["settings", "설정", "docs-settings.html"],
];
const isDocsPage = () => !!document.body.dataset.docsTab;
// 산안법 / 시특법(2026-10-10) — 그룹웨어 왼쪽 메뉴 [보고서 자동화]·[서류 자동화] 아래 소메뉴. <body data-law="sitok">이면 시특법 화면(없으면 산안법).
// 시특법은 아직 메인 하나씩(설계: 바탕화면 "시특법 견본\인수인계.md") — 단계마다 탭을 늘린다.
const pageLaw = () => (document.body.dataset.law === "sitok" ? "sitok" : "sanan");
const SITOK_TABS = [["facilities", "시설물 목록", "sitok.html"]];
const SITOK_DOCS_TABS = [["contracts", "계약 목록", "sitok-docs.html"]];
const LAW_LABEL = { sanan: "산안법", sitok: "시특법" };
const SIDEBAR_CACHE_KEY = "kfsc-report:gw-sidebar";

function renderReportHeader() {
  const main = document.querySelector("main.main");
  const docs = isDocsPage();
  const active = docs ? document.body.dataset.docsTab : document.body.dataset.reportTab;
  if (!main || !active) return;
  const tabsOnly = document.body.dataset.tabsOnly !== undefined;
  const head = document.createElement("div");
  head.className = "report-head";
  const law = pageLaw();
  const sub = law === "sitok"
    ? (docs ? "시설물 점검 용역의 착수계·준공계 등 서류를 만듭니다." : "시설물 정기안전점검 결과보고서를 작성하고 PDF로 만듭니다.")
    : (docs ? "용역 계약별 착수계·완수계를 만들고 제출 현황·일정을 봅니다." : "현장별 기술지도 결과보고서를 작성하고 PDF로 만듭니다.");
  head.innerHTML = `<h1>${docs ? "서류 자동화" : "보고서 자동화"}<span class="law-badge ${law}">${LAW_LABEL[law]}</span></h1>
    <p class="page-sub">${sub}</p>`;
  const nav = document.createElement("nav");
  nav.className = `report-tabs${tabsOnly ? " tabs-only" : ""}`;
  const tabs = law === "sitok" ? (docs ? SITOK_DOCS_TABS : SITOK_TABS) : (docs ? DOCS_TABS : REPORT_TABS);
  for (const [key, label, href] of tabs) {
    const a = document.createElement("a");
    a.href = href;
    a.textContent = label;
    if (key === active) a.className = "active";
    nav.appendChild(a);
  }
  // 탭 줄은 머리(제목) 안이 아니라 본문 바로 아래 자식으로 — position: sticky는 부모 안에서만 붙어 있어서, 제목 칸 안에 두면 제목과 같이 올라가 버림
  main.prepend(nav);
  if (!tabsOnly) main.prepend(head);
  const setH = () => document.documentElement.style.setProperty("--tabs-h", `${nav.offsetHeight}px`);
  setH();
  if (window.ResizeObserver) new ResizeObserver(setH).observe(nav);
}

function renderFallbackSidebar(aside) {
  aside.innerHTML = `
    <a class="brand" href="dashboard.html"><img src="img/logo-white.png" alt="한국미래안전" /></a>
    <nav class="nav"><a class="nav-item" data-menu="report" href="dashboard.html">보고서 자동화</a>
      <div class="nav-sub"><a class="nav-subitem" data-law="sanan" href="dashboard.html">산안법</a><a class="nav-subitem" data-law="sitok" href="sitok.html">시특법</a></div>
      <a class="nav-item" data-menu="docs" href="docs.html">서류 자동화</a>
      <div class="nav-sub"><a class="nav-subitem" data-law="sanan" href="docs.html">산안법</a><a class="nav-subitem" data-law="sitok" href="sitok-docs.html">시특법</a></div></nav>
    <div class="sidebar-foot">
      <div class="avatar" id="fallback-avatar">-</div>
      <div><div class="who" id="fallback-name">-</div><div class="role">직원</div></div>
    </div>`;
  markSidebar(aside);
  api("/auth/me").then((me) => {
    const name = me.display_name || me.email || "?";
    document.getElementById("fallback-name").textContent = name;
    document.getElementById("fallback-avatar").textContent = name[0];
  }).catch(() => {});
}

function readSidebarCache() {
  try { return sessionStorage.getItem(SIDEBAR_CACHE_KEY); } catch { return null; }
}

function writeSidebarCache(html) {
  try { sessionStorage.setItem(SIDEBAR_CACHE_KEY, html); } catch { /* 저장 못 해도 매번 받아오면 그만 */ }
}

// 지금 화면에 맞는 메뉴 줄 켜기 — 그룹웨어 조각은 늘 "보고서 자동화"를 켜서 주므로 서류 화면이면 "서류 자동화"로 바꾸고,
// 그 아래 소메뉴(산안법/시특법) 중 이 화면 쪽을 켠다. 예전 조각(data-menu 없음)이면 주소로 찾는다.
function markSidebar(aside) {
  const want = isDocsPage() ? "docs" : "report";
  const parent = aside.querySelector(`.nav-item[data-menu="${want}"]`)
    || aside.querySelector(want === "docs" ? '.nav-item[href$="docs.html"]' : '.nav-item[href$="/report/"]');
  if (!parent) return;
  aside.querySelectorAll(".nav-item.active, .nav-subitem.active").forEach((a) => a.classList.remove("active"));
  parent.classList.add("active");
  const subs = parent.nextElementSibling;
  if (subs && subs.classList.contains("nav-sub")) {
    subs.querySelector(`.nav-subitem[data-law="${pageLaw()}"]`)?.classList.add("active");
  }
}

// 받아온 조각 HTML에서 <aside class="sidebar">를 꺼내 지금 자리(#gw-sidebar)와 바꾼다. 성공하면 true.
function mountSidebar(html) {
  const current = document.getElementById("gw-sidebar");
  if (!current || !html) return false;
  const fetched = new DOMParser().parseFromString(html, "text/html").querySelector("aside.sidebar");
  if (!fetched) return false;
  fetched.id = "gw-sidebar";
  markSidebar(fetched);
  current.replaceWith(fetched);
  // 폰에선 사이드바가 가로 메뉴 줄로 접히는데(style.css), "보고서 자동화"가 오른쪽 끝이라 화면 밖에 숨는다 → 보이게 스크롤
  const active = fetched.querySelector(".nav-item.active");
  if (active && fetched.scrollWidth > fetched.clientWidth) {
    fetched.scrollLeft = active.offsetLeft - (fetched.clientWidth - active.offsetWidth) / 2;
  }
  return true;
}

async function loadGroupwareSidebar() {
  if (!document.getElementById("gw-sidebar")) return;
  const cached = readSidebarCache();
  const shownFromCache = cached ? mountSidebar(cached) : false;
  try {
    const res = await fetch("/report-shell/sidebar", { credentials: "include", redirect: "manual" });
    const html = res.ok ? await res.text() : "";
    if (!html.includes("sidebar")) throw new Error("그룹웨어 사이드바를 받지 못함");
    if (html !== cached) {
      if (!mountSidebar(html)) throw new Error("그룹웨어 사이드바 형식이 다름");
      writeSidebarCache(html);
    }
  } catch (err) {
    if (!shownFromCache) renderFallbackSidebar(document.getElementById("gw-sidebar"));
  }
}

// 파일 선택칸 — 브라우저 기본 버튼은 브라우저 언어를 따라 "Choose File / No file chosen"(영어)로 나오기도 하고 모양도 제각각이라,
// 원래 칸은 안 보이게 두고(동작·이벤트는 그대로) 그룹웨어 보조 버튼 모양의 "사진 선택/파일 선택" 버튼을 옆에 붙인다.
// 섹션이 나중에 그려지는 칸(보고서 슬롯 등)도 있어서 문서 변화를 지켜보며 새로 생긴 칸에도 붙인다.
// 사진 칸(미리보기 썸네일이 있는 곳)은 고르는 즉시 올라가고 썸네일이 보이므로 파일 이름은 안 띄운다. PC에선 끌어다 놓기도 된다.
function enhanceFileInputs(root) {
  root.querySelectorAll('.main input[type="file"]:not([data-kr-file])').forEach((input) => {
    input.dataset.krFile = "1";
    if (input.style.display === "none") return; // 자체 버튼이 있는 칸(서명 이미지 올리기 등)
    const showName = !input.closest(".photo-slot")?.querySelector(".thumb");
    const wrap = document.createElement("span");
    wrap.className = "file-pick";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "secondary file-pick-btn";
    btn.textContent = (input.accept || "").startsWith("image") ? "사진 선택" : "파일 선택";
    const name = document.createElement("span");
    name.className = "file-pick-name";
    name.textContent = showName ? "선택된 파일 없음" : "";
    wrap.append(btn, name);
    input.classList.add("file-pick-input");
    input.after(wrap);
    btn.addEventListener("click", () => input.click());
    input.addEventListener("change", () => {
      if (showName) name.textContent = input.files[0]?.name || "선택된 파일 없음";
    });
    // PC에서 파일을 끌어다 놓기 — 사진 칸이면 칸 전체(.photo-slot), 아니면 버튼 줄이 받는 곳. 놓은 파일을 원래 칸에 넣고
    // change를 일으켜서 "선택"한 것과 똑같이 처리된다(사진 칸은 바로 업로드).
    const zone = input.closest(".photo-slot") || wrap;
    zone.addEventListener("dragover", (e) => {
      if (![...(e.dataTransfer?.types || [])].includes("Files")) return;
      e.preventDefault();
      zone.classList.add("drop-over");
    });
    zone.addEventListener("dragleave", (e) => {
      if (!zone.contains(e.relatedTarget)) zone.classList.remove("drop-over");
    });
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("drop-over");
      const file = e.dataTransfer.files[0];
      if (!file) return;
      const accept = (input.accept || "").trim();
      const okType = !accept || accept.split(",").some((a) => {
        a = a.trim();
        return a.endsWith("/*") ? file.type.startsWith(a.slice(0, -1)) : file.type === a || file.name.toLowerCase().endsWith(a);
      });
      if (!okType) {
        alert(accept.startsWith("image") ? "이미지 파일만 올릴 수 있습니다." : "이 칸에 맞는 파일 형식이 아닙니다.");
        return;
      }
      const dt = new DataTransfer();
      dt.items.add(file);
      input.files = dt.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
  });
}

renderReportHeader();
loadGroupwareSidebar();
enhanceFileInputs(document);
new MutationObserver(() => enhanceFileInputs(document)).observe(document.querySelector("main.main") || document.body, { childList: true, subtree: true });
