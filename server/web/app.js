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
// 폰 사진은 한 장 5~20MB라 그대로 올리면 느리고, 큰 요청이 AWS 중계(nginx)에서 500으로 실패하기도 했다(2026-09-29).
// 서버는 어차피 보고서에 넣을 때 긴 변 1400px로 줄이므로(core/report_builder_hwpx_jpeg.py), 올리기 전에 브라우저에서
// 긴 변 2000px JPEG로 줄여 보낸다(한 장 0.5MB 안팎). 사진 방향(EXIF 회전)은 브라우저가 그릴 때 반영돼 똑바로 된 픽셀로 나간다.
// PNG(도장·서명 — 투명 배경)와 작은 사진은 건드리지 않고, 폰이 못 읽는 형식(일부 HEIC 등)이면 원본을 그대로 보낸다.
const UPLOAD_MAX_SIDE = 2000;
const UPLOAD_SHRINK_OVER_BYTES = 1.5 * 1024 * 1024;

async function shrinkPhotoForUpload(file) {
  if (!(file instanceof File) || !/^image\/(jpeg|jpg|heic|heif|webp)$/i.test(file.type)) return file;
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    const w = img.naturalWidth, h = img.naturalHeight;
    const ratio = Math.min(1, UPLOAD_MAX_SIDE / Math.max(w, h));
    if (ratio === 1 && file.size <= UPLOAD_SHRINK_OVER_BYTES) return file;
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(w * ratio);
    canvas.height = Math.round(h * ratio);
    canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
    if (!blob || blob.size >= file.size) return file; // 줄여도 안 작아지면 원본
    return new File([blob], file.name.replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg" });
  } catch {
    return file;
  } finally {
    URL.revokeObjectURL(url);
  }
}

async function apiUpload(path, formData) {
  const url = apiUrl(path);
  const body = new FormData();
  for (const [key, value] of formData.entries()) {
    body.append(key, value instanceof File ? await shrinkPhotoForUpload(value) : value);
  }
  const res = await fetch(url, { method: "POST", credentials: "include", body });
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
