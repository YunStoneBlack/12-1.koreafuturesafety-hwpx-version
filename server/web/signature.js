// 재사용 서명/도장 칸 — 담당요원 서명(staff.html "수정"), 결재란 이사·대표이사 도장(settings.html),
// 보고서 1번 현장책임자 서명(report.html). 데스크톱 서명칸(desktop/widgets/signature_pad.py)처럼 "직접 그리기"와
// "이미지 올리기"(도장 스캔 등) 둘 다 된다. 서버는 둘 다 PNG로 저장.
//
// 실수 방지(2026-09-29 사용자 요청 — 손이 한 번 스쳐 서명이 망가지거나, "지우기"가 서버 서명을 바로 지워 버리던 문제):
//   - "저장"을 누르기 전에는 서버에 아무것도 반영하지 않는다. 그리다 망치면 "처음 상태로"(또는 저장 안 하고 닫기)로 끝.
//   - "↶ 한 획 되돌리기": 획·지우기·이미지 올리기를 하나씩 취소. 저장된 서명 위에 처음 그으면 칸을 비우고 새로 시작하는데,
//     이것도 되돌리기 한 번에 원래 서명으로 돌아온다.
//   - "지우기"는 칸만 비운다. 빈 칸으로 저장하면 그때 확인창을 띄우고 서명을 삭제한다.
//   - 저장 안 한 변경이 있는 채로 페이지를 떠나면 브라우저가 경고한다.
//
// createSignatureField(container, { imageUrl, uploadUrl, deleteUrl, registered, onChange, standalone, saveLabel, lockable })
//   imageUrl  : 저장된 이미지 GET 경로(미리보기)
//   uploadUrl : POST(FormData: file, source="drawn"|"uploaded")
//   deleteUrl : DELETE
//   registered: 처음 상태(등록 여부)
//   onChange(result): 저장/삭제 후 서버 응답을 넘겨준다
//   lockable  : true면 저장된 서명이 있을 때 잠가 둔다(보기만, "수정" 버튼만) — "수정"을 눌러야 도구·저장·취소가 나오고,
//               저장하거나 취소하면 다시 잠긴다. 저장된 서명이 없으면 바로 그릴 수 있다(보고서 1번에서 현장 책임자에게 바로 받게).
//               결재란 도장(settings.html)·보고서 1번 현장책임자 서명에 사용(2026-09-29 사용자 요청). standalone일 때만 의미 있음.
//   standalone: true(기본)면 칸 아래에 자체 "저장" 버튼을 둔다. false면 버튼 없이, 부르는 쪽이 돌려받은 field.save()를 부른다
//               (담당요원 "수정"처럼 이름·연락처와 한 번에 저장하는 경우).
// 돌려주는 값: { isDirty(), save() } — save()는 바뀐 게 없으면 아무것도 안 하고 true, 저장/삭제하면 true, 삭제 확인에서 취소하면 false.

const _dirtySignatureFields = new Set();
window.addEventListener("beforeunload", (e) => {
  if ([..._dirtySignatureFields].some((f) => f.isConnected() && f.isDirty())) {
    e.preventDefault();
    e.returnValue = "";
  }
});

