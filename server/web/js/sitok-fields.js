// 시특법 시설물·계약 칸 정의와 그리기·읽기(2026-10-12) — 시설물 고치기(js/sitok-facility.js)와 새 등록(js/sitok-new.js)이 같이 씀.
// 민간/관급 기본값(인수인계 10/10): 민간 = 독자수행 100%·수의계약·건축. 법정 외(자체 점검 — 관리대장 없음)는 틀 2종/3종 일반 중 고르고 결과표 종별 "해당없음".

const SitokFields = (() => {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  // [키, 이름, 종류, 도움말]
  const FAC = [
    ["name", "시설물명", "text", ""], ["mgmt_no", "번호", "text", "목록 번호표(예: 26-4) — 새 등록 때 자동, 묶인 동은 같은 번호"],
    ["fms_no", "시설물번호(FMS)", "text", "예: AR2004-0004955"],
    ["template", "보고서 틀", "template", "2종 / 3종 일반(+안전등급 평가) / 3종 학교(+치장벽돌·내진보강 점검)"],
    ["legal", "법정 시설물", "legal", "1·2·3종이 아닌 자체 점검이면 '법정 외' — 결과표 종별 해당없음"],
    ["kind", "시설물 구분", "text", "결과표 — 보통 건축물"], ["use_type", "종류", "text", "결과표 — 종교시설·교육연구시설 등"],
    ["main_use", "주용도(관리대장)", "text", ""], ["address", "시설물 위치", "text", ""],
    ["owner_name", "관리주체명", "text", ""], ["owner_type", "관리주체구분", "text", "민간·공공"], ["owner_phone", "관리주체 전화", "text", ""],
    ["contact_name", "담당자(관리소장 등)", "text", "목록 📞 전화 버튼"], ["contact_phone", "담당자 전화", "text", "비우면 관리주체 전화로 걺"],
    ["completion_date", "준공일", "date", ""], ["structure", "구조형식", "text", "예: 철근콘크리트구조"],
    ["floors_above", "지상 층수", "int", ""], ["floors_below", "지하 층수", "int", ""], ["floors_roof", "옥탑 층수", "int", ""],
    ["max_height", "최고높이(m)", "num", ""], ["total_area", "연면적(㎡)", "num", ""], ["building_area", "건축면적(㎡)", "num", ""],
    ["land_area", "대지면적(㎡)", "num", "상태평가 결과(SafetyMan 건물개요) — 건축물대장"], ["coverage_ratio", "건폐율(%)", "num", ""], ["floor_area_ratio", "용적율(%)", "num", ""],
    ["base_wall", "면적률 기준 — 벽 한 면(㎡)", "num", "비우면 24.5(기둥간격 7m × 층고 3.5m)"],
    ["base_slab", "면적률 기준 — 슬래브 한 칸(㎡)", "num", "비우면 49(7m × 7m)"],
    ["memo", "메모", "text", "보고서엔 안 나감"],
  ];
  const CON = [
    ["sector", "계약 구분", "sector", ""], ["title", "계약건명", "text", ""], ["contract_no", "계약번호", "text", "관급(나라장터)"],
    ["contract_date", "계약일", "date", ""], ["start_date", "계약기간 시작(착수일)", "date", ""], ["end_date", "계약기간 끝(완수일)", "date", ""],
    ["halves", "점검 반기", "halves", "연간 = 상·하반기 둘 다"],
    ["first_half_end", "상반기 완료일", "date", "관급 1년 계약 — 직접 정함"], ["second_half_start", "하반기 시작일", "date", "관급 1년 계약 — 직접 정함"],
    ["amount", "계약금액(원, VAT 포함)", "int", "민간은 반기 한 번 금액"], ["rep_name", "관리주체 대표자", "text", "결과표 대표자"],
    ["joint_type", "공동수급", "joint_types", ""], ["joint_pct", "지분(%)", "int", ""],
    ["bid_method", "입찰방식", "bid_methods", ""], ["field", "수행분야", "fields", ""],
  ];
  const TEMPLATE_LABEL = { "2종": "2종", "3종일반": "3종 일반", "3종학교": "3종 학교" };
  const LEGAL = [["true", "법정 시설물(1·2·3종)"], ["false", "법정 외 — 자체 점검"]];

  function input(opts, prefix, [key, label, type, help]) {
    const idAttr = `${prefix}-${key}`;
    let field;
    if (type === "legal") {
      field = `<select id="${idAttr}" data-key="${key}" data-type="legal">${LEGAL.map(([v, t]) => `<option value="${v}">${esc(t)}</option>`).join("")}</select>`;
    } else if (type === "template" || type === "sector" || type === "halves" || type.endsWith("s")) {
      const list = { template: opts.templates, sector: opts.sectors, halves: opts.halves }[type] || opts[type];
      field = `<select id="${idAttr}" data-key="${key}">${list.map((v) => `<option value="${esc(v)}">${esc(TEMPLATE_LABEL[v] || v)}</option>`).join("")}</select>`;
    } else {
      const t = type === "date" ? "date" : type === "int" || type === "num" ? "number" : "text";
      field = `<input id="${idAttr}" data-key="${key}" data-type="${type}" type="${t}"${type === "num" ? ' step="any"' : ""} />`;
    }
    return `<div class="sk-f sk-f-${key}"><label for="${idAttr}">${esc(label)}${help ? ` <span class="sk-help">${esc(help)}</span>` : ""}</label>${field}</div>`;
  }

  function setValues(box, data, onlyEmpty) {
    for (const el of box.querySelectorAll("[data-key]")) {
      const v = data[el.dataset.key];
      if (v === undefined || v === null || v === "") continue;
      if (onlyEmpty && el.value && el.tagName !== "SELECT") continue;
      el.value = String(v);
      el.classList.add("sk-filled");
      setTimeout(() => el.classList.remove("sk-filled"), 2500);
    }
  }

  function values(box) {
    const out = {};
    for (const el of box.querySelectorAll("[data-key]")) {
      const v = el.value.trim();
      const t = el.dataset.type;
      out[el.dataset.key] = t === "int" ? (v === "" ? null : parseInt(v, 10)) : t === "num" ? (v === "" ? null : parseFloat(v))
        : t === "date" ? (v || null) : t === "legal" ? v !== "false" : v;
    }
    return out;
  }

  // 법정 외면 틀은 2종 / 3종 일반 중에서(10/12 사용자 "2종틀로 쓸건지 3종일반틀로 쓸건지") — 3종 학교는 막음. 값을 넣은 뒤 다시 부르려고 sync를 돌려줌.
  function linkLegal(box) {
    const legal = box.querySelector('[data-key="legal"]');
    const tpl = box.querySelector('[data-key="template"]');
    if (!legal || !tpl) return () => {};
    const sync = () => {
      const off = legal.value === "false";
      const school = tpl.querySelector('option[value="3종학교"]');
      if (school) school.disabled = off;
      if (off && tpl.value === "3종학교") tpl.value = "3종일반";
    };
    legal.addEventListener("change", sync);
    sync();
    return sync;
  }

  return { esc, FAC, CON, TEMPLATE_LABEL, input, setValues, values, linkLegal };
})();
