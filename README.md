# Kindle Dashboard

A self-hosted productivity dashboard for Dashboard NAS. Administrators manage tasks, deadlines, weather location, and widgets in React. FastAPI stores data in SQLite and serves a script-free Kindle page with a grayscale Pillow image. The dashboard can share selected data with the Kindle over a trusted LAN.

## KOReader landscape dashboard

Phase 3A is complete and physically verified on the Kindle Paperwhite 2. The KOReader plugin provides a 1024 × 758 interactive Todo dashboard with Calendar and Pomodoro previews. Use Todo to complete or reopen shared tasks, with updates synchronized to the web administration interface. The existing portrait TRMNL client continues to work.

Version 0.3.1 adds a Salat times strip above the navigation buttons on Todo, Calendar, and Pomodoro. It shows the five daily prayers and displays Sunrise immediately after Fajr, with all times in AM/PM format. Each prayer is highlighted when it starts. Sunrise is highlighted for 30 minutes, then the highlight clears until Dhuhr. Isha stays highlighted until Fajr. Schedules are fetched from AlAdhan and cached in SQLite for the current and following months, so cached times stay available during an AlAdhan outage. The strip was verified on a physical Kindle.

- [Salat times release](https://github.com/RahatulAmin/kindle-dashboard/releases/tag/v0.3.1)
- [Phase 3A release and verified plugin ZIP](https://github.com/RahatulAmin/kindle-dashboard/releases/tag/v0.3.0)
- [Project roadmap](IMPLEMENTATION_PLAN.md)
- [Permanent NAS deployment and backups](docs/DEPLOYMENT.md)
- [KOReader plugin ZIP, installation and device checklist](docs/PHASE3A.md)

## Local installation

Run on Dashboard NAS as the deployment user using the existing Python 3.12 and Node installations.

```bash
cd /srv/kindle-dashboard/project
export TMPDIR="$PWD/../tmp"
export PIP_CACHE_DIR="$PWD/../tmp/kindle-pip-cache"
export XDG_CACHE_HOME="$PWD/../xdg-cache"
export npm_config_cache="$PWD/../npm-cache"
test -e .env || (umask 077 && cp .env.example .env)
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
npm --prefix frontend ci
npm --prefix frontend run typecheck
npm --prefix frontend run build
bash scripts/prepare-storage.sh
```

## Migrate and create the administrator

For an existing installation, make a verified [SQLite backup](docs/DATABASE.md) and stop the application before upgrading. Revision `0002` adds the Phase 2 tables to the existing database. Revision `0003` adds the prayer preferences and monthly schedule cache. The setup command and app startup both apply pending migrations.

```bash
cd /srv/kindle-dashboard/project
bash scripts/prepare-storage.sh
umask 077
PYTHONPATH=backend .venv/bin/python -m app.setup_admin admin
```

Choose your own username in place of `admin` and enter a unique password of at least 12 characters at the prompt. This is a one-time terminal setup. Sign in through the admin page afterward. Keep the SQLite database, sidecar files, and backups readable only by trusted NAS users and the app's UID. Review existing file permissions when upgrading an older installation.

## Run locally

Start the application in the foreground.

```bash
cd /srv/kindle-dashboard/project
umask 077
bash scripts/prepare-storage.sh && PYTHONPATH=backend .venv/bin/python -m app
```

Press **Ctrl+C** in the server terminal to stop it.

| Page | Local URL |
| --- | --- |
| Administration overview | http://127.0.0.1:8765/ |
| Health | http://127.0.0.1:8765/api/v1/health |
| Kindle display | http://127.0.0.1:8765/kindle |
| Kindle browser diagnostic | http://127.0.0.1:8765/kindle/test |

The admin cookie defaults to Secure and should be used over trusted HTTPS. If you need to sign in from another device over trusted-LAN plain HTTP, explicitly set `ADMIN_COOKIE_SECURE=false` in `.env` and restart. HTTP exposes the password and session to anyone who can observe or manipulate LAN traffic. Keep the app off the public internet and prefer administering over HTTPS or locally on Dashboard NAS. The Kindle display and diagnostic can use LAN HTTP independently of administrator sign-in.

For controlled LAN testing, set `APP_HOST` in `.env` to Dashboard NAS’s specific trusted LAN IPv4 address and restart. Replace `127.0.0.1` in the URLs with that address. Keep the port off public reverse proxies and router port forwarding. Return to loopback when LAN testing ends. The Vite dev server uses loopback and proxies to the configured backend. With the backend running, start it with `npm --prefix frontend run dev`.

## Use the dashboard

- **Tasks** supports manual position, priority, due date and title sorting, plus status and text filtering.
- **Deadlines** lists chronological entries. Same-day timed entries precede date-only entries. Countdown is the number of calendar days from today in America/Toronto.
- **Settings** controls the dashboard title, refresh interval, weather location and Kindle sharing. When sharing is enabled, anyone who can reach the Kindle page can see the selected widget content. The browser diagnostic continues to show its separate test image.
- **Prayer Times** lets you choose the location, calculation method, Standard or Hanafi Asr, high-latitude rule, and per-prayer adjustments. The dashboard uses America/Toronto time. The strip is disabled by default. To enable it, select an Asr convention, check **Show prayer times on the Kindle**, and save. Use **Refresh schedules** to fetch updated times on demand.
- **Widgets** controls visibility and order. Tasks and deadlines accept item limits and share the available image space. Pomodoro and NAS status preferences are reserved for later phases.
- **Weather** defaults to Montréal and caches Open-Meteo conditions for 15 minutes in memory. A failed refresh displays the last successful snapshot if available and retries after one minute. The cache resets on app restart.

## Native Kindle preview via KUAL

The Phase 2.5B KUAL extension starts in one-shot preview mode. Full-screen mode requires a power-button rehearsal on the current boot and a separate manual opt-in. Download the [KUAL ZIP](kindle-native/rahat-dashboard.zip) and follow the [installation, physical verification, and recovery guide](kindle-native/rahat-dashboard/README.md). The package defaults to the verified Dashboard NAS address `192.0.2.10:8765`.

## Compose deployment

**Deferred on Dashboard NAS.** The daemon uses the system partition and the inspection found 4.0 GB free. Before building, check `df -h / /srv`, the Docker data root and its mount, and the port. Build only when storage conditions safely permit it.

```bash
cd /srv/kindle-dashboard/project
bash scripts/prepare-storage.sh
docker compose config --quiet
docker compose up --build -d --wait
docker compose ps
```

Compose uses host networking so the server binds directly to the configured address. This preserves loopback-only access on the installed Docker 27 engine and creates no project bridge network. Use a specific LAN IPv4 address when enabling LAN access.

Stop the project with `docker compose stop` from the same checkout. The app runs as UID/GID 1000 by default. Set `APP_UID` and `APP_GID` to the numeric owner of the mount directories if needed. Prepare the directories as that owner and grant it directory write access for SQLite journals, media and rotating logs. The database must be inside `PERSISTENT_DATA_DIR`. Keep data and log directories under the the data volume project storage root. Compose writes application logs to `LOG_DIR/dashboard.jsonl` with rotation and disables Docker's persistent log driver. For local runs, choose stdout or rotating files with `LOG_DESTINATION`.

## Maintenance

- [Environment and storage assessment](docs/ENVIRONMENT.md)
- [Database migrations and backups](docs/DATABASE.md)
- [External assistant API and Muse Briefing](docs/ASSISTANT_API.md)
- [Security architecture](docs/SECURITY.md)
- [Verification results](docs/VERIFICATION.md)
- [Kindle compatibility and physical test procedure](KINDLE_COMPATIBILITY.md)
- [Implementation plan](IMPLEMENTATION_PLAN.md)
- [Requirements checklist](REQUIREMENTS_CHECKLIST.md)
