// 공통 fetch 헬퍼 — 모든 API 호출은 /api 아래이고, 세션 쿠키를 항상 같이 보낸다
// (같은 오리진에서 서빙하므로 CORS 없이도 credentials: 'include'만으로 충분하다).
async function api(path, options = {}) {
  // report.html의 여러 섹션이 "/api/reports/{id}/..." 형태의 완성된 경로를 그대로 넘기는
  // 경우와, 이 파일의 다른 곳처럼 "/sites"처럼 /api 없이 넘기는 경우가 섞여있다 — 앞에
  // /api가 이미 붙어있으면 또 붙이지 않는다(중복되면 /api/api/...가 되어 404가 난다,
  // 실제로 report.html 여러 섹션에서 이 버그로 목록 조회가 전부 실패하고 있었다).
  const url = path.startsWith("/api/") ? path : `/api${path}`;
  const res = await fetch(url, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (res.status === 401) {
    window.location.href = "/index.html";
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
  const url = path.startsWith("/api/") ? path : `/api${path}`;
  const res = await fetch(url, { method: "POST", credentials: "include", body: formData });
  if (res.status === 401) {
    window.location.href = "/index.html";
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
