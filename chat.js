// AI advisor chat page
(() => {
  const $ = (s) => document.querySelector(s);
  const els = {
    side: $("#side"), scrim: $("#scrim"), menu: $("#menu-btn"), list: $("#conv-list"), newChat: $("#new-chat"),
    title: $("#chat-title"), status: $(".status"), statusText: $("#status-text"),
    scroll: $("#scroll"), welcome: $("#welcome"), messages: $("#messages"), suggestions: $("#suggestions"),
    setup: $("#setup-note"), form: $("#composer"), input: $("#input"), send: $("#send"),
  };
  let user = null, configured = false, conversationId = null, busy = false, controller = null;

  const SUGGESTIONS = {
    student: [
      ["Plan Spring 2027", "What should I register for in Spring 2027? Check my prerequisites and keep it within a normal load."],
      ["Am I on track?", "Am I on track to graduate on time? What's left and how many credits do I still need?"],
      ["Can I take it yet?", "Can I take Ethical Hacking (SEC432) next semester? What do I need first?"],
      ["My GPA", "How is my GPA looking, and what would help me make the Dean's List?"],
    ],
    advisor: [
      ["Who needs help?", "Which of my advisees are at risk or on probation, and what should I do first?"],
      ["Meeting prep", "Prepare me for an advising meeting with Hessa Al Mazrouei: record summary, concerns and a suggested plan."],
      ["Graduation check", "Which of my advisees are closest to graduating, and is anything blocking them?"],
      ["Registration plans", "Suggest a Spring 2027 registration for Fatima Al Suwaidi based on her study plan."],
    ],
  };

  // ---------------------------------------------------------------- Markdown (safe subset)
  const esc = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  function inline(s) {
    return esc(s)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>")
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  }
  function markdown(text) {
    const lines = text.replace(/\r/g, "").split("\n");
    let html = "", para = [], list = null, table = null;
    const flushPara = () => { if (para.length) { html += `<p>${para.map(inline).join("<br>")}</p>`; para = []; } };
    const flushList = () => { if (list) { html += `<${list.tag}>${list.items.map((i) => `<li>${inline(i)}</li>`).join("")}</${list.tag}>`; list = null; } };
    const flushTable = () => {
      if (!table) return;
      const [head, ...rows] = table.filter((r) => !/^\s*\|?\s*:?-{2,}/.test(r));
      const cells = (r) => r.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      html += `<table><thead><tr>${cells(head).map((c) => `<th>${inline(c)}</th>`).join("")}</tr></thead><tbody>` +
        rows.map((r) => `<tr>${cells(r).map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`).join("") + "</tbody></table>";
      table = null;
    };
    const flushAll = () => { flushPara(); flushList(); flushTable(); };
    for (const line of lines) {
      let m;
      if (/^\s*\|.*\|\s*$/.test(line)) { flushPara(); flushList(); (table ||= []).push(line); continue; }
      flushTable();
      if (!line.trim()) { flushPara(); flushList(); }
      else if ((m = line.match(/^(#{1,4})\s+(.*)/))) { flushAll(); html += `<h${m[1].length < 3 ? 3 : 4}>${inline(m[2])}</h${m[1].length < 3 ? 3 : 4}>`; }
      else if ((m = line.match(/^\s*[-*•]\s+(.*)/))) { flushPara(); if (list?.tag !== "ul") { flushList(); list = { tag: "ul", items: [] }; } list.items.push(m[1]); }
      else if ((m = line.match(/^\s*\d+[.)]\s+(.*)/))) { flushPara(); if (list?.tag !== "ol") { flushList(); list = { tag: "ol", items: [] }; } list.items.push(m[1]); }
      else if (list && /^\s{2,}\S/.test(line)) { list.items[list.items.length - 1] += " " + line.trim(); }
      else { flushList(); para.push(line); }
    }
    flushAll();
    return html;
  }

  // ---------------------------------------------------------------- rendering
  function scrollToBottom(force = false) {
    const s = els.scroll;
    if (force || s.scrollHeight - s.scrollTop - s.clientHeight < 160) s.scrollTop = s.scrollHeight;
  }
  function showWelcome(show) { els.welcome.hidden = !show; }

  function addUser(text) {
    const div = document.createElement("div");
    div.className = "msg msg-user";
    div.innerHTML = `<div class="bubble" dir="auto"></div>`;
    div.querySelector(".bubble").textContent = text;
    els.messages.append(div);
    return div;
  }
  function addAI(text = "", { pending = false } = {}) {
    const div = document.createElement("div");
    div.className = "msg msg-ai";
    div.innerHTML = `<div class="avatar-ai" aria-hidden="true"><svg class="icon icon-sm"><use href="#i-cap"/></svg></div><div class="bubble" dir="auto"></div>`;
    const bubble = div.querySelector(".bubble");
    if (pending) bubble.innerHTML = `<span class="typing" aria-label="Advisor is thinking"><span></span><span></span><span></span></span>`;
    else bubble.innerHTML = markdown(text);
    els.messages.append(div);
    return bubble;
  }
  function addError(message, retryText) {
    const div = document.createElement("div");
    div.className = "msg-error";
    div.textContent = message;
    if (retryText) {
      const b = document.createElement("button");
      b.type = "button"; b.textContent = "Try again";
      b.addEventListener("click", () => { div.remove(); send(retryText, { echo: false }); });
      div.append(b);
    }
    els.messages.append(div);
    scrollToBottom(true);
  }

  // ---------------------------------------------------------------- conversations
  async function loadList() {
    const { conversations } = await (await fetch("/api/conversations")).json();
    els.list.innerHTML = "";
    if (!conversations.length) { els.list.innerHTML = `<p class="conv-empty">No conversations yet.</p>`; return; }
    for (const c of conversations) {
      const item = document.createElement("div");
      item.className = "conv-item" + (c.id === conversationId ? " active" : "");
      item.innerHTML = `<button class="conv-link" type="button"></button><button class="conv-del" type="button" aria-label="Delete conversation"><svg class="icon icon-sm"><use href="#i-trash"/></svg></button>`;
      const link = item.querySelector(".conv-link");
      link.textContent = c.title; link.title = c.title;
      link.addEventListener("click", () => { openConversation(c.id); closeSide(); });
      item.querySelector(".conv-del").addEventListener("click", async () => {
        if (busy) return;
        await fetch(`/api/conversations/${c.id}`, { method: "DELETE" });
        if (c.id === conversationId) newChat();
        loadList();
      });
      els.list.append(item);
    }
  }

  async function openConversation(id) {
    if (busy) return;
    const res = await fetch(`/api/conversations/${id}`);
    if (!res.ok) { newChat(); return; }
    const conv = await res.json();
    conversationId = conv.id;
    els.title.textContent = conv.title;
    els.messages.innerHTML = "";
    showWelcome(false);
    for (const m of conv.messages) m.role === "user" ? addUser(m.text) : addAI(m.text);
    setUrl(); loadList(); scrollToBottom(true);
    els.input.focus();
  }

  function newChat() {
    if (busy) return;
    conversationId = null;
    els.messages.innerHTML = "";
    els.title.textContent = "AI Advisor";
    showWelcome(true); setUrl(); loadList(); closeSide();
    els.input.focus();
  }
  function setUrl() {
    const url = new URL(location.href);
    conversationId ? url.searchParams.set("c", conversationId) : url.searchParams.delete("c");
    history.replaceState(null, "", url);
  }

  // ---------------------------------------------------------------- sending + streaming
  async function send(text, { echo = true } = {}) {
    if (busy || !text.trim()) return;
    if (!configured) { els.setup.hidden = false; showWelcome(true); return; }
    busy = true; updateSend();
    showWelcome(false);
    if (echo) addUser(text);
    const bubble = addAI("", { pending: true });
    scrollToBottom(true);

    let raw = "", started = false;
    const render = (final = false) => {
      bubble.innerHTML = markdown(raw);
      bubble.classList.toggle("cursor", !final);
      scrollToBottom();
    };

    try {
      controller = new AbortController();
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, conversation_id: conversationId }),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Something went wrong. Please try again.");
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "", failed = null;
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buffer.indexOf("\n\n")) !== -1) {
          const chunk = buffer.slice(0, idx); buffer = buffer.slice(idx + 2);
          const event = (chunk.match(/^event: (.*)$/m) || [])[1];
          const data = JSON.parse((chunk.match(/^data: (.*)$/m) || [])[1] || "{}");
          if (event === "meta") {
            if (!conversationId) { conversationId = data.conversation_id; setUrl(); }
          } else if (event === "delta") {
            if (!started) { started = true; bubble.innerHTML = ""; }
            raw += data.text; render();
          } else if (event === "reset") {
            raw = ""; started = false;
            bubble.innerHTML = `<span class="typing"><span></span><span></span><span></span></span>`;
          } else if (event === "done") {
            raw = data.text; render(true);
            if (data.note) bubble.insertAdjacentHTML("beforeend", `<p class="msg-note">${esc(data.note)}</p>`);
          } else if (event === "error") {
            failed = data.message;
          }
        }
      }
      if (failed) throw new Error(failed);
      if (!raw) throw new Error("The advisor didn't reply. Please try again.");
    } catch (err) {
      bubble.closest(".msg").remove();
      if (err.name !== "AbortError") addError(err.message, text);
    } finally {
      busy = false; controller = null; updateSend();
      await loadList();
      if (conversationId) {
        const title = els.list.querySelector(".conv-item.active .conv-link")?.textContent;
        if (title) els.title.textContent = title;
      }
    }
  }

  // ---------------------------------------------------------------- composer
  function updateSend() { els.send.disabled = busy || !els.input.value.trim(); }
  function autosize() { els.input.style.height = "auto"; els.input.style.height = Math.min(els.input.scrollHeight, 192) + "px"; }
  els.input.addEventListener("input", () => { autosize(); updateSend(); });
  els.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); els.form.requestSubmit(); }
  });
  els.form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = els.input.value.trim();
    if (!text || busy) return;
    els.input.value = ""; autosize(); updateSend();
    send(text);
  });

  // ---------------------------------------------------------------- sidebar drawer (mobile)
  function openSide() { els.side.classList.add("open"); els.scrim.hidden = false; }
  function closeSide() { els.side.classList.remove("open"); els.scrim.hidden = true; }
  els.menu.addEventListener("click", openSide);
  els.scrim.addEventListener("click", closeSide);
  els.newChat.addEventListener("click", newChat);

  // ---------------------------------------------------------------- init
  (async () => {
    ({ user } = await (await fetch("/api/me")).json());
    if (!user) { location.replace("/auth"); return; }
    $("#first-name").textContent = user.name.split(/\s+/)[0];
    for (const [title, prompt] of SUGGESTIONS[user.role] || SUGGESTIONS.student) {
      const b = document.createElement("button");
      b.type = "button"; b.className = "suggestion";
      b.innerHTML = `<strong></strong><span></span>`;
      b.querySelector("strong").textContent = title;
      b.querySelector("span").textContent = prompt;
      b.addEventListener("click", () => send(prompt));
      els.suggestions.append(b);
    }
    const status = await (await fetch("/api/chat/status")).json();
    configured = status.configured;
    if (configured) els.statusText.textContent = `Online · powered by ${status.provider}`;
    if (!configured) {
      els.setup.hidden = false;
      els.status.classList.add("offline");
      els.statusText.textContent = "Not connected — API key needed";
    }
    const params = new URLSearchParams(location.search);
    const startId = Number(params.get("c"));
    if (startId) openConversation(startId); else loadList();
    // /chat?q=... (from the record page): start a new chat with that question
    const q = params.get("q");
    if (q && !startId) {
      history.replaceState(null, "", "/chat");
      send(q.slice(0, 4000));
    }
    els.input.focus();
  })();
})();
