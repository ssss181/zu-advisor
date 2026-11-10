// Signed-in dashboard
(async () => {
  const $ = (s) => document.querySelector(s);

  const res = await fetch("/api/me", { credentials: "same-origin" });
  const { user } = await res.json();
  if (!user) { location.replace("/auth"); return; }

  const first = user.name.split(/\s+/)[0];
  const initials = user.name.split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();
  $("#u-name").textContent = user.name;
  $("#u-email").textContent = user.email;
  $("#u-avatar").textContent = initials;
  $("#u-first").textContent = first;
  $("#u-role").textContent = user.role === "advisor" ? "Faculty advisor" : "Student";
  $("#demo-note").hidden = !user.demo;

  const TOOLS = {
    student: [
      ["i-calendar", "Smart Registration", "Build your Spring 2027 plan — routine plans are approved instantly."],
      ["i-chat", "24/7 AI Advisor", "Ask about courses, prerequisites and your graduation timeline."],
      ["i-book", "Course Catalogue", "Real ZU B.Sc. IT courses with credits and prerequisites."],
      ["i-calendar", "Smart Study Plans", "Build a clash-free semester that respects prerequisites."],
      ["i-file", "Student Records", "Your transcript, GPA and earned credits."],
      ["i-shield", "Policy Database", "Search university rules and registration deadlines."],
      ["i-bell", "Smart Alerts", "Deadlines, seat availability and graduation milestones."],
      ["i-cap", "Graduation Tracker", "See exactly what's left before you graduate."],
    ],
    advisor: [
      ["i-shield", "Registration Approvals", "Only the cases that need your judgment — routine ones are auto-approved."],
      ["i-users", "My Advisees", "Every student you advise, with progress at a glance."],
      ["i-chat", "AI Advisor", "Draft answers to common student questions in seconds."],
      ["i-calendar", "Plan Reviews", "Ask the AI to draft or check a student's next-semester plan."],
      ["i-cap", "Graduation Risk", "Early warning: spot students falling behind — plus seat demand vs capacity."],
      ["i-book", "Course Catalogue", "Real ZU B.Sc. IT courses with credits and prerequisites."],
      ["i-shield", "Policy Database", "Search university rules and registration deadlines."],
    ],
  };
  $("#welcome-copy").textContent = user.role === "advisor"
    ? "Your advisees, their plans, and the governed rules in one place — freed from inbox triage."
    : "Registration is easier with a plan. Here's everything you need to graduate on time.";

  // Tools that are built link to their page; the rest are marked "Coming soon".
  const planQ = "/chat?q=" + encodeURIComponent("What should I register for in Spring 2027? Check my prerequisites and keep it within a normal load.");
  const reviewQ = "/chat?q=" + encodeURIComponent("Suggest a Spring 2027 registration for Fatima Al Suwaidi based on her study plan.");
  const LIVE = {
    "Smart Registration": "/register", "Registration Approvals": "/register",
    "24/7 AI Advisor": "/chat", "AI Advisor": "/chat", "Course Catalogue": "/catalog",
    "Student Records": "/record", "Graduation Tracker": "/record#progress", "Smart Study Plans": planQ,
    "My Advisees": "/record", "Graduation Risk": "/alerts", "Plan Reviews": reviewQ,
    "Smart Alerts": "/alerts", "Policy Database": "/policies",
  };
  $("#tools").innerHTML = TOOLS[user.role].map(([icon, title, text]) => {
    const href = LIVE[title];
    const tag = href ? "a" : "article";
    return `
    <${tag} class="card${href ? " card-live" : ""}"${href ? ` href="${href}"` : ""}>
      <div class="card-icon"><svg class="icon"><use href="#${icon}"/></svg></div>
      <h3>${title}</h3>
      <p>${text}</p>
      <span class="soon">${href ? "Open →" : "Coming soon"}</span>
    </${tag}>`;
  }).join("");

  // Record summary strip
  try {
    const r = await (await fetch("/api/record")).json();
    let html = "";
    if (r.role === "student") {
      const s = r.summary;
      html = `<div class="mini"><span>CGPA</span><strong>${s.cgpa ?? "–"}</strong></div>
        <div class="mini"><span>Credits</span><strong>${s.credits_earned}/${s.credits_required}</strong></div>
        <div class="mini"><span>Semester</span><strong>${r.record.semester} of 8</strong></div>
        <div class="mini"><span>Standing</span><strong>${s.cgpa != null && s.cgpa < 2 ? "Probation" : s.cgpa == null ? "New" : "Good"}</strong></div>`;
      $("#u-program").textContent = r.record.program_name;
    } else if (r.role === "advisor") {
      const n = r.advisees.length, risk = r.advisees.filter((a) => a.summary.cgpa != null && a.summary.cgpa < 2).length;
      html = `<div class="mini"><span>Advisees</span><strong>${n}</strong></div>
        <div class="mini"><span>On probation</span><strong>${risk}</strong></div>
        <div class="mini"><span>Programme</span><strong>B.Sc. IT</strong></div>`;
    }
    $("#mini-stats").innerHTML = html;
    // primary call to action: registration
    const ask = document.querySelector(".ask-btn");
    if (ask && r.role === "student") {
      const reg = await (await fetch("/api/registration")).json();
      const st = reg.request?.status;
      ask.insertAdjacentHTML("beforebegin", `<a href="/register" class="btn btn-gold btn-lg ask-btn" style="margin-right:.75rem">${
        st === "approved" ? "✅ Registered for " + reg.term : st === "pending" ? "⏳ Registration with your advisor" : "Register for " + reg.term}</a>`);
      ask.classList.replace("btn-gold", "btn-outline");
    } else if (ask && r.role === "advisor") {
      const q = await (await fetch("/api/advising/queue")).json();
      ask.insertAdjacentHTML("beforebegin", `<a href="/register" class="btn btn-gold btn-lg ask-btn" style="margin-right:.75rem">Review ${q.pending.length} pending approval${q.pending.length === 1 ? "" : "s"}</a>`);
      ask.classList.replace("btn-gold", "btn-outline");
    }
  } catch {}

  $("#logout").addEventListener("click", async () => {
    await fetch("/api/logout", { method: "POST", credentials: "same-origin" });
    location.href = "/";
  });
})();
