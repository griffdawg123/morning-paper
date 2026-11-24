"""Pick, order and blurb each section's items; write LLM-generated sections.

One LLM call per section keeps prompts small enough for a local model. If the
LLM is off or fails, a section falls back to newest-first with the feed's own
snippet as the blurb, so a broken model never stops the paper going out.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

import markdown

from .llm import _THINK, LLM, LLMError
from .models import Item

log = logging.getLogger(__name__)

CURATE_SYSTEM = """You are the editor of a personal morning newspaper read on a Kindle.
From the candidate stories, choose the ones most worth the reader's time and put them in reading order.
Prefer substance over hype: skip listicles, press-release rewrites, deals/promotions and clickbait.
Never pick two candidates about the same event, even if worded differently or from different outlets:
keep only the most informative one. Check your picks for this before answering.
For each pick, write a one or two sentence blurb that says what actually happened or why it matters,
not a teaser. Use only facts stated in the candidate's title and snippet; never add names, numbers
or claims that aren't there. Mark "full": true on the picks that deserve to be read in full.
Reply with JSON only, no prose: {"picks": [{"id": <number>, "blurb": "...", "full": true|false}]}"""

GENERATE_SYSTEM = """You write one section of a personal morning newspaper read on a Kindle.
Write in Markdown: short headings, short paragraphs, plain lists. Don't repeat the section name
as a title. No preamble, no sign-off, no links you are not sure exist."""


def _fallback(items: list[Item], max_items: int, max_full: int) -> list[Item]:
    picked = sorted(items, key=lambda i: i.published or datetime.min.astimezone(), reverse=True)[:max_items]
    for n, item in enumerate(picked):
        item.blurb = item.snippet[:240]
        item.full = n < max_full
    return picked


def curate_section(llm: LLM, section: dict, items: list[Item], reader_profile: str) -> list[Item]:
    max_items, max_full = section["max_items"], section["max_full"]
    if not items:
        return []
    if not llm.enabled:
        return _fallback(items, max_items, max_full)

    # Newest first, capped, so a busy category doesn't blow the context window.
    candidates = sorted(items, key=lambda i: i.published or datetime.min.astimezone(), reverse=True)[:60]
    lines = []
    for n, item in enumerate(candidates):
        lines.append(f"[{n}] {item.title} | {item.source}\n    {item.snippet[:300]}")
    prompt = (
        f"Section: {section['name']}\n"
        f"Pick at most {max_items} stories; mark at most {max_full} as full.\n"
        + (f"Reader: {reader_profile}\n" if reader_profile else "")
        + (f"Section guidance: {section['hint']}\n" if section["hint"] else "")
        + "\nCandidates:\n"
        + "\n".join(lines)
    )
    try:
        data = llm.chat_json(CURATE_SYSTEM, prompt)
        picks = []
        seen: set[int] = set()
        for p in data.get("picks", []):
            idx = int(p.get("id", -1))
            if idx in seen or not 0 <= idx < len(candidates):
                continue
            seen.add(idx)
            item = candidates[idx]
            item.blurb = str(p.get("blurb") or item.snippet[:240]).strip()
            item.full = bool(p.get("full"))
            picks.append(item)
            if len(picks) >= max_items:
                break
        if not picks:
            raise LLMError("curator picked nothing")
        fulls = [i for i in picks if i.full]
        for extra in fulls[max_full:]:
            extra.full = False
        return picks
    except (LLMError, TypeError, ValueError) as e:
        log.warning("curate: %s fell back to newest-first (%s)", section["name"], e)
        return _fallback(items, max_items, max_full)


_LIST = re.compile(r"^\s*([*+-]|\d+[.)])\s")
_H1 = re.compile(r"</?h1>")

_SEASONS = ["winter", "winter", "spring", "spring", "spring", "summer",
            "summer", "summer", "autumn", "autumn", "autumn", "winter"]  # northern, by month


def season(month: int, hemisphere: str) -> str:
    s = _SEASONS[month - 1]
    if hemisphere.lower().startswith("s"):
        s = {"winter": "summer", "summer": "winter", "spring": "autumn", "autumn": "spring"}[s]
    return s


def generate_section(llm: LLM, section: dict, today: datetime, reader_profile: str, hemisphere: str = "south") -> str:
    if not llm.enabled:
        return ""
    prompt = (
        f"Today is {today:%A %-d %B %Y}; it is {season(today.month, hemisphere)} where the reader lives.\n"
        + (f"Reader: {reader_profile}\n" if reader_profile else "")
        + f"Section: {section['name']}\n\n{section['generate']}"
    )
    try:
        text = llm.chat(GENERATE_SYSTEM, prompt, temperature=0.8)
    except LLMError as e:
        log.warning("generate: %s skipped (%s)", section["name"], e)
        return ""
    text = _THINK.sub("", text).strip()
    # Models like to open with the section name as a heading; the page already has one.
    first, _, rest = text.partition("\n")
    if first.lstrip("# ").strip().lower() == section["name"].lower():
        text = rest.strip()
    # Markdown needs a blank line before a list; small models rarely leave one.
    lines: list[str] = []
    for line in text.splitlines():
        if _LIST.match(line) and lines and lines[-1].strip() and not _LIST.match(lines[-1]):
            lines.append("")
        lines.append(line)
    html = markdown.markdown("\n".join(lines), extensions=["sane_lists"])
    # The section page owns <h1>; keep generated headings below it.
    return _H1.sub(lambda m: m.group(0).replace("h1", "h2"), html)
