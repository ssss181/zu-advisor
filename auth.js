// Sign in / create account page
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const tabs = { signin: $("#tab-signin"), signup: $("#tab-signup") };
  const forms = { signin: $("#form-signin"), signup: $("#form-signup") };
  const errorBox = $("#form-error");
  const copy = {
    signin: ["Welcome back", "Sign in to continue planning your semester."],
    signup: ["Create your account", "Get a conflict-free plan and a clear path to graduation."],
  };

  function setMode(mode, { focus = false } = {}) {
    for (const m of ["signin", "signup"]) {
      tabs[m].setAttribute("aria-selected", String(m === mode));
      forms[m].hidden = m !== mode;
    }
    $("#auth-title").textContent = copy[mode][0];
    $("#auth-subtitle").textContent = copy[mode][1];
    document.title = (mode === "signup" ? "Create account" : "Sign in") + " — ZU Advisor";
    clearErrors();
    const url = new URL(location.href);
    mode === "signup" ? url.searchParams.set("mode", "signup") : url.searchParams.delete("mode");
    history.replaceState(null, "", url);
    if (focus) forms[mode].querySelector("input:not([type=radio])")?.focus();
  }

  tabs.signin.addEventListener("click", () => setMode("signin", { focus: true }));
  tabs.signup.addEventListener("click", () => setMode("signup", { focus: true }));
  // Arrow keys move between tabs
  $(".tabs").addEventListener("keydown", (e) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    const next = tabs.signin.getAttribute("aria-selected") === "true" ? "signup" : "signin";
    setMode(next); tabs[next].focus();
  });

  // Errors
  function clearErrors() {
    errorBox.hidden = true; errorBox.textContent = "";
    document.querySelectorAll("[aria-invalid]").forEach((el) => el.removeAttribute("aria-invalid"));
  }
  function showError(msg, form, field) {
    errorBox.textContent = msg; errorBox.hidden = false;
    const input = field && form?.querySelector(`[name="${field}"]`);
    if (input) { input.setAttribute("aria-invalid", "true"); input.focus(); }
  }

  // Show / hide password
  document.querySelectorAll(".pw-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const input = btn.previousElementSibling;
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
      btn.querySelector("use").setAttribute("href", show ? "#i-eye-off" : "#i-eye");
    });
  });

  // Concentration + semester only apply to students
  const studentFields = $("#student-fields");
  forms.signup.querySelectorAll('input[name="role"]').forEach((r) =>
    r.addEventListener("change", () => { studentFields.hidden = forms.signup.elements.role.value !== "student"; }));

  // Password strength bar
  const meter = $(".pw-meter span");
  $("#su-password").addEventListener("input", (e) => {
    const v = e.target.value;
    let score = 0;
    if (v.length >= 8) score++;
    if (v.length >= 12) score++;
    if (/[A-Z]/.test(v) && /[a-z]/.test(v)) score++;
    if (/\d/.test(v)) score++;
    if (/[^A-Za-z0-9]/.test(v)) score++;
    const colors = ["hsl(0 70% 42%)", "hsl(0 70% 42%)", "hsl(32 85% 48%)", "hsl(42 55% 48%)", "hsl(145 45% 32%)", "hsl(145 45% 32%)"];
    meter.style.width = v ? Math.max(15, score * 20) + "%" : "0";
    meter.style.background = colors[score];
  });

  // API helper
  async function post(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw Object.assign(new Error(data.error || "Something went wrong. Please try again."), { field: data.field });
    return data;
  }

  function busy(btn, on, label) {
    if (on) { btn.dataset.label = btn.innerHTML; btn.disabled = true; btn.innerHTML = `<span class="spinner"></span>${label}`; }
    else { btn.disabled = false; btn.innerHTML = btn.dataset.label; }
  }

  // Sign in
  forms.signin.addEventListener("submit", async (e) => {
    e.preventDefault(); clearErrors();
    const f = forms.signin, btn = f.querySelector("[type=submit]");
    const el = f.elements;
    const email = el.email.value.trim(), password = el.password.value;
    if (!email) return showError("Please enter your email.", f, "email");
    if (!password) return showError("Please enter your password.", f, "password");
    busy(btn, true, "Signing in…");
    try {
      await post("/api/login", { email, password, remember: el.remember.checked });
      location.href = "/dashboard";
    } catch (err) { busy(btn, false); showError(err.message, f, err.field); }
  });

  // Sign up
  forms.signup.addEventListener("submit", async (e) => {
    e.preventDefault(); clearErrors();
    const f = forms.signup, btn = f.querySelector("[type=submit]");
    const el = f.elements;
    const body = { name: el.name.value.trim(), email: el.email.value.trim(), password: el.password.value, role: el.role.value,
                   program: el.program.value, semester: Number(el.semester.value) };
    if (body.name.length < 2) return showError("Please enter your full name.", f, "name");
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(body.email)) return showError("Please enter a valid email address.", f, "email");
    if (body.password.length < 8) return showError("Password must be at least 8 characters.", f, "password");
    busy(btn, true, "Creating account…");
    try {
      await post("/api/signup", body);
      location.href = "/dashboard";
    } catch (err) {
      busy(btn, false); showError(err.message, f, err.field);
      if (err.message.includes("already exists")) { forms.signin.elements.email.value = body.email; }
    }
  });

  // Demo buttons
  document.querySelectorAll("[data-demo]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      clearErrors(); busy(btn, true, "Opening demo…");
      try { await post("/api/demo", { role: btn.dataset.demo }); location.href = "/dashboard"; }
      catch (err) { busy(btn, false); showError(err.message); }
    });
  });

  // Initial mode from ?mode=signup, or #signup
  const params = new URLSearchParams(location.search);
  setMode(params.get("mode") === "signup" || location.hash === "#signup" ? "signup" : "signin");
})();
