# Architecture

**Analysis Date:** 2026-03-18

## Pattern Overview

**Overall:** Three-tier event-driven system with task queueing and external synchronization

**Key Characteristics:**
- **Synchronous REST API** serving frontend with CRUD operations on a centralized task store
- **Asynchronous agent processing** via scheduled CLI invocations (agent_run.py runs overnight via cron)
- **External source integration** polling Gmail and Google Calendar, writing tasks back to the dashboard
- **File-based persistence** with locking to avoid concurrent write conflicts
- **Pool-based task routing** separating human-managed and AI-agent-executed work

## Layers

**API Layer (REST):**
- Purpose: Expose task operations to frontend and external integrators
- Location: `app.py` (routes starting at line 84)
- Contains: Flask route handlers for CRUD, sync triggering, task cleanup
- Depends on: File I/O layer (read_tasks/write_tasks), domain logic
- Used by: Frontend (static/index.html), sync_tasks.py, agent_run.py

**File I/O Layer (Locking & Persistence):**
- Purpose: Manage concurrent access to tasks.json without data corruption
- Location: `app.py` lines 35-43 (shared pattern), also in `agent_run.py` lines 38-45, `sync_tasks.py` lines 49-75
- Contains: read_tasks(), write_tasks() wrappers with FileLock
- Depends on: filelock library, filesystem
- Used by: All layers (API, sync, agent)

**Domain Logic Layer:**
- Purpose: Compute derived fields, enforce business rules
- Location: `app.py` lines 25-81 (eisenhower_quadrant, recurrence spawning, cleanup)
- Contains: Quadrant calculation, recurrence scheduling, task purging logic
- Depends on: Task schema
- Used by: API layer, frontend (via calculated fields)

**Frontend (Single-Page App):**
- Purpose: Interactive task management UI with real-time rendering
- Location: `static/index.html` (lines 431-669: JavaScript)
- Contains: State management (allTasks array), rendering functions, API client, user interactions
- Depends on: Flask REST API at `/tasks`
- Used by: Browser/user

**Sync Integration Layer:**
- Purpose: Pull data from Gmail/Google Calendar, transform into tasks
- Location: `sync_tasks.py` (lines 101-204)
- Contains: Gmail message fetching, Calendar event fetching, deduplication, cleanup of stale tasks
- Depends on: Google APIs, file I/O layer, REST API for posting
- Used by: `/sync` endpoint, external cron scheduler

**Agent Execution Layer:**
- Purpose: Process pending agent-pool tasks via Claude Code CLI
- Location: `agent_run.py` (lines 90-138)
- Contains: Task batching, subprocess invocation, deliverables file tracking, completion marking
- Depends on: Claude CLI binary, file I/O layer, task state
- Used by: Scheduled cron job (com.gordonrcwang.agentrun.plist), manual invocation

## Data Flow

**Task Creation (Manual):**

1. User fills form in frontend
2. POST /tasks (app.py line 133)
3. Validate title, compute Eisenhower quadrant, assign UUID
4. Lock, read tasks.json, append, write back
5. Return created task, re-render UI

**Task Completion & Recurrence:**

1. User clicks "✓ Done" (frontend line 552)
2. PUT /tasks/{id} with status=complete (app.py line 168)
3. Server locks, updates task.status, sets completed_at timestamp
4. If task has recurrence: _spawn_next_recurrence() (line 48) appends next instance to data["tasks"]
5. Write all changes atomically
6. Frontend re-renders showing next occurrence

**External Sync (Gmail/Calendar):**

1. User clicks "⟳ Sync" button or cron triggers /sync endpoint (app.py line 226)
2. Server runs sync_tasks.py as subprocess
3. sync_tasks fetches credentials, queries Gmail for unread emails (last 7 days)
4. For each email with action keywords: create task via POST /tasks
5. Queries Calendar for events (next 14 days)
6. For each event: POST task with source=calendar, pool=schedule
7. Cleans up stale calendar tasks (events deleted from Google Calendar)
8. Returns counts, logs to tasks.log

**Agent Task Execution (Overnight):**

1. Cron invokes agent_run.py (via com.gordonrcwang.agentrun.plist)
2. agent_run fetches all tasks with pool=agent and status=pending
3. For each task:
   - Builds prompt from title + description + system constraints
   - Invokes Claude CLI with --dangerously-skip-permissions
   - Waits up to 600s (TASK_TIMEOUT)
   - Captures new files in /deliverables or stdout fallback
4. On success: marks task status=complete, sets completed_at
5. Logs all activity to agent_run.log
6. Completed tasks visible in Done section on next load

