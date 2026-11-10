"""Smart Registration + advisor exception queue (Challenge 19, R2: risk-tiered approvals).

Flow for a registration request (next term):
  green  -> approved instantly by the rules engine, with an explanation
  amber  -> routed to a named advisor (needs academic judgment)
  red    -> blocked with fixes; the student may request an exception with a reason,
            which is routed to the advisor (human recourse)
Advisors see only the routed cases, with the rule checks, the student's record and an
AI-drafted recommendation, and approve / deny / return them with a note.

The queue is pre-filled with SAMPLE requests from simulated students so the KPIs reflect a
realistic cohort. Nothing here is real student data.
"""
from __future__ import annotations

import json
import random
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from flask import Flask, abort, jsonify, request

import rules
import students
from catalog import COURSES, ELECTIVE, PROGRAMS

TERM = students.NEXT_TERM
# Illustrative baseline for the pitch: before, EVERY registration waited for manual advisor
# approval. Clearly labelled as an assumption in the UI.
BASELINE_HOURS = 72

_FIRST = ["Mariam", "Fatima", "Aisha", "Noura", "Hessa", "Shamma", "Maitha", "Alia", "Reem", "Sara", "Hind", "Amna",
          "Latifa", "Mozah", "Salama", "Wadha", "Afra", "Khawla", "Moza", "Shaikha", "Ahmed", "Mohammed", "Khalid",
          "Saeed", "Rashid", "Omar", "Hamdan", "Sultan", "Abdulla", "Yousef"]
_LAST = ["Al Hammadi", "Al Suwaidi", "Al Mansoori", "Al Ketbi", "Al Mazrouei", "Al Nuaimi", "Al Shamsi", "Al Dhaheri",
         "Al Kaabi", "Al Falasi", "Al Marri", "Al Muhairi", "Al Blooshi", "Al Ali", "Al Hosani", "Al Qubaisi"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def init_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """CREATE TABLE IF NOT EXISTS reg_requests (
                   id            INTEGER PRIMARY KEY AUTOINCREMENT,
                   owner         TEXT NOT NULL,        -- 'u:<id>', 'demo:<key>' or 'sample:<n>'
                   is_sample     INTEGER NOT NULL DEFAULT 0,
                   term          TEXT NOT NULL,
                   student       TEXT NOT NULL,        -- JSON snapshot: name, id, program, semester, cgpa...
                   courses       TEXT NOT NULL,        -- JSON list of codes
                   credits       INTEGER NOT NULL,
                   tier          TEXT NOT NULL,        -- green | amber | red
                   checks        TEXT NOT NULL,        -- JSON rule results
                   kind          TEXT NOT NULL,        -- routine | review | exception
                   status        TEXT NOT NULL,        -- approved | pending | denied | returned | withdrawn
                   advisor       TEXT,
                   student_note  TEXT,
                   decision_note TEXT,
                   decided_by    TEXT,
                   ai_recommendation TEXT,
                   created_at    TEXT NOT NULL,
                   decided_at    TEXT
               );
               CREATE INDEX IF NOT EXISTS reg_owner ON reg_requests(owner, term);
               CREATE INDEX IF NOT EXISTS reg_status ON reg_requests(status, is_sample);"""
        )


def _snapshot(record: dict, summary: dict) -> dict:
    return {"name": record["name"], "student_id": record["student_id"], "program": record["program"],
            "program_short": PROGRAMS[record["program"]]["short"], "semester": record["semester"],
            "cgpa": summary["cgpa"], "credits_earned": summary["credits_earned"], "standing": summary["standing"]}


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    for k in ("student", "courses", "checks"):
        d[k] = json.loads(d[k])
    d["course_details"] = [
        {"code": c, "title": "Free elective (any ZU course)" if c == ELECTIVE else COURSES[c]["title"],
         "credits": 3 if c == ELECTIVE else COURSES[c]["credits"]} for c in d["courses"]]
    return d


