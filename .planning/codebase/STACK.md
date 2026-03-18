# Technology Stack

**Analysis Date:** 2026-03-18

## Languages

**Primary:**
- Python 3 - Backend API, task sync, and agent task runner

**Secondary:**
- HTML5 - Frontend markup
- CSS3 - Frontend styling
- JavaScript (vanilla) - Frontend interactions and API calls

## Runtime

**Environment:**
- Python 3 (version not pinned in requirements)

**Package Manager:**
- pip (Python package manager)

## Frameworks

**Core:**
- Flask 2.x - REST API framework serving `/tasks` endpoints and static frontend (`app.py`)

**Authentication:**
- google-auth-oauthlib - OAuth2 flow for Google authentication
- google-auth (via googleapiclient) - Token refresh and credential management

**API Clients:**
- google-api-python-client - Gmail v1 and Calendar v3 API clients

**Utilities:**
- filelock - File-level locking for concurrent JSON writes (`tasks.json`, `tasks.lock`)

## Key Dependencies

**Critical:**
- Flask - Web framework serving dashboard and task API
- google-auth-oauthlib - Handles OAuth2 flow to Google APIs (requires manual initial authorization via browser)
- google-api-python-client - Provides Gmail and Calendar service objects

**Infrastructure:**
- filelock - Prevents simultaneous writes to `tasks.json` from Flask API, sync_tasks.py, and agent_run.py

**Note:** No requirements.txt file detected in repository. Dependencies are assumed to be installed via pip without version pinning.

## Configuration

**Environment:**
- Google OAuth2 credentials stored in `google_credentials.json` (service account JSON file)
- Google OAuth2 token stored in `google_token.json` (auto-generated on first auth)
- API base URL hardcoded as `http://localhost:5001` in `sync_tasks.py` line 23
- Claude Code CLI path hardcoded as `/Users/gordonrcwang/.local/bin/claude` in `agent_run.py` line 24

**Build:**
- No build step; Python scripts run directly
- Flask development server runs on `0.0.0.0:5001` (`app.py` line 245)

## Platform Requirements

**Development:**
- Python 3
- pip or equivalent package manager
- macOS (plist scheduler: `com.gordonrcwang.agentrun.plist`)
- Google account with Gmail and Calendar access
- Claude Code CLI installed and authorized

**Production:**
- Python 3 runtime
- Network access to Google APIs
- Network access to local Flask API on port 5001 (frontend communication)
- File system write access for JSON data storage and logs

## Data Storage

**Primary:**
- JSON file (`tasks.json`) - Single source of truth for all tasks
- Lock file (`tasks.lock`) - Prevents concurrent modifications

**Logging:**
- `tasks.log` - Application logs from Flask, sync, and agent runner
- `agent_run.log` - Dedicated agent task execution logs

## Scheduler

**Task Execution:**
- macOS launchd via `com.gordonrcwang.agentrun.plist`
- Runs `agent_run.py` at scheduled intervals (overnight agent task processor)

---

*Stack analysis: 2026-03-18*
