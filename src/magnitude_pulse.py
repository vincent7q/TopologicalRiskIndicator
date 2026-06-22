"""
magnitude_pulse.py  --  experiment: persistence MAGNITUDE as a leading signal.

Motivation (see the investigation in the project history): the SPEC pipeline
plots normalized H1 *entropy*, which divides out exactly the quantities that
move in a market crash, and trips only on an upper-tail threshold. This script
instead tracks **total H1 persistence S** (the magnitude of loop structure) over
a shorter, AI-complete horizon, with a trailing-baseline trend detector, and
runs a small event study to ask whether S *leads* the drawdown or only reacts.

It is deliberately decoupled from the SPEC pipeline: it does not touch main.py,
config.py, tda_engine.compute_entropy_series, or results/risk_pulse.png.

Usage:
    python src/magnitude_pulse.py                 # use cache as-is (default)
    python src/magnitude_pulse.py --start 2016-01-01
    python src/magnitude_pulse.py --min-drop 0.20 --lookback 252
"""

from __future__ import annotations

import argparse
import logging
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from gtda.homology import VietorisRipsPersistence

import analysis
import config
import data_fetcher
import db
import tda_engine

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# AI-complete horizon: 2020 start keeps all 18 AI/semis (META, AVGO, TSLA,
# PANW, CRWD, DDOG, ...) that the default ~20y coverage filter drops.
EXPERIMENT_START = "2020-01-01"
BUILD_PCT = 0.80       # S percentile (vs history-to-date) above which = "elevated build"
SLOPE_WINDOW = 252     # trailing window (~1 trading year) for the trend slope
PCT_MINP = 252         # min history before the percentile level is meaningful
MIN_DROP = 0.15        # min peak->trough depth to count as a crash event
CHART_PATH = os.path.join(config.OUTPUT_DIR, "magnitude_pulse.png")


def compute_signals(returns: pd.DataFrame) -> pd.DataFrame:
    """One batched VR pass; derive both magnitude S and entropy E per window."""
    mats, dates = tda_engine.build_distance_matrices(returns)
    vr = VietorisRipsPersistence(metric="precomputed",
                                 homology_dimensions=list(config.HOMOLOGY_DIMENSIONS),
                                 n_jobs=-1)
    diagrams = vr.fit_transform(mats)
    return pd.DataFrame(
        {"S": tda_engine.h1_total_persistence(diagrams),
         "E": tda_engine.normalized_h1_entropy(diagrams)},
        index=pd.DatetimeIndex(dates, name="Date"),
    )


def event_study(S: pd.Series, pct: pd.Series, benchmark: pd.Series,
                min_drop: float) -> list[dict]:
    """For each drawdown event, measure how elevated S was before the peak
    (percentile vs history) and when S bottomed relative to the price trough."""
    rows = []
    for peak_dt, trough_dt, depth in analysis.drawdown_events(benchmark, min_drop):
        pre = pct.loc[peak_dt - pd.Timedelta(days=90):peak_dt].dropna()
        offset = analysis.signal_trough_offset(S, peak_dt, trough_dt)
        rows.append({
            "peak": peak_dt, "trough": trough_dt, "depth": depth,
            "pre_peak_max_pct": pre.max() if not pre.empty else float("nan"),
            "S_trough_offset_days": offset,
        })
    return rows


