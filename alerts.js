// Smart Alerts (student)
(async () => {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const res = await fetch("/api/alerts");
  if (res.status === 401) { location.replace("/auth"); return; }
  if (res.status === 403) { location.replace("/dashboard"); return; }
  const data = await res.json();
  const ICON = { registration: "📝", deadline: "⏰", standing: "⚠️", repeat: "🔁", seats: "🎟️", graduation: "🎓", milestone: "⭐" };
  const n = data.alerts.filter((a) => a.level === "urgent" || a.level === "warn").length;
  $("#hero-sub").textContent = n ? `${n} item${n === 1 ? "" : "s"} need${n === 1 ? "s" : ""} your attention for ${data.term}.` : `You're all set for ${data.term}.`;
  $("#alerts").innerHTML = data.alerts.map((a) => `
    <div class="alert l-${a.level}">
      <span class="a-ico" aria-hidden="true">${ICON[a.kind] || "🔔"}</span>
      <div class="a-body"><strong>${esc(a.title)}</strong><p>${esc(a.text)}</p>
        ${a.action ? `<a class="btn btn-outline btn-sm" href="${esc(a.action.href)}">${esc(a.action.label)}</a>` : ""}</div>
    </div>`).join("");
  $("#seat-term").textContent = data.term;
  $("#seats").innerHTML = data.plan_seats.map((s) => {
    const pct = Math.min(100, Math.round(100 * s.requested / s.capacity));
    const label = s.status === "full" ? '<span class="tag no">Full · waitlist</span>'
      : s.status === "tight" ? `<span class="tag no">${s.seats_left} left</span>` : `<span class="tag ok">${s.seats_left} seats left</span>`;
    return `<div class="seat-row"><span class="code">${esc(s.code)}</span>
      <div><div class="t">${esc(s.title)}</div><div class="seat-bar ${s.status}"><span style="width:${pct}%"></span></div></div>
      <div class="s">${label}</div></div>`;
  }).join("") || '<p class="empty">No seat data for your plan.</p>';
})();
