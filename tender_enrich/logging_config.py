from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class OneLineFormatter(logging.Formatter):
    def __init__(self, json_mode: bool):
        super().__init__()
        self.json_mode = json_mode

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage().replace("\r", " ").replace("\n", " ")
        if self.json_mode:
            payload = {
                "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": message,
            }
            for key in ("tenders_read", "enriched", "skipped", "closed_skipped", "imputed", "valid", "invalid", "line", "error_type"):
                if hasattr(record, key):
                    payload[key] = getattr(record, key)
            return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return f"{record.levelname} {record.name}: {message}"


def configure_logging(level: str, log_format: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(OneLineFormatter(log_format.lower() == "json"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
