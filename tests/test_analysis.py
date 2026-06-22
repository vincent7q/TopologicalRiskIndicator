"""Tests for the magnitude-signal analysis helpers (trend + event study).

Pure functions, no TDA / network. These back the magnitude_pulse experiment:
    - expanding_percentile:  level of S vs all history to date (build detector)
    - trailing_slope:        sign/strength of the local trend
    - drawdown_events:       locate peak->trough crash episodes in a price series
    - signal_trough_offset:  lead/lag of a signal's trough vs the price trough
"""

import numpy as np
import pandas as pd

import analysis


# ---------------------------------------------------------------------------
# expanding_percentile  (level vs all history to date — lookahead-free)
# ---------------------------------------------------------------------------

def test_expanding_percentile_monotonic_build_stays_lit():
    # A monotonically rising series: every point is a new high -> percentile 1.0.
    # (This is the case the trailing z-score adapts away; percentile must not.)
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    p = analysis.expanding_percentile(s, min_periods=1)
    assert np.allclose(p.values, 1.0)


def test_expanding_percentile_values_and_min_periods():
    s = pd.Series([3.0, 1.0, 2.0, 4.0])
    p = analysis.expanding_percentile(s, min_periods=2)
    assert np.isnan(p.iloc[0])                 # fewer than min_periods points
    assert np.isclose(p.iloc[1], 0.5)          # [3,1], 1 is <= 1 of 2 -> 0.5
    assert np.isclose(p.iloc[2], 2 / 3)        # [3,1,2], 2 beats {1,2} -> 2/3
    assert np.isclose(p.iloc[3], 1.0)          # [3,1,2,4], 4 is the max -> 1.0


# ---------------------------------------------------------------------------
# trailing_slope  (sign/strength of the local trend)
# ---------------------------------------------------------------------------

def test_trailing_slope_linear():
    s = pd.Series([5.0, 7.0, 9.0, 11.0, 13.0])   # y = 2x + 5
    sl = analysis.trailing_slope(s, window=3)
    assert sl.iloc[:2].isna().all()              # need a full window
    assert np.isclose(sl.iloc[2], 2.0)
    assert np.isclose(sl.iloc[4], 2.0)


# ---------------------------------------------------------------------------
# drawdown_events
# ---------------------------------------------------------------------------

def test_drawdown_events_finds_major_ignores_minor():
    idx = pd.bdate_range("2020-01-01", periods=9)
    # rise to 110, crash to 77 (-30%), recover to 115 (new high), dip to 109 (-5%).
    price = pd.Series([100, 110, 95, 77, 100, 115, 112, 109, 113.0], index=idx)

    events = analysis.drawdown_events(price, min_drop=0.15)

    assert len(events) == 1                       # the -5% wiggle is ignored
    peak_dt, trough_dt, depth = events[0]
    assert peak_dt == idx[1]                       # the 110 print
    assert trough_dt == idx[3]                     # the 77 print
    assert np.isclose(depth, 77 / 110 - 1.0)       # ~ -0.30


# ---------------------------------------------------------------------------
# signal_trough_offset  (negative = signal leads the price trough)
# ---------------------------------------------------------------------------

def test_signal_trough_offset_sign():
    idx = pd.bdate_range("2020-01-01", periods=30)
    peak_dt, price_trough_dt = idx[5], idx[15]

    # Signal bottoms 5 business days AFTER the price trough -> lags (positive).
    lagging = pd.Series(1.0, index=idx)
    lagging.loc[idx[20]] = -1.0
    off = analysis.signal_trough_offset(lagging, peak_dt, price_trough_dt, post_days=30)
    assert off == (idx[20] - price_trough_dt).days
    assert off > 0

    # Signal bottoms before the price trough -> leads (negative).
    leading = pd.Series(1.0, index=idx)
    leading.loc[idx[10]] = -1.0
    off2 = analysis.signal_trough_offset(leading, peak_dt, price_trough_dt, post_days=30)
    assert off2 < 0
