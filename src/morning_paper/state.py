"""Small JSON state file: which stories already ran, and the day of the last scheduled run."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


class State:
    KEEP_DAYS = 30

    def __init__(self, data_dir: Path):
        self.path = data_dir / "state.json"
        try:
            raw = json.loads(self.path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            raw = {}
        self.seen: dict[str, str] = raw.get("seen", {})
        self.last_run: str = raw.get("last_run", raw.get("last_sent", ""))

    def is_seen(self, key: str) -> bool:
        return key in self.seen

    def mark_seen(self, keys: list[str]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        for k in keys:
            self.seen[k] = now

    def ran_on(self, day: date) -> bool:
        return self.last_run == day.isoformat()

    def save(self, run_day: date | None = None) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.KEEP_DAYS)).isoformat()
        self.seen = {k: v for k, v in self.seen.items() if v >= cutoff}
        if run_day:
            self.last_run = run_day.isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"last_run": self.last_run, "seen": self.seen}, indent=1))
        tmp.replace(self.path)
