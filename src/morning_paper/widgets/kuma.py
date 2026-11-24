"""Overnight homelab status from an Uptime Kuma public status page.

Needs a status page in Kuma (Status Pages > New) listing the monitors you care
about; its slug goes in `status_page`. Only reads the public status-page API.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from .. import USER_AGENT
from ..text import esc
from . import Context, widget

DOWN, UP = 0, 1


@widget("kuma", "Homelab")
def kuma(opts: dict, ctx: Context) -> str | None:
    base = opts["url"].rstrip("/")
    slug = opts["status_page"]
    h = {"User-Agent": USER_AGENT}
    page = requests.get(f"{base}/api/status-page/{slug}", headers=h, timeout=ctx.timeout)
    page.raise_for_status()
    names = {
        str(m["id"]): m["name"]
        for g in page.json().get("publicGroupList", [])
        for m in g.get("monitorList", [])
    }
    beats = requests.get(f"{base}/api/status-page/heartbeat/{slug}", headers=h, timeout=ctx.timeout)
    beats.raise_for_status()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=int(opts.get("hours", 12)))

    down_now, blipped = [], []
    for mid, history in beats.json().get("heartbeatList", {}).items():
        name = names.get(str(mid), f"monitor {mid}")
        recent = []
        for b in history:
            # Kuma reports heartbeat times in UTC, without an offset.
            t = datetime.fromisoformat(b["time"].replace(" ", "T")[:19]).replace(tzinfo=timezone.utc)
            if t >= cutoff:
                recent.append(b)
        if history and history[-1].get("status") == DOWN:
            down_now.append(name)
        elif any(b.get("status") == DOWN for b in recent):
            blipped.append(name)

    if down_now:
        out = f"<p><strong>Down now:</strong> {esc(', '.join(sorted(down_now)))}.</p>"
    else:
        out = f"<p>All {len(names)} monitored services are up.</p>"
    if blipped:
        out += f"<p>Had an outage overnight but recovered: {esc(', '.join(sorted(blipped)))}.</p>"
    return out
