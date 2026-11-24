"""Full-text extraction: fetch the article page and keep just the story.

This is what fixes truncated feeds: the feed only has to point at the article.
If the page can't be fetched or extracted (paywall, JS-only site), the feed's
own content is used if it's long enough, otherwise the item stays a headline.
"""

from __future__ import annotations

import logging

import requests
import trafilatura

from . import USER_AGENT
from .models import Item
from .text import clean_html, word_count

log = logging.getLogger(__name__)

# Sites disagree: the Guardian 403s browser-looking UAs but serves an honest
# one, others only serve browsers. Try honest first, browser-ish on a 403.
_UAS = [USER_AGENT, "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"]


def fetch_article(url: str, timeout: int) -> str:
    for ua in _UAS:
        r = requests.get(url, headers={"User-Agent": ua}, timeout=timeout)
        if r.status_code != 403:
            break
    r.raise_for_status()
    out = trafilatura.extract(
        r.text,
        url=url,
        output_format="html",
        include_comments=False,
        include_images=False,
        include_tables=True,
        include_links=False,
        favor_precision=True,
    )
    return clean_html(out or "")


def fill(item: Item, timeout: int, min_words: int) -> bool:
    """Give `item` a body. Returns False (and demotes it) when there's nothing worth reading."""
    body = ""
    try:
        body = fetch_article(item.url, timeout)
    except Exception as e:  # noqa: BLE001 - any one article failing is fine
        log.info("extract: %s failed (%s)", item.url, e)
    if word_count(body) < min_words:
        fallback = clean_html(item.feed_html)
        if word_count(fallback) > word_count(body):
            body = fallback
    words = word_count(body)
    if words < min_words:
        log.info("extract: %s too short (%d words), headline only", item.url, words)
        item.full = False
        return False
    item.body_html, item.words = body, words
    return True
