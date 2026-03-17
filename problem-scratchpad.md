# Problem Scratchpad
*Topic: Autonomous To-Do Dashboard with Gmail/Calendar Integration | Started: 2026-03-16*

## Stage 1: Deconstruct

**Facts vs. Assumptions:**

| Item | Type | Status |
|------|------|--------|
| Tasks split into two pools: human tasks & agent tasks, switchable | Fact | Confirmed |
| Daily cron job triggers Claude to work through agent tasks by priority | Fact | Confirmed |
| Needs iPhone access (mobile-responsive web UI or PWA) | Fact | Confirmed |
| Gmail and Google Calendar integration to auto-create/update tasks | Fact | Confirmed |
| State stored in `tasks.json`, activity logged to `tasks.log` | Fact | Confirmed |
| User has Google Workspace CLI access and MCP Gmail/Calendar tools | Fact | Confirmed |
| A local web server on the Mac can be reached from iPhone | Assumption | Unverified — requires same WiFi or tunneling (ngrok/Tailscale) |
| Claude can meaningfully execute most "agent" tasks autonomously | Assumption | Unverified — depends on task types |
| Gmail/Calendar polling can reliably infer task intent from emails | Assumption | Unverified — needs classification heuristics |

**Root Cause:** The root cause is fragmented capture — thoughts, emails, and calendar obligations live in 3+ disconnected systems with 0 unified views, resulting in tasks being forgotten or discovered too late to act on (currently unmeasured, but observable via missed follow-ups and lost ideas).

**Problem Definition:** The problem is no single capture-and-execution layer across thoughts, Gmail, and Calendar, affecting Gordon personally, which means ideas evaporate and obligations slip — and it's worth solving now because the building blocks (MCP integrations, Claude autonomy, local dev) are all available today.

## Stage 2: Diverge

**Options:**

A. **Conventional — Static HTML + vanilla JS dashboard.** Single-page app served by Python HTTP server. Tasks in `tasks.json`, manual CRUD, Gmail/Calendar pulled via MCP tools in cron. Simple but limited extensibility.

B. **Unconstrained adapted — React + Tailwind PWA.** Full React app, installable on iPhone home screen. Eisenhower matrix view, drag-to-reorder, dated tasks, Gmail/Calendar auto-sync. Agent tasks processed via Claude Code cron at 3 AM using 4-stage workflow.

C. **Kanban / Eisenhower hybrid.** 4-quadrant board matching Eisenhower matrix with "Mine" / "Agent" swimlanes. Cards flow between quadrants via drag-and-drop. Borrowed from Trello/Linear.

D. **Deliberately ridiculous — Voice-activated ambient display.** Always-on Mac screen with Siri Shortcuts for capture. Surfaces the question: is typing really the fastest capture method?

E. **Inversion — No dashboard, just a capture bot.** Telegram/iMessage bot for capture, daily digest email for review. Zero UI maintenance. Loses the "single pane of glass" that's the whole point.

F. **User-added — Fork an existing GitHub repo.** Find an open-source task dashboard (React/Next.js) that's 60-70% of what's needed, then extend it with Gmail/Calendar integration, agent task pool, and Eisenhower sorting.

**Consequence Table:**

| Option | 1st-Order Effect | 2nd-Order Effect | Hidden Risk |
|--------|-----------------|-----------------|-------------|
| A — Static HTML | Ships fast, works in hours | Hard to extend, mobile layout fragile | Outgrow it in a week, rebuild from scratch |
| B — React PWA | Polished mobile UX, installable, future-proof | More build complexity upfront | Takes longer to ship v1, risk of over-engineering |
| C — Kanban hybrid | Visual priority is instant, drag-and-drop natural | Eisenhower quadrants map well to columns | Doesn't handle schedule/notifications panels from CalCentral layout |
| D — Voice capture | Fastest possible capture | Requires Siri Shortcuts + speech parsing chain | Fragile — one broken link kills the flow |
| E — No dashboard | Zero maintenance | No visual overview, no reordering | Loses the entire point of unified visibility |
| F — Fork existing repo | Head start on UI/UX, proven patterns | Must learn someone else's codebase, adapt to your stack | Repo may be unmaintained, or architecture may fight your customizations |

**User refinements:**
- Every task must have a date label
- Theme customization is lowest priority
- Explore existing GitHub repos before building from scratch

