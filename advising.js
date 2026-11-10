// Advisor approvals queue
(async () => {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const md = (s) => esc(s).replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/\n/g, "<br>");
  const post = async (url, body = {}) => {
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || "Something went wrong.");
    return data;
  };
  const ago = (iso) => {
    const h = (Date.now() - new Date(iso)) / 36e5;
    return h < 1 ? `${Math.max(1, Math.round(h * 60))} min` : h < 48 ? `${Math.round(h)} h` : `${Math.round(h / 24)} days`;
  };
  const tierTag = (r) => r.tier === "red" ? '<span class="tag no">Exception</span>' : '<span class="tag gold">Review</span>';

  let state = null, current = null;

  async function load() {
    const res = await fetch("/api/advising/queue");
    if (res.status === 401) { location.replace("/auth"); return; }
    if (res.status === 403) { location.replace("/dashboard"); return; }
    state = await res.json();
    render();
  }

  function render() {
    const k = state.kpis;
    $("#title").textContent = `Registration approvals · ${state.term}`;
    $("#kpis").innerHTML = `
      <div class="kpi"><div class="kpi-label">Approved instantly</div><div class="kpi-value good">${k.auto_rate}%</div><div class="kpi-sub">${k.auto_approved} of ${k.total} requests, no advisor needed</div></div>
      <div class="kpi"><div class="kpi-label">Needed judgment</div><div class="kpi-value">${k.routed}</div><div class="kpi-sub">${k.pending} waiting for a decision</div></div>
      <div class="kpi"><div class="kpi-label">Avg. time to decision</div><div class="kpi-value">${k.avg_wait_hours < 1 ? "<1" : k.avg_wait_hours} h</div><div class="kpi-sub">routed cases: ${k.routed_avg_wait_hours} h</div></div>
      <div class="kpi"><div class="kpi-label">Advisor workload</div><div class="kpi-value good">−${k.workload_reduction}%</div><div class="kpi-sub">cases advisors no longer handle</div></div>`;
    $("#kpi-note").textContent = `Compared with a baseline where every registration waits for manual approval (assumed ${k.baseline_hours} h average — replace with ZU's real figure). Sample cohort: simulated students.`;

    $("#pending-count").textContent = `${state.pending.length} case${state.pending.length === 1 ? "" : "s"}`;
    const overdue = (r) => r.status === "pending" && Date.now() - new Date(r.created_at).getTime() > 48 * 3600e3;
    const nOver = state.pending.filter(overdue).length;
    if (nOver) $("#pending-count").innerHTML += ` · <span class="tag risk-high">${nOver} overdue</span>`;
    const caseBtn = (r) => {
      const issues = r.checks.filter((c) => c.level !== "ok");
      return `<button class="case ${current === r.id ? "sel" : ""}" data-id="${r.id}" type="button">
        <div class="case-top"><span class="case-name">${esc(r.student.name)}</span>${r.status === "pending" ? tierTag(r) : `<span class="tag ${r.status === "approved" ? "ok" : "no"}">${esc(r.status)}</span>`}</div>
        <div class="case-meta">${esc(r.student.program_short)} · sem ${r.student.semester} · CGPA ${r.student.cgpa ?? "–"} · ${r.credits} cr · ${r.status === "pending" ? "waiting " + ago(r.created_at) : "decided by " + esc(r.decided_by)}${r.is_sample ? "" : " · <strong>live</strong>"}</div>
        ${overdue(r) ? '<div class="overdue-row"><span class="tag risk-high">⚠ Overdue · past 48 h</span><span class="source-note">Escalated to Program Chair</span></div>' : ""}
        <div class="case-reason">${esc(issues[0]?.message || "")}${issues.length > 1 ? ` <span class="tag">+${issues.length - 1}</span>` : ""}</div>
      </button>`;
    };
    $("#queue").innerHTML = state.pending.map(caseBtn).join("") || '<p class="empty">🎉 No cases waiting — everything routine was approved automatically.</p>';
    $("#decided").innerHTML = state.decided.slice(0, 6).map(caseBtn).join("") || '<p class="source-note">Nothing yet.</p>';
    const max = Math.max(1, ...state.top_reasons.map((r) => r.count));
    $("#reasons").innerHTML = state.top_reasons.map((r) => `
      <div class="bar-row"><span><span class="rid code">${esc(r.rule)}</span> ${esc(r.name)}</span><span class="bar"><span style="width:${100 * r.count / max}%"></span></span><span>${r.count}</span></div>`).join("")
      || '<p class="source-note">No exceptions yet.</p>';
    if (current) showCase(current, false);
  }

  function find(id) { return [...state.pending, ...state.decided].find((r) => r.id === id); }

  function showCase(id, scroll = true) {
    const r = find(id);
    if (!r) { $("#case").innerHTML = '<p class="empty">Select a case to review it.</p>'; current = null; return; }
    current = id;
    document.querySelectorAll(".case").forEach((b) => b.classList.toggle("sel", Number(b.dataset.id) === id));
    const s = r.student;
    const order = { red: 0, amber: 1, ok: 2 };
    $("#case").innerHTML = `
      <div class="panel-head"><h2>${esc(s.name)}</h2>${tierTag(r)}</div>
      <p class="case-meta">${esc(s.student_id)} · ${esc(s.program_short)} · semester ${s.semester} · CGPA <strong>${s.cgpa ?? "–"}</strong> · ${s.credits_earned}/120 credits · ${esc(s.standing)}</p>
      <p class="case-meta">Assigned to <strong>${esc(r.advisor)}</strong> · submitted ${ago(r.created_at)} ago</p>
      <div class="course-chips">${r.course_details.map((c) => `<span class="tag">${esc(c.code === "ELECTIVE" ? "Elective" : c.code)} ${esc(c.code === "ELECTIVE" ? "" : c.title)} · ${c.credits}</span>`).join("")}<span class="tag gold">${r.credits} credits</span></div>
      ${r.student_note ? `<div class="ai-box" style="border-style:solid;border-color:var(--border)"><div class="ai-label" style="color:var(--muted-fg)">Student's reason</div>${esc(r.student_note)}</div>` : ""}
      <h3 style="margin:1.25rem 0 .25rem;font-size:.9375rem">Rule checks</h3>
      <div>${[...r.checks].sort((a, b) => order[a.level] - order[b.level]).map((c) => `
        <div class="check"><span class="lvl lvl-${c.level}"></span><div>${esc(c.message)}<span class="rid">${esc(c.rule)} · ${esc(c.rule_name)} · owner: ${esc(state.rules[c.rule]?.owner || "")}</span></div></div>`).join("")}</div>
      <div class="ai-box" id="ai-box">${r.ai_recommendation ? `<div class="ai-label"><svg class="icon icon-xs"><use href="#i-sparkles"/></svg>AI recommendation</div>${md(r.ai_recommendation)}` :
        `<button class="btn btn-gold btn-sm" id="ai-btn" type="button"><svg class="icon icon-xs"><use href="#i-sparkles"/></svg>Get AI recommendation</button>`}</div>
      ${r.status === "pending" ? `
        <label class="field-label" for="d-note">Note to the student</label>
        <textarea class="note-input" id="d-note" rows="2" maxlength="1000" placeholder="Required when denying or returning"></textarea>
        <div class="decide-row">
          <button class="btn btn-ok btn-sm" data-d="approve" type="button">Approve</button>
          <button class="btn btn-mid btn-sm" data-d="return" type="button">Return for changes</button>
          <button class="btn btn-no btn-sm" data-d="deny" type="button">Deny</button>
        </div>
        <div class="error-box" id="d-err" hidden></div>` :
        `<p class="case-meta" style="margin-top:1rem"><strong>${esc(r.status)}</strong> by ${esc(r.decided_by)}${r.decision_note ? ": " + esc(r.decision_note) : ""}</p>`}`;
    if (scroll && window.innerWidth < 1000) $("#case").scrollIntoView({ behavior: "smooth" });
  }

  $("#queue").addEventListener("click", (e) => { const b = e.target.closest(".case"); if (b) showCase(Number(b.dataset.id)); });
  $("#decided").addEventListener("click", (e) => { const b = e.target.closest(".case"); if (b) showCase(Number(b.dataset.id)); });

  $("#case").addEventListener("click", async (e) => {
    if (e.target.closest("#ai-btn")) {
      const box = $("#ai-box");
      box.innerHTML = '<div class="ai-label"><svg class="icon icon-xs"><use href="#i-sparkles"/></svg>AI recommendation</div><span class="typing"><span></span><span></span><span></span></span> Analysing the case…';
      try {
        const { recommendation } = await post(`/api/advising/${current}/ai`);
        find(current).ai_recommendation = recommendation;
        box.innerHTML = `<div class="ai-label"><svg class="icon icon-xs"><use href="#i-sparkles"/></svg>AI recommendation</div>${md(recommendation)}`;
      } catch (err) {
        box.innerHTML = `<span class="source-note">${esc(err.message)}</span> <button class="btn btn-mid btn-sm" id="ai-btn" type="button">Try again</button>`;
      }
      return;
    }
    const d = e.target.closest("[data-d]");
    if (d) {
      try {
        await post(`/api/advising/${current}/decide`, { decision: d.dataset.d, note: $("#d-note").value });
        await load();
        showCase(current);
      } catch (err) { $("#d-err").textContent = err.message; $("#d-err").hidden = false; }
    }
  });

  $("#reset").addEventListener("click", async (e) => {
    e.preventDefault();
    await post("/api/advising/reset-demo"); current = null; await load();
    $("#case").innerHTML = '<p class="empty">Select a case to review it.</p>';
  });

  await load();
  if (state.pending[0]) showCase(state.pending[0].id, false);
  setInterval(() => { if (!document.hidden && !$("#d-note")?.value) load(); }, 20000);   // live queue
})();
