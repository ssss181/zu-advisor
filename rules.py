"""Registration rules engine — risk-tiered approval (Challenge 19, root causes R1 + R2).

Every rule has an ID, a plain-language statement, a source and an accountable owner, so the
same rule set drives validation, explanations and governance (one progression framework).

A proposed registration gets a tier:
  green  — routine: every rule passes -> approved automatically, no advisor needed
  amber  — needs academic judgment (e.g. overload, probation, under-load) -> routed to a
           named advisor
  red    — blocked by a hard rule (e.g. missing prerequisite) -> the student sees how to fix
           it, or can request an exception (human recourse), which is routed to an advisor
"""
from __future__ import annotations

from catalog import COURSES, ELECTIVE, PROGRAMS, plan_semester_of

RULES = {
    "PRQ-01": {"name": "Prerequisites",
               "text": "A course's prerequisites must be passed, or in progress this term (registration is then "
                       "conditional and cancelled if the prerequisite is not passed).",
               "source": "ZU Catalog 2021-22: course descriptions; pre-registration policy",
               "owner": "Curriculum Committee (CTI)"},
    "COR-01": {"name": "Labs with lectures",
               "text": "A lab must be taken together with its lecture (co-requisite), unless the lecture is already passed.",
               "source": "ZU Catalog 2021-22: course descriptions",
               "owner": "Curriculum Committee (CTI)"},
    "DUP-01": {"name": "No repeat of passed courses",
               "text": "A course that is already passed cannot be registered again.",
               "source": "Registrar policy (prototype assumption)",
               "owner": "Registrar"},
    "PLN-01": {"name": "Study plan",
               "text": "Courses should belong to the student's programme study plan; other courses count as electives "
                       "and need advisor confirmation.",
               "source": "CTI 2025 study plans (B.Sc. IT)",
               "owner": "Program Chair, B.Sc. IT"},
    "LOD-01": {"name": "Full-time load",
               "text": "Students in good standing register 15-19 credit hours. Fewer than 15 or more than 19 needs advisor approval.",
               "source": "ZU Catalog 2021-22: Course Load",
               "owner": "Registrar"},
    "LOD-02": {"name": "Probation load",
               "text": "Students with a CGPA below 2.00 may register 12-13 credit hours, and their plan is reviewed by an advisor.",
               "source": "ZU Catalog 2021-22: Course Load / Academic Probation",
               "owner": "Academic Advising"},
    "RPT-01": {"name": "Repeat failed courses",
               "text": "Failed required courses should be repeated at the next opportunity.",
               "source": "Advising guideline (prototype assumption)",
               "owner": "Academic Advising"},
}

# Named advisors (fictional) — each case gets an accountable owner.
ADVISORS = {"SECNET": "Dr. Khalid Al Shamsi", "WAM": "Dr. Latifa Al Zaabi"}


def _check(rule: str, level: str, message: str, course: str | None = None, fix: str | None = None) -> dict:
    return {"rule": rule, "rule_name": RULES[rule]["name"], "level": level, "message": message,
            "course": course, "fix": fix}


