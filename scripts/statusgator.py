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
HOST              = "statusgator.com"
API_BASE          = "/api/v3"
STATUSGATOR_TOKEN = os.environ.get("STATUSGATOR_TOKEN", "")
TELEGRAM_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT     = os.environ.get("TELEGRAM_CHAT_ID", "")
STATE_FILE        = "state.json"
HISTORY_FILE      = "history.ndjson"
CONFIG_FILE       = "config.json"

# Used only on the first line of Telegram messages
STATUS_EMOJI = {
    "up":          "✅",
    "warn":        "⚠️",
    "down":        "🔴",
    "maintenance": "🔧",
    "unknown":     "❓",
}

PROBLEM_STATUSES = {"warn", "down", "maintenance"}


def load_config() -> list:
    if not os.path.exists(CONFIG_FILE):
        print(f"ERROR: {CONFIG_FILE} not found.")
        sys.exit(1)
    with open(CONFIG_FILE) as f:
        data = json.load(f)
    services = data.get("services", [])
    if not services:
        print(f"ERROR: No services defined in {CONFIG_FILE}.")
        sys.exit(1)
    return services


def api_get(host: str, path: str, token: str):
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
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("Telegram not configured — skipping notification")
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
    print(f"Telegram error HTTP {resp.status}: {raw[:200]}")
    return False


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
    print(f"State saved -> {STATE_FILE}")


def append_history(entries: list):
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    print(f"History updated -> {HISTORY_FILE} ({len(entries)} entries)")


def build_message(name: str, old_status: str, new_status: str, last_msg: str, ts: str) -> str:
    emoji = STATUS_EMOJI.get(new_status, "")
    if new_status in PROBLEM_STATUSES:
        header = f"{emoji} <b>{name.upper()} — {new_status.upper()}</b>"
    else:
        header = f"{emoji} <b>{name.upper()} — RECOVERED</b>"

    lines = [
        header,
        f"Was: {old_status.upper()}  ->  Now: {new_status.upper()}",
    ]
    if last_msg and last_msg != "—":
        lines.append(last_msg)
    lines.append(ts)
    return "\n".join(lines)


def main():
    missing = [n for n, v in [
        ("STATUSGATOR_TOKEN", STATUSGATOR_TOKEN),
        ("TELEGRAM_BOT_TOKEN", TELEGRAM_TOKEN),
        ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT),
    ] if not v]
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    services = load_config()
    watched_matches = {s["match"].lower(): s["name"] for s in services}

    now_utc = datetime.now(timezone.utc)
    year = now_utc.year

    def last_sunday(y, month):
        import calendar
        last_day = calendar.monthrange(y, month)[1]
        d = datetime(y, month, last_day)
        return d - timedelta(days=d.weekday() + 1) if d.weekday() != 6 else d

    cest_start = last_sunday(year, 3).replace(hour=1, tzinfo=timezone.utc)
    cest_end   = last_sunday(year, 10).replace(hour=1, tzinfo=timezone.utc)

    if cest_start <= now_utc < cest_end:
        tz_offset, tz_label = timedelta(hours=2), "CEST"
    else:
        tz_offset, tz_label = timedelta(hours=1), "CET"

    now_ts = f"{(now_utc + tz_offset).strftime('%Y-%m-%d %H:%M:%S')} {tz_label}"
    print(f"[{now_ts}]\n")

    print("Step 1: Fetching boards...")
    http_status, body = api_get(HOST, f"{API_BASE}/boards?per_page=25", STATUSGATOR_TOKEN)
    if http_status != 200:
        print(f"ERROR: Boards API HTTP {http_status}: {str(body)[:300]}")
        sys.exit(1)

    boards = body.get("data", [])
    if not boards:
        print("ERROR: No boards found in StatusGator.")
        sys.exit(1)

    board    = boards[0]
    board_id = board["id"]
    print(f"Board: '{board['name']}' (id: {board_id})\n")

    print("Step 2: Fetching monitors...")
    http_status, body = api_get(HOST, f"{API_BASE}/boards/{board_id}/monitors", STATUSGATOR_TOKEN)
    if http_status != 200:
        print(f"ERROR: Monitors API HTTP {http_status}: {str(body)[:300]}")
        sys.exit(1)

    monitors = body.get("data", [])
    print(f"Found {len(monitors)} monitor(s)\n")

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

    print("=" * 45)
    print("  SERVICE STATUS REPORT")
    print("=" * 45)
    for key, data in current.items():
        print(f"\n  {data['name']}")
        print(f"      Status : {data['status'].upper()}")
        print(f"      Message: {data['last_message']}")
    print("\n" + "=" * 45 + "\n")

    previous    = load_state()
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
            print(f"Transition: {data['name']} — {old_status.upper()} -> {new_status.upper()}")
        else:
            print(f"No change:  {data['name']} — {new_status.upper()}")

    if transitions:
        print(f"\nSending {len(transitions)} Telegram notification(s)...")
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
            print("Sent" if ok else "Failed to send")
    else:
        print("\nNo transitions — no notifications sent")

    new_state = dict(previous)
    for key, data in current.items():
        new_state[key] = {"status": data["status"], "since": now_ts}
    save_state(new_state)

    history_entries = [
        {"ts": now_ts, "service": key, "status": data["status"]}
        for key, data in current.items()
    ]
    append_history(history_entries)


if __name__ == "__main__":
    main()
