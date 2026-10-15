from __future__ import annotations

import argparse
import logging
import signal
import time
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from .config import Settings
from .cppp import CPPPScraper
from .cpwd import CPWDScraper
from .gem import GeMScraper
from .ireps import IREPSScraper
from .logging_config import configure_logging
from .runtime import LockHeldError, RunLock
from .storage import _load_active, atomic_write_jsonl, inspect_records

SCRAPERS = {"cppp": CPPPScraper, "cpwd": CPWDScraper, "gem": GeMScraper, "ireps": IREPSScraper}
LOG = logging.getLogger("tenderscrape.cli")


def write_jsonl(records, path: Path, *, today: date | None = None) -> int:
    records = list(records)
    atomic_write_jsonl(path, records, today=today)
    return len(records)


class GlobalTimeout(TimeoutError):
    pass


@contextmanager
def _global_deadline(seconds: float):
    if not hasattr(signal, "setitimer") or not hasattr(signal, "SIGALRM"):
        yield
        return
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)

    def timeout_handler(_signum, _frame):
        raise GlobalTimeout(f"global timeout exceeded after {seconds:g} seconds")

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)
        signal.signal(signal.SIGALRM, previous_handler)


def _output_path(settings: Settings, override: str | None) -> Path:
    if override is None:
        return settings.output_path
    path = Path(override).expanduser()
    return path if path.is_absolute() else settings.output_dir / path


def _summary(portal: str, found: int, new: int, duplicates: int, errors: int,
             duration: float, status: str) -> None:
    LOG.info("portal summary", extra={
        "portal": portal, "found": found, "new": new, "duplicates": duplicates,
        "errors": errors, "duration_seconds": round(duration, 3), "status": status,
    })


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tenderscrape", description="Collect public active tender listings")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="scrape one portal or all enabled portals")
    run.add_argument("--portal", choices=[*SCRAPERS, "all"], default="all")
    run.add_argument("--output", help="output JSONL path (relative paths are under OUTPUT_DIR)")
    run.add_argument("--dry-run", action="store_true", help="scrape and log without writing raw payloads or JSONL")
    run.add_argument("--max-pages", type=int, default=None, help="limit GeM result pages for a bounded run")
    args = parser.parse_args(argv)
    if args.max_pages is not None and args.max_pages < 1:
        parser.error("--max-pages must be at least 1")

    try:
        settings = Settings()
    except Exception as exc:
        logging.basicConfig(level=logging.ERROR)
        logging.getLogger("tenderscrape").error("Invalid configuration: %s", exc.__class__.__name__)
        return 2
    configure_logging(settings.log_level, settings.log_format)
    portals = list(SCRAPERS) if args.portal == "all" else [args.portal]
    output_path = _output_path(settings, args.output)
    output_dir = settings.output_dir
    records = []
    run_summaries: dict[str, dict] = {}
    successful_portals = 0
    lock = RunLock(output_dir, settings.lock_stale_hours * 3600)

    try:
        with lock, _global_deadline(settings.global_timeout_seconds):
            for portal in portals:
                started = time.monotonic()
                if not settings.portal_enabled(portal):
                    _summary(portal, 0, 0, 0, 0, time.monotonic() - started, "disabled")
                    continue
                scraper_kwargs = {
                    "data_dir": output_dir,
                    "min_interval": settings.request_delay,
                    "retries": settings.max_retries,
                    "request_timeout": settings.request_timeout_seconds,
                    "proxy": settings.proxy_url,
                    "user_agent": settings.user_agent,
                    "persist_raw": not args.dry_run,
                }
                if portal == "gem":
                    scraper_kwargs["max_pages"] = args.max_pages if args.max_pages is not None else settings.gem_max_pages
                scraper = None
                portal_records = []
                errors = 0
                status = "failed"
                try:
                    scraper = SCRAPERS[portal](**scraper_kwargs)
                    for record in scraper.scrape():
                        portal_records.append(record)
                        records.append(record)
                    if scraper.successful_requests:
                        successful_portals += 1
                        status = "success"
                    else:
                        errors = 1
                except GlobalTimeout:
                    errors = 1
                    status = "timeout"
                    raise
                except Exception as exc:
                    errors = 1
                    LOG.error("Portal failed", extra={"portal": portal, "error_type": exc.__class__.__name__})
                    if scraper is not None and scraper.successful_requests:
                        successful_portals += 1
                        status = "partial"
                finally:
                    if scraper is not None:
                        scraper.close()
                    run_summaries[portal] = {
                        "found": len(portal_records), "errors": errors, "status": status,
                        "duration": time.monotonic() - started,
                    }

            existing = _load_active(output_path, date.today())
            unique, new_counts, duplicate_counts = inspect_records(records, existing, today=date.today())
            for portal, summary in run_summaries.items():
                summary["new"] = new_counts.get(portal, 0)
                summary["duplicates"] = duplicate_counts.get(portal, 0)
                _summary(portal, summary["found"], summary["new"], summary["duplicates"],
                         summary["errors"], summary["duration"], summary["status"])
            if not args.dry_run and successful_portals:
                atomic_write_jsonl(output_path, unique, today=date.today())
            elif args.dry_run:
                LOG.info("Dry run complete; no raw payloads or JSONL records were written")
    except LockHeldError as exc:
        LOG.error("Could not start run: %s", exc)
        return 2
    except GlobalTimeout as exc:
        for portal, summary in run_summaries.items():
            _summary(portal, summary["found"], 0, 0, summary["errors"],
                     summary["duration"], summary["status"])
        LOG.error("Job timed out", extra={"error_type": exc.__class__.__name__})
        return 1
    except Exception as exc:
        for portal, summary in run_summaries.items():
            _summary(portal, summary["found"], 0, 0, summary["errors"],
                     summary["duration"], summary["status"])
        LOG.error("Fatal run error", extra={"error_type": exc.__class__.__name__})
        return 2
    return 0 if successful_portals else 1


if __name__ == "__main__":
    raise SystemExit(main())
