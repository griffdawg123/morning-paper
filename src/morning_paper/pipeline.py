"""gather -> curate -> extract -> build -> deliver."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from . import curate, deliver, epub, extract, sources, widgets
from .llm import LLM
from .models import Edition, Item, Section
from .state import State

log = logging.getLogger(__name__)

class EmptyPaper(RuntimeError):
    pass


DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def run(cfg: dict, send: bool = True, out: Path | None = None, only: list[str] | None = None) -> Path:
    tz = ZoneInfo(cfg["timezone"])
    now = datetime.now(tz)
    data_dir = Path(cfg["data_dir"])
    state = State(data_dir)
    since = sources.since(int(cfg["max_age_hours"]))
    llm = LLM(**cfg["llm"])
    timeout = int(cfg["fetch_timeout"])
    profile = cfg.get("reader_profile", "")

    today = DAYS[now.weekday()]
    section_cfgs = [
        s for s in cfg["sections"]
        if (not s["days"] or today in [d.lower()[:3] for d in s["days"]])
        and (not only or s["name"] in only)
    ]

    # --- gather -----------------------------------------------------------
    fresh = None
    if cfg["freshrss"]["url"] and any(s["category"] for s in section_cfgs):
        f = cfg["freshrss"]
        try:
            fresh = sources.FreshRSS(f["url"], f["user"], f["api_password"], timeout)
        except Exception as e:  # noqa: BLE001
            log.error("freshrss: login failed (%s); FreshRSS sections will be empty", e)

    claimed: set[str] = set()  # a story appears in one section only
    gathered: list[tuple[dict, list[Item]]] = []
    for s in section_cfgs:
        items: list[Item] = []
        for cat in s["category"] if fresh else []:
            try:
                items += fresh.category(cat, since)
            except Exception as e:  # noqa: BLE001
                log.warning("freshrss: category %r failed (%s)", cat, e)
        for url in s["feeds"]:
            try:
                items += sources.read_feed(url, since, timeout)
            except Exception as e:  # noqa: BLE001
                log.warning("feed %s failed (%s)", url, e)
        exclude = re.compile(s["exclude"], re.I) if s["exclude"] else None
        unique = []
        for it in items:
            if it.id in claimed or state.is_seen(it.id):
                continue
            if exclude and exclude.search(it.title):
                continue
            claimed.add(it.id)
            unique.append(it)
        log.info("gather: %s: %d new of %d", s["name"], len(unique), len(items))
        gathered.append((s, unique))

    # --- curate -----------------------------------------------------------
    sections: list[Section] = []
    for s, items in gathered:
        sec = Section(name=s["name"])
        if s["generate"]:
            sec.generated_html = curate.generate_section(llm, s, now, profile, cfg["hemisphere"])
        sec.items = curate.curate_section(llm, s, items, profile)
        sections.append(sec)

    # Global cap on full-text chapters, earlier sections first.
    budget = int(cfg["full_articles"])
    for sec in sections:
        for it in sec.items:
            if it.full:
                if budget > 0:
                    budget -= 1
                else:
                    it.full = False

    # --- extract ----------------------------------------------------------
    wanted = [it for sec in sections for it in sec.items if it.full]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda it: extract.fill(it, timeout, int(cfg["min_article_words"])), wanted))

    # --- widgets + build --------------------------------------------------
    ed = Edition(
        title=cfg["title"],
        tagline=cfg["tagline"],
        date=now,
        front_page=widgets.render_all(cfg["widgets"], widgets.Context(now=now, tz=tz, timeout=timeout)),
        sections=[s for s in sections if s.items or s.generated_html],
    )
    path = out or data_dir / "archive" / f"{cfg['title']} {now:%Y-%m-%d}.epub"
    epub.build(ed, path, font_dir=str(data_dir / "fonts"))
    n_items = sum(len(s.items) for s in ed.sections)
    n_full = sum(1 for s in ed.sections for i in s.items if i.full)
    log.info("build: %s (%d sections, %d stories, %d full)", path, len(ed.sections), n_items, n_full)

    # --- deliver ----------------------------------------------------------
    if not send:
        return path
    if n_items < int(cfg["min_stories"]):
        raise EmptyPaper(f"only {n_items} stories (min_stories={cfg['min_stories']}); not sending {path.name}")
    if not deliver.can_send(cfg):
        log.warning("deliver: SMTP not configured, built only")
        state.save(run_day=now.date())
        return path
    deliver.send(cfg, path, f"{cfg['title']}: {now:%A %-d %B %Y}")

    used = [it for s in ed.sections for it in s.items]
    state.mark_seen([it.id for it in used])
    state.save(run_day=now.date())
    if fresh and cfg["freshrss"].get("mark_read"):
        try:
            fresh.mark_read([it.freshrss_id for it in used])
        except Exception as e:  # noqa: BLE001
            log.warning("freshrss: mark read failed (%s)", e)
    if cfg["heartbeat_url"]:
        try:
            requests.get(cfg["heartbeat_url"], params={"status": "up", "msg": f"{n_items} stories"}, timeout=15)
        except requests.RequestException as e:
            log.warning("heartbeat failed (%s)", e)
    return path
