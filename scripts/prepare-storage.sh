#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
PYTHONPATH="$project_dir/backend" .venv/bin/python - <<'PY'

import os

from app.core.config import DEFAULT_STORAGE, Settings

settings = Settings()
storage = DEFAULT_STORAGE.resolve()
data = settings.persistent_data_dir.resolve()
logs = settings.log_dir.resolve()
database = settings.sqlite_path
if not data.is_relative_to(storage) or not logs.is_relative_to(storage):
    raise SystemExit("Data and log directories must be under the Kindle Dashboard storage directory")
if not database.is_relative_to(data):
    raise SystemExit("DATABASE_PATH must be under PERSISTENT_DATA_DIR for the Compose bind mount")
for directory in dict.fromkeys((database.parent, data / "db", data / "photos", data / "processed",
                  data / "backups", logs)):
    directory.mkdir(parents=True, exist_ok=True)
    if not os.access(directory, os.W_OK | os.X_OK):
        raise SystemExit(f"Storage directory is not writable: {directory}")
    print(directory)
PY
