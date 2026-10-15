from __future__ import annotations

import hashlib
import math
import random
import re
import string
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from .schema import SyntheticBlock
from .seeds import BoqVariant, DeliveryVariant, NetWorthVariant, RegistrationVariant, SeedModel, TurnoverVariant
from .storage import normalize_bid_dates

BASE36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
def derived_seed(global_seed: int, source_portal: Any, tender_id: Any) -> int:
    material = f"{global_seed}\0{source_portal or ''}\0{tender_id or ''}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big") & 0x7FFFFFFFFFFFFFFF


def _rounded_inr(value: float | Decimal) -> int:
    amount = Decimal(str(value))
    step = Decimal("100000") if amount >= Decimal("100000000") else (
        Decimal("10000") if amount >= Decimal("10000") else Decimal("1")
    )
    return int((amount / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step)


def _choose_variant(variants: list[SeedModel], value: Decimal, rng: random.Random) -> SeedModel:
    # A soft logarithmic weight favors nearby scale references without excluding any variant.
    weights = [math.exp(-0.32 * abs(math.log(float(value) / variant.reference_value))) for variant in variants]
    return rng.choices(variants, weights=weights, k=1)[0]


def _impute_value(
    rng: random.Random,
    minimum: Decimal,
    maximum: Decimal,
    matched_trade: str | None,
    trade_value_bands: dict[str, tuple[Decimal, Decimal]],
) -> Decimal:
    log_value = rng.uniform(math.log(float(minimum)), math.log(float(maximum)))
    value = Decimal(str(math.exp(log_value)))
    if matched_trade is not None:
        trade_min, trade_max = trade_value_bands[matched_trade]
        value = min(max(value, trade_min), trade_max)
    return value


def _fy_basis(today: date | None = None) -> list[str]:
    today = today or date.today()
    latest_start = today.year - 1 if today.month >= 4 else today.year - 2
    return [f"{year}-{(year + 1) % 100:02d}" for year in range(latest_start - 2, latest_start + 1)]


def _base36_char(value: int) -> str:
    return BASE36[value]


def gst_checksum(first_14: str) -> str:
    """Return the GSTIN checksum character for a 14-character prefix."""
    total = 0
    factor = 2
    for char in reversed(first_14.upper()):
        product = BASE36.index(char) * factor
        total += (product // 36) + (product % 36)
        factor = 1 if factor == 2 else 2
    return _base36_char((36 - total % 36) % 36)


def fake_gstin(pan: str, rng: random.Random) -> str:
    state = f"{rng.randint(1, 37):02d}"
    prefix = state + pan + str(rng.randint(1, 9)) + "Z"
    correct = gst_checksum(prefix)
    invalid = BASE36[(BASE36.index(correct) + rng.randint(1, 35)) % 36]
    return prefix + invalid


def _fake_pan(rng: random.Random) -> str:
    return "ZZZ" + "".join(rng.choice(string.ascii_uppercase) for _ in range(2)) + f"{rng.randint(0, 9999):04d}" + rng.choice(string.ascii_uppercase)


def generate_registrations(variant: RegistrationVariant, rng: random.Random, tender_seed: int) -> dict[str, Any]:
    pan = _fake_pan(rng)
    return {
        "gst": {"required": variant.gst_required, "number": fake_gstin(pan, rng)},
        "pan": {"required": variant.pan_required, "number": pan},
        "epfo": {"required": variant.epfo_required, "code": f"ZZ/ZZZ/{tender_seed:016X}/000/0000000"},
        "esic": {"required": variant.esic_required, "code": "99999" + f"{rng.randrange(10**12):012d}"},
        "udyam": {"required": variant.udyam_required, "number": f"UDYAM-ZZ-00-{tender_seed:019d}"},
        "msme_preference": variant.msme_preference,
        "ids_are_fake": True,
    }


def match_trade(title: Any, keyword_map: dict[str, str]) -> str | None:
    text = str(title or "").casefold()
    for keyword, trade in keyword_map.items():
        escaped = re.escape(keyword.casefold())
        left = r"(?<!\w)" if keyword[:1].isalnum() else ""
        right = r"(?!\w)" if keyword[-1:].isalnum() else ""
        if re.search(left + escaped + right, text):
            return trade
    return None


def _generate_boq(variant: BoqVariant, value: Decimal, rng: random.Random, trade_source: str) -> dict[str, Any]:
    raw_total = sum(Decimal(str(item.quantity)) * Decimal(item.unit_rate_estimate) for item in variant.items)
    target_total = value * Decimal(str(rng.uniform(0.90, 1.10)))
    factor = target_total / raw_total
    items = []
    for index, item in enumerate(variant.items, 1):
        scaled_quantity = Decimal(str(item.quantity)) * factor
        if item.uom in {"Nos", "Set", "Lot"}:
            quantity: int | float = max(1, int(scaled_quantity.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))
        else:
            quantity = float(max(Decimal("0.01"), scaled_quantity.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)))
        items.append({
            "item_no": index,
            "description": item.description,
            "uom": item.uom,
            "quantity": quantity,
            "unit_rate_estimate": item.unit_rate_estimate,
            "datasheet_ref": f"TDS-{rng.randint(1, 9999):04d}.pdf",
            "technical_specs_summary": item.technical_specs_summary,
        })

    current_total = sum(Decimal(str(item["quantity"])) * item["unit_rate_estimate"] for item in items)
    if current_total > 0:
        rate_factor = target_total / current_total
        for generated, source in zip(items, variant.items):
            generated["unit_rate_estimate"] = max(
                1,
                int((Decimal(source.unit_rate_estimate) * rate_factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
            )
        last = items[-1]
        other_total = sum(
            Decimal(str(item["quantity"])) * item["unit_rate_estimate"] for item in items[:-1]
        )
        adjusted_last_rate = (target_total - other_total) / Decimal(str(last["quantity"]))
        if adjusted_last_rate >= 1:
            last["unit_rate_estimate"] = max(1, int(adjusted_last_rate.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))

    total = sum(Decimal(str(item["quantity"])) * item["unit_rate_estimate"] for item in items)
    if value > 0 and not Decimal("0.85") <= total / value <= Decimal("1.15"):
        # Very small values can make rounded pack counts dominate; use one scaled line.
        item = items[0]
        item["quantity"] = 1 if item["uom"] in {"Nos", "Set", "Lot"} else 1.0
        item["unit_rate_estimate"] = float(target_total / Decimal(str(item["quantity"])))
        items = [item]
    return {"trade": variant.trade, "trade_source": trade_source, "items": items}


def enrich_tender(
    tender: dict[str, Any],
    *,
    global_seed: int,
    default_value_min: Decimal,
    default_value_max: Decimal,
    seeds: dict[str, list[SeedModel]],
    keyword_map: dict[str, str],
    trade_value_bands: dict[str, tuple[Decimal, Decimal]],
) -> dict[str, Any]:
    tender = normalize_bid_dates(tender)
    key_seed = derived_seed(global_seed, tender.get("source_portal"), tender.get("tender_id"))
    rng = random.Random(key_seed)
    matched_trade = match_trade(tender.get("title"), keyword_map)
    # estimated_value is synthetic for every record. Always draw a stable, per-tender
    # amount, even when the source supplied one, and enforce the ₹5 crore ceiling.
    cap = Decimal("50000000")
    minimum = min(default_value_min, cap)
    maximum = min(default_value_max, cap)
    if minimum <= 0 or maximum < minimum:
        raise ValueError("Estimated value bounds must be positive, ascending, and no higher than INR 50,000,000")
    value = _impute_value(rng, minimum, maximum, matched_trade, trade_value_bands)
    value = min(cap, max(minimum, Decimal(_rounded_inr(value))))
    tender["estimated_value"] = int(value)
    imputed = True

    turnover = _choose_variant(seeds["avg_turnover"], value, rng)
    networth = _choose_variant(seeds["net_worth_solvency"], value, rng)
    registrations = _choose_variant(seeds["registrations"], value, rng)
    if matched_trade is None:
        boq = _choose_variant(seeds["boq"], value, rng)
        trade_source = "random"
    else:
        trade_variants = [variant for variant in seeds["boq"] if isinstance(variant, BoqVariant) and variant.trade == matched_trade]
        if not trade_variants:
            raise ValueError(f"No BOQ variant configured for matched trade {matched_trade!r}")
        boq = _choose_variant(trade_variants, value, rng)
        trade_source = "keyword"
    delivery = _choose_variant(seeds["delivery"], value, rng)
    assert isinstance(turnover, TurnoverVariant)
    assert isinstance(networth, NetWorthVariant)
    assert isinstance(registrations, RegistrationVariant)
    assert isinstance(boq, BoqVariant)
    assert isinstance(delivery, DeliveryVariant)

    required_turnover = _rounded_inr(value * Decimal(str(rng.uniform(0.25, 0.35) * rng.uniform(0.90, 1.10))))
    sample_values = [
        max(0, _rounded_inr(required_turnover * ratio * rng.uniform(0.93, 1.07)))
        for ratio in turnover.sample_ratios
    ]
    net_worth_amount = _rounded_inr(value * Decimal(str(networth.net_worth_ratio * rng.uniform(0.90, 1.10))))
    solvency_amount = max(net_worth_amount, _rounded_inr(value * Decimal(str(0.40 * rng.uniform(0.90, 1.10)))))
    delivery_data = {
        "delivery_period_days": delivery.period_days,
        "delivery_location": delivery.location.model_dump(),
        "delivery_terms": delivery.terms,
        "inspection_required": delivery.inspection_required,
        "installation_required": delivery.installation_required,
        "logistics_notes": delivery.logistics_notes,
        "liquidated_damages_pct": delivery.liquidated_damages_pct,
    }
    synthetic = {
        "is_synthetic": True,
        "generator_version": "1.0",
        "seed": key_seed,
        "value_imputed": imputed,
        "avg_turnover": {
            "required_avg_annual_turnover": required_turnover,
            "fy_basis": _fy_basis(),
            "reference_turnover_by_fy": sample_values,
            "currency": "INR",
            "years_considered": 3,
        },
        "net_worth_solvency": {
            "min_net_worth": net_worth_amount,
            "net_worth_must_be_positive": networth.positive_required,
            "solvency_certificate_required": networth.solvency_required,
            "min_solvency_amount": solvency_amount,
            "issuing_bank_type": networth.bank_type,
            "certificate_validity_months": networth.validity_months,
        },
        "registrations": generate_registrations(registrations, rng, key_seed),
        "boq": _generate_boq(boq, value, rng, trade_source),
        "delivery": delivery_data,
        "variant_ids": {
            "avg_turnover": turnover.id,
            "net_worth_solvency": networth.id,
            "registrations": registrations.id,
            "boq": boq.id,
            "delivery": delivery.id,
        },
    }
    # Validate the new blocks before returning a record to the writer.
    SyntheticBlock.model_validate(synthetic)
    return {**tender, "synthetic": synthetic}
