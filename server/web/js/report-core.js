// report.html 스크립트 — 공통 상수·보고서 불러오기·기본 정보·1번(결재·통보, 서명패드)·2·5·6·6-3번.
// report.html에서 순서대로 불러오는 5개 파일 중 하나(core → photos → work → support → main). 파일끼리는
// 전역 함수/상수를 공유하고, 페이지 시작 시 실행하는 호출은 전부 report-main.js 맨 아래에 모아 두었다
// (앞 파일이 뒤 파일 함수를 불러오는 시점 문제를 없애려고 — 여기엔 정의만 둔다).

const errorEl = document.getElementById("error");
const reportId = new URLSearchParams(window.location.search).get("id");
const NOTIFICATION_METHODS = ["직접전달", "등기우편", "전자우편", "모바일", "기타"];
// core/constants.py::MAJOR_HAZARD_WORKS와 동일한 순서 — 인덱스가 저장값이라 순서를 바꾸면 안 됨.
const MAJOR_HAZARD_WORKS = [
  "흙막이지보공 설치작업(굴착깊이 10m 이상)", "흙막이지보공 해체작업",
  "관로매설 굴착작업(굴착깊이1.5m이상)", "거푸집동바리 설치작업(층고5m이상)",
  "무지보동바리 설치작업(호리빔, 데크플레이트 등)", "구조물 철거(해체)작업(3층 이상)",
  "터널 굴착작업", "철골 1절(3개층) 조립 작업", "pc 조립작업",
  "교량 상부공 거치작업(psc빔, steel box)", "비계 설치작업(높이 20m이상)", "비계 해체작업",
  "타워크레인 설치작업", "작업발판 일체형 거푸집(갱폼, ACS·RCS폼, 교각폼 등) 조립작업",
  "타워크레인 상승작업(1회 한정)", "타워크레인 해체작업",
  "작업발판 일체형 거푸집 상승(인양)작업 (1회 한정)", "작업발판 일체형 거푸집 해체작업",
  "외벽 마감작업(곤돌라 작업)", "외벽 마감작업(달비계 작업)", "외벽 마감작업(고소작업대 작업)",
  "지하층 내 유증기 발생작업(방수, 도장, 배관접속 작업 등)", "우레탄폼 등 단열재 주위 용접·용단작업",
  "밀페공간작업(콘크리트 양생작업)", "밀폐공간적업(저수조, 탱크 내부 방수·청소작업)",
];

// core/constants.py::FIXED_HAZARD_FACTORS와 동일 — (번호, 기인물명, [지도사항 줄, ...])
const FIXED_HAZARD_FACTORS = [
  [1, "단부 개구부", ["단부안전난간 설치", "개구부덮개 고정"]],
  [2, "철골", ["철골 인양전 안전대 부착설비 설치"]],
  [3, "지붕", ["안전난간 발판설치", "채광창 덮개설치"]],
  [4, "비계, 작업발판", ["안전난간 설치", "외벽 틈 추락방호망 설치"]],
  [5, "굴착기", ["작업반경 출입통제", "후방 충돌방지장치 작동확인"]],
  [6, "고소작업대", ["안전대 체결", "작업대 이탈 금지"]],
  [7, "사다리", ["안전모착용, 2인1조 작업"]],
  [8, "달비계", ["구명줄 안전대 체결", "2개 고정점 설치(구명줄작업줄)"]],
  [9, "트럭", ["이동구간 출입통제", "전담유도자 배치"]],
  [10, "이동식비계", ["최상부 안전난간 설치"]],
  [11, "거푸집동바리", ["시스템동바리 사용", "하부 추락방지망 설치"]],
  [12, "이동식크레인", ["인양물 고정 철저", "하부 출입통제"]],
  [13, "화재·폭발", ["용접장치, 전기설비, 위험물질·폭발 사고 예방 조치 등"]],
  [14, "그 밖의 위험요인 안전조치", ["밀폐공간 안전조치 등"]],
  [15, "MSDS, 폭염 등에 대한 보건조치", ["폭염 시 현장 내 그늘막, 얼음물 등 제공", "혹한기 방한용품 구비", "MSDS 현장비치"]],
  [16, "작업전 TBM(안전점검 회의) 실시 여부", ["작업 전 TBM 실시 후 작업 투입"]],
  [17, "위험성 평가 결과 현장 근로자 공유 여부", ["TBM을 통해 위험성 평가 결과 공유"]],
];

