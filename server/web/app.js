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

function showError(el, err) {
  el.textContent = err.message || String(err);
  el.style.display = "block";
}
