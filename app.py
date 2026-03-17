import json
import uuid
import logging
import subprocess
import sys
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
from filelock import FileLock

app = Flask(__name__, static_folder="static")

BASE_DIR = Path(__file__).parent
TASKS_FILE = BASE_DIR / "tasks.json"
LOG_FILE = BASE_DIR / "tasks.log"
LOCK_FILE = BASE_DIR / "tasks.lock"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def eisenhower_quadrant(urgency: bool, importance: bool) -> str:
    if urgency and importance:
        return "Q1"
    if importance and not urgency:
        return "Q2"
    if urgency and not importance:
        return "Q3"
    return "Q4"


def read_tasks():
    with FileLock(LOCK_FILE):
        data = json.loads(TASKS_FILE.read_text())
    return data


def write_tasks(data):
    with FileLock(LOCK_FILE):
        TASKS_FILE.write_text(json.dumps(data, indent=2))


RECURRENCE_DELTA = {"daily": 1, "weekly": 7, "biweekly": 14}

def _spawn_next_recurrence(task, data):
    """If task recurs, append next instance to data['tasks'] (not yet written)."""
    recurrence = task.get("recurrence")
    if not recurrence or recurrence not in RECURRENCE_DELTA:
        return

    days = RECURRENCE_DELTA[recurrence]
    next_date = None
    if task.get("date"):
        try:
            next_date = (date.fromisoformat(task["date"]) + timedelta(days=days)).isoformat()
        except ValueError:
            pass

    urgency = bool(next_date)
    importance = bool(task.get("importance"))
    next_task = {
        "id": str(uuid.uuid4()),
        "title": task["title"],
        "description": task.get("description", ""),
        "video_url": task.get("video_url"),
        "date": next_date,
        "importance": importance,
        "pool": task.get("pool", "human"),
        "status": "pending",
        "source": task.get("source", "manual"),
        "source_id": None,
        "recurrence": recurrence,
        "created_at": datetime.now(datetime.UTC).isoformat(),
        "completed_at": None,
        "eisenhower_quadrant": eisenhower_quadrant(urgency, importance),
    }
    data["tasks"].append(next_task)
    logging.info(f"RECURRENCE spawned next {recurrence} task: {next_task['title']} on {next_date}")


# ── Serve frontend ────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


# ── Task endpoints ────────────────────────────────────────────────

def _purge_old_completed(data):
    """Remove completed tasks with completed_at older than 30 days. Returns count removed."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    to_remove = []
    for t in data["tasks"]:
        if t.get("status") != "complete" or not t.get("completed_at"):
            continue
        try:
            completed = datetime.fromisoformat(t["completed_at"])
            if completed.tzinfo is None:
                completed = completed.replace(tzinfo=timezone.utc)
            if completed < cutoff:
                to_remove.append(t["id"])
        except (ValueError, TypeError):
            pass
    if to_remove:
        data["tasks"] = [t for t in data["tasks"] if t["id"] not in to_remove]
    return len(to_remove)


@app.route("/tasks", methods=["GET"])
def get_tasks():
    data = read_tasks()
    removed = _purge_old_completed(data)
    if removed:
        write_tasks(data)
        logging.info(f"AUTO-CLEANUP removed {removed} completed tasks older than 30 days")
    return jsonify(data["tasks"])


@app.route("/tasks/cleanup", methods=["POST"])
def cleanup_tasks():
    data = read_tasks()
    removed = _purge_old_completed(data)
    if removed:
        write_tasks(data)
        logging.info(f"MANUAL-CLEANUP removed {removed} completed tasks older than 30 days")
    return jsonify({"removed": removed})


@app.route("/tasks", methods=["POST"])
def create_task():
    body = request.get_json()
    if not body.get("title"):
        return jsonify({"error": "title is required"}), 400

    date = body.get("date") or None
    urgency = bool(date)                          # auto-computed from date
    importance = bool(body.get("importance", False))

    task = {
        "id": str(uuid.uuid4()),
        "title": body["title"],
        "description": body.get("description", ""),
        "video_url": body.get("video_url") or None,
        "date": date,
        "importance": importance,
        "pool": body.get("pool", "human"),
        "status": "pending",
        "source": body.get("source", "manual"),
        "source_id": body.get("source_id") or None,
        "recurrence": body.get("recurrence") or None,
        "created_at": datetime.now(datetime.UTC).isoformat(),
        "completed_at": None,
        "eisenhower_quadrant": eisenhower_quadrant(urgency, importance),
    }

    data = read_tasks()
    data["tasks"].append(task)
    write_tasks(data)

    logging.info(f"CREATED task {task['id']}: {task['title']}")
    return jsonify(task), 201


@app.route("/tasks/<task_id>", methods=["PUT"])
def update_task(task_id):
    body = request.get_json()
    data = read_tasks()

    task = next((t for t in data["tasks"] if t["id"] == task_id), None)
    if not task:
        return jsonify({"error": "task not found"}), 404

    for field in ["title", "description", "video_url", "date", "pool", "status", "completed_at"]:
        if field in body:
            task[field] = body[field] or None if field in ("date", "video_url", "completed_at") else body[field]

    if "importance" in body:
        task["importance"] = bool(body["importance"])

    # Recompute quadrant whenever date or importance may have changed
    if "date" in body or "importance" in body:
        urgency = bool(task.get("date"))
        importance = bool(task.get("importance", False))
        task["eisenhower_quadrant"] = eisenhower_quadrant(urgency, importance)

    if body.get("status") == "complete" and not task.get("completed_at"):
        task["completed_at"] = datetime.now(datetime.UTC).isoformat()
        _spawn_next_recurrence(task, data)

    write_tasks(data)
    logging.info(f"UPDATED task {task_id}: {task['title']}")
    return jsonify(task)


@app.route("/tasks/<task_id>", methods=["DELETE"])
def delete_task(task_id):
    data = read_tasks()
    original_len = len(data["tasks"])
    data["tasks"] = [t for t in data["tasks"] if t["id"] != task_id]

    if len(data["tasks"]) == original_len:
        return jsonify({"error": "task not found"}), 404

    write_tasks(data)
    logging.info(f"DELETED task {task_id}")
    return jsonify({"deleted": task_id})


@app.route("/tasks/<task_id>/move", methods=["POST"])
def move_task(task_id):
    data = read_tasks()
    task = next((t for t in data["tasks"] if t["id"] == task_id), None)
    if not task:
        return jsonify({"error": "task not found"}), 404

    task["pool"] = "agent" if task["pool"] == "human" else "human"
    write_tasks(data)
    logging.info(f"MOVED task {task_id} to pool={task['pool']}")
    return jsonify(task)


@app.route("/sync", methods=["POST"])
def sync():
    try:
        result = subprocess.run(
            [sys.executable, str(BASE_DIR / "sync_tasks.py")],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            logging.error(f"SYNC failed: {result.stderr}")
            return jsonify({"error": result.stderr}), 500
        logging.info(f"SYNC triggered via /sync endpoint: {result.stdout.strip()}")
        return jsonify({"message": result.stdout.strip()})
    except subprocess.TimeoutExpired:
        return jsonify({"error": "sync timed out after 60s"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
