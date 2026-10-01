// 공통 fetch 헬퍼 — 모든 API 호출은 {BASE}/api 아래이고, 세션 쿠키를 항상 같이 보낸다
// (같은 오리진에서 서빙하므로 CORS 없이도 credentials: 'include'만으로 충분하다).

// 웹판이 올라가 있는 경로(예: "/report") — 그룹웨어 https://groupware.kfsc21c.com/report/... 아래든, 사무실 LAN
// http://<IP>:8000/report/... 든 같은 코드로 동작하도록 현재 페이지 주소에서 계산한다(서버 WEB_BASE_PATH와 같은 값).
// 모든 페이지가 같은 폴더에 있으므로 화면 간 이동·css·이미지는 상대 주소, API·사진 주소는 `${BASE}/api/...`로 쓴다.
const BASE = window.location.pathname.replace(/\/[^/]*$/, "");

// "/sites"처럼 /api 없이 넘기든, "/api/..." 또는 `${BASE}/api/...`로 완성된 경로를 넘기든 한 번만 붙인다
// (예전에 /api가 두 번 붙어 /api/api/...로 조용히 404가 난 적이 있다).
function apiUrl(path) {
  if (BASE && path.startsWith(`${BASE}/api/`)) return path;
  if (path.startsWith("/api/")) return BASE + path;
  return `${BASE}/api${path}`;
}

