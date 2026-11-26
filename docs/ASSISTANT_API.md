# External assistant API

Muse and other clients can use this API independently of the web admin and Kindle plugin. Routes are relative to the dashboard server. Use HTTPS or a trusted encrypted connection such as an SSH tunnel or private VPN for Bearer credentials. Keep the server on a trusted LAN. This feature requires no public ingress, port forwarding, CORS change, or external cloud service.

The live server generates its complete contract at `/openapi.json`. The [external-client OpenAPI contract](assistant-openapi.json) covers the scoped routes in this guide.

## Provision a token

Run the CLI in the checkout with its Python environment activated and the intended dashboard storage configuration loaded. For a systemd deployment, use the private environment file used by the service. The database must be initialized to revision `0004`. Keep the token out of shell history, logs, screenshots, Git, and browser bundles.

```bash
export PYTHONPATH=backend
python -m app.api_tokens create muse \
  --scopes tasks:read,tasks:write,deadlines:read,deadlines:write,briefing:read,briefing:write \
  --expires-at 2027-06-01T00:00:00Z
python -m app.api_tokens list
python -m app.api_tokens revoke 1
```

Supply `--expires-at` as a future ISO 8601 timestamp with an explicit timezone. Omitting it creates a token without an automatic expiration. Creation prints the credential once. SQLite retains the SHA-256 hash and metadata. Listing returns the ID, name, scopes, creation time, last successful scoped use, expiration, and revocation status. The ID is the argument to `revoke`.

To rotate, issue a new token with the intended scopes and expiry, install it in the client's secret store, verify a scoped read, and revoke the old ID. Revocation takes effect for subsequent authorized requests. Revoke a lost or exposed credential immediately and issue a replacement.

## Authentication and scopes

Send `Authorization: Bearer <token>` on every request. A token grants access to the corresponding collection across the dashboard. `source` separates external identities for synchronization and does not limit the token's permissions.

| Scope | Access |
| --- | --- |
| `tasks:read` | List and retrieve tasks |
| `tasks:write` | Create, upsert, edit, complete, and reopen tasks |
| `tasks:delete` | Delete tasks |
| `deadlines:read` | List and retrieve deadlines |
| `deadlines:write` | Create, upsert, edit, archive, complete, and reopen deadlines |
| `deadlines:delete` | Delete deadlines |
| `briefing:read` | Get the current briefing |
| `briefing:write` | Replace the current briefing |

Cookie-authenticated administrators keep their existing access and submit the existing CSRF header on mutations. When a Bearer credential is supplied on a scoped route, it takes precedence over cookies. Settings, prayer preferences, audit history, authentication and Kindle device access use their existing mechanisms or administrator sign-in.

## Tasks and deadlines

| Method and route | Scope | Result |
| --- | --- | --- |
| `GET /api/v1/tasks` | `tasks:read` | 200, task array ordered by position and ID |
| `GET /api/v1/tasks/{id}` | `tasks:read` | 200, one task |
| `POST /api/v1/tasks` | `tasks:write` | 201 on creation, 200 for existing identity |
| `PUT /api/v1/tasks/{id}` | `tasks:write` | 200, updated task |
| `DELETE /api/v1/tasks/{id}` | `tasks:delete` | 204, no response body |
| `GET /api/v1/deadlines` | `deadlines:read` | 200, ordered by date, time, and ID, including archived entries |
| `GET /api/v1/deadlines/{id}` | `deadlines:read` | 200, one deadline |
| `POST /api/v1/deadlines` | `deadlines:write` | 201 on creation, 200 for existing identity |
| `PUT /api/v1/deadlines/{id}` | `deadlines:write` | 200, updated deadline |
| `DELETE /api/v1/deadlines/{id}` | `deadlines:delete` | 204, no response body |

All successful JSON bodies use `{"data": ...}`. Item IDs are integers. List filters combine with AND.

| Filter | Type and meaning |
| --- | --- |
| `completed` | Boolean, matches completed or open entries |
| `due_from`, `due_to` | Inclusive ISO dates, `YYYY-MM-DD`. Undated tasks are excluded when either bound is supplied. |
| `source`, `external_ref` | Exact strings. A list request may filter by either or both. |
| `updated_since` | Inclusive ISO 8601 timestamp with timezone. Deduplicate boundary results by item ID and `updated_at`. |

