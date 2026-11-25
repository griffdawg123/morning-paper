"""Config loading: one YAML file, `${VAR}` placeholders filled from the environment.

Secrets stay out of the YAML: write `api_key: ${LLM_API_KEY}` and pass the
value as an env var. An unset variable becomes an empty string, which turns the
feature that needs it off (e.g. no SMTP password = don't send).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

_VAR = re.compile(r"\$\{([A-Z0-9_]+)\}")

DEFAULTS: dict[str, Any] = {
    "title": "The Morning Paper",
    "tagline": "All the news that fits on a Kindle",
    "timezone": "Australia/Sydney",
    "hemisphere": "south",  # for the season named to LLM-written sections
    "schedule": "06:00",
    # If the container starts after `schedule` but before this time and today's
    # paper hasn't gone out, build it straight away instead of waiting a day.
    "catch_up_until": "09:00",
    "data_dir": "/data",
    "max_age_hours": 26,
    "full_articles": 10,
    "min_article_words": 150,
    # Below this many stories the paper isn't sent and the run counts as failed
    # (so `serve` retries until catch_up_until): an outage upstream (FreshRSS
    # login, network) shouldn't mail you an empty paper.
    "min_stories": 1,
    "fetch_timeout": 20,
    "llm": {"base_url": "", "api_key": "", "models": [], "timeout": 180, "max_tokens": 4096},
    "freshrss": {"url": "", "user": "", "api_password": "", "mark_read": False},
    "delivery": {
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 465,
        "smtp_user": "",
        "smtp_password": "",
        "from": "",
        "to": [],
    },
    # Optional URL to GET after a successful send (e.g. an Uptime Kuma push
    # monitor), so a paper that silently stops arriving gets noticed.
    "heartbeat_url": "",
    # Optional ntfy push when the paper has been sent (so you know to sync the
    # Kindle) and when the day's run has failed for good. url = full topic URL.
    "notify": {"url": "", "token": "", "priority": "default", "tags": [], "click": "", "on_failure": True},
    "widgets": {},
    "sections": [],
}

SECTION_DEFAULTS: dict[str, Any] = {
    "category": [],  # FreshRSS category (label) name, or a list of them
    "feeds": [],  # extra feed URLs read directly, no FreshRSS needed
    "max_items": 6,  # headlines (with blurbs) in this section
    "max_full": 2,  # of those, how many get a full-text chapter
    "hint": "",  # extra guidance for the curator
    "generate": "",  # LLM-written section: the prompt (no feeds needed)
    "days": [],  # limit to weekdays, e.g. [sat, sun]; empty = every day
    "exclude": "",  # regex; items whose title matches are dropped before curation
}


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        return _VAR.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, list):
        return [_expand(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    return value


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def find_config(explicit: str | None) -> Path:
    for candidate in (explicit, os.environ.get("MORNING_PAPER_CONFIG"), "/config/paper.yml", "paper.yml"):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise SystemExit("No config found: pass --config, set MORNING_PAPER_CONFIG, or create paper.yml")


def load(path: str | Path) -> dict[str, Any]:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    cfg = _merge(DEFAULTS, _expand(raw))
    sections = []
    for s in cfg["sections"]:
        if "name" not in s:
            raise SystemExit(f"Every section needs a name: {s!r}")
        sec = _merge(SECTION_DEFAULTS, s)
        cat = sec["category"]
        sec["category"] = [c for c in ([cat] if isinstance(cat, str) else cat or []) if c]
        sections.append(sec)
    cfg["sections"] = sections
    if isinstance(cfg["delivery"].get("to"), str):
        cfg["delivery"]["to"] = [cfg["delivery"]["to"]]
    cfg["delivery"]["to"] = [t for t in cfg["delivery"]["to"] if t]
    cfg["llm"]["models"] = [m for m in cfg["llm"].get("models") or [] if m]
    return cfg
