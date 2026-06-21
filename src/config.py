"""
config.py
Single source of truth for the TDA-RiskPulse pipeline.

All tunable parameters (ticker basket, benchmark, date range, rolling-window
geometry, data-quality thresholds, file paths) live here so the data, engine,
and visualization layers stay decoupled (PRD non-functional requirement).
"""

from __future__ import annotations

import os
from datetime import datetime

# ---------------------------------------------------------------------------
# Asset universe  (from docs/nasdaq_tda_portfolio.md — 65 assets)
# ---------------------------------------------------------------------------
TDA_TICKERS = [
    # --- GROUP A: NASDAQ MEGACAPS (core index weight - 25) ---
    "MSFT", "AAPL", "NVDA", "AMZN", "META",
    "GOOGL", "TSLA", "AVGO", "ASML", "COST",
    "NFLX", "AMD", "QCOM", "TMUS", "INTU",
    "AMGN", "ISRG", "HON", "AMAT", "BKNG",
    "VRTX", "ADP", "PANW", "MDLZ", "REGN",

    # --- GROUP B: LIQUIDITY & MACRO CANARIES (systemic transmission - 15) ---
    "TLT", "HYG", "GLD", "SLV", "USO",
    "FXE", "FXY", "XLF", "KRE", "XLU",
    "IYR", "SMH", "IBIT", "LQD", "SHY",

    # --- GROUP C: HIGH-SENSITIVITY SECTOR SENTINELS (25) ---
    "ADBE", "WDAY", "CRWD", "DDOG", "TEAM",
    "MELI", "LULU", "ORLY", "ROST", "MAR",
    "LRCX", "CSX", "ODFL", "FAST", "PCAR",
    "GILD", "BIIB", "SGEN", "IDXX", "DXCM",
    "CEG", "CTAS", "AEP", "EXC", "NXPI",
]

BENCHMARK_INDEX = "^IXIC"  # Nasdaq Composite Index

# ---------------------------------------------------------------------------
# Date range  (~20 years of history by default)
# ---------------------------------------------------------------------------
END_DATE = datetime.now().strftime("%Y-%m-%d")
START_DATE = f"{datetime.now().year - 20}-01-01"

# ---------------------------------------------------------------------------
# Rolling-window geometry  (SPEC §2 / §3)
# ---------------------------------------------------------------------------
WINDOW_SIZE = 40   # tau: trading days per correlation window
STEP_SIZE = 1      # stride between windows

# ---------------------------------------------------------------------------
# Data-quality / signal thresholds
# ---------------------------------------------------------------------------
# Drop any asset missing more than this fraction of rows over the analysis
# window. Applied at panel level to keep a FIXED point-cloud size N across all
# windows (see plan: enables batched VietorisRipsPersistence). This is the
# pragmatic stand-in for the SPEC §4 per-slice substitution rule.
MISSING_THRESHOLD = 0.05

# Crisis trigger: mu + THRESHOLD_SIGMA * sigma over the H1-entropy history.
THRESHOLD_SIGMA = 2.0

# Homology dimensions to compute (0 = clusters, 1 = loops). The H1 entropy is
# the headline signal.
HOMOLOGY_DIMENSIONS = [0, 1]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_THIS_DIR)

DB_PATH = os.path.join(PROJECT_ROOT, "stocks.db")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
CHART_PATH = os.path.join(OUTPUT_DIR, "risk_pulse.png")
