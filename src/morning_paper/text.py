"""Small HTML/text helpers shared by sources, extraction and the EPUB builder."""

from __future__ import annotations

import html
import re

from lxml import etree
from lxml import html as lhtml
from lxml_html_clean import Cleaner

_WS = re.compile(r"\s+")

_cleaner = Cleaner(
    scripts=True,
    javascript=True,
    comments=True,
    style=True,
    inline_style=True,
    links=True,
    meta=True,
    page_structure=True,
    processing_instructions=True,
    embedded=True,
    frames=True,
    forms=True,
    annoying_tags=True,
    remove_unknown_tags=False,
    safe_attrs_only=True,
    safe_attrs=frozenset({"href", "alt", "title", "colspan", "rowspan"}),
    kill_tags={"img", "picture", "figure", "svg", "video", "audio", "iframe", "noscript", "button"},
)

_ALLOWED = {
    "p", "br", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "blockquote",
    "pre", "code", "em", "strong", "b", "i", "u", "a", "table", "thead", "tbody",
    "tr", "td", "th", "hr", "sub", "sup", "dl", "dt", "dd", "span", "div", "cite", "q",
}


def to_text(fragment: str, limit: int | None = None) -> str:
    """HTML (or plain text) -> collapsed plain text."""
    if not fragment:
        return ""
    try:
        text = lhtml.fromstring(fragment).text_content() if "<" in fragment else fragment
    except (etree.ParserError, ValueError):
        text = fragment
    text = _WS.sub(" ", html.unescape(text)).strip()
    if limit and len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0] + "…"
    return text


def clean_html(fragment: str) -> str:
    """Untrusted article HTML -> a conservative XHTML fragment that EPUB readers accept."""
    if not fragment or not fragment.strip():
        return ""
    try:
        doc = lhtml.fragment_fromstring(fragment, create_parent="div")
        doc = _cleaner.clean_html(doc)
    except (etree.ParserError, ValueError):
        return f"<p>{html.escape(to_text(fragment))}</p>"
    for el in list(doc.iter()):
        if not isinstance(el.tag, str):
            continue
        if el.tag not in _ALLOWED:
            el.drop_tag()
        elif el.tag == "a":
            href = el.get("href", "")
            if not href.startswith(("http://", "https://")):
                el.drop_tag()
    out = []
    if doc.text and doc.text.strip():
        out.append(f"<p>{html.escape(doc.text.strip())}</p>")
    for child in doc:
        out.append(etree.tostring(child, method="xml", encoding="unicode"))
    return "".join(out)


def word_count(fragment: str) -> int:
    return len(to_text(fragment).split())


def esc(s: str) -> str:
    return html.escape(s or "", quote=True)
