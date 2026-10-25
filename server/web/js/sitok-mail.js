// 시특법 회차 화면 "📧 보고서 보내기" 칸(2026-10-25 민재형 "시특법에 메일 기능", 방식 = 내려받기 링크 — 사용자 "1번이지 당연히").
// 합본 PDF가 커서(96MB) 첨부 대신 기한 있는 내려받기 링크를 메일로. [📧 지금 보내기] 또는 [⏰ 예약 보내기](날짜·시각 — 작업 프로그램이 보냄).
// 받는 사람 = 서류 자동화 계약의 현장 담당·발주처 담당(체크) + 직접 입력, 처음엔 이 시설물에 지난번 보낸 주소대로. 보내면 제출 현황 "전송" 표시.
// 보낸 기록: 링크 열기·복사·끊기(잘못 보냈을 때), 내려받은 횟수, 예약 취소. 서버 server/api/routers/sitok_mail.py, 받는 쪽 화면 share.py.
(function () {
  const rid = new URLSearchParams(location.search).get("report");
  const box = document.getElementById("rd-mail");
  if (!rid || !box) return;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const RE = MAIL_RE, size = mailSizeText; // mail.js(이 화면에 같이 불러옴)와 같은 주소 검사·크기 표시
  const same = (a, b) => a.toLowerCase() === b.toLowerCase();
  let info = null, state = null, flash = null;

  async function load() {
    try {
      info = await api(`/sitok/reports/${rid}/mail`);
      if (!state) start();
      draw();
    } catch (err) {
      box.innerHTML = `<div class="mail-msg bad">${esc(err.message)}</div>`;
    }
  }

  // 처음 고를 값 — 지난번 받는 사람이 있으면 그대로(등록된 담당은 체크, 나머지는 직접 입력 칸), 처음 보내면 등록된 담당 전부
  function start() {
    const last = info.last_recipients || [];
    const checked = {};
    for (const r of info.roles) checked[r.key] = r.emails.length > 0 && (!last.length || r.emails.some((a) => last.some((l) => same(l, a))));
    const roleMails = info.roles.flatMap((r) => r.emails);
    const extras = last.filter((a) => !roleMails.some((r) => same(r, a)));
    state = { checked, extras: extras.length || roleMails.length ? extras : [""], subject: info.subject, note: "", sched: false };
  }

  function recipients() {
    const out = [];
    const picked = info.roles.flatMap((r) => (state.checked[r.key] ? r.emails : []));
    for (const a of [...picked, ...state.extras.map((x) => x.trim())]) if (a && !out.some((o) => same(o, a))) out.push(a);
    return out;
  }

  function jobLine(j) {
    const tag = j.status === "queued" ? `<span class="sm-tag sched">⏰ 예약 ${esc(j.run_at.slice(5))}</span>`
      : j.status === "done" ? '<span class="sm-tag done">보냄</span>'
      : j.status === "failed" ? '<span class="sm-tag bad">못 보냄</span>'
      : j.status === "cancelled" ? '<span class="sm-tag">취소</span>' : '<span class="sm-tag">보내는 중</span>';
    const when = j.status === "done" ? j.sent_at : j.created_at;
    let link = "";
    if (j.status === "done" && j.url) {
      link = j.expired
        ? `<div class="sm-link off">링크 닫힘 — ${esc(j.expires_at.slice(0, 10))} · 내려받음 ${j.downloads}회</div>`
        : `<div class="sm-link"><a href="${esc(j.url)}" target="_blank" rel="noopener">🔗 링크 열기</a>
            <button type="button" class="secondary sm-mini sm-copy" data-u="${esc(j.url)}">링크 복사</button>
            <button type="button" class="secondary sm-mini sm-revoke" data-j="${j.id}" title="잘못 보냈을 때 — 이 링크를 바로 닫습니다">링크 끊기</button>
            <small>~${esc(j.expires_at.slice(0, 10))}까지 · 내려받음 ${j.downloads}회${j.last_download_at ? ` (마지막 ${esc(j.last_download_at.slice(5))})` : ""}</small></div>`;
    }
    return `<div class="sm-job">
      <div class="sm-job-h">${tag} <b>${esc(j.to)}</b> <small>${esc(when)} ${esc(j.created_by)}</small>
        ${j.status === "queued" ? `<button type="button" class="secondary sm-mini sm-cancel" data-j="${j.id}">예약 취소</button>` : ""}</div>
      ${j.message ? `<div class="sm-job-msg${j.status === "failed" ? " bad" : ""}">${esc(j.message)}</div>` : ""}${link}
    </div>`;
  }

  function draw() {
    const n = recipients().length;
    const pad = (v) => String(v).padStart(2, "0");
    const t = new Date(); t.setDate(t.getDate() + 1);
    const tomorrow9 = `${t.getFullYear()}-${pad(t.getMonth() + 1)}-${pad(t.getDate())}T09:00`;
    box.innerHTML = `
      ${info.configured ? "" : '<div class="mail-msg bad">⚠ 메일 보내기 설정이 아직 안 됐습니다(회사 네이버 메일 연결 필요).</div>'}
      ${flash ? `<div class="mail-msg ${flash[1]}">${flash[0]}</div>` : ""}
      ${info.problem ? `<div class="mail-msg warn">⚠ ${esc(info.problem)}</div>`
        : `<div class="sm-file">📄 <b>${esc(info.filename)}</b> <span>(${size(info.size_bytes)})</span> <small>— 첨부 대신 내려받기 링크(${info.share_days}일 동안 열림, 그사이 다시 만들면 새 합본)</small></div>`}
      <div class="sm-sec">받는 사람 <small>모두에게 한 통으로(서로 보임)${(info.last_recipients || []).length ? " · 지난번 보낸 주소대로 골라 두었습니다" : ""}</small></div>
      <div class="sm-roles">${info.roles.map((r) => `<label class="mail-opt${r.emails.length ? "" : " disabled"}">
          <input type="checkbox" data-k="${r.key}" ${r.emails.length ? "" : "disabled"} ${state.checked[r.key] ? "checked" : ""} />
          <span><b>${esc(r.label)}</b> ${esc(r.name)}<span class="mail-addr">${r.emails.length ? r.emails.map(esc).join(", ") : "(서류 자동화 계약에 메일이 없습니다)"}</span></span></label>`).join("")}</div>
      <div class="sm-extras">${state.extras.map((v, i) => `<div class="sm-extra"><input type="email" class="sm-x-in" data-i="${i}" placeholder="받는 사람 메일 (예: name@korea.kr)" value="${esc(v)}" autocomplete="email" />
          <button type="button" class="secondary sm-mini sm-x" data-i="${i}" aria-label="이 주소 빼기">✕</button></div>`).join("")}</div>
      <button type="button" class="secondary sm-add"${n >= info.max_recipients ? " hidden" : ""}>+ 받는 사람 추가</button>
      <div class="field-grid sm-fields">
        <div class="sk-f sm-wide"><label>제목</label><input class="sm-subject" value="${esc(state.subject)}" /></div>
        <div class="sk-f sm-wide"><label>덧붙일 말 <span class="sk-help">비우면 기본 문장만 — 인사·링크·기한은 자동</span></label><textarea class="sm-note" rows="2" placeholder="예: 검토 후 회신 부탁드립니다.">${esc(state.note)}</textarea></div>
      </div>
      ${info.cc ? `<div class="sm-cc">참조 ${esc(info.cc)}</div>` : ""}
      <div class="sm-acts">
        <button type="button" class="sm-send"${info.configured && !info.problem ? "" : " disabled"}>📧 지금 보내기${n > 1 ? ` (${n}곳)` : ""}</button>
        <button type="button" class="secondary sm-sched-btn"${info.configured ? "" : " disabled"}>⏰ 예약 보내기</button>
      </div>
      <div class="sm-sched"${state.sched ? "" : " hidden"}>
        <div class="field-grid"><div class="sk-f"><label>보낼 날짜·시각 <span class="sk-help">서버 PC가 꺼져 있었으면 켜질 때 보냄</span></label><input type="datetime-local" class="sm-at" value="${tomorrow9}" /></div></div>
        <div class="sm-acts"><button type="button" class="sm-sched-ok">예약</button><button type="button" class="secondary sm-sched-x">닫기</button></div>
      </div>
      ${info.jobs.length ? `<div class="sm-sec">보낸·예약 기록</div><div class="sm-jobs">${info.jobs.map(jobLine).join("")}</div>` : ""}`;
    wire();
  }

  const say = (text, kind) => { flash = [text, kind]; };

  function check() {
    const bad = state.extras.map((x) => x.trim()).filter((a) => a && !RE.test(a));
    if (bad.length) { say(`메일 주소를 확인하세요: ${esc(bad.join(", "))}`, "bad"); draw(); return null; }
    const to = recipients();
    if (!to.length) { say("받는 사람을 한 곳 이상 넣으세요.", "bad"); draw(); return null; }
    if (to.length > info.max_recipients) { say(`받는 사람은 ${info.max_recipients}곳까지 넣을 수 있습니다.`, "bad"); draw(); return null; }
    return to;
  }

  async function send(runAt) {
    const to = check();
    if (!to) return;
    const when = runAt ? `${runAt.replace("T", " ")}에 보내도록 예약할까요?` : "보낸 메일은 되돌릴 수 없습니다. 보낼까요?";
    if (!confirm(`받는 사람: ${to.join(", ")}\n${when}`)) return;
    box.querySelectorAll(".sm-send, .sm-sched-ok").forEach((b) => { b.disabled = true; });
    try {
      info = await apiPost(`/sitok/reports/${rid}/mail`, { to, subject: state.subject, note: state.note, run_at: runAt || null });
      state.sched = false;
      say(runAt ? `⏰ ${esc(runAt.replace("T", " "))}에 보내도록 예약했습니다 — 아래 기록에서 취소할 수 있습니다.`
        : `✓ ${esc(to.join(", "))}로 보냈습니다. 제출 현황 "전송"도 표시했습니다.`, "ok");
    } catch (err) {
      say(esc(err.message), "bad");
    }
    draw();
  }

  function wire() {
    box.querySelectorAll(".sm-roles input").forEach((c) => c.addEventListener("change", () => { state.checked[c.dataset.k] = c.checked; draw(); }));
    box.querySelectorAll(".sm-x-in").forEach((inp) => inp.addEventListener("input", () => {
      state.extras[+inp.dataset.i] = inp.value;
      const n = recipients().filter((a) => RE.test(a)).length;
      box.querySelector(".sm-send").textContent = `📧 지금 보내기${n > 1 ? ` (${n}곳)` : ""}`;
    }));
    box.querySelectorAll(".sm-x").forEach((b) => b.addEventListener("click", () => { state.extras.splice(+b.dataset.i, 1); draw(); }));
    box.querySelector(".sm-add").addEventListener("click", () => {
      state.extras.push("");
      draw();
      const ins = box.querySelectorAll(".sm-x-in");
      ins[ins.length - 1].focus();
    });
    box.querySelector(".sm-subject").addEventListener("input", (e) => { state.subject = e.target.value; });
    box.querySelector(".sm-note").addEventListener("input", (e) => { state.note = e.target.value; });
    box.querySelector(".sm-send").addEventListener("click", () => { flash = null; send(null); });
    box.querySelector(".sm-sched-btn").addEventListener("click", () => { state.sched = !state.sched; box.querySelector(".sm-sched").hidden = !state.sched; });
    box.querySelector(".sm-sched-x").addEventListener("click", () => { state.sched = false; box.querySelector(".sm-sched").hidden = true; });
    box.querySelector(".sm-sched-ok").addEventListener("click", () => {
      const at = box.querySelector(".sm-at").value;
      if (!at) { say("날짜·시각을 고르세요.", "bad"); draw(); return; }
      flash = null;
      send(at);
    });
    box.querySelectorAll(".sm-cancel").forEach((b) => b.addEventListener("click", async () => {
      if (!confirm("이 예약 메일을 취소할까요?")) return;
      try { await api(`/mail-jobs/${b.dataset.j}`, { method: "DELETE" }); say("예약을 취소했습니다.", "ok"); await load(); } catch (err) { say(esc(err.message), "bad"); draw(); }
    }));
    box.querySelectorAll(".sm-revoke").forEach((b) => b.addEventListener("click", async () => {
      if (!confirm("이 내려받기 링크를 지금 닫을까요? 받는 사람이 더는 내려받을 수 없습니다(메일은 이미 간 것 그대로).")) return;
      try { await apiPost(`/mail-jobs/${b.dataset.j}/revoke`, {}); say("링크를 닫았습니다.", "ok"); await load(); } catch (err) { say(esc(err.message), "bad"); draw(); }
    }));
    box.querySelectorAll(".sm-copy").forEach((b) => b.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(b.dataset.u); b.textContent = "복사됨 ✓"; } catch { prompt("이 링크를 복사하세요", b.dataset.u); }
    }));
  }

  // 칸을 처음 펼칠 때 불러옴(다른 칸처럼 접혀 있음)
  const panel = document.getElementById("rd-mail-panel");
  if (panel && !panel.open) panel.addEventListener("toggle", function once() { if (panel.open) { panel.removeEventListener("toggle", once); load(); } });
  else load();
})();
