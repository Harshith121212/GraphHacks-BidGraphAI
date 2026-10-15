"""Local Scraper/Enricher Cron Runner and CLI Utility for Periodic Tender Ingestion."""

import os
import sys
import time
import json
import logging
import argparse
from typing import List, Dict, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.enricher_ingestor import EnricherIngestor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cron_runner")

# Realistic sample tenders from GeM (Government e-Marketplace) and CPPP (Central Public Procurement Portal)
DEFAULT_SAMPLE_TENDERS: List[Dict[str, Any]] = [
    {
        "id": "GEM-2026-BMRCL-401",
        "title": "Supply and Erection of 33kV HT Armoured Cables and Havells Switchgear for Phase 2A Metro Line",
        "reference_no": "BMRCL/PH2A/ELEC/2026/401",
        "ministry_name": "Ministry of Power",
        "tender_amount": 35000000.0,
        "description": "Procurement of BIS IS-7098 compliant LT/HT Armoured Cables and authorized Havells Switchgear components. OEM or authorized wholesaler mandatory. Location: Bengaluru, Karnataka.",
        "raw_location": "Bengaluru, Karnataka",
        "product_quantity": 6000,
    },
    {
        "id": "CPPP-2026-KPTCL-502",
        "title": "Civil Construction of Substation Control Room and HT Cable Trench Infrastructure at Belagavi",
        "reference_no": "KPTCL/ZONE-NORTH/CIVIL/2026/502",
        "ministry_name": "Ministry of Urban Development",
        "tender_amount": 28000000.0,
        "description": "Civil contractor required for construction of integrated substation foundation, structural girders, and cable trenches. CPWD-CLASS-I-CIVIL or equivalent state enlistment. Location: Belagavi, Karnataka.",
        "raw_location": "Belagavi, Karnataka",
        "product_quantity": 1,
    },
    {
        "id": "GEM-2026-SWR-603",
        "title": "Supply of Ergonomic Modular Workstations and BIFMA Certified Desks for Divisional HQ",
        "reference_no": "SWR/HQ/MODULAR/2026/603",
        "ministry_name": "Ministry of Railways",
        "tender_amount": 8500000.0,
        "description": "Supply of BIFMA Level 3 certified ergonomic office furniture and Nilkamal authorized executive seating. Location: Hubballi, Karnataka.",
        "raw_location": "Hubballi, Karnataka",
        "product_quantity": 300,
    },
]


