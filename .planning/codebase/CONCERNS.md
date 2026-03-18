# Codebase Concerns

**Analysis Date:** 2026-03-18

## Tech Debt

**JSON File Parsing Without Exception Handling:**
- Issue: `json.loads()` called without try-catch block; malformed JSON will crash the application
- Files: `app.py:37`, `agent_run.py:40`
- Impact: Any corruption of `tasks.json` (incomplete writes, encoding issues) will crash the entire task system
- Fix approach: Wrap `json.loads()` in try-except, implement JSON validation on read, add recovery mechanism (backup or default empty state)

**Bare Exception Handlers:**
- Issue: Multiple `except Exception as e:` blocks with silent logging; masks actual error types and makes debugging difficult
- Files: `app.py:240`, `sync_tasks.py:73`, `sync_tasks.py:83`, `sync_tasks.py:137`, `sync_tasks.py:226`, `sync_tasks.py:237`
- Impact: Genuine failures are logged but not escalated; harder to distinguish transient vs permanent failures
- Fix approach: Catch specific exceptions (ValueError, requests.RequestException, etc.), re-raise or handle appropriately, add structured error context

**Hardcoded File Paths and Config:**
- Issue: API_BASE hardcoded to localhost:5001; CLAUDE_BIN hardcoded to user's local path; timezone assumptions
- Files: `sync_tasks.py:23`, `agent_run.py:24`
- Impact: Code is not portable; breaks immediately if port/user changes; no environment config support
- Fix approach: Move to config file or environment variables (.env); document required setup

**Incomplete Date Handling:**
- Issue: Multiple ad-hoc timezone conversions; some dates created without timezone info (`.isoformat()` without `datetime.UTC`); inconsistent handling of `completed_at` timezone awareness
- Files: `app.py:76`, `app.py:155`, `app.py:191`, `sync_tasks.py:136-137`
- Impact: Date comparisons may fail or produce incorrect results; 30-day cleanup logic vulnerable to timezone edge cases
- Fix approach: Enforce UTC for all timestamps, use explicit timezone when parsing, centralize date formatting utility

**Missing Input Validation:**
- Issue: No validation on email truncation (120 chars), calendar description (300 chars), title length limits; no validation on date format before use
- Files: `sync_tasks.py:142`, `sync_tasks.py:191`
- Impact: Malformed input could truncate meaningful data; no guarantees on data integrity
- Fix approach: Define schema with pydantic or dataclass, validate all external inputs before inserting

---

## Known Bugs

**Agent Run Fails in Claude Code Sessions:**
- Symptoms: AGENT FAILED task 022e6119-3573-49f8-9e1f-9ebce2ba4f86 — "Claude Code cannot be launched inside another Claude Code session"
- Files: `agent_run.py:100-110`
- Trigger: Running `agent_run()` from within Claude Code environment (detected via CLAUDECODE env var)
- Workaround: Code already clears CLAUDECODE from subprocess environment (line 101), but this only works if parent session context doesn't interfere; run `agent_run.py` directly from system shell, not from within Claude Code

**Recurrence Task Creation Ignores Status on No Date:**
- Symptoms: `_spawn_next_recurrence()` computes `urgency = bool(next_date)` — but if next_date is None (missing email date), task spawned with urgency=False even if original was urgent
- Files: `app.py:62`
- Trigger: Complete a recurring task that has no date field
- Impact: Lost urgency information on recurrence; incorrect quadrant classification
- Fix approach: Preserve importance/urgency from parent task, don't recompute from date alone

**Potential Duplicate Tasks from Gmail:**
- Symptoms: Same email could be synced multiple times if dedup check fails
- Files: `sync_tasks.py:115-116`
- Cause: `is_task_worthy()` check happens after dedup check; if same email is re-scanned with different label/subject, second sync may create duplicate
- Trigger: Rare - would require email labels to change or sync to run while email is being modified
- Fix approach: Move dedup check before subject/label inspection, or use more robust dedup (email message ID alone)

---

## Security Considerations

**Google API Credentials Storage:**
- Risk: `google_token.json` contains OAuth2 refresh token in plain text; if file is exposed, attacker gains calendar/email access
- Files: `sync_tasks.py:60`, `google_token.json` (present in working directory)
- Current mitigation: File is in .gitignore (check .gitignore); chmod not enforced
- Recommendations:
  1. Document that `google_token.json` must have restrictive permissions (0600)
  2. Add startup check to verify file permissions
  3. Consider encrypting token at rest (requires secure key storage)
  4. Rotate token if leaked

