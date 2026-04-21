"""
Fetches monitor statuses from StatusGator API V3.
Detects transitions and sends Telegram notifications.
Commits updated state.json back to repo via git.

"""

import os
import sys
import json
import http.client
from datetime import datetime, timezone, timedelta

# ── Config ────────────────────────────────────────────────
HOST            = "statusgator.com"
API_BASE        = "/api/v3"
STATUSGATOR_TOKEN = os.environ.get("STATUSGATOR_TOKEN", "")
TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT   = os.environ.get("TELEGRAM_CHAT_ID", "")
STATE_FILE      = "state.json"
CONFIG_FILE     = "config.json"


def load_config() -> list:
    """Load service definitions from config.json."""
    if not os.path.exists(CONFIG_FILE):
        print(f"❌  {CONFIG_FILE} not found.")
        sys.exit(1)
    with open(CONFIG_FILE) as f:
        data = json.load(f)
    services = data.get("services", [])
    if not services:
        print(f"❌  No services defined in {CONFIG_FILE}.")
        sys.exit(1)
    return services

# ── Status display ────────────────────────────────────────
STATUS_EMOJI = {
    "up":          "✅",
    "warn":        "⚠️",
    "down":        "🔴",
    "maintenance": "🔧",
    "unknown":     "❓",
}

# Statuses that mean something is wrong
PROBLEM_STATUSES = {"warn", "down", "maintenance"}


# ── Helpers ───────────────────────────────────────────────
def api_get(host: str, path: str, token: str):
    """Authenticated GET, returns (http_status, parsed_json)."""
    conn = http.client.HTTPSConnection(host, timeout=15)
    conn.request("GET", path, headers={
        "Authorization": f"Bearer {token}",
        "Accept":        "application/json",
    })
    resp = conn.getresponse()
    raw  = resp.read().decode()
    conn.close()
    return resp.status, json.loads(raw)


def send_telegram(message: str):
    """Send a message to Telegram. Returns True on success."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("⚠️  Telegram not configured — skipping notification")
        return False

    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT,
        "text":    message,
        "parse_mode": "HTML",
    }).encode()

    conn = http.client.HTTPSConnection("api.telegram.org", timeout=15)
    conn.request(
        "POST",
        f"/bot{TELEGRAM_TOKEN}/sendMessage",
        body=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = conn.getresponse()
    raw  = resp.read().decode()
    conn.close()

    if resp.status == 200:
        return True
    else:
        print(f"⚠️  Telegram error HTTP {resp.status}: {raw[:200]}")
        return False


def load_state() -> dict:
    """Load previous state from file. Returns empty dict if not found."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    """Persist current state to file."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
    print(f"💾  State saved → {STATE_FILE}")


def build_message(name: str, old_status: str, new_status: str, last_msg: str, ts: str) -> str:
    """Build a Telegram notification message."""
    emoji     = STATUS_EMOJI.get(new_status, "❓")
    old_emoji = STATUS_EMOJI.get(old_status, "❓")

    if new_status in PROBLEM_STATUSES:
        header = f"{emoji} <b>{name.upper()} — {new_status.upper()}</b>"
    else:
        header = f"{emoji} <b>{name.upper()} — RECOVERED</b>"

    lines = [
        header,
        f"Was: {old_emoji} {old_status.upper()}  →  Now: {emoji} {new_status.upper()}",
    ]
    if last_msg and last_msg != "—":
        lines.append(f"ℹ️ {last_msg}")
    lines.append(f"🕐 {ts}")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────
