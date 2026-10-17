"""Playwright-backed browser actions with private-network protection."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

from virgo.contracts.errors import ProviderUnavailableError, ValidationError

MAX_PAGE_TEXT = 30_000


@dataclass(frozen=True, slots=True)
class BrowserPage:
    url: str
    title: str
    text: str


class BrowserAutomationService:
    provider_name = "playwright-browser"

    def __init__(self, *, headless: bool = True, timeout_ms: int = 15_000) -> None:
        if timeout_ms <= 0 or timeout_ms > 120_000:
            raise ValidationError("Browser timeout is outside the safe range", source_module=__name__)
        self.headless = headless
        self.timeout_ms = timeout_ms
        self._playwright: object | None = None
        self._browser: object | None = None
        self._context: object | None = None
        self._page: object | None = None

    def health_check(self) -> bool:
        try:
            import playwright  # noqa: F401
        except ImportError:
            return False
        return True

    def open(self, url: str) -> BrowserPage:
        page = self._ensure_page()
        safe_url = self._validate_url(url)
        try:
            page.goto(safe_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            title = str(page.title())
            text = _bounded_text(str(page.locator("body").inner_text(timeout=self.timeout_ms)))
            return BrowserPage(url=str(page.url), title=title, text=text)
        except Exception as error:
            raise ProviderUnavailableError(
                "The browser could not open the requested page",
                technical_detail=str(error), source_module=__name__, cause=error,
            ) from error

    def search(self, query: str, *, limit: int = 5) -> tuple[BrowserPage, ...]:
        if not query.strip():
            raise ValidationError("Browser search query must not be empty", source_module=__name__)
        page = self.open("https://www.google.com/search?q=" + _quote(query))
        return (page,) if limit >= 1 else ()

    def click(self, label: str) -> str:
        page = self._ensure_page()
        if not label.strip():
            raise ValidationError("Browser label must not be empty", source_module=__name__)
        try:
            page.get_by_role("link", name=label).first.click(timeout=self.timeout_ms)
            return str(page.url)
        except Exception as error:
            raise ProviderUnavailableError(
                "The requested browser control could not be clicked",
                technical_detail=str(error), source_module=__name__, cause=error,
            ) from error

    def read(self) -> BrowserPage:
        page = self._ensure_page()
        try:
            return BrowserPage(
                url=str(page.url), title=str(page.title()),
                text=_bounded_text(str(page.locator("body").inner_text(timeout=self.timeout_ms))),
            )
        except Exception as error:
            raise ProviderUnavailableError(
                "The current browser page could not be read",
                technical_detail=str(error), source_module=__name__, cause=error,
            ) from error

    def execute(self, objective: str) -> str:
        text = objective.casefold()
        if "open http" in text or "open https" in text:
            import re
            match = re.search(r"https?://[^\s]+", objective)
            if match is None:
                raise ValidationError("Browser URL could not be extracted", source_module=__name__)
            page = self.open(match.group(0).rstrip(".,)"))
            return f"Opened {page.title or page.url}\n{page.text[:4_000]}"
        if any(marker in text for marker in ("search web", "search browser", "google")):
            query = objective.split("for", 1)[1].strip() if " for " in text else objective
            page = self.search(query)
            return f"Browser search page: {page[0].url}\n{page[0].text[:4_000]}"
        return self.read().text[:4_000]

    def close(self) -> None:
        for resource in (self._context, self._browser, self._playwright):
            close = getattr(resource, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
        self._page = self._context = self._browser = self._playwright = None

    def _ensure_page(self):
        if self._page is not None:
            return self._page
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise ProviderUnavailableError(
                "Browser automation requires the browser extra",
                technical_detail="Install the browser optional dependency and Chromium.",
                source_module=__name__, cause=error,
            ) from error
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=self.headless)
            self._context = self._browser.new_context()
            self._page = self._context.new_page()
            self._page.set_default_timeout(self.timeout_ms)
            return self._page
        except Exception as error:
            self.close()
            raise ProviderUnavailableError(
                "Chromium could not be started",
                technical_detail=str(error), source_module=__name__, cause=error,
            ) from error

    @staticmethod
    def _validate_url(url: str) -> str:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValidationError("Only HTTP(S) URLs are allowed", source_module=__name__)
        host = parsed.hostname
        try:
            infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        except OSError as error:
            raise ProviderUnavailableError(
                "The browser could not resolve the requested host",
                technical_detail=str(error), source_module=__name__, cause=error,
            ) from error
        addresses = {str(info[4][0]) for info in infos}
        if any(_is_private_or_reserved(address) for address in addresses):
            raise ValidationError("Private or loopback browser targets are blocked", source_module=__name__)
        return url.strip()


def _is_private_or_reserved(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return bool(ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast)


def _bounded_text(value: str) -> str:
    clean = " ".join(value.split())
    return clean[:MAX_PAGE_TEXT]


def _quote(value: str) -> str:
    from urllib.parse import quote_plus
    return quote_plus(value.strip())
