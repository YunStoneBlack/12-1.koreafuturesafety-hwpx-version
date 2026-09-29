// 재사용 서명/도장 칸 — 담당요원 서명(staff.html "수정"), 결재란 이사·대표이사 도장(settings.html),
// 보고서 1번 현장책임자 서명(report.html). 데스크톱 서명칸(desktop/widgets/signature_pad.py)처럼 "직접 그리기"와
// "이미지 올리기"(도장 스캔 등) 둘 다 된다. 서버는 둘 다 PNG로 저장.
//
// 화면 구성(2026-09-29 사용자 요청 — 폰에서 서명하다 화면이 같이 스크롤되거나, 스크롤하다 칸이 그어지던 문제):
//   - 페이지 안에는 서명 **미리보기**와 [서명하기]/[수정] 버튼만 있다(그려지지 않음 → 스크롤하다 스쳐도 안전).
//   - 버튼을 누르면 화면 가득 **서명 창**이 열린다. 창이 떠 있는 동안 뒤 화면은 스크롤되지 않고, 칸 안 터치는 코드로도 스크롤을 막는다
//     (touch-action만으론 일부 폰 브라우저가 같이 움직였음). 칸이 커서 서명도 크게 받는다.
//   - 창 안: "↶ 한 획 되돌리기"·"처음 상태로"·"지우기"(칸만 비움)·"이미지로 올리기"(끌어다 놓기도 됨), [취소]/[완료].
//     저장된 서명 위에 처음 그으면 칸을 비우고 새로 시작하되 되돌리기 한 번에 원래대로.
//   - [완료]: standalone(기본)이면 바로 서버에 저장(빈 칸이면 확인 후 삭제). standalone:false면 저장하지 않고 "대기"로 두고,
//     부르는 쪽이 field.save()로 저장한다(담당요원 "수정"처럼 이름·연락처와 한 번에 저장).
//   - 저장 안 한 대기 서명이 있거나 창이 열린 채 페이지를 떠나면 브라우저가 경고한다.
//
// createSignatureField(container, { imageUrl, uploadUrl, deleteUrl, registered, onChange, standalone, title })
//   imageUrl  : 저장된 이미지 GET 경로(미리보기)
//   uploadUrl : POST(FormData: file, source="drawn"|"uploaded")
//   deleteUrl : DELETE
//   registered: 처음 상태(등록 여부)
//   onChange(result): 저장/삭제 후 서버 응답을 넘겨준다
//   title     : 서명 창 제목(예: "현장책임자 서명", "대표이사 도장")
// 돌려주는 값: { isDirty(), save() } — save()는 대기 서명이 없으면 true, 저장/삭제하면 true, 삭제 확인에서 취소하면 false.

const _dirtySignatureFields = new Set();
window.addEventListener("beforeunload", (e) => {
  if ([..._dirtySignatureFields].some((f) => f.isConnected() && f.isDirty())) {
    e.preventDefault();
    e.returnValue = "";
  }
});

const SIG_W = 900, SIG_H = 350; // 창 안 서명 칸 해상도(예전 360×140과 같은 비율, 크게 받아 보고서에서 선명하게)