function createSignatureField(container, opts) {
  const standalone = opts.standalone !== false;
  const lockable = standalone && !!opts.lockable;
  container.innerHTML = `
    <canvas class="sig-pad" width="360" height="140"></canvas>
    <div class="sig-tools">
      <button type="button" class="secondary sig-undo">↶ 한 획 되돌리기</button>
      <button type="button" class="secondary sig-reset">처음 상태로</button>
      <button type="button" class="secondary sig-clear">지우기</button>
      <label class="sig-upload-label">
        <span class="sig-upload-btn">이미지로 올리기</span>
        <input type="file" accept="image/*" class="sig-file" style="display:none;" />
      </label>
      ${standalone ? `<button type="button" class="sig-save">${opts.saveLabel || "저장"}</button>` : ""}
      ${lockable ? '<button type="button" class="secondary sig-cancel">취소</button>' : ""}
    </div>
    ${lockable ? '<div class="sig-locked-bar"><button type="button" class="secondary sig-edit">수정</button></div>' : ""}
    <div class="status sig-status"></div>
    <div class="sig-drop-hint">PC에서는 이미지 파일을 서명 칸 위로 끌어다 놓아도 됩니다.</div>
  `;
  const canvas = container.querySelector(".sig-pad");
  const ctx = canvas.getContext("2d");
  const statusEl = container.querySelector(".sig-status");
  const undoBtn = container.querySelector(".sig-undo");
  const resetBtn = container.querySelector(".sig-reset");
  const saveBtn = container.querySelector(".sig-save");

  let registered = !!opts.registered;
  let savedImage = null; // 서버에 저장된 서명(Image) — "처음 상태로"의 기준
  // 편집 기록: {t:"stroke", pts:[[x,y],...]} / {t:"clear", auto?} / {t:"image", img, file}
  // 화면 = 마지막 clear/image를 바탕으로(없으면 저장된 서명) 그 뒤 획들을 그린 것. 되돌리기 = 마지막 기록 빼고 다시 그림.
  let ops = [];
  let drawing = null;
  let locked = false;

  const drawContained = (img) => {
    // 비율 유지해서 가운데에 맞춤(도장 이미지는 정사각형에 가까워 늘리면 찌그러짐)
    const ratio = Math.min(canvas.width / img.width, canvas.height / img.height);
    const w = img.width * ratio, h = img.height * ratio;
    ctx.drawImage(img, (canvas.width - w) / 2, (canvas.height - h) / 2, w, h);
  };
  const baseIndex = () => {
    for (let i = ops.length - 1; i >= 0; i--) if (ops[i].t !== "stroke") return i;
    return -1;
  };
  const strokeCount = () => ops.length - baseIndex() - 1;
  const isBlank = () => {
    const b = baseIndex();
    const base = b >= 0 ? ops[b] : null;
    const baseEmpty = base ? base.t === "clear" : !registered;
    return baseEmpty && strokeCount() === 0;
  };
  const isDirty = () => ops.length > 0;

  const redraw = () => {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.lineWidth = 2.5;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    const b = baseIndex();
    if (b >= 0 && ops[b].t === "image") drawContained(ops[b].img);
    else if (b < 0 && savedImage) drawContained(savedImage);
    for (const op of ops.slice(b + 1)) {
      ctx.beginPath();
      op.pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      if (op.pts.length === 1) ctx.lineTo(op.pts[0][0] + 0.1, op.pts[0][1]); // 점 하나도 보이게
      ctx.stroke();
    }
    refreshUi();
  };

  const refreshUi = (message, ok) => {
    undoBtn.disabled = !ops.length;
    resetBtn.disabled = !ops.length;
    if (saveBtn) saveBtn.disabled = !ops.length;
    if (message) {
      statusEl.className = "status sig-status " + (ok ? "ok" : "bad");
      statusEl.textContent = message;
    } else if (isDirty()) {
      statusEl.className = "status sig-status warn";
      statusEl.textContent = isBlank()
        ? "칸을 비웠습니다 — 저장하면 서명이 삭제됩니다."
        : "바뀐 서명이 아직 저장되지 않았습니다.";
    } else {
      statusEl.className = "status sig-status " + (registered ? "ok" : "bad");
      statusEl.textContent = registered ? "등록됨" : "미등록 — 그리거나 이미지를 올려주세요.";
    }
  };

  // 저장된 서명을 다시 불러와 그린다. message가 있으면 다 그린 뒤 그 안내를 띄운다(바로 "등록됨"으로 덮이지 않게).
  const loadSaved = (message, ok) => {
    const done = () => { redraw(); if (message) refreshUi(message, ok); };
    if (!registered) {
      savedImage = null;
      done();
      return;
    }
    const img = new Image();
    img.onload = () => { savedImage = img; done(); };
    img.onerror = done;
    img.src = `${opts.imageUrl}?ts=${Date.now()}`;
  };

  const point = (e) => {
    const r = canvas.getBoundingClientRect();
    return [(e.clientX - r.left) * (canvas.width / r.width), (e.clientY - r.top) * (canvas.height / r.height)];
  };
  canvas.addEventListener("pointerdown", (e) => {
    if (locked) return;
    // 저장된 서명/올린 이미지 위에 처음 그으면 칸을 비우고 새로 시작(겹쳐 그리지 않게) — 되돌리기 한 번에 원래대로
    const b = baseIndex();
    const baseHasPicture = b >= 0 ? ops[b].t === "image" : !!savedImage;
    if (baseHasPicture && strokeCount() === 0) ops.push({ t: "clear", auto: true });
    drawing = { t: "stroke", pts: [point(e)] };
    ops.push(drawing);
    canvas.setPointerCapture(e.pointerId);
    redraw();
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!drawing) return;
    drawing.pts.push(point(e));
    redraw();
  });
  const endStroke = () => { drawing = null; };
  canvas.addEventListener("pointerup", endStroke);
  canvas.addEventListener("pointercancel", endStroke);

  undoBtn.addEventListener("click", () => {
    const op = ops.pop();
    if (op && op.t === "stroke" && ops.length && ops[ops.length - 1].auto) ops.pop();
    redraw();
  });
  resetBtn.addEventListener("click", () => { ops = []; redraw(); });
  container.querySelector(".sig-clear").addEventListener("click", () => {
    if (isBlank()) return;
    ops.push({ t: "clear" });
    redraw();
  });
  const loadImageFile = (file) => {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      refreshUi("이미지 파일(PNG·JPG 등)만 올릴 수 있습니다.", false);
      return;
    }
    const img = new Image();
    img.onload = () => { ops.push({ t: "image", img, file }); redraw(); };
    img.onerror = () => refreshUi("이미지를 열 수 없습니다.", false);
    img.src = URL.createObjectURL(file);
  };
  container.querySelector(".sig-file").addEventListener("change", (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    loadImageFile(file);
  });
  // 도장 스캔 이미지 등을 서명 칸 위로 끌어다 놓아도 "이미지로 올리기"와 같다(저장은 똑같이 "저장"을 눌러야 반영)
  canvas.title = "여기에 이미지를 끌어다 놓아도 됩니다";
  container.addEventListener("dragover", (e) => {
    if (![...(e.dataTransfer?.types || [])].includes("Files")) return;
    e.preventDefault(); // 잠겨 있어도 막는다 — 안 막으면 브라우저가 놓은 파일을 새 창으로 열어 버림
    if (!locked) canvas.classList.add("drop-over");
  });
  container.addEventListener("dragleave", (e) => {
    if (!container.contains(e.relatedTarget)) canvas.classList.remove("drop-over");
  });
  container.addEventListener("drop", (e) => {
    e.preventDefault();
    canvas.classList.remove("drop-over");
    if (locked) {
      refreshUi('먼저 "수정"을 누른 뒤 이미지를 올려 주세요.', false);
      return;
    }
    loadImageFile(e.dataTransfer.files[0]);
  });

  async function save() {
    if (!isDirty()) return true;
    let out;
    if (isBlank()) {
      if (!registered) { ops = []; redraw(); return true; }
      if (!confirm("서명을 삭제할까요?")) return false;
      out = await api(opts.deleteUrl, { method: "DELETE" });
      registered = false;
    } else {
      const b = baseIndex();
      const form = new FormData();
      if (b >= 0 && ops[b].t === "image" && strokeCount() === 0) {
        // 올린 이미지를 그대로 저장(캔버스로 다시 그리면 화질이 떨어짐)
        form.append("file", ops[b].file, ops[b].file.name);
        form.append("source", "uploaded");
      } else {
        const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
        form.append("file", blob, "signature.png");
        form.append("source", "drawn");
      }
      out = await apiUpload(opts.uploadUrl, form);
      registered = true;
    }
    ops = [];
    setLocked(lockable && registered); // 저장하면 다시 잠금(삭제해서 비었으면 바로 그릴 수 있게 둠)
    loadSaved(registered ? "저장되었습니다." : "서명을 삭제했습니다.", registered);
    if (opts.onChange) opts.onChange(out);
    return true;
  }

  if (saveBtn) {
    saveBtn.addEventListener("click", async () => {
      saveBtn.disabled = true;
      try {
        await save();
      } catch (err) {
        refreshUi(err.message, false);
      }
    });
  }

  // --- 잠금(lockable) — 컨테이너에 sig-locked 클래스(도구 숨김·칸 보기 전용, style.css) ---
  function setLocked(value) {
    locked = value;
    container.classList.toggle("sig-locked", value);
  }
  if (lockable) {
    container.classList.add("sig-lockable");
    container.querySelector(".sig-edit").addEventListener("click", () => { setLocked(false); refreshUi(); });
    container.querySelector(".sig-cancel").addEventListener("click", () => {
      if (isDirty() && !confirm("저장하지 않고 닫을까요? 바꾼 내용은 사라집니다.")) return;
      ops = [];
      redraw();
      if (registered) setLocked(true);
    });
  }
  setLocked(lockable && registered);

  const field = { isDirty, save, isConnected: () => canvas.isConnected };
  _dirtySignatureFields.add(field);
  loadSaved();
  return field;
}
