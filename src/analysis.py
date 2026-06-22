"""
analysis.py  --  signal-analysis helpers for the magnitude-pulse experiment.

Pure, TDA-free functions used to ask the question the SPEC's threshold chart
cannot: does a topological *magnitude* signal build ahead of, or only react to,
a drawdown?

    - expanding_percentile  level of S vs all history to date (slow-build detector)
    - trailing_slope        sign/strength of the local trend
    - drawdown_events       peak->trough crash episodes in a benchmark price series
    - signal_trough_offset  lead/lag (days) of a signal's trough vs the price trough
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def expanding_percentile(series: pd.Series, min_periods: int = 60) -> pd.Series:
    """Percentile rank of each point vs ALL history up to and including it.

    p_t = (#{x_s <= x_t, s <= t}) / (t + 1), using only past+present data (no
    lookahead). Unlike a trailing z-score, this does NOT adapt a slow monotonic
    build away: while S keeps making new highs, p stays near 1.0. NaN until at
    least `min_periods` observations exist.
    """
    vals = series.to_numpy(dtype=float)
    out = np.full(vals.shape[0], np.nan)
    for t in range(vals.shape[0]):
        if t + 1 >= min_periods:
            out[t] = np.mean(vals[: t + 1] <= vals[t])
    return pd.Series(out, index=series.index)


def trailing_slope(series: pd.Series, window: int) -> pd.Series:
    """OLS slope of `series` over each trailing `window` (per step).

    Positive => rising trend, negative => rolling over. Points with an
    incomplete window are NaN.
    """
    x = np.arange(window, dtype=float)
    x -= x.mean()
    denom = (x * x).sum()

    def _slope(y: np.ndarray) -> float:
        return float((x * (y - y.mean())).sum() / denom)

    return series.rolling(window, min_periods=window).apply(_slope, raw=True)


def drawdown_events(price: pd.Series, min_drop: float = 0.15):
    """Locate peak->trough drawdown episodes deeper than `min_drop`.

    An episode runs from a running-high peak, through the trough, until price
    reclaims that peak (a new high). Returns a list of
    (peak_date, trough_date, depth) with depth <= -min_drop (depth is negative).
    """
    p = price.dropna()
    events = []
    peak_val, peak_dt = -np.inf, None
    active = False
    trough_val = trough_dt = ep_peak_val = ep_peak_dt = None

    def close():
        depth = trough_val / ep_peak_val - 1.0
        if depth <= -min_drop:
            events.append((ep_peak_dt, trough_dt, depth))

    for dt, val in p.items():
        if val >= peak_val:                 # new running high
            if active:
                close()
                active = False
            peak_val, peak_dt = val, dt
        else:                               # underwater vs the running peak
            if not active:
                active = True
                ep_peak_val, ep_peak_dt = peak_val, peak_dt
                trough_val, trough_dt = val, dt
            elif val < trough_val:
                trough_val, trough_dt = val, dt
    if active:
        close()
    return events


def signal_trough_offset(
    signal: pd.Series,
    peak_dt: pd.Timestamp,
    price_trough_dt: pd.Timestamp,
    post_days: int = 30,
) -> float:
    """Days between a signal's trough and the price trough within an event.

    The signal's minimum is sought over [peak_dt, price_trough_dt + post_days].
    Returns (signal_trough_date - price_trough_date) in days:
        negative -> signal bottoms BEFORE price (leads)
        positive -> signal bottoms AFTER price (lags)
    NaN if the signal has no data in the window.
    """
    hi = price_trough_dt + pd.Timedelta(days=post_days)
    seg = signal.loc[peak_dt:hi].dropna()
    if seg.empty:
        return float("nan")
    return float((seg.idxmin() - price_trough_dt).days)
