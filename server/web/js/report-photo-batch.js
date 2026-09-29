// report.html 스크립트 — 3번 전경·점검사진 "여러 장 한 번에 올리기"(2026-09-30 사용자 요청, 8번 지적사항엔 안 붙임).
// 갤러리에서 여러 장 고르기 → 번호 붙은 미리보기 창(처음 순서 = 찍은 시간순) → 끌어서 순서 바꾸기 → [이대로 넣기]로 빈칸에 차례로.
// 폰 사진 선택 화면이 "고른 순서"를 페이지에 그대로 넘겨 준다는 보장이 없어서(iOS·안드로이드 제각각) 순서는 이 창에서 눈으로 맞춘다.
// 실제 업로드는 칸 하나 올리기와 같은 API(`.../{slot}`)를 한 장씩 차례로 부른다 — 서버 수정 없음.
// setupPhotoSlots(report-photos.js)가 addBatchPhotoButton()을 부른다. 여기엔 정의만 둔다.

// 버튼을 칸 목록 위에 붙인다. slots: { getEmptySlots() → 빈 슬롯 번호 배열, upload(slot, file) → 성공 여부 Promise, afterBatch() }
function addBatchPhotoButton(container, labelPrefix, slots) {
  const bar = document.createElement("div");
  bar.className = "batch-bar";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "secondary batch-btn";
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/*";
  input.multiple = true;
  input.style.display = "none"; // shell.js enhanceFileInputs가 "사진 선택" 버튼을 또 붙이지 않게
  bar.append(btn, input);
  container.before(bar);

  const refresh = () => {
    const free = slots.getEmptySlots().length;
    btn.disabled = free === 0;
    btn.textContent = free ? `📷 ${labelPrefix} 여러 장 올리기 (빈칸 ${free}개)` : `${labelPrefix} 칸이 모두 찼습니다`;
  };
  btn.addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    const files = [...input.files].filter((f) => f.type.startsWith("image/") || /\.(jpe?g|png|webp|gif)$/i.test(f.name));
    input.value = "";
    if (files.length) openBatchPhotoModal(labelPrefix, files, slots, refresh);
  });
  refresh();
  return refresh;
}

async function openBatchPhotoModal(labelPrefix, files, slots, refresh) {
  const times = await Promise.all(files.map(photoTakenTime));
  let items = files
    .map((file, i) => ({ file, time: times[i], url: URL.createObjectURL(file) }))
    .sort((a, b) => a.time - b.time);

  const overlay = document.createElement("div");
  overlay.className = "sig-modal-overlay";
  overlay.innerHTML = `
    <div class="sig-modal batch-modal" role="dialog" aria-modal="true">
      <div class="sig-modal-head">
        <b></b>
        <span class="sig-modal-hint batch-hint"></span>
      </div>
      <div class="batch-info"></div>
      <div class="batch-grid"></div>
      <div class="sig-modal-status batch-status"></div>
      <div class="sig-modal-actions">
        <div class="sig-modal-foot">
          <button type="button" class="batch-cancel">취소</button>
          <button type="button" class="batch-go primary"></button>
        </div>
      </div>
    </div>`;
  overlay.querySelector(".sig-modal-head b").textContent = `${labelPrefix} 여러 장 올리기`;
  overlay.querySelector(".batch-hint").textContent = matchMedia("(hover: none)").matches
    ? "사진을 살짝 길게 누른 채 끌면 순서가 바뀝니다."
    : "사진을 끌어서 순서를 바꿀 수 있습니다.";
  document.body.appendChild(overlay);
  const prevOverflow = document.documentElement.style.overflow;
  document.documentElement.style.overflow = "hidden";

  const grid = overlay.querySelector(".batch-grid");
  const info = overlay.querySelector(".batch-info");
  const statusEl = overlay.querySelector(".batch-status");
  const goBtn = overlay.querySelector(".batch-go");
  const cancelBtn = overlay.querySelector(".batch-cancel");
  let busy = false;

  const close = () => {
    items.forEach((it) => URL.revokeObjectURL(it.url));
    overlay.remove();
    document.documentElement.style.overflow = prevOverflow;
  };

  const render = () => {
    const free = slots.getEmptySlots();
    grid.innerHTML = "";
    items.forEach((it, i) => {
      const tile = document.createElement("div");
      tile.className = "batch-tile" + (i >= free.length ? " no-room" : "");
      tile.dataset.index = i;
      tile.title = it.file.name;
      tile.style.backgroundImage = `url("${it.url}")`;
      tile.innerHTML = `<span class="batch-no"></span><button type="button" class="batch-x" aria-label="빼기">×</button>` +
        (i >= free.length ? '<span class="batch-noroom">칸 없음</span>' : "");
      tile.querySelector(".batch-no").textContent = i + 1;
      tile.querySelector(".batch-x").addEventListener("click", (e) => {
        e.stopPropagation();
        if (busy) return;
        URL.revokeObjectURL(it.url);
        items.splice(i, 1);
        if (!items.length) close(); else render();
      });
      attachTileDrag(tile, grid, () => busy, (from, to) => {
        const [moved] = items.splice(from, 1);
        items.splice(to, 0, moved);
        render();
      });
      grid.appendChild(tile);
    });
    const fit = Math.min(items.length, free.length);
    const over = items.length - fit;
    info.textContent = `${items.length}장 골랐습니다 · 빈칸 ${free.length}개(${free.map((s) => `${labelPrefix} ${s}`).join(", ")})` +
      (over ? ` — 뒤의 ${over}장은 넣을 칸이 없어요. 순서를 바꾸거나 ×로 빼세요.` : "");
    info.classList.toggle("warn", over > 0);
    goBtn.textContent = `이대로 넣기 (${fit}장)`;
    goBtn.disabled = fit === 0;
  };

  cancelBtn.addEventListener("click", () => { if (!busy) close(); });
  overlay.addEventListener("click", (e) => { if (e.target === overlay && !busy) close(); });

  goBtn.addEventListener("click", async () => {
    const free = slots.getEmptySlots();
    const plan = items.slice(0, free.length).map((it, i) => ({ ...it, slot: free[i] }));
    if (!plan.length) return;
    busy = true;
    goBtn.disabled = cancelBtn.disabled = true;
    overlay.classList.add("batch-busy");
    statusEl.style.color = "var(--warn)";
    let failed = 0;
    for (let i = 0; i < plan.length; i++) {
      statusEl.textContent = `${i + 1}/${plan.length} 올리는 중…`;
      grid.children[i]?.classList.add("sending");
      const ok = await slots.upload(plan[i].slot, plan[i].file);
      grid.children[i]?.classList.remove("sending");
      grid.children[i]?.classList.add(ok ? "sent" : "failed");
      if (!ok) failed++;
    }
    slots.afterBatch();
    refresh();
    if (failed) {
      // 실패한 칸엔 칸 안에 "⚠ 실패 + 다시 시도"가 떠 있다(uploadWithStatus) — 창은 닫아서 그 칸을 보게 한다.
      alert(`${plan.length - failed}장 넣었고 ${failed}장은 못 올렸습니다. 빨간 표시가 있는 칸에서 [다시 시도]를 누르세요.`);
    }
    close();
  });

  render();
}

// 끌어서 순서 바꾸기 — 마우스는 바로, 손가락은 살짝 길게(0.3초) 누른 뒤부터 끈다(짧게 스치면 창 스크롤로 둔다).
// 끄는 동안 사진 복사본이 손가락을 따라오고, 원래 자리는 점선 칸으로 남아 놓을 자리로 옮겨 다닌다. 놓으면 onMove(from, to).
function attachTileDrag(tile, grid, isBusy, onMove) {
  let pressTimer = null, start = null, drag = null;

  const cancelPress = () => { clearTimeout(pressTimer); pressTimer = null; };

  const begin = (x, y) => {
    const rect = tile.getBoundingClientRect();
    const ghost = tile.cloneNode(true);
    ghost.classList.add("batch-ghost");
    ghost.style.width = `${rect.width}px`;
    ghost.style.height = `${rect.height}px`;
    document.body.appendChild(ghost);
    drag = { ghost, dx: x - rect.left, dy: y - rect.top, from: Number(tile.dataset.index) };
    tile.classList.add("placeholder");
    moveGhost(x, y);
    if (navigator.vibrate) navigator.vibrate(15);
  };

  const moveGhost = (x, y) => {
    drag.ghost.style.transform = `translate(${x - drag.dx}px, ${y - drag.dy}px)`;
    const over = document.elementFromPoint(x, y)?.closest(".batch-tile");
    if (!over || over === tile || over.parentElement !== grid) return;
    const tiles = [...grid.children];
    const overIdx = tiles.indexOf(over);
    const myIdx = tiles.indexOf(tile);
    grid.insertBefore(tile, overIdx > myIdx ? over.nextSibling : over);
  };

  const finish = () => {
    cancelPress();
    if (!drag) return;
    drag.ghost.remove();
    tile.classList.remove("placeholder");
    const to = [...grid.children].indexOf(tile);
    const from = drag.from;
    drag = null;
    onMove(from, to); // 다시 그려서 번호·"칸 없음" 표시를 새 순서로 맞춘다(제자리여도 같은 모양)
  };

  // 누른 뒤 움직임·손 떼기는 window에서 받는다 — 끄는 중에 칸 자리를 옮기면(insertBefore) 마우스 붙잡기(pointer capture)가
  // 풀려 칸에 달린 이벤트가 끊겼다(2026-09-30 시험: PC에서 한 칸만 움직이고 멈춤).
  const onMoveEv = (e) => {
    if (!start || e.pointerId !== start.id) return;
    if (drag) { moveGhost(e.clientX, e.clientY); return; }
    const moved = Math.hypot(e.clientX - start.x, e.clientY - start.y);
    if (start.touch) {
      if (moved > 8) end(false); // 길게 누르기 전에 움직였으면 스크롤
    } else if (moved > 4) {
      begin(start.x, start.y);
      moveGhost(e.clientX, e.clientY);
    }
  };
  const onUpEv = (e) => { if (start && e.pointerId === start.id) end(true); };
  const end = (drop) => {
    start = null;
    window.removeEventListener("pointermove", onMoveEv);
    window.removeEventListener("pointerup", onUpEv);
    window.removeEventListener("pointercancel", onUpEv);
    if (drop) finish(); else cancelPress();
  };

  tile.addEventListener("pointerdown", (e) => {
    if (isBusy() || e.button > 0 || e.target.closest(".batch-x")) return;
    start = { x: e.clientX, y: e.clientY, id: e.pointerId, touch: e.pointerType !== "mouse" };
    window.addEventListener("pointermove", onMoveEv);
    window.addEventListener("pointerup", onUpEv);
    window.addEventListener("pointercancel", onUpEv);
    if (start.touch) {
      pressTimer = setTimeout(() => { pressTimer = null; if (start) begin(start.x, start.y); }, 300);
    }
  });
  // 손가락으로 끄는 중엔 화면이 같이 스크롤되지 않게(끌기 시작 전엔 막지 않음 — 창 스크롤 그대로)
  tile.addEventListener("touchmove", (e) => { if (drag) e.preventDefault(); }, { passive: false });
  tile.addEventListener("contextmenu", (e) => e.preventDefault()); // 길게 누를 때 뜨는 "이미지 저장" 메뉴 막기
  tile.addEventListener("dragstart", (e) => e.preventDefault());
}

// 찍은 시각(ms) — JPEG EXIF의 DateTimeOriginal(없으면 DateTime), 못 읽으면 파일 날짜(lastModified).
async function photoTakenTime(file) {
  try {
    const buf = await file.slice(0, 256 * 1024).arrayBuffer();
    const t = exifDateTime(new DataView(buf));
    if (t) return t;
  } catch (_) { /* 읽기 실패 → 파일 날짜 */ }
  return file.lastModified || 0;
}

