"""
Discord Status Monitor
Fetches status from discordstatus.com (Atlassian Statuspage).
Uses the top-level status indicator — no API key required.
Only modifies the 'discord' key in state.json; all other service keys are preserved.

Usage:
    python scripts/check_discord.py
"""

import os
import sys
import json
import http.client

from utils import (
    TELEGRAM_TOKEN, TELEGRAM_CHAT,
    local_timestamp, send_telegram, load_state, save_state, append_history
)

HOST        = "discordstatus.com"
PATH        = "/api/v2/summary.json"
SERVICE_KEY = "discord"
SERVICE_NAME = "Discord"

STATUS_EMOJI = {
    "up":          "✅",
    "warn":        "⚠️",
    "down":        "🔴",
    "maintenance": "🔧",
    "unknown":     "❓",
}

INDICATOR_MAP = {
    "none":        "up",
    "minor":       "warn",
    "major":       "down",
    "critical":    "down",
    "maintenance": "maintenance",
}

PROBLEM_STATUSES = {"warn", "down", "maintenance"}


def fetch_summary() -> dict:
    conn = http.client.HTTPSConnection(HOST, timeout=15)
    conn.request("GET", PATH, headers={
        "Accept":     "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; gatorstatus/1.0)"
    })
    resp = conn.getresponse()
    raw  = resp.read().decode()
    conn.close()
    if resp.status != 200:
        print(f"ERROR: {SERVICE_NAME} API HTTP {resp.status}")
        sys.exit(1)
    return json.loads(raw)


def build_message(old_ind: str, new_ind: str, ts: str) -> str:
    old_simple = INDICATOR_MAP.get(old_ind, old_ind)
    new_simple = INDICATOR_MAP.get(new_ind, new_ind)
    emoji      = STATUS_EMOJI.get(new_simple, "")

    if new_simple in PROBLEM_STATUSES:
        header = f"{emoji} <b>{SERVICE_NAME.upper()} — {new_simple.upper()}</b>"
    else:
        header = f"{emoji} <b>{SERVICE_NAME.upper()} — RECOVERED</b>"

    return "\n".join([
        header,
        f"Was: {old_simple.upper()}  ->  Now: {new_simple.upper()}",
        ts,
    ])


def main():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("ERROR: Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
        sys.exit(1)

    now_ts, _ = local_timestamp()
    print(f"[{now_ts}]\n")
    print(f"Fetching {SERVICE_NAME} status...")

    data      = fetch_summary()
    indicator = data.get("status", {}).get("indicator", "none")

    maintenances = data.get("scheduled_maintenances", [])
    if indicator == "none" and any(m.get("status") == "in_progress" for m in maintenances):
        indicator = "maintenance"

    simple_status = INDICATOR_MAP.get(indicator, "unknown")

    print(f"\n{'=' * 45}")
    print(f"  {SERVICE_NAME.upper()} STATUS")
    print(f"{'=' * 45}")
    print(f"\n  {SERVICE_NAME}")
    print(f"      Status    : {simple_status.upper()}")
    print(f"      Indicator : {indicator}")
    print(f"\n{'=' * 45}\n")

    state   = load_state()
    old_ind = state.get(SERVICE_KEY, {}).get("raw_status", "unknown")

    if old_ind != indicator:
        print(f"Transition: {old_ind} -> {indicator}")
        msg = build_message(old_ind, indicator, now_ts)
        print(f"\n--- Message ---\n{msg}\n---------------")
        ok = send_telegram(msg)
        print("Sent" if ok else "Failed to send")
    else:
        print(f"No change: {SERVICE_NAME} — {simple_status.upper()}")
        print("No notification sent")

    state[SERVICE_KEY] = {
        "status":     simple_status,
        "raw_status": indicator,
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