# ---------------------------------------------------------------- sample cohort
def _make_cohort(rng: random.Random, n: int) -> list[tuple[dict, dict]]:
    """The 6 named advisees + n simulated students (deterministic for a given rng seed)."""
    cohort = [(a["record"], a["summary"]) for a in students.advisees()]
    profiles = ["strong"] * 3 + ["steady"] * 5 + ["struggling"] * 2 + ["at_risk"]
    used = {rec["name"] for rec, _ in cohort}
    for i in range(n):
        name = f"{rng.choice(_FIRST)} {rng.choice(_LAST)}"
        while name in used:
            name = f"{rng.choice(_FIRST)} {rng.choice(_LAST)}"
        used.add(name)
        rec = students.generate_record(f"cohort-{i}", name, rng.choice(["SECNET", "WAM"]), rng.randint(2, 8),
                                       rng.choice(profiles))
        cohort.append((rec, students.summarize(rec)))
    return cohort


_COHORT_CACHE: list | None = None


def sample_cohort() -> list[tuple[dict, dict]]:
    """Same simulated cohort as the seeded queue (cached)."""
    global _COHORT_CACHE
    if _COHORT_CACHE is None:
        _COHORT_CACHE = _make_cohort(random.Random(2027), 140)
    return _COHORT_CACHE


