# Ultra-Effective Nasdaq TDA Prediction Portfolio (65 Assets)

This portfolio is mathematically optimized for Topological Data Analysis (TDA) crisis prediction. It expands the point cloud to 69 assets by integrating the dominant equity drivers of the Nasdaq, cross-asset liquidity transmission channels, and systemic macro indicators. This structure prevents geometric collapse and enhances the sensitivity of the $H_1$ Topological Entropy signal.

## 1. Ticker List (Python Ready)
```python
# Copy-paste this directly into your data_fetcher.py script
TDA_TICKERS = [
    # --- GROUP A: NASDAQ MEGAPORTS (The Core Index Weight - 24 Stocks) ---
    "MSFT", "AAPL", , "AMZN", "META", 
    "GOOGL", "TSLA", "AVGO", "ASML", "COST", 
    "NFLX", "AMD", "QCOM", "TMUS", "INTU", 
    "AMGN", "ISRG", "HON", "AMAT", "BKNG", 
    "VRTX", "ADP", "PANW", "MDLZ", "REGN",

    #--- GROUP B: AI stocks (5 Stocks) ---
     "NVDA","SNDK", "MU", "MRVL", "LITE",

    # --- GROUP C: LIQUIDITY & MACRO CANARIES (Systemic Transmission - 15 Stocks) ---
    "TLT",   # iShares 20+ Year Treasury Bond ETF (Duration & Interest Rate Stress)
    "HYG",   # iShares iBoxx $ High Yield Corporate Bond ETF (Credit Spread & Default Risk)
    "GLD",   # SPDR Gold Shares (Safe Haven Capital Flight Proxy)
    "SLV",   # iShares Silver Trust (Industrial Demand vs. Precious Metal Speculation)
    "USO",   # United States Oil Fund (Energy Supply Shock / Inflation Input)
    "FXE",   # Invesco CurrencyShares Euro Currency Trust (FX Liquidity / Dollar Strength Proxy)
    "FXY",   # Invesco CurrencyShares Japanese Yen Trust (Global Carry Trade Unwind Canary)
    "XLF",   # Financial Select Sector SPDR Fund (Systemic Banking Transmission Matrix)
    "KRE",   # SPDR S&P Regional Banking ETF (Regional Liquidity & Credit Crunch Sensor)
    "XLU",   # Utilities Select Sector SPDR Fund (Defensive Equity Rotation Anchor)
    "IYR",   # iShares U.S. Real Estate ETF (Commercial Real Estate & Leverage Stress)
    "SMH",   # VanEck Semiconductor ETF (Pure-play Tech Momentum Cluster Anchor)
    "IBIT",  # iShares Bitcoin Trust (High-Beta Liquidity Speculation Benchmark)
    "LQD",   # iShares iBoxx $ Investment Grade Corporate Bond ETF (Corporate Debt Stress)
    "SHY",   # iShares 1-3 Year Treasury Bond ETF (Short-term Funding & Yield Curve Stress)

    # --- GROUP D: HIGH-SENSITIVITY SECTOR SENTINELS (25 Stocks) ---
    # Software & Cloud
    "ADBE", "WDAY", "CRWD", "DDOG", "TEAM",
    # Consumer Discretionary & High-Beta Retail
    "MELI", "LULU", "ORLY", "ROST", "MAR",
    # Industrials & Supply Chain
    "LRCX", "CSX", "ODFL", "FAST", "PCAR",
    # Biotech & Health-Tech
    "GILD", "BIIB", "SGEN", "IDXX", "DXCM",
    # Industrial Tech & Infrastructure
    "CEG", "CTAS", "AEP", "EXC", "NXPI"
]

BENCHMARK_INDEX = "^IXIC"  # Nasdaq Composite Index