**State Management:**

- **Single source of truth:** tasks.json (JSON array)
- **Transient frontend state:** allTasks array in memory (re-fetched on every mutation)
- **Concurrency control:** FileLock on read/write ensures no lost updates
- **Derived fields:** Eisenhower quadrant computed on write, never stored with assumptions

## Key Abstractions

**Task Object:**
- Purpose: Represent a unit of work with metadata
- Fields: id, title, description, date, importance, pool (human/agent/schedule), status, source (manual/gmail/calendar), source_id, recurrence, created_at, completed_at, eisenhower_quadrant, video_url
- Persistence: Stored as dict in tasks.json array, serialized on each write
- Schema enforcement: Minimal — only title required; nulls/defaults handled by POST handler

**Eisenhower Quadrant:**
- Purpose: Classify task by urgency × importance
- Mapping: (urgent=date exists, important=importance flag) → Q1/Q2/Q3/Q4
- Computation: app.py lines 25-32, called on task create (line 157), update (line 188), and recurrence spawn (line 78)
- Use: Frontend sorts and groups tasks by quadrant

**Pool:**
- Purpose: Route tasks to execution context
- Values: human (user), agent (Claude CLI), schedule (calendar-derived)
- Routing logic:
  - human: displayed in My Tasks column, user can manually complete
  - agent: hidden from main columns, fetched by agent_run.py overnight
  - schedule: displayed in Schedule column, not executable directly, pulled from Google Calendar

**Recurrence:**
- Purpose: Generate follow-up tasks after completion
- Values: daily, weekly, biweekly
- Mechanism: On task complete (app.py line 190), _spawn_next_recurrence (line 48) appends next instance
- Date shift: days_delta = {daily: 1, weekly: 7, biweekly: 14}
- No rescheduling on skipped dates (static rule)

## Entry Points

**Web Server (Flask):**
- Location: `app.py` main block (line 244)
- Invokes: app.run(host="0.0.0.0", port=5001)
- Responsibilities: Serve static/index.html, handle all /tasks* endpoints, trigger sync

**Frontend:**
- Location: `static/index.html` onload (line 668)
- Invokes: loadTasks() → render()
- Responsibilities: Poll /tasks, render columns, handle user actions

**Sync Process:**
- Location: Via Flask endpoint `/sync` (app.py line 226) or direct script execution
- Invokes: subprocess.run([sys.executable, "sync_tasks.py"]) with 60s timeout
- Responsibilities: Fetch Gmail/Calendar, deduplicate, POST new tasks

**Agent Runner:**
- Location: `agent_run.py` main() (line 142)
- Invokes: Via cron (com.gordonrcwang.agentrun.plist) or manual python agent_run.py
- Responsibilities: Fetch agent pool tasks, run Claude CLI on each, mark complete

## Error Handling

**Strategy:** Fail-safe per component; errors logged but don't block other operations

**Patterns:**

- **API errors:** Return JSON error + HTTP status (400 for bad request, 404 for not found, 500 for server error) — see app.py lines 137, 175, 206
- **Sync errors:** Log warning/error, skip individual task, continue batch (sync_tasks.py lines 73-75, 84)
- **Agent execution:** On timeout (line 133) or exception (line 136), log and mark task as failed (stays pending for retry)
- **Recurrence parsing:** Try/except on date math (app.py lines 57-60), silently skip if invalid
- **Cleanup:** try/except around ISO date parsing (app.py lines 100-107), skip malformed timestamps
- **Lock contention:** No explicit handling — FileLock will wait, potential bottleneck under high concurrency

## Cross-Cutting Concerns

**Logging:**
- Tool: Python logging module
- Config: app.py line 18, basicConfig to tasks.log
- Pattern: Structured "LEVEL context message" format (app.py line 21)
- Used by: All modules (app, sync_tasks, agent_run)
- Examples: "CREATED task {id}: {title}" (line 164), "SYNC gmail: N tasks created" (sync_tasks.py line 155)

**Validation:**
- Frontend: HTML5 required attribute on title field (static/index.html line 378)
- Backend: title length check (app.py line 136), JSON type coercion on update (line 182)
- No schema validation library; validation is inline per endpoint

**Authentication:**
- Frontend: None — no user isolation
- Google APIs: OAuth2 flow via google_credentials.json + refresh via google_token.json (sync_tasks.py lines 49-62)
- Claude CLI: Requires ~/.local/bin/claude authenticated globally (agent_run.py line 24)
- No task-level access control; all users see all tasks
