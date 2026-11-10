// Smart Registration (student)
(async () => {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const post = async (url, body) => {
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error(data.error || "Something went wrong."), { data });
    return data;
  };

  const res = await fetch("/api/registration");
  if (res.status === 401) { location.replace("/auth"); return; }
  if (res.status === 403) { location.replace("/dashboard"); return; }
  const data = await res.json();
  const term = data.term;
  $("#title").textContent = `Register for ${term}`;
  $("#sub").textContent = `${data.record.name} · ${data.record.program_name} · CGPA ${data.record.cgpa ?? "–"} (${data.record.standing})`;
  $("#rule-note").textContent = "Every check is a published rule with an owner (e.g. PRQ-01 Prerequisites — Curriculum Committee). "
    + "Routine plans are approved instantly; only plans that need judgment go to your advisor.";

  // ---------------- course options
  const ELECTIVE = "ELECTIVE";
  const opts = [...data.options];
  const selected = new Set(data.suggested);
  if (data.suggested.includes(ELECTIVE) || true) {
    opts.push({ code: ELECTIVE, title: "Free elective (any ZU course)", credits: 3, plan_semester: 99, eligible: true, missing_prereqs: [], coreqs: [] });
  }
  const credOf = (c) => opts.find((o) => o.code === c)?.credits ?? 0;

  function renderOptions() {
    const suggested = opts.filter((o) => data.suggested.includes(o.code));
    const ready = opts.filter((o) => !data.suggested.includes(o.code) && o.eligible);
    const later = opts.filter((o) => !data.suggested.includes(o.code) && !o.eligible);
    const item = (o) => `
      <label class="opt ${selected.has(o.code) ? "on" : ""}">
        <input type="checkbox" value="${esc(o.code)}" ${selected.has(o.code) ? "checked" : ""}>
        <span class="opt-main">
          <span class="opt-title"><span class="code">${o.code === ELECTIVE ? "ELECTIVE" : esc(o.code)}</span> ${esc(o.title)}</span>
          <span class="opt-sub">${o.plan_semester === 99 ? "Counts toward your free-elective requirement" :
            o.plan_semester === 9 ? "Internship semester" : "Study plan semester " + o.plan_semester}${o.coreqs?.length ? " · take with " + esc(o.coreqs.join(", ")) : ""}${!o.eligible ? " · needs " + esc(o.missing_prereqs.join(", ")) : ""}</span>
        </span>
        <span class="opt-cr">${o.credits} cr</span>
      </label>`;
    $("#options").innerHTML =
      (suggested.length ? `<p class="opt-group-title">Suggested for you</p>${suggested.map(item).join("")}` : "") +
      (ready.length ? `<p class="opt-group-title">Also available to you</p>${ready.map(item).join("")}` : "") +
      (later.length ? `<p class="opt-group-title">Needs prerequisites first</p>${later.map(item).join("")}` : "");
  }

  $("#options").addEventListener("change", (e) => {
    const cb = e.target.closest("input[type=checkbox]");
    if (!cb) return;
    cb.checked ? selected.add(cb.value) : selected.delete(cb.value);
    cb.closest(".opt").classList.toggle("on", cb.checked);
    schedule();
  });

  // ---------------- instant check
  let timer = null, lastEval = null, seq = 0;
  function schedule() {
    clearTimeout(timer);
    $("#check-panel").classList.add("checking");
    $("#submit").disabled = true;
    timer = setTimeout(check, 120);
  }
  async function check() {
    const mine = ++seq;
    const courses = [...selected];
    $("#sel-credits").textContent = `${courses.reduce((a, c) => a + credOf(c), 0)} credits selected`;
    if (!courses.length) {
      $("#check-panel").classList.remove("checking");
      $("#verdict").innerHTML = ""; $("#checks").innerHTML = '<p class="source-note">Pick at least one course.</p>';
      $("#submit").disabled = true; $("#exception").hidden = true; return;
    }
    const ev = await post("/api/registration/check", { courses });
    if (mine !== seq) return;            // a newer check is on its way
    lastEval = ev;
    $("#check-panel").classList.remove("checking");
    const V = {
      green: ["v-green", "Routine — approved instantly", "Every rule passes. Submitting registers you right away, no advisor approval needed."],
      amber: ["v-amber", "Needs your advisor's review", `This plan needs academic judgment. It goes straight to ${ev.advisor}, your named advisor.`],
      red: ["v-red", "Blocked by a rule", "Fix the items below to make it routine — or request an exception and your advisor will decide."],
    }[ev.tier];
    $("#verdict").innerHTML = `<div class="verdict ${V[0]}"><span class="dot"></span><div><strong>${V[1]}</strong><span>${esc(V[2])}</span></div></div>`;
    const order = { red: 0, amber: 1, ok: 2 };
    $("#checks").innerHTML = [...ev.checks].sort((a, b) => order[a.level] - order[b.level]).map((c) => `
      <div class="check"><span class="lvl lvl-${c.level}"></span><div>${esc(c.message)}
        ${c.fix ? `<span class="fix">→ ${esc(c.fix)}</span>` : ""}<span class="rid">${esc(c.rule)} · ${esc(c.rule_name)}</span></div></div>`).join("");
    $("#exception").hidden = ev.tier !== "red";
    $("#submit").disabled = false;
    $("#submit").textContent = ev.tier === "green" ? "Register now" : ev.tier === "amber" ? `Send to ${ev.advisor}` : "Request exception";
    $("#error").hidden = true;
  }

  $("#submit").addEventListener("click", async () => {
    const btn = $("#submit");
    btn.disabled = true;
    try {
      const { request } = await post("/api/registration/submit", { courses: [...selected], note: $("#note").value });
      showStatus(request);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      $("#error").textContent = err.message; $("#error").hidden = false;
    } finally { btn.disabled = false; }
  });

  // ---------------- current request status
  function showStatus(r) {
    if (!r) { $("#status-panel").innerHTML = ""; return; }
    const when = (iso) => iso ? new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "";
    const secs = r.decided_at ? Math.max(0, (new Date(r.decided_at) - new Date(r.created_at)) / 1000) : null;
    const S = {
      approved: [r.decided_by === "Rules engine" ? "✅ You're registered" : "✅ Approved by your advisor",
        r.decided_by === "Rules engine" ? `Approved automatically by the rules engine${secs != null ? " in under " + Math.max(1, Math.ceil(secs)) + " second" + (Math.ceil(secs) > 1 ? "s" : "") : ""} — no waiting for an advisor.`
          : `${esc(r.decided_by)} approved your plan on ${when(r.decided_at)}.`],
      pending: ["⏳ With your advisor", `Sent to ${esc(r.advisor)} on ${when(r.created_at)}. You'll see the decision here.`],
      denied: ["Not approved", `${esc(r.decided_by)} did not approve this plan. Adjust it below and resubmit.`],
      returned: ["Returned for changes", `${esc(r.decided_by)} asked you to adjust your plan. Change it below and resubmit.`],
    }[r.status];
    const steps = r.kind === "routine"
      ? `<span class="step done">Submitted</span><span class="step done">Rules check passed</span><span class="step done">Registered</span>`
      : `<span class="step done">Submitted</span><span class="step done">Rules check: ${r.tier === "red" ? "exception" : "needs review"}</span>
         <span class="step ${r.status === "pending" ? "now" : "done"}">Advisor ${r.status === "pending" ? "reviewing" : "decided"}</span>`;
    $("#status-panel").innerHTML = `
      <div class="status-card s-${r.status}">
        <div style="flex:1;min-width:16rem">
          <h2>${S[0]}</h2><p>${S[1]}</p>
          ${r.decision_note && r.decided_by !== "Rules engine" ? `<p><strong>Advisor's note:</strong> ${esc(r.decision_note)}</p>` : ""}
          <div class="timeline">${steps}</div>
          <div class="course-chips">${r.course_details.map((c) => `<span class="tag">${esc(c.code === ELECTIVE ? "Elective" : c.code)} · ${c.credits} cr</span>`).join("")}<span class="tag gold">${r.credits} credits</span></div>
        </div>
        ${r.status === "pending" ? '<button class="btn btn-mid btn-sm" id="withdraw" type="button">Withdraw</button>' : ""}
      </div>`;
    $("#withdraw")?.addEventListener("click", async () => {
      await post("/api/registration/withdraw", {}); showStatus(null);
    });
    if (["approved", "pending"].includes(r.status)) {
      for (const c of r.courses) selected.add(c);
    }
  }

  showStatus(data.request);
  if (data.request && ["approved", "pending"].includes(data.request.status)) {
    selected.clear(); data.request.courses.forEach((c) => selected.add(c));
  }
  renderOptions();
  check();
})();