**Subprocess Execution Without Shell Escaping:**
- Risk: `agent_run.py` passes user-controlled task title/description to subprocess via `-p` prompt flag
- Files: `agent_run.py:104-105`
- Impact: If task title contains shell metacharacters, could break command parsing; relies on subprocess safety (not shell=True)
- Current mitigation: Using `shell=False` (default) prevents shell injection
- Recommendations: Document that titles/descriptions must be plain text; validate input in create_task endpoint

**Flask Debug Mode Not Confirmed Off:**
- Risk: `app.py:245` sets `debug=False`, but logging config uses development defaults
- Files: `app.py:245`
- Impact: Acceptable for current use case, but if Flask updated or accidentally flipped, would expose stack traces
- Recommendations: Confirm debug=False is enforced via environment config, not hardcoded

**API Endpoint Lacks Authentication:**
- Risk: All endpoints open to network; no auth check on `/tasks`, `/sync`, `/tasks/<id>`
- Files: `app.py` — all route handlers
- Impact: Any network access to 0.0.0.0:5001 can read, create, delete, modify tasks
- Current mitigation: Running on local network only (0.0.0.0 binds all interfaces, accessible from 10.9.x.x)
- Recommendations:
  1. Document that this is for local/trusted networks only
  2. Add optional auth (API key or basic auth) via environment flag
  3. Bind to 127.0.0.1 if meant for single machine only
  4. Add rate limiting to prevent spam

---

## Performance Bottlenecks

**Full Task List Loaded on Every Request:**
- Problem: `read_tasks()` loads entire JSON file every request; `get_tasks()` reads, auto-purges, then returns all tasks
- Files: `app.py:35-38`, `app.py:113-120`
- Cause: No caching, no pagination, no filtering at read time
- Current capacity: JSON file currently ~6.7KB (50+ tasks); acceptable for now
- Improvement path:
  1. Add in-memory cache with TTL (invalidate on write)
  2. Implement pagination (limit/offset) in `/tasks` endpoint
  3. Add filtering by status/pool to reduce payload
  4. Consider SQLite for >1000 tasks

**Sync Tasks Makes Multiple API Calls in Sequence:**
- Problem: `sync_gmail()` and `sync_calendar()` each call `existing_source_ids()` which fetches all tasks; then POST each new task individually
- Files: `sync_tasks.py:48-50`, `sync_tasks.py:78-85`
- Current impact: For 50 emails + 50 calendar items = 101 API calls (1 fetch + 100 POSTs)
- Improvement path:
  1. Fetch dedup set once, pass to both sync functions
  2. Batch POST operations (if API supports bulk create)
  3. Cache dedup set between runs

**Gmail Scan Limited to 50 Results:**
- Problem: `maxResults=50` on line 107; user with >50 unread action items will miss older ones
- Files: `sync_tasks.py:107`
- Impact: Tasks in older emails never synced
- Fix approach: Implement pagination loop or increase limit; add config for limit

**Calendar Cleanup Scans ±90 Days:**
- Problem: Hardcoded 90-day window; events created on day 91 won't be detected as stale
- Files: `sync_tasks.py:212`
- Impact: Old calendar tasks may remain marked as pending forever
- Fix approach: Make configurable, or use unbounded fetch + explicit ignore list

---

## Fragile Areas

**JSON Lock File Fragmentation:**
- Files: `app.py:9-16`, `agent_run.py:39-40`
- Why fragile: FileLock is used but only works on POSIX systems; on network filesystems (if scaled), could have race conditions
- Safe modification: Ensure all code paths acquire lock before read/write; document that this is not suitable for concurrent processes on different machines
- Test coverage: No unit tests for concurrent access; manual testing only

**Recurrence Task Spawning on Completion:**
- Files: `app.py:190-192`
- Why fragile: New task appended to `data["tasks"]` list in memory, then written atomically; but if spawn happens, write fails, recurrence is lost
- Safe modification: Wrap task completion + recurrence spawning in try-except, log failure separately, don't swallow errors
- Test coverage: No test for failed recurrence spawn

**Timestamp Parsing Edge Cases:**
- Files: `app.py:101-107` (completed_at parsing), `sync_tasks.py:136-137` (email date parsing)
- Why fragile: Multiple try-except blocks that silently pass on ValueError/TypeError; wrong timezone assumptions
- Safe modification: Add explicit error logging, consider default fallback (current time), validate timestamps on creation
- Test coverage: No test for malformed dates or timezone transitions

