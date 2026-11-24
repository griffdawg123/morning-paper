"""Today's events from one or more iCal URLs.

For Google Calendar use the calendar's "Secret address in iCal format"
(Settings > the calendar > Integrate calendar). Treat it like a password.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import icalendar
import recurring_ical_events
import requests

from .. import USER_AGENT
from ..text import esc
from . import Context, widget


@widget("calendar", "Today")
def calendar(opts: dict, ctx: Context) -> str | None:
    urls = opts.get("ical_urls") or [opts.get("ical_url")]
    urls = [u for u in urls if u]
    if not urls:
        return None
    start = ctx.now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    events = []
    for url in urls:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=ctx.timeout)
        r.raise_for_status()
        cal = icalendar.Calendar.from_ical(r.content)
        for ev in recurring_ical_events.of(cal).between(start, end):
            dt = ev.get("DTSTART").dt
            all_day = not isinstance(dt, datetime)
            when = start if all_day else dt.astimezone(ctx.tz)
            events.append((all_day, when, str(ev.get("SUMMARY", "")), str(ev.get("LOCATION", "") or "")))
    if not events:
        return f"<p>{esc(opts.get('empty_text', 'Nothing in the calendar today.'))}</p>"
    events.sort(key=lambda e: (not e[0], e[1]))
    rows = []
    for all_day, when, summary, location in events:
        t = "All day" if all_day else when.strftime("%-I:%M%p").lower()
        loc = f" <em>({esc(location)})</em>" if location else ""
        rows.append(f"<li><strong>{t}</strong> {esc(summary)}{loc}</li>")
    return "<ul>" + "".join(rows) + "</ul>"

