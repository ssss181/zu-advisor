"""AI advisor chat — streamed to the browser with Server-Sent Events.

Two AI providers are supported; the first one with a key in .env is used:
  1. Google Gemini   GEMINI_API_KEY=...      (free tier at https://aistudio.google.com/apikey)
  2. Anthropic Claude ANTHROPIC_API_KEY=...  (paid, https://console.anthropic.com)
Set CHAT_PROVIDER=gemini or CHAT_PROVIDER=claude to force one, and GEMINI_MODEL / CLAUDE_MODEL
to change the model.

Conversations are stored in SQLite. Each assistant turn is stored with the raw data the
provider returned (Claude content blocks incl. thinking blocks, or Gemini parts incl. thought
signatures) and sent back unchanged on the next turn, as both providers ask. History is
append-only and the system prompt is frozen per conversation.

The .env file lives next to server.py and is never served to the browser.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Callable, Iterator

from flask import Flask, Response, abort, jsonify, request, stream_with_context


# Hosted (e.g. Render): the platform's proxy puts the visitor's IP in X-Forwarded-For, which
# server.py's ProxyFix turns into request.remote_addr. Local + Cloudflare quick tunnel: the
# server only listens on 127.0.0.1, so CF-Connecting-IP can only come via the tunnel.
HOSTED = bool(os.environ.get("RENDER") or os.environ.get("ZU_HOSTED"))


def client_ip() -> str:
    if HOSTED:
        return request.remote_addr or "?"
    return request.headers.get("CF-Connecting-IP") or request.remote_addr or "?"

MAX_TOKENS = 16000          # plenty for a chat reply
MAX_MESSAGE_CHARS = 4000
# Per-person limit so a demo visitor can't use up the API quota.
RATE_LIMIT = 30             # messages
RATE_WINDOW = 10 * 60       # seconds
_recent: dict[str, list[float]] = {}

SYSTEM_PROMPT = """You are ZU Advisor, an AI academic advisor for Zayed University (UAE), \
helping {role_desc} named {name}.

What you help with: planning semesters, understanding prerequisites and course sequencing, \
balancing credit loads, avoiding schedule clashes, registration strategy, academic policies \
in general terms, and staying on track to graduate on time.

What you have (below): {have}. Course codes, titles, credits and recommended semesters come \
from ZU's official 2025 study plans for the B.Sc. in Information Technology; prerequisites come \
from the ZU Catalog 2021-2022 and may have changed. The student record(s) are SAMPLE data for \
this prototype — treat them as the user's record in conversation without repeating that \
disclaimer, unless asked.

