"""JSON-lines logging to stderr and logs/app.jsonl, with secret redaction."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOG_FILE = ROOT / "logs" / "app.jsonl"
LOGGER_NAME = "dada"
_SENSITIVE_KEYS = ("key", "secret", "token", "authorization")
_KEY_RE = re.compile(r"sk-or-[A-Za-z0-9-]+")


def redact(value: Any, key: str = "") -> Any:
    if any(w in key.lower() for w in _SENSITIVE_KEYS):
        return "[redacted]"
    if isinstance(value, str):
        return _KEY_RE.sub("[redacted]", value)
    if isinstance(value, dict):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v, key) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "event": getattr(record, "event", record.name),
        }
        data.update(getattr(record, "fields", {}))
        if not hasattr(record, "event"):
            data["message"] = record.getMessage()
        return json.dumps(redact(data), ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    logger.setLevel(level.upper())
    logger.propagate = False
    fmt = JsonFormatter()
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(LOG_FILE, encoding="utf-8"))
    except OSError:
        pass
    for h in handlers:
        h.setFormatter(fmt)
        logger.addHandler(h)
    return logger


def log_event(name: str, **fields: Any) -> None:
    logging.getLogger(LOGGER_NAME).info(name, extra={"event": name, "fields": fields})
