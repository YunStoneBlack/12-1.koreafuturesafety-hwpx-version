// 시특법 시설물·계약 칸 정의와 그리기·읽기(2026-10-12) — 시설물 고치기(js/sitok-facility.js)와 새 등록(js/sitok-new.js)이 같이 씀.
// 민간/관급 기본값(인수인계 10/10): 민간 = 독자수행 100%·수의계약·건축. 법정 외(자체 점검 — 관리대장 없음)는 틀 2종/3종 일반 중 고르고 결과표 종별 "해당없음".

const SitokFields = (() => {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  // [키, 이름, 종류, 도움말]
  const FAC = [
    ["name", "시설물명", "text", ""], ["mgmt_no", "번호", "text", "민간-3·관급-1처럼 — 새 등록 때 자동(서류 자동화 시설물 카드·드롭박스 폴더와 같은 번호), 묶인 동은 같은 번호"],
    ["sector", "민간·관급", "sector", "번호 앞 글자"], ["badge_field", "분야 뱃지", "badge_fields", "목록 거르기·개수"],
    ["badge_kind", "관급 종류 뱃지", "badge_kinds", "관급만 — 학교·일반(계약서로 자동, 바꾸면 그대로 둠)"],
    ["fms_no", "시설물번호(FMS)", "text", "예: AR2004-0004955"],
    ["template", "보고서 틀", "template", "2종 / 3종 일반(+안전등급 평가) / 3종 학교(+치장벽돌·내진보강 점검)"],
    ["legal", "법정 시설물", "legal", "1·2·3종이 아닌 자체 점검이면 '법정 외' — 결과표 종별 해당없음"],
    ["class_no", "종별", "class_nos", "도래주기 — 1종 정기~정밀안전진단, 2종 ~정밀안전점검, 3종 정기만(비우면 보고서 틀로)"],
    ["safety_grade", "안전등급", "safety_grades", "도래주기 계산 — 비우면 최근 보고서 결과표"],
    ["kind", "시설물 구분", "text", "결과표 — 보통 건축물"], ["use_type", "종류", "text", "결과표 — 종교시설·교육연구시설 등"],
    ["main_use", "주용도(관리대장)", "text", ""], ["address", "시설물 위치", "text", ""],
    ["owner_name", "관리주체명", "text", ""], ["holder", "소유주", "text", "관리대장 소유자 칸 — 결과표 대표자(비면 계약서 대표자)"],
    ["owner_type", "관리주체구분", "text", "민간·공공"], ["owner_phone", "관리주체 전화", "text", ""],
    ["contact_name", "담당자(관리소장 등)", "text", "기록용"], ["contact_phone", "담당자 전화", "text", "기록용 — 📞 전화는 서류 자동화 계약 정보 현장 담당(없으면 관리주체 전화)"],
    ["completion_date", "준공일", "date", ""], ["structure", "구조형식", "text", "예: 철근콘크리트구조"],
    ["last_precision", "전회차 정밀안전점검 완료일", "date", "우리 정밀 회차·전회차 보고서 이력이 없을 때 — 계약 창 📅 도래주기에서도"],
    ["last_diagnosis", "전회차 정밀안전진단 완료일", "date", "1종"],
    ["floors_above", "지상 층수", "int", ""], ["floors_below", "지하 층수", "int", ""], ["floors_roof", "옥탑 층수", "int", ""],
    ["max_height", "최고높이(m)", "num", ""], ["total_area", "연면적(㎡)", "num", ""], ["building_area", "건축면적(㎡)", "num", ""],
    ["land_area", "대지면적(㎡)", "num", "상태평가 결과(SafetyMan 건물개요) — 건축물대장"], ["coverage_ratio", "건폐율(%)", "num", ""], ["floor_area_ratio", "용적율(%)", "num", ""],
    ["base_wall", "면적률 기준 — 벽 한 면(㎡)", "num", "비우면 24.5(기둥간격 7m × 층고 3.5m)"],
    ["base_slab", "면적률 기준 — 슬래브 한 칸(㎡)", "num", "비우면 49(7m × 7m)"],
    // 옹벽 관리대장 칸(10/21 형) — 옹벽 시설물이면 건축물 칸(주용도·구조·층수·면적) 대신 이것(applyKind). 보고서 1.2.1 현황표·요약문·과업대상 표에 들어감
    ["wall_form", "옹벽형식", "text", "관리대장 — 예: 블록쌓기·역T형·중력식"], ["wall_material", "재료", "text", "예: 보강토·철근콘크리트"],
    ["wall_length", "연장(m)", "text", ""], ["wall_height", "지면노출높이(m)", "text", ""], ["wall_base_width", "저판폭(m)", "text", ""],
    ["wall_route", "노선", "text", "관리대장 노선·도로명"], ["wall_surround", "주변환경", "text", "예: 산업단지·도로변·주거지"],
    ["wall_builder", "시공자", "text", ""], ["wall_project", "공사명", "text", "관리대장 공사명(1.3.1 자료수집 보존대상 목록)"], ["wall_attached", "부대·부착시설", "text", "예: 안전펜스·점검로·배수시설 / 교량은 수도관·통신관 등"],
    // 교량 제원(10/29 — 교량 원본 1.2.1 시설물 현황표 칸): 교량이면 옹벽·건축물 칸 대신 이것(applyKind). 연장·노선·부대시설은 옹벽 칸과 같이 씀
    ["wall_load", "설계하중", "text", "예: DB-24·DL-24(1등교)"], ["wall_spans", "경간 구성", "text", "예: 3@20.0=60.0"], ["wall_width", "폭(m)", "text", "총폭"],
    ["wall_lanes", "차로", "text", "예: (보도 1.5+차도 7.0) 2차로"], ["wall_super_type", "상부 형식", "text", "예: PSC I형 거더교·RC 슬래브교"],
    ["wall_sub_type", "하부 형식", "text", "예: 역T형 교대·T형 교각"], ["wall_abut_found", "교대 기초", "text", "예: 직접기초·말뚝기초"], ["wall_pier_found", "교각 기초", "text", ""],
    ["wall_bearing", "교량받침", "text", "예: 탄성받침(고무)"], ["wall_joint", "신축이음", "text", "예: 모노셀·핑거형"],
    ["wall_crossing", "교차시설물", "text", "도로·철도·하천 — 예: 한탄강(하천)"], ["wall_clearance", "통과 높이(m)", "text", ""],
    ["memo", "메모", "text", "보고서엔 안 나감"],
  ];
  const WALL_ONLY = new Set(["wall_form", "wall_material", "wall_height", "wall_base_width", "wall_surround", "wall_builder", "wall_project"]);
  const BRIDGE_ONLY = new Set(["wall_load", "wall_spans", "wall_width", "wall_lanes", "wall_super_type", "wall_sub_type", "wall_abut_found", "wall_pier_found", "wall_bearing",
    "wall_joint", "wall_crossing", "wall_clearance"]); // 교량(10/29)
  const CIVIL_BOTH = new Set(["wall_length", "wall_route", "wall_attached"]); // 옹벽·교량 같이
  const BUILDING_ONLY = new Set(["main_use", "structure", "floors_above", "floors_below", "floors_roof", "max_height", "total_area", "building_area", "land_area", "coverage_ratio", "floor_area_ratio", "base_wall", "base_slab"]);

  // 보고서 틀(10/21 형): 건축물 = 2종 / 3종 일반 / 3종 학교, 옹벽 = 2종 / 3종(속값은 3종일반), 교량·수리 등 다른 토목 = 준비 중(만들기 막힘)
  function applyTemplate(box, isWall, civil) {
    const tpl = box.querySelector('[data-key="template"]');
    if (!tpl) return;
    const help = tpl.closest(".sk-f")?.querySelector(".sk-help");
    const cur = tpl.value;
    if (isWall) { // 옹벽·교량(10/29) — 2종 / 3종(속값 3종일반)
      tpl.innerHTML = '<option value="2종">2종</option><option value="3종일반">3종</option>';
      tpl.value = cur === "2종" ? "2종" : "3종일반";
      tpl.disabled = false;
      if (help) help.textContent = civil === "교량" ? "교량 2종 / 3종(+15항목 안전등급 평가)" : "옹벽 2종 / 3종(+18항목 안전등급 평가)";
    } else if (civil) {
      tpl.innerHTML = `<option value="${esc(cur || "2종")}">준비 중 — ${esc(civil)} 보고서 틀 없음</option>`;
      tpl.disabled = true;
      if (help) help.textContent = `${civil} 보고서 틀은 준비 중입니다 — 보고서 만들기가 막혀 있습니다`;
    }
  }

  function applyKind(box, isWall, civil = "") { // 옹벽이면 건축물 칸을 숨기고 옹벽 관리대장 칸을, 아니면 그 반대(10/21) · 교량(civil "교량", 10/29)이면 교량 제원 칸
    applyTemplate(box, isWall, civil);
    const bridge = isWall && civil === "교량";
    for (const el of box.querySelectorAll(".sk-f")) {
      const key = el.className.replace(/.*sk-f-(\S+).*/, "$1");
      const off = !isWall ? (WALL_ONLY.has(key) || BRIDGE_ONLY.has(key) || CIVIL_BOTH.has(key))
        : bridge ? (BUILDING_ONLY.has(key) || WALL_ONLY.has(key)) : (BUILDING_ONLY.has(key) || BRIDGE_ONLY.has(key));
      el.classList.toggle("sk-off", off);
    }
    const kind = box.querySelector("[data-key=kind]");
    const use = box.querySelector("[data-key=use_type]");
    if (kind && kind.closest(".sk-f")) kind.closest(".sk-f").querySelector(".sk-help").textContent = bridge ? "결과표 — 교량" : isWall ? "결과표 — 옹벽" : "결과표 — 보통 건축물";
    if (use && use.closest(".sk-f")) use.closest(".sk-f").querySelector(".sk-help").textContent = bridge ? "결과표 — 도로교량·보도육교 등(관리대장 시설물종류)"
      : isWall ? "결과표 — 건축물옹벽·도로옹벽 등(관리대장 시설물종류)" : "결과표 — 종교시설·교육연구시설 등";
  }
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
  const BLANK_LABEL = { class_nos: "자동(보고서 틀 — 3종 틀이면 3종)", safety_grades: "자동(최근 보고서 결과표)" }; // 도래주기 칸(10/20)
  const LEGAL = [["true", "법정 시설물(1·2·3종)"], ["false", "법정 외 — 자체 점검"]];

  function input(opts, prefix, [key, label, type, help]) {
    const idAttr = `${prefix}-${key}`;
    let field;
    if (type === "legal") {
      field = `<select id="${idAttr}" data-key="${key}" data-type="legal">${LEGAL.map(([v, t]) => `<option value="${v}">${esc(t)}</option>`).join("")}</select>`;
    } else if (type === "template" || type === "sector" || type === "halves" || type.endsWith("s")) {
      const list = { template: opts.templates, sector: opts.sectors, halves: opts.halves, badge_kinds: ["", ...(opts.badge_kinds || [])] }[type] || opts[type] || [];
      field = `<select id="${idAttr}" data-key="${key}">${list.map((v) => `<option value="${esc(v)}">${esc(v === "" && BLANK_LABEL[type] ? BLANK_LABEL[type] : TEMPLATE_LABEL[v] || v)}</option>`).join("")}</select>`;
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

  // 목록 뱃지 글 — 옹벽은 3종일반을 "3종", 틀 없는 토목은 "준비 중"(10/21)
  const templateLabel = (f) => (f.civil_kind && !["옹벽", "교량"].includes(f.civil_kind) ? "틀 준비 중" : ["옹벽", "교량"].includes(f.civil_kind) ? (f.template === "2종" ? "2종" : "3종")
    : TEMPLATE_LABEL[f.template] || f.template);
  return { esc, FAC, CON, TEMPLATE_LABEL, templateLabel, input, setValues, values, linkLegal, applyKind };
})();
