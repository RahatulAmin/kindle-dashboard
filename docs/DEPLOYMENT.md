# Permanent NAS deployment

Phase 3A runs as the unprivileged account that owns the checkout. The user service runs on port 8765 and a separate user timer takes an online SQLite backup each day. The isolated port 8766 test instance can stay available during cutover.

## Configuration and startup

Use the existing Everything1 checkout and its sibling directories:

| Path relative to the checkout | Purpose |
|---|---|
| `../config/dashboard.env` | Private permanent settings and device key, mode 600 |
| `../data/db/dashboard.sqlite3` | Existing permanent database |
| `../data/photos/`, `../data/processed/` | Media directories |
| `../data/backups/` | Verified daily backups |
| `../data/backups/snapshots/` | Pre-deployment and other manual snapshots |
| `../logs/dashboard.jsonl` | Application logs plus three rotating files |

Install backend and frontend dependencies using the README, then build the frontend with `npm --prefix frontend run build`. Verify that Everything1 is mounted at boot using your system's mount configuration.

Use the following fields in the private settings file. Substitute the NAS’s private IPv4 address and absolute paths. Generate `TRMNL_ACCESS_TOKEN` with `.venv/bin/python -c 'from secrets import token_urlsafe; print(token_urlsafe(32))'` in a private NAS terminal. This key authorizes Kindle reads and the scoped completion endpoint.

```dotenv
APP_HOST=<NAS-private-IPv4>
APP_PORT=8765
PERSISTENT_DATA_DIR=<storage>/data
DATABASE_PATH=<storage>/data/db/dashboard.sqlite3
LOG_DIR=<storage>/logs
LOG_DESTINATION=file
ADMIN_COOKIE_SECURE=false
TRMNL_ACCESS_TOKEN=<generated-device-key>
```

Restrict the service to a trusted LAN. Plain HTTP exposes passwords, the session cookie, the Kindle key, and dashboard contents to network observers. `ADMIN_COOKIE_SECURE=false` is required for the admin login on LAN HTTP. Do not port-forward or expose it publicly. The existing portrait PNG is reachable by LAN clients when Kindle sharing is enabled.

From the checkout, install the supplied systemd user units. This example assumes the deployment paths contain no spaces or shell metacharacters.

```bash
mount_dir=$(findmnt -n -o TARGET --target "$PWD")
test "$mount_dir" != / && mountpoint -q "$mount_dir" || exit 1
storage_dir=$(dirname "$PWD")
install -d -m 700 "$storage_dir/config" "$storage_dir/data/db" \
  "$storage_dir/data/photos" "$storage_dir/data/processed" \
  "$storage_dir/data/backups" "$storage_dir/logs"
install -d -m 700 "$HOME/.config/systemd/user"
for unit in deploy/systemd/kindle-dashboard*; do
  sed -e "s|@PROJECT@|$PWD|g" -e "s|@STORAGE@|$storage_dir|g" \
    -e "s|@MOUNT@|$mount_dir|g" "$unit" > "$HOME/.config/systemd/user/${unit##*/}"
done
systemctl --user daemon-reload
loginctl enable-linger "$(id -un)"
systemctl --user enable --now kindle-dashboard.service kindle-dashboard-backup.timer
```

Linger activates the user manager before login. The application retries if the mount or configured LAN listener is unavailable. The backup job retries after boot-time mount failures. Application file logs rotate at 2 MB with three retained files. The units also rate-limit writes to the system journal.

## Administrator and Kindle

Existing administrator hashes stay in the database. If the admin page reports setup is required, run the following in a private terminal from the permanent checkout. Enter your new password only at the local prompt. Then use a browser to visit `http://<NAS-private-IPv4>:8765/` and sign in.

```bash
set -a
. ../config/dashboard.env
set +a
PYTHONPATH=backend .venv/bin/python -m app.setup_admin admin
```

Use **TRMNL Display → Configure TRMNL** in KOReader. Set Base URL to `http://<NAS-private-IPv4>:8765`, set API Key to the private persistent token, and leave the MAC address automatic with header name `ID`. If an `apikey.txt` file is present in the plugin folder, it overrides the dialog key at startup. Use only one key source. The [installation ZIP and orientation notes](PHASE3A.md) describe the interactive plugin.

## Management and backups

```bash
systemctl --user status kindle-dashboard.service
systemctl --user restart kindle-dashboard.service
journalctl --user -u kindle-dashboard.service -n 50
systemctl --user list-timers kindle-dashboard-backup.timer
systemctl --user start kindle-dashboard-backup.service
journalctl --user -u kindle-dashboard-backup.service -n 50
```

The timer runs daily at 03:30 America/Toronto and catches up after downtime. SQLite’s online backup API writes to a private temporary file and checks integrity before replacing that day’s backup. The 14 newest daily files are retained. Timestamped snapshots and older legacy backup names are outside the daily rotation. See [SQLite restore and rollback](DATABASE.md).

## Rollback

Stop the permanent user service and backup timer first:

```bash
systemctl --user stop kindle-dashboard.service kindle-dashboard-backup.timer kindle-dashboard-backup.service
```

To use the isolated test instance during rollback, point KOReader to the previously saved port 8766 Base URL and test API key. To roll application code back while keeping the permanent database, use a separate stable checkout at `v0.2.0` with a built frontend. Load the permanent settings shown above, then run `PYTHONPATH=backend .venv/bin/python -m app` in that checkout. Both versions use database revision `0002`. Restore a pre-deployment snapshot only when you want to discard database changes made after it was taken. The temporary test instance can continue on port 8766 throughout.
