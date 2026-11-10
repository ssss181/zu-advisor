"""Sample student records for the prototype.

Every student account gets a SAMPLE academic record generated from the real ZU 2025 study
plan for their concentration (see catalog.py): completed semesters with grades, the current
semester's registration, GPA and credits. Records are deterministic per account (seeded), so
they stay the same across visits. Advisors get a list of fictional advisees.

Nothing here is real student data.
"""
from __future__ import annotations

import json
import random
import sqlite3
from pathlib import Path

from catalog import COURSES, ELECTIVE, GRADE_POINTS, PROGRAMS

CURRENT_TERM = "Fall 2026"
NEXT_TERM = "Spring 2027"

# Grade distributions for different kinds of student
_PROFILES = {
    "strong":   (["A", "A-", "B+", "B"], [40, 30, 20, 10]),
    "steady":   (["A", "A-", "B+", "B", "B-", "C+"], [12, 18, 25, 25, 12, 8]),
    "struggling": (["B", "B-", "C+", "C", "F"], [15, 20, 25, 28, 12]),
    "at_risk":  (["B-", "C+", "C", "F"], [20, 30, 35, 15]),
}

# Fictional advisees for advisor accounts: (name, programme, current semester, profile)
_ADVISEES = [
    ("Mariam Al Hammadi", "SECNET", 5, "strong"),
    ("Fatima Al Suwaidi", "WAM", 3, "steady"),
    ("Aisha Al Mansoori", "SECNET", 7, "steady"),
    ("Noura Al Ketbi", "WAM", 6, "struggling"),
    ("Hessa Al Mazrouei", "SECNET", 4, "at_risk"),
    ("Shamma Al Nuaimi", "WAM", 8, "strong"),
]


def _term_name(offset_from_current: int) -> str:
    """Term label `offset` semesters before the current one (Fall/Spring only)."""
    year, season = 2026, "Fall"
    for _ in range(offset_from_current):
        if season == "Fall":
            season = "Spring"
        else:
            season, year = "Fall", year - 1
    return f"{season} {year}"


def _row_for(code: str, n_elective: int) -> tuple[str, dict]:
    """Plan slot -> (code, course info). Elective slots become 'ELECTIVE-<n>' (any ZU course)."""
    if code == ELECTIVE:
        return f"{ELECTIVE}-{n_elective}", {"title": "Free elective (any ZU course)", "credits": 3}
    return code, COURSES[code]


def generate_record(seed: str, name: str, program: str, semester: int, profile: str = "steady") -> dict:
    """Build a sample record for a student currently in `semester` (1-8) of `program`."""
    rng = random.Random(f"zu-{seed}")
    prog = PROGRAMS[program]
    grades, weights = _PROFILES[profile]
    n_elec = 0

    terms, failed_open = [], []
    for s in range(1, semester):
        rows = []
        for slot in prog["plan"][s - 1]:
            if slot == ELECTIVE:
                n_elec += 1
            code, c = _row_for(slot, n_elec)
            g = rng.choices(grades, weights)[0]
            rows.append({"code": code, "title": c["title"], "credits": c["credits"], "grade": g,
                         "type": "Elective" if slot == ELECTIVE else "Required"})
        terms.append({"term": _term_name(semester - s), "semester": s, "courses": rows})

    # A failed course is usually repeated in the next term and replaced in the GPA. At-risk
    # students often postpone repeats, so their Fs stay in the GPA until repeated this term.
    retake_chance = 0.25 if profile == "at_risk" else 1.0
    for i, t in enumerate(terms):
        for row in t["courses"]:
            if row["grade"] == "F":
                if i + 1 < len(terms) and rng.random() < retake_chance:
                    retake = rng.choices(["C", "C+", "B-", "B"], [30, 30, 25, 15])[0]
                    terms[i + 1]["courses"].append({**row, "grade": retake, "type": "Repeat"})
                    row["repeated"] = True
                else:
                    failed_open.append(row["code"])

    current = list(prog["plan"][semester - 1]) if semester <= len(prog["plan"]) else []
    # Load caps from ZU policy: at most 19 credits, or 13 when the CGPA is below 2.00.
    provisional = summarize({"program": program, "terms": terms, "current": {"courses": []}})
    cap = 13 if provisional["cgpa"] is not None and provisional["cgpa"] < 2.0 else 19
    current_rows = []
    for slot in failed_open + current:      # repeats first
        if slot == ELECTIVE:
            n_elec += 1
        code, c = (slot, _failed_info(terms, slot)) if slot in failed_open else _row_for(slot, n_elec)
        if sum(r["credits"] for r in current_rows) + c["credits"] > cap:
            continue
        # a lab must be taken with its lecture (co-requisite)
        coreqs = COURSES.get(code, {}).get("coreqs", [])
        if coreqs and not all(any(r["code"] == q for r in current_rows) for q in coreqs) \
                and COURSES[code]["credits"] == 1:
            continue
        current_rows.append({"code": code, "title": c["title"], "credits": c["credits"],
                             "type": "Repeat" if slot in failed_open else ("Elective" if slot == ELECTIVE else "Required")})

    first, *_ = name.split() or ["Student"]
    return {
        "sample": True,
        "name": name,
        "first_name": first,
        "student_id": f"M{rng.randint(10_000_00, 99_999_99)}",
        "program": program,
        "program_name": prog["name"],
        "semester": semester,
        "year": (semester + 1) // 2,
        "current_term": CURRENT_TERM,
        "next_term": NEXT_TERM,
        "terms": terms,
        "current": {"term": CURRENT_TERM, "courses": current_rows},
    }