function createSignatureField(container, opts) {
  const standalone = opts.standalone !== false;
  container.innerHTML = `
    <div class="sig-preview"><img alt="" hidden /><span class="sig-preview-empty">서명 없음</span></div>
    <div class="sig-inline-bar">
      <button type="button" class="secondary sig-open"></button>
      <span class="status sig-status"></span>
    </div>
  `;
  const previewImg = container.querySelector(".sig-preview img");
  const previewEmpty = container.querySelector(".sig-preview-empty");
  const openBtn = container.querySelector(".sig-open");
  const statusEl = container.querySelector(".sig-status");

  let registered = !!opts.registered;
  let savedImage = null; // 서버에 저장된 서명(Image)
  // standalone:false에서 [완료]했지만 아직 저장 안 한 결과: {kind:"drawn", blob, img} | {kind:"uploaded", file, img} | {kind:"delete"}
  let pending = null;
  let modalOpen = false;

  // 지금 보여 줄 그림(대기 결과가 있으면 그것, 아니면 저장된 서명)
  const currentImage = () => (pending ? (pending.kind === "delete" ? null : pending.img) : savedImage);

  const renderInline = (message, ok) => {
    const img = currentImage();
    previewImg.hidden = !img;
    previewEmpty.hidden = !!img;
    if (img) previewImg.src = img.src;
    openBtn.textContent = img ? "수정" : "서명하기";
    if (message) {
      statusEl.className = "status sig-status " + (ok ? "ok" : "bad");
      statusEl.textContent = message;
    } else if (pending) {
      statusEl.className = "status sig-status warn";
      statusEl.textContent = pending.kind === "delete" ? "저장하면 서명이 삭제됩니다." : "바뀐 서명이 아직 저장되지 않았습니다.";
    } else {
      statusEl.className = "status sig-status " + (registered ? "ok" : "bad");
      statusEl.textContent = registered ? "등록됨" : "미등록";
    }
  };

  const loadSaved = (message, ok) => {
    const done = () => renderInline(message, ok);
    if (!registered) {
      savedImage = null;
      done();
      return;
    }
    const img = new Image();
    img.onload = () => { savedImage = img; done(); };
    img.onerror = () => { savedImage = null; done(); };
    img.src = `${opts.imageUrl}?ts=${Date.now()}`;
  };

  // 결과를 서버에 반영(업로드/삭제). 삭제 확인에서 취소하면 false.
  async function commit(result) {
    let out;
    if (result.kind === "delete") {
      if (!registered) {
        pending = null;
        renderInline();
        return true;
      }
      if (!confirm("서명을 삭제할까요?")) return false;
      out = await api(opts.deleteUrl, { method: "DELETE" });
      registered = false;
    } else {
      const form = new FormData();
      if (result.kind === "uploaded") {
        form.append("file", result.file, result.file.name); // 올린 이미지는 원본 그대로(캔버스로 다시 그리면 화질이 떨어짐)
        form.append("source", "uploaded");
      } else {
        form.append("file", result.blob, "signature.png");
        form.append("source", "drawn");
      }
      out = await apiUpload(opts.uploadUrl, form);
      registered = true;
    }
    pending = null;
    loadSaved(registered ? "저장되었습니다." : "서명을 삭제했습니다.", registered);
    if (opts.onChange) opts.onChange(out);
    return true;
  }

  async function save() {
    if (!pending) return true;
    return commit(pending);
  }

  openBtn.addEventListener("click", () => {
    openSignatureModal({
      title: opts.title || "서명",
      baseImage: currentImage(),
      doneLabel: standalone ? "완료(저장)" : "완료",
      onOpen: () => { modalOpen = true; },
      onClose: () => { modalOpen = false; },
      // 창에서 [완료] — 결과가 없으면(안 바뀜) null
      onDone: async (result) => {
        if (!result) return true;
        if (standalone) return commit(result);
        pending = result;
        renderInline();
        return true;
      },
    });
  });

  const field = {
    isDirty: () => !!pending || modalOpen,
    save,
    isConnected: () => container.isConnected,
  };
  _dirtySignatureFields.add(field);
  loadSaved();
  return field;
}

