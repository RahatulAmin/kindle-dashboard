import json
import logging
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler

from app.core.config import Settings

logger = logging.getLogger("kindle_dashboard")


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def configure_logging(settings: Settings) -> logging.Handler:
    handler: logging.Handler
    if settings.log_destination == "file":
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            settings.log_dir / "dashboard.jsonl",
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
    else:
        handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logger.setLevel(settings.log_level)
    logger.propagate = False
    logger.addHandler(handler)
    return handler
