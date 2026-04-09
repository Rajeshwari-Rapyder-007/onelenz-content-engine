import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

from .context import request_context


class JSONFormatter(logging.Formatter):
    """Formats log records as structured JSON with request context."""

    def format(self, record: logging.LogRecord) -> str:
        ctx = request_context()

        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": ctx.service_name,
        }

        # Attach request context if available
        if ctx.request_id:
            log_entry["request_id"] = ctx.request_id
        if ctx.user_id:
            log_entry["user_id"] = ctx.user_id
        if ctx.session_id:
            log_entry["session_id"] = ctx.session_id
        if ctx.endpoint:
            log_entry["endpoint"] = f"{ctx.method} {ctx.endpoint}"

        # Attach exception info if present
        if record.exc_info and record.exc_info[1]:
            log_entry["error"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
            }

        # Attach extra fields passed via logger.info("msg", extra={"key": "val"})
        for key, val in record.__dict__.items():
            if key.startswith("x_"):
                log_entry[key[2:]] = val

        return json.dumps(log_entry, default=str)


class DevFormatter(logging.Formatter):
    """Human-readable format for local development."""

    COLORS = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[35m",  # magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        ctx = request_context()
        color = self.COLORS.get(record.levelname, self.RESET)

        parts = [
            f"{color}{record.levelname:<8}{self.RESET}",
            f"[{record.name}]",
            record.getMessage(),
        ]

        context_parts = []
        if ctx.request_id:
            context_parts.append(f"req={ctx.request_id[:8]}")
        if ctx.user_id:
            context_parts.append(f"user={ctx.user_id[:8]}")
        if ctx.endpoint:
            context_parts.append(f"{ctx.method} {ctx.endpoint}")

        if context_parts:
            parts.append(f"({' | '.join(context_parts)})")

        if record.exc_info and record.exc_info[1]:
            parts.append(f"\n  {type(record.exc_info[1]).__name__}: {record.exc_info[1]}")

        return " ".join(parts)


def setup_logging(service_name: str) -> None:
    """Initialize logging for a service. Call once in main.py."""
    env = os.getenv("ENVIRONMENT", "dev")
    log_level = os.getenv("LOG_LEVEL", "DEBUG" if env == "dev" else "INFO")

    handler = logging.StreamHandler(sys.stdout)

    if env == "dev":
        handler.setFormatter(DevFormatter())
    else:
        handler.setFormatter(JSONFormatter())

    # Configure root logger
    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()
    root.addHandler(handler)

    # Suppress noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance. Use module name as the logger name.

    Usage:
        logger = get_logger(__name__)
        logger.info("User logged in")
        logger.error("Failed to hash password", exc_info=True)
        logger.info("Deal updated", extra={"x_deal_id": "123", "x_action": "stage_change"})
    """
    return logging.getLogger(name)
