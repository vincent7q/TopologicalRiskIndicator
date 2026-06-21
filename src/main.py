"""
main.py  --  TDA-RiskPulse Module 3 (Orchestrator + Visualizer)

Coordinates the pipeline end to end:
    data_fetcher (cache + log returns)  ->  tda_engine (H1 entropy)  ->  chart.

The crisis trigger is the static boundary  mu + THRESHOLD_SIGMA * sigma  over
the H1-entropy history (SPEC §3). Output is a dual-panel figure:
    Panel A: benchmark (^IXIC) price, with structural-stress zones shaded where
             entropy breaches the threshold.
    Panel B: H1 topological entropy with the threshold line.

Usage:
    python src/main.py                 # fetch/refresh cache, then compute + plot
    python src/main.py --no-fetch      # use the existing cache as-is
    python src/main.py --start 2010-01-01 --end 2024-12-31
"""

from __future__ import annotations

import argparse
import logging
import os

import matplotlib

matplotlib.use("Agg")  # headless; we save to file rather than display
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config
import db
import data_fetcher
import tda_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def crisis_threshold(entropy: pd.Series, sigma: float = config.THRESHOLD_SIGMA) -> float:
    """Static anomaly boundary: mu + sigma * std over the entropy history.

    Zero-entropy windows (the SPEC §4 fallback / structurally trivial periods)
    are excluded so they don't deflate the baseline.
    """
    active = entropy[entropy > 0.0]
    base = active if not active.empty else entropy
    return float(base.mean() + sigma * base.std())


def make_chart(
    benchmark_price: pd.Series,
    entropy: pd.DataFrame,
    threshold: float,
    benchmark_name: str,
    out_path: str,
) -> None:
    """Render and save the dual-panel risk-pulse chart."""
    h1 = entropy["H1_Entropy"]
    # Align the benchmark to the entropy date index so both panels share an x-axis.
    price = benchmark_price.reindex(h1.index).ffill()
    breach = h1 > threshold

    fig, (ax_price, ax_ent) = plt.subplots(
        2, 1, figsize=(15, 9), sharex=True,
        gridspec_kw={"height_ratios": [2, 1]},
    )

    # --- Panel A: benchmark price + stress zones ---
    ax_price.plot(price.index, price.values, color="#1f3b6f", lw=1.1,
                  label=f"{benchmark_name} (adj close)")
    ax_price.fill_between(
        h1.index, price.min(), price.max(), where=breach.values,
        color="crimson", alpha=0.15, step="mid",
        label=f"Entropy > threshold",
    )
    ax_price.set_ylabel("Index price")
    ax_price.set_title("TDA-RiskPulse — H1 topological stress vs. Nasdaq Composite")
    ax_price.legend(loc="upper left")
    ax_price.grid(alpha=0.25)

    # --- Panel B: H1 entropy + threshold ---
    ax_ent.plot(h1.index, h1.values, color="#b8430f", lw=0.9, label="H1 entropy")
    ax_ent.axhline(threshold, color="black", ls="--", lw=1.0,
                   label=f"threshold (mu + {config.THRESHOLD_SIGMA:g}σ = {threshold:.3f})")
    ax_ent.fill_between(h1.index, 0, h1.values, where=breach.values,
                        color="crimson", alpha=0.25, step="mid")
    ax_ent.set_ylabel("Normalized H1 entropy")
    ax_ent.set_xlabel("Date")
    ax_ent.legend(loc="upper left")
    ax_ent.grid(alpha=0.25)

    fig.tight_layout()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    logger.info("Saved chart -> %s", out_path)


def run(
    db_path: str = config.DB_PATH,
    start: str = config.START_DATE,
    end: str = config.END_DATE,
    fetch: bool = True,
    force: bool = False,
    out_path: str = config.CHART_PATH,
) -> pd.DataFrame:
    """Execute the full pipeline and return the entropy DataFrame."""
    conn = db.connect(db_path)
    try:
        if fetch:
            symbols = [*config.TDA_TICKERS, config.BENCHMARK_INDEX]
            logger.info("Refreshing cache for %d symbols ...", len(symbols))
            data_fetcher.fetch_to_db(conn, symbols, start, end, force=force)

        returns, benchmark_price, kept = data_fetcher.build_returns(
            conn, start=start, end=end
        )
        logger.info("Computing rolling H1 entropy over %d windows ...",
                    len(returns) - config.WINDOW_SIZE + 1)
        entropy = tda_engine.compute_entropy_series(returns)

        threshold = crisis_threshold(entropy["H1_Entropy"])
        n_breach = int((entropy["H1_Entropy"] > threshold).sum())
        logger.info("Threshold = %.4f; %d/%d windows in stress zone.",
                    threshold, n_breach, len(entropy))

        make_chart(benchmark_price, entropy, threshold,
                   config.BENCHMARK_INDEX, out_path)
        return entropy
    finally:
        conn.close()


def main() -> None:
    p = argparse.ArgumentParser(description="TDA-RiskPulse pipeline (Module 3).")
    p.add_argument("--db", default=config.DB_PATH, help="Path to stocks.db.")
    p.add_argument("--start", default=config.START_DATE, help="Start date YYYY-MM-DD.")
    p.add_argument("--end", default=config.END_DATE, help="End date YYYY-MM-DD.")
    p.add_argument("--no-fetch", action="store_true",
                   help="Skip the yfinance refresh and use the cache as-is.")
    p.add_argument("--force", action="store_true",
                   help="Re-download the full span (ignore cache).")
    p.add_argument("--output", default=config.CHART_PATH, help="Output PNG path.")
    args = p.parse_args()

    run(db_path=args.db, start=args.start, end=args.end,
        fetch=not args.no_fetch, force=args.force, out_path=args.output)


if __name__ == "__main__":
    main()
