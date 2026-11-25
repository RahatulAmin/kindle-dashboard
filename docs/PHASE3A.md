# Phase 3A landscape dashboard

The interactive dashboard is an opt-in mode in the existing TRMNL plugin. The ordinary TRMNL display actions still use the portrait API. Calendar and Pomodoro are previews for later phases.

## Review artifacts

- [Todo](phase3a-previews/todo.png)
- [Calendar](phase3a-previews/calendar.png)
- [Pomodoro](phase3a-previews/pomodoro.png)
- [Completed and incomplete tasks](phase3a-previews/todo-mixed.png)
- [KOReader plugin ZIP](../kindle-koreader/trmnl-landscape-phase3a.zip)

The PNGs use synthetic tasks and weather. Rebuild them with `.venv/bin/python scripts/preview-kindle-landscape.py`. Rebuild the ZIP with `.venv/bin/python scripts/package-kindle-landscape.py`. The ZIP bundles a minimally patched TRMNL plugin and a separate landscape module. The MIT-licensed upstream source is pinned at [commit a952ab8](https://github.com/usetrmnl/trmnl-koreader/tree/a952ab878640cae30b2f5c1eb5ac3bc1447d6725). Noto Sans is bundled under the SIL Open Font License.

## Architecture

- `backend/app/rendering/landscape_layout.py` supplies the geometry to both the Pillow renderer and API. The renderer emits a 1024 × 758 grayscale PNG and uses the same Unicode font family as portrait. Time comes from America/Toronto. The weather panel reuses the existing Open-Meteo cache.
- `GET /api/kindle/landscape/frame` returns one authenticated, uncacheable JSON response containing the PNG, unique filename, 30-second refresh interval, selected page and page number, and exactly the hit regions for that PNG. Inlining the PNG avoids downloading an image from a separate request that might see different database data. Authenticated clients can supply battery and Wi-Fi observations from KOReader. A temporary Wi-Fi connection is omitted from the panel.
- `PUT /api/kindle/landscape/tasks/{id}/completion` accepts only the desired boolean state and the signed permission attached to that task’s checkbox. A permitted state change is serialized with admin writes and checks sharing, task visibility, task identity, version, and expiry. Repeating an update already reflected in the task succeeds without another write while the permission is valid. Expired or superseded actions that would change state require a fresh frame. The signing key lives in the app process, so restart invalidates existing permissions.
- `kindle-koreader/landscape.lua` uses the upstream image widget with an opt-in gesture handler. It maps KOReader’s rotated coordinates into the currently displayed frame, pauses refresh during suspend, restores the previous orientation on exit, and retains the last image and hit regions if a fetch fails. The session exists in memory and opens on Todo.
- Existing task ordering is position, then ID. Landscape paginates Kindle-visible tasks, including completed tasks, in groups of six. The admin’s task-widget visibility setting applies. Its portrait widget limit continues to apply to the portrait layout.

There is no schema migration in Phase 3A. The live database and Kindle installation were outside development and test scope.

## Install for a controlled test after approval

1. Check out the feature branch in a separate directory on the NAS. Install dependencies there using the project README. Use an isolated SQLite database with a few synthetic tasks, including both completed and hidden tasks. Use a fresh test device key and a free LAN port, such as 8766. Keep the stable NAS instance running on its own port.
2. In the test checkout, set `APP_HOST` to the NAS’s private IPv4 address, `APP_PORT` to the test port, `DATABASE_PATH` to the separate SQLite path, and `TRMNL_ACCESS_TOKEN` to the test key in the checkout’s private `.env`. Start FastAPI normally. Use the admin interface or the fixture below to enable Kindle sharing and seed the test database.
3. On a computer, back up the working `koreader/plugins/trmnl.koplugin/` folder, including any local `apikey.txt`, and a copy of `koreader/settings/trmnl.lua` if present. Close KOReader before copying. Move the stable plugin outside `koreader/plugins/` so KOReader loads only one TRMNL plugin.
4. Extract the ZIP into `koreader/plugins/`. The installed folder is `koreader/plugins/trmnl.koplugin/`. Keep any file-based stable key in the backup during the staging test, since upstream reads `apikey.txt` on startup and gives it precedence over the saved API key.
5. Start KOReader. In **Tools → TRMNL Display → Configure TRMNL**, enter the test key and the test Base URL, in the form `http://<private-LAN-IPv4>:8766`. Select **Start interactive landscape dashboard** from the TRMNL menu. It starts on Todo and refreshes every 30 seconds. Long-press the frame to return to KOReader. If the first fetch fails before a frame opens, use **Stop interactive landscape dashboard**.
6. To roll back, exit the dashboard and KOReader, remove the test plugin folder, restore the backed-up plugin folder and settings, then restart KOReader. Stop the isolated NAS test process.

### Optional synthetic fixture

With the test checkout’s `.env` configured as above, run this before starting the test server. The script requires a fresh database path.

```bash
PYTHONPATH=backend .venv/bin/python - <<'PY'
from app.core.config import Settings
from app.db.database import Database
from app.models.dashboard import Task
from app.schemas.dashboard import Preferences
from app.services.dashboard import save_preferences

settings = Settings()
assert settings.app_port == 8766 and not settings.sqlite_path.exists()
db = Database(settings.sqlite_path)
db.migrate()
with db.sessions() as session:
    save_preferences(session, Preferences(kindle_data_enabled=True))
    for index in range(9):
        session.add(Task(
            title=f"Review sample task {index + 1}", position=index,
            completed=index == 1, kindle_visible=index != 8,
            priority="high" if index == 0 else "normal", description="",
        ))
    session.commit()
db.close()
PY
PYTHONPATH=backend .venv/bin/python -m app
```

### LAN security

The interactive mode accepts a private IPv4 HTTP Base URL and does not follow redirects. Plain HTTP exposes the device key, frames and task changes to anyone who can observe or tamper with LAN traffic. Use a trusted isolated LAN, keep the test port off public proxies and port forwarding, and use a dedicated device key rather than an admin credential. The existing portrait PNG sharing behavior remains in effect for any app instance with Kindle sharing enabled.

## Controlled Paperwhite 2 checklist

- [ ] Open from KOReader in portrait. Confirm the full 1024 × 758 frame fills the screen in landscape with readable accents, date, clock, and weather.
- [ ] Tap all three tabs and test both edges of the bottom bar. Verify the tab highlight and persistent panel. Tap blank space and both disabled timer controls.
- [ ] Complete and reopen a synthetic task. Confirm each change in the test database or admin UI. Check pagination and verify the hidden task never appears.
- [ ] Edit or hide an item in admin while its old frame is visible. Tap the old checkbox and verify it cannot change the updated or hidden item. Confirm synchronization after refresh.
- [ ] Leave Calendar visible through two refresh cycles. Confirm the page stays selected, the clock updates, and no update pop-ups appear.
- [ ] Stop the staging server after a frame is visible. Confirm failed taps and refreshes retain the last frame. Restart staging and confirm refresh resumes.
- [ ] Verify frontlight controls and the physical power button. Suspend, wake, and confirm the dashboard remains responsive. Long-press to exit and verify the prior orientation and normal KOReader navigation.
- [ ] Restore the stable plugin and settings. Confirm the stable portrait dashboard still opens and refreshes.

## Automated verification

Run `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests`. The KOReader harness uses LuaJIT, Lua 5.4, or liblua5.4 and mocked KOReader interfaces. It exercises coordinate mapping, blank taps, tab navigation, double taps during a pending fetch, stale widgets, timeout and render failures, suspend, resume, and orientation restoration. The harness does not emulate the Kindle’s touch hardware or e-ink panel.
