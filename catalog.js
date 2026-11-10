// Course catalogue page
(async () => {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const [catRes, recRes] = await Promise.all([fetch("/api/catalog"), fetch("/api/record")]);
  if (catRes.status === 401) { location.replace("/auth"); return; }
  const cat = await catRes.json();
  const rec = recRes.ok ? await recRes.json() : null;
  const byCode = Object.fromEntries(cat.courses.map((c) => [c.code, c]));

  // Student status per course (from their sample record)
  let status = {};
  if (rec?.role === "student") {
    $("#program").value = rec.record.program;
    const passed = new Set(rec.summary.passed);
    const current = new Set(rec.record.current.courses.map((c) => c.code));
    for (const c of cat.courses) {
      if (passed.has(c.code)) status[c.code] = ["ok", "Completed"];
      else if (current.has(c.code)) status[c.code] = ["gold", "In progress"];
      else {
        const missing = c.prereqs.filter((p) => !passed.has(p) && !current.has(p));
        status[c.code] = missing.length ? ["no", "Needs " + missing.join(", ")] : ["ok", "Can take"];
      }
    }
  } else if (rec?.role === "advisor") {
    $("#nav-record").textContent = "My Advisees";
    document.querySelector("#nav-reg").textContent = "Approvals";
    document.querySelector("#nav-alerts").textContent = "Early Warning";
  }

  for (const a of [...new Set(cat.courses.map((c) => c.area))]) {
    $("#area").insertAdjacentHTML("beforeend", `<option>${esc(a)}</option>`);
  }
  $("#source").textContent = "Source: " + cat.source + ". Prerequisites may have changed — confirm with the Registrar.";

  const link = (code) => byCode[code] ? `<a href="#" data-code="${esc(code)}">${esc(code)}</a>` : esc(code);

  function render() {
    const q = $("#q").value.trim().toLowerCase();
    const prog = $("#program").value, area = $("#area").value;
    const list = cat.courses
      .filter((c) => !prog || c.programs[prog])
      .filter((c) => !area || c.area === area)
      .filter((c) => !q || c.code.toLowerCase().includes(q) || c.title.toLowerCase().includes(q))
      .sort((a, b) => ((prog ? a.programs[prog] : Math.min(...Object.values(a.programs))) - (prog ? b.programs[prog] : Math.min(...Object.values(b.programs)))) || a.code.localeCompare(b.code));
    $("#count").textContent = `${list.length} course${list.length === 1 ? "" : "s"}`;
    $("#grid").innerHTML = list.map((c) => {
      const plans = Object.entries(c.programs).map(([p, sem]) =>
        `<span class="tag">${p === "SECNET" ? "Sec & Net" : "Web & Mobile"} · ${sem === 9 ? "Internship" : "Sem " + sem}</span>`).join("");
      const st = status[c.code];
      return `<article class="course-card" id="c-${esc(c.code)}">
        <div class="course-top"><span class="code">${esc(c.code)}</span><span class="tag">${c.credits} credit${c.credits === 1 ? "" : "s"}</span></div>
        <h3>${esc(c.title)}</h3>
        <div class="course-meta"><span class="tag gold">${esc(c.area)}</span>${plans}</div>
        <div class="course-req"><strong>Prerequisites:</strong> ${c.prereqs.length ? c.prereqs.map(link).join(" + ") : "none listed"}
          ${c.coreqs.length ? `<br><strong>Take with:</strong> ${c.coreqs.map(link).join(", ")}` : ""}</div>
        ${st ? `<div class="course-status"><span class="tag ${st[0]}">${esc(st[1])}</span></div>` : ""}
      </article>`;
    }).join("") || emptyMessage(q, prog);
  }

  function emptyMessage(q, prog) {
    const elsewhere = prog && q && cat.courses.some((c) => !c.programs[prog] &&
      (c.code.toLowerCase().includes(q) || c.title.toLowerCase().includes(q)));
    return elsewhere
      ? `<p class="empty">No match in your concentration. <a href="#" id="show-all" style="color:var(--accent);font-weight:600">Show matches in the other concentration</a></p>`
      : '<p class="empty">No courses match your search.</p>';
  }
  $("#grid").addEventListener("click", (e) => {
    if (e.target.id === "show-all") { e.preventDefault(); $("#program").value = ""; render(); }
  });

  $("#grid").addEventListener("click", (e) => {
    const a = e.target.closest("a[data-code]");
    if (!a) return;
    e.preventDefault();
    $("#q").value = a.dataset.code; $("#area").value = ""; $("#program").value = "";
    render();
  });
  for (const id of ["#q", "#program", "#area"]) $(id).addEventListener("input", render);
  const q = new URLSearchParams(location.search).get("q");
  if (q) { $("#q").value = q; $("#program").value = ""; }
  render();
})();
