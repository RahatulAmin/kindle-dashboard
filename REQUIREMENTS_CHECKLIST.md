# Requirements checklist

Statuses are **Planned**, **Implemented**, **Tested**, **Blocked**, and **Not applicable**. Where a row mixes outcomes, each outcome is labeled separately.

## Phase 1

| Requirement | Status |
| --- | --- |
| Existing Git checkout, NAS and Python inspection, Docker/Compose and data root inspection, TCP 8765 check, writable ext4 mount, storage risk assessment | Tested |
| Source on the data volume, project-local tools and caches, separate application layers, no changes to existing services or Docker configuration | Implemented |
| Python 3.12, FastAPI, SQLAlchemy, Pydantic, SQLite, Alembic, Pillow and pinned dependencies | Tested |
| Environment configuration, structured logs, response schemas and errors, versioned API, startup migration and graceful teardown | Tested for configuration, startup, teardown, health and HTTP errors. Rotating file logs implemented. |
| SQLite path configuration, session management, baseline version, no domain tables, idempotent startup | Tested |
| Backup, restore and migration procedures, shared model metadata for future entities | Implemented |
| React/TypeScript/Vite/Tailwind, responsive admin shell, Overview and six navigable empty states, live backend connectivity | Tested with TypeScript, Vite, built static assets and Firefox at desktop and mobile widths. |
| Kindle HTML, no JavaScript, configurable dimensions, 758 × 1024 default grayscale PNG with title and server date/time, widget render seam | Tested at HTTP, PNG and modern Firefox levels |
| Toronto timezone, Celsius, English, port 8765, default loopback, 60-second dashboard, 30-second Pomodoro, 600-second photo rotation, 300-second idle, reserved authentication settings | Implemented. Display intervals are reserved for later phases. |
| Single multi-stage Compose container, Python-only runtime, non-root, restart policy, health probe, no privileged access or Docker socket, mount paths for data and media | Implemented. Compose configuration tested. |
| Container image build, runtime ownership and live Docker health probe | Blocked by system partition space |
| Administrator/device authentication design, no write endpoints, secret exclusions and local exposure policy | Implemented |
| Backend automated tests, TypeScript check, Vite build, static frontend integration and Compose validation | Tested |
| Production domain tables, login, device enrollment and physical-device modification | Not applicable to Phase 1 |
| README, compatibility notes, phase plan and status checklist | Implemented |

## Phase 2

| Requirement | Status |
| --- | --- |
| Terminal-only administrator setup, scrypt, expiry/revocation, cookie policy, CSRF, authenticated data access and login throttling | Tested |
| Task CRUD, manual ordering, timestamps, due date, priority, completion and Kindle visibility | Tested |
| Deadline CRUD, archive/completion, Toronto calendar-day countdown and chronological order | Tested |
| Open-Meteo current conditions, high/low, successful update time, 15-minute cache and outage fallback | Tested |
| Persisted general settings and ordered widget visibility and limits | Tested |
| Responsive Overview, Tasks, Deadlines, Display, Settings and Widgets with future Pomodoro and Photo Library placeholders | Implemented. TypeScript and production builds passed. |
| Opt-in 758 × 1024 server-side Kindle dashboard with bounded text, widget ordering, and isolated diagnostic | Tested at HTTP and PNG levels. Updated dashboard pending physical verification. |
| Alembic 0001 → 0002, existing-row preservation and restart recovery | Tested against temporary databases |
| Docker build and runtime on Dashboard NAS | Blocked by Ubuntu partition space |

## Phase 2.5A

| Requirement | Status |
| --- | --- |
| Inspect Kindle endpoints and auth, back up live SQLite before migration, verify integrity and revision | Tested. Live database is at `0002`. |
| Review PW2 KUAL metadata, curl/eips rendering, process detachment, framework restoration, and power-button recovery | Implemented in the reference and recovery documentation. |
| Four KUAL actions, POSIX shell, writable USB state, no administrator credentials | Tested locally. KUAL loading pending on hardware. |
| Configurable NAS address, HTTP 200 and PNG checks, timeouts, logs, retained last verified frame | Tested with loopback fixtures and a live NAS download from the ZIP. |
| Safe one-shot startup, stop/cancellation, no framework takeover, refresh loop, or startup hook | Tested with a mocked eips utility and cancellation during a fetch. |
| Windows USB install path, logging, uninstall, normal exit, crash and power recovery instructions | Implemented |
| ZIP layout, LF, content integrity and script permissions | Tested |
| On-device KUAL, download, eips, and Amazon repaint | Tested on the Paperwhite 2 |
| Framework takeover, automatic refresh and autostart | Not applicable to Phase 2.5A |

## Phase 2.5B

| Requirement | Status |
| --- | --- |
| Review PW2 framework management, detachment and recovery | Implemented in the extension guide |
| Device power-key rehearsal, same-boot proof and default opt-out | Tested with simulated input. Physical rehearsal required. |
| Detached supervisor validates the first PNG before stopping only the framework | Tested with mocked Upstart |
| Periodic refresh, timeout, cached fallback and full e-ink redraw requests | Tested with loopback HTTP and mocked eips |
| Clean stop, timed trial, worker error restoration and Home repaint request | Tested with mocked Upstart |
| Owner-verified stale claim cleanup and failed or late detach handling | Tested locally |
| Physical full-screen display | Tested. First short power press did not visibly restore Home. |
| Physical power-button and 120-second timed recovery | Controlled retest pending |
| Updated ZIP, installation guide and recovery procedure | Implemented |
| Boot hooks, production touch controls, Pomodoro and photos | Not applicable to Phase 2.5B |

## Later phases

| Phase | Requirements | Status |
| --- | --- | --- |
| 3 | Server-authoritative persistent timer, sessions and progress, 25/5/15 defaults, configurable durations, Start/Pause/Resume/Reset/Skip, admin controls and one-second updates | Planned |
| 4 | Mode selection, extended grayscale widgets and preview, 30-second Kindle Pomodoro refresh, and authorized touchscreen forms | Planned |
| 5 | Photo and album management, uploaded originals, optimized cache, grayscale rendering, 300-second idle and 600-second rotation defaults, configurable intervals, sequential/shuffled rotation, touchscreen return and timer-aware idle suppression | Planned |
| 6 | Registered display records, device management, scoped access, synchronization and mode integration | Planned |
| 7 | Deployment hardening and complete system testing, including container runtime and recovery tests | Planned |
| Later scope | Optional NAS status, notes and reminders | Planned |
| 8 | Continuous awake, sleep/reconnect, TLS/cookies, Phase 2 dashboard fit on PW2 and optional native-client feasibility | Planned. Screen fit, 30-second refresh, standard POST and manual refresh confirmed on the diagnostic. |