// 화면 가득 서명 창. onDone(result|null)이 true를 돌려주면 닫힌다(삭제 확인 취소·저장 실패면 창 유지).
function openSignatureModal({ title, baseImage, doneLabel, onDone, onOpen, onClose }) {
  const overlay = document.createElement("div");
  overlay.className = "sig-modal-overlay";
  overlay.innerHTML = `
    <div class="sig-modal" role="dialog" aria-modal="true">
      <div class="sig-modal-head">
        <b></b>
        <span class="sig-modal-hint">칸 안에 그리세요. PC에서는 이미지 파일을 끌어다 놓아도 됩니다.</span>
        <span class="sig-modal-rotate">폰을 가로로 돌리면 서명 칸이 더 커집니다.</span>
      </div>
      <div class="sig-modal-pad"><canvas width="${SIG_W}" height="${SIG_H}"></canvas></div>
      <div class="sig-modal-status"></div>
      <div class="sig-modal-actions">
        <div class="sig-modal-tools">
          <button type="button" class="sig-undo">↶ 한 획 되돌리기</button>
          <button type="button" class="sig-reset">처음 상태로</button>
          <button type="button" class="sig-clear">지우기</button>
          <label class="sig-upload"><span>이미지로 올리기</span><input type="file" accept="image/*" hidden /></label>
        </div>
        <div class="sig-modal-foot">
          <button type="button" class="sig-cancel">취소</button>
          <button type="button" class="sig-done primary"></button>
        </div>
      </div>
    </div>`;
  overlay.querySelector(".sig-modal-head b").textContent = title;
  overlay.querySelector(".sig-done").textContent = doneLabel;
  document.body.appendChild(overlay);
  const prevOverflow = document.documentElement.style.overflow;
  document.documentElement.style.overflow = "hidden"; // 창이 떠 있는 동안 뒤 화면 스크롤 잠금
  if (onOpen) onOpen();

  const canvas = overlay.querySelector("canvas");
  const ctx = canvas.getContext("2d");
  const statusEl = overlay.querySelector(".sig-modal-status");
  const undoBtn = overlay.querySelector(".sig-undo");
  const resetBtn = overlay.querySelector(".sig-reset");
  const doneBtn = overlay.querySelector(".sig-done");

  // 편집 기록: {t:"stroke", pts} / {t:"clear", auto?} / {t:"image", img, file}. 화면 = 마지막 clear/image(없으면 처음 그림) + 그 뒤 획들
  let ops = [];
  let drawing = null;
  const baseIndex = () => { for (let i = ops.length - 1; i >= 0; i--) if (ops[i].t !== "stroke") return i; return -1; };
  const strokeCount = () => ops.length - baseIndex() - 1;
  const isBlank = () => {
    const b = baseIndex();
    const baseEmpty = b >= 0 ? ops[b].t === "clear" : !baseImage;
    return baseEmpty && strokeCount() === 0;
  };
  const drawContained = (img) => {
    const ratio = Math.min(canvas.width / img.width, canvas.height / img.height);
    const w = img.width * ratio, h = img.height * ratio;
    ctx.drawImage(img, (canvas.width - w) / 2, (canvas.height - h) / 2, w, h);
  };
  const redraw = () => {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.lineWidth = 6;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    const b = baseIndex();
    if (b >= 0 && ops[b].t === "image") drawContained(ops[b].img);
    else if (b < 0 && baseImage) drawContained(baseImage);
    for (const op of ops.slice(b + 1)) {
      ctx.beginPath();
      op.pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      if (op.pts.length === 1) ctx.lineTo(op.pts[0][0] + 0.1, op.pts[0][1]);
      ctx.stroke();
    }
    undoBtn.disabled = !ops.length;
    resetBtn.disabled = !ops.length;
  };
  const say = (text, bad) => { statusEl.textContent = text || ""; statusEl.classList.toggle("bad", !!bad); };

  const point = (e) => {
    const r = canvas.getBoundingClientRect();
    return [(e.clientX - r.left) * (canvas.width / r.width), (e.clientY - r.top) * (canvas.height / r.height)];
  };
  canvas.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    const b = baseIndex();
    const baseHasPicture = b >= 0 ? ops[b].t === "image" : !!baseImage;
    if (baseHasPicture && strokeCount() === 0) ops.push({ t: "clear", auto: true });
    drawing = { t: "stroke", pts: [point(e)] };
    ops.push(drawing);
    canvas.setPointerCapture(e.pointerId);
    say("");
    redraw();
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!drawing) return;
    e.preventDefault();
    drawing.pts.push(point(e));
    redraw();
  });
  const endStroke = () => { drawing = null; };
  canvas.addEventListener("pointerup", endStroke);
  canvas.addEventListener("pointercancel", endStroke);
  // touch-action:none만으론 일부 폰 브라우저가 긋는 도중 화면을 같이 움직여서, 칸 안 터치는 코드로도 막는다
  for (const type of ["touchstart", "touchmove"]) {
    canvas.addEventListener(type, (e) => e.preventDefault(), { passive: false });
  }

  undoBtn.addEventListener("click", () => {
    const op = ops.pop();
    if (op && op.t === "stroke" && ops.length && ops[ops.length - 1].auto) ops.pop();
    redraw();
  });
  resetBtn.addEventListener("click", () => { ops = []; say(""); redraw(); });
  overlay.querySelector(".sig-clear").addEventListener("click", () => {
    if (!isBlank()) { ops.push({ t: "clear" }); redraw(); }
  });
  const loadImageFile = (file) => {
    if (!file) return;
    if (!file.type.startsWith("image/")) { say("이미지 파일(PNG·JPG 등)만 올릴 수 있습니다.", true); return; }
    const img = new Image();
    img.onload = () => { ops.push({ t: "image", img, file }); say(""); redraw(); };
    img.onerror = () => say("이미지를 열 수 없습니다.", true);
    img.src = URL.createObjectURL(file);
  };
  const fileInput = overlay.querySelector(".sig-upload input");
  fileInput.addEventListener("change", () => { loadImageFile(fileInput.files[0]); fileInput.value = ""; });
  const pad = overlay.querySelector(".sig-modal-pad");
  overlay.addEventListener("dragover", (e) => {
    if (![...(e.dataTransfer?.types || [])].includes("Files")) return;
    e.preventDefault();
    pad.classList.add("drop-over");
  });
  overlay.addEventListener("dragleave", (e) => { if (!overlay.contains(e.relatedTarget)) pad.classList.remove("drop-over"); });
  overlay.addEventListener("drop", (e) => {
    e.preventDefault();
    pad.classList.remove("drop-over");
    loadImageFile(e.dataTransfer.files[0]);
  });

  const close = () => {
    overlay.remove();
    document.documentElement.style.overflow = prevOverflow;
    document.removeEventListener("keydown", onKey);
    if (onClose) onClose();
  };
  const cancel = () => {
    if (ops.length && !confirm("바꾼 서명을 버리고 닫을까요?")) return;
    close();
  };
  const onKey = (e) => { if (e.key === "Escape") cancel(); };
  document.addEventListener("keydown", onKey);
  overlay.querySelector(".sig-cancel").addEventListener("click", cancel);

  // [완료] — 안 바뀌었으면 결과 없음(null). 빈 칸이면 삭제, 올린 이미지만 있으면 원본 파일, 그 외엔 캔버스를 PNG로.
  doneBtn.addEventListener("click", async () => {
    doneBtn.disabled = true;
    try {
      let result = null;
      if (ops.length) {
        const b = baseIndex();
        if (isBlank()) {
          result = baseImage ? { kind: "delete" } : null;
        } else if (b >= 0 && ops[b].t === "image" && strokeCount() === 0) {
          result = { kind: "uploaded", file: ops[b].file, img: ops[b].img };
        } else {
          const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
          const img = new Image();
          img.src = URL.createObjectURL(blob);
          await img.decode().catch(() => {});
          result = { kind: "drawn", blob, img };
        }
      }
      if (await onDone(result)) close();
    } catch (err) {
      say(err.message, true);
    } finally {
      doneBtn.disabled = false;
    }
  });

  redraw();
}
