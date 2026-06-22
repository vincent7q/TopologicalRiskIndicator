"""
tda_engine.py  --  TDA-RiskPulse Module 2 (TDA Compute Engine)

The mathematical core, fully decoupled from data I/O and plotting.

Pipeline per rolling window of `window_size` trading days (SPEC §2/§3):
    1. Pearson correlation matrix  rho   (N x N)
    2. Distance matrix             D[i,j] = sqrt(2 * (1 - rho[i,j]))
    3. Vietoris-Rips persistence over homology dimensions [0, 1]
    4. Normalized persistence entropy; the H1 column is the headline signal.

All windows are stacked into a single (n_windows, N, N) array and pushed
through giotto-tda in one batched `fit_transform`, which both vectorizes the
filtration and parallelizes across cores (`n_jobs=-1`). This is what keeps
~5000 windows over a 65-asset cloud tractable.

SPEC §4 edge case: a window whose H1 diagram has fewer than 2 finite bars
would make the normalization `1/ln(M)` divide by zero; such windows are forced
to entropy 0.0.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd

from gtda.homology import VietorisRipsPersistence

import config


# ---------------------------------------------------------------------------
# Geometry: correlation -> distance  (the testable math core)
# ---------------------------------------------------------------------------

def distance_from_correlation(rho: np.ndarray) -> np.ndarray:
    """Map a correlation matrix to the SPEC distance matrix.

        D[i,j] = sqrt(2 * (1 - rho[i,j]))

    rho == 1  -> distance 0   (identical behaviour)
    rho == -1 -> distance 2   (maximally anti-correlated)
    The diagonal is forced to exactly 0 to avoid sqrt round-off noise.
    """
    rho = np.clip(np.asarray(rho, dtype=float), -1.0, 1.0)
    dist = np.sqrt(2.0 * (1.0 - rho))
    np.fill_diagonal(dist, 0.0)
    return dist


def correlation_to_distance(window: np.ndarray) -> np.ndarray:
    """Correlation-distance matrix for one window of returns.

    `window` is shape (window_size, N) with assets in columns. Assets that are
    constant within the window (zero variance -> NaN correlation, e.g. a halted
    ticker that was forward-filled) are treated as uncorrelated (rho = 0).
    """
    with np.errstate(invalid="ignore", divide="ignore"):
        rho = np.corrcoef(window, rowvar=False)
    rho = np.where(np.isfinite(rho), rho, 0.0)
    np.fill_diagonal(rho, 1.0)
    return distance_from_correlation(rho)


def build_distance_matrices(
    returns: pd.DataFrame,
    window_size: int = config.WINDOW_SIZE,
    step_size: int = config.STEP_SIZE,
) -> tuple[np.ndarray, list[pd.Timestamp]]:
    """Slide over `returns` and stack one distance matrix per window.

    Returns the array of shape (n_windows, N, N) and the list of window-end
    dates (each window is labelled by its last trading day).
    """
    X = returns.to_numpy(dtype=float)
    n_rows, n_assets = X.shape
    if n_rows < window_size:
        raise ValueError(
            f"Need at least {window_size} rows, got {n_rows}."
        )

    starts = range(0, n_rows - window_size + 1, step_size)
    mats = np.empty((len(starts), n_assets, n_assets), dtype=float)
    dates: list[pd.Timestamp] = []
    for k, s in enumerate(starts):
        mats[k] = correlation_to_distance(X[s : s + window_size])
        dates.append(returns.index[s + window_size - 1])
    return mats, dates


# ---------------------------------------------------------------------------
# Persistence entropy with the SPEC §4 fallback
# ---------------------------------------------------------------------------

def h1_bar_counts(diagrams: np.ndarray) -> np.ndarray:
    """Count finite (positive-persistence) H1 bars per diagram.

    giotto diagrams have shape (n_samples, n_features, 3) with columns
    (birth, death, homology_dimension). Points padded onto the diagonal
    (death == birth) carry zero persistence and are excluded.
    """
    births = diagrams[:, :, 0]
    deaths = diagrams[:, :, 1]
    dims = diagrams[:, :, 2]
    is_h1 = dims == 1
    is_finite_bar = (deaths - births) > 0
    return np.sum(is_h1 & is_finite_bar, axis=1)


def h1_total_persistence(diagrams: np.ndarray) -> np.ndarray:
    """Total H1 persistence  S = sum_k (death_k - birth_k)  per diagram.

    Unlike `normalized_h1_entropy` (which divides out both the bar count via
    1/ln(M) and the total via p_k = L_k/S), this keeps the *magnitude* of the
    loop structure — the quantity that actually collapses in a correlation
    crash and builds during a slow bubble. Diagonal/zero-persistence points and
    non-H1 features contribute 0.
    """
    births = diagrams[:, :, 0]
    deaths = diagrams[:, :, 1]
    dims = diagrams[:, :, 2]
    lifetimes = np.where((dims == 1) & ((deaths - births) > 0.0),
                         deaths - births, 0.0)
    return lifetimes.sum(axis=1)


def normalized_h1_entropy(diagrams: np.ndarray) -> np.ndarray:
    """Normalized H1 topological entropy per diagram, exactly per SPEC §2 Step 3:

        L_k = death_k - birth_k        (H1 bar lifetimes, positive only)
        S   = sum_k L_k,   p_k = L_k / S
        E   = -1/ln(M) * sum_k p_k ln(p_k)     (M = number of H1 bars)

    This is implemented directly rather than via giotto's
    PersistenceEntropy(normalize=True): giotto normalizes by ln(sum of
    lifetimes), not ln(M), which is unbounded when the total persistence is
    small (it produced O(1000) values on this data). The SPEC's definition is
    bounded in [0, 1] and is the authority here.

    SPEC §4 fallback: windows with M < 2 H1 bars return 0.0 (the 1/ln(M)
    factor is undefined for M < 2).
    """
    births = diagrams[:, :, 0]
    deaths = diagrams[:, :, 1]
    dims = diagrams[:, :, 2]
    lifetimes = np.where((dims == 1) & ((deaths - births) > 0.0),
                         deaths - births, 0.0)

    out = np.zeros(diagrams.shape[0], dtype=float)
    for i in range(diagrams.shape[0]):
        L = lifetimes[i][lifetimes[i] > 0.0]
        M = L.size
        if M < 2:
            continue  # 0.0
        p = L / L.sum()
        out[i] = float(-np.sum(p * np.log(p)) / np.log(M))
    return out


def compute_entropy_series(
    returns: pd.DataFrame,
    window_size: int = config.WINDOW_SIZE,
    step_size: int = config.STEP_SIZE,
    homology_dimensions: Sequence[int] = tuple(config.HOMOLOGY_DIMENSIONS),
    n_jobs: int = -1,
) -> pd.DataFrame:
    """Compute the rolling H1 topological-entropy time series.

    Returns a DataFrame indexed by window-end Date with a single column
    `H1_Entropy`.
    """
    homology_dimensions = list(homology_dimensions)
    mats, dates = build_distance_matrices(returns, window_size, step_size)

    vr = VietorisRipsPersistence(
        metric="precomputed",
        homology_dimensions=homology_dimensions,
        n_jobs=n_jobs,
    )
    diagrams = vr.fit_transform(mats)

    h1 = normalized_h1_entropy(diagrams)
    return pd.DataFrame({"H1_Entropy": h1}, index=pd.DatetimeIndex(dates, name="Date"))
