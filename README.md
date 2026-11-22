# Kindle Dashboard

A self-hosted dashboard foundation for Dashboard NAS. FastAPI serves a React administration shell and a separate HTML page for the Kindle. SQLite is initialized through Alembic. The Kindle test display is a grayscale PNG rendered on the server with Pillow.

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

Start the application in the foreground.

```bash
cd /srv/kindle-dashboard/project
bash scripts/prepare-storage.sh && PYTHONPATH=backend .venv/bin/python -m app
```

Press **Ctrl+C** in the server terminal to stop it.

| Page | Local URL |
| --- | --- |
| Administration overview | http://127.0.0.1:8765/ |
| Health | http://127.0.0.1:8765/api/v1/health |
| Kindle test page | http://127.0.0.1:8765/kindle |
| Raw PNG | http://127.0.0.1:8765/api/kindle/image.png |

For controlled LAN testing, set `APP_HOST` in `.env` to Dashboard NAS’s specific trusted LAN IPv4 address and restart. Replace `127.0.0.1` in the URLs with that address. Keep the port off public reverse proxies and router port forwarding. Return to loopback when LAN testing ends. The Vite dev server uses loopback and proxies to the configured backend. With the backend running, start it with `npm --prefix frontend run dev`.

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
- [Security architecture](docs/SECURITY.md)
- [Verification results](docs/VERIFICATION.md)
- [Kindle compatibility and physical test procedure](KINDLE_COMPATIBILITY.md)
- [Implementation plan](IMPLEMENTATION_PLAN.md)
- [Requirements checklist](REQUIREMENTS_CHECKLIST.md)
