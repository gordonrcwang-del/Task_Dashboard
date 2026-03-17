"""
sync_tasks.py — Gmail + Google Calendar → Task Dashboard
Run once manually to authorize, then runs automatically via cron or /sync endpoint.
"""

import json
import logging
import re
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# ── Config ────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
CREDS_FILE = BASE_DIR / "google_credentials.json"
TOKEN_FILE = BASE_DIR / "google_token.json"
LOG_FILE = BASE_DIR / "tasks.log"
API_BASE = "http://localhost:5001"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]

# Email subject keywords that signal a task worth capturing
ACTION_KEYWORDS = [
    "action required", "follow up", "follow-up", "deadline", "due date",
    "confirm", "confirmation", "review", "invitation", "invite",
    "interview", "application", "schedule", "reminder", "urgent",
    "asap", "approve", "approval", "submit", "complete", "respond",
    "response needed", "please reply", "rsvp",
]

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("sync")


# ── Auth ──────────────────────────────────────────────────────────

def get_credentials():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())

    return creds


# ── Dedup ─────────────────────────────────────────────────────────

def existing_source_ids():
    """Return set of (source, source_id) tuples already in tasks."""
    try:
        res = requests.get(f"{API_BASE}/tasks", timeout=5)
        tasks = res.json()
        return {(t.get("source"), t.get("source_id")) for t in tasks if t.get("source_id")}
    except Exception as e:
        log.warning(f"Could not fetch existing tasks for dedup: {e}")
        return set()


def post_task(task_body):
    try:
        res = requests.post(f"{API_BASE}/tasks", json=task_body, timeout=5)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        log.error(f"Failed to POST task '{task_body.get('title')}': {e}")
        return None


# ── Gmail sync ────────────────────────────────────────────────────

def is_task_worthy(subject, label_ids):
    """True if email looks like it needs action."""
    # Skip pure promotions / social
    skip_labels = {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL"}
    if skip_labels.intersection(set(label_ids)):
        return False

    subject_lower = subject.lower()
    return any(kw in subject_lower for kw in ACTION_KEYWORDS)


def sync_gmail(service, seen):
    """Fetch unread emails from last 7 days, create tasks for actionable ones."""
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y/%m/%d")
    query = f"is:unread after:{since}"

    results = service.users().messages().list(
        userId="me", q=query, maxResults=50
    ).execute()

    messages = results.get("messages", [])
    created = 0

    for msg_ref in messages:
        msg_id = msg_ref["id"]
        if ("gmail", msg_id) in seen:
            continue

        msg = service.users().messages().get(
            userId="me", id=msg_id, format="metadata",
            metadataHeaders=["Subject", "From", "Date"]
        ).execute()

        label_ids = msg.get("labelIds", [])
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        subject = headers.get("Subject", "(no subject)")
        sender = headers.get("From", "")
        date_str = headers.get("Date", "")

        if not is_task_worthy(subject, label_ids):
            continue

        # Parse date from email header for due-date awareness
        task_date = None
        try:
            from email.utils import parsedate_to_datetime
            parsed = parsedate_to_datetime(date_str)
            task_date = parsed.date().isoformat()
        except Exception:
            pass

        task = post_task({
            "title": subject[:120],
            "description": f"From: {sender}",
            "date": task_date,
            "importance": "IMPORTANT" in label_ids,
            "pool": "human",
            "source": "gmail",
            "source_id": msg_id,
        })

        if task:
            created += 1
            log.info(f"SYNC gmail task created: {subject[:60]}")

    log.info(f"SYNC gmail: {created} tasks created from {len(messages)} emails scanned")
    return created


# ── Calendar sync ─────────────────────────────────────────────────

def sync_calendar(service, seen):
    """Fetch events for next 14 days, create a task for each new one."""
    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=14)).isoformat()

    events_result = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        maxResults=50,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = events_result.get("items", [])
    created = 0

    for event in events:
        event_id = event["id"]
        if ("calendar", event_id) in seen:
            continue

        summary = event.get("summary", "(no title)")
        description = event.get("description", "")
        start = event.get("start", {})
        event_date = start.get("date") or (start.get("dateTime") or "")[:10]

        task = post_task({
            "title": summary[:120],
            "description": description[:300] if description else "",
            "date": event_date or None,
            "importance": False,
            "pool": "schedule",
            "source": "calendar",
            "source_id": event_id,
        })

        if task:
            created += 1
            log.info(f"SYNC calendar task created: {summary}")

    log.info(f"SYNC calendar: {created} tasks created from {len(events)} events scanned")
    return created


# ── Cleanup stale calendar tasks ─────────────────────────────────

def cleanup_stale_calendar_tasks(cal_svc):
    """Delete dashboard tasks whose source_id no longer exists in Google Calendar."""
    now = datetime.now(timezone.utc)
    time_min = (now - timedelta(days=90)).isoformat()
    time_max = (now + timedelta(days=90)).isoformat()

    events_result = cal_svc.events().list(
        calendarId="primary",
        timeMin=time_min, timeMax=time_max,
        maxResults=250, singleEvents=True, orderBy="startTime",
    ).execute()

    live_ids = {e["id"] for e in events_result.get("items", [])}

    try:
        res = requests.get(f"{API_BASE}/tasks", timeout=5)
        tasks = res.json()
    except Exception as e:
        log.warning(f"Could not fetch tasks for cleanup: {e}")
        return 0

    stale = [t for t in tasks if t.get("source") == "calendar" and t.get("source_id") not in live_ids]
    removed = 0
    for t in stale:
        try:
            requests.delete(f"{API_BASE}/tasks/{t['id']}", timeout=5)
            log.info(f"SYNC removed stale calendar task: {t['title']}")
            removed += 1
        except Exception as e:
            log.warning(f"Could not delete stale task {t['id']}: {e}")

    return removed


# ── Main ──────────────────────────────────────────────────────────

def run_sync():
    log.info("SYNC started")
    creds = get_credentials()

    gmail_svc = build("gmail", "v1", credentials=creds)
    cal_svc = build("calendar", "v3", credentials=creds)

    seen = existing_source_ids()

    gmail_count = sync_gmail(gmail_svc, seen)
    cal_count = sync_calendar(cal_svc, seen)
    removed_count = cleanup_stale_calendar_tasks(cal_svc)

    log.info(f"SYNC complete: {gmail_count} gmail + {cal_count} calendar tasks created, {removed_count} stale removed")
    return {"gmail": gmail_count, "calendar": cal_count, "removed": removed_count}


if __name__ == "__main__":
    result = run_sync()
    print(f"Sync complete: {result['gmail']} email tasks, {result['calendar']} calendar tasks, {result['removed']} stale removed")
