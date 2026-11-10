"""Zayed University course data used by the prototype.

Sources (official zu.ac.ae documents, read November 2026):
  * Courses, titles, credits and recommended semesters: College of Technological Innovation,
    "2025 Catalog" eight-semester study plans for the B.Sc. in Information Technology —
    SECNET2025.pdf (Security and Network Technologies) and WAM2025.pdf (Web and Mobile
    Application Development).
  * Prerequisites / co-requisites: "Zayed University Catalog 2021-2022" course descriptions.
    Only prerequisites that are courses in this list are kept; prerequisites that refer to
    courses no longer in the 2025 plans (e.g. ENG240, CIT300) are dropped, not guessed.
    They may have changed since 2021-22 — the app tells users to confirm.
  * Policies: Zayed University Catalog 2021-2022.
"""
from __future__ import annotations

CATALOG_SOURCE = ("ZU College of Technological Innovation 2025 study plans (B.Sc. Information "
                  "Technology); prerequisites from the ZU Catalog 2021-2022")

# code: (title, credits, prerequisites, co-requisites, area)
_C = {
    # General education / first-year experience (2025 plan, semesters 1-2)
    "FYE100": ("Academic Foundations and Development", 3, [], [], "General Education"),
    "FYE105": ("Workplace Readiness and Professional Skills", 3, [], [], "General Education"),
    "FYE110": ("Reasoning with Data", 3, [], [], "General Education"),
    "FYE120": ("Islamic Studies", 3, [], [], "General Education"),
    "FYE125": ("UAE Studies", 3, [], [], "General Education"),
    "FYE140": ("Critical Analysis and Composition", 3, [], [], "General Education"),
    "FYE145": ("Arabic Concepts (Native Speakers)", 3, [], [], "General Education"),
    "FYE146": ("Arabic Concepts (Non-Native Speakers)", 3, [], [], "General Education"),
    "FYE150": ("Fundamentals of Innovation and Entrepreneurship", 3, [], [], "General Education"),
    "FYE155": ("Digital Humanities", 3, [], [], "General Education"),
    "FYE195": ("Artificial Intelligence Essentials and Applications", 3, [], [], "General Education"),
    "ARA345": ("Advanced Arabic Skills", 3, [], [], "General Education"),
    # Mathematics
    "MTH215": ("Computing Foundations", 3, [], [], "Mathematics"),
    "MTH281": ("Probability and Statistics", 3, [], [], "Mathematics"),
    # IT core
    "CIT210": ("Essentials of IT and Infrastructure", 3, [], [], "IT Core"),
    "CIT285": ("Technical Communication", 3, [], [], "IT Core"),
    "CIT305": ("IT in Global and Local Cultures", 3, [], [], "IT Core"),
    "CIT315": ("Operating Systems", 3, ["SWE225"], [], "IT Core"),
    "CIT365": ("Database Systems", 3, ["CIT210"], [], "IT Core"),
    "CIT466": ("Data Analytics", 3, ["CIT365"], [], "IT Core"),
    "CIT480": ("IT Entrepreneurship", 3, [], [], "IT Core"),
    "CIT491": ("Internship", 6, [], [], "IT Core"),
    "CIT497": ("Senior Project Seminar", 1, [], [], "IT Core"),
    "CIT498": ("Senior Project", 3, [], [], "IT Core"),
    "INS377": ("IT Project Management", 3, ["CIT210"], [], "IT Core"),
    "SWE225": ("Introduction to Programming and Problem Solving", 3, ["MTH215"], [], "IT Core"),
    "SWE245": ("Web Development", 3, ["SWE225"], [], "IT Core"),
    "SWE320": ("Object Oriented Programming", 3, ["SWE225"], ["SWE321"], "IT Core"),
    "SWE321": ("Object Oriented Programming Lab", 1, [], ["SWE320"], "IT Core"),
    "SWE324": ("Software Requirements and Design", 3, [], [], "IT Core"),
    "NET256": ("Computer Network Foundations", 3, ["CIT210"], ["NET257"], "IT Core"),
    "NET257": ("Computer Network Foundations Lab", 1, [], ["NET256"], "IT Core"),
    "SEC235": ("Information Security Foundations", 3, [], [], "IT Core"),
    # Security and Network Technologies concentration
    "NET351": ("Computer Network Technologies", 3, ["NET256", "NET257"], ["NET352"], "Security & Networks"),
    "NET352": ("Computer Network Technologies Lab", 1, [], ["NET351"], "Security & Networks"),
    "NET455": ("Cyber Physical Systems and IoT", 3, ["NET351"], [], "Security & Networks"),
    "SEC335": ("Information Security Technologies", 3, ["SEC235", "NET256"], ["SEC336"], "Security & Networks"),
    "SEC336": ("Information Security Technologies Lab", 1, [], ["SEC335"], "Security & Networks"),
    "SEC430": ("Information Security Management", 3, ["SEC235"], [], "Security & Networks"),
    "SEC432": ("Ethical Hacking", 3, ["NET256", "SEC335"], ["SEC433"], "Security & Networks"),
    "SEC433": ("Ethical Hacking Lab", 1, [], ["SEC432"], "Security & Networks"),
    "SEC435": ("Digital Forensics Foundations", 3, ["SEC335", "CIT315"], [], "Security & Networks"),
    # Web and Mobile Application Development concentration
    "CIT372": ("Cloud Computing", 3, ["CIT210"], [], "Web & Mobile"),
    "CIT470": ("Applied Database Systems", 3, ["CIT365"], [], "Web & Mobile"),
    "IMT340": ("Computer Graphics", 3, ["SWE225"], [], "Web & Mobile"),
    "IMT375": ("Human Computer Interaction", 3, [], [], "Web & Mobile"),
    "IMT376": ("Game Development", 3, ["SWE225", "IMT375"], [], "Web & Mobile"),
    "SWE346": ("Dynamic Web Development", 3, ["SWE245", "SWE320", "CIT365"], [], "Web & Mobile"),
    "SWE371": ("Mobile Computing", 3, ["SWE225"], [], "Web & Mobile"),
}

