"""
run.py  --  TDA-RiskPulse daily daemon.

A long-running process that, once per **weekday** (Sat/Sun are skipped):
    1. imports the latest daily prices into stocks.db (incremental fetch), then
    2. runs the magnitude-pulse analysis, and
    3. saves a dated snapshot to  results/YYYY_MM_DD.png

so you can open the latest image each day to check the current status.

It is idempotent per day: the snapshot file's existence is the "already ran
today" marker, so restarting the daemon never double-runs or loses a day. A
failed job (e.g. a network hiccup) is logged and retried on the next poll.

Usage (from the project root, with the venv):
    # run the daemon (foreground; leave it running, e.g. in its own terminal):
    .\\.venv\\Scripts\\python.exe run.py

    # produce today's snapshot once and exit (manual / testing):
    .\\.venv\\Scripts\\python.exe run.py --run-once

    # same, but skip the price import and use the cache as-is (fast):
    .\\.venv\\Scripts\\python.exe run.py --run-once --no-fetch

On a Linux server use ./.venv/bin/python. The recommended server setup is cron
firing one job per weekday at 22:00 UTC (after the US close):
    0 22 * * 1-5  cd /path/to/repo && .venv/bin/python run.py --run-once --utc >> results/cron.log 2>&1

Options: --utc (UTC basis for the date stamp + run-hour, use on a server),
--run-hour (wait until the hour >= H, default 1; pair with --utc 22 for the
daemon), --poll (daemon check interval in seconds), --results-dir, --no-fetch.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import date, datetime, timezone

# run.py lives at the project root; make the src/ modules importable.
_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import config
import data_fetcher
import db
import magnitude_pulse

RUN_HOUR = 1            # only auto-run once local hour >= this (data-freshness guard)
POLL_SECONDS = 1800     # daemon poll interval (30 min)

logger = logging.getLogger("tda_daemon")


# ---------------------------------------------------------------------------
# Pure scheduling helpers (unit-tested)
# ---------------------------------------------------------------------------

def is_weekday(d: date) -> bool:
    """True Mon–Fri; False Sat/Sun (markets closed)."""
    return d.weekday() < 5


def snapshot_path(d: date, results_dir: str) -> str:
    """Dated snapshot path:  <results_dir>/YYYY_MM_DD.png."""
    return os.path.join(results_dir, d.strftime("%Y_%m_%d") + ".png")


def due_today(now: datetime, run_hour: int, results_dir: str) -> bool:
    """Should the daemon run the job at `now`?

    True only when it is a weekday, the local hour has reached `run_hour`, and
    today's snapshot has not been produced yet.
    """
    return (is_weekday(now.date())
            and now.hour >= run_hour
            and not os.path.exists(snapshot_path(now.date(), results_dir)))


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_once(day: date, results_dir: str = config.OUTPUT_DIR,
             fetch: bool = True) -> str:
    """Import latest prices (optional) then render the dated snapshot."""
    out = snapshot_path(day, results_dir)
    logger.info("=== daily job for %s -> %s ===", day, out)

    if fetch:
        symbols = [*config.TDA_TICKERS, config.BENCHMARK_INDEX]
        logger.info("Importing latest prices for %d symbols ...", len(symbols))
        conn = db.connect(config.DB_PATH)
        try:
            data_fetcher.fetch_to_db(conn, symbols, config.START_DATE,
                                     day.strftime("%Y-%m-%d"))
        finally:
            conn.close()
    else:
        logger.info("--no-fetch: using the cache as-is.")

    logger.info("Running magnitude-pulse analysis ...")
    magnitude_pulse.run(out_path=out)
    logger.info("Snapshot saved: %s", out)
    return out


def _now(use_utc: bool) -> datetime:
    """Current time in UTC (`use_utc`) or the server's local zone."""
    return datetime.now(timezone.utc) if use_utc else datetime.now()


def daemon(run_hour: int, poll_seconds: int, results_dir: str,
           use_utc: bool = False) -> None:
    """Loop forever; run the daily job once per weekday."""
    logger.info("Daemon started (run_hour=%d %s, poll=%ds, results=%s). "
                "Sat/Sun are skipped.", run_hour, "UTC" if use_utc else "local",
                poll_seconds, results_dir)
    while True:
        now = _now(use_utc)
        if due_today(now, run_hour, results_dir):
            try:
                run_once(now.date(), results_dir)
            except Exception:
                logger.exception("daily job failed; will retry on the next poll")
        time.sleep(poll_seconds)


def _setup_logging(results_dir: str) -> None:
    os.makedirs(results_dir, exist_ok=True)
    handlers = [logging.StreamHandler(),
                logging.FileHandler(os.path.join(results_dir, "run.log"))]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )


def main() -> None:
    p = argparse.ArgumentParser(description="TDA-RiskPulse daily daemon.")
    p.add_argument("--run-once", action="store_true",
                   help="Run one job now and exit (ignores the weekday/hour guards).")
    p.add_argument("--no-fetch", action="store_true",
                   help="Skip the price import; analyse the cache as-is.")
    p.add_argument("--run-hour", type=int, default=RUN_HOUR,
                   help="Auto-run only once the hour >= this (default 1).")
    p.add_argument("--utc", action="store_true",
                   help="Use UTC for the run-hour check and the YYYY_MM_DD date stamp "
                        "(recommended on a server; pairs with --run-hour 22).")
    p.add_argument("--poll", type=int, default=POLL_SECONDS,
                   help="Daemon poll interval in seconds (default 1800).")
    p.add_argument("--results-dir", default=config.OUTPUT_DIR,
                   help="Where to write YYYY_MM_DD.png (default results/).")
    args = p.parse_args()

    _setup_logging(args.results_dir)

    if args.run_once:
        run_once(_now(args.utc).date(), args.results_dir, fetch=not args.no_fetch)
        return
    daemon(args.run_hour, args.poll, args.results_dir, use_utc=args.utc)


if __name__ == "__main__":
    main()
