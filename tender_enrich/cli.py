from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .config import Settings
from .generator import enrich_tender
from .logging_config import configure_logging
from .schema import EnrichedTender
from .seeds import load_seeds, load_trade_config
from .storage import atomic_write_jsonl, is_closed, read_jsonl

LOG = logging.getLogger("tender_enrich")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tender_enrich", description="Add deterministic synthetic tender requirements")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="enrich JSONL tender records")
    run.add_argument("--input", type=Path)
    run.add_argument("--output", type=Path)
    run.add_argument("--seed", type=int)
    run.add_argument("--limit", type=int)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--drop-closed", action="store_true", help="skip tenders whose bid end date is before now")
    validate = subparsers.add_parser("validate", help="validate enriched JSONL records")
    validate.add_argument("--input", type=Path)
    return parser


def _same_file(input_path: Path, output_path: Path) -> bool:
    return input_path.resolve() == output_path.resolve()


def _run(args: argparse.Namespace, settings: Settings, seeds: dict, keyword_map: dict, trade_value_bands: dict) -> int:
    input_path = args.input or settings.input_path
    output_path = args.output or settings.output_path
    seed = settings.seed if args.seed is None else args.seed
    if args.limit is not None and args.limit < 1:
        raise ValueError("--limit must be at least 1")
    if _same_file(input_path, output_path):
        raise ValueError("input and output paths must differ; input is never modified")
    if not input_path.is_file():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")

    input_records: list[dict[str, Any]] = []
    lines_read = skipped = closed_skipped = 0
    for line_number, tender in read_jsonl(input_path):
        lines_read = line_number
        if tender is None:
            skipped += 1
            LOG.warning("Skipping malformed JSONL line", extra={"line": line_number})
            continue
        if args.drop_closed and is_closed(tender):
            closed_skipped += 1
            continue
        input_records.append(tender)
        if args.limit is not None and len(input_records) >= args.limit:
            break

    enriched: list[dict[str, Any]] = []
    imputed = 0
    for tender in input_records:
        result = enrich_tender(
            tender,
            global_seed=seed,
            default_value_min=settings.default_value_min,
            default_value_max=settings.default_value_max,
            seeds=seeds,
            keyword_map=keyword_map,
            trade_value_bands=trade_value_bands,
        )
        EnrichedTender.model_validate(result)
        enriched.append(result)
        imputed += int(result["synthetic"]["value_imputed"])

    if not args.dry_run:
        atomic_write_jsonl(output_path, enriched)
    LOG.info(
        "Enrichment summary",
        extra={
            "tenders_read": lines_read,
            "enriched": len(enriched),
            "skipped": skipped,
            "closed_skipped": closed_skipped,
            "imputed": imputed,
        },
    )
    if args.dry_run:
        LOG.info("Dry run complete; output was not written")
    return 0


def _validate(args: argparse.Namespace, settings: Settings) -> int:
    input_path = args.input or settings.output_path
    if not input_path.is_file():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")
    valid = invalid = 0
    for line_number, record in read_jsonl(input_path):
        if record is None:
            invalid += 1
            LOG.error("Invalid JSONL record", extra={"line": line_number})
            continue
        try:
            EnrichedTender.model_validate(record)
            valid += 1
        except ValidationError as exc:
            invalid += 1
            LOG.error("Record failed schema validation", extra={"line": line_number, "error_type": exc.__class__.__name__})
    LOG.info("Validation summary", extra={"valid": valid, "invalid": invalid, "tenders_read": valid + invalid})
    return 0 if invalid == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    configured = False
    try:
        settings = Settings()
        configure_logging(settings.log_level, settings.log_format)
        configured = True
        seeds = load_seeds()
        keyword_map, trade_value_bands = load_trade_config()
        if args.command == "run":
            return _run(args, settings, seeds, keyword_map, trade_value_bands)
        return _validate(args, settings)
    except Exception as exc:
        # Keep failure details useful without printing tender bodies or raw content.
        if not configured:
            configure_logging("ERROR", "text")
        LOG.error("Fatal error: %s", str(exc).replace("\n", " "), extra={"error_type": exc.__class__.__name__})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
