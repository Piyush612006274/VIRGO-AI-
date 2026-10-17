"""Bounded public-web research using DuckDuckGo HTML and stdlib HTTP."""

from __future__ import annotations

import html
import ipaddress
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from threading import Event
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

from virgo.contracts.errors import ProviderUnavailableError, ValidationError
from virgo.contracts.models.knowledge_on_demand import (
    KnowledgeNeed,
    KnowledgeSource,
)

USER_AGENT = "VirgoAI/1.0 (+local-research)"
MAX_BYTES = 512_000
MAX_RESULTS = 5


@dataclass(frozen=True, slots=True)
class ResearchResult:
    title: str
    url: str
    excerpt: str


class _SearchParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[ResearchResult] = []
        self._anchor: str | None = None
        self._title: list[str] = []
        self._snippet: list[str] = []
        self._in_result = False

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_dict = dict(attrs)
        if tag == "a" and "result__a" in attrs_dict.get("class", ""):
            self._anchor = attrs_dict.get("href")
            self._title = []
            self._in_result = True
        elif tag in {"a", "div"} and self._in_result:
            classes = attrs_dict.get("class", "")
            if "result__snippet" in classes:
                self._snippet = []

    def handle_data(self, data: str) -> None:
        if self._in_result:
            self._title.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_result and self._anchor:
            title = " ".join("".join(self._title).split())
            url = _unwrap_ddg_url(self._anchor)
            if title and url:
                self.results.append(ResearchResult(title=title, url=url, excerpt=""))
            self._anchor = None
            self._in_result = False


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.skip_depth == 0:
            clean = " ".join(data.split())
            if clean:
                self.text.append(clean)


class WebResearchService:
    provider_name = "public-web-research"

    def health_check(self) -> bool:
        return True

    def search(self, query: str, *, limit: int = MAX_RESULTS, cancellation: Event | None = None) -> tuple[ResearchResult, ...]:
        if not isinstance(query, str) or not query.strip():
            raise ValidationError("Research query must not be empty", source_module=__name__)
        limit = max(1, min(limit, MAX_RESULTS))
        signal = cancellation or Event()
        if signal.is_set():
            return ()
        url = "https://html.duckduckgo.com/html/?q=" + quote_plus(query.strip())
        body = self._fetch(url, signal)
        parser = _SearchParser()
        parser.feed(body)
        values: list[ResearchResult] = []
        for result in parser.results:
            if len(values) >= limit or signal.is_set():
                break
            try:
                page_text = self.fetch_text(result.url, signal)
            except ProviderUnavailableError:
                page_text = ""
            values.append(ResearchResult(result.title, result.url, page_text[:500]))
        return tuple(values)

    def fetch_text(self, url: str, cancellation: Event | None = None) -> str:
        signal = cancellation or Event()
        safe_url = self._validate_public_url(url)
        if signal.is_set():
            return ""
        body = self._fetch(safe_url, signal)
        parser = _TextParser()
        parser.feed(body)
        return " ".join(parser.text)[:8_000]

    def execute(self, objective: str, *, cancellation: Event | None = None) -> str:
        results = self.search(objective, cancellation=cancellation)
        if not results:
            return "No public research results were retrieved."
        return "\n\n".join(
            f"{index}. {item.title}\n{item.url}\n{item.excerpt}"
            for index, item in enumerate(results, 1)
        )

    def _fetch(self, url: str, cancellation: Event) -> str:
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
        try:
            with urlopen(request, timeout=15) as response:
                chunks: list[bytes] = []
                total = 0
                while total < MAX_BYTES and not cancellation.is_set():
                    chunk = response.read(min(65_536, MAX_BYTES - total))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total += len(chunk)
        except OSError as error:
            raise ProviderUnavailableError(
                "Public web research is currently unavailable",
                technical_detail=str(error), source_module=__name__, cause=error,
            ) from error
        return b"".join(chunks).decode("utf-8", errors="replace")

    @staticmethod
    def _validate_public_url(url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValidationError("Research source must be an HTTP(S) URL", source_module=__name__)
        hostname = parsed.hostname
        try:
            addresses = {info[4][0] for info in socket.getaddrinfo(hostname, 443)}
        except OSError as error:
            raise ProviderUnavailableError(
                "Research host could not be resolved",
                technical_detail=str(error), source_module=__name__, cause=error,
            ) from error
        if any(_blocked_address(str(address)) for address in addresses):
            raise ValidationError("Private or loopback research targets are blocked", source_module=__name__)
        return url


class WebKnowledgeProvider:
    """Adapt public research results into the existing knowledge evidence boundary."""

    configured = True

    def __init__(self, service: WebResearchService | None = None) -> None:
        self.service = service or WebResearchService()

    def retrieve(self, need: KnowledgeNeed, cancellation: Event) -> tuple[KnowledgeSource, ...]:
        results = self.service.search(
            need.question, limit=need.maximum_sources, cancellation=cancellation
        )
        return tuple(
            KnowledgeSource(
                source_type="public_web",
                title=result.title[:200] or result.url,
                origin=result.url,
                excerpt=result.excerpt[:500] or result.title[:500],
                provenance="PUBLIC_WEB_RESEARCH",
                retrieval_method="duckduckgo_html",
            )
            for result in results
            if result.url and (result.excerpt or result.title)
        )


def _unwrap_ddg_url(url: str) -> str:
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    if parsed.path.startswith("/l/"):
        values = parse_qs(parsed.query).get("uddg")
        if values:
            return unquote(values[0])
    return url


def _blocked_address(value: str) -> bool:
    ip = ipaddress.ip_address(value)
    return bool(ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast)
