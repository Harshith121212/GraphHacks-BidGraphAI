from __future__ import annotations

import logging
import re
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import BaseScraper
from .models import Tender

LOG = logging.getLogger("tenderscrape.cppp")
HOME_URL = "https://eprocure.gov.in/eprocure/app"
ACTIVE_URL = "https://eprocure.gov.in/eprocure/app?page=FrontEndLatestActiveTenders&service=page"


def parse_date(value: str) -> datetime | None:
    text = " ".join(value.replace("\xa0", " ").split())
    for fmt in ("%d-%b-%Y %I:%M %p", "%d-%b-%Y %H:%M", "%d-%b-%Y", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(hour=23, minute=59, second=59) if fmt in {"%d-%b-%Y", "%d/%m/%Y"} else parsed
        except ValueError:
            continue
    return None


def parse_money(value: str) -> Decimal | None:
    cleaned = re.sub(r"[^0-9.]", "", value.replace(",", ""))
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_latest_tenders(html: str, *, scraped_at: datetime, raw_payload_path: str, today: date | None = None) -> list[Tender]:
    today = today or date.today()
    soup = BeautifulSoup(html, "html.parser")
    tenders: list[Tender] = []
    active_table = soup.find("table", id="activeTenders")
    tables = [active_table] if active_table is not None else soup.find_all("table")
    for table in tables:
        if table is None:
            continue
        rows = table.find_all("tr")
        header_row = None
        headings = []
        if table.get("id") == "activeTenders":
            headings = ["tender title", "reference no", "closing date", "bid opening date"]
        else:
            for candidate in rows:
                header_cells = candidate.find_all(["th", "td"], recursive=False)
                labels = [" ".join(cell.stripped_strings).lower() for cell in header_cells]
                if any("title" in label for label in labels) and any(
                    "reference" in label or "tender id" in label for label in labels
                ) and any("closing" in label or "end date" in label for label in labels):
                    header_row = candidate
                    headings = labels
                    break
        if not headings or not any("reference" in h or "tender id" in h for h in headings):
            continue
        index = {h: i for i, h in enumerate(headings)}

        def col(*terms: str) -> int | None:
            return next((i for label, i in index.items() if any(term in label for term in terms)), None)

        title_i = col("title", "tender name")
        ref_i = col("reference", "tender id")
        close_i = col("closing date", "bid end", "submission")
        publish_i = col("published", "publish date")
        for row in rows:
            if row is header_row:
                continue
            cells = row.find_all(["td", "th"], recursive=False)
            if not cells or len(cells) < len(headings):
                continue
            values = [" ".join(cell.stripped_strings) for cell in cells]
            if title_i is None or ref_i is None or close_i is None or max(title_i, ref_i, close_i) >= len(values):
                continue
            title_cell = cells[title_i]
            link = title_cell.find("a", href=True)
            title = values[title_i]
            tender_id = values[ref_i]
            end = parse_date(values[close_i])
            if not title or parse_date(title) is not None or not tender_id or end is None or end.date() < today:
                continue
            if re.search(r"cancel+|retender", title, re.I):
                continue
            publish = parse_date(values[publish_i]) if publish_i is not None and publish_i < len(values) else None
            url = urljoin(HOME_URL, link["href"]) if link else HOME_URL
            tenders.append(Tender(
                tender_id=tender_id,
                source_portal="cppp",
                title=re.sub(r"^\s*\d+[.)]\s*", "", title),
                requesting_unit=None,
                department=None,
                estimated_value=None,
                publish_date=publish.date() if publish else None,
                bid_start_date=None,
                bid_end_date=end,
                emd=None,
                eligibility_text=None,
                tender_url=url,
                scraped_at=scraped_at,
                raw_payload_path=raw_payload_path,
            ))
    return tenders


class CPPPScraper(BaseScraper):
    source_portal = "cppp"
    base_url = HOME_URL

    def __init__(self, **kwargs):
        self.today = kwargs.pop("today", None) or date.today()
        super().__init__(**kwargs)

    def scrape(self):
        # Dedicated active listing requires a CAPTCHA; use the public latest-tenders HTML table on landing page
        response = self.fetch(HOME_URL)
        if response is None:
            return
        raw_path = self.save_payload(response.content)
        scraped_at = datetime.now().astimezone()
        yield from parse_latest_tenders(response.text, scraped_at=scraped_at,
                                        raw_payload_path=str(raw_path), today=self.today)
