// staff.html — 그룹웨어 직원정보로 담당요원 관리(2026-09-30). 그룹웨어 `/report-shell/employees`(같은 도메인, 그룹웨어 로그인)에서
// 직원 목록을 받아 보고서 서버(/staff-groupware/sync)로 보내 이어 붙이고, 직원마다 [담당요원] 체크 + 서명만 여기서 관리한다.
// 이름·연락처·메일은 그룹웨어 값을 따라간다(고치는 곳은 그룹웨어 관리자 메뉴 → 직원정보).
// 그룹웨어 목록이나 새 API를 못 쓰면(사무실 LAN 직접 접속, 배포 전 등) false를 돌려주고 staff.html이 예전 화면을 그린다.

async function fetchGroupwareEmployees() {
  try {
    const res = await fetch("/report-shell/employees", { credentials: "include", redirect: "manual" });
    if (!res.ok || !(res.headers.get("content-type") || "").includes("json")) return null;
    const list = await res.json();
    return Array.isArray(list) ? list : null;
  } catch (_) {
    return null;
  }
}

async function initGroupwareStaff() {
  const employees = await fetchGroupwareEmployees();
  if (!employees) return false;
  let view;
  try {
    view = await apiPost("/staff-groupware/sync", { employees });
  } catch (_) {
    return false; // 보고서 서버가 아직 예전 버전 — 예전 화면으로
  }
  document.querySelector(".tab-intro").textContent =
    "그룹웨어 직원정보에서 가져온 목록입니다. [담당요원]을 체크한 사람만 보고서·현장 배정에 나옵니다. " +
    "이름·연락처·메일은 그룹웨어 관리자 메뉴 → 직원정보에서 고치면 여기도 따라 바뀝니다. 서명은 여기서 등록하세요.";
  renderGroupwareStaff(view, employees);
  return true;
}

async function reloadGroupwareStaff() {
  errorEl.style.display = "none";
  const employees = await fetchGroupwareEmployees();
  if (!employees) {
    showError(errorEl, new Error("그룹웨어 직원 목록을 불러오지 못했습니다. 잠시 후 새로고침하세요."));
    return;
  }
  try {
    renderGroupwareStaff(await apiPost("/staff-groupware/sync", { employees }), employees);
    window.reloadReportOrder?.(); // 요원이 늘거나 쉬게 되면 보고서 담당 순서도(js/staff-order.js)
  } catch (err) {
    showError(errorEl, err);
  }
}

function renderGroupwareStaff(view, employees) {
  const list = document.getElementById("staff-list");
  const head = list.closest(".panel").querySelector(".panel-head h2");
  const staffCount = view.employees.filter((e) => e.is_staff).length;
  head.textContent = `그룹웨어 직원 (담당요원 ${staffCount}명 / 전체 ${view.employees.length}명)`;
  list.innerHTML = view.employees.length ? "" : '<div class="empty-note">그룹웨어 직원정보에 등록된 직원이 없습니다.</div>';
  // 담당요원 먼저, 그다음 부서·이름 순
  const rows = [...view.employees].sort((a, b) =>
    (b.is_staff - a.is_staff) || a.department.localeCompare(b.department, "ko") || a.name.localeCompare(b.name, "ko"));
  for (const e of rows) list.appendChild(gwStaffRow(e));
  if (typeof decorateK2b === "function") decorateK2b(list); // 요원마다 K2B 계정 표시·[K2B 계정](js/staff-k2b.js)

  const unlinkedPanel = document.getElementById("unlinked-panel");
  const free = view.employees.filter((e) => e.staff_id == null);
  unlinkedPanel.hidden = !view.unlinked_staff.length;
  const ul = document.getElementById("unlinked-list");
  ul.innerHTML = "";
  for (const s of view.unlinked_staff) ul.appendChild(unlinkedRow(s, free, employees));
}