Creation requires a nonblank `title` of at most 160 characters. Both collections accept `description` up to 4,000 characters, `priority` of `low`, `normal`, or `high`, and booleans `completed` and `kindle_visible`. Defaults for a token-authenticated creation are empty description, normal priority, open, and hidden from Kindle. Tasks accept nullable `due_date` and integer `position` from 0 to 999999 (default 0). Deadlines require `due_date`, accept a nullable local Toronto `due_time` without an offset, and default `archived` to false. Deadlines include the read-only `days_until` field. Responses include `id`, `created_at`, `updated_at`, and the nullable external identity fields.

### Synchronization and conflicts

- Use a stable pair such as `"source": "muse", "external_ref": "task-42"`. Both values are required together and may be up to 80 and 160 characters respectively. Pairs are unique per collection. A POST with a pair atomically creates or updates the matching record, keeping its ID and creation time. An unpaired POST creates a fresh entry on each request.
- Bearer PUT and paired POST preserve omitted fields. Two explicit nulls clear an external identity on PUT. Null may also clear a nullable date or time. The admin's normal edit form preserves external identity.
- Send the returned `updated_at` as `expected_updated_at` when modifying an existing record. A conflicting stale write returns 409 and includes the latest version in `ETag` and the item URL in a `Link` with `rel="latest-version"`. Retrieve the item, reconcile the user's intent, and submit again with the latest version. The version can also be supplied as a DELETE query parameter.
- An upsert that would change `completed`, `kindle_visible`, `position`, or `archived` requires the current version. Any token request that changes `completed` on an existing item requires the current version. Complete or reopen using PUT with `completed: true` or `false` and the current version. This prevents retries from undoing a Kindle completion. An already-applied retry succeeds without changing `updated_at` or appending an audit entry.

### Curl examples

```bash
export DASHBOARD_URL=https://dashboard.example.internal
read -rsp 'Dashboard token: ' DASHBOARD_TOKEN
printf '\n'
api() {
  printf 'Authorization: Bearer %s\n' "$DASHBOARD_TOKEN" |
    curl --silent --show-error --fail-with-body --header @- "$@"
}

api --get --data-urlencode source=muse --data-urlencode completed=false \
  "$DASHBOARD_URL/api/v1/tasks"

api --json '{"title":"Review agenda","source":"muse","external_ref":"task-42","due_date":"2027-01-12"}' \
  "$DASHBOARD_URL/api/v1/tasks"

api --request PUT --json '{"completed":true,"expected_updated_at":"2026-11-26T13:30:00.000000+00:00"}' \
  "$DASHBOARD_URL/api/v1/tasks/42"

api --json '{"title":"Submit report","due_date":"2027-01-12","due_time":"15:00:00","source":"muse","external_ref":"due-3"}' \
  "$DASHBOARD_URL/api/v1/deadlines"
```

Example task response:

```json
{
  "data": {
    "id": 42,
    "title": "Review agenda",
    "description": "",
    "priority": "normal",
    "completed": false,
    "kindle_visible": false,
    "due_date": "2027-01-12",
    "position": 0,
    "source": "muse",
    "external_ref": "task-42",
    "created_at": "2026-11-26T13:30:00.000000+00:00",
    "updated_at": "2026-11-26T13:30:00.000000+00:00"
  }
}
```

## Briefing

| Method and route | Scope | Result |
| --- | --- | --- |
| `GET /api/v1/briefing` | `briefing:read` | 200, current briefing or `{"data":null}` |
| `POST /api/v1/briefing` | `briefing:write` | 200, replaces the singleton briefing |

POST requires a printable single-line title of 1 to 80 characters and an array of zero to six printable single-line strings. Each supplied line must be 1 to 100 characters after trimming. The response includes `updated_at`. An identical replacement leaves the timestamp and audit history as they were. A browser administrator can preview and clear the content under **Briefing**. Clearing is an administrator-only action. To render it on the landscape **Muse** page, enable **Briefing** in **Widgets** and enable Kindle sharing. Briefing is off by default. The tab badge counts priorities and updates on every frame. Long text wraps over one or more pages. Install the [Muse landscape plugin ZIP](../kindle-koreader/trmnl-landscape-muse.zip) for the Muse and local suspend buttons. Older clients continue to receive the three-tab frame.

