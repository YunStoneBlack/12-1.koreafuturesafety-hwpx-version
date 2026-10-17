// 보고서 자동화 시설물 화면 맨 위 "① 시설물 등록"(sitok-facility.html?id=, 2026-10-16 민재형 개편) — 시설물(건물·동) 관리는 여기서만.
// 건물 등록만(10/16 민재형 "몇 개든 등록시키고 → 보고서 구성") — 자료 [시설물관리대장 | 관리대장 없음 — 자체점검·법정 외]를 고르고 파일을 올리면
// 줄마다 읽어(3개씩 같이) 이름을 채우고 [등록]으로 건물을 만듦. 등록 전 시설물이면 첫 줄이 이 시설물(이름도 관리대장·결과표 시설물명으로).
// 몇 권으로 낼지(묶음·따로)·계약 연결은 아래 📚 보고서 구성(js/sitok-compose.js)에서 — 새 건물은 처음엔 따로 보고서.
// 관리대장이 없으면 결과표·시설물 현황(전회차 보고서 그대로, 또는 동마다 그 쪽만 모은 PDF)을 AI가 읽음 — 결과표 개수 = 동 수(양식은 회사가 달라도 같음).
// 서버 /sitok/docs/facilities/{id}/add/read(관리대장)·add/read-sheets(결과표)·add(따로 — 지금 계약이 같이 맡음)·dong(묶음), 이 시설물은 PATCH /sitok/facilities/{id}.
// 10/16 개편 2차: 등록 전이면 맨 위에 펼쳐 둠, 등록 뒤엔 숨겨 두고 동 타일의 [＋ 동 추가](js/sitok-facility.js → "sitok-reg-open")로만 엶.