COURSES = {
    code: {"code": code, "title": t, "credits": cr, "prereqs": pre, "coreqs": co, "area": area}
    for code, (t, cr, pre, co, area) in _C.items()
}

ELECTIVE = "ELECTIVE"   # a free elective slot in a study plan (3 credits)

_FIRST_YEAR = [
    ["FYE100", "FYE140", "FYE110", "FYE150", "FYE120"],
    ["FYE105", "FYE155", "FYE195", "FYE145", "FYE125"],   # FYE145 or FYE146
]

PROGRAMS = {
    "SECNET": {
        "code": "SECNET",
        "name": "B.Sc. Information Technology — Security and Network Technologies",
        "short": "IT · Security & Networks",
        "total_credits": 120,
        "plan": _FIRST_YEAR + [
            ["CIT210", "MTH215", "CIT285", "SEC235", "ARA345"],
            ["SWE225", "NET256", "NET257", "CIT365", "MTH281", ELECTIVE],
            ["SEC335", "SEC336", "CIT315", "SWE320", "SWE321", "SWE245"],
            ["NET351", "NET352", "CIT305", "SWE324", "CIT466", "INS377"],
            ["SEC432", "SEC433", "SEC435", "CIT480", "NET455", "CIT497"],
            ["SEC430", ELECTIVE, "CIT498"],
        ],
        "internship": "CIT491",
    },
    "WAM": {
        "code": "WAM",
        "name": "B.Sc. Information Technology — Web and Mobile Application Development",
        "short": "IT · Web & Mobile",
        "total_credits": 120,
        "plan": _FIRST_YEAR + [
            ["CIT210", "MTH215", "CIT285", "SEC235", "ARA345"],
            ["SWE225", "CIT365", "NET256", "NET257", "MTH281", ELECTIVE],
            ["SWE320", "SWE321", "SWE245", "IMT375", "IMT340", "CIT315"],
            ["CIT305", "SWE324", "CIT372", "SWE346", "SWE371"],
            ["CIT466", "CIT480", "IMT376", "INS377", ELECTIVE, "CIT497"],
            ["CIT470", "CIT498"],
        ],
        "internship": "CIT491",
    },
}

# Grades counted in the GPA (ZU Catalog 2021-2022 grade table).
GRADE_POINTS = {"A": 4.0, "A-": 3.7, "B+": 3.3, "B": 3.0, "B-": 2.7, "C+": 2.3, "C": 2.0, "F": 0.0}

POLICIES = [
    "Full-time load for a student in good standing: minimum 15, maximum 19 credit hours per semester.",
    "Academic probation: cumulative GPA below 2.00. At-risk students (CGPA below 2.0) may register "
    "12-13 credit hours per semester.",
    "Dean's List: at least 15 gradable credit hours in a semester with a term GPA of 3.60 or above.",
    "Graduation honors: graduating CGPA of 3.60 or above.",
    "Pre-registration: a student may pre-register for a course whose prerequisite is still in progress; "
    "if the prerequisite is not passed, that registration is cancelled.",
    "Grade scale: A 4.00, A- 3.70, B+ 3.30, B 3.00, B- 2.70, C+ 2.30, C 2.00, F 0.",
]


def course(code: str) -> dict:
    if code == ELECTIVE:
        return {"code": ELECTIVE, "title": "Free elective", "credits": 3, "prereqs": [], "coreqs": [], "area": "Elective"}
    return COURSES[code]


def plan_semester_of(program: str) -> dict[str, int]:
    """course code -> recommended semester (1-8) in the programme's study plan."""
    out = {}
    for i, sem in enumerate(PROGRAMS[program]["plan"], 1):
        for c in sem:
            if c != ELECTIVE:
                out.setdefault(c, i)
    out[PROGRAMS[program]["internship"]] = 9
    return out


def catalog_for_api() -> dict:
    sems = {p: plan_semester_of(p) for p in PROGRAMS}
    courses = []
    for c in COURSES.values():
        courses.append({**c, "programs": {p: sems[p].get(c["code"]) for p in PROGRAMS if c["code"] in sems[p]}})
    return {
        "source": CATALOG_SOURCE,
        "programs": {k: {"name": v["name"], "short": v["short"], "total_credits": v["total_credits"]} for k, v in PROGRAMS.items()},
        "courses": courses,
        "policies": POLICIES,
    }