def seed_samples(db_path: Path, n: int = 140, force: bool = False) -> None:
    """Fill the queue with requests from simulated students (decided + a few pending)."""
    with sqlite3.connect(db_path) as conn:
        if not force and conn.execute("SELECT 1 FROM reg_requests WHERE is_sample = 1 LIMIT 1").fetchone():
            return
        conn.execute("DELETE FROM reg_requests WHERE is_sample = 1")
        rng = random.Random(2027)
        now = _now()
        cohort = _make_cohort(rng, n)
        for i, (rec, summ) in enumerate(cohort):
            plan = rules.suggested_plan(rec, summ)
            roll = rng.random()
            exception_note = None
            if roll < 0.10:      # some ask for an overload
                extra = []
                for r in students.eligible_next(rec, summ):
                    if r["eligible"] and r["code"] not in plan and not COURSES[r["code"]]["coreqs"] and r["credits"] == 3:
                        extra.append(r["code"])
                plan = plan + extra[:2]
            elif roll < 0.17:    # some want a course without its prerequisite -> exception request
                remaining = [r["code"] for r in summ["remaining"] if COURSES[r["code"]]["prereqs"]
                             and r["code"] not in plan and not COURSES[r["code"]]["coreqs"]]
                if remaining:
                    plan = plan + [rng.choice(remaining)]
                    exception_note = rng.choice([
                        "I am graduating next year and this course is only offered in Spring.",
                        "I completed equivalent material in a summer program and can provide the certificate.",
                        "My sponsor requires me to complete this course this year.",
                    ])
            ev = rules.evaluate(rec, summ, plan)
            if ev["tier"] == "red" and not exception_note:
                continue
            created = now - timedelta(hours=rng.uniform(2, 96))
            snap = _snapshot(rec, summ)
            if ev["tier"] == "green":
                kind, status, decided_by = "routine", "approved", "Rules engine"
                decided = created + timedelta(seconds=rng.uniform(0.2, 1.5))
                note = "All rules passed — approved automatically."
            else:
                kind = "exception" if ev["tier"] == "red" else "review"
                pending = rng.random() < 0.45 or i < 6       # named advisees stay pending for the demo
                status = "pending" if pending else rng.choice(["approved", "approved", "approved", "denied", "returned"])
                decided_by = None if pending else ev["advisor"]
                decided = None if pending else created + timedelta(hours=rng.uniform(3, 30))
                note = None if pending else {"approved": "Reviewed with the student — approved.",
                                             "denied": "Not approved this term; see the suggested alternative.",
                                             "returned": "Please adjust your plan as discussed and resubmit."}[status]
            conn.execute(
                """INSERT INTO reg_requests (owner, is_sample, term, student, courses, credits, tier, checks, kind,
                       status, advisor, student_note, decision_note, decided_by, created_at, decided_at)
                   VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (f"sample:{i}", TERM, json.dumps(snap), json.dumps(ev["courses"]), ev["credits"], ev["tier"],
                 json.dumps(ev["checks"]), kind, status, ev["advisor"], exception_note, note, decided_by,
                 _iso(created), _iso(decided) if decided else None))


# ---------------------------------------------------------------- KPIs
def kpis(conn) -> dict:
    rows = conn.execute("SELECT kind, status, created_at, decided_at, decided_by FROM reg_requests "
                        "WHERE term = ? AND status != 'withdrawn'", (TERM,)).fetchall()
    total = len(rows)
    auto = sum(1 for r in rows if r["kind"] == "routine")
    routed = total - auto
    pending = sum(1 for r in rows if r["status"] == "pending")
    waits = []
    for r in rows:
        if r["decided_at"]:
            a = datetime.strptime(r["created_at"], "%Y-%m-%dT%H:%M:%SZ")
            b = datetime.strptime(r["decided_at"], "%Y-%m-%dT%H:%M:%SZ")
            waits.append((b - a).total_seconds() / 3600)
    avg_wait = sum(waits) / len(waits) if waits else 0
    routed_waits = [w for w, r in zip(waits, [r for r in rows if r["decided_at"]]) if r["kind"] != "routine"]
    routed_avg = sum(routed_waits) / len(routed_waits) if routed_waits else 0
    reduction = (1 - avg_wait / BASELINE_HOURS) * 100 if total else 0
    return {"total": total, "auto_approved": auto, "routed": routed, "pending": pending,
            "auto_rate": round(100 * auto / total) if total else 0,
            "avg_wait_hours": round(avg_wait, 1), "routed_avg_wait_hours": round(routed_avg, 1),
            "baseline_hours": BASELINE_HOURS,
            "delay_reduction": round(reduction), "workload_reduction": round(100 * auto / total) if total else 0}


# ---------------------------------------------------------------- routes
def register(app: Flask, *, db_path: Path, current_user: Callable, user_key: Callable,
             record_for_user: Callable, ai_complete: Callable[[str, str], str] | None) -> None:
    init_db(db_path)
    seed_samples(db_path)

    def connect():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def need(role: str) -> dict:
        user = current_user()
        if not user:
            abort(401)
        if user["role"] != role:
            abort(403)
        return user

    def body() -> dict:
        if not request.is_json:
            abort(415)
        return request.get_json(silent=True) or {}

    def clean_courses(raw) -> list[str]:
        if not isinstance(raw, list):
            abort(400)
        out = []
        for c in raw[:20]:
            c = str(c).strip().upper()
            if c == ELECTIVE or c in COURSES:
                out.append(c)
        return out

    # ---------------- student
    @app.get("/api/registration")
    def reg_get():
        user = need("student")
        rec = record_for_user(user)
        summ = students.summarize(rec)
        with connect() as conn:
            row = conn.execute("SELECT * FROM reg_requests WHERE owner = ? AND term = ? AND status != 'withdrawn' "
                               "ORDER BY id DESC LIMIT 1", (user_key(), TERM)).fetchone()
        options = []
        for r in students.eligible_next(rec, summ):
            options.append({**r, "coreqs": COURSES[r["code"]]["coreqs"]})
        return jsonify({"term": TERM, "suggested": rules.suggested_plan(rec, summ), "options": options,
                        "record": {"name": rec["name"], "program_name": rec["program_name"], "semester": rec["semester"],
                                   "cgpa": summ["cgpa"], "standing": summ["standing"]},
                        "request": _row(row) if row else None,
                        "rules": rules.RULES})

    @app.post("/api/registration/check")
    def reg_check():
        user = need("student")
        rec = record_for_user(user)
        return jsonify(rules.evaluate(rec, students.summarize(rec), clean_courses(body().get("courses"))))

    @app.post("/api/registration/submit")
    def reg_submit():
        user = need("student")
        data = body()
        courses = clean_courses(data.get("courses"))
        if not courses:
            return jsonify({"error": "Choose at least one course."}), 400
        note = str(data.get("note", "")).strip()[:1000]
        rec = record_for_user(user)
        summ = students.summarize(rec)
        ev = rules.evaluate(rec, summ, courses)
        if ev["tier"] == "red" and len(note) < 15:
            return jsonify({"error": "This plan breaks a rule. Fix it, or request an exception with a reason "
                                     "(at least 15 characters).", "evaluation": ev}), 400
        now = _iso(_now())
        kind = {"green": "routine", "amber": "review", "red": "exception"}[ev["tier"]]
        with connect() as conn:
            conn.execute("UPDATE reg_requests SET status = 'withdrawn' WHERE owner = ? AND term = ? "
                         "AND status IN ('pending', 'returned', 'denied', 'approved')", (user_key(), TERM))
            approved = ev["tier"] == "green"
            cur = conn.execute(
                """INSERT INTO reg_requests (owner, term, student, courses, credits, tier, checks, kind, status, advisor,
                       student_note, decision_note, decided_by, created_at, decided_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_key(), TERM, json.dumps(_snapshot(rec, summ)), json.dumps(ev["courses"]), ev["credits"], ev["tier"],
                 json.dumps(ev["checks"]), kind, "approved" if approved else "pending", ev["advisor"], note or None,
                 "All rules passed — approved automatically." if approved else None,
                 "Rules engine" if approved else None, now, now if approved else None))
            row = conn.execute("SELECT * FROM reg_requests WHERE id = ?", (cur.lastrowid,)).fetchone()
        return jsonify({"request": _row(row)}), 201

    @app.post("/api/registration/withdraw")
    def reg_withdraw():
        need("student")
        with connect() as conn:
            conn.execute("UPDATE reg_requests SET status = 'withdrawn' WHERE owner = ? AND term = ? AND status = 'pending'",
                         (user_key(), TERM))
        return jsonify({"ok": True})

    # ---------------- advisor
    @app.get("/api/advising/queue")
    def adv_queue():
        need("advisor")
        with connect() as conn:
            pending = conn.execute("SELECT * FROM reg_requests WHERE term = ? AND status = 'pending' "
                                   "ORDER BY is_sample ASC, CASE tier WHEN 'red' THEN 0 ELSE 1 END, created_at ASC",
                                   (TERM,)).fetchall()
            decided = conn.execute("SELECT * FROM reg_requests WHERE term = ? AND status IN ('approved','denied','returned') "
                                   "AND kind != 'routine' ORDER BY decided_at DESC LIMIT 15", (TERM,)).fetchall()
            k = kpis(conn)
            reasons = {}
            for r in conn.execute("SELECT checks FROM reg_requests WHERE term = ? AND kind != 'routine' AND status != 'withdrawn'",
                                  (TERM,)):
                for c in json.loads(r["checks"]):
                    if c["level"] != "ok":
                        reasons[c["rule"]] = reasons.get(c["rule"], 0) + 1
        top = sorted(({"rule": r, "name": rules.RULES[r]["name"], "count": n} for r, n in reasons.items()),
                     key=lambda x: -x["count"])
        return jsonify({"term": TERM, "pending": [_row(r) for r in pending], "decided": [_row(r) for r in decided],
                        "kpis": k, "top_reasons": top, "rules": rules.RULES})

    @app.post("/api/advising/<int:req_id>/decide")
    def adv_decide(req_id: int):
        user = need("advisor")
        data = body()
        decision = str(data.get("decision", ""))
        if decision not in ("approve", "deny", "return"):
            abort(400)
        note = str(data.get("note", "")).strip()[:1000]
        if decision != "approve" and len(note) < 5:
            return jsonify({"error": "Add a short note so the student knows why and what to do next."}), 400
        status = {"approve": "approved", "deny": "denied", "return": "returned"}[decision]
        with connect() as conn:
            row = conn.execute("SELECT * FROM reg_requests WHERE id = ? AND status = 'pending'", (req_id,)).fetchone()
            if not row:
                abort(404)
            conn.execute("UPDATE reg_requests SET status = ?, decision_note = ?, decided_by = ?, decided_at = ? WHERE id = ?",
                         (status, note or "Approved by your advisor.", user["name"], _iso(_now()), req_id))
            row = conn.execute("SELECT * FROM reg_requests WHERE id = ?", (req_id,)).fetchone()
        return jsonify({"request": _row(row)})

    _ai_calls: dict[str, list[float]] = {}

    @app.post("/api/advising/<int:req_id>/ai")
    def adv_ai(req_id: int):
        user = need("advisor")
        if ai_complete is None:
            return jsonify({"error": "The AI isn't connected (no API key in .env)."}), 503
        now = time.time()
        calls = [t for t in _ai_calls.get(user["email"], []) if now - t < 600]
        if len(calls) >= 20:
            return jsonify({"error": "Too many AI requests — wait a few minutes."}), 429
        _ai_calls[user["email"]] = calls + [now]
        with connect() as conn:
            row = conn.execute("SELECT * FROM reg_requests WHERE id = ?", (req_id,)).fetchone()
            if not row:
                abort(404)
            if row["ai_recommendation"]:
                return jsonify({"recommendation": row["ai_recommendation"]})
        r = _row(row)
        s = r["student"]
        issues = "\n".join(f"- [{c['level'].upper()}] {c['rule']} {c['rule_name']}: {c['message']}"
                           for c in r["checks"] if c["level"] != "ok") or "- none"
        courses = ", ".join(f"{c['code']} {c['title']} ({c['credits']})" for c in r["course_details"])
        prompt = (
            f"Registration request for {TERM} (prototype, sample data).\n"
            f"Student: {s['name']} ({s['student_id']}), {s['program_short']}, semester {s['semester']}, "
            f"CGPA {s['cgpa']}, {s['credits_earned']}/120 credits, {s['standing']}.\n"
            f"Requested ({r['credits']} credits): {courses}\n"
            f"Request type: {r['kind']}. Student's reason: {r['student_note'] or '(none)'}\n"
            f"Rule checks that need judgment:\n{issues}\n\n"
            "Write a recommendation for the advisor in at most 90 words: start with one of APPROVE, APPROVE WITH "
            "CHANGES, or DENY in bold, then the reasoning tied to the rules, and if relevant a concrete adjusted plan "
            "using only the course codes above or ones named in the checks. No preamble.")
        system = ("You are an academic-advising assistant at Zayed University helping a faculty advisor decide "
                  "registration exceptions. Be concise, fair and policy-grounded. Policies: full-time load 15-19 credits; "
                  "CGPA below 2.00 = probation, 12-13 credits; labs are taken with their lectures; prerequisites must be "
                  "passed or in progress. The advisor makes the final decision.")
        try:
            text = ai_complete(system, prompt).strip()
        except Exception as exc:  # noqa: BLE001
            app.logger.warning("advising AI error: %r", exc)
            return jsonify({"error": "The AI is busy right now — try again in a moment."}), 503
        with connect() as conn:
            conn.execute("UPDATE reg_requests SET ai_recommendation = ? WHERE id = ?", (text, req_id))
        return jsonify({"recommendation": text})

    @app.post("/api/advising/reset-demo")
    def adv_reset():
        need("advisor")
        seed_samples(db_path, force=True)
        return jsonify({"ok": True})