// core/constants.py의 MACHINERY_EQUIPMENT_ITEMS/HAND_TOOL_ITEMS/HAZMAT_ITEMS와 동일 순서.
const MACHINERY_EQUIPMENT_ITEMS = [
  ["굴착기", ["작업반경 내 출입금지 구역 설정 및 신호수 배치", "버킷 핀 안전핀 체결 확인 의무화", "후방가동 경보기 및 영상표지장치(CCTV/스마트감지기) 작동"]],
  ["덤프트럭", ["운전원 시야 확보 위한 신호수 배치 및 유도"]],
  ["불도저/ 로더", ["후진 경보기 및 후방 카메라 설치·점검", "운전원 시야 확보 위한 신호수 배치 및 유도"]],
  ["이동식크레인", ["지반 지지력 확보(철판 등) 및 아웃트리거 최대 인출"]],
  ["지게차", ["운전원 시야 확보(화물 높이 제한) 및 미확보 시 후진 운행 또는 신호수 동행"]],
  ["롤러", ["후방 카메라 및 접근 감지 센서 정상 작동 확인", "경사지 다짐 시 전복 방지 안전조치 및 무리한 단부 접근 금지"]],
  ["항타 및 항발기", ["작업 전 주 와이어로프, 장비 연결부 구조점검"]],
  ["레미콘", ["현장 내 전담 신호수 배치 및 유도 동선 확보", "경사지 정차 시 고임목 반드시 체결 및 주차브레이크 작동", "보안경, 화학물질 방호장갑 등 적절한 보호구 착용 의무화"]],
  ["콘크리트 펌프카", ["연약지반 지주판 설치 및 아웃트리거 완벽 인출", "압송관 관절부 안전핀 체결 및 레미콘 유입 전 공기압 체크"]],
  ["그 외 기계 장비", ["장비에 맞는 안전조치 확인"]],
];
const HAND_TOOL_ITEMS = [
  ["핸드그라인더 / 고속절단기", ["안전덮개 부착, 보호구(보안경, 방진마스크) 착용, 주변 가연물 제거"]],
  ["체인톱", ["체인 브레이크 점검, 안면보호구 및 절단방지용 보호복 착용"]],
  ["임팩트 드라이버 /전기드릴", ["회전 작업 시 면장갑 착용 금지(가죽장갑/밀착형 장갑 사용), 보조손잡이 활용"]],
  ["파쇄기", ["연속 작업 시간 제한(휴식시간 준수), 귀마개 및 보안경 착용, 전선 상태 점검"]],
  ["네일건 / 타카", ["안전장치(연동장치) 임의 해제 금지, 미사용 시 에어호스/가스 분리, 사람을 향해 겨누지 않기"]],
  ["철근 절곡기", ["외함접지 및 풋 스위치와 커버 배치 확인"]],
  ["믹서기", ["전선 절연 상태 확인"]],
  ["면삭기", ["방진마스크 등 개인보호구 착용"]],
];
const HAZMAT_ITEMS = [
  ["유기용제 및 도료·접착제(페인트, 신너, 에폭시, 우레탄 등)", ["국소배기장치 설치 및 주기적 환기", "화기 엄금 및 인화성 물질 별도 저장소 보관", "물질안전보건자료(MSDS) 비치 및 교육"]],
  ["시멘트 및 콘크리트 제품(시멘트 분진, 몰탈, 혼화제 등)", ["작업장 습식 작업 전환 및 분진 비산 방지", "작업 후 즉시 세정 (손세척장 마련)", "피부 직접 접촉 금지"]],
  ["용접 및 절단용 가스(아세틸렌, LPG, 산소 등)", ["용기 역화방지기(Flashback Arrestor) 설치", "용기 전도방지 조치 및 직사광선 차단", "가스 누출 점검(비눗물 등)"]],
  ["거푸집 박리제 및 세척제(폼유, 유기 세척제 등)", ["지정된 장소에서 분무 작업 실시", "화기 작업구역과 충분한 이격거리 확보", "작업장 주변 소화기 배치"]],
  ["단열재 및 섬유류(글라스울, 암면, 석면 등)", ["작업구역 밀폐 및 음압기 가동 (석면 작업 시)", "작업 후 폐기물 즉시 밀봉 처리", "자단 및 가공 시 전용 공구 사용 (비산 최소화)"]],
  ["밀폐공간 유해가스(일산화탄소, 황화수소 등)", ["작업 전 및 작업 중 산소/유해가스 농도 측정", "작업 전·작업 중 지속적인 강제 기", "감시인 배치 및 비상연락체계 구축"]],
  ["그 외 유해물질", ["물질에 맞는 안전조치 확인"]],
];
let currentMethod = "";
let currentAccidentStatus = "";
let siteId = null;
let pollTimer = null;
let notifySigField = null;