```bash
api --json '{"title":"Muse Briefing","lines":["Review the agenda before 2 PM.","Workshop confirmation is due Friday."]}' \
  "$DASHBOARD_URL/api/v1/briefing"
api "$DASHBOARD_URL/api/v1/briefing"
unset DASHBOARD_TOKEN
```

```json
{
  "data": {
    "title": "Muse Briefing",
    "lines": ["Review the agenda before 2 PM.", "Workshop confirmation is due Friday."],
    "updated_at": "2026-11-26T13:30:00.000000+00:00"
  }
}
```

### Physical Kindle staging check

Install the replacement ZIP in the existing KOReader plugin location and use the staging server and staging device credential. Keep a copy of the existing plugin and settings for rollback. On the Kindle, tap all four tabs, open a multipage Muse briefing, and leave it open through a refresh. Tap Todo to return to the last Todo page. Tap the on-screen power region, then press the physical power button to wake the device. Confirm the same page is visible and refresh resumes. Long-press to exit and confirm that the prior orientation is restored.

The plugin requests the expanded Kindle frame with `ui=2`. The power region invokes KOReader's local [suspend mechanism](https://github.com/koreader/koreader/blob/master/frontend/ui/uimanager.lua). The server only delivers the image and touch region.

## Errors, retries, and audit

Errors use `{"error":{"code":"http_409","message":"Entry version has changed. Retrieve the latest state and retry."}}`.

| Status | Client action |
| --- | --- |
| 401 | Check credential, expiration, and revocation. Replace it if needed. |
| 403 | Issue a token with the required scope if the client is authorized to perform the operation. |
| 404 | The item is missing. After an uncertain DELETE, use a read to confirm it was removed. |
| 409 | Follow the latest-version link if present. Compare the current state before retrying. |
| 413 | Reduce the body. Scoped JSON write operations are capped at 32 KiB. |
| 422 | Correct the request fields or query parameters. |
| 429 | Honor `Retry-After`. A process allows 120 scoped Bearer attempts per client address and 1,200 total per minute. |
| 5xx or transport timeout | Retry reads with backoff. For writes, read the current state or retry the same versioned request or paired upsert. An unpaired POST has no deduplication. |

Administrator **API Audit** shows successful token mutations with UTC time, token ID and name, action, resource, and changed field names. It can be filtered by token ID, action, and UTC date. No-op retries do not produce audit entries. Audit records and mutations commit as one SQLite transaction.

## Production deployment and rollback

1. After physical acceptance and explicit approval, retain the currently deployed commit and frontend bundle and verify the approved release SHA. Build the new frontend away from the production static directory. Rehearse `0003 → 0004` and rollback on a private backup copy.
2. During the maintenance window, using the production service's private environment, create and check a mode-600 pre-migration snapshot using `PYTHONPATH=backend python -m app.backup_database --snapshot`. Require SQLite `PRAGMA integrity_check` to return `ok` and confirm revision `0003`. Preserve the service environment and device credential.
3. Stop the dashboard service for cutover, install the approved backend and frontend, and start only the permanent dashboard service. Startup applies `0004`. Verify health, administrator sign-in, settings, prayer times, Kindle frames, and the unchanged backup timer. Enable Briefing and issue the production Muse credential only when intended. The plugin uses the existing landscape frame protocol.
4. To roll back, stop the dashboard and pause the backup timer and any active backup job. Snapshot the current `0004` database before downgrading. With the Phase 3B code and production environment still in place, run `alembic -c backend/alembic.ini downgrade 0003`. This retains ordinary task, deadline, and preference edits and removes assistant tokens, audit records, briefing data, and external identifiers. Alternatively, preserve the current database and its journal sidecars together, verify the pre-migration snapshot, and restore that copy with mode 600. Restoring a snapshot discards changes since it was taken. Restore the prior backend and frontend, start the service and backup timer, and confirm health and revision `0003`. See [database backup and restoration](DATABASE.md).
