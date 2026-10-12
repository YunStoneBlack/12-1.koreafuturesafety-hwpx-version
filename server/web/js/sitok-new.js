// 시특법 새 점검 대상 등록(sitok-new.html, 2026-10-12 사용자) — 계약서·이전 회차 보고서·동마다 [시설물관리대장]-[건축물대장]을 한 번에.
// 관리대장 → 그 동 칸(시설물명은 관리대장 따라감), 계약서 → 계약 칸(+ 1번 동 빈 칸), 건축물대장 → 보관만(시설물 현황·1.2.8 초안이 나중에 읽음),
// 이전 회차 → 한글이면 이미 낸 보고서로(여러 동이면 나눔), PDF면 첫 회차 현장 조사에 전회차 결함. [등록하고 시작] = POST /sitok/onboard → 대표 동 화면.

(function () {
  const errorEl = document.getElementById("error");
  const { FAC, CON, setValues, values } = SitokFields;
  const SHOW = ["name", "fms_no", "template", "legal", "kind", "use_type", "main_use", "address", "owner_name", "owner_type", "owner_phone",
    "completion_date", "structure", "floors_above", "floors_below", "floors_roof", "max_height", "total_area", "building_area"];
  let opts = null;
  let prior = null; // {token, kind, name, year, half, chapters, ours, has_defects}
  let conToken = null;
  let ownerRep = "";
  let seq = 0;
  const input = (prefix, f) => SitokFields.input(opts, prefix, f);

  async function upload(path, file, extra) {
    const fd = new FormData();
    Object.entries(extra || {}).forEach(([k, v]) => fd.append(k, v));
    fd.append("file", file);
    return apiUpload(path, fd);
  }

  function dropZone(zone, onFile) {
    const inp = zone.querySelector("input");
    inp.addEventListener("change", () => { if (inp.files[0]) onFile(inp.files[0]); });
    enableFileDrop(zone, inp);
  }

  async function busy(zone, msg, work) {
    const out = zone.querySelector(".sk-drop-msg");
    zone.classList.add("busy");
    out.classList.remove("bad");
    out.textContent = msg;
    try { out.textContent = await work(); } catch (e) { out.textContent = `읽지 못했습니다: ${e.message}`; out.classList.add("bad"); }
    zone.classList.remove("busy");
  }

  // ---------- 동 ----------
  function building() {
    seq += 1;
    const el = document.createElement("div");
    el.className = "nw-b";
    el.dataset.k = `b${seq}`;
    el.innerHTML = `<div class="nw-b-head"><b class="nw-b-no"></b><button type="button" class="link-btn nw-b-del">이 동 빼기</button></div>
      <div class="nw-b-drops">
        <label class="sk-drop nw-ledger"><input type="file" accept="application/pdf,.pdf" hidden data-kr-file="1" />
          <b>📄 시설물관리대장 PDF</b><span class="sk-drop-msg">FMS 출력 — 시설물명 등이 채워짐. 없으면(법정 외 자체 점검) 아래 칸에 직접</span></label>
        <span class="nw-dash">—</span>
        <label class="sk-drop nw-reg"><input type="file" accept="application/pdf,.pdf" hidden data-kr-file="1" />
          <b>📄 건축물대장 PDF</b><span class="sk-drop-msg">변동사항("을") 쪽까지 — 없으면(군사보안 등) 비워 두기: 그 칸은 "-"로 두고 직접 입력</span></label>
      </div>
      <details class="nw-fields"><summary>시설물 칸 <span class="sk-help">관리대장을 올리면 채워집니다 — 확인·고치기</span></summary>
        <div class="field-grid">${FAC.filter((f) => SHOW.includes(f[0])).map((f) => input(el.dataset.k, f)).join("")}</div></details>`;
    setValues(el, { legal: true, kind: "건축물" });
    el.querySelectorAll(".sk-filled").forEach((x) => x.classList.remove("sk-filled"));
    const syncLegal = SitokFields.linkLegal(el);
    dropZone(el.querySelector(".nw-ledger"), (file) => busy(el.querySelector(".nw-ledger"), `${file.name} — 읽는 중…(10~30초)`, async () => {
      const r = await upload("/sitok/read", file, { kind: "ledger" });
      el.dataset.ledger = r.token;
      el._extra = (r.fields || {}).ledger || null;
      ownerRep = ownerRep || (r.fields || {}).owner_rep || "";
      setValues(el, { ...r.fields, legal: true }, false);
      syncLegal();
      el.querySelector(".nw-fields").open = true;
      label();
      if (ownerRep) setValues(document.getElementById("nw-con"), { rep_name: ownerRep }, true);
      return r.error || `✓ ${file.name} — ${(r.fields || {}).name || "칸"}을(를) 채웠습니다`;
    }));
    dropZone(el.querySelector(".nw-reg"), (file) => busy(el.querySelector(".nw-reg"), `${file.name} 올리는 중…`, async () => {
      const r = await upload("/sitok/read", file, { kind: "register" });
      el.dataset.register = r.token;
      return `✓ ${file.name} — 시설물 현황·1.2.8 변경사항 초안에 씁니다`;
    }));
    el.querySelector('[data-key="name"]').addEventListener("input", label);
    el.querySelector(".nw-b-del").addEventListener("click", () => { el.remove(); label(); });
    document.getElementById("nw-buildings").appendChild(el);
    label();
    return el;
  }

  function label() { // 동 번호·이름, 묶음 이름 칸(2동 이상)
    const all = [...document.querySelectorAll(".nw-b")];
    all.forEach((b, i) => {
      const name = b.querySelector('[data-key="name"]').value.trim();
      b.querySelector(".nw-b-no").textContent = `${i + 1}번 동${name ? ` — ${name}` : ""}${all.length > 1 ? ` (시설물편 제${i + 1}장)` : ""}`;
      b.querySelector(".nw-b-del").hidden = all.length === 1;
    });
    const g = document.getElementById("nw-group");
    g.hidden = all.length < 2;
    const gn = document.getElementById("nw-group-name");
    if (!g.hidden && !gn.value.trim()) gn.placeholder = all[0].querySelector('[data-key="owner_name"]').value.trim() || "예: 숭의교회";
  }

  // ---------- 계약 ----------
  function contract() {
    const box = document.getElementById("nw-con");
    box.innerHTML = `<div class="field-grid">${CON.map((f) => input("nc", f)).join("")}</div>`;
    setValues(box, { sector: "민간", halves: "연간", joint_type: "독자수행", joint_pct: 100, bid_method: "수의계약", field: "건축" });
    box.querySelectorAll(".sk-filled").forEach((x) => x.classList.remove("sk-filled"));
    const sync = () => { // 관급 + 연간일 때만 상반기 완료일·하반기 시작일, 계약번호는 관급만
      const gov = box.querySelector('[data-key="sector"]').value === "관급";
      const yearly = box.querySelector('[data-key="halves"]').value === "연간";
      box.querySelectorAll(".sk-f-first_half_end, .sk-f-second_half_start").forEach((x) => { x.hidden = !(gov && yearly); });
      box.querySelector(".sk-f-contract_no").hidden = !gov;
    };
    box.querySelector('[data-key="sector"]').addEventListener("change", (e) => {
      if (e.target.value === "민간") setValues(box, { joint_type: "독자수행", joint_pct: 100, bid_method: "수의계약" });
      sync();
    });
    box.querySelector('[data-key="halves"]').addEventListener("change", sync);
    sync();
  }

  dropZone(document.getElementById("nw-con-drop"), (file) => busy(document.getElementById("nw-con-drop"), `${file.name} — 읽는 중…(10~30초)`, async () => {
    const r = await upload("/sitok/read", file, { kind: "contract" });
    const f = r.fields || {};
    conToken = r.token;
    const box = document.getElementById("nw-con");
    setValues(box, { ...f, rep_name: f.sector === "민간" && ownerRep ? ownerRep : f.rep_name }, false);
    box.querySelector('[data-key="sector"]').dispatchEvent(new Event("change"));
    setValues(box, { joint_type: f.joint_type, bid_method: f.bid_method }, false);
    setValues(document.querySelector(".nw-b"), { owner_name: f.owner_name, address: f.address }, true); // 1번 동 빈 칸만
    return r.error || `✓ ${file.name} — 계약 칸을 채웠습니다`;
  }));

  dropZone(document.getElementById("nw-prior-drop"), (file) => busy(document.getElementById("nw-prior-drop"), `${file.name} 올리는 중…(한글은 바꾸느라 10~30초)`, async () => {
    prior = await upload("/sitok/prior", file);
    if (prior.kind === "hwpx") {
      const n = document.querySelectorAll(".nw-b").length;
      const more = prior.chapters > n ? ` — 보고서는 ${prior.chapters}동입니다. [+ 동 추가]로 ${prior.chapters}동을 넣으세요(장 순서대로 나눔)` : "";
      return `✓ 우리 보고서 ${prior.year}년 ${prior.half} · ${prior.chapters}동 — 이미 낸 보고서로 등록하고 이번 회차가 데이터를 가져옵니다${more}`;
    }
    return prior.has_defects ? `✓ ${prior.ours ? "우리" : "타회사"} PDF — 첫 회차 현장 조사에 전회차 결함으로 가져옵니다(한 동일 때)`
      : "PDF에서 결함현황표를 찾지 못했습니다 — 보관만 합니다";
  }));

  document.getElementById("nw-add").addEventListener("click", () => building().scrollIntoView({ behavior: "smooth", block: "center" }));

  document.getElementById("nw-go").addEventListener("click", async () => {
    errorEl.style.display = "none";
    const bs = [...document.querySelectorAll(".nw-b")];
    const buildings = bs.map((b) => {
      const f = values(b);
      Object.keys(f).forEach((k) => { if (!SHOW.includes(k)) delete f[k]; });
      return { facility: f, ledger_token: b.dataset.ledger || null, ledger_extra: b._extra || null, register_token: b.dataset.register || null };
    });
    const missing = buildings.findIndex((b) => !b.facility.name);
    if (missing >= 0) {
      bs[missing].querySelector(".nw-fields").open = true;
      alert(`${missing + 1}번 동 시설물명을 넣어 주세요 — 시설물관리대장을 올리면 채워집니다.`);
      return;
    }
    const con = values(document.getElementById("nw-con"));
    const hasContract = con.title || con.start_date || con.amount || conToken;
    const btn = document.getElementById("nw-go");
    btn.disabled = true;
    document.getElementById("nw-msg").textContent = "등록하는 중…";
    try {
      const r = await apiPost("/sitok/onboard", {
        buildings, contract: hasContract ? { ...con, contract_token: conToken } : null,
        prior_token: prior ? prior.token : null, prior_name: prior ? prior.name : null,
        group_name: document.getElementById("nw-group-name").value.trim() || null,
        year: Number(document.getElementById("nw-year").value), half: document.getElementById("nw-half").value,
      });
      if (r.notes && r.notes.length) alert(`등록했습니다.\n\n${r.notes.map((n) => `· ${n}`).join("\n")}`);
      location.href = `sitok-facility.html?id=${r.facility.id}`;
    } catch (e) {
      showError(errorEl, e);
      document.getElementById("nw-msg").textContent = "";
      btn.disabled = false;
    }
  });

  (async () => {
    try {
      opts = await api("/sitok/options");
      const today = new Date();
      document.getElementById("nw-year").value = today.getFullYear();
      document.getElementById("nw-half").value = today.getMonth() < 6 ? "상반기" : "하반기";
      building();
      contract();
    } catch (e) { showError(errorEl, e); }
  })();
})();
