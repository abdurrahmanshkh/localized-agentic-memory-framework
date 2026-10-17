"""
Tests for search validation, SSRF protection, and partial scraping fault tolerance.
"""

from unittest.mock import patch

from src import search


def test_is_safe_external_url_ssrf_protection():
    """Verifies that private, loopback, and local network URLs are rejected."""
    # Disallowed URLs (SSRF vectors)
    assert not search.is_safe_external_url("http://localhost:8080/admin")
    assert not search.is_safe_external_url("http://127.0.0.1/secrets")
    assert not search.is_safe_external_url("http://[::1]/internal")
    assert not search.is_safe_external_url("http://192.168.1.1/router")
    assert not search.is_safe_external_url("http://10.0.0.5/api")
    assert not search.is_safe_external_url("http://172.16.0.2/meta")
    assert not search.is_safe_external_url("http://169.254.169.254/latest/meta-data/")
    assert not search.is_safe_external_url("file:///etc/passwd")
    assert not search.is_safe_external_url("ftp://example.com/file")
    assert not search.is_safe_external_url("javascript:alert(1)")

    # Legitimate external URLs
    assert search.is_safe_external_url("https://en.wikipedia.org/wiki/Artificial_intelligence")
    assert search.is_safe_external_url("http://example.com/research.html")
    assert search.is_safe_external_url("https://github.com/trending")


def test_search_web_handles_empty_query():
    """Verifies that empty queries return an empty list without network calls."""
    assert search.search_web("") == []
    assert search.search_web("   ") == []


def test_deepsearch_tolerates_individual_page_failures():
    """Verifies that if one page fails to download, the remaining results are still processed."""
    fake_results = [
        {"title": "Broken Page", "href": "https://broken.example.com", "body": "Snippet 1"},
        {"title": "Working Page", "href": "https://working.example.com", "body": "Snippet 2"},
    ]

    with patch.object(search, "search_web", return_value=fake_results):
        with patch("trafilatura.fetch_url", side_effect=[Exception("Connection reset"), "<html>Clean content</html>"]):
            with patch("trafilatura.extract", return_value="Extracted main article text"):
                results = search.search_and_scrape("test query")
                assert len(results) == 2
                # The first item fell back to the snippet
                assert results[0]["title"] == "Broken Page"
                assert results[0]["text"] == "Snippet 1"
                # The second item used extracted article text
                assert results[1]["title"] == "Working Page"
                assert results[1]["text"] == "Extracted main article text"
