# GatorStatus

A lightweight GitHub Actions pipeline that monitors gaming and online services for outages, sends Telegram push notifications on state changes, and publishes a live status dashboard via GitHub Pages.

---

## Live Dashboard

Enable GitHub Pages to get a hosted status history chart:

1. Repo → **Settings → Pages**
2. Source: **Deploy from a branch** → branch `main`, folder `/ (root)`
3. Save — page goes live at `https://<user>.github.io/gatorstatus/`

The dashboard reads `history.ndjson` directly in the browser. No build step. Updates automatically with every commit from the monitor workflow.

**Features:**
- Summary chart — all services on one graph, one line per service
- Per-service charts — dots at each recorded check, line segments coloured by transition direction (green = up, orange = partial/maintenance, red = down)
- Time filters: last Day / Week / Month

---

## How It Works

Every 10 minutes, GitHub Actions:

1. Calls the **StatusGator API** to fetch current monitor statuses
2. Fetches **Epic Games Store** status directly from the official Atlassian status page
3. Compares each service against the last known state (`state.json`)
4. Sends a Telegram message only if a transition is detected (e.g. `up → warn`, `down → up`)
5. Commits updated `state.json` and `history.ndjson` back to the repo

No notification is sent if nothing changed. Silence means everything is fine.

First run always fires a notification per service so you know the pipeline is working.

---

## Monitored Services

| Service | Script | Monitor Type | Source |
|---------|--------|-------------|--------|
| Ubisoft Connect | `statusgator.py` | Service monitor | Official Ubisoft status page via StatusGator |
| Steam | `statusgator.py` | Website monitor | HTTP probe via StatusGator |
| EA / Electronic Arts | `statusgator.py` | Service monitor | Official EA status page via StatusGator |
| Epic Games Store | `check_epic.py` | Direct Atlassian API | status.epicgames.com |
| PlayStation Network | `check_psn.py` | Direct Atlassian API | status.playstation.com |
| Discord | `check_discord.py` | Direct Atlassian API | discordstatus.com |

StatusGator free tier is capped at 3 monitors — all others are fetched directly from their Atlassian Statuspage APIs (no auth required). Each script only modifies its own key in `state.json`; other services are never touched.

---

## Status Values

| Status | Meaning | Chart colour |
|--------|---------|--------------|
| ✅ `up` | Service operating normally | Green |
| ⚠️ `warn` | Partial outage or degraded performance | Orange |
| 🔴 `down` | Major outage | Red |
| 🔧 `maintenance` | Scheduled maintenance | Orange |

---

## Repository Structure

```
.
├── .github/
│   └── workflows/
│       └── monitor.yml         # GitHub Actions workflow (runs every 10 min)
├── scripts/
│   ├── statusgator.py          # StatusGator monitor (Ubisoft, Steam, EA)
│   ├── check_epic.py           # Epic Games Store — Atlassian Statuspage direct
│   ├── check_psn.py            # PlayStation Network — Atlassian Statuspage direct
│   └── check_discord.py        # Discord — Atlassian Statuspage direct
├── config.json                 # Service match config for statusgator.py
├── state.json                  # Last known status per service (auto-updated)
├── history.ndjson              # Full status history, one JSON record per line
├── index.html                  # GitHub Pages dashboard (client-side, no build)
└── README.md
```

`history.ndjson` format — one record per line:
```json
{"ts": "2026-04-23 20:48:07 CEST", "service": "epic_store", "status": "up"}
```

---

## Tech Stack

- **Python 3** — stdlib only, no pip or requirements file needed
- **GitHub Actions** — scheduler and runner (free tier)
- **StatusGator** — monitoring platform (free tier, 3 monitors)
- **Telegram Bot API** — push notifications
- **GitHub Pages** — static dashboard hosting (free)
- **Chart.js 4** — browser-side charts, loaded from CDN

---

## Setup Guide

### 1. StatusGator

1. Create a free account at [statusgator.com](https://statusgator.com)
2. Create a board
3. Add monitors:
   - **Ubisoft** — Service monitor (search for Ubisoft)
   - **Steam** — Website monitor — `https://store.steampowered.com`
   - **EA** — Service monitor (search for Electronic Arts)
4. Go to **API** in the left sidebar and generate a **Read-only** token

### 2. Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the bot token BotFather provides
4. Start a chat with your bot and send any message
5. Open `https://api.telegram.org/botYOUR_TOKEN/getUpdates` in a browser
6. Find `"chat": { "id": XXXXXXXXX }` — that number is your chat ID

Optional hardening: in BotFather go to `/mybots` → your bot → **Bot Settings → Allow Groups → Turn off**.

### 3. GitHub Secrets

Repo → **Settings → Secrets and variables → Actions**:

| Secret name | Value |
|-------------|-------|
| `STATUSGATOR_TOKEN` | StatusGator API token |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Numeric Telegram chat ID |

### 4. Initial state.json

Create `state.json` in the repo root:
```json
{}
```
The scripts populate it on the first run.

### 5. Workflow permissions

Repo → **Settings → Actions → General → Workflow permissions → Read and write permissions**

---

## Running Manually

**Actions → Service Status Monitor → Run workflow** — triggers immediately without waiting for the schedule. Useful for testing after setup.

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

## Extending to More Services

### Via direct Atlassian Statuspage API (recommended, no auth needed)

Copy `check_psn.py` or `check_discord.py` (they use the simpler top-level indicator approach), change the four constants at the top (`HOST`, `PATH`, `SERVICE_KEY`, `SERVICE_NAME`), and add a step in `monitor.yml`.

Services with confirmed Atlassian Statuspage feeds:

| Service | Host | Notes |
|---------|------|-------|
| ~~PlayStation Network~~ | ~~status.playstation.com~~ | Already monitored |
| ~~Discord~~ | ~~discordstatus.com~~ | Already monitored |
| Rockstar Games | `support.rockstargames.com` | GTA Online, RDO |
| Riot Games | `status.riotgames.com` | LoL, Valorant — per-region API |
| GOG / CD Projekt | `status.gog.com` | GOG Galaxy |
| Twitch | `twitchstatus.com` | Streaming platform |

### Via StatusGator (uses one of the 3 free monitor slots)

Add a Service monitor on your board, then add its lowercase name to `config.json`.

---

## Timezone

Timestamps are in CET/CEST (Central European Time), switching automatically between UTC+1 and UTC+2 based on EU daylight saving rules.

---

## Limitations

- GitHub Actions scheduled workflows can lag a few minutes under high queue load.
- StatusGator free tier: 3 monitors max.
- Steam has no official status page — the monitor is an HTTP probe only, not a granular health feed.
- `history.ndjson` grows ~4 records/hour. At that rate it stays well under 1 MB for years.

---

## License

MIT
