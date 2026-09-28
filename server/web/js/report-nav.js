// report.html 스크립트 — 섹션 목차 줄(화면 위에 붙어 다니는 바로가기 + 자동 저장 상태)과 빈 슬롯 접기.
// 보고서 화면은 섹션 14개로 PC에서도 스크롤이 매우 길어 원하는 섹션을 찾기 어려웠다 → 목차 줄에서 누르면 그 섹션으로 이동,
// 스크롤하면 지금 보고 있는 섹션이 표시된다. 폰에선 목차 줄이 가로로 밀린다.

// 섹션 제목 앞 번호 → 목차에 쓸 짧은 이름(제목 전체는 마우스를 올리면 보임)
const TOC_SHORT_NAMES = {
  "1.": "결재·통보", "2.": "특이사항", "3.": "사진", "4.": "이전지적", "5.": "대형사고", "6.": "기인물",
  "6-3.": "장비·물질", "7.": "현재공정", "8.": "지적사항", "9.": "향후공정", "10.": "지원사항", "11.": "제공자료",
};

function setupReportToc() {
  const sections = Array.from(document.querySelectorAll("main.main > section.panel"));
  const bar = document.createElement("div");
  bar.className = "report-toc";
  const chips = document.createElement("nav");
  chips.className = "toc-chips";
  const links = sections.map((section, idx) => {
    const title = section.querySelector(".panel-head h2").textContent.trim();
    const num = title.split(" ")[0];
    section.id = section.id || `sec-${idx}`;
    const a = document.createElement("a");
    a.href = `#${section.id}`;
    a.title = title;
    a.textContent = TOC_SHORT_NAMES[num] ? `${num.replace(/\.$/, "")} ${TOC_SHORT_NAMES[num]}` : title;
    a.addEventListener("click", (e) => {
      e.preventDefault();
      section.scrollIntoView({ behavior: "smooth", block: "start" });
      history.replaceState(null, "", `#${section.id}`);
    });
    chips.appendChild(a);
    return a;
  });
  const indicator = document.createElement("span");
  indicator.id = "save-indicator";
  indicator.title = "누르면 맨 위로";
  indicator.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
  bar.append(chips, indicator);
  document.getElementById("error").before(bar);
  updateSaveIndicator();

  // 지금 보고 있는 섹션 = 목차 줄 바로 아래를 지나간 마지막 섹션
  let activeIdx = -1;
  const markActive = () => {
    const edge = bar.getBoundingClientRect().bottom + 30; // 섹션으로 이동하면 목차 줄 아래 여백(scroll-margin-top)만큼 떨어져 멈춘다
    let idx = 0;
    sections.forEach((s, i) => { if (s.getBoundingClientRect().top <= edge) idx = i; });
    if (idx === activeIdx) return;
    activeIdx = idx;
    links.forEach((a, i) => a.classList.toggle("active", i === idx));
    const a = links[idx];
    // 페이지는 그대로 두고 목차 줄 안에서만 가로 스크롤(scrollIntoView는 페이지까지 움직임)
    chips.scrollLeft = a.offsetLeft - (chips.clientWidth - a.offsetWidth) / 2;
  };
  window.addEventListener("scroll", markActive, { passive: true });
  markActive();
}

// 빈 슬롯 접기 — 지적사항/공정/사진처럼 칸이 여러 개 미리 있는 곳에서 빈 칸이 전부 펼쳐져 화면이 길었다.
// 내용 있는 칸은 그대로 보이고, 빈 칸은 숨긴 뒤 "+ ○○ 추가" 버튼으로 하나씩 연다(전부 비었으면 첫 칸은 보여 줌).
// 숨긴 칸도 문서엔 그대로 있어서 저장·번호(슬롯)는 예전과 같다. isEmpty(칸)이 true면 빈 칸.
function collapseEmptySlots(container, isEmpty, label) {
  container.querySelectorAll(":scope > .slot-add").forEach((b) => b.remove());
  const cards = Array.from(container.children);
  const hidden = cards.filter(isEmpty);
  const anyFilled = hidden.length < cards.length;
  if (!anyFilled && hidden.length) hidden.shift().hidden = false; // 전부 비었으면 첫 칸은 보이게
  hidden.forEach((c) => { c.hidden = true; });
  if (!hidden.length) return;

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "secondary slot-add";
  const updateLabel = () => { btn.textContent = `+ ${label} 추가 (${hidden.length}칸 남음)`; };
  btn.addEventListener("click", () => {
    const card = hidden.shift();
    card.hidden = false;
    card.querySelector("input:not([type=file]):not(:disabled), textarea, select")?.focus({ preventScroll: true });
    if (hidden.length) updateLabel(); else btn.remove();
  });
  updateLabel();
  container.appendChild(btn);
}
