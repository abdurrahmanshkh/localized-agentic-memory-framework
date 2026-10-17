"""
Search service module encapsulating DuckDuckGo search and web scraping.

Provides URL sanitization, SSRF protection, bounded timeouts, and graceful
partial failure handling.
"""

from __future__ import annotations

import ipaddress
import urllib.parse

try:
    from duckduckgo_search import DDGS
except ImportError:
    try:
        from ddgs import DDGS
    except ImportError:
        DDGS = None

try:
    import trafilatura
except ImportError:
    trafilatura = None

try:
    from . import config
except ImportError:
    import config


class SearchError(Exception):
    """Base exception for external search errors."""


def is_safe_external_url(url: str) -> bool:
    """Validates that a URL uses HTTP/HTTPS and does not target localhost or private IP ranges."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme.lower() not in ("http", "https"):
            return False

        host = parsed.hostname
        if not host:
            return False

        host_lower = host.lower()
        if host_lower in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return False

        # If hostname is an IP literal, verify it is not private/reserved
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        except ValueError:
            # Domain name, allowed
            pass

        return True
    except Exception:
        return False


def search_web(
    query: str,
    max_results: int | None = None,
    timeout: float | None = None,
    attempts: int = 2,
) -> list[dict[str, str]]:
    """Runs a DuckDuckGo text search with retry policy and bounded results."""
    cleaned_query = query.strip()
    if not cleaned_query:
        return []

    if DDGS is None:
        raise SearchError("Neither 'duckduckgo-search' nor 'ddgs' package is installed.")

    limit = max_results or config.SEARCH_MAX_RESULTS
    req_timeout = timeout or config.SEARCH_TIMEOUT

    last_error = None
    for attempt in range(attempts):
        try:
            with DDGS(timeout=int(req_timeout)) as ddgs:
                results = list(ddgs.text(cleaned_query, max_results=limit))
                formatted = []
                for r in results:
                    title = r.get("title", "").strip()
                    body = r.get("body", "").strip()
                    href = r.get("href", "").strip()
                    if title or body:
                        formatted.append({"title": title, "body": body, "href": href})
                return formatted
        except Exception as e:
            last_error = e

    raise SearchError(f"Web search failed after {attempts} attempts: {last_error}")


def search_and_scrape(
    query: str,
    max_results: int | None = None,
    timeout: float | None = None,
    page_timeout: float | None = None,
) -> list[dict[str, str]]:
    """Performs deep web search by fetching and extracting text from result pages.

    Individual page download or parsing failures are absorbed to return best-effort
    results from remaining sources.
    """
    raw_results = search_web(query, max_results=max_results, timeout=timeout)
    if not raw_results:
        return []

    scraped_items: list[dict[str, str]] = []

    for item in raw_results:
        url = item.get("href", "")
        title = item.get("title", "Untitled")

        # SSRF validation
        if not is_safe_external_url(url):
            # Fall back to snippet if URL is suspect or internal
            body = item.get("body", "")
            if body:
                scraped_items.append({"title": title, "url": url, "text": body[:1000]})
            continue

        extracted_text = None
        if trafilatura is not None:
            try:
                downloaded = trafilatura.fetch_url(url)
                if downloaded:
                    # Enforce maximum downloaded byte length
                    if len(downloaded) > config.MAX_PAGE_CONTENT_BYTES:
                        downloaded = downloaded[:config.MAX_PAGE_CONTENT_BYTES]
                    extracted = trafilatura.extract(downloaded)
                    if extracted and extracted.strip():
                        extracted_text = extracted.strip()[:1000]
            except Exception:
                extracted_text = None

        # If deep extraction failed for this item, fall back gracefully to the snippet
        if not extracted_text:
            extracted_text = item.get("body", "")[:1000]

        if extracted_text:
            scraped_items.append({
                "title": title,
                "url": url,
                "text": extracted_text,
            })

    return scraped_items