(function () {
  const id = Number(new URLSearchParams(location.search).get("id")) || null;
  const box = document.getElementById("sk-reg");
  if (!id || !box) return;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const D = "/sitok/docs/facilities";
  const FAC_KEYS = ["fms_no", "template", "kind", "use_type", "main_use", "address", "owner_name", "owner_type", "owner_phone", "completion_date", "structure",
    "floors_above", "floors_below", "floors_roof", "max_height", "total_area", "building_area", "land_area", "coverage_ratio", "floor_area_ratio"];
  let fac = null;
  const st = { src: "ledger", rows: [], reading: 0, busy: false }; // 건물은 따로 등록하고 묶음은 📚 보고서 구성에서

  const base = () => String(fac.mgmt_no || "").replace(/^((?:관급|민간)-\d+)-\d+$/, "$1");
  const grouped = () => !!(fac.group && fac.group.members.length > 1);
  const units = () => fac.card_units || [];
  const registered = () => !!(fac.has_ledger_pdf || fac.fms_no || fac.legal === false || grouped() || units().length > 1); // 법정 외(결과표로 등록)도 등록됨
  const clean = (fields) => Object.fromEntries(FAC_KEYS.filter((k) => fields[k] !== undefined && fields[k] !== null && fields[k] !== "").map((k) => [k, fields[k]]));

  function summary() { // 접힌 칸 머리 — 지금 등록 상태 한 줄
    const el = document.getElementById("sk-info-count");
    if (!el) return;
    const kind = fac.legal === false ? "관리대장 없음(법정 외)" : fac.has_ledger_pdf ? "관리대장 ✓" : fac.fms_no ? `FMS ${fac.fms_no}` : "";
    el.textContent = units().length > 1 ? `보고서 따로 ${units().length}곳(${units().map((u) => u.mgmt_no).join(" · ")})${kind ? ` · ${kind}` : ""}`
      : grouped() ? `동 묶음 ${fac.group.members.length}동 — 보고서 한 권(${fac.group.name})${kind ? ` · ${kind}` : ""}`
        : registered() ? `이 시설물 하나 · ${kind}` : "등록 전 — 보고서를 어떻게 내는지 고르고 관리대장(없으면 결과표)을 올리세요";
  }

  function texts() {
    if (st.src === "ledger") {
      return ["시설물관리대장 — 건물마다 한 장, 여러 장 한꺼번에(종합 관리대장도 됨)",
        "PDF·한글·사진 — 줄마다 읽어 이름을 채웁니다(한 장에 10~30초, 3장씩 같이). 이름을 확인하고 [등록] → 아래 📚 보고서 구성에서 묶거나 나누기"];
    }
    return ["전회차 보고서 또는 결과표 + 시설물 현황(동마다 모은 PDF도)",
      "결과표 개수만큼 건물을 만들고 값은 AI가 읽습니다(다른 회사 보고서도 결과표 양식은 같음) — 법정 외. 등록 뒤 아래 📚 보고서 구성에서 묶기"];
  }

  function draw() {
    box.innerHTML = `
      <div class="rg-q" role="radiogroup" aria-label="자료"><span class="rg-l">자료</span>
        <label><input type="radio" name="rg-src" value="ledger" /> 시설물관리대장</label>
        <label><input type="radio" name="rg-src" value="sheet" /> 관리대장 없음 <small>자체점검·법정 외</small></label></div>
      <label class="sk-drop rg-drop"><input type="file" class="rg-file" accept=".pdf,.hwp,.hwpx,.jpg,.jpeg,.png,application/pdf,image/*" hidden data-kr-file="skip" />
        <b>📄 <span class="rg-drop-t"></span></b><span class="sk-drop-msg rg-drop-s"></span></label>
      <div class="lg-list rg-list" hidden></div>
      <div class="rg-msg mail-note"></div>
      <div class="rg-foot" hidden><button type="button" class="rg-clear secondary">목록 비우기</button><button type="button" class="rg-go">등록</button></div>`;
    box.querySelector(`input[name="rg-src"][value="${st.src}"]`).checked = true;
    box.querySelectorAll('input[name="rg-src"]').forEach((r) => r.addEventListener("change", () => { st.src = r.value; sync(); }));
    const file = box.querySelector(".rg-file");
    file.addEventListener("change", () => { const fs = [...file.files]; file.value = ""; if (fs.length) take(fs); });
    enableFileDrop(box.querySelector(".rg-drop"), file);
    box.querySelector(".rg-go").addEventListener("click", go);
    box.querySelector(".rg-clear").addEventListener("click", () => { st.rows = []; drawRows(); say(""); });
    sync();
  }

  function sync() { // 고른 방식에 맞게 글자·칸
    const [t, s] = texts();
    box.querySelector(".rg-drop-t").textContent = t;
    box.querySelector(".rg-drop-s").textContent = s;
    box.querySelector(".rg-file").multiple = true;
    drawRows();
  }

  function say(text, cls) {
    const m = box.querySelector(".rg-msg");
    m.className = `rg-msg mail-note${cls ? ` ${cls}` : ""}`;
    m.innerHTML = text;
  }

  const known = (fields) => { // 카드에 이미 있는 건물(시설물번호) — 등록하지 않음(10/16 관급-3 관리동 두 번)
    const no = String((fields || {}).fms_no || "").replace(/\s/g, "").toUpperCase();
    return no ? (fac.card_fms || []).find((x) => String(x.fms_no || "").replace(/\s/g, "").toUpperCase() === no) || null : null;
  };

  function drawRows() {
    const list = box.querySelector(".rg-list");
    list.hidden = !st.rows.length;
    box.querySelector(".rg-foot").hidden = !st.rows.length;
    list.innerHTML = "";
    const first = !registered();
    const live = st.rows.filter((x) => !x.done && !known(x.fields));
    st.rows.forEach((it) => {
      const row = document.createElement("div");
      const dup = !it.done && known(it.fields);
      row.className = `lg-row${it.done || dup ? " done" : ""}`;
      const role = it.done ? "" : dup ? `이미 있음 — ${dup.mgmt_no} ${dup.name}` : first && it === live[0] && !st.rows.some((x) => x.done) ? "이 시설물" : "새 시설물";
      row.innerHTML = `<span class="lg-file" title="${esc(it.file)}">${esc(it.file)}</span>
        <input class="lg-name" value="${esc(it.name)}" placeholder="${it.reading ? "읽는 중…" : "이름"}" aria-label="이름"${it.done ? " disabled" : ""} />
        <span class="lg-st">${esc(it.status)}${!it.legal && !it.reading ? ' <span class="rg-tag">법정 외</span>' : ""}${role ? ` <span class="rg-role">${role}</span>` : ""}</span>
        ${it.done ? "" : '<button type="button" class="rg-x" title="이 줄 빼기">✕</button>'}`;
      row.querySelector(".lg-name").addEventListener("input", (e) => { it.name = e.target.value; });
      row.querySelector(".rg-x")?.addEventListener("click", () => { st.rows.splice(st.rows.indexOf(it), 1); drawRows(); });
      list.appendChild(row);
    });
    box.querySelector(".rg-go").disabled = st.reading > 0 || st.busy;
  }

  const read = (f) => {
    const fd = new FormData();
    fd.append("file", f);
    return apiUpload(`${D}/${id}/add/${st.src === "ledger" ? "read" : "read-sheets"}`, fd);
  };

  async function take(fs) {
    say(`${fs.length}개 읽는 중… — ${st.src === "ledger" ? "한 장에 10~30초" : "결과표마다 AI가 읽느라 20~60초"}, 3개씩 같이`);
    const jobs = fs.map((f) => {
      const it = { file: f.name, name: "", status: "읽는 중…", reading: true, legal: st.src === "ledger", fields: {}, token: null, extra: null, done: false };
      st.rows.push(it);
      return { f, it };
    });
    drawRows();
    let i = 0;
    const warns = [];
    const worker = async () => {
      while (i < jobs.length) {
        const { f, it } = jobs[i++];
        st.reading += 1;
        try {
          const r = await read(f);
          if (st.src === "ledger") {
            (r.items || [r]).forEach((x, k) => { // 종합 관리대장(여러 건물을 한 PDF로) — 건물마다 줄
              const row = k === 0 ? it : { file: `${f.name} (${k + 1})`, done: false, legal: true };
              row.token = x.token;
              row.fields = { ...(x.fields || {}) };
              row.extra = row.fields.ledger || null;
              delete row.fields.ledger;
              row.name = row.name || row.fields.name || "";
              row.status = x.error ? "못 읽음 — 이름 직접" : `✓ 읽음${row.fields.fms_no ? ` · ${row.fields.fms_no}` : ""}`;
              row.reading = false;
              if (k > 0) st.rows.splice(st.rows.indexOf(it) + k, 0, row);
            });
          } else {
            const items = r.items || [];
            if (!items.length) { it.status = r.error || "못 읽음 — 이름 직접"; it.legal = false; }
            items.forEach((x, k) => { // 파일 하나에 결과표 여럿(동마다 모은 PDF) — 줄을 늘림
              const row = k === 0 ? it : { file: `${f.name} (${k + 1})`, done: false, token: null, extra: null };
              row.fields = { ...x.fields };
              row.legal = !!x.fields.legal;
              row.name = x.fields.name || "";
              row.status = `✓ 결과표${x.fields.total_area ? ` · 연면적 ${Number(x.fields.total_area).toLocaleString("ko-KR")}㎡` : ""}`;
              row.reading = false;
              if (k > 0) st.rows.splice(st.rows.indexOf(it) + k, 0, row);
            });
            if (r.found && r.found !== items.length) warns.push(`${f.name}: 결과표 ${r.found}장인데 건물 ${items.length}개를 읽었습니다 — 줄을 확인하세요`);
          }
        } catch (err) {
          it.status = `못 읽음 — ${err.message}`;
        } finally {
          it.reading = false;
          st.reading -= 1;
          drawRows();
        }
      }
    };
    await Promise.all([worker(), worker(), worker()]);
    const n = st.rows.filter((x) => !x.done).length;
    say(`${n}개 — 이름을 확인하고 [등록]을 누르세요. ${!registered() ? "첫 줄은 <b>이 시설물</b>(이름도 바뀜), 나머지는 " : ""}새 건물(지금 계약이 같이 맡음)이 됩니다 — 등록 뒤 아래 📚 보고서 구성에서 한 권으로 묶거나 나누세요.`
      + (warns.length ? `<br>⚠ ${warns.map(esc).join("<br>⚠ ")}` : ""), warns.length ? "bad" : "");
  }

  async function go() { // [등록] — 줄마다 차례로(번호가 차례로 붙게), 실패한 줄은 남기고 다시 누르면 그 줄만
    if (st.reading || st.busy) return;
    const todo = st.rows.filter((x) => !x.done && x.name.trim() && !known(x.fields));
    if (!todo.length) { say(st.rows.some((x) => !x.done) ? "이름이 있는 줄이 없습니다 — 못 읽은 줄은 이름을 넣어 주세요." : "이미 다 등록했습니다.", "bad"); return; }
    st.busy = true;
    drawRows();
    let first = !registered() && !st.rows.some((x) => x.done);
    const made = [];
    let bad = 0;
    for (const [n, it] of todo.entries()) {
      say(`등록하는 중… ${n + 1}/${todo.length}`);
      const body = { name: it.name.trim(), address: it.fields.address || fac.address || "", owner_name: it.fields.owner_name || fac.owner_name || "",
        ledger_token: it.token, fields: it.fields, ledger_extra: it.extra, legal: it.legal };
      try {
        if (first) { // 등록 전 시설물 — 첫 줄이 이 시설물(이름·칸·관리대장)
          fac = await apiPatch(`/sitok/facilities/${id}${it.token ? `?ledger_token=${encodeURIComponent(it.token)}` : ""}`, { ...clean(it.fields), name: body.name, legal: it.legal });
          made.push(`${fac.mgmt_no} ${fac.name}(이 시설물)`);
          first = false;
        } else {
          const out = await apiPost(`${D}/${id}/add`, { ...body, join_active: true });
          made.push(`${out.mgmt_no} ${body.name}`);
        }
        it.done = true;
        it.status = "✓ 등록";
      } catch (err) {
        bad += 1;
        it.status = `✗ ${err.message}`;
      }
      drawRows();
    }
    st.busy = false;
    drawRows();
    if (bad) { say(`${made.length}개 등록, ${bad}개 실패 — 줄 옆 ✗를 보고 고친 뒤 [등록]을 다시 누르면 실패한 줄만 합니다.`, "bad"); return; }
    say(`✓ 등록했습니다: ${made.map(esc).join(" · ")} — 화면을 새로 엽니다.`, "ok");
    setTimeout(() => location.reload(), 1500);
  }

  window.addEventListener("sitok-facility-loaded", (e) => {
    fac = e.detail;
    st.src = fac.legal === false ? "sheet" : "ledger";
    const panel = document.getElementById("sk-info-panel");
    if (panel && !registered()) panel.open = true; // 등록 전이면 펼쳐 둠
    const sec = document.getElementById("fi-reg");
    sec.hidden = registered(); // 등록 뒤엔 [＋ 동 추가]로만
    sec.classList.toggle("fi-boxed", registered());
    document.getElementById("fi-reg-t").textContent = registered() ? "동 추가" : "시설물 등록 — 무엇으로 등록할까요?";
    document.getElementById("fi-reg-x").hidden = !registered();
    summary();
    draw();
  });
  window.addEventListener("sitok-reg-open", () => { // 동 타일 [＋ 동 추가]
    const sec = document.getElementById("fi-reg");
    sec.hidden = false;
    sec.scrollIntoView({ block: "start", behavior: "smooth" });
  });
  document.getElementById("fi-reg-x")?.addEventListener("click", () => { document.getElementById("fi-reg").hidden = true; });
})();