async function api(path, options = {}) {
  const url = apiUrl(path);
  const res = await fetch(url, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (res.status === 401) {
    window.location.href = "index.html";
    throw new Error("로그인이 필요합니다.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `요청 실패 (${res.status})`);
  }
  if (res.status === 204) return null;
  return res.json();
}

function apiPost(path, data) {
  return api(path, { method: "POST", body: JSON.stringify(data ?? {}) });
}

function apiPatch(path, data) {
  return api(path, { method: "PATCH", body: JSON.stringify(data ?? {}) });
}

// 파일 업로드(multipart) — Content-Type은 브라우저가 boundary까지 붙여 정하게 비워둔다.
async function apiUpload(path, formData) {
  // 사진은 원본 그대로 올려 서버에 보관한다(사용자 결정 2026-09-29 — 고화질 원본 보관, 보고서에 넣을 때만 서버가 1400px로 줄임).
  const url = apiUrl(path);
  const res = await fetch(url, { method: "POST", credentials: "include", body: formData });
  if (res.status === 401) {
    window.location.href = "index.html";
    throw new Error("로그인이 필요합니다.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `요청 실패 (${res.status})`);
  }
  return res.json();
}

// ---------- 파일 받기 준비 창 ----------
// 한글·PDF 받기를 누르면 몇 초 아무 반응이 없다가 저장 창이 떠서 답답했음(2026-09-29 사용자) → 누르는 즉시 작은 창에
// "⟳ 한글 파일 만드는 중… N초"를 보여 주고, 준비되면 받기를 시작한 뒤 "✓ 준비됐습니다"로 바꿔 3초 뒤 닫는다.
// 쓰는 곳: <a data-download="pdf|hwpx" data-report-id="…" href="PDF 주소">. 한글은 먼저 서버에서 만들어 두고(.../hwpx/prepare) 받는다.
// 받기는 <a download>를 눌러서(페이지 이동 없음 → 보고서 화면의 "저장 안 한 내용" 경고도 안 뜸), 폰·카카오톡 브라우저도 평소 받기처럼 저장 창이 뜬다.
// onCancel을 주면 [취소] 버튼이 붙는다(한글 만들기가 오래 걸릴 때 — 2026-09-29 사용자).
function openDownloadStatus(label, onCancel) {
  const box = document.createElement("div");
  box.className = "dl-status";
  box.innerHTML = '<span class="dl-spin"></span><span class="dl-text"></span>' +
    (onCancel ? '<button type="button" class="dl-cancel">취소</button>' : "");
  document.body.appendChild(box);
  const text = box.querySelector(".dl-text");
  if (onCancel) box.querySelector(".dl-cancel").addEventListener("click", onCancel);
  const started = Date.now();
  const tick = () => { text.textContent = `${label}… ${Math.round((Date.now() - started) / 1000)}초`; };
  tick();
  const timer = setInterval(tick, 1000);
  const finish = (cls, message, ms) => {
    clearInterval(timer);
    box.classList.add(cls);
    box.querySelector(".dl-spin").remove();
    box.querySelector(".dl-cancel")?.remove();
    text.textContent = message;
    setTimeout(() => box.remove(), ms);
  };
  return {
    done: () => finish("ok", "✓ 준비됐습니다 — 저장할지 묻는 창이 뜨면 \"다운로드\"를 누르세요", 4000),
    fail: (msg) => finish("bad", `⚠ ${msg}`, 6000),
    canceled: () => finish("muted", "취소했습니다", 2000),
  };
}

async function startDownload(kind, reportId, href) {
  // 취소 — 기다리던 요청을 끊고 받기를 시작하지 않는다(서버는 시작한 한글 파일 만들기를 몇 초 안에 마저 끝내고 그냥 둔다, 보고서엔 영향 없음)
  const ctrl = new AbortController();
  let canceled = false;
  const onCancel = kind === "hwpx" ? () => { canceled = true; ctrl.abort(); status.canceled(); } : null;
  const status = openDownloadStatus(kind === "hwpx" ? "한글 파일 만드는 중" : "PDF 받는 중", onCancel);
  try {
    let url = href;
    if (kind === "hwpx") {
      const out = await api(`/reports/${reportId}/hwpx/prepare`, { signal: ctrl.signal });
      if (canceled) return;
      url = `${BASE}/api/reports/${reportId}/hwpx?token=${encodeURIComponent(out.token)}`;
    }
    const a = document.createElement("a");
    a.href = url;
    a.download = "";
    document.body.appendChild(a);
    a.click();
    a.remove();
    status.done();
  } catch (err) {
    if (canceled) return;
    status.fail(err.message || "받지 못했습니다. 다시 시도하세요.");
  }
}

document.addEventListener("click", (e) => {
  const link = e.target.closest("a[data-download]");
  if (!link) return;
  e.preventDefault();
  e.stopPropagation();
  startDownload(link.dataset.download, link.dataset.reportId, link.href);
});

function showError(el, err) {
  el.textContent = err.message || String(err);
  el.style.display = "block";
}

// ---------- 현장 [📞 전화] [📍 지도] (현장 목록·현장 화면·방문 달력, 2026-09-30) ----------
// 전화 = 현장책임자 연락처: 폰은 누르면 통화 화면, PC(마우스)는 전화를 걸 수 없어 번호를 보여 주고 누르면 복사.
// 지도 = 지도 방문 주소(없으면 현장 주소 — 서버가 map_address로 줌): PC는 네이버 지도 검색을 새 창으로, 폰은 매번 [티맵]/[네이버 지도] 선택 창.
// 둘 다 없으면 null. 현장 목록 줄은 줄 전체가 링크라 버튼을 누른 게 줄 이동으로 번지지 않게 막는다.
function siteLinkButtons(phone, mapAddress) {
  phone = (phone || "").trim();
  mapAddress = (mapAddress || "").trim();
  if (!phone && !mapAddress) return null;
  const box = document.createElement("div");
  box.className = "site-links";
  const make = (cls, icon, short, full, title, onClick) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = `site-link ${cls}`;
    b.title = title;
    b.innerHTML = `<span class="sl-ico">${icon}</span><span class="sl-short"></span><span class="sl-full"></span>`;
    b.querySelector(".sl-short").textContent = short;
    b.querySelector(".sl-full").textContent = full;
    b.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); onClick(b); });
    box.appendChild(b);
  };
  if (phone) {
    make("tel", "📞", "전화", phone, "현장책임자에게 전화(PC에선 번호 복사)", async (b) => {
      if (matchMedia("(hover: hover) and (pointer: fine)").matches) { // PC — 복사
        try {
          await navigator.clipboard.writeText(phone);
          const full = b.querySelector(".sl-full");
          full.textContent = "복사됨 ✓";
          setTimeout(() => { full.textContent = phone; }, 1500);
        } catch (_) { /* 복사가 막혀 있으면 번호가 이미 보이므로 그대로 */ }
        return;
      }
      window.location.href = `tel:${phone.replace(/[^0-9+]/g, "")}`;
    });
  }
  if (mapAddress) {
    make("map", "📍", "지도", `지도 ${mapAddress}`, `지도에서 열기: ${mapAddress}`, () => openMapChooser(mapAddress));
    // PC는 [지도]가 바로 네이버 지도라 선택 창(📋 주소 복사)이 없다 → 옆에 따로(2026-10-01 사용자). 폰은 선택 창 안에.
    if (matchMedia("(hover: hover) and (pointer: fine)").matches) {
      make("copy", "📋", "복사", "주소 복사", `주소 복사: ${mapAddress}`, async (b) => {
        const full = b.querySelector(".sl-full");
        full.textContent = (await copyText(mapAddress)) ? "복사됨 ✓" : "복사 안 됨";
        setTimeout(() => { full.textContent = "주소 복사"; }, 1500);
      });
    }
  }
  return box;
}