def _failed_info(terms: list[dict], code: str) -> dict:
    for t in terms:
        for r in t["courses"]:
            if r["code"] == code:
                return {"title": r["title"], "credits": r["credits"]}
    return {"title": code, "credits": 3}


def summarize(record: dict) -> dict:
    """GPA, credits and progress computed from a record."""
    program = PROGRAMS[record["program"]]
    best: dict[str, dict] = {}         # latest attempt per course counts
    term_gpas = []
    for t in record["terms"]:
        pts = cr = 0.0
        for row in t["courses"]:
            pts += GRADE_POINTS[row["grade"]] * row["credits"]
            cr += row["credits"]
            best[row["code"]] = row
        term_gpas.append({"term": t["term"], "gpa": round(pts / cr, 2) if cr else None, "credits": cr})
    graded = [r for r in best.values()]
    gp = sum(GRADE_POINTS[r["grade"]] * r["credits"] for r in graded)
    att = sum(r["credits"] for r in graded)
    earned = sum(r["credits"] for r in graded if r["grade"] != "F")
    passed = {r["code"] for r in graded if r["grade"] != "F"}
    in_progress = {r["code"] for r in record["current"]["courses"]}
    cgpa = round(gp / att, 2) if att else None

    remaining = []
    for i, sem in enumerate(program["plan"], 1):
        for code in sem:
            if code != ELECTIVE and code not in passed and code not in in_progress:
                remaining.append({"code": code, "title": COURSES[code]["title"], "credits": COURSES[code]["credits"],
                                  "plan_semester": i})
    if program["internship"] not in passed:
        c = COURSES[program["internship"]]
        remaining.append({"code": c["code"], "title": c["title"], "credits": c["credits"], "plan_semester": 9})

    standing = ("Academic probation (CGPA below 2.00)" if cgpa is not None and cgpa < 2.0
                else "Good standing" if cgpa is not None else "New student")
    deans_list = [t["term"] for t in term_gpas if t["gpa"] and t["gpa"] >= 3.6 and t["credits"] >= 15]
    return {
        "cgpa": cgpa,
        "credits_earned": earned,
        "credits_in_progress": sum(r["credits"] for r in record["current"]["courses"]),
        "credits_required": program["total_credits"],
        "credits_remaining": max(program["total_credits"] - earned, 0),
        "percent_complete": round(100 * earned / program["total_credits"]),
        "standing": standing,
        "deans_list_terms": deans_list,
        "term_gpas": term_gpas,
        "passed": sorted(passed),
        "remaining": remaining,
    }


def eligible_next(record: dict, summary: dict) -> list[dict]:
    """Remaining plan courses whose prerequisites are passed or in progress this term."""
    done = set(summary["passed"]) | {r["code"] for r in record["current"]["courses"]}
    out = []
    for r in summary["remaining"]:
        missing = [p for p in COURSES[r["code"]]["prereqs"] if p not in done]
        out.append({**r, "eligible": not missing, "missing_prereqs": missing})
    return out