Rules:
- Base course advice on the record and study plan below: check prerequisites and co-requisites \
(labs must be taken with their lecture), the recommended semester order, credit totals and the \
policies. Name courses by code and title. Add up credits when proposing a semester.
- Requirements come ONLY from the REGISTRATION RULES and study plan below — the same rules ZU's registration engine runs. Never add requirements that aren't there (e.g. don't say a lab or course must be *passed* before another unless it is a listed prerequisite). When citing a requirement, name its rule ID (e.g. PRQ-01). If you're unsure, say so and suggest checking the Registration page, which runs the rules exactly.
- When a plan breaks a rule, give the fix AND say the student can request an exception with a reason on the Registration page; their advisor decides within 48 hours.
- Only use course codes listed below. Don't invent other ZU courses, sections, instructors, \
class times, seat counts or deadlines — you don't have timetables or seat data; say so and \
point to the Registrar / ZU portal when needed.
- If asked about other programmes, explain that only the B.Sc. IT (both concentrations) is loaded.
- Free electives can be any ZU course; you don't have the elective list.

Style: warm, clear and practical. Keep answers short — a few sentences or a compact list — \
unless the user asks for a full plan. Use plain Markdown (short lists, **bold** for key \
points); no tables wider than 4 columns. Reply in the language the user writes in (English \
or Arabic).

{context}"""


def _plan_text(program: str) -> str:
    from catalog import COURSES, ELECTIVE, PROGRAMS
    p = PROGRAMS[program]
    lines = [f"OFFICIAL STUDY PLAN: {p['name']} — {p['total_credits']} credits"]
    for i, sem in enumerate(p["plan"], 1):
        items = []
        for c in sem:
            if c == ELECTIVE:
                items.append("Free elective (3)")
                continue
            v = COURSES[c]
            req = []
            if v["prereqs"]:
                req.append("prereq " + "+".join(v["prereqs"]))
            if v["coreqs"]:
                req.append("with " + "+".join(v["coreqs"]))
            items.append(f"{c} {v['title']} ({v['credits']}{'; ' + '; '.join(req) if req else ''})")
        lines.append(f"  Semester {i}: " + " | ".join(items))
    lines.append(f"  Internship semester: {p['internship']} {COURSES[p['internship']]['title']} (6)")
    return "\n".join(lines)


def build_system_prompt(user: dict, record_for_user) -> str:
    """System prompt with the user's sample record (students) or advisees (advisors)."""
    import students
    from catalog import POLICIES, PROGRAMS
    import rules
    policies = ("REGISTRATION RULES (checked automatically by the registration engine; versioned per catalog year):\n"
                + "\n".join(f"- {rid} {r['name']}: {r['text']} (source: {r['source']}; owner: {r['owner']})"
                            for rid, r in rules.RULES.items())
                + "\n\nZU POLICIES (Catalog 2021-2022):\n" + "\n".join(f"- {x}" for x in POLICIES))
    if user["role"] == "advisor":
        context = "\n\n".join([students.advisees_for_ai()] + [_plan_text(p) for p in PROGRAMS] + [policies])
        have = "your advisees' sample records, both B.Sc. IT study plans with prerequisites, and key ZU policies"
        role_desc = "a faculty advisor"
    else:
        rec = record_for_user(user)
        context = "\n\n".join([students.record_for_ai(rec), _plan_text(rec["program"]), policies])
        have = "the student's academic record, their programme's study plan with prerequisites, and key ZU policies"
        role_desc = "a student"
    return SYSTEM_PROMPT.format(role_desc=role_desc, name=user["name"], have=have, context=context)

REFUSAL_TEXT = "Sorry — I can't help with that request. Try rephrasing it."


class Refused(Exception):
    """The provider's safety system declined to answer."""


# ======================================================================== providers
# A provider's stream(system, history) is a generator that yields ("delta", text) and
# ("reset", None) events, and finally returns (content_to_store, stop_note_or_None).
# `history` is a list of {"role": "user"|"assistant", "content": <stored JSON>}.

def display_text(content) -> str:
    """Text to show in the UI for a stored message."""
    if isinstance(content, str):
        return content
    blocks = content
    for i, b in enumerate(content):            # Claude: text after a fallback switch only
        if b.get("type") == "fallback":
            blocks = content[i + 1:]
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


class GeminiProvider:
    name = "gemini"
    label = "Google Gemini"

    def __init__(self, api_key: str):
        from google import genai
        from google.genai import errors, types
        self.genai, self.types, self.errors = genai, types, errors
        self.model = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
        # Backups tried in order when a model is overloaded (503) or out of free quota (429).
        fallbacks = os.environ.get("GEMINI_FALLBACKS", "gemini-3.5-flash-lite,gemini-3.6-flash")
        self.models = [self.model] + [m.strip() for m in fallbacks.split(",") if m.strip() and m.strip() != self.model]
        self.client = genai.Client(api_key=api_key)

    def _contents(self, history: list[dict], model: str) -> list:
        T = self.types
        out = []
        for m in history:
            c = m["content"]
            if m["role"] == "user":
                out.append(T.Content(role="user", parts=[T.Part(text=c)]))
                continue
            gem = next((b for b in c if b.get("type") == "gemini_parts"), None) if isinstance(c, list) else None
            if gem and gem.get("model") == model:
                # same model wrote it: send its parts back unchanged (keeps thought signatures)
                out.append(T.Content.model_validate({"role": "model", "parts": gem["parts"]}))
            else:     # written by another model/provider: plain text (signatures are model-specific)
                out.append(T.Content(role="model", parts=[T.Part(text=display_text(c))]))
        return out

    def stream(self, system: str, history: list[dict]) -> Iterator:
        """Try each model in turn; move to the next only if a model fails before replying."""
        for i, model in enumerate(self.models):
            started = False
            try:
                gen = self._stream_model(model, system, history)
                while True:
                    try:
                        event = next(gen)
                    except StopIteration as stop:
                        return stop.value
                    started = True
                    yield event
            except Exception as exc:
                is_api = isinstance(exc, self.errors.APIError)
                busy = (is_api and exc.code in (429, 500, 503)) or "timeout" in type(exc).__name__.lower()
                if started or not busy or i == len(self.models) - 1:
                    raise
                why = exc.code if is_api else "no response in time"
                print(f"[chat] {model} unavailable ({why}); trying {self.models[i + 1]}", flush=True)

    def _stream_model(self, model: str, system: str, history: list[dict]) -> Iterator:
        T = self.types
        last = model == self.models[-1]
        config = T.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=MAX_TOKENS,
            thinking_config=T.ThinkingConfig(thinking_level="low"),  # snappy chat replies
            # Max silence between chunks of the reply. Busy free models sometimes queue a
            # request for a long time; giving up early lets us switch to a backup model.
            http_options=T.HttpOptions(timeout=60_000 if last else 10_000),  # Google's minimum is 10s
        )
        parts, text, finish, blocked = [], "", None, None
        for chunk in self.client.models.generate_content_stream(
            model=model, contents=self._contents(history, model), config=config
        ):
            if chunk.prompt_feedback and chunk.prompt_feedback.block_reason:
                blocked = chunk.prompt_feedback.block_reason
            cand = chunk.candidates[0] if chunk.candidates else None
            if cand is None:
                continue
            if cand.content and cand.content.parts:
                parts.extend(p.model_dump(mode="json", exclude_none=True) for p in cand.content.parts)
            if cand.finish_reason:
                finish = cand.finish_reason
            delta = chunk.text   # excludes internal "thought" parts
            if delta:
                text += delta
                yield ("delta", delta)

        R = T.FinishReason
        if blocked or finish in (R.SAFETY, R.PROHIBITED_CONTENT, R.BLOCKLIST, R.SPII, R.RECITATION):
            raise Refused()
        if not text:
            raise RuntimeError(f"empty Gemini reply (finish_reason={finish})")
        note = "The reply was cut off — ask me to continue." if finish == R.MAX_TOKENS else None
        return [{"type": "text", "text": text}, {"type": "gemini_parts", "model": model, "parts": parts}], note

    def friendly_error(self, exc: Exception) -> str:
        E = self.errors
        if isinstance(exc, E.ClientError):
            if exc.code == 429:
                return ("The free AI quota is used up on all models for now (Gemini free tier limits). "
                        "Try again in a minute, or tomorrow if the daily limit was reached.")
            if exc.code in (400, 401, 403) and "key" in (exc.message or "").lower():
                return "The Gemini API key was rejected. Check GEMINI_API_KEY in the .env file."
            if exc.code == 404:
                return f"The AI model '{self.model}' wasn't found. Check GEMINI_MODEL in the .env file."
            return "The AI advisor couldn't process that request."
        if isinstance(exc, E.ServerError):
            return "Google's AI models are very busy right now. Please try again in a minute."
        return _generic_error(exc)


