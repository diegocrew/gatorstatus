import os
import json
import http.client
from datetime import datetime, timezone, timedelta
import calendar

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")

_ROOT        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE   = os.path.join(_ROOT, "state.json")
HISTORY_FILE = os.path.join(_ROOT, "history.ndjson")


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


def send_telegram(message: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("Telegram not configured — skipping")
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


def append_history(entries) -> None:
    """Accept a single dict or a list of dicts."""
    if isinstance(entries, dict):
        entries = [entries]
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    print(f"History updated -> {HISTORY_FILE} ({len(entries)} entries)")
