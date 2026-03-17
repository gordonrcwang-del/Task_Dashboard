# agent_run.py — 4-Stage Planning
*Started: 2026-03-17*

---

## Stage 1: Deconstruct

**Facts vs. Assumptions:**

| Item | Type | Status |
|------|------|--------|
| Agent tasks currently sit in the queue indefinitely — nothing processes them | Fact | Confirmed |
| Tasks are research/learning requests routed to topic-learner skill | Fact | Confirmed (v1 scope) |
| Output goes to a deliverables folder; user sorts manually next morning | Fact | Confirmed |
| Execution is fully autonomous at 3 AM — no human in the loop | Fact | Confirmed |
| Permissions must be bypassed for unattended runs (`--dangerously-skip-permissions`) | Fact | Confirmed mechanism |
| Future task types (email drafting, scripts, scheduling) may be added later | Assumption | Unverified — out of v1 scope |
| topic-learner skill is reliable enough for overnight unattended runs | Assumption | Unverified — needs test run |
| Tasks in agent pool are well-formed enough for Claude to act on title alone | Assumption | Unverified |

**Root Cause:** Agent pool tasks are captured but never executed — there is no script that reads the queue, processes tasks, writes outputs, and marks them complete. The gap is 0 automated executions per night vs. the target of N tasks processed per night with deliverables ready by morning.

**Problem in one sentence:** `agent_run.py` does not exist, so 0 agent tasks are completed per night; the goal is a script that processes all pending agent-pool tasks autonomously, writes research outputs to `/deliverables/`, and marks each task complete via the Flask API.

---

## Stage 2: Diverge

**Options for how agent_run.py works:**

**A. Claude Code subprocess — invoke `claude` CLI per task**
- `agent_run.py` calls `subprocess.run(["claude", "--dangerously-skip-permissions", "-p", prompt])`
- Each task gets its own Claude Code session with full tool access
- topic-learner skill runs inside that session
- Output captured from stdout or written to deliverables folder directly

**B. Anthropic API directly — call claude-sonnet-4-6 via SDK**
- `agent_run.py` uses `anthropic` Python SDK, sends task title as a message
- Claude generates research notes as text, script writes to file
- No tool access (web search, NotebookLM) unless you build it in manually
- Simpler but weaker — can't use existing MCP tools or skills

**C. Hybrid — API for routing, CLI subprocess for execution**
- API call first: classify task type, generate the exact Claude Code prompt
- Then subprocess: run that prompt with full tool access
- More robust for future multi-type tasks
- More complex for v1

**Consequence Table:**

| Option | 1st-Order Effect | 2nd-Order Effect | Hidden Risk |
|--------|-----------------|-----------------|-------------|
| A — CLI subprocess | Full tool access, skills work, topic-learner runs as-is | Each task spins up a full Claude Code session (slower, more API cost) | Session isolation means no shared context between tasks; stdout capture may be unreliable |
| B — API direct | Fast, cheap, predictable | No web search, no NotebookLM, no existing skills — research quality is much lower | Defeats the purpose of topic-learner; output is shallow |
| C — Hybrid | Best of both for future extensibility | Overkill for v1; more failure points | Classification step adds latency and cost before any work is done |

**And-then-what for Option A (best option):**
- agent_run.py calls `claude --dangerously-skip-permissions -p "Run topic-learner for: {task.title}"` as subprocess
- And then what? Claude Code session runs, topic-learner gathers sources, creates NotebookLM notebook, writes markdown notes file to deliverables/
- And then what? agent_run.py detects completion, calls `PUT /tasks/{id}` to mark complete, logs result — morning review shows notes ready

---

## Stage 3: Converge

**Failure Mode Table:**

| Option | How It Fails | Severity | Reversible? |
|--------|-------------|----------|-------------|
| A — CLI subprocess | `claude` binary not on PATH in launchd environment; subprocess hangs if Claude waits for input; stdout hard to parse | Annoying | Yes — fix PATH, add timeout |
| B — API direct | Output is shallow summaries, not real research notes; defeats the purpose | Painful | Yes — switch to A |
| C — Hybrid | Classification prompt misroutes tasks; double API cost per task | Annoying | Yes — simplify back to A |

**Eliminated:** B (too weak for research tasks), C (unnecessary complexity for v1 scope)

**Recommendation: Option A — Claude Code CLI subprocess**

- Each task runs `claude --dangerously-skip-permissions --print -p "{prompt}"` in a subprocess
- `--print` flag outputs result to stdout and exits (non-interactive)
- agent_run.py captures stdout, writes to `deliverables/{task_id}_{slug}.md`
- Marks task complete via Flask API
- Logs pass/fail per task to `tasks.log`

**Key mitigations:**
1. Set `PATH` explicitly in the subprocess call to include Claude Code binary location
2. Add a per-task timeout (e.g. 5 minutes) — if it hangs, log as failed and move on
3. Create `deliverables/` folder if it doesn't exist
4. Never let one failed task block the rest — wrap each in try/except

---

## Stage 4: Execute

**Target state:** Running `python agent_run.py` manually processes all pending agent-pool tasks, writes markdown files to `deliverables/`, marks tasks complete, logs everything. Then wire to launchd for 3 AM.

**Build steps:**

| Step | Action | Done When |
|------|--------|-----------|
| 1 | Create `deliverables/` folder + add to `.gitignore` | Folder exists |
| 2 | Write `agent_run.py` — fetch pending agent tasks from `GET /tasks` | Returns task list |
| 3 | Per task: build topic-learner prompt, call `claude --print --dangerously-skip-permissions -p "..."` | Subprocess runs |
| 4 | Capture stdout, write to `deliverables/{date}_{slug}.md` | File appears |
| 5 | `PUT /tasks/{id}` to mark complete, log result | Task moves to Done section |
| 6 | Test manually: add 1 agent task, run script, verify deliverable + task marked done | End-to-end works |
| 7 | Create `launchd` plist for 3 AM daily | `launchctl load` succeeds |
| 8 | Test launchd: set time to 1 min from now, verify it fires | Auto-run confirmed |

**Stop signal:** If `claude --print` subprocess doesn't reliably exit after task completion, switch to direct Anthropic API (Option B) for the execution layer and accept shallower research quality.

**First move:** Write `agent_run.py` skeleton (fetch tasks, loop, log) — no Claude subprocess yet. Confirm Flask API connectivity. Then add the subprocess step.

---

## Resolved Decisions

1. **Claude binary path:** `/Users/gordonrcwang/.local/bin/claude` — use this explicitly in subprocess and launchd (shell function wrapper is not available in launchd environment)
2. **Failed tasks:** Stay `pending` — retry automatically next night
3. **Research prompt:** Use both title AND description for richer context
4. **Max tasks per night:** No cap for v1 — may add guard in future