def record_for_ai(record: dict) -> str:
    """Compact text version of a student's record for the AI's system prompt."""
    s = summarize(record)
    lines = [
        f"SAMPLE STUDENT RECORD (fictional prototype data) — {record['name']}, ID {record['student_id']}",
        f"Programme: {record['program_name']} (120 credits). Year {record['year']}, semester {record['semester']} of 8. "
        f"Current term: {record['current_term']}; next registration: {record['next_term']}.",
        f"CGPA {s['cgpa'] if s['cgpa'] is not None else 'n/a'} · Standing: {s['standing']} · "
        f"Credits earned {s['credits_earned']}/{s['credits_required']} ({s['percent_complete']}%), "
        f"in progress {s['credits_in_progress']}.",
    ]
    if s["deans_list_terms"]:
        lines.append("Dean's List: " + ", ".join(s["deans_list_terms"]))
    lines.append("Completed courses (term: code grade):")
    for t in record["terms"]:
        lines.append(f"  {t['term']}: " + ", ".join(
            f"{r['code']} {r['grade']}{' (repeat)' if r['type'] == 'Repeat' else ''}{' (later repeated)' if r.get('repeated') else ''}"
            for r in t["courses"]))
    lines.append(f"Currently registered ({record['current_term']}): " + ", ".join(
        f"{r['code']} {r['title']} ({r['credits']} cr){' [repeat of failed course]' if r['type'] == 'Repeat' else ''}"
        for r in record["current"]["courses"]) if record["current"]["courses"] else "Currently registered: none")
    elig = eligible_next(record, s)
    lines.append("Remaining required courses (recommended plan semester; prerequisite status assuming current courses are passed):")
    for r in elig:
        status = "eligible" if r["eligible"] else "needs " + ", ".join(r["missing_prereqs"])
        lines.append(f"  {r['code']} {r['title']} ({r['credits']} cr, plan sem {r['plan_semester'] if r['plan_semester'] < 9 else 'internship'}) — {status}")
    return "\n".join(lines)


def advisees() -> list[dict]:
    out = []
    for i, (name, prog, sem, prof) in enumerate(_ADVISEES):
        rec = generate_record(f"advisee-{i}", name, prog, sem, prof)
        out.append({"record": rec, "summary": summarize(rec)})
    return out


def advisees_for_ai() -> str:
    lines = ["SAMPLE ADVISEES (fictional prototype data):"]
    for a in advisees():
        r, s = a["record"], a["summary"]
        lines.append(f"- {r['name']} ({r['student_id']}), {PROGRAMS[r['program']]['short']}, semester {r['semester']}: "
                     f"CGPA {s['cgpa']}, {s['credits_earned']}/120 credits, {s['standing']}"
                     + (f", Dean's List {', '.join(s['deans_list_terms'])}" if s["deans_list_terms"] else "")
                     + ". Current: " + ", ".join(c["code"] for c in r["current"]["courses"]))
    return "\n".join(lines)


# ---------------------------------------------------------------- storage
def init_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS student_profiles (
                   owner      TEXT PRIMARY KEY,      -- 'u:<id>' or 'demo:<role>'
                   program    TEXT NOT NULL,
                   semester   INTEGER NOT NULL,
                   created_at TEXT NOT NULL DEFAULT (datetime('now'))
               )"""
        )


def save_profile(db_path: Path, owner: str, program: str, semester: int) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT OR REPLACE INTO student_profiles (owner, program, semester) VALUES (?, ?, ?)",
                     (owner, program, semester))


def record_for_user(db_path: Path, user: dict) -> dict:
    """The student's sample record (created with defaults if missing)."""
    if user.get("demo"):
        return generate_record("demo-student", user["name"], "SECNET", 5, "steady")
    owner = f"u:{user['id']}"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT program, semester FROM student_profiles WHERE owner = ?", (owner,)).fetchone()
    program, semester = row if row else ("SECNET", 3)
    if not row:
        save_profile(db_path, owner, program, semester)
    return generate_record(owner, user["name"], program, semester, "steady")
