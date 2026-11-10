// My Record page: student transcript + graduation tracker, or an advisor's advisees
(async () => {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const gradeClass = (g) => g === "F" ? "g-f" : /^A/.test(g) ? "g-a" : /^C/.test(g) ? "g-c" : "";
  const gpaClass = (x) => x == null ? "" : x < 2 ? "bad" : x < 2.5 ? "warn" : "good";
  const chatLink = (q, label) => `<a class="btn btn-gold btn-sm" href="/chat?q=${encodeURIComponent(q)}"><svg class="icon icon-sm"><use href="#i-chat"/></svg>${esc(label)}</a>`;

  const res = await fetch("/api/record");
  if (res.status === 401) { location.replace("/auth"); return; }
  const data = await res.json();
  const body = $("#body");

  if (data.role === "advisor") {
    $("#nav-record").textContent = "My Advisees";
    document.querySelector("#nav-reg").textContent = "Approvals";
    document.querySelector("#nav-alerts").textContent = "Early Warning";
    document.title = "My Advisees — ZU Advisor";
    $("#hero-title").textContent = "My Advisees";
    $("#hero-sub").textContent = `${data.advisees.length} students · B.Sc. Information Technology · Fall 2026`;
    const sorted = [...data.advisees].sort((a, b) => (a.summary.cgpa ?? 9) - (b.summary.cgpa ?? 9));
    body.innerHTML = `
      <section class="panel">
        <div class="panel-head"><h2>Advisees</h2><p>Sorted by CGPA, lowest first</p></div>
        <div class="table-wrap"><table class="data">
          <thead><tr><th>Student</th><th>Concentration</th><th>Sem.</th><th>CGPA</th><th>Credits</th><th>Standing</th><th></th></tr></thead>
          <tbody>${sorted.map(({ record: r, summary: s }) => `
            <tr>
              <td><strong>${esc(r.name)}</strong><br><span class="code">${esc(r.student_id)}</span></td>
              <td>${r.program === "SECNET" ? "Security &amp; Networks" : "Web &amp; Mobile"}</td>
              <td>${r.semester}</td>
              <td class="${gpaClass(s.cgpa)}"><strong>${s.cgpa ?? "–"}</strong></td>
              <td>${s.credits_earned}/120<div class="progress" style="margin-top:.375rem;width:6rem"><span style="width:${s.percent_complete}%"></span></div></td>
              <td>${s.cgpa != null && s.cgpa < 2 ? '<span class="tag no">Probation</span>' : '<span class="tag ok">Good</span>'}
                  ${s.deans_list_terms.length ? '<span class="tag gold">Dean\'s List</span>' : ""}
                  ${r.current.courses.some((c) => c.type === "Repeat") ? '<span class="tag no">Repeating</span>' : ""}</td>
              <td>${chatLink(`Prepare me for an advising meeting with ${r.name}: summary, concerns and a suggested Spring 2027 plan.`, "Ask AI")}</td>
            </tr>`).join("")}</tbody>
        </table></div>
      </section>
      <p class="source-note">All advisees are fictional sample students for this prototype. Courses follow ZU's official 2025 B.Sc. IT study plans.</p>`;
    return;
  }

  const r = data.record, s = data.summary;
  $("#hero-title").textContent = r.name;
  $("#hero-sub").textContent = `${r.program_name} · Year ${r.year}, semester ${r.semester} · ID ${r.student_id}`;

  const eligible = data.next.filter((c) => c.eligible);
  const blocked = data.next.filter((c) => !c.eligible);
  body.innerHTML = `
    <section class="kpis">
      <div class="kpi"><div class="kpi-label">Cumulative GPA</div><div class="kpi-value ${gpaClass(s.cgpa)}">${s.cgpa ?? "–"}</div><div class="kpi-sub">${esc(s.standing)}</div></div>
      <div class="kpi"><div class="kpi-label">Credits earned</div><div class="kpi-value">${s.credits_earned}</div><div class="kpi-sub">of ${s.credits_required} required</div></div>
      <div class="kpi"><div class="kpi-label">This term</div><div class="kpi-value">${s.credits_in_progress}</div><div class="kpi-sub">credits in ${esc(r.current_term)}</div></div>
      <div class="kpi"><div class="kpi-label">Dean's List</div><div class="kpi-value">${s.deans_list_terms.length}</div><div class="kpi-sub">${s.deans_list_terms.length ? esc(s.deans_list_terms.join(", ")) : "terms so far"}</div></div>
    </section>

    <section class="panel" id="progress">
      <div class="panel-head"><h2>Graduation tracker</h2><p>${s.percent_complete}% complete · ${s.credits_remaining} credits to go</p></div>
      <div class="progress"><span style="width:${s.percent_complete}%"></span></div>
      <div class="progress-legend"><span>${s.credits_earned} earned + ${s.credits_in_progress} in progress</span><span>${s.credits_required} credits</span></div>
      <div class="ask-row">
        ${chatLink(`What should I register for in ${r.next_term}? Check my prerequisites and keep it within a normal load.`, `Plan ${r.next_term} with AI`)}
        ${chatLink("Am I on track to graduate on time? What's left?", "Am I on track?")}
      </div>
    </section>

    <section class="panel">
      <div class="panel-head"><h2>Current registration · ${esc(r.current_term)}</h2><p>${s.credits_in_progress} credits</p></div>
      <div class="table-wrap"><table class="data">
        <thead><tr><th>Course</th><th>Title</th><th>Credits</th><th></th></tr></thead>
        <tbody>${r.current.courses.map((c) => `<tr><td class="code">${esc(c.code)}</td><td>${esc(c.title)}</td><td>${c.credits}</td><td>${c.type === "Repeat" ? '<span class="tag no">Repeat</span>' : ""}</td></tr>`).join("") || '<tr><td colspan="4">No courses this term.</td></tr>'}</tbody>
      </table></div>
    </section>

    <section class="panel">
      <div class="panel-head"><h2>What's left</h2><p>${eligible.length} you can take next · ${blocked.length} need prerequisites first</p></div>
      <div class="table-wrap"><table class="data">
        <thead><tr><th>Course</th><th>Title</th><th>Cr.</th><th>Plan</th><th>Status</th></tr></thead>
        <tbody>${data.next.map((c) => `<tr>
          <td class="code">${esc(c.code)}</td><td>${esc(c.title)}</td><td>${c.credits}</td>
          <td>${c.plan_semester < 9 ? "Sem " + c.plan_semester : "Internship"}</td>
          <td>${c.eligible ? '<span class="tag ok">Can take</span>' : `<span class="tag no">Needs ${esc(c.missing_prereqs.join(", "))}</span>`}</td>
        </tr>`).join("") || '<tr><td colspan="5">Nothing left — ready to graduate!</td></tr>'}</tbody>
      </table></div>
      <p class="source-note" style="margin-top:.75rem">"Can take" assumes you pass your current courses. Prerequisites from the ZU Catalog 2021–2022 — confirm with the Registrar.</p>
    </section>

    <section class="panel">
      <div class="panel-head"><h2>Transcript</h2><p>${r.terms.length} completed term${r.terms.length === 1 ? "" : "s"}</p></div>
      <div class="terms">${r.terms.slice().reverse().map((t) => {
        const tg = s.term_gpas.find((x) => x.term === t.term);
        return `<div class="term">
          <div class="term-head">${esc(t.term)} <span>Term GPA ${tg?.gpa ?? "–"}${tg && tg.gpa >= 3.6 && tg.credits >= 15 ? " · Dean's List" : ""}</span></div>
          <table class="data"><tbody>${t.courses.map((c) => `<tr>
            <td class="code">${esc(c.code.startsWith("ELECTIVE") ? "ELECT" : c.code)}</td>
            <td>${esc(c.title)}${c.type === "Repeat" ? ' <span class="tag">Repeat</span>' : ""}${c.repeated ? ' <span class="tag">Repeated later</span>' : ""}</td>
            <td>${c.credits}</td><td><span class="grade ${gradeClass(c.grade)}">${esc(c.grade)}</span></td>
          </tr>`).join("")}</tbody></table>
        </div>`;
      }).join("") || '<p class="empty">No completed terms yet — this is your first semester.</p>'}</div>
    </section>

    <p class="source-note">This is a <strong>sample record</strong> generated for the prototype from ZU's official 2025 B.Sc. IT study plan — not real student data.</p>`;
})();
