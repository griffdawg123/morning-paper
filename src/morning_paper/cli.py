"""morning-paper run | serve | widgets"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config, notify, pipeline, widgets
from .state import State

log = logging.getLogger("morning_paper")


def _at(now: datetime, hhmm: str) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return now.replace(hour=h, minute=m, second=0, microsecond=0)


def serve(cfg_path: Path) -> None:
    """Sleep until `schedule` each day, then build and send. Config is re-read every run."""
    while True:
        cfg = config.load(cfg_path)
        tz = ZoneInfo(cfg["timezone"])
        now = datetime.now(tz)
        start, catch_up = _at(now, cfg["schedule"]), _at(now, cfg["catch_up_until"])
        ran_today = State(Path(cfg["data_dir"])).ran_on(now.date())
        if start <= now < catch_up and not ran_today:
            target = now
        else:
            target = start if now < start else _at(now + timedelta(days=1), cfg["schedule"])
        wait = (target - now).total_seconds()
        if wait > 0:
            log.info("serve: next paper at %s", target.isoformat(timespec="minutes"))
            # Sleep in chunks so a laptop suspend / clock change can't overshoot by hours.
            while (remaining := (target - datetime.now(tz)).total_seconds()) > 0:
                time.sleep(min(remaining, 300))
            cfg = config.load(cfg_path)
        try:
            pipeline.run(cfg)
        except Exception as e:  # noqa: BLE001
            # Inside the catch-up window this retries; after it, tomorrow.
            log.exception("serve: run failed; retrying in 15 minutes if still before catch_up_until")
            retry_at = datetime.now(tz) + timedelta(seconds=900)
            if retry_at >= _at(retry_at, cfg["catch_up_until"]):
                notify.failed(cfg, str(e) or type(e).__name__)  # last attempt today
            time.sleep(900)
        else:
            time.sleep(60)  # step past the scheduled minute


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="morning-paper")
    p.add_argument("--config", help="path to paper.yml")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="build (and send) one paper now")
    r.add_argument("--no-send", action="store_true", help="build only; don't email or mark anything")
    r.add_argument("--out", type=Path, help="where to write the EPUB")
    r.add_argument("--section", action="append", help="only this section (repeatable)")
    sub.add_parser("serve", help="run daily at the configured time")
    sub.add_parser("widgets", help="print the front-page widgets (quick config check)")
    a = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if a.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for noisy in ("trafilatura", "urllib3", "charset_normalizer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    cfg_path = config.find_config(a.config)
    if a.cmd == "serve":
        serve(cfg_path)
        return
    cfg = config.load(cfg_path)
    if a.cmd == "widgets":
        tz = ZoneInfo(cfg["timezone"])
        ctx = widgets.Context(now=datetime.now(tz), tz=tz, timeout=int(cfg["fetch_timeout"]))
        for heading, html in widgets.render_all(cfg["widgets"], ctx):
            print(f"== {heading}\n{html}\n")
        return
    path = pipeline.run(cfg, send=not a.no_send, out=a.out, only=a.section)
    print(path)


if __name__ == "__main__":
    main()
