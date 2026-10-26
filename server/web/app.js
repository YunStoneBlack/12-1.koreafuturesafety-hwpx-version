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
    const err = new Error(body.detail || `요청 실패 (${res.status})`);
    err.status = res.status; // 화면이 상태 코드로 나눠 처리(428 = 회차 종류 물음, 10/14)
    throw err;
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

// ---------- 신호 약한 곳 사진 올리기(2026-10-22 민재형 "지하 등 신호 약한 곳에서 사진이 저장되는 모습이 보이다 사라짐 — 방어 장치") ----------
// apiUploadSafe = apiUpload처럼 쓰되, 보내기 전에 사진을 폰 저장소(IndexedDB)에 먼저 넣고 서버가 받았다고 답하면 지운다. 신호 문제(끊김·시간 초과·서버 5xx)로
// 실패하면 폰에 둔 채 e.queued 오류를 던지고, 화면 아래 알림 + 신호가 돌아오면(online)·30초마다·화면을 다시 열 때 오래된 것부터 자동으로 다시 보낸다
// (화면을 닫아도 다음에 아무 화면이나 열면 이어서). 나중에 올라가면 "kf-upload-done"(detail: key·path·data) — 화면이 받아 다시 그림.
// 서버가 4xx로 거절하면(사진 아님·결함 지워짐) 다시 보내도 안 되니 알리고 지운다. key가 같으면 나중 사진으로 바꿈(같은 결함 이번 사진을 다시 찍음),
// 안 주면 한 장마다 따로. 보관 상태가 바뀌면 "kf-uploads-change"(detail: key). 저장소를 못 쓰는 브라우저(사생활 보호 창 등)는 예전 apiUpload 그대로.
const KfUploads = (() => {
  const DB = "kf-uploads", ST = "q", STALE = 6 * 60 * 1000;
  const cache = new Map(); // key → {at, state, url, label} — 화면이 바로 그릴 수 있게(사진 미리보기 주소)
  let dbp = null, bar = null, timer = null, busy = false, noteText = "", noteTimer = null;
  const open = () => (dbp ||= new Promise((ok, no) => {
    const rq = indexedDB.open(DB, 1);
    rq.onupgradeneeded = () => rq.result.createObjectStore(ST, { keyPath: "key" });
    rq.onsuccess = () => ok(rq.result);
    rq.onerror = () => no(rq.error);
  }));
  const req = async (mode, fn) => {
    const db = await open();
    return new Promise((ok, no) => {
      const t = db.transaction(ST, mode);
      const r = fn(t.objectStore(ST));
      t.oncomplete = () => ok(r ? r.result : undefined);
      t.onerror = () => no(t.error);
      t.onabort = () => no(t.error);
    });
  };
  const all = () => req("readonly", (s) => s.getAll());
  const get = (key) => req("readonly", (s) => s.get(key));
  const emit = (name, detail) => window.dispatchEvent(new CustomEvent(name, { detail }));
  function remember(it) {
    const old = cache.get(it.key);
    let url = old && old.at === it.at ? old.url : "";
    if (!url) { if (old) URL.revokeObjectURL(old.url); url = URL.createObjectURL(it.blob); }
    cache.set(it.key, { at: it.at, state: it.state, url, label: it.label || "" });
  }
  function forget(key) { const c = cache.get(key); if (c) URL.revokeObjectURL(c.url); cache.delete(key); }
  async function save(it, quiet) {
    await req("readwrite", (s) => s.put(it));
    remember(it);
    if (!quiet) emit("kf-uploads-change", { key: it.key });
    draw();
  }
  async function finish(it) { // 보낸 그 사진만 지움 — 그 사이 같은 key로 새 사진을 넣었으면 그건 남김
    const cur = await get(it.key).catch(() => null);
    if (cur && cur.at !== it.at) return false;
    await req("readwrite", (s) => s.delete(it.key));
    forget(it.key);
    draw();
    return true;
  }
  async function send(it) {
    const fd = new FormData();
    for (const [k, v] of Object.entries(it.fields || {})) fd.append(k, v);
    fd.append("file", it.blob, it.name || "photo.jpg");
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), Math.min(300000, Math.max(60000, (it.blob.size || 0) / 20))); // 약 20KB/초 기준, 1~5분
    try {
      const res = await fetch(apiUrl(it.path), { method: "POST", credentials: "include", body: fd, signal: ctl.signal });
      if (res.status === 401) return { retry: true, login: true, error: "로그인이 풀렸습니다" };
      if (res.ok) return { ok: true, data: await res.json().catch(() => null) };
      const body = await res.json().catch(() => ({}));
      return { retry: res.status >= 500 || res.status === 408 || res.status === 429, error: body.detail || `요청 실패 (${res.status})` };
    } catch (e) {
      return { retry: true, error: "신호가 약하거나 끊겼습니다" };
    } finally { clearTimeout(t); }
  }
  async function runOnce() {
    const items = (await all()).sort((a, b) => a.at - b.at);
    for (const it of items) {
      if ((it.state === "first" || it.state === "sending") && Date.now() - (it.sent || 0) < STALE) continue; // 다른 곳(처음 보내기·다른 창)이 보내는 중
      Object.assign(it, { state: "sending", sent: Date.now(), tries: (it.tries || 0) + 1 });
      await save(it);
      const r = await send(it);
      if (r.ok) {
        if (await finish(it)) emit("kf-upload-done", { key: it.key, path: it.path, data: r.data });
        continue;
      }
      if (!r.retry) {
        if (await finish(it)) { emit("kf-uploads-change", { key: it.key }); note(`${it.label || "사진"} — 서버가 받지 않아 보관을 지웠습니다: ${r.error}`); }
        continue;
      }
      const cur = await get(it.key).catch(() => null);
      if (!cur || cur.at === it.at) { Object.assign(it, { state: "failed", error: r.error }); await save(it); }
      break; // 신호가 안 좋으면 다음 것도 안 됨 — 다음 차례에
    }
  }
  async function run() {
    if (busy || !cache.size) return;
    busy = true;
    draw();
    try {
      if (navigator.locks) await navigator.locks.request("kf-uploads", { ifAvailable: true }, async (lock) => { if (lock) await runOnce(); }); // 창이 여럿이어도 한 곳만
      else await runOnce();
    } catch (e) { /* 저장소 오류 — 다음 차례에 */ }
    busy = false;
    draw();
    later();
  }
  function later() { clearTimeout(timer); if (cache.size) timer = setTimeout(run, 30000); }
  function note(text) { noteText = text; clearTimeout(noteTimer); noteTimer = setTimeout(() => { noteText = ""; draw(); }, 9000); draw(); }
  function draw() {
    const wait = [...cache.values()].filter((c) => c.state !== "first").length;
    if (!bar) {
      if ((!wait && !noteText) || !document.body) return;
      bar = document.createElement("div");
      bar.className = "kf-up-bar";
      bar.innerHTML = '<span class="kf-up-txt"></span><button type="button" class="kf-up-go">지금 다시 보내기</button><span class="kf-up-note"></span>';
      bar.querySelector(".kf-up-go").addEventListener("click", () => { if (!navigator.onLine) note("아직 신호가 없습니다 — 신호가 잡히면 자동으로 보냅니다."); run(); });
      document.body.appendChild(bar);
    }
    bar.hidden = !wait && !noteText;
    bar.querySelector(".kf-up-txt").textContent = !wait ? "" : busy ? `⬆ 폰에 보관한 사진 다시 보내는 중… (${wait}장)`
      : `📶 아직 못 올린 사진 ${wait}장 — 폰에 보관 중, 신호가 돌아오면 자동으로 올립니다`;
    bar.querySelector(".kf-up-go").hidden = !wait || busy;
    bar.querySelector(".kf-up-note").textContent = noteText;
  }
  function start() {
    if (typeof indexedDB === "undefined") return;
    all().then((items) => {
      items.forEach((it) => { remember(it); emit("kf-uploads-change", { key: it.key }); });
      draw();
      if (items.length) setTimeout(run, 1500);
    }).catch(() => {});
    window.addEventListener("online", () => run());
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") run(); });
  }
  start();
  return { save, send, finish, later, note, run, peek: (key) => cache.get(key) || null };
})();

