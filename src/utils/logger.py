"""JSON logger for Lambda functions."""

from __future__ import annotations

import json
import logging
import os
import sys
from contextvars import ContextVar
from typing import Any

_context: ContextVar[dict[str, Any] | None] = ContextVar("_logger_context", default=None)


def bind_context(**kwargs: Any) -> None:
    """Merge key/values into every subsequent log record on this invocation."""
    current = dict(_context.get() or {})
    current.update({k: v for k, v in kwargs.items() if v is not None})
    _context.set(current)


def clear_context() -> None:
    _context.set({})


_STANDARD_ATTRS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        payload.update(_context.get() or {})
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, default=str, separators=(",", ":"))


def get_logger(name: str) -> logging.Logger:
    root = logging.getLogger()
    if not getattr(root, "_json_configured", False):
        for handler in list(root.handlers):
            root.removeHandler(handler)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)
        root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
        root._json_configured = True
    return logging.getLogger(name)
