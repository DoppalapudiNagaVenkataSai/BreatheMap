"""Accessibility and HTML landmark static tests."""

from html.parser import HTMLParser

import pytest
from httpx import AsyncClient


class AccessibilityParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.h1_count = 0
        self.has_lang = False
        self.has_skip_link = False
        self.has_main = False
        self.inputs_without_labels: list[str] = []
        self.current_labels: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        if tag == "html" and "lang" in attr_dict:
            self.has_lang = True
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "a" and attr_dict.get("href") == "#main":
            self.has_skip_link = True
        elif tag == "main" and attr_dict.get("id") == "main":
            self.has_main = True
        elif tag == "label" and "for" in attr_dict:
            label_for = attr_dict.get("for")
            if label_for:
                self.current_labels.add(label_for)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/", "/about", "/route", "/assistant", "/watch"])
async def test_page_accessibility_and_landmarks(client: AsyncClient, path: str) -> None:
    res = await client.get(path)
    assert res.status_code == 200
    html = res.text

    parser = AccessibilityParser()
    parser.feed(html)

    # WCAG AA assertions
    assert parser.has_lang is True, f"Missing html lang on {path}"
    assert parser.has_skip_link is True, f"Missing skip-link on {path}"
    assert parser.has_main is True, f"Missing main id='main' on {path}"
    assert parser.h1_count == 1, f"Expected exactly one <h1> on {path}, got {parser.h1_count}"
    if path == "/route":
        assert 'role="region"' in html and 'aria-label="Route comparison map"' in html
