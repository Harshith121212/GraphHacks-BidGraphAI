from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, HttpUrl, field_validator


class Tender(BaseModel):
    """Normalized public tender data. Unknown source fields remain ``None``."""

    model_config = ConfigDict(extra="forbid")

    tender_id: str
    source_portal: Literal["cppp", "cpwd", "gem", "ireps"]
    title: str
    requesting_unit: str | None = None
    department: str | None = None
    estimated_value: Decimal | None = None
    publish_date: date | None = None
    bid_start_date: datetime | None = None
    bid_end_date: datetime
    emd: Decimal | None = None
    eligibility_text: str | None = None
    tender_url: HttpUrl
    scraped_at: datetime
    raw_payload_path: str

    @field_validator("tender_id", "title")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("raw_payload_path")
    @classmethod
    def normalize_raw_path(cls, value: str) -> str:
        return str(Path(value))