function exifDateTime(view) {
  if (view.byteLength < 4 || view.getUint16(0) !== 0xffd8) return null; // JPEG 아님
  let pos = 2;
  while (pos + 4 <= view.byteLength) {
    const marker = view.getUint16(pos);
    const size = view.getUint16(pos + 2);
    if (marker === 0xffe1 && pos + 10 <= view.byteLength && view.getUint32(pos + 4) === 0x45786966) { // "Exif"
      return readTiffDate(view, pos + 10);
    }
    if ((marker & 0xff00) !== 0xff00 || marker === 0xffda) return null; // 영상 데이터 시작 — EXIF 없음
    pos += 2 + size;
  }
  return null;
}

function readTiffDate(view, tiff) {
  const little = view.getUint16(tiff) === 0x4949;
  const u16 = (o) => view.getUint16(tiff + o, little);
  const u32 = (o) => view.getUint32(tiff + o, little);
  const readIfd = (off) => {
    const out = {};
    const n = u16(off);
    for (let i = 0; i < n; i++) {
      const e = off + 2 + i * 12;
      out[u16(e)] = { type: u16(e + 2), count: u32(e + 4), value: u32(e + 8) };
    }
    return out;
  };
  const ascii = (entry) => {
    if (!entry || entry.type !== 2 || entry.count < 19) return "";
    let s = "";
    for (let i = 0; i < 19; i++) s += String.fromCharCode(view.getUint8(tiff + entry.value + i));
    return s;
  };
  const toMs = (s) => {
    const m = /^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})$/.exec(s);
    return m ? new Date(+m[1], m[2] - 1, +m[3], +m[4], +m[5], +m[6]).getTime() : null;
  };
  const ifd0 = readIfd(u32(4));
  const exifPtr = ifd0[0x8769];
  const exif = exifPtr ? readIfd(exifPtr.value) : {};
  return toMs(ascii(exif[0x9003])) || toMs(ascii(exif[0x9004])) || toMs(ascii(ifd0[0x0132]));
}
