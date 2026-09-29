// report.html 스크립트 — 자동 저장. 예전엔 섹션·슬롯마다 "저장" 버튼이 수십 개라 누르는 걸 잊으면 입력이 사라졌다.
// 저장 로직은 그대로 두고(각 파일의 저장 버튼 클릭 처리), 버튼에 class="autosave"를 달아 숨긴 뒤 입력이 바뀌면 여기서 대신 누른다.
//   - 입력칸이 속한 범위 = 가장 가까운 .sub-card(슬롯 카드) 또는 .panel-body(섹션) → 그 범위에 직접 속한 autosave 버튼이 저장 담당.
//   - 글자 입력은 멈춘 뒤 1.2초, 선택·체크·토글 버튼은 0.3초 뒤 저장(연달아 바꾸면 마지막 한 번만).
//   - 사진 칸(input[type=file])은 원래 고르는 즉시 저장되므로 제외, data-no-autosave(담당요원 — 바꾸는 즉시 저장)도 제외.
//   - AI가 입력칸을 채운 경우엔 입력 이벤트가 안 나므로 각 파일에서 autosaveTouch(칸)를 부른다.
//   - 1번 현장책임자 서명은 자동 저장하지 않는다(손이 스쳐 망가진 서명이 바로 저장되면 안 됨 — signature.js의 "서명 저장").
// 저장 상태(저장 중/저장됨/실패)는 목차 줄 오른쪽 표시(report-nav.js)에 보인다. 페이지를 떠날 때 저장 대기 중이면 즉시 저장하고 경고,
// PDF 생성 전에는 autosaveFlush()로 남은 저장을 끝낸다.

const AUTOSAVE_DELAY_TYPING = 1200;
const AUTOSAVE_DELAY_CHANGE = 300;
const autosaveTimers = new Map(); // 저장 버튼 → 대기 중 타이머
let autosaveInflight = 0;
let autosaveLastSavedAt = null;
let autosaveFailed = false;

// 저장·업로드·삭제 요청(GET 이외) 진행 수를 센다. AI 분석·PDF 생성 요청은 저장이 아니라서 뺀다(수십 초 걸려 "저장 중"으로 보이면 헷갈림).
(function trackWrites() {
  const originalFetch = window.fetch.bind(window);
  window.fetch = async (input, init = {}) => {
    const method = (init.method || "GET").toUpperCase();
    const url = typeof input === "string" ? input : input.url;
    if (method === "GET" || /\/ai\/|\/render$/.test(url)) return originalFetch(input, init);
    autosaveInflight++;
    updateSaveIndicator();
    try {
      const res = await originalFetch(input, init);
      autosaveFailed = !res.ok;
      if (res.ok) autosaveLastSavedAt = new Date();
      return res;
    } catch (err) {
      autosaveFailed = true;
      throw err;
    } finally {
      autosaveInflight--;
      updateSaveIndicator();
    }
  };
})();

function autosaveScope(el) {
  return el.closest(".sub-card, .panel-body");
}

function autosaveButtonFor(el) {
  const scope = autosaveScope(el);
  if (!scope) return null;
  return Array.from(scope.querySelectorAll("button.autosave")).find((b) => autosaveScope(b) === scope) || null;
}

function scheduleAutosave(btn, delay) {
  clearTimeout(autosaveTimers.get(btn));
  autosaveTimers.set(btn, setTimeout(() => {
    autosaveTimers.delete(btn);
    btn.click();
    updateSaveIndicator();
  }, delay));
  updateSaveIndicator();
}

// 입력칸 el이 속한 범위의 저장을 예약한다(AI가 값을 채운 뒤 등 코드에서 값을 바꿨을 때도 호출).
function autosaveTouch(el, delay = AUTOSAVE_DELAY_CHANGE) {
  const btn = el && autosaveButtonFor(el);
  if (btn) scheduleAutosave(btn, delay);
}

// 대기 중인 저장을 전부 지금 실행하고, 진행 중인 저장 요청이 끝날 때까지 기다린다.
function autosaveFlushNow() {
  for (const [btn, timer] of autosaveTimers) {
    clearTimeout(timer);
    btn.click();
  }
  autosaveTimers.clear();
  updateSaveIndicator();
}

async function autosaveFlush() {
  autosaveFlushNow();
  while (autosaveInflight > 0) await new Promise((r) => setTimeout(r, 100));
}

function isAutosaveField(t) {
  return t.matches("input, select, textarea") && t.type !== "file" && !t.closest("[data-no-autosave]");
}

// 캡처 단계에서 듣는다 — 행 "삭제"처럼 원래 처리에서 요소가 문서에서 빠지면 그 뒤엔 범위를 못 찾는다.
document.addEventListener("input", (e) => {
  const t = e.target;
  if (!isAutosaveField(t)) return;
  const typing = t.matches("textarea, input:not([type=checkbox]):not([type=radio]):not([type=date])");
  autosaveTouch(t, typing ? AUTOSAVE_DELAY_TYPING : AUTOSAVE_DELAY_CHANGE);
}, true);
document.addEventListener("change", (e) => {
  if (isAutosaveField(e.target)) autosaveTouch(e.target);
}, true);
document.addEventListener("click", (e) => {
  const toggle = e.target.closest(".method-btn, .eval-btn, .pi-del");
  if (toggle) autosaveTouch(toggle);
}, true);

window.addEventListener("beforeunload", (e) => {
  if (autosaveTimers.size) autosaveFlushNow();
  if (autosaveInflight > 0) {
    e.preventDefault();
    e.returnValue = "";
  }
});

function updateSaveIndicator() {
  const el = document.getElementById("save-indicator");
  if (!el) return;
  if (autosaveTimers.size || autosaveInflight > 0) {
    el.className = "save-indicator busy";
    el.textContent = "저장 중…";
  } else if (autosaveFailed) {
    el.className = "save-indicator bad";
    el.textContent = "⚠ 저장 실패 — 맨 위 오류를 확인하세요";
  } else if (autosaveLastSavedAt) {
    const t = autosaveLastSavedAt;
    el.className = "save-indicator ok";
    el.textContent = `✓ 자동 저장됨 ${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}`;
  } else {
    el.className = "save-indicator";
    el.textContent = "입력하면 자동 저장됩니다";
  }
}
