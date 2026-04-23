"""
PlayStation Network Status Monitor
Fetches status from status.playstation.com/data/statuses/region/SCEE.json
Sony's own format (NOT Atlassian Statuspage).
- Empty status arrays across all services = operational (up)
- Any entry with statusType "Outage" = down
- Any entry with statusType "Maintenance" = maintenance (if no outage)

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
import calendar

REGION         = "SCEE"
HOST           = "status.playstation.com"
PATH           = f"/data/statuses/region/{REGION}.json"
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")
STATE_FILE     = "state.json"
HISTORY_FILE   = "history.ndjson"
SERVICE_KEY    = "psn"
SERVICE_NAME   = "PlayStation Network"

STATUS_EMOJI = {
    "up":          "✅",
    "warn":        "⚠️",
    "down":        "🔴",
    "maintenance": "🔧",
    "unknown":     "❓",
}

PROBLEM_STATUSES = {"warn", "down", "maintenance"}


def local_timestamp() -> tuple[str, str]:
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
            print(f"⚠️   {SERVICE_NAME} API HTTP {resp.status} — skipping this run")
            return None
        return json.loads(raw)
    except Exception as e:
        print(f"⚠️   {SERVICE_NAME} fetch error: {e} — skipping this run")
        return None


def extract_status(data: dict) -> str:
    """
    Walk all countries → services → resources in the Sony status payload.
    Any non-empty status array with statusType containing 'outage' → 'down'.
    Any non-empty status array with statusType containing 'maintenance' → 'maintenance'.
    All empty → 'up'.
    """
    has_outage      = False
    has_maintenance = False

    def check_statuses(status_list: list):
        nonlocal has_outage, has_maintenance
        for entry in status_list:
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


def build_message(old_status: str, new_status: str, ts: str) -> str:
    old_emoji = STATUS_EMOJI.get(old_status, "❓")
    new_emoji = STATUS_EMOJI.get(new_status, "❓")

    if new_status in PROBLEM_STATUSES:
        header = f"{new_emoji} <b>{SERVICE_NAME.upper()} — {new_status.upper()}</b>"
    else:
        header = f"{new_emoji} <b>{SERVICE_NAME.upper()} — RECOVERED</b>"

    return "\n".join([
        header,
        f"Was: {old_emoji} {old_status.upper()}  →  Now: {new_emoji} {new_status.upper()}",
        f"🕐 {ts}",
    ])


def main():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("❌  Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
        sys.exit(1)

    now_ts, _ = local_timestamp()
    print(f"[{now_ts}]\n")
    print(f"Fetching {SERVICE_NAME} status ({REGION} region)...")

    data = fetch_psn_status()
    if data is None:
        print("⏭️   Skipping state/history update due to fetch failure.")
        sys.exit(0)   # non-fatal — don't break the workflow

    simple_status = extract_status(data)
    emoji         = STATUS_EMOJI.get(simple_status, "✅")

    print(f"\n{'=' * 45}")
    print(f"  {SERVICE_NAME.upper()} STATUS ({REGION})")
    print(f"{'=' * 45}")
    print(f"\n  {emoji}  {SERVICE_NAME}")
    print(f"      Status : {simple_status.upper()}")
    print(f"\n{'=' * 45}\n")

    # Load full state — only touch our own key, leave all other services intact
    state      = load_state()
    old_status = state.get(SERVICE_KEY, {}).get("status", "unknown")

    if old_status != simple_status:
        print(f"🔄  Transition: {old_status} → {simple_status}")
        msg = build_message(old_status, simple_status, now_ts)
        print(f"\n--- Message ---\n{msg}\n---------------")
        ok = send_telegram(msg)
        print("✅  Sent" if ok else "❌  Failed to send")
    else:
        print(f"➡️   No change: {SERVICE_NAME} — {simple_status.upper()}")
        print("🔕  No notification sent")

    state[SERVICE_KEY] = {
        "status":     simple_status,
        "raw_status": simple_status,
        "since":      now_ts,
    }
    save_state(state)
    append_history({"ts": now_ts, "service": SERVICE_KEY, "status": simple_status})


if __name__ == "__main__":
    main()