async function apiUploadSafe(path, formData, { key = "", label = "", queueOnly = false } = {}) {
  const file = formData.get("file");
  if (!(file instanceof Blob) || typeof indexedDB === "undefined") return apiUpload(path, formData);
  const fields = {};
  for (const [k, v] of formData.entries()) if (k !== "file" && typeof v === "string") fields[k] = v;
  let blob;
  try { blob = new Blob([await file.arrayBuffer()], { type: file.type || "image/jpeg" }); } catch (e) { return apiUpload(path, formData); } // 찍은 사진을 바로 폰 저장소로 복사
  const it = { key: key || `${path}#${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, path, fields, blob, name: file.name || "photo.jpg", label,
    at: Date.now(), sent: Date.now(), tries: queueOnly ? 0 : 1, state: queueOnly ? "failed" : "first", error: "" };
  try { await KfUploads.save(it); } catch (e) { return apiUpload(path, formData); }
  const queued = () => {
    KfUploads.later();
    const e = new Error("📶 신호가 약해 사진을 폰에 보관했습니다 — 신호가 돌아오면 자동으로 올립니다(화면을 닫아도 다음에 열면 이어서).");
    e.queued = true;
    return e;
  };
  if (queueOnly) throw queued();
  const r = await KfUploads.send(it);
  if (r.ok) { await KfUploads.finish(it); return r.data; }
  if (r.login) { window.location.href = "index.html"; throw new Error("로그인이 필요합니다."); }
  if (!r.retry) { if (await KfUploads.finish(it)) window.dispatchEvent(new CustomEvent("kf-uploads-change", { detail: { key: it.key } })); throw new Error(r.error); }
  it.state = "failed";
  it.error = r.error;
  await KfUploads.save(it);
  throw queued();
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

// ---------- 끌어다 놓기(2026-10-06 사용자: 계약서·서류·사진 올리는 곳은 전부) ----------
// zone에 파일을 끌어다 놓으면 input에 넣고 change를 일으킨다 — "파일 선택"으로 고른 것과 똑같이 처리됨.
// accept에 안 맞는 파일은 빼고, multiple이 아니면 첫 파일만. 놓는 중엔 zone에 .drop-over(파란 점선, style.css).
// shell.js의 보고서 파일·사진 칸, signature.js 서명 칸은 각자 같은 방식으로 이미 됨 — 여기는 서류 자동화·K2B 첨부 등 나머지.
function fileAccepts(input, file) {
  const accept = (input.accept || "").trim();
  if (!accept) return true;
  const name = file.name.toLowerCase();
  return accept.split(",").some((a) => {
    a = a.trim().toLowerCase();
    if (!a) return false;
    if (a.startsWith(".")) return name.endsWith(a);
    if (a.endsWith("/*")) return (file.type || "").startsWith(a.slice(0, -1));
    return file.type === a;
  });
}

// 층만 보기 단추 줄(10/25 민재형 — 내진 현장조사 부재 단면·철근탐사가 폰에서 길어) — [전체 보기] [지상1층 2/9] …, 다 채운 층은 done(초록 숫자).
// list = [{n, label, done, total}](total 0인 층은 뺌), cur = 고른 층(문자열, ""= 전체). 단추마다 data-mf, 숫자 칸 data-fcc(그 자리에서 숫자만 고칠 때). CSS = css/sitok.css .sf2-fchips
function floorChips(list, cur) {
  const h = (x) => String(x ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  return `<div class="sf2-fchips"><button type="button" class="${cur ? "" : "on"}" data-mf="">전체 보기</button>${list.filter((x) => x.total).map((x) =>
    `<button type="button" class="${String(x.n) === cur ? "on" : ""}${x.done >= x.total ? " done" : ""}" data-mf="${x.n}">${h(x.label)} <small data-fcc="${x.n}">${x.done}/${x.total}</small></button>`).join("")}</div>`;
}

// 검색해서 고르기(10/22 — 내진성능평가 일람표 칸: 철근탐사·부재 단면) — 숨긴 <select> 위에 글 칸 + 목록. 누르면 전체(지금 칸 굵게), 치면 낱말마다
// (빈칸·대소문자 무시) 다 들어간 칸만, 방향키·Enter·누르기로 고르면 select 값을 바꾸고 change(저장은 원래 select 그대로). Esc·바깥 = 원래 값.
// 고를 칸이 없으면(첫 "고르기" 칸뿐) 그냥 select. select의 style(flex 등)은 감싼 칸으로 옮김. CSS = css/sitok.css .search-sel
// 폰(터치 화면, 10/25 사용자 "검색창 키보드와 선택 리스트가 간섭으로 불편"): 칸을 누르면 목록만(키보드 안 뜸 — readonly), 목록 창 맨 위 검색칸·[🔍]를 누르면
// 키보드로 검색, 키보드 [검색]·[완료]면 키보드가 내려가고 걸러진 목록만 → 눌러서 고름. 검색어는 남아 다시 🔍·검색칸으로 이어서(민재형 "다시 눌러도 키보드").
// 검색칸은 늘 쓸 수 있는 진짜 칸 — 칸의 readonly를 풀고 코드로 focus하던 처음 방식은 아이폰에서 두 번째부터 키보드가 안 떴음. 바깥을 누르면 닫힘. PC는 예전처럼 바로 쳐서 검색.
function searchSelect(sel, { placeholder = "" } = {}) {
  const opts = [...sel.options].map((o) => ({ v: o.value, t: o.textContent }));
  if (opts.length < 2) return null;
  const h = (x) => String(x ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const norm = (x) => String(x || "").toLowerCase().replace(/\s+/g, "");
  const cur = () => opts.find((o) => o.v && o.v === sel.value);
  const touch = !!window.matchMedia?.("(pointer: coarse)").matches;
  const box = document.createElement("div");
  box.className = `search-sel${touch ? " touch" : ""}`;
  box.style.cssText = sel.style.cssText;
  const ph = h(placeholder || `${opts[0].t} — 검색`);
  box.innerHTML = touch
    ? `<input type="text" class="search-sel-in" readonly inputmode="none" placeholder="${ph}" title="${h(sel.title)}" />
      <button type="button" class="search-sel-find" aria-label="검색" title="검색어로 찾기">🔍</button>
      <div class="search-sel-pop" hidden><input type="search" class="search-sel-q" autocomplete="off" spellcheck="false" enterkeyhint="search" placeholder="🔍 검색어 — 눌러서 치기" />
        <div class="search-sel-list"></div></div>`
    : `<input type="text" class="search-sel-in" autocomplete="off" spellcheck="false" placeholder="${ph}" title="${h(sel.title)}" />
      <div class="search-sel-list" hidden></div>`;
  sel.hidden = true;
  sel.after(box);
  const inp = box.querySelector(".search-sel-in"), list = box.querySelector(".search-sel-list");
  const pop = touch ? box.querySelector(".search-sel-pop") : list; // 열고 닫는 칸(폰 = 검색칸 + 목록)
  const q = touch ? box.querySelector(".search-sel-q") : inp; // 검색어 치는 칸(PC = 글 칸 자체)
  inp.value = cur()?.t || "";
  let shown = [], on = 0;
  const paint = () => {
    list.innerHTML = shown.length ? shown.map((o, k) => `<div data-k="${k}" class="${k === on ? "on" : ""}${o.v && o.v === sel.value ? " sel" : ""}">${o.v
      ? h(o.t).replace("⚠미확인", "<em>⚠미확인</em>") : '<span class="none">— 선택 안 함 —</span>'}</div>`).join("") : '<div class="none">맞는 칸 없음</div>';
    list.querySelector(".on")?.scrollIntoView({ block: "nearest" });
  };
  const open = (text) => {
    const words = String(text || "").trim().split(/\s+/).map(norm).filter(Boolean);
    shown = words.length ? opts.filter((o) => o.v && words.every((w) => norm(o.t).includes(w))) : opts;
    on = words.length ? 0 : Math.max(0, shown.findIndex((o) => o.v && o.v === sel.value));
    pop.hidden = false;
    paint();
  };
  const close = () => {
    pop.hidden = true;
    inp.value = cur()?.t || "";
    if (touch) { q.value = ""; q.blur(); }
  };
  box._close = close;
  box._open = () => !pop.hidden;
  const pick = (o) => {
    if (!o) { close(); return; }
    if (o.v !== sel.value) { sel.value = o.v; sel.dispatchEvent(new Event("change")); }
    close();
  };
  if (touch) {
    // 칸 = 목록 열기(키보드 안 뜸), 🔍·검색칸 = 키보드(늘 쓸 수 있는 진짜 칸이라 몇 번이고 뜸), 키보드 [검색]·[완료] = 키보드만 내리고 걸러진 목록 그대로
    inp.addEventListener("click", () => { if (pop.hidden) { open(""); pop.scrollIntoView({ block: "nearest" }); } else close(); });
    box.querySelector(".search-sel-find").addEventListener("click", () => {
      if (pop.hidden) open(q.value);
      q.focus(); // 아이폰 — 누른 그 순간(같은 처리 안)에 부르면 키보드가 뜸, 안 떠도 검색칸이 바로 위에 보여 눌러 칠 수 있음
      const n = q.value.length;
      try { q.setSelectionRange(n, n); } catch (_) { /* search 칸이 막는 브라우저 */ }
    });
    q.addEventListener("input", () => open(q.value));
    q.addEventListener("keydown", (e) => {
      if (e.isComposing) return;
      if (e.key === "Enter") { e.preventDefault(); q.blur(); open(q.value); } // 검색어는 남김(다시 🔍·검색칸 누르면 이어서 고침)
      else if (e.key === "Escape") close();
    });
  } else {
    inp.addEventListener("focus", () => { inp.select(); open(""); });
    inp.addEventListener("input", () => open(inp.value));
    inp.addEventListener("keydown", (e) => {
      if (e.isComposing) return;
      if (pop.hidden && (e.key === "ArrowDown" || e.key === "Enter")) { e.preventDefault(); open(""); return; }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        on = (on + (e.key === "ArrowDown" ? 1 : -1) + shown.length) % Math.max(1, shown.length);
        paint();
      } else if (e.key === "Enter") { e.preventDefault(); pick(shown[on]); inp.blur(); }
      else if (e.key === "Escape") { close(); inp.blur(); }
    });
    inp.addEventListener("blur", () => setTimeout(() => { if (!pop.hidden) close(); }, 150));
  }
  list.addEventListener("mousedown", (e) => {
    e.preventDefault(); // 글 칸 포커스를 잃기 전에 고름
    const it = e.target.closest("[data-k]");
    if (it) { pick(shown[Number(it.dataset.k)]); inp.blur(); }
  });
  return box;
}
// 폰: 검색 고르기 목록 바깥을 누르면 닫힘(PC는 글 칸 blur로 닫힘)
document.addEventListener("pointerdown", (e) => {
  document.querySelectorAll(".search-sel.touch").forEach((box) => {
    if (!box.contains(e.target) && box._open?.()) box._close?.();
  });
}, true);

// input은 칸 자체 또는 "지금 칸을 찾아 주는 함수"(창을 다시 그려 칸이 바뀌는 곳 — 착수계 창 전체)
function enableFileDrop(zone, input) {
  if (!zone || !input || zone.dataset.dropOn) return;
  const getInput = typeof input === "function" ? input : () => input;
  zone.dataset.dropOn = "1";
  const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes("Files");
  zone.addEventListener("dragover", (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    e.stopPropagation();
    zone.classList.add("drop-over");
  });
  zone.addEventListener("dragleave", (e) => {
    if (!zone.contains(e.relatedTarget)) zone.classList.remove("drop-over");
  });
  zone.addEventListener("drop", (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    e.stopPropagation();
    zone.classList.remove("drop-over");
    const input = getInput();
    if (!input) return;
    const files = [...e.dataTransfer.files].filter((f) => fileAccepts(input, f));
    if (!files.length) {
      alert("이 칸에 맞는 파일 형식이 아닙니다.");
      return;
    }
    const dt = new DataTransfer();
    (input.multiple ? files : files.slice(0, 1)).forEach((f) => dt.items.add(f));
    input.files = dt.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

// 놓을 수 없는 곳에 파일을 떨어뜨려도 브라우저가 그 파일을 열어 화면을 떠나지 않게(놓는 칸은 각자 먼저 처리함)
document.addEventListener("dragover", (e) => { if ([...(e.dataTransfer?.types || [])].includes("Files")) e.preventDefault(); });
document.addEventListener("drop", (e) => { if ([...(e.dataTransfer?.types || [])].includes("Files")) e.preventDefault(); });
// 놓기가 끝나면(어느 칸에 놓았든·끌다 말았든) 화면의 "받는 중" 표시를 전부 지움 — 안쪽 칸이 놓기를 받으면(stopPropagation) 바깥 칸(완수계 창 전체)엔
// 신호가 안 가서 .drop-over가 남아 창이 반투명해졌음(10/8 형). 붙잡기 단계(capture)라 안쪽 칸이 막아도 먼저 들어옴.
function clearDropMarks() { document.querySelectorAll(".drop-over").forEach((el) => el.classList.remove("drop-over")); }
window.addEventListener("drop", () => setTimeout(clearDropMarks, 0), true);
window.addEventListener("dragend", clearDropMarks, true);
document.addEventListener("dragleave", (e) => { if (!e.relatedTarget) clearDropMarks(); }, true); // 창 밖으로 끌고 나감

function showError(el, err) {
  el.textContent = err.message || String(err);
  el.style.display = "block";
}

// ---------- 현장 [📞 전화] [📍 지도] (현장 목록·현장 화면·방문 달력, 2026-09-30) ----------
// 전화 = 현장책임자 연락처: 폰은 누르면 통화 화면, PC(마우스)는 전화를 걸 수 없어 번호를 보여 주고 누르면 복사.
// 지도 = 지도 방문 주소(없으면 현장 주소 — 서버가 map_address로 줌): PC는 네이버 지도 검색을 새 창으로, 폰은 매번 [티맵]/[네이버 지도] 선택 창.
// 둘 다 없으면 null. 현장 목록 줄은 줄 전체가 링크라 버튼을 누른 게 줄 이동으로 번지지 않게 막는다.
// 마우스로 쓰는 PC인지(폰·태블릿 아님) — 전화는 복사, 지도는 바로 네이버, 동선 창 내비 버튼 숨김 등을 가른다
const isMousePc = () => matchMedia("(hover: hover) and (pointer: fine)").matches;

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
      if (isMousePc()) { // PC — 복사
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
    if (isMousePc()) {
      make("copy", "📋", "복사", "주소 복사", `주소 복사: ${mapAddress}`, async (b) => {
        const full = b.querySelector(".sl-full");
        full.textContent = (await copyText(mapAddress)) ? "복사됨 ✓" : "복사 안 됨";
        setTimeout(() => { full.textContent = "주소 복사"; }, 1500);
      });
    }
  }
  return box;
}

// ---------- 공사 상태 4칸(2026-10-01 사용자) — 착공전·진행중·공사중지·준공 중 하나만 불이 켜짐, 누르면 바로 저장 ----------
// 진행중만 지도 출장 배치(server/api/site_status.py). 진행중이 아니게 되면 앞으로의 방문 예정(📌 포함)을 지울지 묻고 지움,
// 진행중이 되면 지도 일정 자동 배치를 물어 미리보기 창(js/auto-plan.js openAutoPlan). onChanged(새 상태)는 저장 뒤 화면 새로고침용.
const SITE_STATUSES = ["착공전", "진행중", "공사중지", "준공"];
function siteStatusSwitch(site, onChanged) {
  const box = document.createElement("div");
  box.className = "st-switch";
  box.setAttribute("role", "group");
  box.setAttribute("aria-label", "공사 상태");
  const draw = () => {
    box.querySelectorAll("button").forEach((b) => {
      const on = b.dataset.s === site.status;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on);
    });
  };
  for (const s of SITE_STATUSES) {
    const b = document.createElement("button");
    b.type = "button";
    b.dataset.s = s;
    b.textContent = s;
    b.addEventListener("click", async (e) => {
      e.preventDefault(); // 현장 목록 줄은 링크라 — 현장 화면으로 넘어가지 않게
      e.stopPropagation();
      if (s === site.status) return;
      box.classList.add("busy");
      try {
        // 실수로 누르는 것 막기 — 항상 "A → B" 한 번 묻는다(2026-10-01 사용자). 지울 예정이 있으면 같은 창에 함께 알린다.
        const jong = (w) => (w.charCodeAt(w.length - 1) - 0xAC00) % 28; // 마지막 글자 받침(0 = 없음, 8 = ㄹ)
        let question = `${site.status || "진행중"} → ${s}${jong(s) && jong(s) !== 8 ? "으로" : "로"} 바꾸시겠습니까?`;
        if (s !== "진행중") {
          const dry = await apiPost(`/sites/${site.id}/status`, { status: s, dry_run: true });
          if (dry.plans) question += `\n\n${s}${jong(s) ? "은" : "는"} 지도 출장을 배치하지 않아서 앞으로의 방문 예정 ${dry.plans}건(📌 고정 포함)도 지웁니다.`;
        }
        if (!confirm(question)) return;
        await apiPost(`/sites/${site.id}/status`, { status: s });
        site.status = s;
        draw();
        if (onChanged) onChanged(s);
        if (s === "진행중" && typeof openAutoPlan === "function" && site.total_guidance_count && site.period_end &&
            confirm("진행중으로 바꿨습니다. 이 현장의 지도 일정을 자동으로 넣을까요?\n(넣기 전에 미리 보여 줍니다)")) {
          openAutoPlan({ siteId: site.id }, siteLabel(site), () => { if (onChanged) onChanged(s); });
        }
      } catch (err) {
        alert(`상태를 바꾸지 못했습니다: ${err.message}`);
      } finally {
        box.classList.remove("busy");
      }
    });
    box.appendChild(b);
  }
  draw();
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
    if (pace.period_start) timeRow.title = `${pace.period_src} ${pace.period_start} ~ ${pace.period_end}`; // 공기 경과 = 우리 계약기간(10/20)
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
// "(으)로" — 받침이 있으면 "으로"(ㄹ 받침은 "로"): 기둥으로·보로·벽체로·접합부로
function withRo(word) {
  const c = String(word || "").charCodeAt(String(word || "").length - 1) - 0xac00;
  const jong = c >= 0 && c < 11172 ? c % 28 : 0;
  return `${word}${jong === 0 || jong === 8 ? "로" : "으로"}`;
}

// 고르기 창(10/26 내진 칸 수 표) — pickSheet({title, sub, options: [{v, label, note, disabled}]}) → 고른 v, 취소·바깥·Esc = null. PC 가운데, 폰 아래에서.
function pickSheet({ title = "", sub = "", options = [] } = {}) {
  return new Promise((resolve) => {
    document.querySelector(".pick-sheet-bg")?.remove();
    const bg = document.createElement("div");
    bg.className = "pick-sheet-bg";
    bg.innerHTML = `<div class="pick-sheet" role="dialog" aria-modal="true"><div class="pick-sheet-title"></div><div class="pick-sheet-sub"></div>
      ${options.map((o, i) => `<button type="button" class="pick-opt" data-i="${i}"${o.disabled ? " disabled" : ""}><b></b><span></span></button>`).join("")}
      <button type="button" class="pick-cancel">취소</button></div>`;
    bg.querySelector(".pick-sheet-title").textContent = title;
    bg.querySelector(".pick-sheet-sub").textContent = sub;
    bg.querySelectorAll(".pick-opt").forEach((b) => { const o = options[b.dataset.i]; b.querySelector("b").textContent = o.label; b.querySelector("span").textContent = o.note || ""; });
    const key = (e) => { if (e.key === "Escape") done(null); };
    const done = (v) => { bg.remove(); document.removeEventListener("keydown", key); resolve(v); };
    bg.addEventListener("click", (e) => { if (e.target === bg) done(null); });
    bg.querySelector(".pick-cancel").addEventListener("click", () => done(null));
    bg.querySelectorAll(".pick-opt").forEach((b) => b.addEventListener("click", () => done(options[b.dataset.i].v)));
    document.addEventListener("keydown", key);
    document.body.appendChild(bg);
    bg.querySelector(".pick-opt:not([disabled])")?.focus();
  });
}

function naverMapUrl(address) {
  return `https://map.naver.com/p/search/${encodeURIComponent(address)}`;
}
function openMapChooser(address) {
  if (isMousePc()) {
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
// 화면에 보이는 현장 이름 앞 관리번호(2026-10-01 사용자) — "26-12)_고모지구 …". 서버 server/api/site_label.py와 같은 규칙:
// "연도-숫자"면 연도 뒤 두 자리·숫자 앞 0 빼기(2026-0000046 → 26-46), 그 밖(26-M5)은 그대로, 없으면 이름만.
function shortMgmt(no) {
  const m = String(no || "").trim();
  const found = m.match(/^(\d{2}|\d{4})-0*(\d+)$/);
  return found ? `${found[1].slice(-2)}-${found[2]}` : m;
}
function siteLabel(site) {
  const short = shortMgmt(site?.management_no);
  return short ? `${short})_${site.name}` : site?.name || "";
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