// ---------- 현장 진행 막대(공기 경과 vs 기술지도 수행) — 데스크톱 현장 카드와 같은 계산(서버 pace, core/site_pace.py) ----------
// 🚨 N회 부족(빨강)·✅ N회 여유(파랑)·✅ 정상·🏁 완료 + 🎯 월 N회 필요, 막대 두 줄(2026-09-30 사용자 A안). 총 횟수·공기 정보가 없으면 null.
const PACE_COLORS = { shortage: ["#dc2626", "#dc2626"], surplus: ["#2563eb", "#2563eb"], normal: ["#111827", "#4f46e5"], done: ["#2563eb", "#2563eb"] };
function sitePaceBox(pace) {
  if (!pace || !PACE_COLORS[pace.status]) return null;
  const [textColor, barColor] = PACE_COLORS[pace.status];
  const label = pace.status === "done" ? "🏁 완료" : pace.status === "shortage" ? `🚨 ${pace.diff}회 부족`
    : pace.status === "surplus" ? `✅ ${pace.diff}회 여유` : "✅ 정상";
  const extra = pace.period_over ? "기간 종료" : pace.monthly_needed != null ? `🎯 월 ${pace.monthly_needed.toFixed(1)}회 필요` : "";
  const pct = (r) => (r == null ? 0 : Math.round(r * 100));
  const box = document.createElement("div");
  box.className = "pace";
  box.innerHTML = `
    <div class="pace-status"><span class="pace-label"></span><span class="pace-extra"></span></div>
    <div class="pace-row"><span class="pace-cap">공기 경과</span><span class="pace-bar"><span class="pace-fill time"></span></span>
      <span class="pace-val"><span class="pace-num"></span><span class="pace-note"></span></span></div>
    <div class="pace-row"><span class="pace-cap">지도 수행</span><span class="pace-bar"><span class="pace-fill count"></span></span>
      <span class="pace-val"><span class="pace-num"></span><span class="pace-note"></span></span></div>`;
  const lab = box.querySelector(".pace-label");
  lab.textContent = label;
  lab.style.color = textColor;
  box.querySelector(".pace-extra").textContent = extra ? ` · ${extra}` : "";
  const [timeRow, countRow] = box.querySelectorAll(".pace-row");
  if (pace.time_ratio == null) timeRow.remove();
  else {
    timeRow.querySelector(".pace-fill").style.width = `${pct(pace.time_ratio)}%`;
    timeRow.querySelector(".pace-num").textContent = `${pct(pace.time_ratio)}%`;
    // 경과 개월/전체 공사 개월(예: 6/15개월 경과) — 시작 전이면 "시작 전"
    const months = pace.elapsed_months == null ? (pace.elapsed_text || "")
      : `${pace.elapsed_months}/${pace.total_months}개월 경과`;
    timeRow.querySelector(".pace-note").textContent = months ? ` (${months})` : "";
  }
  const fill = countRow.querySelector(".pace-fill");
  fill.style.width = `${pct(pace.count_ratio)}%`;
  fill.style.background = barColor;
  countRow.querySelector(".pace-num").textContent = `${pace.performed}`;
  countRow.querySelector(".pace-note").textContent = `/${pace.total}회`;
  return box;
}


