from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from .cppp import parse_date
from .models import Tender

LOG = logging.getLogger("tenderscrape.storage")
TenderKey = tuple[str, str]


def _load_active(path: Path, today: date) -> dict[TenderKey, dict]:
    existing: dict[TenderKey, dict] = {}
    if not path.exists():
        return existing
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            end = datetime.fromisoformat(row["bid_end_date"]).date()
            title = row.get("title", "")
            if end < today or parse_date(title) is not None or re.search(r"cancel+|retender", title, re.I):
                continue
            existing[(row["source_portal"], row["tender_id"])] = row
        except (ValueError, KeyError, TypeError):
            LOG.warning("Skipping malformed existing JSONL row")
    return existing


def inspect_records(records: Iterable[Tender], existing: dict[TenderKey, dict], *, today: date | None = None):
    today = today or date.today()
    seen: set[TenderKey] = set()
    unique: list[Tender] = []
    duplicates: dict[str, int] = {}
    new_counts: dict[str, int] = {}
    for record in records:
        if record.bid_end_date.date() < today:
            continue
        key = (record.source_portal, record.tender_id)
        if key in seen:
            duplicates[record.source_portal] = duplicates.get(record.source_portal, 0) + 1
            continue
        seen.add(key)
        unique.append(record)
        if key in existing:
            duplicates[record.source_portal] = duplicates.get(record.source_portal, 0) + 1
        else:
            new_counts[record.source_portal] = new_counts.get(record.source_portal, 0) + 1
    return unique, new_counts, duplicates


def atomic_write_jsonl(path: Path, records: Iterable[Tender], *, today: date | None = None):
    today = today or date.today()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_active(path, today)
    unique, new_counts, duplicates = inspect_records(records, existing, today=today)
    for record in unique:
        existing[(record.source_portal, record.tender_id)] = record.model_dump(mode="json")

    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            for row in existing.values():
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return new_counts, duplicates
