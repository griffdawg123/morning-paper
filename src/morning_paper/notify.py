"""Push notifications via ntfy (https://ntfy.sh or self-hosted).

`notify.url` is the full topic URL (e.g. http://ntfy.example:8080/morning-paper).
One message when a paper has been emailed to the Kindle ("sync now"), and one
when the day's run has failed for good. A failed notification is logged and
ignored; it never fails the paper.
"""

from __future__ import annotations

import logging

import requests

from . import USER_AGENT

log = logging.getLogger(__name__)


def _post(cfg: dict, title: str, message: str, priority: str, tags: list[str]) -> None:
    n = cfg.get("notify") or {}
    if not n.get("url"):
        return
    headers = {
        "User-Agent": USER_AGENT,
        "Title": title,
        "Priority": str(priority),
        "Tags": ",".join(tags),
    }
    if n.get("token"):
        headers["Authorization"] = f"Bearer {n['token']}"
    if n.get("click"):
        headers["Click"] = n["click"]
    try:
        r = requests.post(n["url"], data=message.encode(), headers=headers, timeout=15)
        r.raise_for_status()
    except requests.RequestException as e:
        log.warning("notify: ntfy post failed (%s)", e)


def published(cfg: dict, subject: str, sections: int, stories: int, full: int) -> None:
    n = cfg.get("notify") or {}
    _post(
        cfg,
        f"{cfg['title']} is out",
        f"{subject}\n{stories} stories in {sections} sections ({full} full). "
        "Sent to your Kindle: sync in a minute or two to get it.",
        n.get("priority", "default"),
        n.get("tags") or ["newspaper"],
    )


def failed(cfg: dict, error: str) -> None:
    n = cfg.get("notify") or {}
    if not n.get("on_failure", True):
        return
    _post(cfg, f"{cfg['title']} failed", f"No paper today: {error}", "high", ["warning", "newspaper"])
