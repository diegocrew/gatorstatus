"""
PlayStation Network Status Monitor
Fetches status from status.playstation.com (Atlassian Statuspage).
Uses the top-level status indicator — no API key required.
Only modifies the 'psn' key in state.json; all other service keys are preserved.

Usage:
    python scripts/check_psn.py
"""

import os
import sys
import json
import http.client
from datetime import datetime, timezone, timedelta
import calendar

HOST           = "status.playstation.com"
PATH           = "/api/v2/summary.json"
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")
STATE_FILE     = "state.json"
HISTORY_FILE   = "history.ndjson"
SERVICE_KEY    = "psn"
SERVICE_NAME   = "PlayStation Network"

# Atlassian top-level indicator → simplified status used throughout the project
INDICATOR_MAP = {
    "none":        "up",
    "minor":       "warn",
    "major":       "down",
    "critical":    "down",
    "maintenance": "maintenance",   # synthetic — set when a maintenance is in_progress
}

INDICATOR_EMOJI = {
    "none":        "✅",
    "minor":       "⚠️",
    "major":       "🔴",
    "critical":    "🔴",
    "maintenance": "🔧",
}

PROBLEM_STATUSES = {"warn", "down", "maintenance"}


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


def fetch_summary() -> dict:
    conn = http.client.HTTPSConnection(HOST, timeout=15)
    conn.request("GET", PATH, headers={"Accept": "application/json",
                                        "User-Agent": "gatorstatus-monitor/1.0"})
    resp = conn.getresponse()
    raw  = resp.read().decode()
    conn.close()
    if resp.status != 200:
        print(f"❌  {SERVICE_NAME} API HTTP {resp.status}")
        sys.exit(1)
    return json.loads(raw)


def send_telegram(message: str) -> bool:
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


def build_message(old_ind: str, new_ind: str, ts: str) -> str:
    old_simple = INDICATOR_MAP.get(old_ind, old_ind)
    new_simple = INDICATOR_MAP.get(new_ind, new_ind)
    old_emoji  = INDICATOR_EMOJI.get(old_ind, "❓")
    new_emoji  = INDICATOR_EMOJI.get(new_ind, "❓")

    if new_simple in PROBLEM_STATUSES:
        header = f"{new_emoji} <b>{SERVICE_NAME.upper()} — {new_simple.upper()}</b>"
    else:
        header = f"{new_emoji} <b>{SERVICE_NAME.upper()} — RECOVERED</b>"

    return "\n".join([
        header,
        f"Was: {old_emoji} {old_simple.upper()}  →  Now: {new_emoji} {new_simple.upper()}",
        f"🕐 {ts}",
    ])


def main():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("❌  Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
        sys.exit(1)

    now_ts, _ = local_timestamp()
    print(f"[{now_ts}]\n")
    print(f"Fetching {SERVICE_NAME} status...")

    data      = fetch_summary()
    indicator = data.get("status", {}).get("indicator", "none")

    # Promote to maintenance if a scheduled maintenance window is currently active
    maintenances = data.get("scheduled_maintenances", [])
    if indicator == "none" and any(m.get("status") == "in_progress" for m in maintenances):
        indicator = "maintenance"

    simple_status = INDICATOR_MAP.get(indicator, "unknown")
    emoji         = INDICATOR_EMOJI.get(indicator, "✅")

    print(f"\n{'=' * 45}")
    print(f"  {SERVICE_NAME.upper()} STATUS")
    print(f"{'=' * 45}")
    print(f"\n  {emoji}  {SERVICE_NAME}")
    print(f"      Status    : {simple_status.upper()}")
    print(f"      Indicator : {indicator}")
    print(f"\n{'=' * 45}\n")

    # Load full state — only touch our own key, leave all other services intact
    state     = load_state()
    old_ind   = state.get(SERVICE_KEY, {}).get("raw_status", "unknown")

    if old_ind != indicator:
        print(f"🔄  Transition: {old_ind} → {indicator}")
        msg = build_message(old_ind, indicator, now_ts)
        print(f"\n--- Message ---\n{msg}\n---------------")
        ok = send_telegram(msg)
        print("✅  Sent" if ok else "❌  Failed to send")
    else:
        print(f"➡️   No change: {SERVICE_NAME} — {simple_status.upper()}")
        print("🔕  No notification sent")

    state[SERVICE_KEY] = {
        "status":     simple_status,
        "raw_status": indicator,
        "since":      now_ts,
    }
    save_state(state)
    append_history({"ts": now_ts, "service": SERVICE_KEY, "status": simple_status})


if __name__ == "__main__":
    main()
