"""Structured logging: one JSON object per line, tagged with the current request id.

Usage stays standard:
    logger.info("Booking created", extra={"booking_id": booking.id, "user_id": user.id})
Every `extra` key becomes a top-level JSON field.
"""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

# Set per request by RequestIdMiddleware; None outside a request (e.g. management commands)
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Attributes every LogRecord has; anything else on a record came from `extra`
_STANDARD_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {
    "message",
    "asctime",
    "request_id",
}


class RequestIdFilter(logging.Filter):
    """Adds `record.request_id` so the plain-text format can show it too."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, UTC)
        data = {
            "timestamp": timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                data[key] = value
        if record.exc_info:
            data["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str)  # default=str: Decimal, UUID, datetime, enums
