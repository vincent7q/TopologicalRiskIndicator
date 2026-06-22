"""
Tests for the load-bearing correctness rules of the TDA-RiskPulse engine.

These run fully offline on tiny synthetic data:
    1. Distance formula:  rho=1 -> 0,  rho=-1 -> 2,  symmetric, zero diagonal.
    2. SPEC §4 fallback:  a window with < 2 finite H1 bars -> entropy 0.0.
    3. Data alignment:    misaligned cached prices -> a single shared, NaN-free
                          date index in the returned log-return matrix.
Plus a small end-to-end smoke test through giotto-tda.
"""

import sqlite3

import numpy as np
import pandas as pd

import db
import tda_engine
from data_fetcher import build_returns


# ---------------------------------------------------------------------------
# 1. Distance formula
# ---------------------------------------------------------------------------

def test_distance_from_correlation_endpoints():
    rho = np.array([[1.0, 1.0, -1.0],
                    [1.0, 1.0, -1.0],
                    [-1.0, -1.0, 1.0]])
    dist = tda_engine.distance_from_correlation(rho)

    # rho=1 -> 0 (between assets 0 and 1)
    assert dist[0, 1] == 0.0
    # rho=-1 -> 2
    assert np.isclose(dist[0, 2], 2.0)
    # diagonal is exactly zero, matrix symmetric
    assert np.allclose(np.diag(dist), 0.0)
    assert np.allclose(dist, dist.T)


def test_correlation_to_distance_handles_constant_asset():
    # Asset 1 perfectly tracks asset 0; asset 2 is constant (zero variance).
    window = np.column_stack([
        np.array([1.0, 2.0, 3.0, 4.0]),
        np.array([2.0, 4.0, 6.0, 8.0]),
        np.array([5.0, 5.0, 5.0, 5.0]),
    ])
    dist = tda_engine.correlation_to_distance(window)

    assert np.all(np.isfinite(dist))           # no NaN leaks from zero variance
    assert np.isclose(dist[0, 1], 0.0)         # perfectly correlated -> 0
    # constant asset treated as uncorrelated (rho=0) -> sqrt(2)
    assert np.isclose(dist[0, 2], np.sqrt(2.0))


# ---------------------------------------------------------------------------
# 2. SPEC §4 fallback: < 2 H1 bars -> 0.0
# ---------------------------------------------------------------------------

def _diagram_with_h1_bars(n_bars: int, lifetime: float = 0.3,
                          total: int = 6) -> np.ndarray:
    """Build a single giotto-style diagram with `n_bars` finite H1 bars (all of
    equal `lifetime`), padded with diagonal (zero-persistence) points to a fixed
    `total` row count so diagrams can be stacked (giotto pads to equal length)."""
    rows = []
    for _ in range(n_bars):
        rows.append([0.1, 0.1 + lifetime, 1.0])     # finite H1 bar, equal length
    for _ in range(total - n_bars):
        rows.append([0.2, 0.2, 1.0])                # diagonal padding (death==birth)
    return np.array(rows, dtype=float)


def test_normalized_h1_entropy_fallback_and_bounds():
    # sample 0: 0 H1 bars, sample 1: 1 bar, sample 2: 3 EQUAL-length bars.
    diagrams = np.stack([
        _diagram_with_h1_bars(0),
        _diagram_with_h1_bars(1),
        _diagram_with_h1_bars(3),
    ])
    h1 = tda_engine.normalized_h1_entropy(diagrams)

    assert h1[0] == 0.0                 # 0 bars -> 0 (SPEC §4)
    assert h1[1] == 0.0                 # 1 bar  -> 0 (1/ln(1) undefined)
    # 3 equal-length bars => maximal entropy => normalized value exactly 1.0
    assert np.isclose(h1[2], 1.0)


def test_normalized_h1_entropy_unequal_bars_below_one():
    # Two bars of different lifetimes -> entropy strictly inside (0, 1).
    diagram = np.array([[0.0, 1.0, 1.0],    # lifetime 1.0
                        [0.0, 0.2, 1.0],    # lifetime 0.2
                        [0.3, 0.3, 1.0]])   # diagonal padding
    h1 = tda_engine.normalized_h1_entropy(diagram[None, :, :])
    assert 0.0 < h1[0] < 1.0


def test_h1_bar_counts():
    diagrams = np.stack([_diagram_with_h1_bars(0),
                         _diagram_with_h1_bars(2)])
    counts = tda_engine.h1_bar_counts(diagrams)
    assert list(counts) == [0, 2]


def test_h1_total_persistence():
    # sample 0: no H1 bars -> S = 0; sample 1: 3 bars of lifetime 0.3 -> S = 0.9.
    diagrams = np.stack([_diagram_with_h1_bars(0),
                         _diagram_with_h1_bars(3, lifetime=0.3)])
    S = tda_engine.h1_total_persistence(diagrams)
    assert S[0] == 0.0
    assert np.isclose(S[1], 0.9)


# ---------------------------------------------------------------------------
# 3. Data alignment via the SQLite layer
# ---------------------------------------------------------------------------

def _seed(conn, stock, dates, prices):
    df = pd.DataFrame({"Close": prices}, index=pd.to_datetime(dates))
    df["Open"] = df["High"] = df["Low"] = df["Close"]
    df["Volume"] = 1000
    db.upsert_prices(conn, stock, df)


def test_build_returns_aligns_and_drops_nan():
    conn = sqlite3.connect(":memory:")
    db.init_db(conn)

    dates = pd.bdate_range("2024-01-01", periods=12).strftime("%Y-%m-%d").tolist()
    # Benchmark defines the trading calendar.
    _seed(conn, "^IXIC", dates, np.linspace(100, 120, 12))
    # Three assets fully present; one (AAA) missing a single interior day.
    _seed(conn, "AAA", dates[:5] + dates[6:], np.linspace(10, 21, 11))
    _seed(conn, "BBB", dates, np.linspace(50, 61, 12))
    _seed(conn, "CCC", dates, np.linspace(5, 16, 12))

    returns, benchmark, kept = build_returns(
        conn, tickers=["AAA", "BBB", "CCC"], benchmark="^IXIC",
        start="2024-01-01", end="2024-12-31", missing_threshold=0.2,
    )

    # All three assets survive the (generous) coverage filter.
    assert set(kept) == {"AAA", "BBB", "CCC"}
    # Single shared, monotonic, NaN-free date index.
    assert returns.index.is_monotonic_increasing
    assert not returns.isna().any().any()
    assert list(returns.columns) == ["AAA", "BBB", "CCC"]
    assert len(benchmark) >= len(returns)
    conn.close()


# ---------------------------------------------------------------------------
# 4. End-to-end smoke test through giotto-tda
# ---------------------------------------------------------------------------

def test_compute_entropy_series_smoke():
    rng = np.random.default_rng(42)
    idx = pd.bdate_range("2020-01-01", periods=80)
    returns = pd.DataFrame(
        rng.normal(scale=0.01, size=(80, 6)),
        index=idx,
        columns=[f"A{i}" for i in range(6)],
    )
    out = tda_engine.compute_entropy_series(
        returns, window_size=40, step_size=5, n_jobs=1
    )

    assert list(out.columns) == ["H1_Entropy"]
    assert len(out) == len(range(0, 80 - 40 + 1, 5))     # number of windows
    # Normalized entropy lives in [0, 1].
    assert (out["H1_Entropy"] >= 0.0).all()
    assert (out["H1_Entropy"] <= 1.0 + 1e-9).all()
