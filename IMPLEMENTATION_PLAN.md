# Implementation plan

| Phase | Scope | State |
| --- | --- | --- |
| 1. Project foundation and architecture | NAS inspection, environment, backend, SQLite/Alembic, admin shell, Kindle test endpoints, Compose and security design | Implemented. Container deployment deferred for storage. |
| 2. Web administration, tasks, deadlines and weather | Administrator setup and sessions, task and deadline management, Toronto calendar-day countdowns, Montréal Open-Meteo weather, persisted widget settings, opt-in Kindle dashboard, and responsive admin pages | Implemented. Portrait TRMNL and the admin interface were verified on the NAS. |
| 2.5A. Native KUAL preview | Package a credential-free one-shot NAS/PNG test and manual eips preview. Plan framework and power-button recovery for later approval. | Physically verified on the Paperwhite 2. |
| 2.5B. Persistent native Kindle display | Detached full-screen refresh, power-key rehearsal, timed first trial, and supervised restoration | Initial physical display passed. Recovery fixes packaged for a controlled 120-second retest. |
| 3A. Interactive landscape Kindle dashboard | KOReader/TRMNL landscape display, touch navigation, Todo completion synced with web admin, Calendar and Pomodoro previews, permanent NAS service and SQLite backups | Complete. Physically accepted on the Paperwhite 2 and released in v0.3.0. |
| Salat times strip | Five daily prayer times on the landscape pages, prayer highlighting, web administration preferences, and AlAdhan monthly schedules cached in SQLite | Complete. Physically accepted on Kindle and released in v0.3.1. |
| 3B. External assistant integration | Scoped API tokens, task and deadline synchronization, audit history, and the Muse Briefing widget | Implemented on the feature branch. Physical acceptance and production approval pending. |
| Calendar | Monthly navigation, current-day highlighting, deadline indicators and selected-day agenda | Planned |
| 4. Persistent Pomodoro timer | Server-side state, focus/break defaults, Start/Pause/Resume/Reset/Skip, completed sessions, progress, one-second admin updates, restart recovery and authorized Kindle timer controls | Planned |
| 5. Idle photo frame and photo library | Albums, uploads, e-ink processing, sequential/shuffled playback, configurable idle and rotation intervals and manual return. Suppress idle mode while timer is running or paused. | Planned |
| 6. Device management, synchronization and integration | Enrollment, scoped credentials, revocation, per-device settings, synchronization and end-to-end mode behavior | Planned |
| 7. Deployment hardening and complete testing | Production storage recheck, deployment, backup and restore drills, authentication review and full integration tests | Planned |
| 8. Physical Kindle compatibility and optional native client | Validate browser behavior on PW2 hardware and decide whether an optional native client is necessary | Planned |
