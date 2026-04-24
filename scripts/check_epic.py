"""
Epic Games Store Status Monitor
Fetches status directly from status.epicgames.com (Atlassian Statuspage).
Monitors only the 'Epic Games Store' component group.
Detects transitions and sends Telegram notifications.
Shares state.json with other monitor scripts — only modifies the 'epic_store' key.

No API key required.

Usage:
    python scripts/check_epic.py
"""

import os
import sys
import json
import http.client

from utils import (
    TELEGRAM_TOKEN, TELEGRAM_CHAT,
    local_timestamp, send_telegram, load_state, save_state, append_history
)

EPIC_HOST    = "status.epicgames.com"
EPIC_PATH    = "/api/v2/summary.json"
SERVICE_KEY  = "epic_store"
SERVICE_NAME = "Epic Games Store"
TARGET_GROUP = "epic games store"

STATUS_EMOJI = {
    "operational":          "✅",
    "degraded_performance": "⚠️",
    "partial_outage":       "⚠️",
    "major_outage":         "🔴",
    "under_maintenance":    "🔧",
    "unknown":              "❓",
}

STATUS_MAP = {
    "operational":          "up",
    "degraded_performance": "warn",
    "partial_outage":       "warn",
    "major_outage":         "down",
    "under_maintenance":    "maintenance",
}

PROBLEM_STATUSES = {"warn", "down", "maintenance"}
STATUS_PRIORITY  = ["major_outage", "partial_outage", "degraded_performance",
                    "under_maintenance", "operational"]


def fetch_epic_summary() -> dict:
    conn = http.client.HTTPSConnection(EPIC_HOST, timeout=15)
    conn.request("GET", EPIC_PATH, headers={"Accept": "application/json"})
    resp = conn.getresponse()
    raw  = resp.read().decode()
    conn.close()
    if resp.status != 200:
        print(f"ERROR: Epic API HTTP {resp.status}")
        sys.exit(1)
    return json.loads(raw)


def worst_status(statuses: list) -> str:
    for s in STATUS_PRIORITY:
        if s in statuses:
            return s
    return "operational"


def build_message(old_status: str, new_status: str, ts: str) -> str:
    emoji     = STATUS_EMOJI.get(new_status, "")
    old_label = STATUS_MAP.get(old_status, old_status).upper()
    new_label = STATUS_MAP.get(new_status, new_status).upper()

    if STATUS_MAP.get(new_status, "up") in PROBLEM_STATUSES:
        header = f"{emoji} <b>{SERVICE_NAME.upper()} — {new_label}</b>"
    else:
        header = f"{emoji} <b>{SERVICE_NAME.upper()} — RECOVERED</b>"

    return "\n".join([
        header,
        f"Was: {old_label}  ->  Now: {new_label}",
        ts,
    ])


def main():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("ERROR: Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
        sys.exit(1)

    now_ts, _ = local_timestamp()
    print(f"[{now_ts}]\n")

    print("Fetching Epic Games status...")
    data       = fetch_epic_summary()
    components = data.get("components", [])

    group_id = None
    for c in components:
        if c.get("name", "").lower() == TARGET_GROUP and c.get("group") is True:
            group_id = c.get("id")
            break

    if not group_id:
        print(f"ERROR: Could not find '{TARGET_GROUP}' group in Epic status page")
        sys.exit(1)

    sub_statuses = []
    for c in components:
        if c.get("group_id") == group_id:
            sub_statuses.append(c.get("status", "operational"))

    if not sub_statuses:
        print("ERROR: No sub-components found for Epic Games Store group")
        sys.exit(1)

    raw_status    = worst_status(sub_statuses)
    simple_status = STATUS_MAP.get(raw_status, "unknown")

    print(f"\n{'=' * 45}")
    print(f"  EPIC GAMES STORE STATUS")
    print(f"{'=' * 45}")
    print(f"\n  {SERVICE_NAME}")
    print(f"      Status : {simple_status.upper()}")
    print(f"      Raw    : {raw_status}")
    print(f"\n{'=' * 45}\n")

    state   = load_state()
    old_raw = state.get(SERVICE_KEY, {}).get("raw_status", "unknown")

    if old_raw != raw_status:
        print(f"Transition: {old_raw} -> {raw_status}")
        msg = build_message(old_raw, raw_status, now_ts)
        print(f"\n--- Message ---\n{msg}\n---------------")
        ok = send_telegram(msg)
        print("Sent" if ok else "Failed to send")
    else:
        print(f"No change: {SERVICE_NAME} — {simple_status.upper()}")
        print("No notification sent")

    state[SERVICE_KEY] = {
        "status":     simple_status,
        "raw_status": raw_status,
        "since":      now_ts,
    }
    save_state(state)
    append_history({"ts": now_ts, "service": SERVICE_KEY, "status": simple_status})


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        send_telegram(f"❌ <b>gatorstatus: {os.path.basename(__file__)} failed</b>\n{type(e).__name__}: {e}")
        raise