async function loadReport() {
  try {
    const report = await api(`/reports/${reportId}`);
    siteId = report.site_id;
    document.getElementById("back-link").href = `site.html?id=${siteId}`;
    document.getElementById("report-title").textContent = `${report.visit_no}회차 보고서`;
    // 경로 표시(현장 목록 / 현장명) — 실패해도 보고서 편집엔 지장 없으니 조용히 넘김
    api(`/sites/${siteId}`).then((site) => {
      document.getElementById("back-link").textContent = site.name;
    }).catch(() => {});
    document.getElementById("notify-signee").value = report.notify_signee_name || "";
    currentMethod = report.notification_method || "";
    renderMethodButtons();

    document.getElementById("misc-overwork").checked = !!report.misc_overwork;
    document.getElementById("misc-no-photo").checked = !!report.misc_no_photo;
    document.getElementById("misc-other").checked = !!report.misc_other;
    document.getElementById("misc-other-text").value = report.misc_other_text || "";
    currentAccidentStatus = report.accident_status || "";
    renderAccidentButtons();
    document.getElementById("accident-content").value = report.accident_content || "";

    renderMajorHazardList(report.major_hazard_work_checks || []);
    renderHazardFactorTable(report.hazard_factor_checks || []);
    renderEquipmentTable("equip-machinery", MACHINERY_EQUIPMENT_ITEMS, report.machinery_checks || []);
    renderEquipmentTable("equip-handtool", HAND_TOOL_ITEMS, report.hand_tool_checks || []);
    renderEquipmentTable("equip-hazmat", HAZMAT_ITEMS, report.hazmat_checks || []);
    // 현장책임자 서명 — signature.js: 페이지엔 미리보기만, [서명하기]/[수정]을 누르면 화면 가득 서명 창(폰 스크롤 간섭 없음),
    // 창에서 [완료]하면 바로 저장. 자동 저장과는 별개.
    notifySigField = createSignatureField(document.getElementById("notify-sig-field"), {
      imageUrl: `${BASE}/api/reports/${reportId}/notify-signature-image`,
      uploadUrl: `${BASE}/api/reports/${reportId}/notify-signature`,
      deleteUrl: `${BASE}/api/reports/${reportId}/notify-signature`,
      registered: !!report.notify_signature_path,
      title: "현장책임자 서명",
    });
    document.getElementById("visit-no").value = report.visit_no ?? "";
    document.getElementById("guidance-date").value = report.guidance_date || "";
    document.getElementById("progress-rate").value = report.progress_rate ?? "";
    document.getElementById("prev-guidance-date").value = report.prev_guidance_date || "";
    document.getElementById("prev-guidance-none").checked = !report.prev_guidance_date;
    document.getElementById("prev-guidance-date").disabled = !report.prev_guidance_date;
    await loadStaff(report.assigned_staff_id);
    await loadSignoffStatus();
  } catch (err) {
    showError(errorEl, err);
  }
}

function renderMethodButtons() {
  const row = document.getElementById("method-row");
  row.innerHTML = "";
  for (const method of NOTIFICATION_METHODS) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "method-btn" + (method === currentMethod ? " on" : "");
    btn.textContent = method;
    btn.addEventListener("click", () => {
      currentMethod = method;
      renderMethodButtons();
    });
    row.appendChild(btn);
  }
}

