from __future__ import annotations

import logging
from datetime import date

from .cppp import CPPPScraper, HOME_URL, parse_latest_tenders

LOG = logging.getLogger("tenderscrape.cpwd")
CPWD_URL = "https://cpwd.gov.in/cpwde_tender.aspx"


class CPWDScraper(CPPPScraper):
    """Read CPWD notices published through CPPP's linked public listing."""

    source_portal = "cpwd"
    base_url = CPWD_URL

    def __init__(self, *, today: date | None = None, **kwargs):
        self.today = today or date.today()
        # CPPP implementation and parser are intentionally reused: CPWD Works
        # Manual says notices are linked to CPPP. Dedicated CPWD e-tender site
        # is a different platform and is currently inaccessible without further
        # inspection, so this scraper does not pretend to cover it.
        from .base import BaseScraper
        BaseScraper.__init__(self, **kwargs)

    def scrape(self):
        response = self.fetch(HOME_URL)
        if response is None:
            return
        path = self.save_payload(response.content)
        from datetime import datetime
        records = parse_latest_tenders(response.text, scraped_at=datetime.now().astimezone(),
                                      raw_payload_path=str(path), today=self.today)
        for record in records:
            # The landing page does not expose organization on every row, so
            # only records whose visible title/reference clearly identify CPWD
            # can be safely attributed to this portal.
            if "cpwd" in f"{record.title} {record.tender_id}".lower():
                yield record.model_copy(update={"source_portal": "cpwd"})
