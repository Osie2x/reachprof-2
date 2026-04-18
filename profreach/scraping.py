from __future__ import annotations
import time
import httpx
from bs4 import BeautifulSoup
from readability import Document

USER_AGENT = "profreach/0.1 (research outreach tool; owner contact: see repo)"
REQUEST_DELAY_SECONDS = 1.0


def fetch_page(url: str) -> str:
    """Fetch a page with polite defaults. Returns raw HTML."""
    time.sleep(REQUEST_DELAY_SECONDS)
    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=20,
        follow_redirects=True,
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def load_fixture(path: str) -> str:
    """Load a synthetic fixture HTML for dev/testing."""
    with open(path) as f:
        return f.read()


def html_to_clean_text(html: str) -> str:
    """Strip boilerplate (nav, footer, sidebar) and return readable text.

    First tries readability-lxml for main-content extraction. If the result is
    shorter than 400 characters, falls back to a full-page BS4 extraction that
    strips nav/footer/sidebar/script/style tags but keeps the rest.
    """
    doc = Document(html)
    cleaned_html = doc.summary()
    soup = BeautifulSoup(cleaned_html, "lxml")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)

    if len(text) < 800:
        # readability chose a fragment that's too small; fall back to full page
        full_soup = BeautifulSoup(html, "lxml")
        for tag in full_soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        # also remove obvious sidebar divs
        for sid in full_soup.find_all(id=lambda x: x and any(
            kw in x.lower() for kw in ("sidebar", "nav", "header", "footer", "breadcrumb", "top-bar")
        )):
            sid.decompose()
        text = full_soup.get_text(separator="\n", strip=True)

    return text