def main():
    # Validate secrets
    missing = [n for n, v in [
        ("STATUSGATOR_TOKEN", STATUSGATOR_TOKEN),
        ("TELEGRAM_BOT_TOKEN", TELEGRAM_TOKEN),
        ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT),
    ] if not v]
    if missing:
        print(f"❌  Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    # Load service config
    services = load_config()
    watched_matches = {s["match"].lower(): s["name"] for s in services}

    # Auto-detect CET (UTC+1) vs CEST (UTC+2)
    # CEST: last Sunday of March → last Sunday of October
    now_utc = datetime.now(timezone.utc)
    year = now_utc.year

    def last_sunday(y, month):
        # Find last Sunday of given month
        import calendar
        last_day = calendar.monthrange(y, month)[1]
        d = datetime(y, month, last_day)
        return d - timedelta(days=d.weekday() + 1) if d.weekday() != 6 else d

    cest_start = last_sunday(year, 3).replace(hour=1, tzinfo=timezone.utc)   # last Sun March 01:00 UTC
    cest_end   = last_sunday(year, 10).replace(hour=1, tzinfo=timezone.utc)  # last Sun October 01:00 UTC

    if cest_start <= now_utc < cest_end:
        tz_offset = timedelta(hours=2)
        tz_label  = "CEST"
    else:
        tz_offset = timedelta(hours=1)
        tz_label  = "CET"

    now_local = now_utc + tz_offset
    now_ts    = f"{now_local.strftime('%Y-%m-%d %H:%M:%S')} {tz_label}"
    print(f"[{now_ts}]\n")

    # ── Fetch boards ──────────────────────────────────────
    print("Step 1: Fetching boards...")
    http_status, body = api_get(HOST, f"{API_BASE}/boards?per_page=25", STATUSGATOR_TOKEN)

    if http_status != 200:
        print(f"❌  Boards API HTTP {http_status}: {str(body)[:300]}")
        sys.exit(1)

    boards = body.get("data", [])
    if not boards:
        print("❌  No boards found in StatusGator.")
        sys.exit(1)

    board    = boards[0]
    board_id = board["id"]
    print(f"✅  Board: '{board['name']}' (id: {board_id})\n")

    # ── Fetch monitors ────────────────────────────────────
    print("Step 2: Fetching monitors...")
    http_status, body = api_get(HOST, f"{API_BASE}/boards/{board_id}/monitors", STATUSGATOR_TOKEN)

    if http_status != 200:
        print(f"❌  Monitors API HTTP {http_status}: {str(body)[:300]}")
        sys.exit(1)

    monitors = body.get("data", [])
    print(f"✅  Found {len(monitors)} monitor(s)\n")

    # ── Parse watched services ────────────────────────────
    current = {}
    for m in monitors:
        name       = (m.get("display_name") or "").strip()
        name_lower = name.lower()
        for match_key, display_name in watched_matches.items():
            if match_key in name_lower:
                current[match_key] = {
                    "name":         display_name,
                    "status":       (m.get("filtered_status") or "unknown").lower(),
                    "last_message": m.get("last_message") or "—",
                }
                break

    # ── Print current statuses ────────────────────────────
    print("=" * 45)
    print("  SERVICE STATUS REPORT")
    print("=" * 45)
    for key, data in current.items():
        emoji = STATUS_EMOJI.get(data["status"], "❓")
        print(f"\n  {emoji}  {data['name']}")
        print(f"      Status : {data['status'].upper()}")
        print(f"      Message: {data['last_message']}")
    print("\n" + "=" * 45 + "\n")

    # ── Load previous state and detect transitions ────────
    previous = load_state()
    transitions = []

    for key, data in current.items():
        old_status = previous.get(key, {}).get("status", "unknown")
        new_status = data["status"]

        if old_status != new_status:
            transitions.append({
                "name":       data["name"],
                "key":        key,
                "old_status": old_status,
                "new_status": new_status,
                "last_msg":   data["last_message"],
            })
            print(f"🔄  Transition: {data['name']} — {old_status.upper()} → {new_status.upper()}")
        else:
            print(f"➡️   No change:  {data['name']} — {new_status.upper()}")

    # ── Send Telegram notifications ───────────────────────
    if transitions:
        print(f"\n📣  Sending {len(transitions)} Telegram notification(s)...")
        for t in transitions:
            msg = build_message(
                name=t["name"],
                old_status=t["old_status"],
                new_status=t["new_status"],
                last_msg=t["last_msg"],
                ts=now_ts,
            )
            print(f"\n--- Message ---\n{msg}\n---------------")
            ok = send_telegram(msg)
            print("✅  Sent" if ok else "❌  Failed to send")
    else:
        print("\n🔕  No transitions — no notifications sent")

    # ── Save updated state ────────────────────────────────
    new_state = {
        key: {"status": data["status"], "since": now_ts}
        for key, data in current.items()
    }
    save_state(new_state)


if __name__ == "__main__":
    main()