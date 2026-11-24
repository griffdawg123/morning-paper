from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Item:
    """One candidate story from a feed."""

    id: str  # stable key: the article URL
    url: str
    title: str
    source: str
    published: datetime | None = None
    snippet: str = ""  # plain text, for the curator
    feed_html: str = ""  # whatever HTML the feed carried (fallback body)
    author: str = ""
    freshrss_id: str = ""  # so it can be marked read afterwards
    # Filled in by curation / extraction:
    blurb: str = ""
    full: bool = False
    body_html: str = ""
    words: int = 0


@dataclass
class Section:
    name: str
    items: list[Item] = field(default_factory=list)  # in reading order
    generated_html: str = ""  # LLM-written sections


@dataclass
class Edition:
    title: str
    tagline: str
    date: datetime
    front_page: list[tuple[str, str]] = field(default_factory=list)  # (heading, html)
    sections: list[Section] = field(default_factory=list)