class ClaudeProvider:
    name = "claude"
    label = "Anthropic Claude"

    def __init__(self, api_key: str):
        import anthropic
        self.anthropic = anthropic
        self.model = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
        self.client = anthropic.Anthropic(api_key=api_key)

    def stream(self, system: str, history: list[dict]) -> Iterator:
        messages = []
        for m in history:
            c = m["content"]
            if m["role"] == "assistant" and isinstance(c, list) and any(b.get("type") == "gemini_parts" for b in c):
                c = [{"type": "text", "text": display_text(c)}]   # reply written by Gemini
            messages.append({"role": m["role"], "content": c})
        with self.client.beta.messages.stream(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
            output_config={"effort": "medium"},
            cache_control={"type": "ephemeral"},
            # If the safety classifier declines, the API re-runs the request on a
            # suitable fallback model inside the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            for event in stream:
                if event.type == "content_block_start" and event.content_block.type == "fallback":
                    yield ("reset", None)   # text so far came from a model that declined
                elif event.type == "content_block_delta" and event.delta.type == "text_delta":
                    yield ("delta", event.delta.text)
            final = stream.get_final_message()
        if final.stop_reason == "refusal":
            raise Refused()
        note = "The reply was cut off — ask me to continue." if final.stop_reason == "max_tokens" else None
        return final.to_dict()["content"], note   # stored and replayed unchanged

    def friendly_error(self, exc: Exception) -> str:
        a = self.anthropic
        if isinstance(exc, a.AuthenticationError):
            return "The Claude API key was rejected. Check ANTHROPIC_API_KEY in the .env file."
        if isinstance(exc, a.PermissionDeniedError):
            return "This API key doesn't have access to the AI model."
        if isinstance(exc, a.RateLimitError):
            return "The AI advisor is busy right now. Please try again in a minute."
        if isinstance(exc, a.BadRequestError):
            msg = str(exc).lower()
            if "credit" in msg or "billing" in msg:
                return "The Anthropic account has no credit left. Add credit in the Anthropic Console."
            return "The AI advisor couldn't process that request."
        if isinstance(exc, a.APIStatusError):
            return "The AI service had a problem. Please try again shortly."
        if isinstance(exc, a.APIConnectionError):
            return "Couldn't reach the AI service. Check your internet connection."
        return _generic_error(exc)


def _generic_error(exc: Exception) -> str:
    if "connect" in type(exc).__name__.lower() or isinstance(exc, (ConnectionError, TimeoutError)):
        return "Couldn't reach the AI service. Check your internet connection."
    return "Something went wrong. Please try again."


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader (KEY=value lines) so keys live in a file, not the code."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def pick_provider():
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    claude_key = os.environ.get("ANTHROPIC_API_KEY")
    forced = os.environ.get("CHAT_PROVIDER", "").strip().lower()
    if forced == "claude" and claude_key:
        return ClaudeProvider(claude_key)
    if forced == "gemini" and gemini_key:
        return GeminiProvider(gemini_key)
    if gemini_key:
        return GeminiProvider(gemini_key)
    if claude_key:
        return ClaudeProvider(claude_key)
    return None


PROVIDER = None   # set by register()


def complete(system: str, prompt: str) -> str:
    """One-shot AI answer (no saved conversation), using the configured provider."""
    if PROVIDER is None:
        raise RuntimeError("no AI provider configured")
    gen = PROVIDER.stream(system, [{"role": "user", "content": prompt}])
    text = ""
    while True:
        try:
            kind, value = next(gen)
        except StopIteration as stop:
            content, _note = stop.value
            return display_text(content) or text
        if kind == "delta":
            text += value
        elif kind == "reset":
            text = ""


# ======================================================================== routes
def register(app: Flask, *, db_path: Path, root: Path,
             current_user: Callable[[], dict | None], user_key: Callable[[], str | None]) -> None:
    global PROVIDER
    _load_dotenv(root / ".env")
    provider = PROVIDER = pick_provider()
    app.logger.info("chat provider: %s", f"{provider.label} ({provider.model})" if provider else "none")

    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """CREATE TABLE IF NOT EXISTS conversations (
                   id         INTEGER PRIMARY KEY AUTOINCREMENT,
                   owner      TEXT NOT NULL,          -- 'u:<user id>' or 'demo:<token>'
                   title      TEXT NOT NULL,
                   system     TEXT NOT NULL,          -- frozen for the conversation's lifetime
                   created_at TEXT NOT NULL DEFAULT (datetime('now')),
                   updated_at TEXT NOT NULL DEFAULT (datetime('now'))
               );
               CREATE INDEX IF NOT EXISTS conv_owner ON conversations(owner, updated_at);
               CREATE TABLE IF NOT EXISTS chat_messages (
                   id              INTEGER PRIMARY KEY AUTOINCREMENT,
                   conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                   role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                   content         TEXT NOT NULL,     -- JSON: a string or a list of content blocks
                   created_at      TEXT NOT NULL DEFAULT (datetime('now'))
               );"""
        )

    def connect() -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def owned_conversation(conn, conv_id: int, owner: str):
        row = conn.execute("SELECT * FROM conversations WHERE id = ? AND owner = ?", (conv_id, owner)).fetchone()
        if row is None:
            abort(404)
        return row

    def require_owner() -> str:
        owner = user_key()
        if owner is None:
            abort(401)
        return owner

    @app.get("/api/chat/status")
    def chat_status():
        require_owner()
        return jsonify({
            "configured": provider is not None,
            "provider": provider.label if provider else None,
            "model": provider.model if provider else None,
        })

    @app.get("/api/conversations")
    def list_conversations():
        owner = require_owner()
        with connect() as conn:
            rows = conn.execute(
                "SELECT id, title, updated_at FROM conversations WHERE owner = ? ORDER BY updated_at DESC LIMIT 50",
                (owner,),
            ).fetchall()
        return jsonify({"conversations": [dict(r) for r in rows]})

    @app.get("/api/conversations/<int:conv_id>")
    def get_conversation(conv_id: int):
        owner = require_owner()
        with connect() as conn:
            conv = owned_conversation(conn, conv_id, owner)
            rows = conn.execute(
                "SELECT role, content FROM chat_messages WHERE conversation_id = ? ORDER BY id", (conv_id,)
            ).fetchall()
        messages = [{"role": r["role"], "text": display_text(json.loads(r["content"]))} for r in rows]
        return jsonify({"id": conv["id"], "title": conv["title"], "messages": messages})

    @app.delete("/api/conversations/<int:conv_id>")
    def delete_conversation(conv_id: int):
        owner = require_owner()
        with connect() as conn:
            owned_conversation(conn, conv_id, owner)
            conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        return jsonify({"ok": True})

    @app.post("/api/chat")
    def chat():
        owner = require_owner()
        if not request.is_json:
            abort(415)
        if provider is None:
            return jsonify({"error": "The AI advisor isn't set up yet: add GEMINI_API_KEY to the .env file and restart the server."}), 503

        data = request.get_json(silent=True) or {}
        text = str(data.get("message", "")).strip()
        conv_id = data.get("conversation_id")
        if not text:
            return jsonify({"error": "Type a message first."}), 400
        if len(text) > MAX_MESSAGE_CHARS:
            return jsonify({"error": f"Messages are limited to {MAX_MESSAGE_CHARS} characters."}), 400

        # Limit per account AND per visitor IP, so repeated demo logins can't use up the
        # free AI quota.
        ip = client_ip()
        now = time.time()
        buckets = [owner, f"ip:{ip}"]
        for b in buckets:
            _recent[b] = [t for t in _recent.get(b, []) if now - t < RATE_WINDOW]
        if any(len(_recent[b]) >= RATE_LIMIT for b in buckets):
            return jsonify({"error": "You've sent a lot of messages in a short time. Please wait a few minutes."}), 429
        for b in buckets:
            _recent[b].append(now)

        user = current_user()
        conn = connect()
        if conv_id:
            conv = owned_conversation(conn, int(conv_id), owner)
            conv_id, system = conv["id"], conv["system"]
            # If the server stopped mid-reply, a question may be left without an answer: drop it.
            last = conn.execute(
                "SELECT id, role FROM chat_messages WHERE conversation_id = ? ORDER BY id DESC LIMIT 1", (conv_id,)
            ).fetchone()
            if last and last["role"] == "user":
                conn.execute("DELETE FROM chat_messages WHERE id = ?", (last["id"],))
        else:
            import students
            system = build_system_prompt(user, lambda u: students.record_for_user(db_path, u))
            title = text if len(text) <= 60 else text[:57].rstrip() + "…"
            conv_id = conn.execute(
                "INSERT INTO conversations (owner, title, system) VALUES (?, ?, ?)", (owner, title, system)
            ).lastrowid
        user_msg_id = conn.execute(
            "INSERT INTO chat_messages (conversation_id, role, content) VALUES (?, 'user', ?)",
            (conv_id, json.dumps(text)),
        ).lastrowid
        conn.commit()

        history = [
            {"role": r["role"], "content": json.loads(r["content"])}
            for r in conn.execute(
                "SELECT role, content FROM chat_messages WHERE conversation_id = ? ORDER BY id", (conv_id,)
            )
        ]

        def sse(event: str, payload: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(payload)}\n\n"

        def generate():
            yield sse("meta", {"conversation_id": conv_id})
            try:
                gen = provider.stream(system, history)
                while True:
                    try:
                        kind, value = next(gen)
                    except StopIteration as stop:
                        content, note = stop.value
                        break
                    yield sse("delta", {"text": value}) if kind == "delta" else sse("reset", {})

                conn.execute(
                    "INSERT INTO chat_messages (conversation_id, role, content) VALUES (?, 'assistant', ?)",
                    (conv_id, json.dumps(content)),
                )
                conn.execute("UPDATE conversations SET updated_at = datetime('now') WHERE id = ?", (conv_id,))
                conn.commit()
                yield sse("done", {"text": display_text(content), "note": note})

            except Exception as exc:  # keep history consistent: drop the unanswered user turn
                conn.execute("DELETE FROM chat_messages WHERE id = ?", (user_msg_id,))
                conn.commit()
                if isinstance(exc, Refused):
                    yield sse("error", {"message": REFUSAL_TEXT})
                else:
                    app.logger.warning("chat error: %r", exc)
                    yield sse("error", {"message": provider.friendly_error(exc)})
            finally:
                conn.close()

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
