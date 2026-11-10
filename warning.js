// Early Warning + seat demand (advisor)
(async () => {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const res = await fetch("/api/early-warning");
  if (res.status === 401) { location.replace("/auth"); return; }
  if (res.status === 403) { location.replace("/dashboard"); return; }
  const data = await res.json();
  const c = data.cohort, ss = data.seat_summary;
  const prog = (p) => p === "SECNET" ? "Sec &amp; Net" : "Web &amp; Mobile";
  const risk = (r) => `<span class="tag risk-${r.level}">${r.level === "high" ? "High" : r.level === "medium" ? "Medium" : "Low"} · ${r.score}</span>`;

  $("#kpis").innerHTML = `
    <div class="kpi"><div class="kpi-label">High risk</div><div class="kpi-value bad">${c.high}</div><div class="kpi-sub">of ${c.total} students scanned</div></div>
    <div class="kpi"><div class="kpi-label">Medium risk</div><div class="kpi-value warn">${c.medium}</div><div class="kpi-sub">check-in recommended</div></div>
    <div class="kpi"><div class="kpi-label">Courses short of seats</div><div class="kpi-value ${ss.full ? "bad" : "good"}">${ss.full}</div><div class="kpi-sub">${ss.tight} more almost full</div></div>
    <div class="kpi"><div class="kpi-label">Extra sections needed</div><div class="kpi-value">${ss.extra_sections}</div><div class="kpi-sub">for ${esc(data.term)}, flagged before term starts</div></div>`;

  const actionCell = (r) => r.level === "low" ? '<span class="source-note">—</span>' : `
    <div style="display:flex;gap:.375rem;flex-wrap:wrap">
      <button class="btn btn-sm ${r.contacted ? "btn-mid" : "btn-gold"}" data-sid="${esc(r.student_id)}" ${r.contacted ? "disabled" : ""}>${r.contacted ? "✓ Check-in sent" : "Send check-in"}</button>
      <a class="btn btn-outline btn-sm" href="/chat?q=${encodeURIComponent(`Prepare me for an advising meeting with ${r.name}: summary, concerns and a suggested Spring 2027 plan.`)}">Ask AI</a>
    </div>`;
  const why = (r) => r.reasons.length
    ? `<ul class="reasons">${r.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` +
      (r.level !== "low" ? `<div style="font-size:.8125rem;margin-top:.25rem"><strong>Suggested:</strong> ${esc(r.action)}</div>` : "")
    : '<span class="source-note">No warning signs</span>';
  $("#advisees").innerHTML = `<div class="table-wrap"><table class="data">
    <thead><tr><th>Student</th><th>Sem.</th><th>CGPA</th><th>Risk</th><th>Why</th><th>Action</th></tr></thead>
    <tbody>${data.advisees.map((r) => `<tr>
      <td><strong>${esc(r.name)}</strong><br><span class="source-note">${prog(r.program)} · ${esc(r.student_id)}</span></td>
      <td>${r.semester}</td><td class="${r.cgpa < 2 ? "bad" : r.cgpa < 2.5 ? "warn" : "good"}"><strong>${r.cgpa ?? "–"}</strong></td>
      <td>${risk(r)}</td><td>${why(r)}</td><td>${actionCell(r)}</td></tr>`).join("")}</tbody></table></div>`;

  $("#cohort-sub").textContent = `${c.high + c.medium} flagged of ${c.total}`;
  $("#cohort").innerHTML = c.top.map((r) => `
    <div class="case" style="cursor:default">
      <div class="case-top"><span class="case-name">${esc(r.name)}</span>${risk(r)}</div>
      <div class="case-meta">${prog(r.program)} · semester ${r.semester} · CGPA ${r.cgpa}</div>
      <div class="case-reason">${esc(r.reasons.join(" · "))}</div>
    </div>`).join("");

  $("#seat-sub").textContent = `${esc(data.term)} · most requested vs seats`;
  $("#seats").innerHTML = data.seats.map((s) => {
    const pct = Math.min(100, Math.round(100 * s.requested / s.capacity));
    const tag = s.status === "full" ? `<span class="tag risk-high">+${s.extra_sections} section</span>`
      : s.status === "tight" ? `<span class="tag risk-medium">${s.seats_left} left</span>` : '<span class="tag risk-low">OK</span>';
    return `<div class="seat-row"><span class="code">${esc(s.code)}</span>
      <div><div class="t">${esc(s.title)} · ${s.requested}/${s.capacity}</div><div class="seat-bar ${s.status}"><span style="width:${pct}%"></span></div></div>
      <div class="s">${tag}</div></div>`;
  }).join("");

  $("#advisees").addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-sid]");
    if (!b) return;
    b.disabled = true;
    const r = await fetch("/api/early-warning/outreach", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ student_id: b.dataset.sid }) });
    if (r.ok) { b.textContent = "✓ Check-in sent"; b.classList.replace("btn-gold", "btn-mid"); } else b.disabled = false;
  });
})();
