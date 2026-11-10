# ZU Advisor — AI Course Planner (prototype)

A hackathon prototype for Zayed University: a landing page, student / advisor accounts,
and an AI academic-advisor chat.

## Features
- Landing page (Dubai campus hero, features, how it works)
- Sign up / sign in (student or advisor), "keep me signed in", demo logins
- Dashboard per role
- AI advisor chat: streaming replies, saved conversations, English & Arabic
- AI provider: **Google Gemini** (free tier) or **Anthropic Claude** — whichever key is set.
  Gemini automatically falls back to a backup model if the main one is busy.

## Challenge 19 — demo script (TDRA UAE Hackathon 2026)
Problem: every registration waits for manual advisor approval. Our core: **risk-tiered approval**.
1. **Demo as Student → Register for Spring 2027.** The plan is pre-filled from the official study
   plan. Instant check: 🟢 *Routine — approved instantly* → **Register now** → registered in < 1 s,
   no advisor (root cause R2).
2. Tick **SEC432 Ethical Hacking** → 🔴 *Blocked: must be taken with SEC433* + the fix. Every check
   names its rule ID, source and owner (R1: one governed rule set).
3. Add **SEC433** → 20 credits → 🟡 *Needs your advisor's review* → **Send to Dr. Khalid Al Shamsi**
   (named case owner). A red plan can still be sent as an **exception** with a reason (human recourse).
4. **Demo as Advisor → Approvals.** KPIs: ~85% of requests approved instantly, advisor workload
   −85%, routed cases decided in hours vs. a manual baseline (assumed 72 h — replace with ZU data).
   The queue holds only judgment cases. Open one → rule checks + **Get AI recommendation** →
   Approve / Return / Deny with a note the student sees.
5. **Why cases need judgment** chart = evidence for improving rules & capacity (R5).
6. **Advisor → Early Warning** (R4 + R3): explainable risk score for every advisee and the whole
   simulated cohort (Hessa Al Mazrouei = High · 85, with reasons) → **Send check-in** / **Ask AI**.
   **Seat demand vs capacity** flags courses short of seats and how many extra sections to open,
   before the term starts.
7. **Student → Alerts**: registration deadline, seats left in their plan, repeats, graduation
   milestones. **Policies**: every rule with ID, owner and source, plus key dates and service
   standards (R1), all searchable.
Also: My Record (sample transcript, graduation tracker), Courses (49 real ZU B.Sc. IT courses),
AI Advisor chat that knows the student's record.

## Run it (Windows)
1. Install Python 3.11+.
2. In this folder:
   ```
   python -m venv .venv
   .venv\Scripts\python -m pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and add a key on the same line, e.g.
   `GEMINI_API_KEY=your-key` (free key: https://aistudio.google.com/apikey).
4. Double-click **Start ZU Advisor.bat** (or run `.venv\Scripts\python server.py`)
   and open http://localhost:5178

## Share it online (free, temporary)
Double-click **Share Online.bat**. It starts the site, creates a public
`https://….trycloudflare.com` link with Cloudflare's free quick tunnel, copies it to the
clipboard and opens it. The link works while that window stays open and the PC is on;
you get a new link each time. Needs `cloudflared.exe` (in `%USERPROFILE%\cloudflare\` or on PATH).
Anyone with the link can use the site, so each visitor is rate-limited to protect the AI quota.

## Project files
| File | What it is |
|---|---|
| `server.py` | Web server, accounts (SQLite, hashed passwords), page routes |
| `chat.py` | AI chat backend (Gemini / Claude, streaming, history) |
| `index.html`, `styles.css` | Landing page |
| `auth.*` | Sign in / sign up page |
| `dashboard.*` | Signed-in dashboard |
| `chat.*` | Chat page |
| `catalog.py`, `students.py` | Real ZU courses + sample student records |
| `rules.py`, `registration.py` | Rules engine, smart registration, advisor queue |
| `insights.py` | Alerts, early warning, seat demand, policy database |
| `alerts.*`, `warning.*`, `policies.*` | Student alerts, advisor early warning, policies pages |
| `assets/` | Campus photo |

## Notes
- Prototype: the AI is not connected to real transcripts or the official catalogue; it is
  instructed not to invent course codes or policies.
- Campus photo: Ahmed J / Wikimedia Commons, CC BY-SA 4.0.
- Free-tier Gemini chats may be used by Google to improve its products — don't enter real
  student data.
- `.env` (your key) and `data/` (accounts database) are private — never share them.
