"""Where candidate stories come from: FreshRSS categories and plain feeds."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import feedparser
import requests

from . import USER_AGENT
from .models import Item
from .text import to_text

log = logging.getLogger(__name__)

_BARE_VERSION = re.compile(r"^(v|version\s*)?\d+(\.\d+)*\S*$", re.I)
_RELEASE_FEED = re.compile(r"^release notes from\s+", re.I)


def display_title(title: str, source: str) -> str:
    """GitHub release titles are often just "v3.3.5": prefix the project name."""
    if _BARE_VERSION.match(title.strip()) and source:
        return f"{_RELEASE_FEED.sub('', source).strip()} {title.strip()}"
    return title

READ_TAG = "user/-/state/com.google/reader/read"


class FreshRSS:
    """FreshRSS via its Google Reader-compatible API.

    Needs "Allow API access" on in FreshRSS (Settings > Authentication) and an
    API password set for the user (Settings > Profile > API management).
    """

    def __init__(self, url: str, user: str, api_password: str, timeout: int = 20):
        self.base = url.rstrip("/") + "/api/greader.php"
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers["User-Agent"] = USER_AGENT
        r = self.s.post(
            f"{self.base}/accounts/ClientLogin",
            data={"Email": user, "Passwd": api_password},
            timeout=timeout,
        )
        r.raise_for_status()
        auth = next((line[5:] for line in r.text.splitlines() if line.startswith("Auth=")), None)
        if not auth:
            raise RuntimeError("FreshRSS login returned no Auth token")
        self.s.headers["Authorization"] = f"GoogleLogin auth={auth}"

    def category(self, name: str, since: datetime, limit: int = 200) -> list[Item]:
        stream = quote(f"user/-/label/{name}", safe="")
        r = self.s.get(
            f"{self.base}/reader/api/0/stream/contents/{stream}",
            params={"n": limit, "ot": int(since.timestamp()), "output": "json"},
            timeout=self.timeout,
        )
        r.raise_for_status()
        items = []
        for e in r.json().get("items", []):
            links = e.get("canonical") or e.get("alternate") or []
            url = links[0].get("href") if links else None
            if not url:
                continue
            body = (e.get("content") or e.get("summary") or {}).get("content", "")
            source = (e.get("origin") or {}).get("title", "")
            items.append(
                Item(
                    id=url,
                    url=url,
                    title=display_title(to_text(e.get("title", "")) or url, source),
                    source=source,
                    published=datetime.fromtimestamp(int(e.get("published", 0)), timezone.utc),
                    snippet=to_text(body, 400),
                    feed_html=body,
                    author=e.get("author", ""),
                    freshrss_id=e.get("id", ""),
                )
            )
        return items

    def mark_read(self, ids: list[str]) -> None:
        ids = [i for i in ids if i]
        if not ids:
            return
        token = self.s.get(f"{self.base}/reader/api/0/token", timeout=self.timeout).text.strip()
        r = self.s.post(
            f"{self.base}/reader/api/0/edit-tag",
            data=[("a", READ_TAG), ("T", token)] + [("i", i) for i in ids],
            timeout=self.timeout,
        )
        r.raise_for_status()


def read_feed(url: str, since: datetime, timeout: int = 20) -> list[Item]:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    source = feed.feed.get("title", url)
    items = []
    for e in feed.entries:
        link = e.get("link")
        if not link:
            continue
        stamp = e.get("published_parsed") or e.get("updated_parsed")
        published = datetime(*stamp[:6], tzinfo=timezone.utc) if stamp else None
        if published and published < since:
            continue
        body = ""
        if e.get("content"):
            body = e.content[0].get("value", "")
        body = body or e.get("summary", "")
        items.append(
            Item(
                id=link,
                url=link,
                title=display_title(to_text(e.get("title", "")) or link, source),
                source=source,
                published=published,
                snippet=to_text(body, 400),
                feed_html=body,
                author=e.get("author", ""),
            )
        )
    return items


def since(max_age_hours: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
