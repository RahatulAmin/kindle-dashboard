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