def make_chart(benchmark: pd.Series, df: pd.DataFrame, pct: pd.Series,
               slope: pd.Series, events: list[dict], out_path: str) -> None:
    idx = df.index
    price = benchmark.reindex(idx).ffill()
    build = (pct >= BUILD_PCT).fillna(False)

    fig, (ax_p, ax_s, ax_m) = plt.subplots(
        3, 1, figsize=(15, 11), sharex=True,
        gridspec_kw={"height_ratios": [2, 2, 1.3]})

    ax_p.plot(price.index, price.values, color="#1f3b6f", lw=1.1,
              label=f"{config.BENCHMARK_INDEX}")
    for ev in events:
        ax_p.axvspan(ev["peak"], ev["trough"], color="crimson", alpha=0.15)
        ax_p.axvline(ev["trough"], color="crimson", ls=":", lw=0.8)
    ax_p.set_ylabel("Index price")
    ax_p.set_title("Magnitude-Pulse — total H1 persistence vs. the AI run-up "
                   f"(horizon {idx[0].date()} → {idx[-1].date()})")
    ax_p.legend(loc="upper left"); ax_p.grid(alpha=0.25)

    ax_s.plot(df.index, df["S"].values, color="#0b6e4f", lw=0.9,
              label="Total H1 persistence S (magnitude)")
    ax_s.fill_between(df.index, df["S"].min(), df["S"].max(), where=build.values,
                      color="orange", alpha=0.18, step="mid",
                      label=f"elevated build (S ≥ {BUILD_PCT:.0%} of history)")
    ax_s.set_ylabel("S"); ax_s.legend(loc="upper left"); ax_s.grid(alpha=0.25)

    # Build monitor: level (percentile vs history) + trend (slope).
    ax_m.plot(pct.index, pct.values, color="#6a0dad", lw=1.0, label="S level (percentile)")
    ax_m.axhline(BUILD_PCT, color="black", ls="--", lw=0.9, label=f"{BUILD_PCT:.0%} build line")
    ax_m.fill_between(pct.index, 0, 1, where=build.values, color="orange", alpha=0.15, step="mid")
    ax_m.set_ylim(0, 1); ax_m.set_ylabel("S percentile"); ax_m.set_xlabel("Date")
    ax_m.legend(loc="lower left", fontsize=8); ax_m.grid(alpha=0.25)
    ax_sl = ax_m.twinx()
    ax_sl.plot(slope.index, slope.values, color="#888888", lw=0.8, alpha=0.8)
    ax_sl.axhline(0.0, color="#888888", ls=":", lw=0.7)
    ax_sl.set_ylabel(f"{SLOPE_WINDOW}d slope", color="#888888", fontsize=8)
    ax_sl.tick_params(axis="y", labelcolor="#888888", labelsize=7)

    fig.tight_layout()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    logger.info("Saved chart -> %s", out_path)


def run(start: str = EXPERIMENT_START, min_drop: float = MIN_DROP,
        slope_window: int = SLOPE_WINDOW, out_path: str = CHART_PATH) -> None:
    conn = db.connect(config.DB_PATH)
    try:
        returns, benchmark, kept = data_fetcher.build_returns(conn, start=start)
    finally:
        conn.close()
    logger.info("Horizon kept %d assets.", len(kept))

    df = compute_signals(returns)
    pct = analysis.expanding_percentile(df["S"], min_periods=PCT_MINP)
    slope = analysis.trailing_slope(df["S"], slope_window)
    events = event_study(df["S"], pct, benchmark, min_drop)

    print("\n" + "=" * 74)
    print(f"EVENT STUDY  (horizon {df.index[0].date()} -> {df.index[-1].date()}, "
          f"{len(kept)} assets, min drop {min_drop:.0%})")
    print("=" * 74)
    if not events:
        print("  no drawdown events exceeded the threshold.")
    for ev in events:
        lead = ev["S_trough_offset_days"]
        verdict = ("n/a (edge of horizon)" if np.isnan(lead)
                   else f"{lead:+.0f}d ({'LEADS' if lead < 0 else 'lags'} price trough)")
        prep = ev["pre_peak_max_pct"]
        prep_s = "n/a" if np.isnan(prep) else f"{prep:.0%}"
        print(f"  {ev['peak'].date()} -> {ev['trough'].date()}  "
              f"({ev['depth']:.0%})  | pre-peak max S level={prep_s}  "
              f"| S trough {verdict}")

    print("\nCURRENT STATE (latest window):")
    pval = pct.dropna().iloc[-1] if pct.notna().any() else float("nan")
    sval = slope.dropna().iloc[-1] if slope.notna().any() else float("nan")
    lit = (not np.isnan(pval)) and pval >= BUILD_PCT
    print(f"  S = {df['S'].iloc[-1]:.3f}   level = {pval:.0%} of history   "
          f"{slope_window}d slope = {sval:+.4f} ({'rising' if sval > 0 else 'falling'})   "
          f"-> {'ELEVATED BUILD' if lit else 'below build line'}")
    yr = df.groupby(df.index.year)["S"].mean().round(3)
    print(f"  yearly mean S: " + ", ".join(f"{y}:{v}" for y, v in yr.items()))

    make_chart(benchmark, df, pct, slope, events, out_path)


def main() -> None:
    p = argparse.ArgumentParser(description="Magnitude-pulse leading-signal experiment.")
    p.add_argument("--start", default=EXPERIMENT_START, help="Horizon start YYYY-MM-DD.")
    p.add_argument("--min-drop", type=float, default=MIN_DROP,
                   help="Min peak->trough depth to flag a crash event (e.g. 0.15).")
    p.add_argument("--slope-window", type=int, default=SLOPE_WINDOW,
                   help="Trailing window (windows) for the trend slope.")
    p.add_argument("--output", default=CHART_PATH, help="Output PNG path.")
    args = p.parse_args()
    run(start=args.start, min_drop=args.min_drop, slope_window=args.slope_window,
        out_path=args.output)


if __name__ == "__main__":
    main()
