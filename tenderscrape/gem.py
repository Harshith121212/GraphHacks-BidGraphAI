from __future__ import annotations

import logging
import json
import re
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import BaseScraper
from .cppp import parse_date
from .models import Tender

LOG = logging.getLogger("tenderscrape.gem")
GEM_URL = "https://bidplus.gem.gov.in/all-bids"
GEM_DATA_URL = "https://bidplus.gem.gov.in/all-bids-data"


def parse_gem_list(html: str, *, scraped_at: datetime, raw_payload_path: str, today: date | None = None) -> list[Tender]:
    today = today or date.today()
    soup = BeautifulSoup(html, "html.parser")
    records: list[Tender] = []
    for table in soup.find_all("table"):
        headings = [" ".join(cell.stripped_strings).lower() for cell in table.find_all("th")]
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"], recursive=False)
            if not cells or all(cell.name == "th" for cell in cells):
                continue
            text = [" ".join(cell.stripped_strings) for cell in cells]
            joined = " ".join(text)
            bid_match = re.search(r"GEM/\d{4}/B/\d+", joined, re.I)
            if not bid_match:
                continue
            links = row.find_all("a", href=True)
            title = None
            end = None
            start = None
            for i, heading in enumerate(headings):
                if i >= len(text):
                    continue
                if "description" in heading or "title" in heading:
                    title = text[i]
                elif "end" in heading or "closing" in heading:
                    end = parse_date(text[i])
                elif "start" in heading or "publish" in heading:
                    start = parse_date(text[i])
            if end is None:
                dates = [parse_date(t) for t in text]
                dates = [d for d in dates if d is not None]
                end = dates[-1] if dates else None
                start = dates[0] if len(dates) > 1 else start
            # The public bid detail page exposes bid number in its path in many
            # listings; keep a stable fallback URL when a row lacks a link.
            bid_id = bid_match.group(0).upper()
            numeric_id = bid_id.rsplit("/", 1)[-1]
            href = next((a["href"] for a in links if "bid" in a["href"].lower()), None)
            if end is None or end.date() < today:
                continue
            if re.search(r"cancel+|retender", joined, re.I):
                continue
            if not title:
                title = bid_id
            records.append(Tender(
                tender_id=bid_id,
                source_portal="gem",
                title=title,
                requesting_unit=None,
                department=None,
                publish_date=None,
                bid_start_date=start,
                bid_end_date=end,
                tender_url=urljoin(GEM_URL, href or f"/bidding/bid-details/{numeric_id}"),
                scraped_at=scraped_at,
                raw_payload_path=raw_payload_path,
            ))
    return records


class GeMScraper(BaseScraper):
    source_portal = "gem"
    base_url = GEM_URL

    def __init__(self, *, today: date | None = None, max_pages: int | None = None, **kwargs):
        super().__init__(**kwargs)
        self.today = today or date.today()
        self.max_pages = max_pages

    def scrape(self):
        response = self.fetch(GEM_URL)
        if response is None:
            return
        page_path = self.save_payload(response.content)
        if self.is_block_page(response.text):
            LOG.warning("blocked: GeM returned a CAPTCHA or block page; skipping")
            return
        if BeautifulSoup(response.text, "html.parser").find("tr"):
            yield from parse_gem_list(response.text, scraped_at=datetime.now().astimezone(),
                                      raw_payload_path=str(page_path), today=self.today)
            return
        LOG.info("GeM listing rows are dynamically loaded; using the page's public listing request")
        token_match = re.search(r"csrf_bd_gem_nk['\"]\s*:\s*['\"]([A-Za-z0-9]+)", response.text)
        if not token_match:
            LOG.warning("GeM page did not expose its listing form token; skipping")
            return
        payload_base = {
            "param": {"searchBid": "", "searchType": "fullText"},
            "filter": {
                "bidStatusType": "ongoing_bids", "byType": "all", "highBidValue": "",
                "byEndDate": {"from": "", "to": ""}, "sort": "Bid-End-Date-Oldest",
            },
        }
        page = 1
        total_pages = None
        while total_pages is None or page <= total_pages:
            payload = dict(payload_base)
            if page > 1:
                payload["page"] = page
            data_response = self.request(
                "POST", GEM_DATA_URL,
                data={"payload": json.dumps(payload), "csrf_bd_gem_nk": token_match.group(1)},
                headers={"Referer": GEM_URL, "X-Requested-With": "XMLHttpRequest"},
            )
            if data_response is None:
                LOG.warning("GeM listing data request failed at page %d; stopping pagination", page)
                return
            raw_path = self.save_payload(data_response.content, suffix=".json")
            try:
                data = data_response.json()
            except ValueError:
                LOG.warning("GeM listing data response was not JSON at page %d; stopping", page)
                return
            response_data = data.get("response", {}).get("response", {})
            docs = response_data.get("docs", [])
            total = int(response_data.get("numFound", len(docs)))
            total_pages = max(1, (total + 9) // 10)
            if self.max_pages is not None:
                total_pages = min(total_pages, self.max_pages)
            LOG.info("GeM page %d/%d returned %d bids (total matching: %d)", page, total_pages, len(docs), total)
            yield from parse_gem_data(docs, scraped_at=datetime.now().astimezone(),
                                      raw_payload_path=str(raw_path), today=self.today)
            page += 1


def parse_gem_data(docs: list[dict], *, scraped_at: datetime, raw_payload_path: str,
                   today: date | None = None) -> list[Tender]:
    today = today or date.today()
    records = []

    def first(value):
        return value[0] if isinstance(value, list) and value else value

    for doc in docs:
        bid_id = str(first(doc.get("b_bid_number")) or "").strip()
        numeric_id = str(first(doc.get("b_id")) or "").strip()
        try:
            end = datetime.fromisoformat(str(first(doc.get("final_end_date_sort")) or "").replace("Z", "+00:00"))
        except ValueError:
            end = None
        status = str(first(doc.get("b_status_text") or doc.get("b_status")) or "")
        if not bid_id or not numeric_id or end is None or end.date() < today:
            continue
        if re.search(r"cancel+|retender", status, re.I):
            continue
        title = str(first(doc.get("b_category_name") or doc.get("b_bid_title")) or bid_id).strip()
        try:
            start = datetime.fromisoformat(str(first(doc.get("final_start_date_sort")) or "").replace("Z", "+00:00"))
        except ValueError:
            start = None
        records.append(Tender(
            tender_id=bid_id,
            source_portal="gem",
            title=title,
            requesting_unit=first(doc.get("ba_official_details_deptName")),
            department=first(doc.get("ba_official_details_minName")),
            publish_date=start.date() if start else None,
            bid_start_date=start,
            bid_end_date=end,
            tender_url=f"https://bidplus.gem.gov.in/showbidDocument/{numeric_id}",
            scraped_at=scraped_at,
            raw_payload_path=raw_payload_path,
        ))
    return records
