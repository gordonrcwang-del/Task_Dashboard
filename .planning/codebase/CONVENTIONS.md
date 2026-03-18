# Coding Conventions

**Analysis Date:** 2026-03-18

## Naming Patterns

**Files:**
- Lowercase with underscores: `app.py`, `sync_tasks.py`, `agent_run.py`
- Module names describe their primary function

**Functions:**
- snake_case: `read_tasks()`, `write_tasks()`, `eisenhower_quadrant()`, `sync_gmail()`
- Private/helper functions prefixed with underscore: `_spawn_next_recurrence()`, `_purge_old_completed()`
- Action-verb naming: `get_*`, `create_*`, `update_*`, `delete_*`, `post_*`, `sync_*`, `run_*`, `fetch_*`, `mark_*`, `build_*`

**Variables:**
- snake_case throughout: `base_dir`, `tasks_file`, `log_file`, `msg_id`, `email_id`, `created_at`, `completed_at`
- Constants in UPPER_SNAKE_CASE: `BASE_DIR`, `TASKS_FILE`, `LOG_FILE`, `LOCK_FILE`, `RECURRENCE_DELTA`, `ACTION_KEYWORDS`, `SCOPES`, `SYSTEM_CONSTRAINTS`
- Boolean prefixes for clarity: `urgency`, `importance`, `is_task_worthy()`, `creds` (for credentials)

**Types:**
- Type hints present in newer code (`agent_run.py`): `-> dict`, `-> list`, `-> str`, `-> bool`
- Older code (`app.py`, `sync_tasks.py`) lacks type hints

## Code Style

**Formatting:**
- No enforced formatter detected (no black, ruff, or prettier config)
- 4-space indentation (Python standard)
- Import organization: stdlib first, then third-party

**Linting:**
- No linter config detected (no .flake8, pylintrc, or pyproject.toml)
- No pre-commit hooks configured

**Spacing & Structure:**
- Blank lines between function definitions
- Section separators: `# ── Section Name ──────────────────────────────────` (dashes with en-dash)
- Descriptive variable naming within functions, minimal abbreviation except `t` for task items in list comprehensions

## Import Organization

**Order:**
1. Python stdlib: `json`, `logging`, `subprocess`, `sys`, `uuid`, `os`, `re`
2. Datetime modules: `from datetime import datetime, date, timedelta, timezone`
3. Path handling: `from pathlib import Path`
4. Third-party frameworks: `from flask import ...`, `from google.oauth2.credentials import ...`
5. Third-party utilities: `from filelock import FileLock`, `from googleapiclient.discovery import build`
6. Late imports: `from email.utils import parsedate_to_datetime` (imported within function when needed)

**Path Aliases:**
- No path aliases used. All imports are absolute or relative to installed packages.

## Error Handling

**Patterns:**

1. **Specific Exception Types:** Prefer catching specific exceptions where possible
   - `except ValueError:` for parsing errors
   - `except subprocess.TimeoutExpired:` for subprocess timeouts
   - `except (ValueError, TypeError):` for multiple related errors

2. **Generic Fallback:** Broad `except Exception as e:` used for I/O and network operations where multiple failure modes exist
   - HTTP requests in `sync_tasks.py`
   - File I/O operations
   - Subprocess execution in `agent_run.py`

3. **Silent Failures:** Pass silently for non-critical operations
   ```python
   except ValueError:
       pass  # in _spawn_next_recurrence (line 59)
   except Exception:
       pass  # in sync_gmail date parsing (line 138)
   ```

4. **Logging on Error:** Always log errors with context before returning fallback
   ```python
   except Exception as e:
       log.error(f"Failed to POST task '{task_body.get('title')}': {e}")
   ```

5. **Error Returns:** Return `None` or falsy value on error, let caller decide handling
   - `post_task()` returns `None` on failure
   - `run_task()` returns `bool` (False on failure)

## Logging

**Framework:** Python's built-in `logging` module

**Initialization Pattern:**
```python
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
```

