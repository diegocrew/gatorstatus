# 🎮 Service Status Monitor

A lightweight GitHub Actions pipeline that monitors gaming and online services for outages and sends instant **Telegram push notifications** when something changes — so you know before you sit down and open the launcher.

---

## How It Works

Every 10 minutes, GitHub Actions:

1. Calls the **StatusGator API** to fetch current monitor statuses
2. Compares against the last known state (`state.json`)
3. If a **transition** is detected (e.g. `up → warn`, `warn → down`, `down → up`) — sends a Telegram message
4. Commits the updated `state.json` back to the repo

**No notification is sent if nothing changed.** Silence = everything is fine.

---

## Monitored Services

| Service | Monitor Type | Source |
|---------|-------------|--------|
| Ubisoft Connect | Service monitor | Official Ubisoft status page via StatusGator |
| Steam | Website monitor | HTTP probe via StatusGator |

> Easily extendable — services with official Atlassian Statuspage feeds (GitHub, Xbox, Meta, LinkedIn) can be added with minimal changes.

---

## Status Values

| Status | Meaning |
|--------|---------|
| ✅ `up` | Service operating normally |
| ⚠️ `warn` | Partial outage or degraded performance |
| 🔴 `down` | Major outage |
| 🔧 `maintenance` | Scheduled maintenance |

---

## Tech Stack

- **Python 3** — stdlib only, no pip/requirements needed
- **GitHub Actions** — scheduler + runner (free tier)
- **StatusGator** — monitoring platform (free tier, 3 monitors)
- **Telegram Bot API** — push notifications

---

## Repository Structure

```
.
├── .github/
│   └── workflows/
│       └── monitor.yml       # GitHub Actions workflow
├── scripts/
│   └── check_status.py       # Main monitoring script
├── state.json                 # Last known status per service (auto-updated)
└── README.md
```

---

## Setup Guide

### 1. StatusGator

1. Create a free account at [statusgator.com](https://statusgator.com)
2. Create a board (e.g. `gaming`)
3. Add monitors:
   - **Ubisoft** → Service monitor (search for Ubisoft)
   - **Steam** → Website monitor → `https://store.steampowered.com`
4. Go to **API** in the left sidebar → generate a **Read-only** token
   - Name it something descriptive, e.g. `github-actions-monitor`
   - Set an expiry (1 year recommended)

### 2. Telegram Bot

1. Open Telegram → search for **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the **bot token** BotFather gives you
4. Search for your new bot → tap **Start** → send any message
5. Open in browser (replace `YOUR_TOKEN`):
   ```
   https://api.telegram.org/botYOUR_TOKEN/getUpdates
   ```
6. Find `"chat": { "id": XXXXXXXXX }` — that is your **chat ID**

**Optional hardening:**
- In BotFather → `/mybots` → your bot → **Bot Settings** → **Allow Groups** → **Turn off**
- The bot only ever *sends* to your chat ID — it never reads or responds to messages

### 3. GitHub Secrets

In your repo → **Settings → Secrets and variables → Actions**, add:

| Secret name | Value |
|-------------|-------|
| `STATUSGATOR_TOKEN` | Your StatusGator API token |
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Your numeric Telegram chat ID |

### 4. Initial state.json

Create `state.json` in the repo root with empty content:

```json
{}
```

The script will populate it on the first run.

### 5. Workflow permissions

The workflow commits `state.json` back to the repo after each run. Make sure **Actions** have write access:

Repo → **Settings → Actions → General → Workflow permissions** → select **Read and write permissions**

---

## Running Manually

Go to **Actions → Service Status Monitor → Run workflow** to trigger immediately without waiting for the 10-minute schedule.

Useful for:
- Testing after setup
- Forcing a recheck after a known outage

---

## Example Telegram Notifications

**Outage detected:**
```
⚠️ UBISOFT — WARN
Was: ✅ UP  →  Now: ⚠️ WARN
ℹ️ Possible outage: Division 2 server connection issues
🕐 2026-04-21 22:14:00 CEST
```

**Service recovered:**
```
✅ UBISOFT — RECOVERED
Was: ⚠️ WARN  →  Now: ✅ UP
🕐 2026-04-21 23:05:00 CEST
```

---

## Timezone

Timestamps are displayed in **CET/CEST** (Central European Time), switching automatically between UTC+1 and UTC+2 based on EU daylight saving rules — no manual adjustment needed.

---

## Limitations

- GitHub Actions scheduled workflows can lag a few minutes under load — this is a monitoring tool for gaming services, not a production SLA alerter
- StatusGator free tier: **3 monitors maximum**
- Steam has no official status page — the Website monitor is an HTTP probe only, not a granular service health feed

---

## Extending to More Services

Services with official **Atlassian Statuspage** feeds can be added without scraping:

| Service | Status page |
|---------|------------|
| GitHub | `githubstatus.com` |
| Xbox Live | `support.xbox.com/xbox-live-status` |
| Meta / Facebook | `metastatus.com` |
| LinkedIn | `www.linkedin-apistatus.com` |

Add them as **Service monitors** in StatusGator (uses your remaining free monitor slot or upgrade), then add their names to the `WATCHED` set in `check_status.py`.

---

## License

MIT