function renderAccidentButtons() {
  document.getElementById("accident-yes-btn").className = "method-btn" + (currentAccidentStatus === "유" ? " on" : "");
  document.getElementById("accident-no-btn").className = "method-btn" + (currentAccidentStatus === "무" ? " on" : "");
}
document.getElementById("accident-yes-btn").addEventListener("click", () => {
  currentAccidentStatus = "유";
  renderAccidentButtons();
});
document.getElementById("accident-no-btn").addEventListener("click", () => {
  currentAccidentStatus = "무";
  renderAccidentButtons();
});

document.getElementById("section2-save").addEventListener("click", async () => {
  errorEl.style.display = "none";
  const statusEl = document.getElementById("section2-status");
  try {
    await apiPatch(`${BASE}/api/reports/${reportId}`, {
        misc_overwork: document.getElementById("misc-overwork").checked,
        misc_no_photo: document.getElementById("misc-no-photo").checked,
        misc_other: document.getElementById("misc-other").checked,
        misc_other_text: document.getElementById("misc-other-text").value,
        accident_status: currentAccidentStatus,
        accident_content: document.getElementById("accident-content").value,
      });
    statusEl.textContent = "저장되었습니다.";
  } catch (err) {
    showError(errorEl, err);
  }
});

function renderMajorHazardList(checkedIndices) {
  const listEl = document.getElementById("major-hazard-list");
  const checkedSet = new Set(checkedIndices);
  listEl.innerHTML = "";
  MAJOR_HAZARD_WORKS.forEach((text, idx) => {
    const label = document.createElement("label");
    label.style.display = "block";
    label.innerHTML = `<input type="checkbox" data-idx="${idx}" ${checkedSet.has(idx) ? "checked" : ""} /> ${text}`;
    listEl.appendChild(label);
  });
}

document.getElementById("section5-save").addEventListener("click", async () => {
  errorEl.style.display = "none";
  const statusEl = document.getElementById("section5-status");
  const checked = Array.from(document.querySelectorAll("#major-hazard-list input[type=checkbox]:checked")).map(
    (el) => Number(el.dataset.idx)
  );
  try {
    await apiPatch(`${BASE}/api/reports/${reportId}`, { major_hazard_work_checks: checked });
    statusEl.textContent = "저장되었습니다.";
  } catch (err) {
    showError(errorEl, err);
  }
});

function renderHazardFactorTable(checkedList) {
  const checkedSet = new Set(checkedList);
  const listEl = document.getElementById("hazard-factor-list");
  listEl.innerHTML = "";
  for (const [number, name, lines] of FIXED_HAZARD_FACTORS) {
    const row = document.createElement("div");
    row.className = "hazard-row";
    let html = `<label><input type="checkbox" class="hf-factor" data-value="${number}" ${checkedSet.has(String(number)) ? "checked" : ""} /> <b>${number}. ${name}</b></label>`;
    lines.forEach((line, idx) => {
      const value = `${number}-${idx}`;
      html += `<label class="line-check"><input type="checkbox" class="hf-line" data-value="${value}" ${checkedSet.has(value) ? "checked" : ""} /> ${line}</label>`;
    });
    row.innerHTML = html;
    // 기인물을 체크하면 그 필수 지도사항 줄이 전부 같이 체크되고, 해제하면 같이 해제(데스크톱과 같음, 2026-09-30) — 그 뒤 줄 단위로 따로 고칠 수 있다.
    // 사용자가 누를 때(change)만 — 저장된 값을 그릴 때는 발동 안 함. 자동 저장(문서 전체 change)은 이 처리 다음에 돌아 줄 체크까지 저장된다.
    row.querySelector(".hf-factor").addEventListener("change", (e) => {
      row.querySelectorAll(".hf-line").forEach((box) => { box.checked = e.target.checked; });
    });
    listEl.appendChild(row);
  }
}

document.getElementById("section6-save").addEventListener("click", async () => {
  errorEl.style.display = "none";
  const statusEl = document.getElementById("section6-status");
  const checked = Array.from(
    document.querySelectorAll("#hazard-factor-list input[type=checkbox]:checked")
  ).map((el) => el.dataset.value);
  try {
    await apiPatch(`${BASE}/api/reports/${reportId}`, { hazard_factor_checks: checked });
    statusEl.textContent = "저장되었습니다.";
  } catch (err) {
    showError(errorEl, err);
  }
});

