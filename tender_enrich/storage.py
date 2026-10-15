from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any, Iterator

from pydantic import ValidationError

from .schema import EnrichedTender

TENDER_FIELDS = (
    "tender_id", "source_portal", "title", "requesting_unit", "department", "estimated_value",
    "publish_date", "bid_start_date", "bid_end_date", "emd", "eligibility_text", "tender_url",
    "scraped_at", "raw_payload_path",
)
IST = ZoneInfo("Asia/Kolkata")


def _normalize_bid_datetime(value: Any, *, field: str) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    elif isinstance(value, str):
        text = value.strip()
        date_only = len(text) == 10 and text[4] == "-" and text[7] == "-"
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return value
        if date_only and field == "bid_end_date":
            parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
    else:
        return value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=IST)
    return parsed.astimezone(timezone.utc).isoformat()


def is_closed(tender: dict[str, Any], *, now: datetime | None = None) -> bool:
    raw_end = tender.get("bid_end_date")
    if not raw_end:
        return False
    normalized = _normalize_bid_datetime(raw_end, field="bid_end_date")
    if normalized is None:
        return False
    try:
        end = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        current = current.replace(tzinfo=timezone.utc)
    return end < current.astimezone(timezone.utc)


def normalize_bid_dates(tender: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(tender)
    for field in ("bid_start_date", "bid_end_date"):
        normalized[field] = _normalize_bid_datetime(normalized.get(field), field=field)
    return normalized


def read_jsonl(path: Path) -> Iterator[tuple[int, dict[str, Any] | None]]:
    """Yield each line number and a dict, or ``None`` for malformed lines."""
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("JSON line must contain an object")
                for field in TENDER_FIELDS:
                    value.setdefault(field, None)
                yield line_number, normalize_bid_dates(value)
            except (json.JSONDecodeError, ValueError):
                yield line_number, None


def atomic_write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as temporary:
            temporary_path = temporary.name
            for record in records:
                temporary.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
                temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass


def validate_record(record: dict[str, Any]) -> None:
    EnrichedTender.model_validate(record)


def validation_error_message(record: dict[str, Any]) -> str | None:
    try:
        validate_record(record)
    except ValidationError as exc:
        return str(exc).replace("\n", " ")
    return None
