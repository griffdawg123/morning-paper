"""Front-page widgets: small non-feed blocks (weather, calendar, ...).

A widget is a function `(options: dict, ctx: Context) -> str | None` returning
an HTML fragment, registered under a name with `@widget("name")`. The config's
`widgets:` mapping picks which ones run and in what order; the key is the
widget name unless the entry sets `type:` (so one widget can appear twice).
A failing widget is logged and left out; it never stops the paper.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)


@dataclass
class Context:
    now: datetime  # local, timezone-aware
    tz: ZoneInfo
    timeout: int


WidgetFn = Callable[[dict, Context], "str | None"]
REGISTRY: dict[str, tuple[str, WidgetFn]] = {}


def widget(name: str, heading: str):
    def register(fn: WidgetFn) -> WidgetFn:
        REGISTRY[name] = (heading, fn)
        return fn

    return register


def render_all(config: dict, ctx: Context) -> list[tuple[str, str]]:
    out = []
    for key, options in (config or {}).items():
        options = options or {}
        if options.get("enabled", True) is False:
            continue
        kind = options.get("type", key)
        if kind not in REGISTRY:
            log.warning("widget %s: unknown type %r", key, kind)
            continue
        default_heading, fn = REGISTRY[kind]
        try:
            html = fn(options, ctx)
        except Exception as e:  # noqa: BLE001
            log.warning("widget %s failed: %s", key, e)
            continue
        if html:
            out.append((options.get("heading", default_heading), html))
    return out


# Import for the registration side effect.
from . import calendar, kuma, onthisday, seerr, weather  # noqa: E402,F401
