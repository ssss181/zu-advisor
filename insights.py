"""Demo versions of the next-phase tools (Challenge 19, R1 / R3 / R4).

  Policy Database   — every registration rule (ID, owner, source) + academic policies + key dates (R1)
  Smart Alerts      — a student's personal alerts: deadlines, seats, repeats, milestones (R4)
  Early Warning     — advisors see which students are at risk BEFORE registration problems (R4)
  Seat demand       — course demand from registration requests vs. section capacity (R3)

Prototype only: seat capacities and the calendar are SAMPLE values, and the cohort is simulated.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from flask import Flask, abort, jsonify, request

import registration
import rules
import students
from catalog import COURSES, ELECTIVE, POLICIES, PROGRAMS

TERM = students.NEXT_TERM
COHORT_SCALE = 4      # simulated cohort ~ 1/4 of the programme
SECTION_SIZE = 25


# ---------------------------------------------------------------- calendar (sample)
def calendar(today: date | None = None) -> list[dict]:
    """Key dates. The registration window is relative to today so the demo always shows it open."""
    t = today or date.today()
    fmt = lambda d: d.isoformat()
    return [
        {"key": "reg_open", "label": f"{TERM} registration opens", "date": fmt(t - timedelta(days=2))},
        {"key": "exc_deadline", "label": "Last day to request a registration exception", "date": fmt(t + timedelta(days=9))},
        {"key": "reg_close", "label": f"{TERM} registration closes", "date": fmt(t + timedelta(days=16))},
        {"key": "classes", "label": "Classes begin", "date": "2027-01-11"},
        {"key": "add_drop", "label": "Add / drop period ends", "date": "2027-01-15"},
        {"key": "withdraw", "label": "Last day to withdraw with a W grade", "date": "2027-03-25"},
    ]


SERVICE_STANDARDS = [
    {"tier": "green", "name": "Routine plan", "standard": "Approved instantly by the rules engine — no advisor step."},
    {"tier": "amber", "name": "Needs judgment", "standard": "Routed to the student's named advisor; decision within 48 hours."},
    {"tier": "red", "name": "Exception", "standard": "Student gives a reason; advisor decides within 48 hours. Every decision has a note."},
]


def policies_payload() -> dict:
    return {
        "rules": [{"id": k, **v} for k, v in rules.RULES.items()],
        "policies": POLICIES,
        "calendar": calendar(),
        "service": SERVICE_STANDARDS,
        "note": "Rules are versioned per catalog year (prerequisites: Catalog 2021-22; study plans: 2025) and are the same ones the registration engine runs. Dates are a sample calendar for the prototype — "
                "confirm with the Registrar.",
    }


# ---------------------------------------------------------------- seats (R3)
def _h(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest(), 16)


def seat_table(conn) -> dict[str, dict]:
    """Per course: requested seats (approved + pending) vs. sample section capacity."""
    demand: dict[str, int] = {}
    sample_demand: dict[str, int] = {}
    for r in conn.execute("SELECT courses, is_sample FROM reg_requests WHERE term = ? AND status IN ('approved','pending')",
                          (TERM,)):
        for c in json.loads(r["courses"]):
            if c == ELECTIVE:
                continue
            demand[c] = demand.get(c, 0) + 1
            if r["is_sample"]:
                sample_demand[c] = sample_demand.get(c, 0) + 1
    out = {}
    for code, n in demand.items():
        sample = sample_demand.get(code, 0)
        live = n - sample
        # The simulated cohort is a ~1-in-4 sample of the programme, so sample requests are scaled up.
        projected = round(sample * COHORT_SCALE) + live
        # Sample capacity: fixed sections of 25 per course (from the seeded demand); a few are short of seats.
        util = [0.65, 0.75, 0.8, 0.9, 1.15, 0.7, 0.85, 1.05][_h(code) % 8]
        cap = SECTION_SIZE * max(1, math.ceil(sample * COHORT_SCALE / SECTION_SIZE / util))
        status = "full" if projected >= cap else "tight" if projected >= 0.8 * cap else "open"
        out[code] = {"code": code, "title": COURSES[code]["title"], "requested": projected, "capacity": cap,
                     "sections": cap // SECTION_SIZE, "seats_left": max(cap - projected, 0), "status": status,
                     "extra_sections": math.ceil((projected - cap) / SECTION_SIZE) if projected > cap else 0,
                     "short_by": max(projected - cap, 0)}
    return out


# ---------------------------------------------------------------- risk (R4)
def _failed_outstanding(record: dict) -> list[str]:
    latest: dict[str, str] = {}
    for t in record["terms"]:
        for r in t["courses"]:
            latest[r["code"]] = r["grade"]
    current = {r["code"] for r in record["current"]["courses"]}
    return [c for c, g in latest.items() if g == "F" and c not in current and not c.startswith(ELECTIVE)]


def _plan_credits_through(program: str, semester: int) -> int:
    total = 0
    for sem in PROGRAMS[program]["plan"][:semester]:
        total += sum(3 if c == ELECTIVE else COURSES[c]["credits"] for c in sem)
    return total


def risk_profile(record: dict, summary: dict) -> dict:
    """Simple, explainable early-warning score (0-100) with reasons and a suggested action."""
    score, reasons = 0, []
    cgpa = summary["cgpa"]
    if cgpa is not None and cgpa < 2.0:
        score += 40; reasons.append(f"CGPA {cgpa} — on academic probation")
    elif cgpa is not None and cgpa < 2.26:  # ZU Academic Advising Policy
        score += 20; reasons.append(f"CGPA {cgpa} — close to probation")
    failed = _failed_outstanding(record)
    if failed:
        score += min(30, 15 * len(failed)); reasons.append("Failed, not yet repeated: " + ", ".join(failed))
    repeats = [r["code"] for r in record["current"]["courses"] if r.get("type") == "Repeat"]
    if repeats:
        score += 10; reasons.append("Repeating this term: " + ", ".join(repeats))
    expected = _plan_credits_through(record["program"], record["semester"])
    have = summary["credits_earned"] + summary["credits_in_progress"]
    behind = expected - have
    if behind >= 9:
        score += 20; reasons.append(f"{behind} credits behind the study plan — graduation may slip")
    elif behind >= 4:
        score += 10; reasons.append(f"{behind} credits behind the study plan")
    tg = [t["gpa"] for t in summary["term_gpas"] if t["gpa"] is not None]
    if len(tg) >= 2 and tg[-2] - tg[-1] >= 0.5:
        score += 15; reasons.append(f"Term GPA dropped {tg[-2]} → {tg[-1]}")
    score = min(score, 100)
    level = "high" if score >= 50 else "medium" if score >= 25 else "low"
    action = {"high": "Book a meeting before registration; plan a reduced load with repeats first.",
              "medium": "Send a check-in and review the Spring plan together.",
              "low": "No action needed."}[level]
    return {"score": score, "level": level, "reasons": reasons, "action": action, "credits_behind": max(behind, 0),
            "failed": failed}


# ---------------------------------------------------------------- student alerts
def _days_until(iso: str, today: date) -> int:
    return (date.fromisoformat(iso) - today).days


def student_alerts(record: dict, summary: dict, req: dict | None, seats: dict[str, dict]) -> list[dict]:
    today = date.today()
    cal = {c["key"]: c for c in calendar(today)}
    out: list[dict] = []

    def add(level, kind, title, text, label=None, href=None):
        out.append({"level": level, "kind": kind, "title": title, "text": text,
                    "action": {"label": label, "href": href} if label else None})

    # registration status + deadline
    left = _days_until(cal["reg_close"]["date"], today)
    status = req["status"] if req else None
    if status == "approved":
        add("ok", "registration", f"You're registered for {TERM}",
            f"{req['credits']} credits, approved by {req['decided_by']}.", "View registration", "/register")
    elif status == "pending":
        add("info", "registration", f"Your plan is with {req['advisor']}",
            "Decisions are made within 48 hours. You'll see it here and on the Registration page.", "View status", "/register")
    elif status in ("returned", "denied"):
        add("urgent", "registration", "Your advisor asked for changes",
            (req.get("decision_note") or "Adjust your plan and resubmit.") + f" Registration closes in {left} days.",
            "Fix my plan", "/register")
    else:
        add("urgent" if left <= 7 else "warn", "deadline", f"{TERM} registration closes in {left} days",
            "Your suggested plan is ready — routine plans are approved instantly.", "Register now", "/register")

    # probation / load
    if summary["cgpa"] is not None and summary["cgpa"] < 2.0:
        add("urgent", "standing", "You're on academic probation",
            f"CGPA {summary['cgpa']}. Plan 12–13 credits next term and repeat failed courses first (rule LOD-02).",
            "Ask the AI for a recovery plan",
            "/chat?q=" + "I'm on probation. Build me a 12-13 credit recovery plan for Spring 2027 with repeats first.")

    # failed courses to repeat
    for code in _failed_outstanding(record):
        add("warn", "repeat", f"Repeat {code} next term",
            f"{COURSES[code]['title']} was failed and blocks later courses. It's in your suggested plan (rule RPT-01).",
            "See the course", f"/catalog?q={code}")

    # seats for the courses in the student's plan
    plan = req["courses"] if req and status in ("approved", "pending") else rules.suggested_plan(record, summary)
    for code in plan:
        s = seats.get(code)
        if not s or (status == "approved" and code in req["courses"]):
            continue
        if s["status"] == "full":
            add("warn", "seats", f"{code} is full",
                f"{s['title']}: {s['requested']} requests for {s['capacity']} seats. Register now to join the waitlist — "
                "we'll alert you if a seat opens or a section is added.", "Go to registration", "/register")
        elif s["status"] == "tight":
            add("info", "seats", f"Only {s['seats_left']} seats left in {code}",
                f"{s['title']} is filling up. Submitting your plan holds your seat.", "Register now", "/register")

    # graduation milestones
    risk = risk_profile(record, summary)
    if risk["credits_behind"] >= 4:
        add("warn", "graduation", f"{risk['credits_behind']} credits behind your study plan",
            "You can still graduate on time with a plan — ask the AI or your advisor.",
            "Am I on track?", "/chat?q=Am I on track to graduate on time? What's left?")
    else:
        add("ok", "graduation", "On track to graduate",
            f"{summary['credits_earned']} of {summary['credits_required']} credits earned "
            f"({summary['percent_complete']}%).", "Graduation tracker", "/record#progress")
    intern = PROGRAMS[record["program"]]["internship"]
    if intern not in summary["passed"] and summary["credits_earned"] >= 75:
        add("info", "milestone", "Internship coming up",
            f"{intern} Internship is in your plan after semester 8. Start looking for a placement now.",
            "Ask about the internship", "/chat?q=What do I need to do to prepare for my internship?")
    if summary["deans_list_terms"]:
        add("ok", "milestone", "Dean's List",
            "Congratulations — " + ", ".join(summary["deans_list_terms"]) + ".")
    if status != "approved":
        add("info", "deadline", "Exception requests close " + _nice(cal["exc_deadline"]["date"]),
            "Need a course without its prerequisite or an overload? Request it before this date.", "Policies & dates", "/policies")

    order = {"urgent": 0, "warn": 1, "info": 2, "ok": 3}
    return sorted(out, key=lambda a: order[a["level"]])


def _nice(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b')}"


# ---------------------------------------------------------------- routes
def register(app: Flask, *, db_path: Path, current_user: Callable, user_key: Callable,
             record_for_user: Callable) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS outreach (
                            owner TEXT NOT NULL, student_id TEXT NOT NULL, created_at TEXT NOT NULL,
                            PRIMARY KEY (owner, student_id))""")

    def connect():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def need(role: str | None = None) -> dict:
        user = current_user()
        if not user:
            abort(401)
        if role and user["role"] != role:
            abort(403)
        return user

    @app.get("/api/policies")
    def api_policies():
        need()
        return jsonify(policies_payload())

    @app.get("/api/alerts")
    def api_alerts():
        user = need("student")
        rec = record_for_user(user)
        summ = students.summarize(rec)
        with connect() as conn:
            row = conn.execute("SELECT * FROM reg_requests WHERE owner = ? AND term = ? AND status != 'withdrawn' "
                               "ORDER BY id DESC LIMIT 1", (user_key(), TERM)).fetchone()
            seats = seat_table(conn)
        req = registration._row(row) if row else None
        plan = req["courses"] if req and req["status"] in ("approved", "pending") else rules.suggested_plan(rec, summ)
        return jsonify({"term": TERM, "alerts": student_alerts(rec, summ, req, seats),
                        "plan_seats": [seats[c] for c in plan if c in seats]})

    @app.get("/api/early-warning")
    def api_early_warning():
        need("advisor")
        with connect() as conn:
            contacted = {r["student_id"]: r["created_at"] for r in
                         conn.execute("SELECT student_id, created_at FROM outreach WHERE owner = ?", (user_key(),))}
            seats = seat_table(conn)
        cohort = registration.sample_cohort()
        rows = []
        for i, (rec, summ) in enumerate(cohort):
            rp = risk_profile(rec, summ)
            rows.append({"name": rec["name"], "student_id": rec["student_id"], "program": rec["program"],
                         "semester": rec["semester"], "cgpa": summ["cgpa"], "credits_earned": summ["credits_earned"],
                         "advisee": i < 6, "contacted": contacted.get(rec["student_id"]), **rp})
        rows.sort(key=lambda r: -r["score"])
        counts = {lvl: sum(1 for r in rows if r["level"] == lvl) for lvl in ("high", "medium", "low")}
        seat_rows = sorted(seats.values(), key=lambda s: -(s["requested"] / s["capacity"]))
        return jsonify({
            "term": TERM,
            "advisees": [r for r in rows if r["advisee"]],
            "cohort": {"total": len(rows), **counts, "contacted": sum(1 for r in rows if r["contacted"]),
                       "top": [r for r in rows if not r["advisee"] and r["level"] != "low"][:8]},
            "seats": seat_rows[:12],
            "seat_summary": {"full": sum(1 for s in seats.values() if s["status"] == "full"),
                             "tight": sum(1 for s in seats.values() if s["status"] == "tight"),
                             "extra_sections": sum(s["extra_sections"] for s in seats.values()),
                             "courses": len(seats)},
        })

    @app.post("/api/early-warning/outreach")
    def api_outreach():
        need("advisor")
        if not request.is_json:
            abort(415)
        sid = str((request.get_json(silent=True) or {}).get("student_id", ""))[:20]
        if sid not in {rec["student_id"] for rec, _ in registration.sample_cohort()}:
            abort(400)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with connect() as conn:
            conn.execute("INSERT OR REPLACE INTO outreach (owner, student_id, created_at) VALUES (?, ?, ?)",
                         (user_key(), sid, now))
        return jsonify({"ok": True, "contacted": now})
