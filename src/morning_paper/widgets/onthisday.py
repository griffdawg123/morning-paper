"""A few "on this day" events from Wikipedia's feed API."""

from __future__ import annotations

import random

import requests

from .. import USER_AGENT
from ..text import esc
from . import Context, widget


@widget("on_this_day", "On this day")
def on_this_day(opts: dict, ctx: Context) -> str | None:
    r = requests.get(
        f"https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/selected/{ctx.now:%m}/{ctx.now:%d}",
        headers={"User-Agent": USER_AGENT},
        timeout=ctx.timeout,
    )
    r.raise_for_status()
    events = r.json().get("selected", [])
    if not events:
        return None
    # Same picks if the paper is rebuilt on the same day.
    rng = random.Random(ctx.now.strftime("%Y%m%d"))
    picks = sorted(rng.sample(events, min(int(opts.get("count", 3)), len(events))), key=lambda e: e.get("year", 0))
    return "<ul>" + "".join(f"<li><strong>{e.get('year')}</strong>: {esc(e.get('text', ''))}</li>" for e in picks) + "</ul>"
