from __future__ import annotations

import json
from importlib.resources import files
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class SeedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    reference_value: int = Field(gt=0)


class TurnoverVariant(SeedModel):
    sample_ratios: list[float] = Field(min_length=3, max_length=3)
    years_considered: int = 3


class NetWorthVariant(SeedModel):
    net_worth_ratio: float = Field(gt=0, le=1)
    positive_required: bool
    solvency_required: bool
    solvency_ratio: float = Field(gt=0, le=1)
    bank_type: str
    validity_months: int = Field(ge=1, le=60)


class RegistrationVariant(SeedModel):
    gst_required: bool
    pan_required: bool
    epfo_required: bool
    esic_required: bool
    udyam_required: bool
    msme_preference: bool


class BoqSeedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    uom: str
    quantity: float = Field(gt=0)
    unit_rate_estimate: int = Field(ge=0)
    technical_specs_summary: str


class BoqVariant(SeedModel):
    trade: str
    items: list[BoqSeedItem] = Field(min_length=1)


class SeedLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    city: str
    state: str
    pincode: str = Field(pattern=r"^\d{6}$")


class DeliveryVariant(SeedModel):
    period_days: int = Field(gt=0)
    location: SeedLocation
    terms: str
    inspection_required: bool
    installation_required: bool
    liquidated_damages_pct: float = Field(ge=0, le=10)
    logistics_notes: str


def load_trade_config() -> tuple[dict[str, str], dict[str, tuple[Decimal, Decimal]]]:
    """Read title-keyword routing and plausible imputation bands from editable JSON."""
    try:
        data = json.loads(files("tender_enrich").joinpath("seed", "trade_keywords.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load seed/trade_keywords.json: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("keywords_to_trade"), dict):
        raise ValueError("seed/trade_keywords.json must define keywords_to_trade")
    keyword_map: dict[str, str] = {}
    for keyword, trade in data["keywords_to_trade"].items():
        if not isinstance(keyword, str) or not keyword.strip() or not isinstance(trade, str):
            raise ValueError("trade keyword mappings must contain non-empty string keywords and trade names")
        keyword_map[keyword.casefold()] = trade

    raw_bands = data.get("imputed_value_bands")
    if not isinstance(raw_bands, dict):
        raise ValueError("seed/trade_keywords.json must define imputed_value_bands")
    bands: dict[str, tuple[Decimal, Decimal]] = {}
    for trade, bounds in raw_bands.items():
        try:
            low, high = Decimal(str(bounds["min"])), Decimal(str(bounds["max"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid imputed value band for {trade!r}") from exc
        if low <= 0 or high < low or high > Decimal("50000000"):
            raise ValueError(f"Imputed value band for {trade!r} must be positive, ascending, and no higher than INR 50,000,000")
        bands[trade] = (low, high)

    valid_trades = {variant.trade for variant in load_seeds()["boq"] if isinstance(variant, BoqVariant)}
    unknown = set(keyword_map.values()) - valid_trades
    if unknown or set(bands) != valid_trades:
        raise ValueError(f"Trade keyword/band configuration does not match BOQ trades: {sorted(unknown)}")
    return keyword_map, bands


SEED_TYPES: dict[str, tuple[type[SeedModel], str, str]] = {
    "avg_turnover": (TurnoverVariant, "T", "avg_turnover.json"),
    "net_worth_solvency": (NetWorthVariant, "N", "net_worth_solvency.json"),
    "registrations": (RegistrationVariant, "R", "registrations.json"),
    "boq": (BoqVariant, "B", "boq.json"),
    "delivery": (DeliveryVariant, "D", "delivery.json"),
}


def load_seeds() -> dict[str, list[SeedModel]]:
    """Load and validate every editable seed file before either CLI command runs."""
    result: dict[str, list[SeedModel]] = {}
    for block, (model_type, prefix, filename) in SEED_TYPES.items():
        try:
            raw = json.loads(files("tender_enrich").joinpath("seed", filename).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not load seed file seed/{filename}: {exc}") from exc
        if not isinstance(raw, list) or len(raw) != 10:
            raise ValueError(f"Seed file seed/{filename} must contain exactly 10 variants")
        try:
            variants = [model_type.model_validate(item) for item in raw]
        except ValidationError as exc:
            raise ValueError(f"Invalid variant in seed/{filename}: {exc}") from exc
        expected_ids = {f"{prefix}{i:02d}" for i in range(1, 11)}
        ids = [variant.id for variant in variants]
        if set(ids) != expected_ids or len(ids) != len(set(ids)):
            raise ValueError(f"Seed file seed/{filename} must use IDs {prefix}01 through {prefix}10 exactly once")
        fingerprints = [variant.model_dump_json(exclude={"id"}) for variant in variants]
        if len(set(fingerprints)) != 10:
            raise ValueError(f"Seed file seed/{filename} variants must be distinct")
        result[block] = variants
    validate_block_specifics(result)
    return result


def validate_block_specifics(seeds: dict[str, list[SeedModel]]) -> None:
    allowed_uom = {"Nos", "Mtr", "Sqm", "Cum", "Kg", "MT", "Set", "Lot", "Ltr", "Rmt"}
    for item in seeds["boq"]:
        variant = item
        assert isinstance(variant, BoqVariant)
        for boq_item in variant.items:
            if boq_item.uom not in allowed_uom:
                raise ValueError(f"Seed {variant.id} has unsupported UoM {boq_item.uom!r}")
    required_trades = {
        "civil works", "electrical", "IT hardware", "furniture", "medical equipment",
        "railway track items", "stationery and consumables", "vehicles", "water supply",
        "housekeeping services",
    }
    actual_trades = {variant.trade for variant in seeds["boq"] if isinstance(variant, BoqVariant)}
    if actual_trades != required_trades:
        raise ValueError("BOQ seed file must contain one variant for each of the 10 documented trades")
