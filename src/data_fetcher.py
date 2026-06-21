"""
data_fetcher.py  --  TDA-RiskPulse Module 1 (Data Ingestion Engine)

Responsibilities (SPEC §3, Module 1):
    1. Cache-aware download of ADJUSTED daily OHLCV for the ticker basket +
       benchmark into the SQLite store (db.py). First run backfills ~20y;
       later runs only top up the missing tail.
    2. Transform the cached prices into a strictly-aligned, stationary
       log-return matrix:  R[i,t] = ln(P[i,t] / P[i,t-1]).

Data-integrity handling:
    * yfinance is called with auto_adjust=True so splits/dividends are baked
      into Close (the SPEC's "adjusted close" requirement).
    * Assets missing more than MISSING_THRESHOLD of rows over the analysis
      window are dropped, giving a FIXED point-cloud size N across every
      rolling window (required for the batched TDA engine). This is the
      pragmatic stand-in for the SPEC §4 per-slice substitution rule and is
      reported explicitly at runtime.
    * Remaining short gaps are forward-filled; any row still containing a NaN
      is dropped so the correlation matrices never see misaligned data.

CLI:
    python src/data_fetcher.py --build-db      # fetch/refresh the cache
    python src/data_fetcher.py --build-db --start 2010-01-01 --end 2024-12-31
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from datetime import datetime, timedelta
from typing import Iterable

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError:  # pragma: no cover - import guard
    print("ERROR: yfinance is required.  Run:  pip install -r requirements.txt")
    sys.exit(1)

import config
import db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def _download(symbol: str, start: str, end_exclusive: str) -> pd.DataFrame:
    """Download adjusted daily OHLCV for one symbol; return a clean DataFrame.

    Reuses the timezone-normalization pattern from the original single-asset
    fetcher. yfinance's `end` is exclusive, so callers pass an exclusive end.
    """
    hist = yf.Ticker(symbol).history(
        start=start, end=end_exclusive, interval="1d", auto_adjust=True
    )
    if hist is None or hist.empty:
        return pd.DataFrame()

    cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in hist.columns]
    df = hist[cols].copy()

    # Normalise the index to tz-naive midnight timestamps.
    if hasattr(df.index, "tz") and df.index.tz is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)
    df.index = pd.to_datetime(df.index).normalize()
    df.index.name = "Date"
    return df


def fetch_to_db(
    conn: sqlite3.Connection,
    symbols: Iterable[str],
    start: str,
    end: str,
    force: bool = False,
) -> None:
    """Populate/refresh the SQLite cache for `symbols` over [start, end].

    Incremental by default: only the span after each symbol's latest cached
    date is downloaded. `force=True` re-downloads the full [start, end] span.
    """
    # yfinance end is exclusive -> add a day so `end` itself is included.
    end_exclusive = (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    symbols = list(symbols)

    for i, symbol in enumerate(symbols, 1):
        sym_start = start
        if not force:
            latest = db.get_latest_dt(conn, symbol)
            if latest is not None:
                # Resume from the day after the last cached date.
                latest_date = datetime.strptime(str(latest), "%Y%m%d")
                if latest_date.date() >= pd.Timestamp(end).date():
                    logger.info("[%d/%d] %s up to date, skipping",
                                i, len(symbols), symbol)
                    continue
                sym_start = (latest_date + timedelta(days=1)).strftime("%Y-%m-%d")

        logger.info("[%d/%d] downloading %s from %s", i, len(symbols), symbol, sym_start)
        try:
            df = _download(symbol, sym_start, end_exclusive)
        except Exception as exc:  # network / ticker errors shouldn't abort the run
            logger.error("  %s download failed: %s", symbol, exc)
            continue

        n = db.upsert_prices(conn, symbol, df)
        logger.info("  %s: cached %d rows", symbol, n)


# ---------------------------------------------------------------------------
# Transform  ->  aligned log-return matrix
# ---------------------------------------------------------------------------

def build_returns(
    conn: sqlite3.Connection,
    tickers: Iterable[str] | None = None,
    benchmark: str | None = None,
    start: str | None = None,
    end: str | None = None,
    missing_threshold: float = config.MISSING_THRESHOLD,
) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    """Build the stationary log-return matrix from the cache.

    Returns:
        returns:   wide DataFrame (DatetimeIndex x kept tickers) of daily log
                   returns, strictly aligned with no NaN.
        benchmark: adjusted-close price Series for the benchmark (for Panel A).
        kept:      the tickers that survived the coverage filter (the fixed
                   point-cloud, in basket order).
    """
    tickers = list(tickers) if tickers is not None else list(config.TDA_TICKERS)
    benchmark = benchmark or config.BENCHMARK_INDEX
    start = start or config.START_DATE
    end = end or config.END_DATE

    # Use the benchmark's own trading calendar as the reference date index.
    bench_panel = db.load_panel(conn, [benchmark], start, end)
    if bench_panel.empty:
        raise RuntimeError(
            f"No cached data for benchmark {benchmark}. Run with --build-db first."
        )
    ref_dates = bench_panel.index
    benchmark_price = bench_panel[benchmark].reindex(ref_dates)

    panel = db.load_panel(conn, tickers, start, end).reindex(ref_dates)

    # Coverage filter -> fixed N. Drop assets missing > threshold of rows.
    coverage = panel.notna().mean(axis=0)
    keep_mask = coverage >= (1.0 - missing_threshold)
    dropped = sorted(panel.columns[~keep_mask].tolist())
    extra_missing = sorted(set(tickers) - set(panel.columns))  # never fetched
    kept = [t for t in tickers if t in panel.columns and keep_mask.get(t, False)]

    if dropped or extra_missing:
        logger.info(
            "Dropped %d low-coverage/absent assets (kept %d of %d): %s",
            len(dropped) + len(extra_missing), len(kept), len(tickers),
            ", ".join(dropped + extra_missing),
        )

    panel = panel[kept]
    # Forward-fill short internal gaps, then drop any row still incomplete so
    # every surviving window sees a fully-aligned price matrix.
    panel = panel.ffill(limit=5).dropna(axis=0, how="any")

    if panel.shape[1] < 3:
        raise RuntimeError(
            f"Only {panel.shape[1]} assets survived cleaning - too few for TDA."
        )

    returns = np.log(panel).diff().dropna(axis=0, how="any")
    logger.info(
        "Returns matrix: %d days x %d assets  [%s -> %s]",
        returns.shape[0], returns.shape[1],
        returns.index[0].date(), returns.index[-1].date(),
    )
    return returns, benchmark_price, kept


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="TDA-RiskPulse data ingestion (Module 1).")
    p.add_argument("--build-db", action="store_true",
                   help="Fetch/refresh the SQLite cache before reporting.")
    p.add_argument("--force", action="store_true",
                   help="With --build-db, re-download the full span (ignore cache).")
    p.add_argument("--start", default=config.START_DATE, help="Start date YYYY-MM-DD.")
    p.add_argument("--end", default=config.END_DATE, help="End date YYYY-MM-DD (inclusive).")
    p.add_argument("--db", default=config.DB_PATH, help="Path to stocks.db.")
    args = p.parse_args()

    conn = db.connect(args.db)
    try:
        if args.build_db:
            symbols = [*config.TDA_TICKERS, config.BENCHMARK_INDEX]
            logger.info("Fetching %d symbols into %s", len(symbols), args.db)
            fetch_to_db(conn, symbols, args.start, args.end, force=args.force)
            logger.info("Cache now holds %d distinct stocks.",
                        len(db.distinct_stocks(conn)))

        # Report the resulting return matrix shape as a sanity check.
        returns, _, kept = build_returns(
            conn, start=args.start, end=args.end
        )
        logger.info("OK: %d-asset point cloud over %d trading days.",
                    len(kept), len(returns))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
