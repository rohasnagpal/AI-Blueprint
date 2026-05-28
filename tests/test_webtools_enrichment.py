import unittest
from unittest.mock import patch

from webtools import enrich_search_results, format_search_context


class WebSearchEnrichmentTest(unittest.IsolatedAsyncioTestCase):
    async def test_enriches_result_with_http_page_text(self) -> None:
        async def fake_fetch_page_text(url: str) -> dict:
            return {
                "url": url,
                "title": "Rendered Source",
                "text": "A" * 1_500,
                "size_bytes": 1_500,
            }

        async def fail_browser_fetch(url: str) -> dict:
            raise AssertionError("browser fallback should not run")

        with patch("webtools.fetch_page_text", fake_fetch_page_text), patch(
            "webtools.fetch_page_text_browser", fail_browser_fetch
        ):
            results = await enrich_search_results(
                [{"title": "Search Result", "url": "https://example.test/source", "snippet": "short"}]
            )

        self.assertEqual(results[0]["page_fetch_method"], "http")
        self.assertEqual(results[0]["page_title"], "Rendered Source")
        self.assertEqual(results[0]["page_excerpt"], "A" * 1_500)

    async def test_falls_back_to_browser_when_http_text_is_thin(self) -> None:
        async def fake_fetch_page_text(url: str) -> dict:
            return {
                "url": url,
                "title": "Shell",
                "text": "Loading...",
                "size_bytes": 10,
            }

        async def fake_browser_fetch(url: str) -> dict:
            return {
                "url": url,
                "title": "Rendered App",
                "text": "Browser text " * 200,
                "size_bytes": 2_600,
            }

        with patch("webtools.fetch_page_text", fake_fetch_page_text), patch(
            "webtools.fetch_page_text_browser", fake_browser_fetch
        ):
            results = await enrich_search_results(
                [{"title": "Search Result", "url": "https://example.test/app", "snippet": "short"}]
            )

        self.assertEqual(results[0]["page_fetch_method"], "browser")
        self.assertEqual(results[0]["page_title"], "Rendered App")
        self.assertIn("Browser text", results[0]["page_excerpt"])

    async def test_preserves_result_when_fetching_fails(self) -> None:
        async def fail_fetch_page_text(url: str) -> dict:
            raise ValueError("blocked")

        async def fail_browser_fetch(url: str) -> dict:
            raise RuntimeError("browser unavailable")

        result = {"title": "Search Result", "url": "https://example.test/blocked", "snippet": "short"}
        with patch("webtools.fetch_page_text", fail_fetch_page_text), patch(
            "webtools.fetch_page_text_browser", fail_browser_fetch
        ):
            results = await enrich_search_results([result])

        self.assertEqual(results[0]["title"], result["title"])
        self.assertEqual(results[0]["snippet"], result["snippet"])
        self.assertNotIn("page_excerpt", results[0])

    def test_format_search_context_includes_page_excerpt(self) -> None:
        context = format_search_context(
            [
                {
                    "title": "Source",
                    "url": "https://example.test/source",
                    "snippet": "Search snippet",
                    "page_excerpt": "Full page detail",
                }
            ]
        )

        self.assertIn("Snippet: Search snippet", context)
        self.assertIn("Page excerpt: Full page detail", context)


if __name__ == "__main__":
    unittest.main()
