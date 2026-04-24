"""
PlayStation Network Status Monitor
Fetches status from status.playstation.com/data/statuses/region/SCEE.json
Sony's own format (NOT Atlassian Statuspage).
- Empty status arrays across all services = operational (up)
- Any entry with statusType "Outage" (within last STALE_DAYS) = down
- Any entry with statusType "Maintenance" (within last STALE_DAYS) = maintenance

Only modifies the 'psn' key in state.json; all other service keys are preserved.
HTTP errors are non-fatal: workflow continues, nothing written to state/history.

Change REGION below for a different zone (SCEA=Americas, SCEE=Europe, SCEJ=Japan).

Usage:
    python scripts/check_psn.py
"""

import os
import sys
import json
import http.client
from datetime import datetime, timezone, timedelta

from utils import (
    TELEGRAM_TOKEN, TELEGRAM_CHAT,
    local_timestamp, send_telegram, load_state, save_state, append_history
)

REGION       = "SCEE"
HOST         = "status.playstation.com"
PATH         = f"/data/statuses/region/{REGION}.json"
SERVICE_KEY  = "psn"
SERVICE_NAME = "PlayStation Network"

STATUS_EMOJI = {
    "up":          "✅",
    "warn":        "⚠️",
    "down":        "🔴",
    "maintenance": "🔧",
    "unknown":     "❓",
}

PROBLEM_STATUSES = {"warn", "down", "maintenance"}


def fetch_psn_status() -> dict | None:
    """Return parsed JSON or None on any network/HTTP error (non-fatal)."""
    try:
        conn = http.client.HTTPSConnection(HOST, timeout=15)
        conn.request("GET", PATH, headers={
            "Accept":     "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; gatorstatus/1.0)"
        })
        resp = conn.getresponse()
        raw  = resp.read().decode()
        conn.close()
        if resp.status != 200:
            print(f"WARNING: {SERVICE_NAME} API HTTP {resp.status} — skipping this run")
            return None
        return json.loads(raw)
    except Exception as e:
        print(f"WARNING: {SERVICE_NAME} fetch error: {e} — skipping this run")
        return None


def extract_status(data: dict) -> str:
    """
    Walk all countries -> services -> resources in the Sony status payload.
    Sony keeps historical outage entries indefinitely without marking them resolved,
    so only entries within STALE_DAYS are considered to avoid false positives.
    """
    STALE_DAYS      = 7
    cutoff          = datetime.now(timezone.utc) - timedelta(days=STALE_DAYS)
    has_outage      = False
    has_maintenance = False

    def is_recent(entry: dict) -> bool:
        raw = entry.get("startDate", "")
        try:
            return datetime.fromisoformat(raw) >= cutoff
        except (ValueError, AttributeError):
            return True

    def check_statuses(status_list: list):
        nonlocal has_outage, has_maintenance
        for entry in status_list:
            if not is_recent(entry):
                continue
            t = entry.get("statusType", "").lower()
            if "outage" in t:
                has_outage = True
            elif "maintenance" in t:
                has_maintenance = True

    for country in data.get("countries", []):
        check_statuses(country.get("status", []))
        for service in country.get("services", []):
            check_statuses(service.get("status", []))
            for resource in service.get("resources", []):
                check_statuses(resource.get("status", []))

    if has_outage:
        return "down"
    if has_maintenance:
        return "maintenance"
    return "up"


def build_message(old_status: str, new_status: str, ts: str) -> str:
    emoji = STATUS_EMOJI.get(new_status, "")
    if new_status in PROBLEM_STATUSES:
        header = f"{emoji} <b>{SERVICE_NAME.upper()} — {new_status.upper()}</b>"
    else:
        header = f"{emoji} <b>{SERVICE_NAME.upper()} — RECOVERED</b>"

    return "\n".join([
        header,
        f"Was: {old_status.upper()}  ->  Now: {new_status.upper()}",
        ts,
    ])


def main():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("ERROR: Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
        sys.exit(1)

    now_ts, _ = local_timestamp()
    print(f"[{now_ts}]\n")
    print(f"Fetching {SERVICE_NAME} status ({REGION} region)...")

    data = fetch_psn_status()
    if data is None:
        print("Skipping state/history update due to fetch failure.")
        sys.exit(0)

    simple_status = extract_status(data)

    print(f"\n{'=' * 45}")
    print(f"  {SERVICE_NAME.upper()} STATUS ({REGION})")
    print(f"{'=' * 45}")
    print(f"\n  {SERVICE_NAME}")
    print(f"      Status : {simple_status.upper()}")
    print(f"\n{'=' * 45}\n")

    state      = load_state()
    old_status = state.get(SERVICE_KEY, {}).get("status", "unknown")

    if old_status != simple_status:
        print(f"Transition: {old_status} -> {simple_status}")
        msg = build_message(old_status, simple_status, now_ts)
        print(f"\n--- Message ---\n{msg}\n---------------")
        ok = send_telegram(msg)
        print("Sent" if ok else "Failed to send")
    else:
        print(f"No change: {SERVICE_NAME} — {simple_status.upper()}")
        print("No notification sent")

    state[SERVICE_KEY] = {
        "status":     simple_status,
        "raw_status": simple_status,
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
