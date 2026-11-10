"""ZU Advisor — local web server with accounts.

Run:   .venv\\Scripts\\python server.py      then open http://localhost:5178

Pages:  /            landing page
        /auth        sign in / create account   (/auth?mode=signup opens the sign-up tab)
        /dashboard   signed-in home (redirects to /auth when signed out)
        /chat        AI advisor chat (see chat.py; needs GEMINI_API_KEY or ANTHROPIC_API_KEY in .env)
        /record      student: sample academic record + graduation tracker; advisor: advisees
        /catalog     real ZU course catalogue (B.Sc. IT, 2025 plans)
        /register    student: Smart Registration (auto-approval); advisor: exception queue

API (JSON):
        POST /api/signup   {name, email, password, role, program?, semester?}
        GET  /api/record   the signed-in student's sample record (or an advisor's advisees)
        GET  /api/catalog  courses, programmes, policies
        POST /api/login    {email, password}
        POST /api/demo     {role: "student" | "advisor"}
        POST /api/logout
        GET  /api/me
"""
from __future__ import annotations

import os
import re
import secrets
import sqlite3
import time
from pathlib import Path

from flask import Flask, abort, g, jsonify, redirect, request, send_from_directory, session
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

import chat
import insights
import registration
import students
from catalog import PROGRAMS, catalog_for_api

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "zu_advisor.db"
SECRET_PATH = DATA_DIR / "secret_key"

