// 위치도 카드(2026-10-21 형 옹벽 — 주소와 자리가 다름, 10/23 건축물도 — 학교 안 그 동·주소가 동까지만 맞는 곳): 시설물 정보·서류 칸에서 지도(Leaflet + OpenStreetMap, 보고서 지도와 같은 타일)에 핀을 끌어
// 옹벽 자리로 옮겨 저장(ledger.wall.lat/lng) / 밖에서 만든 위치도 그림 올리기(있으면 우선). 보고서 1.2.2·서두·과업수행계획서 위치도가 같이 바뀜.
// 서버 routers/sitok.py(/sitok/facilities/{id}/locmap…), 그림 만들기 server/sitok/locmap.py.

async function sitokDrawLocmap(el, facilityId, name) {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const url = `/sitok/facilities/${facilityId}/locmap`;
  let st;
  try { st = await api(url); } catch (e) { el.innerHTML = `<div class="mail-msg bad">${esc(e.message)}</div>`; return; }
  el.hidden = false;
  if (st.src === "address" && st.rough) st.src = "rough"; // 주소가 동까지만 맞음(10/23 양주덕산초 — 산 쪽에 핀)
  const SRC = { rough: `주소가 '${st.rough}'까지만 맞아 동 한가운데입니다 — 핀을 그 건물로 끌어 [핀 자리 저장]`, image: "올린 그림이 보고서에 들어갑니다(핀보다 우선)", pin: "저장한 핀 자리로 지도를 만듭니다", address: "아직 핀이 없어 주소 자리입니다 — 핀을 그 시설물 자리(옹벽·학교 안 그 동)로 끌어 [핀 자리 저장]", "": "주소로 자리를 못 찾았습니다 — 지도를 움직여 핀을 찍고 저장하세요" };
  el.innerHTML = `<div class="fi-card sk-locmap${st.src ? " has" : ""}">
    <div class="dt-dwg-h"><b>📍 위치도</b> <span class="sk-help">${esc(SRC[st.src] || "")}</span>
      <label class="secondary-link" title="밖에서 만든 위치도 그림(PPT 내보내기 등)">그림 올리기<input type="file" accept="image/*,application/pdf,.pdf" hidden data-kr-file="1" /></label></div>
    <div class="sk-locmap-map"></div>
    <div class="sk-locmap-foot">
      <button type="button" class="secondary btn-sm sk-pin-save">핀 자리 저장</button>
      <button type="button" class="secondary btn-sm sk-pin-addr"${st.address ? "" : " disabled"}>주소 자리로</button>
      ${st.pin ? '<button type="button" class="secondary btn-sm sk-pin-del">핀 지우기</button>' : ""}
      <a class="sk-locmap-prev" href="${BASE}/api/sitok/files/locmap/${facilityId}?v=${Date.now()}" target="_blank" rel="noopener">보고서 위치도 미리보기</a>
      ${st.has_image ? `<a href="${BASE}/api/sitok/files/locmap/${facilityId}?v=${Date.now()}" target="_blank" rel="noopener">올린 그림 보기</a><button type="button" class="link-btn sk-img-del">그림 지우기</button>` : ""}
      <span class="sk-help sk-locmap-msg"></span></div></div>`;
  const msg = el.querySelector(".sk-locmap-msg");
  enableFileDrop(el.querySelector(".sk-locmap"), el.querySelector("input[type=file]")); // 위치도 그림 끌어다 놓기(사용자 10/21)
  const center = st.pin || st.address || [37.5665, 126.978];
  const map = L.map(el.querySelector(".sk-locmap-map"), { scrollWheelZoom: false }).setView(center, st.pin || st.address ? 17 : 7);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap contributors" }).addTo(map);
  const marker = L.marker(center, { draggable: true, title: name }).addTo(map);
  marker.bindTooltip(esc(name), { permanent: true, direction: "top", offset: [-15, -8] });
  marker.on("dragend", () => { msg.textContent = "핀을 옮겼습니다 — [핀 자리 저장]을 누르면 보고서에 반영됩니다."; });
  map.on("click", (e) => { marker.setLatLng(e.latlng); msg.textContent = "핀을 옮겼습니다 — [핀 자리 저장]을 누르면 보고서에 반영됩니다."; });
  setTimeout(() => map.invalidateSize(), 300);
  el.closest("details")?.addEventListener("toggle", () => setTimeout(() => map.invalidateSize(), 50));
  const redraw = () => sitokDrawLocmap(el, facilityId, name);
  el.querySelector(".sk-pin-save").addEventListener("click", async () => {
    const p = marker.getLatLng();
    try { await api(url, { method: "PUT", body: JSON.stringify({ lat: p.lat, lng: p.lng }) }); redraw(); } catch (e) { msg.textContent = e.message; }
  });
  el.querySelector(".sk-pin-addr").addEventListener("click", () => { if (st.address) { marker.setLatLng(st.address); map.setView(st.address, 17); } });
  el.querySelector(".sk-pin-del")?.addEventListener("click", async () => {
    if (!confirm("저장한 핀을 지울까요? 주소 자리로 돌아갑니다.")) return;
    try { await api(url, { method: "DELETE" }); redraw(); } catch (e) { msg.textContent = e.message; }
  });
  el.querySelector("input[type=file]").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    msg.textContent = "올리는 중…";
    const fd = new FormData();
    fd.append("file", file);
    try { await apiUpload(`${url}/image`, fd); redraw(); } catch (err) { msg.textContent = err.message; }
  });
  el.querySelector(".sk-img-del")?.addEventListener("click", async () => {
    if (!confirm("올린 위치도 그림을 지울까요? 핀(또는 주소) 지도로 돌아갑니다.")) return;
    try { await api(`${url}/image`, { method: "DELETE" }); redraw(); } catch (e) { msg.textContent = e.message; }
  });
}