def run_ingestion_cycle(
    sample_file: Optional[str] = None,
    graph_name: Optional[str] = None,
    use_scraper: bool = False,
    portal: str = "gem",
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Executes a single scrape-enrich-upsert cycle and returns ingestion summary."""
    ingestor = EnricherIngestor(graph_name=graph_name)

    tenders_to_process: List[Dict[str, Any]] = []

    # 1. Live scraping via tenderscrape if requested
    if use_scraper:
        try:
            from tenderscrape.cli import SCRAPERS
            logger.info("Triggering live scraper from tenderscrape for portal: %s", portal)
            portals = list(SCRAPERS.keys()) if portal == "all" else [portal]
            for p in portals:
                if p in SCRAPERS:
                    scraper = SCRAPERS[p](persist_raw=False)
                    try:
                        scraped = list(scraper.scrape())
                        for item in scraped:
                            d = item.model_dump() if hasattr(item, "model_dump") else dict(item)
                            tenders_to_process.append(d)
                            if len(tenders_to_process) >= limit:
                                break
                    except Exception as err:
                        logger.warning("Scraper '%s' encountered an issue: %s", p, err)
                    finally:
                        scraper.close()
                if len(tenders_to_process) >= limit:
                    break
        except Exception as exc:
            logger.warning("Live scraping via tenderscrape unavailable: %s. Using dataset.", exc)

    # 2. File-based ingestion (supports both .json and .jsonl from tender_enrich / tenderscrape)
    if not tenders_to_process:
        target_file = sample_file
        if not target_file:
            # Check default data directory for tenders_enriched.jsonl
            default_data_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data", "tenders_enriched.jsonl"
            )
            if os.path.exists(default_data_path):
                target_file = default_data_path

        if target_file and os.path.exists(target_file):
            logger.info("Loading tender feed from: %s", target_file)
            with open(target_file, "r", encoding="utf-8") as f:
                if target_file.endswith(".jsonl"):
                    for line in f:
                        if line.strip():
                            try:
                                tenders_to_process.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
                            if len(tenders_to_process) >= limit:
                                break
                else:
                    tenders_to_process = json.load(f)[:limit]

    # 3. Fallback to default high-fidelity sample tenders
    if not tenders_to_process:
        logger.info("Using default benchmark GeM & CPPP active procurement feed (%d tenders).", len(DEFAULT_SAMPLE_TENDERS))
        tenders_to_process = DEFAULT_SAMPLE_TENDERS

    results = []
    for raw in tenders_to_process:
        try:
            enriched = ingestor.enrich_tender(raw)
            upsert_info = ingestor.upsert_tender(enriched)
            results.append({
                "id": enriched.id,
                "title": (enriched.title[:45] + "...") if len(enriched.title) > 45 else enriched.title,
                "department": enriched.department_name,
                "amount": f"₹{enriched.tender_amount/1e7:.2f} Cr",
                "expected_turnover": f"₹{enriched.expected_turnover_3yr/1e7:.2f} Cr",
                "status": "UPSERTED",
            })
            logger.info("Successfully ingested tender %s (%s)", enriched.id, enriched.title[:30])
        except Exception as exc:
            logger.error("Failed to ingest tender %s: %s", raw.get("id") or raw.get("tender_id"), exc)
            results.append({
                "id": raw.get("id") or raw.get("tender_id", "UNKNOWN"),
                "status": "FAILED",
                "error": str(exc),
            })

    return results


def print_summary_table(results: List[Dict[str, Any]]) -> None:
    """Prints a structured ASCII table summarizing the ingestion results."""
    print("\n" + "=" * 90)
    print(f"{'TENDER ID':<22} | {'TITLE':<35} | {'AMOUNT':<10} | {'STATUS':<10}")
    print("-" * 90)
    for r in results:
        t_id = r.get("id", "")
        title = r.get("title", "")
        amt = r.get("amount", "N/A")
        status = r.get("status", "")
        print(f"{t_id:<22} | {title:<35} | {amt:<10} | {status:<10}")
    print("=" * 90 + "\n")


def main():
    parser = argparse.ArgumentParser(description="BidGraphAI Periodic Scraper & Enricher Runner")
    parser.add_argument("--once", action="store_true", help="Run once and exit immediately")
    parser.add_argument("--scrape", action="store_true", help="Trigger live portal scraping via tenderscrape")
    parser.add_argument("--portal", choices=["gem", "cppp", "cpwd", "ireps", "all"], default="gem", help="Portal to scrape (default gem)")
    parser.add_argument("--limit", type=int, default=10, help="Maximum tenders to process in this run (default 10)")
    parser.add_argument("--interval-minutes", type=int, default=60, help="Periodic interval in minutes (default 60)")
    parser.add_argument("--sample-file", type=str, default=None, help="Path to JSON or JSONL file of raw/enriched tenders")
    parser.add_argument("--graph-name", type=str, default=None, help="Target FalkorDB graph name override")

    args = parser.parse_args()

    if args.once:
        logger.info("Starting single ingestion run...")
        results = run_ingestion_cycle(
            sample_file=args.sample_file,
            graph_name=args.graph_name,
            use_scraper=args.scrape,
            portal=args.portal,
            limit=args.limit,
        )
        print_summary_table(results)
        logger.info("Single ingestion run complete.")
        return

    logger.info("Starting recurring cron loop (interval: %d minutes)...", args.interval_minutes)
    try:
        while True:
            logger.info("Triggering periodic ingestion cycle...")
            results = run_ingestion_cycle(
                sample_file=args.sample_file,
                graph_name=args.graph_name,
                use_scraper=args.scrape,
                portal=args.portal,
                limit=args.limit,
            )
            print_summary_table(results)
            logger.info("Sleeping for %d minutes...", args.interval_minutes)
            time.sleep(args.interval_minutes * 60)
    except KeyboardInterrupt:
        logger.info("Cron runner stopped by user.")


if __name__ == "__main__":
    main()
