"""
Epic Games Store Status Monitor
Fetches status directly from status.epicgames.com (Atlassian Statuspage).
Monitors only the 'Epic Games Store' component group.
Detects transitions and sends Telegram notifications.
Shares state.json with check_status.py.

No API key required.

Usage:
    python scripts/check_epic.py
"""

import os
import sys
import json
import http.client
from datetime import datetime, timezone, timedelta
import calendar

EPIC_HOST       = "status.epicgames.com"
EPIC_PATH       = "/api/v2/summary.json"
TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT   = os.environ.get("TELEGRAM_CHAT_ID", "")
STATE_FILE      = "state.json"
HISTORY_FILE    = "history.ndjson"
SERVICE_KEY     = "epic_store"
SERVICE_NAME    = "Epic Games Store"

# Group name to match in the components list
TARGET_GROUP    = "epic games store"

STATUS_EMOJI = {
    "operational":            "✅",
    "degraded_performance":   "⚠️",
    "partial_outage":         "⚠️",
    "major_outage":           "🔴",
    "under_maintenance":      "🔧",
    "unknown":                "❓",
}

# Map Atlassian status values → our simplified labels
STATUS_MAP = {
    "operational":          "up",
    "degraded_performance": "warn",
    "partial_outage":       "warn",
    "major_outage":         "down",
    "under_maintenance":    "maintenance",
}

PROBLEM_STATUSES = {"warn", "down", "maintenance"}

# Worst-status priority order
STATUS_PRIORITY = ["major_outage", "partial_outage", "degraded_performance",
                   "under_maintenance", "operational"]


def local_timestamp() -> tuple[str, str]:
    """Return (formatted_timestamp, tz_label) in CET or CEST."""
    now_utc = datetime.now(timezone.utc)
    year = now_utc.year

    def last_sunday(y, month):
        last_day = calendar.monthrange(y, month)[1]
        d = datetime(y, month, last_day)
        return d - timedelta(days=d.weekday() + 1) if d.weekday() != 6 else d

    cest_start = last_sunday(year, 3).replace(hour=1, tzinfo=timezone.utc)
    cest_end   = last_sunday(year, 10).replace(hour=1, tzinfo=timezone.utc)

    if cest_start <= now_utc < cest_end:
        offset, label = timedelta(hours=2), "CEST"
    else:
        offset, label = timedelta(hours=1), "CET"

    ts = (now_utc + offset).strftime("%Y-%m-%d %H:%M:%S")
    return f"{ts} {label}", label


def fetch_epic_summary() -> dict:
    """Fetch Atlassian summary.json from Epic status page."""
    conn = http.client.HTTPSConnection(EPIC_HOST, timeout=15)
    conn.request("GET", EPIC_PATH, headers={"Accept": "application/json"})
    resp = conn.getresponse()
    raw  = resp.read().decode()
    conn.close()
    if resp.status != 200:
        print(f"❌  Epic API HTTP {resp.status}")
        sys.exit(1)
    return json.loads(raw)


def worst_status(statuses: list) -> str:
    """Return the most severe status from a list of Atlassian status strings."""
    for s in STATUS_PRIORITY:
        if s in statuses:
            return s
    return "operational"


def send_telegram(message: str):
    """Send a message to Telegram."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("⚠️  Telegram not configured — skipping")
        return False
    payload = json.dumps({
        "chat_id":    TELEGRAM_CHAT,
        "text":       message,
        "parse_mode": "HTML",
    }).encode()
    conn = http.client.HTTPSConnection("api.telegram.org", timeout=15)
    conn.request("POST", f"/bot{TELEGRAM_TOKEN}/sendMessage",
                 body=payload,
                 headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    raw  = resp.read().decode()
    conn.close()
    if resp.status == 200:
        return True
    print(f"⚠️  Telegram error HTTP {resp.status}: {raw[:200]}")
    return False


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
    print(f"💾  State saved → {STATE_FILE}")


def append_history(entry: dict):
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"📜  History updated → {HISTORY_FILE}")


def build_message(old_status: str, new_status: str, ts: str) -> str:
    emoji     = STATUS_EMOJI.get(new_status, "❓")
    old_emoji = STATUS_EMOJI.get(old_status, "❓")
    old_label = STATUS_MAP.get(old_status, old_status).upper()
    new_label = STATUS_MAP.get(new_status, new_status).upper()

    if STATUS_MAP.get(new_status, "up") in PROBLEM_STATUSES:
        header = f"{emoji} <b>{SERVICE_NAME.upper()} — {new_label}</b>"
    else:
        header = f"{emoji} <b>{SERVICE_NAME.upper()} — RECOVERED</b>"

    return "\n".join([
        header,
        f"Was: {old_emoji} {old_label}  →  Now: {emoji} {new_label}",
        f"🕐 {ts}",
    ])


def main():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("❌  Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
        sys.exit(1)

    now_ts, _ = local_timestamp()
    print(f"[{now_ts}]\n")

    # Fetch Epic summary
    print("Fetching Epic Games status...")
    data = fetch_epic_summary()
    components = data.get("components", [])

    # Find the Epic Games Store group ID first
    group_id = None
    for c in components:
        if c.get("name", "").lower() == TARGET_GROUP and c.get("group") is True:
            group_id = c.get("id")
            break

    if not group_id:
        print(f"❌  Could not find '{TARGET_GROUP}' group in Epic status page")
        sys.exit(1)

    # Collect statuses of all sub-components in that group
    sub_statuses = []
    for c in components:
        if c.get("group_id") == group_id:
            sub_statuses.append(c.get("status", "operational"))

    if not sub_statuses:
        print("❌  No sub-components found for Epic Games Store group")
        sys.exit(1)

    raw_status   = worst_status(sub_statuses)
    simple_status = STATUS_MAP.get(raw_status, "unknown")
    emoji        = STATUS_EMOJI.get(raw_status, "❓")

    print(f"\n{'=' * 45}")
    print(f"  EPIC GAMES STORE STATUS")
    print(f"{'=' * 45}")
    print(f"\n  {emoji}  {SERVICE_NAME}")
    print(f"      Status : {simple_status.upper()}")
    print(f"      Raw    : {raw_status}")
    print(f"\n{'=' * 45}\n")

    # Load state and detect transition
    state = load_state()
    old_raw = state.get(SERVICE_KEY, {}).get("raw_status", "unknown")

    if old_raw != raw_status:
        print(f"🔄  Transition: {old_raw} → {raw_status}")
        msg = build_message(old_raw, raw_status, now_ts)
        print(f"\n--- Message ---\n{msg}\n---------------")
        ok = send_telegram(msg)
        print("✅  Sent" if ok else "❌  Failed to send")
    else:
        print(f"➡️   No change: {SERVICE_NAME} — {simple_status.upper()}")
        print("🔕  No notification sent")

    # Update state + history
    state[SERVICE_KEY] = {
        "status":     simple_status,
        "raw_status": raw_status,
        "since":      now_ts,
    }
    save_state(state)
    append_history({"ts": now_ts, "service": SERVICE_KEY, "status": simple_status})


if __name__ == "__main__":
    main()