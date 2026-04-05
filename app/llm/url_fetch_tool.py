"""URL fetch tool: fetches a URL and returns truncated page content."""

from __future__ import annotations

import asyncio
import logging

import httpx
from bs4 import BeautifulSoup
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)

_FETCH_TIMEOUT = 8
_MAX_BODY_CHARS = 12000
_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class URLFetchTool(BaseTool):
    """Fetches a URL and returns the page text content."""

    name: str = "fetch_url"
    description: str = (
        "Fetch a URL and return its page content. "
        "Input should be a single URL string. "
        "Returns the page text (truncated) or an error message."
    )

    def _run(self, url: str) -> str:
        try:
            with httpx.Client(timeout=_FETCH_TIMEOUT, headers=_BROWSER_HEADERS) as client:
                resp = client.get(url.strip(), follow_redirects=True)
                status = resp.status_code
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
                lines = [line for line in text.splitlines() if line.strip()]
                body = "\n".join(lines)[:_MAX_BODY_CHARS]
                return f"HTTP {status}\n\n{body}"
        except Exception as exc:
            return f"Fetch error: {exc}"

    async def _arun(self, url: str) -> str:
        return await asyncio.to_thread(self._run, url)
