// Policy Database (students and advisors)
(async () => {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const [res, me] = await Promise.all([fetch("/api/policies"), fetch("/api/me").then((r) => r.json()).catch(() => ({}))]);
  if (res.status === 401) { location.replace("/auth"); return; }
  const data = await res.json();
  if (me.user?.role === "advisor") {
    $("#nav-reg").textContent = "Approvals"; $("#nav-alerts").textContent = "Early Warning"; $("#nav-record").textContent = "My Advisees";
  }
  $("#note").textContent = data.note;

  const today = new Date(); today.setHours(0, 0, 0, 0);
  const fmt = (iso) => new Date(iso + "T00:00:00").toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" });
  $("#dates").innerHTML = data.calendar.map((d) => {
    const days = Math.round((new Date(d.date + "T00:00:00") - today) / 86400000);
    const tag = days < 0 ? "" : days === 0 ? '<span class="tag no soon-tag">today</span>'
      : days <= 16 ? `<span class="tag no soon-tag">in ${days} days</span>` : "";
    return `<div class="date-row"><span>${esc(d.label)}${tag}</span><span class="d">${fmt(d.date)}</span></div>`;
  }).join("");
  const dot = { green: "lvl-ok", amber: "lvl-amber", red: "lvl-red" };
  $("#service").innerHTML = data.service.map((s) =>
    `<div class="check"><span class="lvl ${dot[s.tier]}"></span><div><strong>${esc(s.name)}</strong> — ${esc(s.standard)}</div></div>`).join("");

  const hl = (text, q) => {
    const t = esc(text);
    if (!q) return t;
    const re = new RegExp("(" + esc(q).replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "gi");
    return t.replace(re, "<mark>$1</mark>");
  };
  function render() {
    const q = $("#q").value.trim();
    const ql = q.toLowerCase();
    const rules = data.rules.filter((r) => !ql || [r.id, r.name, r.text, r.owner, r.source].join(" ").toLowerCase().includes(ql));
    const pols = data.policies.filter((p) => !ql || p.toLowerCase().includes(ql));
    const n = rules.length + pols.length;
    $("#count").textContent = `${n} result${n === 1 ? "" : "s"}`;
    $("#rules").innerHTML = rules.map((r) => `
      <div class="rule-card"><span class="rid">${esc(r.id)}</span><h3>${hl(r.name, q)}</h3>
        <p>${hl(r.text, q)}</p>
        <div class="meta"><span class="tag gold">Owner: ${hl(r.owner, q)}</span><span class="tag">Source: ${hl(r.source, q)}</span><span class="tag ok">Checked automatically</span></div>
      </div>`).join("") || '<p class="empty">No rules match.</p>';
    $("#policies").innerHTML = pols.map((p) => `<div class="policy-li">${hl(p, q)}</div>`).join("") || '<p class="empty">No policies match.</p>';
  }
  $("#q").addEventListener("input", render);
  const q = new URLSearchParams(location.search).get("q");
  if (q) $("#q").value = q;
  render();
})();