// 6-3. 건설기계장비/위험기계기구/유해위험물질 — 완전히 같은 모양(유무 체크 + 줄별 양호/미흡)이라
// 렌더링·수집 함수를 공용으로 쓴다.
function renderEquipmentTable(containerId, items, saved) {
  const container = document.getElementById(containerId);
  container.innerHTML = "";
  items.forEach(([name, lines], idx) => {
    const entry = saved[idx] || {};
    const notes = entry.notes || [];
    const row = document.createElement("div");
    row.className = "equip-row";
    row.dataset.idx = idx;
    let html = `<div class="equip-name"><label><input type="checkbox" class="eq-flag" ${entry.checked ? "checked" : ""} /> ${name}</label></div>`;
    lines.forEach((line, lineIdx) => {
      const current = notes[lineIdx] || "";
      html += `<div class="equip-line"><span>${line}</span><span class="eval-btns" data-line="${lineIdx}">`;
      for (const label of ["양호", "미흡"]) {
        html += `<button type="button" class="eval-btn${current === label ? " on" : ""}" data-label="${label}">${label}</button>`;
      }
      html += `</span></div>`;
    });
    row.innerHTML = html;
    container.appendChild(row);

    const flagCheckbox = row.querySelector(".eq-flag");
    row.querySelectorAll(".eval-btns").forEach((btnGroup) => {
      const buttons = btnGroup.querySelectorAll(".eval-btn");
      buttons.forEach((btn) => {
        btn.addEventListener("click", () => {
          const alreadyOn = btn.classList.contains("on");
          buttons.forEach((b) => b.classList.remove("on"));
          if (!alreadyOn) {
            btn.classList.add("on");
            flagCheckbox.checked = true; // 평가를 고르면 유무 자동 체크(데스크톱과 동일)
          } else if (!row.querySelector(".eval-btn.on")) {
            flagCheckbox.checked = false; // 전부 해제하면 유무도 자동 해제
          }
        });
      });
    });
  });
}

function collectEquipmentTable(containerId) {
  const rows = Array.from(document.querySelectorAll(`#${containerId} .equip-row`));
  return rows.map((row) => {
    const checked = row.querySelector(".eq-flag").checked;
    const notes = Array.from(row.querySelectorAll(".eval-btns")).map((btnGroup) => {
      const on = btnGroup.querySelector(".eval-btn.on");
      return on ? on.dataset.label : "";
    });
    return { checked, notes };
  });
}

document.getElementById("section6-3-save").addEventListener("click", async () => {
  errorEl.style.display = "none";
  const statusEl = document.getElementById("section6-3-status");
  try {
    await apiPatch(`${BASE}/api/reports/${reportId}`, {
        machinery_checks: collectEquipmentTable("equip-machinery"),
        hand_tool_checks: collectEquipmentTable("equip-handtool"),
        hazmat_checks: collectEquipmentTable("equip-hazmat"),
      });
    statusEl.textContent = "저장되었습니다.";
  } catch (err) {
    showError(errorEl, err);
  }
});

// 담당요원 드롭다운 — 이 보고서 지도일 기준 "이미 맡은 다른 현장 수/4"를 이름 옆에 붙인다(하루 4현장 한도,
// 데스크톱 report_wizard_staff_limit.py와 같은 표시). 실제 막는 건 서버(PATCH가 400으로 거부).
let staffSelectedId = null;
async function loadStaff(selectedId) {
  const select = document.getElementById("staff-select");
  if (selectedId !== undefined) staffSelectedId = selectedId;
  try {
    const [staffList, load] = await Promise.all([api("/staff"), api(`/reports/${reportId}/staff-load`)]);
    const byId = Object.fromEntries(load.items.map((it) => [it.staff_id, it]));
    select.innerHTML = '<option value="">선택 안 함</option>';
    for (const s of staffList) {
      const opt = document.createElement("option");
      const l = byId[s.id];
      opt.value = s.id;
      opt.textContent = `${s.name} (${s.phone})` + staffLoadLabel(s.id, l, load.max);
      if (staffSelectedId && s.id === staffSelectedId) opt.selected = true;
      select.appendChild(opt);
    }
  } catch (err) {
    showError(errorEl, err);
  }
}