**Gmail Subject Keywords Heuristic:**
- Files: `sync_tasks.py:30-37`, `sync_tasks.py:98`
- Why fragile: Keyword list is hardcoded and incomplete; "urgent" will match "not urgent"; no ML/scoring
- Safe modification: Add negation filters (exclude "not", "no action"), allow config override, log skipped emails for audit
- Test coverage: No test for keyword matching edge cases

---

## Scaling Limits

**JSON File as Data Store:**
- Current capacity: ~6.7KB for 50+ tasks; scales poorly
- Limit: At ~1000 tasks, file size ~140KB; at 10K tasks, ~1.4MB; JSON parsing becomes measurable bottleneck; FileLock contention rises
- Scaling path: Migrate to SQLite (built-in, no external dependencies); provides better concurrency, indexing, and atomic operations

**Single-Machine Agent Processor:**
- Current capacity: One agent task runs serially on one machine; 10-minute timeout per task
- Limit: If queue > 6 tasks/hour, jobs back up; overnight agent_run processes all or fails one at a time
- Scaling path: Queue tasks to distributed worker (Celery + Redis); implement task priority; add worker pool

**Google API Rate Limits:**
- Current usage: 1 sync run = 2 list queries + N POST calls; Gmail quota ~60M operations/day, Calendar ~1M ops/day
- Limit: Multiple syncs per day could hit quotas; no backoff/retry logic
- Scaling path: Implement exponential backoff; batch operations; add request budgeting

---

## Dependencies at Risk

**google-auth-oauthlib / google-api-python-client:**
- Risk: OAuth library updates may break token refresh; Google API changes could require code updates
- Impact: Sync stops working if libraries are incompatible or API deprecated
- Migration plan: Monitor Google Cloud release notes; test library upgrades in isolated env before deploying; consider pinning versions

**filelock:**
- Risk: Small unmaintained library; if Python adds native file locking, filelock could become stale
- Impact: Concurrent access issues if locked in multi-process scenario
- Migration plan: If filelock unmaintained, migrate to fcntl (POSIX) or use SQLite instead

**Flask:**
- Risk: Flask 2.x to 3.x migration; if dev server used in production, security issues
- Impact: Code currently uses Flask development server (debug=False but still development WSGI)
- Migration plan: Use Gunicorn or uWSGI for production; document that current setup is dev-only

---

## Missing Critical Features

**No Task Validation Schema:**
- Problem: Tasks accepted with missing fields; no type validation on inputs
- Blocks: Can't guarantee data consistency; frontend could receive malformed data
- Priority: Medium — add schema validation layer (pydantic or dataclass)

**No Concurrency Control for Task Updates:**
- Problem: Two simultaneous PUT requests to same task could have race condition
- Blocks: Data corruption possible if user rapid-updates task and agent completes simultaneously
- Priority: High — implement optimistic locking (version field) or mutex per task

**No API Rate Limiting:**
- Problem: Frontend can hammer endpoints; no throttling
- Blocks: DOS vulnerability, resource exhaustion possible
- Priority: Medium — add Flask-Limiter or manual rate check

**No Audit Trail:**
- Problem: Task deletions are permanent; no way to see who/when changed task
- Blocks: Accountability missing, can't recover deleted tasks
- Priority: Low (nice-to-have) — add soft deletes or audit log table

---

## Test Coverage Gaps

**No Unit Tests for Core Logic:**
- What's not tested: `eisenhower_quadrant()` classification, `_spawn_next_recurrence()`, date parsing in sync
- Files: `app.py:25-32`, `app.py:48-81`, `sync_tasks.py:136-137`
- Risk: Logic bugs silently introduced, no regression detection
- Priority: High — add test_app.py with pytest suite covering all business logic

**No Integration Tests for Sync Flow:**
- What's not tested: Gmail/Calendar API calls, dedup logic, task creation via sync
- Files: `sync_tasks.py` (entire file)
- Risk: Sync could break without detecting it until manual test
- Priority: High — add test_sync.py with mock Google API responses

**No Concurrent Access Tests:**
- What's not tested: FileLock behavior under simultaneous requests
- Risk: Race conditions in production undetected
- Priority: Medium — add concurrency test with threading

**No Error Recovery Tests:**
- What's not tested: Malformed JSON recovery, API timeouts, partial failures
- Risk: Edge cases fail silently or crash unexpectedly
- Priority: Medium — add test cases for each exception path

---

*Concerns audit: 2026-03-18*
