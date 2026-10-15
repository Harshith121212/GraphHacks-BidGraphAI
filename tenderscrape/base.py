from __future__ import annotations

import logging
import random
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from .models import Tender
from .config import Settings

LOG = logging.getLogger("tenderscrape")


class BaseScraper(ABC):
    source_portal: str
    base_url: str

    def __init__(
        self,
        *,
        data_dir: Path | str | None = None,
        client: httpx.Client | None = None,
        min_interval: float | None = None,
        retries: int | None = None,
        request_timeout: float | None = None,
        proxy: str | None = None,
        user_agent: str | None = None,
        persist_raw: bool = True,
    ) -> None:
        settings = Settings()
        self.data_dir = Path(data_dir) if data_dir is not None else settings.output_dir
        self.raw_dir = self.data_dir / "raw" / self.source_portal
        self.persist_raw = persist_raw
        if self.persist_raw:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval = max(1.0, min_interval if min_interval is not None else settings.request_delay)
        self.retries = max(0, retries if retries is not None else settings.max_retries)
        self.request_timeout = request_timeout if request_timeout is not None else settings.request_timeout_seconds
        self.proxy = proxy if proxy is not None else settings.proxy_url
        self.user_agent = user_agent or settings.user_agent
        self._last_request = 0.0
        self.successful_requests = 0
        self._robots: dict[str, RobotFileParser | None] = {}
        self._owns_client = client is None
        self.client = client or httpx.Client(
            headers={"User-Agent": self.user_agent},
            follow_redirects=True,
            timeout=httpx.Timeout(self.request_timeout),
            proxy=self.proxy,
        )

    @staticmethod
    def _safe_url(url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    @staticmethod
    def is_block_page(content: str) -> bool:
        return bool(re.search(
            r"captcha|verify\s+(?:that\s+)?you\s+are\s+human|unusual\s+traffic|access\s+denied|request\s+blocked",
            content,
            re.I,
        ))

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()

    def _robots_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            robots_url = urljoin(origin, "/robots.txt")
            try:
                response = self.client.get(robots_url, timeout=httpx.Timeout(self.request_timeout))
                self._last_request = time.monotonic()
                if response.status_code == 404:
                    self._robots[origin] = None
                elif response.is_success:
                    parser = RobotFileParser(robots_url)
                    parser.parse(response.text.splitlines())
                    self._robots[origin] = parser
                else:
                    LOG.warning("Could not read robots.txt for %s (HTTP %s); skipping", origin, response.status_code)
                    self._robots[origin] = False  # type: ignore[assignment]
            except httpx.HTTPError as exc:
                self._last_request = time.monotonic()
                LOG.warning("Could not read robots.txt for %s (%s); skipping", origin, exc)
                self._robots[origin] = False  # type: ignore[assignment]
        parser = self._robots[origin]
        if parser is False:
            return False
        return parser is None or parser.can_fetch(self.client.headers.get("User-Agent", "*"), url)

    def fetch(self, url: str) -> httpx.Response | None:
        return self.request("GET", url)

    def request(self, method: str, url: str, *, data=None, headers=None) -> httpx.Response | None:
        if not self._robots_allowed(url):
            LOG.warning("robots.txt disallows or could not be checked; skipping %s", url)
            return None
        for attempt in range(self.retries + 1):
            delay = self.min_interval - (time.monotonic() - self._last_request)
            if delay > 0:
                time.sleep(delay)
            try:
                response = self.client.request(
                    method, url, data=data, headers=headers,
                    timeout=httpx.Timeout(self.request_timeout),
                )
                self._last_request = time.monotonic()
                self.successful_requests += int(response.is_success)
                if response.status_code in {401, 403}:
                    LOG.warning("blocked: portal denied request to %s (HTTP %s)",
                                self._safe_url(url), response.status_code)
                    return None
                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.retries:
                    wait = self._retry_delay(response.headers.get("Retry-After"), attempt)
                    LOG.warning("Transient HTTP %s from %s; retrying in %.1fs", response.status_code, self._safe_url(url), wait)
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                return response
            except httpx.HTTPError as exc:
                if attempt >= self.retries:
                    LOG.error("Request failed for %s: %s", url, exc)
                    return None
                wait = min(30.0, 2**attempt)
                wait = min(30.0, wait + random.uniform(0, min(1.0, wait * 0.25)))
                LOG.warning("Request failed for %s (%s); retrying in %.1fs", self._safe_url(url), exc.__class__.__name__, wait)
                time.sleep(wait)
        return None

    def save_payload(self, payload: bytes, suffix: str = ".html") -> Path:
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
        path = self.raw_dir / f"{stamp}{suffix}"
        if self.persist_raw:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        return path

    @staticmethod
    def _retry_delay(retry_after: str | None, attempt: int) -> float:
        if retry_after:
            try:
                return min(300.0, max(0.0, float(retry_after)))
            except ValueError:
                try:
                    date = parsedate_to_datetime(retry_after)
                    return min(300.0, max(0.0, (date - datetime.now(date.tzinfo)).total_seconds()))
                except (TypeError, ValueError, OverflowError):
                    pass
        base = min(30.0, 2**attempt)
        return base + random.uniform(0, min(1.0, base * 0.25))

    @abstractmethod
    def scrape(self):
        """Yield currently active Tender records."""
        raise NotImplementedError

    @staticmethod
    def absolute_url(base: str, href: str) -> str:
        return urljoin(base, href)