// "권태형 · 9/29 4/4곳 (마감)" — 그날(이 보고서 지도일) 방문하는 현장 수. 이 보고서를 맡은 사람은 이 현장까지 넣어 센다
// (예전엔 "다른 현장 수/4"라 이미 4곳인 사람이 "3/4"로 보여 헷갈렸음 — 2026-09-29 사용자). 다른 사람은 그날 이미 맡은 수만,
// 4곳이면 "(마감)" — 고르면 서버가 거부한다(하루 4현장 한도).
function staffLoadLabel(staffId, loadItem, max) {
  const date = document.getElementById("guidance-date").value;
  if (!date) return "";
  const mine = staffSelectedId && staffId === staffSelectedId;
  const others = loadItem ? loadItem.count : 0;
  const total = others + (mine ? 1 : 0);
  if (!total) return "";
  const full = mine ? total >= max : others >= max;
  return ` · ${Number(date.slice(5, 7))}/${Number(date.slice(8, 10))} ${total}/${max}곳${full ? " (마감)" : ""}`;
}

async function loadSignoffStatus() {
  try {
    const status = await api(`/reports/${reportId}/signoff-status`);
    setStatusCard("staff-sig-status", status.staff_signed, "미등록 — 왼쪽 '담당요원' 메뉴에서 등록");
    setStatusCard("director-sig-status", status.director_signed, "미등록 — 왼쪽 '설정' 메뉴에서 등록");
    setStatusCard("ceo-sig-status", status.ceo_signed, "미등록 — 왼쪽 '설정' 메뉴에서 등록");
  } catch (err) {
    showError(errorEl, err);
  }
}

function setStatusCard(id, ok, badText) {
  const el = document.getElementById(id);
  el.textContent = ok ? "✓ 등록됨" : badText;
  el.className = ok ? "ok" : "bad";
}

// --- 기본 정보(회차/지도일/이전 지도일/공정률) ---
document.getElementById("prev-guidance-none").addEventListener("change", (e) => {
  const input = document.getElementById("prev-guidance-date");
  input.disabled = e.target.checked;
  if (e.target.checked) input.value = "";
});
document.getElementById("basic-save").addEventListener("click", async () => {
  errorEl.style.display = "none";
  const st = document.getElementById("basic-status");
  const visitNo = document.getElementById("visit-no").value;
  const progress = document.getElementById("progress-rate").value;
  const prevNone = document.getElementById("prev-guidance-none").checked;
  try {
    const out = await apiPatch(`${BASE}/api/reports/${reportId}`, {
      visit_no: visitNo ? Number(visitNo) : undefined,
      guidance_date: document.getElementById("guidance-date").value || null,
      prev_guidance_date: prevNone ? null : (document.getElementById("prev-guidance-date").value || null),
      progress_rate: progress === "" ? null : Number(progress),
    });
    document.getElementById("report-title").textContent = `${out.visit_no}회차 보고서`;
    await loadStaff(); // 지도일이 바뀌면 요원별 "n/4" 표시도 다시 계산
    st.className = "status ok";
    st.textContent = "저장되었습니다.";
  } catch (err) {
    st.textContent = "";
    showError(errorEl, err);
  }
});

document.getElementById("staff-select").addEventListener("change", async (e) => {
  errorEl.style.display = "none";
  const value = e.target.value ? Number(e.target.value) : null;
  try {
    await apiPatch(`${BASE}/api/reports/${reportId}`, { assigned_staff_id: value });
    staffSelectedId = value;
    await Promise.all([loadSignoffStatus(), loadStaff()]); // 이 현장 포함 개수가 사람마다 달라지므로 다시 표시
  } catch (err) {
    e.target.value = staffSelectedId ?? ""; // 하루 4현장 마감 등으로 거부되면 직전 선택으로 되돌림
    showError(errorEl, err);
  }
});

document.getElementById("section1-save").addEventListener("click", async () => {
  errorEl.style.display = "none";
  const statusEl = document.getElementById("section1-status");
  try {
    const staffVal = document.getElementById("staff-select").value;
    await apiPatch(`${BASE}/api/reports/${reportId}`, {
        assigned_staff_id: staffVal ? Number(staffVal) : null,
        notification_method: currentMethod,
        notify_signee_name: document.getElementById("notify-signee").value,
      });
    statusEl.textContent = "저장되었습니다.";
  } catch (err) {
    showError(errorEl, err);
  }
});
