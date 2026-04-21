"""
StatusGator API PoC — Ubisoft + Steam monitor status fetch
Uses correct V3 board-based endpoints.

Usage:
    export STATUSGATOR_TOKEN=your_token_here
    python check_status.py
"""

import os
import sys
import json
import http.client
from datetime import datetime, timezone

HOST = "statusgator.com"
API_BASE = "/api/v3"
TOKEN = os.environ.get("STATUSGATOR_TOKEN", "")

WATCHED = {"steam", "ubisoft"}

STATUS_EMOJI = {
    "up":          "✅",
    "warn":        "⚠️ ",
    "down":        "🔴",
    "maintenance": "🔧",
}


def api_get(path: str):
    """Make an authenticated GET request. Returns (http_status, parsed_json)."""
    conn = http.client.HTTPSConnection(HOST, timeout=15)
    conn.request("GET", f"{API_BASE}{path}", headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/json",
    })
    resp = conn.getresponse()
    raw = resp.read().decode()
    conn.close()
    return resp.status, json.loads(raw)


def main():
    if not TOKEN:
        print("❌  STATUSGATOR_TOKEN env var not set.")
        print("    Run: export STATUSGATOR_TOKEN=your_token_here")
        sys.exit(1)

    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC]\n")

    # Step 1 — get boards
    print("Step 1: Fetching boards...")
    http_status, body = api_get("/boards?per_page=25")

    if http_status != 200:
        print(f"❌  HTTP {http_status} — {body}")
        sys.exit(1)

    boards = body.get("data", [])
    if not boards:
        print("❌  No boards found. Create a board in StatusGator and add your monitors to it.")
        sys.exit(1)

    # Use first board (PoC assumes one board)
    board = boards[0]
    board_id = board["id"]
    board_name = board["name"]
    print(f"✅  Found board: '{board_name}' (id: {board_id})\n")

    # Step 2 — get monitors for that board
    print("Step 2: Fetching monitors...")
    http_status, body = api_get(f"/boards/{board_id}/monitors")

    if http_status != 200:
        print(f"❌  HTTP {http_status} — {body}")
        sys.exit(1)

    monitors = body.get("data", [])
    print(f"✅  Found {len(monitors)} monitor(s)\n")

    # Step 3 — filter to watched services and report
    print("=" * 45)
    print("  SERVICE STATUS REPORT")
    print("=" * 45)

    found = {}
    for m in monitors:
        name = (m.get("display_name") or "").strip()
        name_lower = name.lower()

        if any(w in name_lower for w in WATCHED):
            status_val = (m.get("filtered_status") or "unknown").lower()
            emoji = STATUS_EMOJI.get(status_val, "❓")
            last_msg = m.get("last_message") or "—"
            monitor_type = m.get("monitor_type", "")

            print(f"\n  {emoji}  {name}")
            print(f"      Status : {status_val.upper()}")
            print(f"      Type   : {monitor_type}")
            print(f"      Message: {last_msg}")

            found[name_lower] = {
                "name": name,
                "status": status_val,
                "last_message": last_msg,
            }

    print("\n" + "=" * 45)

    # Report anything not found
    for w in WATCHED:
        if not any(w in k for k in found):
            print(f"  ❓  '{w}' — not found in board monitors")
            print(f"       Make sure it's added to board '{board_name}' in StatusGator")

    # Save full raw monitor list for inspection
    out = "statusgator_raw.json"
    with open(out, "w") as f:
        json.dump(monitors, f, indent=2)
    print(f"\n📄  Full monitor data saved → {out}")


if __name__ == "__main__":
    main()