"""Media that became available in the last day, from Seerr (Overseerr/Jellyseerr).

Logs in as a normal (non-admin) Seerr user with the "View Requests" permission,
so no admin API key is needed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from .. import USER_AGENT
from ..text import esc
from . import Context, widget


@widget("seerr", "New on Jellyfin")
def seerr(opts: dict, ctx: Context) -> str | None:
    base = opts["url"].rstrip("/") + "/api/v1"
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    if not (opts.get("email") and opts.get("password")):
        return None
    r = s.post(f"{base}/auth/local", json={"email": opts["email"], "password": opts["password"]}, timeout=ctx.timeout)
    r.raise_for_status()
    r = s.get(f"{base}/request", params={"take": 30, "filter": "available", "sort": "modified"}, timeout=ctx.timeout)
    r.raise_for_status()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=int(opts.get("hours", 24)))
    names = []
    for req in r.json().get("results", []):
        media = req.get("media") or {}
        stamp = media.get("updatedAt") or req.get("updatedAt")
        if not stamp or datetime.fromisoformat(stamp.replace("Z", "+00:00")) < cutoff:
            continue
        kind = req.get("type") or media.get("mediaType")
        tmdb = media.get("tmdbId")
        if not tmdb or kind not in ("movie", "tv"):
            continue
        d = s.get(f"{base}/{kind}/{tmdb}", timeout=ctx.timeout)
        if not d.ok:
            continue
        info = d.json()
        title = info.get("title") or info.get("name") or f"TMDB {tmdb}"
        year = (info.get("releaseDate") or info.get("firstAirDate") or "")[:4]
        label = "Film" if kind == "movie" else "Show"
        entry = f"<li><strong>{esc(title)}</strong>{f' ({year})' if year else ''}, {label}</li>"
        if entry not in names:
            names.append(entry)
    if not names:
        return None if opts.get("hide_when_empty", True) else "<p>Nothing new overnight.</p>"
    return "<ul>" + "".join(names) + "</ul>"