## Stage 3: Converge

**Failure Mode Table:**

| Option | How It Fails | Severity | Reversible? |
|--------|-------------|----------|-------------|
| A — Vanilla JS + Python server | `tasks.json` conflicts between browser and cron; code gets messy as features grow | Annoying | Yes — refactor or rebuild frontend, backend/data carries over |
| B — React PWA | Over-engineered for a non-developer; build tooling friction; harder to direct Claude without understanding React concepts | Painful | Yes — but wasted learning time |
| C — Kanban hybrid | Layout choice, not architecture — can apply within any option | N/A | N/A |
| D — Voice capture | Fragile multi-link chain, silent failures, debugging Siri Shortcuts is a time sink | Painful | Yes — but wasted effort |
| E — No dashboard (capture bot + md/spreadsheet) | No visual overview, no single pane of glass | Annoying | Yes — can upgrade to dashboard later |
| F — Fork existing repo | Inherit someone else's tech debt; spend more time understanding than building | Painful | Yes — abandon and restart |

**Eliminated:** D (fragile chain, no payoff), B (unnecessary complexity for non-developer), F (understanding foreign code harder than writing fresh with Claude)

**Recommendation: Option A — Vanilla JS + lightweight Python (Flask) server**

- **Why:** Lowest failure severity of all options. Features are finite and concrete (two task pools, Eisenhower sort, buttons, dates, Gmail/Calendar sync). No build tools, no framework concepts to learn. Claude writes all the code. The `tasks.json` conflict is solved by routing all reads/writes through a Flask API (~50 lines). If it eventually gets messy, the data layer and cron job carry over to any rebuild.
- **Remaining risks:**
  - iPhone access requires same WiFi or a tunnel (ngrok/Tailscale) — needs verification
  - Agent autonomous execution quality depends on task types — SOP still being developed
  - Code could get messy after many features — mitigated by asking Claude to refactor
- **Mitigations:**
  1. Build the Flask API layer from day 1 — all task operations go through endpoints, never direct file access from browser
  2. Start with manual task CRUD + Eisenhower sorting as v1. Add Gmail/Calendar integration as v2. Agent cron as v3. Incremental delivery reduces risk.

**Fallback: Option E** — If Option A proves too complex or the local server can't reach iPhone reliably, fall back to a capture bot (Telegram or similar) that writes to a markdown or spreadsheet file. No dashboard, but capture and agent execution still work. Premise: Claude does all coding.

## Stage 4: Execute

**Action Plan:**

| Element | Details |
|---------|---------|
| First Move | Build `app.py` — Flask API with 5 endpoints + filelock |
| Time to start | Now — no blockers, clean directory, Claude writes all code |
| Test Signal | Dashboard loads on iPhone on same WiFi; add/complete/move work |
| Stop Signal | iPhone can't reach local server → investigate Tailscale before continuing |
| Bottleneck Watch | Gmail/Calendar MCP auth — verify credentials before v2 |

**Steps:**
1. Build `app.py` — Flask server with GET/POST/PUT/DELETE /tasks + /tasks/<id>/move + filelock
2. Build `static/index.html` — two-column layout (My Tasks | Agent Tasks), add-task form, Eisenhower sorting
3. Run server on Mac, test in browser (add, complete, move, delete)
4. Find Mac local IP, open from iPhone — verify mobile layout
5. Build `sync_tasks.py` — Gmail + Calendar → tasks.json importer
6. Wire Sync button, test with real Gmail/Calendar data
7. Build `agent_run.py` — reads agent tasks, applies 4-stage workflow, logs, marks complete
8. Run `agent_run.py` manually to verify, then set up 3 AM cron via Claude Code

**Blocker:** None — directory is empty, Claude writes all code.

---
## Full Journey
**Problem:** No single capture-and-execution layer across thoughts, Gmail, and Calendar — ideas evaporate, obligations slip.
**Options:** A (Vanilla JS) / B (React PWA) / C (Kanban) / D (Voice) / E (Capture bot) / F (Fork repo)
**Choice:** Option A — lowest failure severity, finite feature set, no framework learning curve, Claude writes all code.
**Fallback:** Option E — capture bot writing to markdown/spreadsheet if local server can't reach iPhone.
**First Move:** Build `app.py` Flask API and `static/index.html` dashboard.
