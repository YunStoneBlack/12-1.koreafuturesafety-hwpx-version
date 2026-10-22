// 내진성능평가 현장조사 입력(seismic-field.html?id=회차, 2026-10-21 사용자) — 부재 단면·코어·조적조 줄, 현장 사진 칸, 분석 글.
// 칸마다 [저장] = PATCH /seismic/projects/{id}/field {그 칸만}. 사진 = POST/DELETE …/field/photo/{slot}. 코어 [🤖 성적서에서 읽기] = POST …/field/cores/read.

(function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const errorEl = document.getElementById("error");
  const $ = (id) => document.getElementById(id);
  const id = Number(new URLSearchParams(location.search).get("id")) || 0;
  let F = null;
  let members = [], cores = [], masonry = [];
  const err = (e) => showError(errorEl, e);
  const flash = (el, text) => { el.textContent = text; setTimeout(() => { if (el.textContent === text) el.textContent = ""; }, 3500); };
  const opt = (list, v) => list.map(([val, label]) => `<option value="${esc(val)}"${String(val) === String(v ?? "") ? " selected" : ""}>${esc(label)}</option>`).join("");

  // 줄 편집기 — cols: [키, 이름, 너비, 종류(text|number|select), 고르기 목록]
  function rows(box, list, cols, blank, onChange) {
    const draw = () => {
      box.innerHTML = `<div class="sf2-row sf2-row-h"><span class="sf2-no">#</span>${cols.map(([, label, w]) => `<span style="flex:${w}">${esc(label)}</span>`).join("")}<span class="sp-x-sp"></span></div>`
        + list.map((r, i) => `<div class="sf2-row"><span class="sf2-no">${i + 1}</span>${cols.map(([k, label, w, type, choices]) => {
          const c = typeof choices === "function" ? choices(r) : choices;
          return type === "select"
            ? `<select data-i="${i}" data-k="${k}" title="${esc(label)}" style="flex:${w}">${opt(c, r[k])}</select>`
            : `<input data-i="${i}" data-k="${k}" type="${type || "text"}" ${type === "number" ? 'step="any" inputmode="decimal"' : ""} placeholder="${esc(label)}" title="${esc(label)}" style="flex:${w}" value="${esc(r[k] ?? "")}" />`;
        }).join("")}<button type="button" class="sp-x" data-rm="${i}" title="줄 지우기">✕</button></div>`).join("")
        + `<button type="button" class="secondary sp-add">＋ 줄</button>`;
      box.querySelectorAll("[data-k]").forEach((el) => el.addEventListener(el.tagName === "SELECT" ? "change" : "input", () => {
        const r = list[el.dataset.i];
        r[el.dataset.k] = el.value;
        if (onChange && onChange(r, el.dataset.k)) draw();
      }));
      box.querySelectorAll("[data-rm]").forEach((b) => b.addEventListener("click", () => { list.splice(Number(b.dataset.rm), 1); draw(); }));
      box.querySelector(".sp-add").addEventListener("click", () => { const last = list[list.length - 1]; list.push({ ...blank, ...(last ? { floor: last.floor, kind: last.kind } : {}) }); draw(); });
    };
    draw();
  }

  const floorChoices = () => F.floors.map((f) => [f.n, f.label]);

  function drawMembers() {
    members = F.members.map((x) => ({ ...x }));
    const items = (r) => [["", "— 일람표 칸 —"], ...F.schedule.filter((x) => x.kind === r.kind).map((x) => [x.id, `${x.marks.join(",")}${x.size ? ` ${x.size}` : ""}${x.floors ? ` (${x.floors})` : ""}`])];
    rows($("sf2-members"), members, [["floor", "층", 1, "select", floorChoices], ["where", "위치(예: 3 : I 열)", 1.6], ["kind", "부재", 0.9, "select", [["기둥", "기둥"], ["보", "보"], ["벽체", "벽체"]]],
      ["item_id", "일람표 칸", 1.8, "select", items], ["mark", "부호", 0.8], ["design", "도면치수", 1.1], ["measured", "실측치수(못 재면 □)", 1.3], ["note", "비고", 1.3]],
    { floor: F.floors[0]?.n || 1, kind: "기둥" }, (r, k) => {
      if (k === "item_id") { const it = F.schedule.find((x) => x.id === r.item_id); if (it) { r.mark = it.marks[0] || r.mark; r.design = (it.size || "").replace(/\s*[xX×*]\s*/, " x "); } return true; }
      return k === "kind";
    });
    $("sf2-m-sum").textContent = `${F.members.length}개소 (최소 ${F.min_counts.member}) — 2.2.1 부재 단면 치수 조사 결과, 일람표 칸을 고르면 도면치수`;
  }

  function drawCores() {
    cores = F.cores.map((x) => ({ ...x }));
    rows($("sf2-cores"), cores, [["name", "구분(예: 4층-벽체-1)", 2], ["mpa", "압축강도 (MPa)", 1, "number"]], {});
    const s = F.core_stats;
    $("sf2-c-stats").innerHTML = s.n ? `<b>${s.n}개</b> · 평균(m) <b>${s.mean}</b> MPa · 표준편차(s) ${s.std} · 최소 ${s.min} · 최대 ${s.max}` : "";
    $("sf2-c-note").textContent = F.core_note || (F.has_core_report ? "" : "건 화면 서류 칸에 성적서를 올리면 읽을 수 있습니다");
    $("sf2-c-read").disabled = !F.has_core_report;
    $("sf2-c-design").value = F.core_design ?? "";
    $("sf2-c-sum").textContent = `${F.cores.length}개 (최소 ${F.min_counts.core})${s.n ? ` · 평균 ${s.mean}MPa` : ""} — 2.2.3·2.2.4`;
  }

  function drawMasonry() {
    masonry = F.masonry.map((x) => ({ ...x }));
    rows($("sf2-masonry"), masonry, [["floor", "층", 1, "select", floorChoices], ["kind", "구분", 0.9, "select", [["채움벽", "채움벽"], ["허리벽", "허리벽"]]], ["mid", "부재ID", 0.7],
      ["height", "순높이(mm)", 0.9, "number"], ["width", "순너비(mm)", 0.9, "number"], ["thick", "조적두께", 0.8, "select", [["0.5B", "0.5B"], ["1.0B", "1.0B"], ["1.5B", "1.5B"], ["2.0B", "2.0B"]]],
      ["dir", "방향", 0.6, "select", [["X", "X"], ["Y", "Y"]]], ["expose", "노출", 1.3, "select", [["2면 모르타르", "2면 모르타르"], ["1면 모르타르", "1면 모르타르"], ["노출", "노출"]]],
      ["finish", "마감두께", 0.7, "number"], ["boundary", "경계면", 0.8, "select", [["양호", "양호"], ["불량", "불량"]]], ["applied", "적용", 0.8, "select", [["양호", "양호"], ["보통", "보통"], ["불량", "불량"]]]],
    { floor: F.floors[0]?.n || 1, kind: "채움벽", thick: "1.0B", dir: "X", expose: "1면 모르타르", boundary: "양호", finish: 20 }, (r, k) => {
      if (k === "applied") { r.manual = true; return false; }
      if ((k === "expose" || k === "boundary") && !r.manual) { r.applied = r.boundary === "불량" || r.expose === "노출" ? "불량" : r.expose === "2면 모르타르" ? "양호" : "보통"; return true; }
      return false;
    });
    $("sf2-w-sum").textContent = `${F.masonry.length}개 (최소 ${F.min_counts.masonry}) — 2.4.3 조적벽 치수 및 상태조사 결과표`;
  }

  function drawPhotos() {
    const box = $("sf2-photos");
    const have = Object.keys(F.photos).length;
    $("sf2-p-sum").textContent = `${have}/${F.photo_slots.length}장 — 칸마다 한 장, 누르면 올리기·바꾸기`;
    box.innerHTML = F.photo_slots.map(([k, label, where]) => {
      const p = F.photos[k];
      return `<div class="sf2-ph${p ? " on" : ""}" data-slot="${k}">
        <label class="sf2-ph-img">${p ? `<img src="${BASE}/api/seismic/projects/${id}/field/photo/${k}?v=${encodeURIComponent(p.at)}" alt="" loading="lazy" />` : '<span class="sf2-ph-empty">＋ 사진</span>'}
          <input type="file" accept="image/*" hidden data-kr-file="1" /></label>
        <div class="sf2-ph-cap"><b>${esc(label)}</b><span class="sk-help">${esc(where)}</span>${p ? `<button type="button" class="sp-x" title="지우기">✕</button>` : ""}</div></div>`;
    }).join("");
    box.querySelectorAll(".sf2-ph").forEach((el) => {
      const slot = el.dataset.slot;
      const input = el.querySelector("input");
      if (typeof enableFileDrop === "function") enableFileDrop(el, input);
      input.addEventListener("change", async () => {
        if (!input.files[0]) return;
        el.classList.add("busy");
        const fd = new FormData();
        fd.append("file", input.files[0]);
        try { F = await apiUpload(`/seismic/projects/${id}/field/photo/${slot}`, fd); drawPhotos(); } catch (e) { alert(e.message); el.classList.remove("busy"); }
      });
      el.querySelector(".sp-x")?.addEventListener("click", async () => {
        if (!confirm("이 사진을 지울까요?")) return;
        try { F = await api(`/seismic/projects/${id}/field/photo/${slot}`, { method: "DELETE" }); drawPhotos(); } catch (e) { err(e); }
      });
    });
  }

  function drawTexts() {
    $("sf2-summary").value = F.summary || "";
    $("sf2-texts").innerHTML = F.text_labels.map(([k, label]) => `<div class="sk-f"><label>${esc(label)}</label><textarea data-t="${k}" rows="2">${esc(F.texts[k] || "")}</textarea></div>`).join("");
  }

  function drawMin() {
    const m = F.min_counts;
    const it = (label, n, min, href) => `<a class="sp-min-it${n >= min && n > 0 ? " ok" : ""}"${href ? ` href="${href}"` : ""}><b>${n}</b>/${min} ${esc(label)}</a>`;
    $("sf2-min").innerHTML = it("부재 단면", F.members.length, m.member) + it("철근배근", F.rebar, m.rebar, `sitok-seismic.html?report=${id}`)
      + it("코어", F.cores.length, m.core) + it("조적조", F.masonry.length, m.masonry)
      + `<span class="sk-help">조사단위 ${F.units}개 — 매뉴얼 <표 3-1> 최소 수량(지금/최소) · 부재 ${esc((m.how || {}).member || "")} · 철근 ${esc((m.how || {}).rebar || "")}</span>`;
  }

  function draw(f) {
    F = f;
    document.title = `현장조사 입력 - ${f.name}`;
    $("sf2-name").textContent = `${f.name} 현장조사 입력`;
    $("sf2-proj").textContent = f.name;
    $("sf2-proj").href = `seismic-project.html?id=${id}`;
    drawMin(); drawMembers(); drawCores(); drawMasonry(); drawPhotos(); drawTexts();
  }

  async function save(part, body, savedEl) {
    try { draw(await apiPatch(`/seismic/projects/${id}/field`, body)); flash($(savedEl), "✓ 저장했습니다"); } catch (e) { err(e); }
  }
  const nz = (v) => (v === "" || v == null ? null : Number(v));
  $("sf2-m-save").addEventListener("click", () => save("members", { members: members.filter((x) => x.where || x.mark || x.design || x.measured).map((x) => ({ ...x, floor: Number(x.floor) })) }, "sf2-m-saved"));
  $("sf2-c-save").addEventListener("click", () => save("cores", { cores: cores.filter((x) => x.name || x.mpa).map((x) => ({ ...x, mpa: nz(x.mpa) })), core_design: nz($("sf2-c-design").value) }, "sf2-c-saved"));
  $("sf2-w-save").addEventListener("click", () => save("masonry", { masonry: masonry.filter((x) => x.mid || x.height || x.width).map((x) => ({ ...x, floor: Number(x.floor), height: nz(x.height), width: nz(x.width), finish: nz(x.finish) })) }, "sf2-w-saved"));
  $("sf2-t-save").addEventListener("click", () => save("texts", { texts: Object.fromEntries([...document.querySelectorAll("[data-t]")].map((t) => [t.dataset.t, t.value.trim()])), summary: $("sf2-summary").value.trim() }, "sf2-t-saved"));
  for (const [btn, mode, busy] of [["sf2-s-tpl", "template", "견본 문장 채우는 중…"], ["sf2-s-ai", "ai", "AI가 쓰는 중…(20~40초)"]]) {
    $(btn).addEventListener("click", async () => {
      if ($("sf2-summary").value.trim() && !confirm("지금 글을 바꿉니다. 할까요?")) return;
      $(btn).disabled = true;
      $("sf2-s-note").textContent = busy;
      try { draw(await apiPost(`/seismic/projects/${id}/field/summary/${mode}`)); $("sf2-t-panel").open = true; $("sf2-s-note").textContent = "✓ 채웠습니다 — 고치고 [저장]"; }
      catch (e) { $("sf2-s-note").textContent = e.message; }
      $(btn).disabled = false;
    });
  }
  $("sf2-c-read").addEventListener("click", async () => {
    if (cores.length && !confirm("성적서에서 다시 읽으면 지금 코어 줄이 바뀝니다. 읽을까요?")) return;
    const b = $("sf2-c-read");
    b.disabled = true;
    $("sf2-c-note").textContent = "성적서 읽는 중…(10~20초)";
    try { const res = await apiPost(`/seismic/projects/${id}/field/cores/read`); draw(res); $("sf2-c-note").textContent = `✓ ${res.read}개 읽음 — 확인하고 틀리면 고쳐 저장${F.core_note ? ` · ${F.core_note}` : ""}`; } catch (e) { $("sf2-c-note").textContent = e.message; b.disabled = false; }
  });

  (async () => {
    try {
      if (!id) throw new Error("내진성능평가 건을 찾을 수 없습니다.");
      draw(await api(`/seismic/projects/${id}/field`));
    } catch (e) { err(e); }
  })();
})();
