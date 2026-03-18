# Testing Patterns

**Analysis Date:** 2026-03-18

## Test Framework Status

**No automated testing framework detected.**

- No `pytest.ini`, `setup.cfg`, `tox.ini`, or `conftest.py` files
- No test runner dependencies in codebase
- No `*.test.py` or `*.spec.py` files found
- No CI/CD pipeline configuration

**Testing approach:** Manual and integration testing via Flask endpoints and subprocess invocation.

## Integration Testing via API

**Manual Testing:**
The application relies on manual HTTP testing of Flask endpoints in `app.py`:

1. **GET /tasks** — Retrieve all tasks
2. **POST /tasks** — Create a new task
3. **PUT /tasks/<task_id>** — Update a task
4. **DELETE /tasks/<task_id>** — Delete a task
5. **POST /tasks/<task_id>/move** — Toggle task pool
6. **POST /tasks/cleanup** — Manually trigger old task cleanup
7. **POST /sync** — Manually trigger Gmail/Calendar sync

**Testing Approach:**
- Flask app runs locally: `python app.py` (line 245: `app.run(host="0.0.0.0", port=5001, debug=False)`)
- Manual curl/Postman requests or browser testing via static frontend
- No test file exists for endpoint validation

## Error Handling Testing

**Implicit Error Cases:**

1. **Missing Task:**
   - Endpoint: `PUT /tasks/<task_id>`, `DELETE /tasks/<task_id>`, `POST /tasks/<task_id>/move`
   - Check: `if not task:` returns `404` with error message
   - Files: `app.py` lines 174, 206, 218

2. **Missing Required Field:**
   - Endpoint: `POST /tasks` (title required)
   - Check: `if not body.get("title"):` returns `400`
   - File: `app.py` line 136

3. **Subprocess Timeout:**
   - Endpoint: `POST /sync`
   - Check: `subprocess.TimeoutExpired` caught, returns `504` after 60s
   - File: `app.py` lines 238-239

4. **Subprocess Failure:**
   - Endpoint: `POST /sync`
   - Check: `result.returncode != 0` returns `500` with stderr
   - File: `app.py` lines 233-235

5. **Network/API Failures:**
   - Pattern: Try/except with logging and fallback return value
   - Files: `sync_tasks.py` lines 69-75 (dedup), 79-85 (post_task), 223-228 (cleanup)

6. **Date Parsing Failures:**
   - Pattern: Silent pass on `ValueError` or `TypeError`
   - Files: `app.py` lines 59, 100-107; `sync_tasks.py` lines 134-139

## Logging-Based Validation

**Primary Test Method:**

The codebase uses logging as the validation mechanism. Check log files to verify behavior:

**Log File:** `tasks.log` in project root

**Log Format:**
```
%(asctime)s %(levelname)s %(message)s
Example: 2026-03-18 14:33:22,123 INFO CREATED task abc-123: Task Title
```

**Key Logged Events to Validate:**

1. **Task Creation:**
   - `CREATED task {id}: {title}`
   - File: `app.py` line 164

2. **Task Updates:**
   - `UPDATED task {id}: {title}`
   - File: `app.py` line 195

3. **Task Deletion:**
   - `DELETED task {id}`
   - File: `app.py` line 209

4. **Automatic Cleanup:**
   - `AUTO-CLEANUP removed {count} completed tasks older than 30 days`
   - File: `app.py` line 119

5. **Manual Cleanup:**
   - `MANUAL-CLEANUP removed {count} completed tasks older than 30 days`
   - File: `app.py` line 129

6. **Recurrence Spawning:**
   - `RECURRENCE spawned next {recurrence} task: {title} on {date}`
   - File: `app.py` line 81

7. **Sync Operations:**
   - `SYNC started`
   - `SYNC gmail: {created} tasks created from {len(messages)} emails scanned`
   - `SYNC calendar: {created} tasks created from {len(events)} events scanned`
   - `SYNC removed stale calendar task: {title}`
   - `SYNC complete: {gmail_count} gmail + {cal_count} calendar tasks created, {removed_count} stale removed`
   - Files: `sync_tasks.py` lines 246, 155, 203, 235, 258

8. **Agent Task Execution:**
   - `AGENT START task {id}: {title}`
   - `AGENT COMPLETE task {id}: {title}`
   - `AGENT FAILED task {id}: {title} — {error}`
   - `AGENT TIMEOUT task {id}: {title} — exceeded {TASK_TIMEOUT}s`
   - `AGENT ERROR task {id}: {title} — {exception}`
   - `AGENT wrote: {filenames}`
   - `AGENT wrote fallback output to {filename}`
   - Files: `agent_run.py` lines 95, 129, 114, 133, 136, 121, 127

9. **Sync Errors:**
   - `SYNC failed: {stderr}`
   - File: `app.py` line 234

## Subprocess Testing

**Agent Task Execution:**

Testing `agent_run.py` involves subprocess invocation:

1. **Task Execution:** `subprocess.run()` calls Claude CLI with prompt
2. **Timeout Testing:** 600-second timeout configured at `TASK_TIMEOUT`
3. **Output Capture:** Both stdout and stderr captured, with stderr limit (500 chars)
4. **Deliverable Detection:** Snapshots deliverables dir before/after to detect new files
5. **Fallback Output:** If skill doesn't create file, stdout written as `{date}_{slug}.md`

**Files:** `agent_run.py` lines 98-127

**Manual Test Process:**
```bash
python agent_run.py          # Run all pending agent tasks
tail -f tasks.log            # Monitor execution
ls deliverables/             # Check output files
```

## Data Persistence Testing

**File Operations:**

All data persistence uses the following pattern from `app.py` and mirrored in `agent_run.py`:

```python
def read_tasks():
    with FileLock(LOCK_FILE):
        return json.loads(TASKS_FILE.read_text())

def write_tasks(data):
    with FileLock(LOCK_FILE):
        TASKS_FILE.write_text(json.dumps(data, indent=2))
```

**Manual Validation:**
- Check `tasks.json` exists and contains valid JSON
- Verify `tasks.lock` prevents concurrent writes
- Confirm `tasks.log` records all operations

## Edge Cases Not Covered by Testing

**Identified Gaps:**

1. **Concurrent Writes:** File locking prevents race conditions, but no test verifies this works
2. **Invalid JSON Recovery:** No handling if `tasks.json` is corrupted
3. **Large File Handling:** No tests for thousands of tasks
4. **Email Date Parsing:** Silent failure on unparseable dates, no fallback logic
5. **Google API Rate Limits:** No handling for quota exceeded errors
6. **Eisenhower Quadrant Computation:** No test matrix for all 4 quadrants
7. **Recurrence Edge Cases:** No test for tasks without dates or invalid recurrence values
8. **Task ID Collisions:** UUID collision is extremely unlikely, not tested

## Recommended Testing Additions

**Unit Tests (if framework is added):**
- `test_eisenhower_quadrant()` — 4 quadrant combinations
- `test_read_write_tasks()` — File I/O and locking
- `test_post_task_validation()` — Required field checks

**Integration Tests:**
- Test all 7 endpoint paths with valid and invalid inputs
- Test sync with mock Gmail/Calendar services
- Test agent execution with mock Claude CLI

**Manual Test Checklist:**
- [ ] Create task, verify in tasks.json
- [ ] Update task date, verify Eisenhower quadrant updates
- [ ] Mark task complete, verify recurrence spawns (if recurring)
- [ ] Wait 30 days, cleanup should remove completed task
- [ ] Run sync, verify new email/calendar tasks appear
- [ ] Run agent_run.py, verify deliverables written

---

*Testing analysis: 2026-03-18*
