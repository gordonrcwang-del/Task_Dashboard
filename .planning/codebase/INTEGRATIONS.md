# External Integrations

**Analysis Date:** 2026-03-18

## APIs & External Services

**Email & Calendar:**
- Gmail API (v1) - Read-only access to unread emails from last 7 days
  - SDK/Client: `google-api-python-client` (line 16 in `sync_tasks.py`)
  - Auth: OAuth2 via `google_credentials.json` and `google_token.json`
  - Scope: `https://www.googleapis.com/auth/gmail.readonly`

- Google Calendar API (v3) - Read-only access to upcoming events
  - SDK/Client: `google-api-python-client` (line 16 in `sync_tasks.py`)
  - Auth: OAuth2 via `google_credentials.json` and `google_token.json`
  - Scope: `https://www.googleapis.com/auth/calendar.readonly`

**Agent Task Execution:**
- Claude Code CLI - External CLI tool for running research agent tasks
  - Binary: `/Users/gordonrcwang/.local/bin/claude`
  - Invocation: `agent_run.py` lines 104-111
  - Method: Subprocess with `--dangerously-skip-permissions` and `--print` flags

## Data Storage

**Databases:**
- None (file-based storage only)

**File Storage:**
- Local filesystem only - `tasks.json` stores all task data
- Deliverables directory (`deliverables/`) - Output from agent task runs

**Caching:**
- None implemented

## Authentication & Identity

**Auth Provider:**
- Google OAuth2
  - Flow: InstalledAppFlow (browser-based authorization)
  - Initial setup: Manual authorization via browser on first run (`sync_tasks.py` lines 58-59)
  - Token refresh: Automatic via `Request().refresh()` (`sync_tasks.py` line 56)
  - Token storage: `google_token.json` (user home directory location)

## Monitoring & Observability

**Error Tracking:**
- None (errors logged locally)

**Logs:**
- `tasks.log` - Centralized log for all components (Flask, sync, cleanup)
- `agent_run.log` - Dedicated log for agent task execution
- Logging format: `"%(asctime)s %(levelname)s %(message)s"`

## CI/CD & Deployment

**Hosting:**
- Local Flask development server on `localhost:5001`
- No cloud hosting detected

**CI Pipeline:**
- None detected

**Scheduler:**
- macOS launchd via `com.gordonrcwang.agentrun.plist` (midnight or user-configured schedule)

## Environment Configuration

**Required env vars:**
- None explicitly defined in code; all configuration is file-based

**Secrets location:**
- `google_credentials.json` - OAuth2 credentials (must be placed manually)
- `google_token.json` - OAuth2 access/refresh tokens (auto-generated)
- Note: Flask app has no env var or secrets management system

## Webhooks & Callbacks

**Incoming:**
- `/sync` endpoint (`app.py` line 226) - Triggers `sync_tasks.py` via subprocess

**Outgoing:**
- None (read-only integrations with Google APIs)

## Data Flow

**Gmail Sync:**

1. User clicks "Sync" button in frontend
2. Frontend POST to `/sync` endpoint (`app.py` line 226)
3. Flask spawns subprocess running `sync_tasks.py`
4. `sync_tasks.py` authenticates via OAuth2 to Gmail API
5. Fetches unread emails from last 7 days with action keywords (`sync_tasks.py` lines 101-156)
6. For each actionable email, POST to `/tasks` endpoint with source="gmail"
7. Deduplicates by (source, source_id) tuple

**Calendar Sync:**

1. Same trigger as Gmail sync
2. `sync_tasks.py` fetches primary calendar events for next 14 days
3. For each event, POST to `/tasks` endpoint with source="calendar"
4. Cleanup: Removes dashboard tasks with source="calendar" if event no longer exists
5. Deduplicates by (source, source_id) tuple

**Agent Task Execution:**

1. User creates task with pool="agent"
2. Scheduler triggers `agent_run.py` at configured interval
3. `agent_run.py` fetches pending agent tasks from Flask API
4. For each task, runs Claude Code CLI with research prompt
5. Captures CLI output and writes to `deliverables/` directory
6. Marks task as complete when CLI succeeds

---

*Integration audit: 2026-03-18*
