# Phase 1 verification

Executed on Dashboard NAS on 2026-11-22. All application test databases were temporary files on the data volume.

| Check | Result |
| --- | --- |
| Clean Python 3.12 virtual environment install from pinned requirements and `pip check` | Passed |
| Backend pytest suite | 8 passed. Covers startup, repeat startup and database preservation, environment validation, baseline migration, healthy and degraded health responses, HTTP errors, PNG, HTML and built frontend assets. |
| Alembic CLI against a temporary database | `upgrade head` succeeded, `current` reported `0001 (head)` |
| Frontend clean `npm ci`, TypeScript and Vite build | Passed |
| Firefox 159 headless loopback smoke test | Passed. Live connectivity indicator, no horizontal overflow at desktop/mobile viewport sizes, Pomodoro placeholder navigation and a decoded 758 × 1024 image on the Kindle page. |
| Docker Compose syntax and environment resolution | Passed for defaults and `.env.example` |
| Docker image build and live container health check | Deferred. The Docker data root is on the shared Ubuntu partition with 4.0 GB free. |
| Physical Kindle | Deferred to device testing. See the compatibility document. |

Repeat the core checks from the checkout with the local dependencies installed.

```bash
export TMPDIR="$PWD/../tmp"
npm --prefix frontend run typecheck
npm --prefix frontend run build
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests
docker compose config --quiet
docker compose --env-file .env.example config --quiet
```

## Phase 2 verification

| Check | Result |
| --- | --- |
| Backend pytest suite | 19 passed. Includes existing Kindle diagnostics, authentication and expiration, CSRF, login limits, task and deadline CRUD, widget persistence, weather parsing/cache/outage recovery, realistic Kindle rendering, and upgrade/restart recovery. |
| TypeScript and Vite production build | Passed |
| Headless Firefox | Passed for sign-in, task and deadline creation, widget ordering, settings and sharing, no horizontal overflow at phone width, full Kindle image fit, diagnostic access, and sign-out. |
| Open-Meteo on Dashboard NAS | Live Montréal request returned current conditions and daily high and low. |
| Alembic | A read-only SQLite backup of the NAS database upgraded from `0001` to `0002` and passed `PRAGMA integrity_check`. A fresh temporary database also upgraded and passed the metadata drift check. At the Phase 2 handoff, live SQLite was still at `0001`. |
| Compose configuration | Passed with defaults and `.env.example`. The shared Ubuntu partition still has 4.0 GB available, so the build and live container health check were deferred. |
| Physical Kindle | The user confirmed screen fit, automatic 30-second refresh, HTML POST, and manual refresh on the diagnostic. The Phase 2 populated display was verified in Firefox and still needs a physical check. |

## Phase 2.5A KUAL package

| Check | Result |
| --- | --- |
| Live SQLite backup and migration | Verified `0001` backup, mode 600, at `data/backups/dashboard-20261122T231646416498Z.sqlite3` under the the data volume project storage root. Live database upgraded to `0002`, passed integrity check, and matches Alembic metadata. |
| Live FastAPI endpoints | Temporarily started on `192.0.2.10:8765`. Health and the synthetic PNG returned HTTP 200. Pillow verified the PNG as 758 × 1024 grayscale. Real-data sharing remained disabled and the populated endpoint returned 404. Stopped the temporary app afterward. |
| Packaged client and timeouts | The extracted client fetched and validated the NAS image under BusyBox ash. A stalled test endpoint returned curl exit 28 after 20.0 seconds. The previously cached image stayed intact. |
| Automated suite | 25 passed. Includes XML and JSON syntax, menu paths, shell syntax, HTTP failures and invalid PNGs, log messages, cache retention, mocked eips invocation, overlap and cancellation. |
| ZIP | Rebuilt twice with identical SHA-256, passed archive integrity, and verified LF, UNIX script permissions, and the exact nine-file allowlist under `extensions/rahat-dashboard/`. |
| Physical Kindle | KUAL menu launch, curl and eips on the device, native rendering, Amazon repaint and recovery are pending. The extension has one-shot actions only. |
| NAS storage | Ubuntu root had 3.8 GB free and the data volume had 167 GB free. No dependencies, Docker build, or NAS service changes were needed. |
