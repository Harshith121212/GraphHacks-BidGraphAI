from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone

_URL_CREDENTIALS = re.compile(r"(https?://)[^/@\s]+:[^/@\s]+@", re.I)
_URL_QUERY = re.compile(r"(https?://[^\s?#]+)\?[^\s#]+", re.I)


def sanitize(value: str) -> str:
    value = _URL_CREDENTIALS.sub(r"\1[redacted]@", value)
    return _URL_QUERY.sub(r"\1?[redacted]", value).replace("\n", " ").replace("\r", " ")


class StructuredFormatter(logging.Formatter):
    def __init__(self, output_format: str):
        super().__init__()
        self.output_format = output_format

    def format(self, record: logging.LogRecord) -> str:
        message = sanitize(record.getMessage())
        timestamp = datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="seconds")
        fields = {"timestamp": timestamp, "level": record.levelname, "logger": record.name, "message": message}
        for key in ("portal", "found", "new", "duplicates", "errors", "duration_seconds", "status", "error_type"):
            if hasattr(record, key):
                fields[key] = getattr(record, key)
        if self.output_format == "json":
            return json.dumps(fields, ensure_ascii=False, separators=(",", ":"))
        extras = " ".join(f"{key}={fields[key]}" for key in fields if key not in {"timestamp", "level", "logger", "message"})
        return f"{timestamp} {record.levelname} {record.name}: {message}" + (f" {extras}" if extras else "")


def configure_logging(level: str, output_format: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter(output_format))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("httpx").setLevel(logging.WARNING)