ROLES = {"student", "advisor"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8

# Brute-force guard: after MAX_FAILS wrong passwords for one email, lock it for LOCK_SECONDS.
MAX_FAILS = 5
LOCK_SECONDS = 5 * 60
_failed: dict[str, list[float]] = {}

DEMO_USERS = {
    "student": {"id": "demo-student", "name": "Demo Student", "email": "student.demo@zu.ac.ae", "role": "student"},
    "advisor": {"id": "demo-advisor", "name": "Demo Advisor", "email": "advisor.demo@zu.ac.ae", "role": "advisor"},
}


def _secret_key() -> bytes:
    # On a host, set SECRET_KEY so sign-ins survive restarts (render.yaml generates one).
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"].encode()
    DATA_DIR.mkdir(exist_ok=True)
    if not SECRET_PATH.exists():
        SECRET_PATH.write_bytes(secrets.token_bytes(32))
    return SECRET_PATH.read_bytes()


app = Flask(__name__, static_folder=None)
app.config.update(
    SECRET_KEY=_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 7,  # "remember me" lasts a week
    SESSION_COOKIE_SECURE=chat.HOSTED,              # hosted = always HTTPS
)
if chat.HOSTED:
    # Trust exactly one proxy hop (the platform's load balancer) for the client IP and https.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)


# ---------------------------------------------------------------- database
def db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def _close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                   id            INTEGER PRIMARY KEY AUTOINCREMENT,
                   name          TEXT NOT NULL,
                   email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
                   password_hash TEXT NOT NULL,
                   role          TEXT NOT NULL CHECK (role IN ('student', 'advisor')),
                   created_at    TEXT NOT NULL DEFAULT (datetime('now'))
               )"""
        )


def public_user(row) -> dict:
    return {"id": row["id"], "name": row["name"], "email": row["email"], "role": row["role"]}


def current_user() -> dict | None:
    if "demo" in session:
        return {**DEMO_USERS[session["demo"]], "demo": True}
    uid = session.get("uid")
    if uid is None:
        return None
    row = db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if row is None:  # account was deleted
        session.clear()
        return None
    return public_user(row)


def start_session(*, uid=None, demo=None, remember=False) -> None:
    session.clear()
    session.permanent = bool(remember)
    if uid is not None:
        session["uid"] = uid
    if demo is not None:
        session["demo"] = demo
        session["demo_key"] = secrets.token_hex(12)  # keeps each demo visitor's chats separate


def user_key() -> str | None:
    """Stable owner id for stored data: 'u:<id>' for accounts, 'demo:<token>' for demo visitors."""
    user = current_user()
    if user is None:
        return None
    return f"demo:{session['demo_key']}" if user.get("demo") else f"u:{user['id']}"


def err(message: str, status: int = 400, field: str | None = None):
    body = {"error": message}
    if field:
        body["field"] = field
    return jsonify(body), status


def json_body() -> dict:
    # Only accept real JSON requests — a plain HTML form on another site can't send these.
    if not request.is_json:
        abort(415)
    return request.get_json(silent=True) or {}


# ---------------------------------------------------------------- API
@app.post("/api/signup")
def api_signup():
    data = json_body()
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    role = str(data.get("role", "student")).strip().lower()

    if len(name) < 2:
        return err("Please enter your full name.", field="name")
    if not EMAIL_RE.match(email):
        return err("Please enter a valid email address.", field="email")
    if len(password) < MIN_PASSWORD:
        return err(f"Password must be at least {MIN_PASSWORD} characters.", field="password")
    if role not in ROLES:
        return err("Choose student or advisor.", field="role")
    program = str(data.get("program", "SECNET")).upper()
    try:
        semester = int(data.get("semester", 3))
    except (TypeError, ValueError):
        semester = 0
    if role == "student" and program not in PROGRAMS:
        return err("Choose your concentration.", field="program")
    if role == "student" and not 1 <= semester <= 8:
        return err("Choose your current semester (1-8).", field="semester")

    try:
        cur = db().execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (name, email, generate_password_hash(password), role),
        )
        db().commit()
    except sqlite3.IntegrityError:
        return err("An account with this email already exists. Try signing in.", 409, field="email")

    if role == "student":
        students.save_profile(DB_PATH, f"u:{cur.lastrowid}", program, semester)
    start_session(uid=cur.lastrowid, remember=True)
    return jsonify({"user": current_user()}), 201


@app.post("/api/login")
def api_login():
    data = json_body()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    remember = bool(data.get("remember", False))

    now = time.time()
    recent = [t for t in _failed.get(email, []) if now - t < LOCK_SECONDS]
    _failed[email] = recent
    if len(recent) >= MAX_FAILS:
        wait = int(LOCK_SECONDS - (now - recent[0])) // 60 + 1
        return err(f"Too many attempts. Try again in about {wait} minute(s).", 429)

    row = db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if row is None or not check_password_hash(row["password_hash"], password):
        recent.append(now)
        return err("Incorrect email or password.", 401)

    _failed.pop(email, None)
    start_session(uid=row["id"], remember=remember)
    return jsonify({"user": public_user(row)})


_demo_logins: dict[str, list[float]] = {}


@app.post("/api/demo")
def api_demo():
    # Cap demo logins per visitor IP (20 per hour) — each one is a fresh demo identity.
    ip = chat.client_ip()
    now = time.time()
    recent = [t for t in _demo_logins.get(ip, []) if now - t < 3600]
    if len(recent) >= 20:
        return err("Too many demo sessions from your network. Try again later or create an account.", 429)
    _demo_logins[ip] = recent + [now]
    role = str(json_body().get("role", "")).lower()
    if role not in DEMO_USERS:
        return err("Unknown demo role.")
    start_session(demo=role)
    return jsonify({"user": current_user()})


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/me")
def api_me():
    return jsonify({"user": current_user()})


@app.get("/api/record")
def api_record():
    user = current_user()
    if not user:
        abort(401)
    if user["role"] == "advisor":
        return jsonify({"role": "advisor", "advisees": students.advisees()})
    rec = students.record_for_user(DB_PATH, user)
    summary = students.summarize(rec)
    return jsonify({"role": "student", "record": rec, "summary": summary,
                    "next": students.eligible_next(rec, summary)})


@app.get("/api/catalog")
def api_catalog():
    if not current_user():
        abort(401)
    return jsonify(catalog_for_api())


# ---------------------------------------------------------------- pages & static files
@app.get("/")
def page_home():
    return send_from_directory(ROOT, "index.html")


@app.get("/auth")
def page_auth():
    if current_user():
        return redirect("/dashboard")
    return send_from_directory(ROOT, "auth.html")


@app.get("/dashboard")
def page_dashboard():
    if not current_user():
        return redirect("/auth")
    return send_from_directory(ROOT, "dashboard.html")


@app.get("/chat")
def page_chat():
    if not current_user():
        return redirect("/auth")
    return send_from_directory(ROOT, "chat.html")


@app.get("/record")
def page_record():
    if not current_user():
        return redirect("/auth")
    return send_from_directory(ROOT, "record.html")


@app.get("/register")
def page_register():
    user = current_user()
    if not user:
        return redirect("/auth")
    return send_from_directory(ROOT, "advising.html" if user["role"] == "advisor" else "register.html")


@app.get("/alerts")
def page_alerts():
    user = current_user()
    if not user:
        return redirect("/auth")
    return send_from_directory(ROOT, "warning.html" if user["role"] == "advisor" else "alerts.html")


@app.get("/policies")
def page_policies():
    if not current_user():
        return redirect("/auth")
    return send_from_directory(ROOT, "policies.html")


@app.get("/catalog")
def page_catalog():
    if not current_user():
        return redirect("/auth")
    return send_from_directory(ROOT, "catalog.html")


# Only these files are public — server.py, chat.py, .env, data/ and .venv are never served.
PUBLIC_FILES = {"styles.css", "auth.css", "auth.js", "dashboard.js", "chat.css", "chat.js",
                "app.css", "record.js", "catalog.js", "register.js", "advising.js",
                "alerts.js", "warning.js", "policies.js"}


@app.get("/<path:filename>")
def static_files(filename: str):
    if filename in PUBLIC_FILES:
        return send_from_directory(ROOT, filename)
    if filename.startswith("assets/"):
        return send_from_directory(ROOT / "assets", filename.removeprefix("assets/"))
    abort(404)


init_db()
students.init_db(DB_PATH)
chat.register(app, db_path=DB_PATH, root=ROOT, current_user=current_user, user_key=user_key)
registration.register(app, db_path=DB_PATH, current_user=current_user, user_key=user_key,
                      record_for_user=lambda u: students.record_for_user(DB_PATH, u),
                      ai_complete=chat.complete if chat.PROVIDER else None)
insights.register(app, db_path=DB_PATH, current_user=current_user, user_key=user_key,
                  record_for_user=lambda u: students.record_for_user(DB_PATH, u))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5178))
    # Debug mode (auto-reload + error pages) only when asked for: set ZU_DEBUG=1
    app.run(host="127.0.0.1", port=port, debug=os.environ.get("ZU_DEBUG") == "1", threaded=True)