def evaluate(record: dict, summary: dict, selected: list[str]) -> dict:
    """Check a proposed registration. Returns tier, checks and totals."""
    program = record["program"]
    plan_sems = plan_semester_of(program)
    passed = set(summary["passed"])
    in_progress = {c["code"] for c in record["current"]["courses"]}
    chosen = []
    for code in selected:
        if code not in chosen:
            chosen.append(code)
    checks: list[dict] = []

    credits = 0
    for code in chosen:
        if code == ELECTIVE:
            credits += 3
            checks.append(_check("PLN-01", "ok", "Free elective slot (3 credits) — any ZU course.", code))
            continue
        c = COURSES.get(code)
        if not c:
            checks.append(_check("PLN-01", "red", f"{code} is not a recognised course.", code, "Remove it."))
            continue
        credits += c["credits"]
        if code in passed:
            checks.append(_check("DUP-01", "red", f"{code} {c['title']} is already passed.", code, f"Remove {code}."))
            continue
        if code in in_progress:
            checks.append(_check("DUP-01", "red", f"{code} is already in your current registration.", code, f"Remove {code}."))
            continue
        if code not in plan_sems:
            checks.append(_check("PLN-01", "amber", f"{code} {c['title']} is not in your study plan — it would count as an elective.",
                                 code, "An advisor will confirm it can count as your elective."))
        missing = [p for p in c["prereqs"] if p not in passed and p not in in_progress]
        conditional = [p for p in c["prereqs"] if p in in_progress]
        if missing:
            checks.append(_check("PRQ-01", "red", f"{code} needs {', '.join(missing)} first.", code,
                                 f"Take {', '.join(missing)} before {code}, or request an exception."))
        elif conditional:
            checks.append(_check("PRQ-01", "ok", f"{code}: prerequisite {', '.join(conditional)} is in progress — "
                                 "approved on condition you pass it.", code))
        elif c["prereqs"]:
            checks.append(_check("PRQ-01", "ok", f"{code}: prerequisites {', '.join(c['prereqs'])} passed.", code))
        for q in c["coreqs"]:
            if q not in chosen and q not in passed:
                checks.append(_check("COR-01", "red", f"{code} must be taken together with {q} {COURSES[q]['title']}.",
                                     code, f"Add {q}."))

    cgpa = summary["cgpa"]
    on_probation = cgpa is not None and cgpa < 2.0
    if on_probation:
        if credits > 13:
            checks.append(_check("LOD-02", "red", f"{credits} credits is above the 13-credit limit for students on probation "
                                 f"(CGPA {cgpa}).", None, f"Remove {credits - 13}+ credits, or request an exception."))
        else:
            checks.append(_check("LOD-02", "amber", f"CGPA {cgpa} is below 2.00 — your plan is reviewed by an advisor to "
                                 "support your return to good standing.", None))
    elif credits > 19:
        checks.append(_check("LOD-01", "amber", f"{credits} credits is an overload (maximum 19).", None,
                             "An advisor decides on overloads; removing a course makes it routine."))
    elif credits < 15:
        remaining = summary["credits_remaining"] - summary["credits_in_progress"]
        nxt = record["semester"] + 1
        plan = PROGRAMS[program]["plan"]
        plan_load = (sum(3 if c == ELECTIVE else COURSES[c]["credits"] for c in plan[nxt - 1])
                     if nxt <= len(plan) else COURSES[PROGRAMS[program]["internship"]]["credits"])
        if credits >= remaining:
            checks.append(_check("LOD-01", "ok", f"{credits} credits completes your remaining requirements.", None))
        elif credits >= plan_load:
            checks.append(_check("LOD-01", "ok", f"{credits} credits matches your study plan's semester {min(nxt, 9)} load "
                                 f"({plan_load} credits).", None))
        else:
            checks.append(_check("LOD-01", "amber", f"{credits} credits is below the 15-credit full-time minimum.", None,
                                 "Add a course to make it routine, or an advisor will review the reduced load."))
    else:
        checks.append(_check("LOD-01", "ok", f"{credits} credits is within the 15-19 full-time load.", None))

    still_failed = [c["code"] for c in record["current"]["courses"] if c["type"] == "Repeat"]
    failed_open = [r["code"] for t in record["terms"] for r in t["courses"] if r["grade"] == "F" and not r.get("repeated")
                   and r["code"] not in still_failed and r["code"] not in passed]
    for code in failed_open:
        if code not in chosen:
            checks.append(_check("RPT-01", "amber", f"You have not yet repeated {code}, which you failed.", code,
                                 f"Add {code} to make this routine."))

    tier = "red" if any(c["level"] == "red" for c in checks) else "amber" if any(c["level"] == "amber" for c in checks) else "green"
    return {"tier": tier, "credits": credits, "checks": checks, "courses": chosen,
            "advisor": ADVISORS.get(program, "Academic Advising"), "on_probation": on_probation}


def suggested_plan(record: dict, summary: dict) -> list[str]:
    """A routine-friendly starting plan: unrepeated failed courses first, then the earliest
    remaining plan courses whose prerequisites are met (labs kept with lectures), up to a
    normal load (13 credits on probation, otherwise the next plan semester's load, 15-19)."""
    program = PROGRAMS[record["program"]]
    passed = set(summary["passed"])
    in_progress = {c["code"] for c in record["current"]["courses"]}
    done = passed | in_progress
    on_probation = summary["cgpa"] is not None and summary["cgpa"] < 2.0
    nxt = record["semester"] + 1
    if nxt > len(program["plan"]):
        return [program["internship"]] if program["internship"] not in done else []
    next_load = sum(3 if c == ELECTIVE else COURSES[c]["credits"] for c in program["plan"][nxt - 1])
    target = 13 if on_probation else min(max(next_load, 15), 19)

    failed = [r["code"] for t in record["terms"] for r in t["courses"]
              if r["grade"] == "F" and not r.get("repeated") and r["code"] not in done and r["code"] in COURSES]
    ordered = []
    for i, sem in enumerate(program["plan"][:nxt], 1):
        ordered += [c for c in sem if c != ELECTIVE and c not in done]
    elective_owed = sum(1 for sem in program["plan"][:nxt] for c in sem if c == ELECTIVE) - \
        sum(1 for t in record["terms"] for r in t["courses"] if r["code"].startswith(ELECTIVE)) - \
        sum(1 for c in record["current"]["courses"] if c["code"].startswith(ELECTIVE))

    out, credits = [], 0
    def add(code):
        nonlocal credits
        coreqs = COURSES[code]["coreqs"]
        if any(q in in_progress and q not in passed for q in coreqs):
            return      # its lecture/lab is in progress now; can't be split across terms
        group = [code] + [q for q in coreqs if q not in passed and q not in out]
        if any(any(p not in done for p in COURSES[g]["prereqs"]) for g in group):
            return
        cr = sum(COURSES[g]["credits"] for g in group)
        if credits + cr > target or code in out:
            return
        out.extend(g for g in group if g not in out)
        credits += cr
    for code in dict.fromkeys(failed + ordered):
        add(code)
    while elective_owed > 0 and credits + 3 <= target:
        out.append(ELECTIVE); credits += 3; elective_owed -= 1
    return out
