// ---------- K2B 제출 창(현장 화면 보고서 줄 [📤 K2B 제출], 2026-10-01 — server/api/routers/k2b_submit.py) ----------
// 위: 보고서에서 가져가는 값(확인용) + 담당요원 K2B 계정. 가운데: K2B 전용 항목(현재 작업공종·비계는 K2B 필수, 대형사고 위험작업 줄 추가 —
// 없으면 "해당없음", 불량사업장 통보 + 첨부). [K2B에 제출] → 대기열 → 이 PC가 K2B에 새 차수로 입력·저장 → 저장된 화면 사진.
// K2B가 매긴 새 차수가 웹 회차와 다르면 저장하지 않고 멈춤(사용자: 실제 업무에선 같아야 함) — "차수가 달라도 저장"을 켜고 다시 낼 수 있다.
// 창 틀은 css/mail.css, 이 창 규칙은 css/k2b-submit.css. 글자 넣기는 mail.js의 mailEsc.

async function openK2bModal(reportId, titleText, onDone) {
  const overlay = document.createElement("div");
  overlay.className = "mail-overlay";
  overlay.innerHTML = '<div class="mail-box kb-box" role="dialog" aria-modal="true"><div class="mail-wait">불러오는 중…</div></div>';
  document.body.appendChild(overlay);
  const box = overlay.querySelector(".mail-box");
  let busy = false;
  let changed = false;
  const close = () => {
    if (busy && !confirm("K2B 제출은 이 창을 닫아도 계속 진행됩니다. 닫을까요? (결과는 보고서 줄에 나옵니다)")) return;
    overlay.remove();
    document.removeEventListener("keydown", onKey);
    if (changed && onDone) onDone();
  };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  const head = `<div class="mail-head"><b>📤 K2B 제출</b><span class="mail-sub">${mailEsc(titleText)}</span></div>`;

  let info;
  try {
    info = await api(`/reports/${reportId}/k2b`);
  } catch (err) {
    box.innerHTML = `${head}<div class="mail-msg bad">${mailEsc(err.message)}</div><div class="mail-foot"><button type="button" class="kb-close">닫기</button></div>`;
    box.querySelector(".kb-close").addEventListener("click", close);
    return;
  }
  const running = info.jobs.find((j) => j.status === "queued" || j.status === "running");
  if (running) return watch(running.id);
  drawForm();

  function drawForm(prefill) {
    const s = info.summary;
    const lastDone = info.jobs.find((j) => j.status === "done");
    const last = prefill || (info.jobs[0] && info.jobs[0].options) || {};
    const acc = info.account;
    const accText = acc.k2b_id
      ? `${mailEsc(s.staff_name)} · ${mailEsc(acc.k2b_id)} ${acc.check_status === "ok" ? "✓ 로그인 확인" : acc.check_status === "fail" ? "✗ 로그인 실패" : "(확인 전)"}`
      : `${mailEsc(s.staff_name || "담당요원 없음")} · K2B 계정 없음`;
    const photos = Object.entries(s.photos).filter(([, n]) => n).map(([k, n]) => `${k} ${n}`).join(" · ") || "없음";
    const counts = Object.entries(s.counts).map(([k, n]) => `${k} ${n ?? "비움"}`).join(" · ");
    box.innerHTML = `${head}
      ${info.blockers.length ? `<div class="mail-msg bad">${info.blockers.map(mailEsc).join("<br>")}</div>` : ""}
      ${lastDone ? `<div class="mail-msg warn">이미 ${mailEsc(lastDone.finished_at)}에 K2B ${lastDone.round_no ?? ""}차수로 제출했습니다. 다시 내면 K2B에 차수가 하나 더 생깁니다.
        <label class="kb-again"><input type="checkbox" class="kb-again-chk" /> 알고 다시 제출합니다</label></div>` : ""}
      <div class="mail-label">보고서에서 가져가는 값</div>
      <div class="mail-info kb-info">
        <div><span>K2B 검색</span><div><b>${mailEsc(s.search_word)}</b> → ${mailEsc(s.site_name)}</div></div>
        <div><span>회차</span><div>${s.visit_no}회차 · 지도일 ${mailEsc(s.guidance_date || "없음")} → K2B 새 차수</div></div>
        <div><span>점검자</span><div>${accText}</div></div>
        <div><span>공정률</span><div>${s.progress_rate ?? "없음"}% · 통보 ${mailEsc(s.notification_method || "없음")}</div></div>
        <div><span>현장책임자</span><div>${mailEsc(s.site_manager || "없음")}</div></div>
        <div><span>건수</span><div>${mailEsc(counts)}</div></div>
        <div><span>문제점·개선</span><div>${s.problems ? `8번 지적사항 ${s.problems}건 (제목 + 내용)` : "없음"}</div></div>
        <div><span>사진</span><div>${mailEsc(photos)}</div></div>
        <div><span>보고서</span><div>${mailEsc(s.pdf || "PDF 없음")}</div></div>
      </div>
      <div class="mail-label">K2B 전용 항목 <span class="mail-note">(보고서에 없는 값 — 직접 고르세요)</span></div>
      <div class="kb-grid">
        <label class="kb-field"><span>현재 작업공종 <em>필수</em></span>
          <select class="kb-process"><option value="">고르세요</option>${info.choices.current_process.map((p) => `<option>${mailEsc(p)}</option>`).join("")}</select></label>
        <label class="kb-field"><span>이전 기술지도 이행여부 <em>필수</em></span>
          <select class="kb-prev"><option value="">고르세요</option><option>이행</option><option>불이행</option><option>해당없음</option></select>
          <span class="mail-note ${s.prev_guidance_default ? "" : "kb-warn"}">${mailEsc(s.prev_guidance_reason)}</span>
          <span class="mail-note">해당없음은 K2B 1차수에서만 됩니다</span></label>
        <div class="kb-field"><span>비계 사용 <em>필수</em></span>
          <div class="kb-radios"><label><input type="radio" name="kb-scaffold" value="미사용" /> 미사용</label>
            <label><input type="radio" name="kb-scaffold" value="사용" /> 사용</label>
            <span class="kb-types">${info.choices.scaffold_types.map((t) => `<label><input type="checkbox" class="kb-type" value="${mailEsc(t)}" /> ${mailEsc(t)}</label>`).join("")}</span></div></div>
      </div>
      <div class="kb-field"><span>대형사고 위험작업 <span class="mail-note">— 없으면 K2B에 "해당없음"으로 올라갑니다</span></span>
        <div class="kb-hazards"></div>
        <button type="button" class="kb-add">+ 위험작업 추가</button></div>
      <label class="kb-check"><input type="checkbox" class="kb-bad" /> 불량사업장 통보</label>
      <div class="kb-bad-box" hidden>
        <textarea class="mail-input kb-bad-text" rows="3" placeholder="신고내용"></textarea>
        <input type="file" class="kb-bad-files" multiple accept=".jpg,.jpeg,.png,.gif,.bmp,.pdf" />
      </div>
      <label class="kb-check kb-mismatch" hidden><input type="checkbox" class="kb-allow" /> K2B 차수가 웹 회차와 달라도 저장</label>
      <div class="mail-msg kb-msg" hidden></div>
      <div class="mail-foot"><button type="button" class="kb-close">닫기</button>
        <button type="button" class="mail-primary kb-go" ${info.blockers.length ? "disabled" : ""}>K2B에 제출</button></div>
      <div class="kb-hint">이 PC가 K2B에 담당요원 계정으로 들어가 <b>새 차수</b>로 입력하고 <b>저장</b>까지 합니다(1~2분). 저장된 K2B 화면을 사진으로 남깁니다.</div>`;
    const $ = (q) => box.querySelector(q);
    const msg = $(".kb-msg");
    $(".kb-close").addEventListener("click", close);
    $(".kb-process").value = last.current_process || "";
    $(".kb-prev").value = prefill && prefill.prev_needs_choice ? "" : (prefill && prefill.prev_guidance) || s.prev_guidance_default || "";
    if (prefill && prefill.prev_needs_choice) {
      $(".kb-prev").classList.add("kb-need");
      $(".kb-msg").hidden = false;
      $(".kb-msg").className = "mail-msg kb-msg bad";
      $(".kb-msg").textContent = "K2B 차수가 2 이상이라 '해당없음'은 안 됩니다 — 이전 기술지도 이행여부를 '이행' 또는 '불이행'으로 고르세요.";
    }
    const radios = [...box.querySelectorAll('input[name="kb-scaffold"]')];
    const types = [...box.querySelectorAll(".kb-type")];
    const syncTypes = () => {
      const on = radios.find((r) => r.checked)?.value === "사용";
      types.forEach((t) => { t.disabled = !on; if (!on) t.checked = false; });
    };
    radios.forEach((r) => { r.checked = r.value === last.scaffold_usage; r.addEventListener("change", syncTypes); });
    types.forEach((t) => { t.checked = (last.scaffold_types || []).includes(t.value); });
    syncTypes();
    const hazards = $(".kb-hazards");
    const addHazard = (h = {}) => {
      const row = document.createElement("div");
      row.className = "kb-hazard";
      const occ = Object.keys(info.choices.hazard_by_occurrence);
      row.innerHTML = `<select class="kb-occ">${occ.map((o) => `<option>${mailEsc(o)}</option>`).join("")}</select>
        <select class="kb-work"></select>
        <span class="kb-dates"><input type="date" class="kb-start" /> ~ <input type="date" class="kb-end" /></span>
        <button type="button" class="kb-del" aria-label="이 줄 빼기">✕</button>`;
      const occSel = row.querySelector(".kb-occ");
      const workSel = row.querySelector(".kb-work");
      const fill = () => {
        workSel.innerHTML = info.choices.hazard_by_occurrence[occSel.value].map((w) => `<option>${mailEsc(w)}</option>`).join("");
      };
      occSel.value = h.occurrence_type || "전체";
      fill();
      if (h.hazard_work) workSel.value = h.hazard_work;
      occSel.addEventListener("change", fill);
      row.querySelector(".kb-start").value = h.start_date || "";
      row.querySelector(".kb-end").value = h.end_date || "";
      row.querySelector(".kb-del").addEventListener("click", () => row.remove());
      hazards.appendChild(row);
    };
    (last.major_hazard_works || []).forEach(addHazard);
    $(".kb-add").addEventListener("click", () => addHazard());
    const bad = $(".kb-bad");
    bad.checked = !!last.bad_site_notify;
    $(".kb-bad-text").value = last.bad_site_content || "";
    const syncBad = () => { $(".kb-bad-box").hidden = !bad.checked; };
    bad.addEventListener("change", syncBad);
    syncBad();
    // "차수가 달라도 저장"은 차수가 달라 멈춘 뒤 [다시 제출]로 왔을 때만 보인다(처음부터 켜 두지 않게)
    $(".kb-mismatch").hidden = !(prefill && prefill.allow_round_mismatch);
    $(".kb-allow").checked = !!(prefill && prefill.allow_round_mismatch);

    $(".kb-go").addEventListener("click", async (ev) => {
      const show = (cls, text) => { msg.hidden = false; msg.className = `mail-msg kb-msg ${cls}`; msg.textContent = text; };
      if (lastDone && !$(".kb-again-chk").checked) {
        show("bad", "이미 제출한 회차입니다 — 다시 내려면 위의 '알고 다시 제출합니다'를 체크하세요.");
        return;
      }
      const options = {
        current_process: $(".kb-process").value,
        prev_guidance: $(".kb-prev").value,
        scaffold_usage: radios.find((r) => r.checked)?.value || "",
        scaffold_types: types.filter((t) => t.checked).map((t) => t.value),
        major_hazard_works: [...hazards.querySelectorAll(".kb-hazard")].map((r) => ({
          occurrence_type: r.querySelector(".kb-occ").value, hazard_work: r.querySelector(".kb-work").value,
          start_date: r.querySelector(".kb-start").value, end_date: r.querySelector(".kb-end").value,
        })),
        bad_site_notify: bad.checked,
        bad_site_content: $(".kb-bad-text").value.trim(),
        allow_round_mismatch: $(".kb-allow").checked,
      };
      if (!options.current_process) return show("bad", "현재 작업공종을 고르세요(K2B 필수).");
      if (!options.prev_guidance) return show("bad", "이전 기술지도 이행여부를 고르세요(K2B 필수).");
      if (!options.scaffold_usage) return show("bad", "비계 사용 여부를 고르세요(K2B 필수).");
      if (!confirm(`K2B에 ${info.summary.site_name} ${info.summary.visit_no}회차를 새 차수로 저장합니다. 진행할까요?`)) return;
      const fd = new FormData();
      fd.append("options", JSON.stringify(options));
      if (bad.checked) [...$(".kb-bad-files").files].forEach((f) => fd.append("files", f));
      ev.target.disabled = true;
      try {
        const job = await apiUpload(`/reports/${reportId}/k2b`, fd);
        changed = true;
        watch(job.id, options);
      } catch (err) {
        show("bad", err.message);
        ev.target.disabled = false;
      }
    });
  }

  // 진행 상황 — 2초마다. 끝나면 결과(성공: 저장된 K2B 화면 / 실패: 이유 + 화면 + 다시 내기)
  async function watch(jobId, options) {
    busy = true;
    changed = true;
    const started = Date.now();
    box.innerHTML = `${head}<div class="mail-msg kb-progress">K2B 제출 준비 중…</div>
      <div class="mail-foot"><button type="button" class="kb-close">창 닫기(계속 진행)</button></div>`;
    box.querySelector(".kb-close").addEventListener("click", close);
    const line = box.querySelector(".kb-progress");
    for (;;) {
      let job;
      try {
        job = await api(`/k2b-jobs/${jobId}`);
      } catch (err) {
        line.textContent = `상태를 못 읽었습니다(${err.message}) — 잠시 뒤 다시 확인합니다.`;
        await new Promise((r) => setTimeout(r, 4000));
        continue;
      }
      const sec = Math.round((Date.now() - started) / 1000);
      if (job.status === "queued") line.textContent = `대기 중… ${job.ahead ? `(앞에 ${job.ahead}건)` : ""} ${sec}초`;
      else if (job.status === "running") line.textContent = `K2B에 입력하고 저장하는 중… ${sec}초 (보통 1~2분, 창을 닫아도 계속됩니다)`;
      else {
        busy = false;
        return drawResult(job, options);
      }
      if (!document.body.contains(overlay)) return;
      await new Promise((r) => setTimeout(r, 2000));
    }
  }

  function drawResult(job, options) {
    const ok = job.status === "done";
    const mismatch = !ok && /차수는 .*회차라 저장하지 않았습니다/.test(job.message);
    box.innerHTML = `${head}
      <div class="mail-msg ${ok ? "ok" : "bad"}">${ok ? "✓ " : "✗ "}${mailEsc(job.message)}</div>
      ${job.has_shot ? `<a class="kb-shot" href="${BASE}/api/k2b-jobs/${job.id}/shot?ts=${Date.now()}" target="_blank" rel="noopener">
        <img src="${BASE}/api/k2b-jobs/${job.id}/shot?ts=${Date.now()}" alt="K2B 화면" /><span>눌러서 크게 보기</span></a>` : ""}
      <div class="mail-foot"><button type="button" class="kb-close">닫기</button>
        ${ok ? "" : `<button type="button" class="mail-primary kb-retry">${mismatch ? "차수가 달라도 저장하고 다시 제출" : "고쳐서 다시 제출"}</button>`}</div>`;
    box.querySelector(".kb-close").addEventListener("click", close);
    box.querySelector(".kb-retry")?.addEventListener("click", async () => {
      info = await api(`/reports/${reportId}/k2b`);
      const prevBad = /해당없음.*낼 수 없습니다|통보여부를 선택/.test(job.message); // 해당없음을 못 받는 차수 — 이행여부를 다시 고르게 비움
      drawForm({ ...(options || job.options || {}), allow_round_mismatch: mismatch || !!((options || job.options || {}).allow_round_mismatch),
        ...(prevBad ? { prev_guidance: "", prev_needs_choice: true } : {}) });
    });
  }
}
