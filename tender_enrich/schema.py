from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TurnoverBlock(StrictModel):
    required_avg_annual_turnover: int = Field(ge=0)
    fy_basis: list[str] = Field(min_length=3, max_length=3)
    reference_turnover_by_fy: list[int] = Field(min_length=3, max_length=3)
    currency: Literal["INR"]
    years_considered: Literal[3]


class NetWorthSolvencyBlock(StrictModel):
    min_net_worth: int = Field(ge=0)
    net_worth_must_be_positive: bool
    solvency_certificate_required: bool
    min_solvency_amount: int = Field(ge=0)
    issuing_bank_type: str = Field(min_length=1)
    certificate_validity_months: int = Field(ge=1, le=60)

    @model_validator(mode="after")
    def solvency_covers_net_worth(self) -> "NetWorthSolvencyBlock":
        if self.min_net_worth > self.min_solvency_amount:
            raise ValueError("min_net_worth must not exceed min_solvency_amount")
        return self


class RegistrationEntry(StrictModel):
    required: bool
    number: str | None = None
    code: str | None = None


class UdyamEntry(StrictModel):
    required: bool
    number: str | None = None


class RegistrationsBlock(StrictModel):
    gst: RegistrationEntry
    pan: RegistrationEntry
    epfo: RegistrationEntry
    esic: RegistrationEntry
    udyam: UdyamEntry
    msme_preference: bool
    ids_are_fake: Literal[True]


class BoqItem(StrictModel):
    item_no: int = Field(ge=1)
    description: str = Field(min_length=1)
    uom: Literal["Nos", "Mtr", "Sqm", "Cum", "Kg", "MT", "Set", "Lot", "Ltr", "Rmt"]
    quantity: int | float = Field(gt=0)
    unit_rate_estimate: int | float = Field(gt=0)
    datasheet_ref: str = Field(pattern=r"^TDS-\d{4}\.pdf$")
    technical_specs_summary: str = Field(min_length=1)

    @model_validator(mode="after")
    def enforce_quantity_precision(self) -> "BoqItem":
        if self.uom in {"Nos", "Set", "Lot"} and not isinstance(self.quantity, int):
            raise ValueError(f"{self.uom} quantity must be an integer")
        if self.uom not in {"Nos", "Set", "Lot"} and float(self.quantity) != round(float(self.quantity), 2):
            raise ValueError("continuous UoM quantities must be rounded to 2 places")
        return self


class BoqBlock(StrictModel):
    trade: str = Field(min_length=1)
    trade_source: Literal["keyword", "random"]
    items: list[BoqItem] = Field(min_length=1)


class DeliveryLocation(StrictModel):
    city: str
    state: str
    pincode: str = Field(pattern=r"^\d{6}$")


class DeliveryBlock(StrictModel):
    delivery_period_days: int = Field(gt=0)
    delivery_location: DeliveryLocation
    delivery_terms: str
    inspection_required: bool
    installation_required: bool
    logistics_notes: str
    liquidated_damages_pct: float = Field(ge=0, le=10)


class VariantIds(StrictModel):
    avg_turnover: str = Field(pattern=r"^T\d{2}$")
    net_worth_solvency: str = Field(pattern=r"^N\d{2}$")
    registrations: str = Field(pattern=r"^R\d{2}$")
    boq: str = Field(pattern=r"^B\d{2}$")
    delivery: str = Field(pattern=r"^D\d{2}$")


class SyntheticBlock(StrictModel):
    is_synthetic: Literal[True]
    generator_version: Literal["1.0"]
    seed: int = Field(ge=0, le=0x7FFFFFFFFFFFFFFF)
    value_imputed: bool
    avg_turnover: TurnoverBlock
    net_worth_solvency: NetWorthSolvencyBlock
    registrations: RegistrationsBlock
    boq: BoqBlock
    delivery: DeliveryBlock
    variant_ids: VariantIds


class EnrichedTender(BaseModel):
    """Validates synthetic data while allowing the original scraper fields through."""

    model_config = ConfigDict(extra="allow")
    tender_id: str | None = None
    source_portal: Literal["cppp", "cpwd", "gem", "ireps"] | None = None
    title: str | None = None
    requesting_unit: str | None = None
    department: str | None = None
    estimated_value: Decimal | None = None
    publish_date: date | None = None
    bid_start_date: datetime | None = None
    bid_end_date: datetime | None = None
    emd: Decimal | None = None
    eligibility_text: str | None = None
    tender_url: HttpUrl | None = None
    scraped_at: datetime | None = None
    raw_payload_path: str | None = None
    synthetic: SyntheticBlock

    @field_validator("bid_start_date", "bid_end_date")
    @classmethod
    def bid_dates_must_be_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("bid dates must include a timezone")
        return value