function gwStaffRow(e) {
  const wrap = document.createElement("div");
  wrap.className = "staff-item" + (e.is_staff ? "" : " gw-off");
  if (e.is_staff) wrap.dataset.staffId = e.staff_id; // K2B 계정 표시(js/staff-k2b.js decorateK2b)가 찾는 표시
  wrap.innerHTML = `
    <div class="row staff-row">
      <label class="gw-check"><input type="checkbox" ${e.is_staff ? "checked" : ""} /> 담당요원</label>
      <span class="title staff-name"><b class="gw-name"></b><span class="gw-sub"></span>${e.is_staff ? '<span class="k2b-chip"></span>' : ""}</span>
      ${e.is_staff ? (e.has_signature
        ? `<img class="sig-thumb" alt="" src="${BASE}/api/staff/${e.staff_id}/signature?ts=${Date.now()}" />`
        : '<span class="sig-thumb empty">서명 없음</span>') : ""}
      <span class="staff-actions">${e.is_staff ? '<button type="button" class="secondary st-edit">서명</button><button type="button" class="secondary k2b-btn" hidden>K2B 계정</button>' : ""}</span>
    </div>
    <div class="st-panel" hidden></div>
    <div class="k2b-panel" hidden></div>`;
  wrap.querySelector(".gw-name").textContent = e.name + (e.is_me ? " (나)" : "");
  wrap.querySelector(".gw-sub").textContent = [
    [e.department, e.position].filter(Boolean).join(" "), e.phone, e.email, e.username ? "" : "그룹웨어 계정 없음",
  ].filter(Boolean).join(" · ");
  const thumb = wrap.querySelector("img.sig-thumb");
  if (thumb) thumb.alt = `${e.name} 서명`;

  const box = wrap.querySelector(".gw-check input");
  box.addEventListener("change", async () => {
    errorEl.style.display = "none";
    if (!box.checked && !confirm(`${e.name}님을 담당요원에서 뺄까요? 이미 만든 보고서의 담당요원·서명은 그대로 남고, 새 보고서·현장 배정 목록에서만 빠집니다.`)) {
      box.checked = true;
      return;
    }
    box.disabled = true;
    try {
      await apiPost("/staff-groupware/check", { employee: pickEmployee(e), on: box.checked });
      await reloadGroupwareStaff();
    } catch (err) {
      box.checked = !box.checked;
      showError(errorEl, err);
    } finally {
      box.disabled = false;
    }
  });

  const editBtn = wrap.querySelector(".st-edit");
  if (editBtn) {
    const panel = wrap.querySelector(".st-panel");
    let sigField = null;
    const close = () => {
      if (sigField && sigField.isDirty() && !confirm("저장하지 않은 서명 변경이 있습니다. 닫을까요?")) return;
      panel.hidden = true;
      panel.innerHTML = "";
      sigField = null;
      editBtn.textContent = "서명";
    };
    editBtn.addEventListener("click", () => {
      if (!panel.hidden) return close();
      panel.hidden = false;
      editBtn.textContent = "닫기";
      panel.innerHTML = `<label>서명</label><div class="e-sig"></div>
        <div class="edit-actions"><button type="button" class="e-save">저장</button>
        <button type="button" class="secondary e-cancel">취소</button></div>`;
      sigField = createSignatureField(panel.querySelector(".e-sig"), {
        imageUrl: `${BASE}/api/staff/${e.staff_id}/signature`,
        uploadUrl: `${BASE}/api/staff/${e.staff_id}/signature`,
        deleteUrl: `${BASE}/api/staff/${e.staff_id}/signature`,
        registered: e.has_signature,
        standalone: false,
        title: `${e.name} 서명`,
      });
      panel.querySelector(".e-cancel").addEventListener("click", close);
      panel.querySelector(".e-save").addEventListener("click", async (ev) => {
        errorEl.style.display = "none";
        ev.target.disabled = true;
        try {
          if (!(await sigField.save())) return;
          sigField = null;
          reloadGroupwareStaff();
        } catch (err) {
          showError(errorEl, err);
        } finally {
          ev.target.disabled = false;
        }
      });
    });
  }
  return wrap;
}

// 그룹웨어 직원과 안 이어진 담당요원(이름이 달라 자동으로 못 이음, 또는 그룹웨어에서 사라짐) — 직접 잇거나, 필요 없으면 삭제.
function unlinkedRow(s, free, employees) {
  const wrap = document.createElement("div");
  wrap.className = "staff-item";
  wrap.innerHTML = `
    <div class="row staff-row">
      <span class="title staff-name"><b class="gw-name"></b><span class="gw-sub"></span></span>
      ${s.active ? "" : '<span class="status-pill rejected">비활성</span>'}
      <span class="staff-actions">
        <select class="gw-pick"><option value="">그룹웨어 직원 고르기…</option></select>
        <button type="button" class="secondary gw-link">잇기</button>
        <button type="button" class="secondary st-del" style="color:var(--crit);">삭제</button>
      </span>
    </div>`;
  wrap.querySelector(".gw-name").textContent = s.name;
  wrap.querySelector(".gw-sub").textContent = s.gone ? "그룹웨어 직원정보에서 사라졌습니다" : "그룹웨어에서 같은 이름을 못 찾았습니다";
  const pick = wrap.querySelector(".gw-pick");
  for (const e of free) {
    const o = document.createElement("option");
    o.value = e.id;
    o.textContent = [e.name, e.department].filter(Boolean).join(" · ");
    pick.appendChild(o);
  }
  wrap.querySelector(".gw-link").addEventListener("click", async () => {
    const emp = employees.find((e) => String(e.id) === pick.value);
    if (!emp) { alert("이을 그룹웨어 직원을 고르세요."); return; }
    if (!confirm(`${s.name} 담당요원을 그룹웨어 직원 ${emp.name}님과 이을까요? 이름·연락처·메일이 그룹웨어 값으로 바뀌고, 지금까지의 보고서·서명은 그대로 이어집니다.`)) return;
    errorEl.style.display = "none";
    try {
      await apiPost(`/staff-groupware/link/${s.id}`, { employee: pickEmployee(emp) });
      reloadGroupwareStaff();
    } catch (err) {
      showError(errorEl, err);
    }
  });
  wrap.querySelector(".st-del").addEventListener("click", async () => {
    if (!confirm(`${s.name} 요원을 삭제할까요? 이미 배정된 현장/보고서에서는 담당요원이 빈 값이 됩니다.`)) return;
    errorEl.style.display = "none";
    try {
      await api(`/staff/${s.id}`, { method: "DELETE" });
      reloadGroupwareStaff();
    } catch (err) {
      showError(errorEl, err);
    }
  });
  return wrap;
}

function pickEmployee(e) {
  const { id, name, department, position, phone, email, username, loginEnabled } = e;
  return { id, name, department, position, phone, email, username, loginEnabled };
}
