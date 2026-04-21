# Service Status Monitor
 
A lightweight GitHub Actions pipeline that monitors gaming and online services for outages and sends Telegram push notifications when something changes, so you know before you sit down and open the launcher.
 
---
 
## How It Works
 
Every 10 minutes, GitHub Actions:
 
1. Calls the **StatusGator API** to fetch current monitor statuses
2. Fetches **Epic Games Store** status directly from the official Atlassian status page
3. Compares each service against the last known state (`state.json`)
4. Sends a Telegram message only if a transition is detected (e.g. `up -> warn`, `down -> up`)
5. Commits the updated `state.json` back to the repo
No notification is sent if nothing changed. Silence means everything is fine.
 
First run always fires a notification per service so you know the pipeline is working.
 
---
 
## Monitored Services
 
| Service | Monitor Type | Source |
|---------|-------------|--------|
| Ubisoft Connect | Service monitor | Official Ubisoft status page via StatusGator |
| Steam | Website monitor | HTTP probe via StatusGator |
| EA / Electronic Arts | Service monitor | Official EA status page via StatusGator (21 components) |
| Epic Games Store | Direct API | status.epicgames.com (Atlassian Statuspage, no auth required) |
 
StatusGator free tier is capped at 3 monitors. Epic is fetched directly to work around this limit. Additional services with official Atlassian Statuspage feeds can be added via a separate script following the same pattern as `check_epic.py`.
 
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
 
- **Python 3** -- stdlib only, no pip or requirements file needed
- **GitHub Actions** -- scheduler and runner (free tier)
- **StatusGator** -- monitoring platform (free tier, 3 monitors)
- **Telegram Bot API** -- push notifications
---
 
## Repository Structure
 
```
.
+-- .github/
|   +-- workflows/
|       +-- monitor.yml         # GitHub Actions workflow
+-- scripts/
|   +-- check_status.py         # StatusGator monitor (Ubisoft, Steam, EA)
|   +-- check_epic.py           # Epic Games Store direct monitor
+-- config.json                 # Service match config for check_status.py
+-- state.json                  # Last known status per service (auto-updated)
+-- README.md
```
 
---
 
## Setup Guide
 
### 1. StatusGator
 
1. Create a free account at [statusgator.com](https://statusgator.com)
2. Create a board
3. Add monitors:
   - **Ubisoft** -- Service monitor (search for Ubisoft)
   - **Steam** -- Website monitor -- `https://store.steampowered.com`
   - **EA** -- Service monitor (search for Electronic Arts), monitor all components
4. Go to **API** in the left sidebar and generate a **Read-only** token
   - Set a name and an expiry (1 year recommended)
### 2. Telegram Bot
 
1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the bot token BotFather provides
4. Search for your new bot, tap **Start**, and send any message
5. Open this URL in a browser (replace `YOUR_TOKEN`):
   ```
   https://api.telegram.org/botYOUR_TOKEN/getUpdates
   ```
6. Find `"chat": { "id": XXXXXXXXX }` -- that number is your chat ID
Optional hardening: in BotFather go to `/mybots` -> your bot -> **Bot Settings** -> **Allow Groups** -> **Turn off**. The bot only ever sends to your chat ID and never reads or responds to incoming messages.
 
### 3. GitHub Secrets
 
In your repo go to **Settings -> Secrets and variables -> Actions** and add:
 
| Secret name | Value |
|-------------|-------|
| `STATUSGATOR_TOKEN` | Your StatusGator API token |
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Your numeric Telegram chat ID |
 
### 4. Initial state.json
 
Create `state.json` in the repo root:
 
```json
{}
```
 
The scripts populate it on the first run.
 
### 5. Workflow permissions
 
The workflow commits `state.json` back to the repo after each run. Enable write access under:
 
Repo -> **Settings -> Actions -> General -> Workflow permissions** -> **Read and write permissions**
 
---
 
## Running Manually
 
Go to **Actions -> Service Status Monitor -> Run workflow** to trigger immediately without waiting for the schedule. Useful for testing after setup or forcing a recheck after a known outage.
 
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
 
Timestamps are displayed in CET/CEST (Central European Time), switching automatically between UTC+1 and UTC+2 based on EU daylight saving rules.
 
---
 
## Limitations
 
- GitHub Actions scheduled workflows can lag a few minutes under load. This is a personal convenience tool, not a production SLA alerter.
- StatusGator free tier is capped at 3 monitors.
- Steam has no official status page. The website monitor is an HTTP probe only, not a granular service health feed.
---
 
## Extending to More Services
 
To add a service that has an official Atlassian Statuspage feed, create a new script following the pattern of `check_epic.py` and add a step to `monitor.yml`. No changes to existing scripts needed.
 
Services with known Atlassian Statuspage feeds:
 
| Service | Status page |
|---------|------------|
| GitHub | `githubstatus.com` |
| Xbox Live | `support.xbox.com/xbox-live-status` |
| Rockstar Games | `support.rockstargames.com/servicestatus` |
 
To add a service via StatusGator instead, add it as a Service monitor on your board, then add its lowercase name to `config.json`.
 
---
 
## License
 
MIT
