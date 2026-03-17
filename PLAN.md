# Task Dashboard — Build Plan
*Created: 2026-03-16*

## Context
Gordon has thoughts, emails, and calendar events scattered across 3+ systems with no unified view. Ideas flash by and are lost. The goal is a single dashboard that captures tasks from any source, sorts by Eisenhower priority, and lets Claude autonomously execute a subset of them at 3 AM daily.

---

## Architecture

```
tasks.json          ← single source of truth (all reads/writes via Flask API)
tasks.log           ← all activity logged here
app.py              ← Flask API server (port 5000)
static/index.html   ← dashboard frontend (vanilla JS)
sync_tasks.py       ← Gmail/Calendar → tasks.json importer
agent_run.py        ← 3 AM cron: reads agent tasks, executes, logs
```

**Key rule:** Browser and cron scripts NEVER read/write `tasks.json` directly. All operations go through Flask API endpoints.

---

## System Coordination Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INPUTS                              │
│   Browser/iPhone     Gmail/Calendar     3 AM Cron Trigger       │
└──────┬───────────────────┬──────────────────┬───────────────────┘
       │                   │                  │
       ▼                   ▼                  ▼
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│  index.html │    │ sync_tasks.py│    │  agent_run.py   │
│  (frontend) │    │  (importer)  │    │  (executor)     │
└──────┬──────┘    └──────┬───────┘    └────────┬────────┘
       │                  │                     │
       │   HTTP requests  │   HTTP POST         │ HTTP GET
       │   (add/edit/     │   new tasks         │ agent tasks
       │   complete/move) │                     │ HTTP PUT
       │                  │                     │ mark complete
       ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────┐
│                    app.py (Flask API)                    │
│    GET /tasks  POST /tasks  PUT /tasks  DELETE /tasks   │
└────────────────────┬────────────────────────────────────┘
                     │ read/write (exclusive filelock)
                     ▼
              ┌─────────────┐
              │  tasks.json │ ← single source of truth
              └─────────────┘

agent_run.py also writes to:
              ┌─────────────┐
              │  tasks.log  │ ← all agent activity logged
              └─────────────┘

sync_tasks.py reads from:
  ┌──────────────────┐    ┌──────────────────┐
  │  Gmail MCP tool  │    │ Calendar MCP tool │
  └──────────────────┘    └──────────────────┘
```

**Coordination rules:**
- One controller (`app.py`), three clients (`index.html`, `sync_tasks.py`, `agent_run.py`), one file (`tasks.json`)
- Everything that touches `tasks.json` goes through `app.py` — no exceptions
- `app.py` uses `filelock` to guarantee only one write at a time (no conflicts)

---

## Task Data Model

```json
{
  "id": "uuid",
  "title": "string",
  "description": "string",
  "video_url": "string|null",
  "date": "YYYY-MM-DD",
  "urgency": true,
  "importance": true,
  "pool": "human|agent",
  "status": "pending|complete",
  "source": "manual|gmail|calendar",
  "created_at": "ISO timestamp",
  "completed_at": "ISO timestamp|null",
  "eisenhower_quadrant": "Q1|Q2|Q3|Q4"
}
```

Eisenhower mapping: Q1 = urgent+important | Q2 = important only | Q3 = urgent only | Q4 = neither

---

## Phase 1 — Dashboard Foundation (v1) ← START HERE

**Goal:** Working dashboard on Mac + accessible from iPhone. Manual CRUD only.

**Steps:**
1. `tasks.json` + `tasks.log` created (empty)
2. `app.py` — Flask API: GET/POST/PUT/DELETE /tasks + /tasks/<id>/move + filelock
3. `static/index.html` — two-column layout, add-task form, Eisenhower sorting, mobile-responsive
4. Run: `pip install flask filelock` → `python app.py`
5. Test on Mac: `http://localhost:5000`
6. Test on iPhone: `http://[mac-local-ip]:5000` (same WiFi)

**Done when:** Add task on Mac → see it on iPhone → mark complete from iPhone → gone on Mac.
**Stop if:** iPhone can't reach server on same WiFi → investigate Tailscale.

---

## Phase 2 — Gmail + Calendar Sync (v2)

**Goal:** Auto-create tasks from emails and calendar events.

- Build `sync_tasks.py` — fetches Gmail + Calendar via MCP tools, POSTs to Flask API
- Wire Sync button on dashboard
- Add source badge on task cards (manual / gmail / calendar)

**Done when:** Sync button pulls ≥1 real email + ≥1 calendar event as dated tasks.

---

## Phase 3 — Agent Cron (v3)

**Goal:** Claude processes agent-pool tasks at 3 AM daily.

- Build `agent_run.py` — reads agent tasks, applies 4-stage workflow, marks complete, logs
- Set up 3 AM daily cron via Claude Code CronCreate

**Done when:** Manual run of `python agent_run.py` completes 1 agent task and writes to `tasks.log`.

---

## Fallback (Option E)
If local server can't reach iPhone: drop dashboard, use capture bot writing to `tasks.md`. Agent cron still runs from same `tasks.json`.
