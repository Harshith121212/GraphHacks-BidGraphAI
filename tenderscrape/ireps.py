from __future__ import annotations

import logging
import re
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import BaseScraper
from .cppp import parse_date
from .models import Tender

LOG = logging.getLogger("tenderscrape.ireps")
IREPS_URL = "https://www.ireps.gov.in/"


def parse_ireps_list(html: str, *, scraped_at: datetime, raw_payload_path: str, today: date | None = None) -> list[Tender]:
    today = today or date.today()
    soup = BeautifulSoup(html, "html.parser")
    records: list[Tender] = []
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) < 2 or all(cell.name == "th" for cell in cells):
            continue
        values = [" ".join(cell.stripped_strings) for cell in cells]
        joined = " ".join(values)
        if re.search(r"cancel+|retender", joined, re.I):
            continue
        link = row.find("a", href=True)
        tender_id = None
        for value in values:
            match = re.search(r"(?:Tender\s*(?:No\.?|ID)?\s*[:#-]?\s*)?([A-Z0-9][A-Z0-9/-]{5,})", value, re.I)
            if match and any(ch.isdigit() for ch in match.group(1)):
                tender_id = match.group(1)
                break
        if not tender_id:
            continue
        dates = [parse_date(value) for value in values]
        dates = [value for value in dates if value is not None]
        if not dates:
            continue
        end = dates[-1]
        if end.date() < today:
            continue
        title = next((v for v in values if v != tender_id and parse_date(v) is None), tender_id)
        records.append(Tender(
            tender_id=tender_id,
            source_portal="ireps",
            title=title,
            requesting_unit=None,
            department=None,
            publish_date=dates[0].date() if len(dates) > 1 else None,
            bid_start_date=dates[0] if len(dates) > 1 else None,
            bid_end_date=end,
            tender_url=urljoin(IREPS_URL, link["href"] if link else "/"),
            scraped_at=scraped_at,
            raw_payload_path=raw_payload_path,
        ))
    return records


class IREPSScraper(BaseScraper):
    source_portal = "ireps"
    base_url = IREPS_URL

    def __init__(self, *, today: date | None = None, **kwargs):
        super().__init__(**kwargs)
        self.today = today or date.today()

    def scrape(self):
        response = self.fetch(IREPS_URL)
        if response is None:
            LOG.warning("IREPS public site unavailable; skipping")
            return
        path = self.save_payload(response.content)
        if not BeautifulSoup(response.text, "html.parser").find("tr"):
            LOG.warning("IREPS landing page has no public tender rows; search requires separate public workflow")
            return
        yield from parse_ireps_list(response.text, scraped_at=datetime.now().astimezone(),
                                    raw_payload_path=str(path), today=self.today)
