// 재사용 서명/도장 칸 — 담당요원 서명(staff.html), 결재란 이사·대표이사 도장(settings.html).
// 데스크톱 서명칸(desktop/widgets/signature_pad.py)처럼 "직접 그리기"와 "이미지 올리기"(도장 스캔 등)
// 둘 다 된다. 저장은 명시적 "저장" 버튼(그리기) 또는 파일 선택 즉시(이미지). 서버는 둘 다 PNG로 저장.
//
// createSignatureField(container, { imageUrl, uploadUrl, deleteUrl, registered, onChange })
//   imageUrl  : 저장된 이미지 GET 경로(미리보기)
//   uploadUrl : POST(FormData: file, source="drawn"|"uploaded")
//   deleteUrl : DELETE
//   registered: 처음 상태(등록 여부)
//   onChange(result): 저장/삭제 후 서버 응답을 넘겨준다
function createSignatureField(container, opts) {
  container.innerHTML = `
    <canvas class="sig-pad" width="360" height="140"></canvas>
    <div style="display:flex; gap:6px; flex-wrap:wrap; align-items:center;">
      <button type="button" class="secondary sig-clear" style="margin-top:8px;">지우기</button>
      <button type="button" class="sig-save" style="margin-top:8px;">그린 서명 저장</button>
      <label class="sig-upload-label" style="margin:8px 0 0; font-weight:500;">
        <span class="sig-upload-btn">이미지로 올리기</span>
        <input type="file" accept="image/*" class="sig-file" style="display:none;" />
      </label>
    </div>
    <div class="status sig-status"></div>
  `;
  const canvas = container.querySelector(".sig-pad");
  const ctx = canvas.getContext("2d");
  const statusEl = container.querySelector(".sig-status");
  ctx.lineWidth = 2.5;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  let drawing = false;
  let hasInk = false;

  const setStatus = (registered, message) => {
    statusEl.className = "status sig-status " + (registered ? "ok" : "bad");
    statusEl.textContent = message || (registered ? "등록됨" : "미등록 — 그리거나 이미지를 올려주세요.");
  };
  const clearCanvas = () => {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    hasInk = false;
  };
  const showSaved = () => {
    const img = new Image();
    img.onload = () => {
      clearCanvas();
      // 비율 유지해서 가운데에 맞춤(도장 이미지는 정사각형에 가까워 늘리면 찌그러짐)
      const ratio = Math.min(canvas.width / img.width, canvas.height / img.height);
      const w = img.width * ratio, h = img.height * ratio;
      ctx.drawImage(img, (canvas.width - w) / 2, (canvas.height - h) / 2, w, h);
    };
    img.src = `${opts.imageUrl}?ts=${Date.now()}`;
  };
  const point = (e) => {
    const r = canvas.getBoundingClientRect();
    return [(e.clientX - r.left) * (canvas.width / r.width), (e.clientY - r.top) * (canvas.height / r.height)];
  };

  canvas.addEventListener("pointerdown", (e) => {
    if (!hasInk) clearCanvas(); // 저장된 미리보기 위에 겹쳐 그리지 않게 새로 시작
    drawing = true;
    canvas.setPointerCapture(e.pointerId);
    const [x, y] = point(e);
    ctx.beginPath();
    ctx.moveTo(x, y);
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!drawing) return;
    const [x, y] = point(e);
    ctx.lineTo(x, y);
    ctx.stroke();
    hasInk = true;
  });
  canvas.addEventListener("pointerup", () => { drawing = false; });
  canvas.addEventListener("pointerleave", () => { drawing = false; });

  const upload = async (blob, filename, source) => {
    const form = new FormData();
    form.append("file", blob, filename);
    form.append("source", source);
    const out = await apiUpload(opts.uploadUrl, form);
    hasInk = false;
    showSaved();
    setStatus(true, "저장되었습니다.");
    if (opts.onChange) opts.onChange(out);
  };

  container.querySelector(".sig-save").addEventListener("click", () => {
    if (!hasInk) {
      setStatus(false, "먼저 서명을 그려주세요.");
      return;
    }
    canvas.toBlob(async (blob) => {
      try {
        await upload(blob, "signature.png", "drawn");
      } catch (err) {
        setStatus(false, err.message);
      }
    }, "image/png");
  });
  container.querySelector(".sig-file").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      await upload(file, file.name, "uploaded");
    } catch (err) {
      setStatus(false, err.message);
    }
    e.target.value = "";
  });
  container.querySelector(".sig-clear").addEventListener("click", async () => {
    clearCanvas();
    try {
      const out = await api(opts.deleteUrl, { method: "DELETE" });
      setStatus(false);
      if (opts.onChange) opts.onChange(out);
    } catch (err) {
      setStatus(false, err.message);
    }
  });

  if (opts.registered) {
    showSaved();
    setStatus(true);
  } else {
    setStatus(false);
  }
}