**Module Logger:** `sync_tasks.py` creates a named logger:
```python
log = logging.getLogger("sync")
log.info(...)
```

**Log Levels Used:**
- `logging.INFO`: Normal operations, status updates, completion
- `logging.ERROR`: Failures, exceptions, sync/agent errors

**Logging Patterns:**

1. **Operational Status:** Log major operations with context tags
   - `"CREATED task {id}: {title}"`
   - `"UPDATED task {id}: {title}"`
   - `"SYNC started"`, `"SYNC complete: ..."`
   - `"AGENT START task {id}: {title}"`

2. **Decision Events:** Log when automatic processing triggers
   - `"AUTO-CLEANUP removed {count} completed tasks older than 30 days"`
   - `"RECURRENCE spawned next {type} task: {title} on {date}"`

3. **Error Context:** Log with truncated data if needed
   - `"AGENT FAILED task {id}: {title} — {stderr[:500]}"`

4. **Summary Lines:** Use `===` delimiters for session starts/ends
   - `"=== AGENT RUN START ==="`
   - `"=== AGENT RUN DONE — {passed} completed, {failed} failed, {elapsed}s ==="`

## Comments

**When to Comment:**
- Architectural sections: Use separator lines with dashes to organize code into functional areas
- Non-obvious logic: Explain why, not what (e.g., line 140 in app.py: "auto-computed from date")
- Constraints and requirements: Document mandatory system constraints (`SYSTEM_CONSTRAINTS` in `agent_run.py`)
- Config/constant definitions: Explain the purpose of major constants

**JSDoc/TSDoc:**
- Not used. Single-line docstrings only for public functions
- Format: Triple-quoted strings directly after function def
  ```python
  def _purge_old_completed(data):
      """Remove completed tasks with completed_at older than 30 days. Returns count removed."""
  ```

**Docstring Style:**
- Imperative tone: "Return set of...", "Fetch unread emails...", "Delete dashboard tasks..."
- Include return description in the docstring
- No parameter documentation

## Function Design

**Size:**
- Small, focused functions: 3-40 lines
- Flask route handlers: ~30 lines (get_tasks, create_task, update_task)
- Helper functions: 5-20 lines (read_tasks, write_tasks, eisenhower_quadrant)
- Multi-step operations: Group into separate functions (sync_gmail, sync_calendar are ~55 lines each)

**Parameters:**
- Minimal parameters, max 2-3 positional args
- When many fields needed, pass objects/dicts: `post_task(task_body)`, `run_task(task)`
- Type hints in newer code: `task_id: str`, `text: str -> str`, `task: dict -> bool`

**Return Values:**
- Consistent return types per function: either `None` or specific type
- Falsy return on error: `None` from `post_task()`, `False` from `run_task()`
- Logging outside return: errors logged in the function, caller checks return value

## Module Design

**Exports:**
- All functions at module level (no classes)
- Private functions prefixed with `_`: `_spawn_next_recurrence()`, `_purge_old_completed()`
- Flask routes decorated with `@app.route()` serve as public endpoints

**Barrel Files:**
- Not used. Single-purpose modules: `app.py` (API), `sync_tasks.py` (Gmail/Calendar), `agent_run.py` (task runner)

**Module Purposes:**
- `app.py`: Flask API with task CRUD operations, automatic cleanup, recurrence spawning
- `sync_tasks.py`: Gmail and Google Calendar integration, deduplication, stale task cleanup
- `agent_run.py`: Agent task execution via Claude CLI, deliverable tracking

## Data Structure Patterns

**Task Objects:**
- Represented as dicts with fixed schema throughout codebase
- Keys: `id`, `title`, `description`, `video_url`, `date`, `importance`, `pool`, `status`, `source`, `source_id`, `recurrence`, `created_at`, `completed_at`, `eisenhower_quadrant`
- Consistent field access: `task.get("field", default)` for optional fields

**File Locking:**
- All file I/O wrapped in `FileLock` context manager: `with FileLock(LOCK_FILE): ...`
- Applied to both read and write operations to prevent race conditions

---

*Convention analysis: 2026-03-18*
