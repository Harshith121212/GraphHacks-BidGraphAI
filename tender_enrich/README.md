# Tender enrichment

`tender_enrich` is a standalone Python 3.12 package. It reads the scraper's JSONL file format and attaches synthetic **tender requirements** for downstream scoring and graph modules. It does not import the scraper package, contact government portals, or connect to a database. All generated qualifications and IDs are illustrative and are not real tender terms.

## Install and run

From the repository root:

```sh
python3.12 -m venv .venv-enrich
. .venv-enrich/bin/activate
python -m pip install -e './tender_enrich[dev]'
cp tender_enrich/.env.example .env
python -m tender_enrich run
python -m tender_enrich validate --input ./data/tenders_enriched.jsonl
```

Run options:

```sh
python -m tender_enrich run --input ./data/tenders.jsonl \
  --output ./data/tenders_enriched.jsonl --seed 42 --limit 100 --dry-run --drop-closed
python -m tender_enrich validate --input ./data/tenders_enriched.jsonl
```

`run` skips malformed JSONL lines with a single-line warning, fills absent scraper fields with `null`, and overwrites the output atomically. It refuses to use the same input and output path. `--drop-closed` skips records whose bid end is before the current time and reports the skipped count. Naive bid dates are assumed to be India Standard Time; bid start/end dates are written as timezone-aware UTC ISO strings. A dry run enriches and validates records in memory but writes no output. Re-running with the same source records and seed produces byte-identical JSONL. The original object is retained, its top-level `estimated_value` is replaced with a per-tender synthetic INR estimate, and it receives a `synthetic` object.

## Output schema

Each output record has the scraper's original fields plus:

| Block | Generated requirement data |
| --- | --- |
| `avg_turnover` | Required average annual INR turnover, three Indian financial years, and `reference_turnover_by_fy`, an illustrative threshold sample—not bidder financial data |
| `net_worth_solvency` | Minimum net worth, positive net worth requirement, solvency certificate and amount, issuing bank type, validity |
| `registrations` | GST, PAN, EPFO, ESIC and Udyam requirement flags/identifiers, MSME preference, and `ids_are_fake: true` |
| `boq` | Trade, `trade_source` (`keyword` or `random`), realistic items, adjusted quantities and estimates, fake datasheet references, and short technical summaries |
| `delivery` | Period, destination, delivery terms, inspection/installation requirements, logistics notes, and liquidated damages |

The enclosing `synthetic` object also contains `is_synthetic`, `generator_version`, the per-tender derived `seed`, `value_imputed`, and all five selected `variant_ids`.

## Seed variants and scaling

Editable, hand-authored JSON is stored in `seed/avg_turnover.json`, `seed/net_worth_solvency.json`, `seed/registrations.json`, `seed/boq.json`, and `seed/delivery.json`. Each block file must contain exactly ten valid, distinct variants with its prescribed IDs. `seed/trade_keywords.json` maps title keywords to BOQ trades and defines plausible imputation bands per trade. Startup validates the block schemas, keyword destinations, bands, and BOQ trade list; invalid seed data stops the command with an error. Edit the JSON directly to add or tune a variant, keeping IDs unique and each block file at ten variants unless the validator and selection contract are deliberately updated.

Selection uses a stable SHA-256-derived RNG for each `(SEED, source_portal, tender_id)`; the stored per-tender seed is masked to a non-negative 63-bit integer. Adding, removing, or reordering other records does not change a tender's generated values. Magnitude weighting favors variants sized for the tender while preserving spread across variants. Case-insensitive title keywords route matching BOQs to the mapped trade; unmatched titles select a trade randomly. Delivery and registrations remain random. Turnover is generated at 25–35% of value, minimum net worth at 20–40%, and solvency at about 40%; each receives up to 10% jitter and is rounded to the nearest ₹10,000 or ₹1 lakh. Solvency is never below minimum net worth. BOQ quantities are adjusted so the estimate total is 90–110% of tender value. `Nos`, `Set`, and `Lot` quantities are positive integers; continuous units are rounded to two decimals, with rates re-fitted as needed.

Every tender receives a deterministic, randomly drawn `estimated_value` from the configured log-uniform band (default ₹5 lakh to ₹5 crore), even when the source already had a value. This keeps the value synthetic and consistent with the enrichment blocks. A matched trade clamps the draw to its plausible range in `trade_keywords.json`; no generated amount can exceed ₹5 crore. `value_imputed` is true for every record to mark the top-level amount as synthetic. The draw is random-looking per tender but stable for the same tender and seed, so reruns remain reproducible.

Financial year labels represent the latest three completed Indian financial years when the run is made. Synthetic requirements are training/demo inputs only; they must not be presented as actual tender conditions.

## Fake identifier rules

- GSTIN values use the 15-character structure and the generated record PAN as characters 3–12, with a valid-looking state, entity digit, and `Z`, but the final checksum is deliberately invalid.
- PAN-like numbers use the reserved `ZZZ` prefix.
- EPFO codes have a unique per-tender patterned `ZZ/ZZZ/.../000/0000000` body.
- Udyam numbers are unique per tender and use a reserved `UDYAM-ZZ-00-` fake prefix.
- ESIC numbers have a fixed `99999` prefix.
- `registrations.ids_are_fake` is always `true`.

These identifiers are fabricated, not issued IDs, and must not be used for registration, procurement, or compliance.

## Configuration

All variables can be set in the environment or `.env`; CLI options override the corresponding path/seed setting.

| Variable | Default | Meaning |
| --- | --- | --- |
| `INPUT_PATH` | `./data/tenders.jsonl` | Input JSONL |
| `OUTPUT_PATH` | `./data/tenders_enriched.jsonl` | Atomic enriched output |
| `SEED` | `42` | Global deterministic seed |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` |
| `LOG_FORMAT` | `text` | One-line `text` or `json` logs to stdout |
| `DEFAULT_VALUE_MIN` | `500000` | Minimum randomly assigned synthetic estimated value in INR |
| `DEFAULT_VALUE_MAX` | `50000000` | Maximum randomly assigned synthetic estimated value in INR (₹5 crore; hard ceiling) |

## Tests

From the repository root, run `pytest`. The tests validate seed files, schema coverage, determinism, non-degenerate variant frequencies, scale bands, keyword routing, integer quantities, fake IDs, date normalization/closed filtering, tolerant reading, atomic replacement, input preservation, CLI exit codes, and the no-scraper-import boundary.