// ---------- [📍 지도] 폰 선택 창 — 🚗 티맵 / 🗺 네이버 지도 (2026-09-30 사용자: 매번 묻기, 카카오내비는 안 넣음) ----------
// 티맵은 키 없이 "검색 방식": 주소가 검색된 채 열린다. 폰에서 직접 눌러 본 결과(tmap-test) 된 형식만 쓴다 —
//   안드로이드: intent://search?name=…#Intent;scheme=tmap;package=com.skt.tmap.ku;end (티맵이 없으면 플레이스토어로)
//   아이폰: tmap://search?name=… (티맵이 없으면 안 열림 → 잠시 뒤 화면이 그대로면 앱스토어 설치를 묻는다)
// PC(마우스)는 티맵이 없으니 묻지 않고 네이버 지도 웹을 새 창으로.
const TMAP_APPSTORE = "https://apps.apple.com/kr/app/id431589174";
function naverMapUrl(address) {
  return `https://map.naver.com/p/search/${encodeURIComponent(address)}`;
}
function openMapChooser(address) {
  const isPc = matchMedia("(hover: hover) and (pointer: fine)").matches;
  if (isPc) {
    window.open(naverMapUrl(address), "_blank", "noopener");
    return;
  }
  document.querySelector(".map-chooser")?.remove();
  const overlay = document.createElement("div");
  overlay.className = "map-chooser";
  overlay.innerHTML = `
    <div class="map-sheet" role="dialog" aria-modal="true">
      <div class="map-sheet-title">어디서 열까요?</div>
      <div class="map-sheet-addr"></div>
      <button type="button" class="map-opt tmap">🚗 티맵 <span>길안내</span></button>
      <button type="button" class="map-opt naver">🗺 네이버 지도</button>
      <button type="button" class="map-opt copy">📋 주소 복사 <span>다른 앱에 붙여 넣기</span></button>
      <button type="button" class="map-cancel">취소</button>
    </div>`;
  overlay.querySelector(".map-sheet-addr").textContent = address;
  const close = () => overlay.remove();
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  overlay.querySelector(".map-cancel").addEventListener("click", close);
  overlay.querySelector(".copy").addEventListener("click", async (e) => { // 2026-10-01 사용자 요청
    const btn = e.currentTarget;
    const ok = await copyText(address);
    btn.innerHTML = ok ? "✓ 주소를 복사했습니다" : "복사가 막혀 있습니다 — 위 주소를 길게 눌러 복사하세요";
    if (ok) setTimeout(close, 900);
  });
  overlay.querySelector(".naver").addEventListener("click", () => {
    close();
    window.open(naverMapUrl(address), "_blank", "noopener");
  });
  overlay.querySelector(".tmap").addEventListener("click", () => {
    close();
    openTmapSearch(address);
  });
  document.body.appendChild(overlay);
}
// 글자 복사 — 클립보드 API(https)가 안 되면 숨긴 입력 칸으로 한 번 더(옛 브라우저·일부 앱 안 브라우저)
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (_) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.cssText = "position:fixed;top:0;left:0;opacity:0;";
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (_) { ok = false; }
    ta.remove();
    return ok;
  }
}
function openTmapSearch(address) {
  const q = encodeURIComponent(address);
  if (/android/i.test(navigator.userAgent)) {
    window.location.href = `intent://search?name=${q}#Intent;scheme=tmap;package=com.skt.tmap.ku;end`;
    return;
  }
  // 아이폰 등 — 앱이 열리면 이 화면이 숨겨진다. 1.5초 뒤에도 보이면 티맵이 없는 것으로 보고 설치를 묻는다.
  let left = false;
  const onHide = () => { if (document.visibilityState === "hidden") left = true; };
  document.addEventListener("visibilitychange", onHide);
  window.location.href = `tmap://search?name=${q}`;
  setTimeout(() => {
    document.removeEventListener("visibilitychange", onHide);
    if (!left && document.visibilityState === "visible" &&
        confirm("티맵이 설치되어 있지 않은 것 같습니다. 앱스토어에서 티맵을 설치할까요?")) {
      window.location.href = TMAP_APPSTORE;
    }
  }, 1500);
}

