"""Structured JSON-line logging for easy ingestion by ELK / Splunk / Datadog.

Usage::

    from src.utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Portal authenticated", extra={"portal": "pje"})
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------

class JSONFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Merge any structured extras passed via `extra={...}`
        for key in ("portal", "advogado", "client_id", "elapsed_ms", "error"):
            val = getattr(record, key, None)
            if val is not None:
                payload[key] = val

        if record.exc_info and record.exc_info[1]:
            payload["exc"] = str(record.exc_info[1])

        return json.dumps(payload, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_LOG_INITIALISED = False


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger instance.

    Logs are written to *both* stderr (human-readable, for dev) and a
    daily-rotated JSON file under ``data/logs/``.
    """
    global _LOG_INITIALISED

    logger = logging.getLogger(name)

    if not _LOG_INITIALISED:
        _LOG_INITIALISED = True
        _configure_root()

    return logger


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _configure_root() -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # -- Console handler (human-readable, INFO+) --
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root.addHandler(console)

    # -- File handler (JSON, daily rotation) --
    log_dir = Path("data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    file_handler = RotatingFileHandler(
        log_dir / f"execution_{today}.log",
        maxBytes=10 * 1024 * 1024,  # 10 MiB
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(os.getenv("LOG_LEVEL_FILE", "DEBUG"))  # type: ignore[arg-type]
    file_handler.setFormatter(JSONFormatter())
    root.addHandler(file_handler)
