# TopologicalRiskIndicator

**TDA-RiskPulse** — a High-Dimensional Topological Risk Indicator for equity indices.

It applies Topological Data Analysis (persistent homology + topological entropy) to the
rolling correlation geometry of a ~65-asset point cloud built around the Nasdaq Composite.
The idea: structural "embrittlement" of the market shows up as persistent **$H_1$ loops**
in the correlation structure, which the normalized **H1 topological entropy** summarizes
into a single daily stress series plotted against the index.

See `docs/PRD.md` and `docs/SPEC.md` for the product and mathematical specification.

---

## Installation

**Requires Python 3.10.** `giotto-tda==0.6.2` ships wheels for 3.8–3.11 only; on 3.12+ pip
tries to build from source (painful on Windows), so use a 3.10 virtual environment.

### Windows (PowerShell)

```powershell
# from the repo root
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# sanity check the heavy dependency installed
.\.venv\Scripts\python.exe -c "import gtda, yfinance; print('OK')"
```

### macOS / Linux

```bash
python3.10 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
```

> The examples below use the Windows path `.\.venv\Scripts\python.exe`.
> On macOS/Linux substitute `./.venv/bin/python`.

---

## How to run

The pipeline has three stages. Normally you run **step 1 once**, then **step 3** whenever
you want a fresh chart.

### 1. Build the price cache (first run, slow)

Downloads ~20 years of daily adjusted prices for all 65 tickers + the `^IXIC` benchmark
into a local SQLite database `stocks.db`. This takes a few minutes (one network call per
symbol) and only needs to be done once — later runs top up incrementally.

```powershell
.\.venv\Scripts\python.exe src\data_fetcher.py --build-db
```

Useful flags: `--start 2014-01-01 --end 2024-12-31` (custom range), `--force` (re-download
the full span, ignoring the cache).

### 2. (Optional) Run the tests

Offline unit tests covering the distance formula, the entropy edge cases, and data
alignment. No network required.

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

### 3. Compute the indicator and render the chart

```powershell
.\.venv\Scripts\python.exe src\main.py --no-fetch      # use the cache as-is (fast)
.\.venv\Scripts\python.exe src\main.py                 # refresh the cache (incremental) then run
```

Output is written to **`results/risk_pulse.png`**.

Common flags: `--start` / `--end` (restrict the analysis window), `--output <path>`
(change where the PNG is saved), `--no-fetch` (skip the yfinance refresh).

---

## Understanding the result

`results/risk_pulse.png` is a two-panel, shared-time-axis chart.

```
┌──────────────────────────────────────────────────────────┐
│ Panel A: ^IXIC (Nasdaq Composite) adjusted-close price    │
│          red shaded bands = "stress zones"                │
├──────────────────────────────────────────────────────────┤
│ Panel B: Normalized H1 topological entropy (0–1)          │
│          dashed line = crisis threshold (mu + 2σ)         │
└──────────────────────────────────────────────────────────┘
```

**Panel A — the benchmark.** The Nasdaq Composite price over the analysis window. Vertical
red bands mark the dates where the entropy in Panel B breached the threshold, so you can
read structural-stress events directly against price action.

**Panel B — the signal.** The normalized H1 topological entropy, one value per trading day
(each computed from a trailing 40-day window of the 48-ish-asset correlation cloud):

- **Range is 0 to 1.** It measures how the persistence (lifetimes) of the $H_1$ loops are
  distributed within a window.
  - **High entropy (→1):** many loops of *similar* persistence — the loop structure is
    diffuse / evenly spread.
  - **Low entropy (→0):** a few *dominant* persistent loops carry most of the structure.
  - **Exactly 0:** a window with fewer than two $H_1$ loops (structurally trivial — a
    deliberate, defined fallback, not an error).
- **The dashed threshold line** is the static crisis boundary $\mu + 2\sigma$ computed over
  the entropy history (non-zero values only). Days above it are the shaded stress zones.

**How to read it in practice.** Watch for the entropy moving toward an extreme and breaching
the dashed line while price (Panel A) is still elevated — that is the intended
"structural embrittlement before the drop" reading. The shaded bands are the model's
flagged dates.

### Important caveats

- **This is a research indicator, not trading advice.** With the SPEC's literal
  $\mu+2\sigma$ rule the signal is *sparse* (only a handful of breaches over 20 years), and
  empirically those high-entropy spikes tend to *coincide with* stress periods (2011, 2015,
  2020) more than cleanly *lead* them. Treating topological entropy as a reliable leading
  indicator requires further tuning (e.g. a rolling threshold, a shorter horizon, or pairing
  it with a persistence-norm signal).
- **Asset count depends on the horizon.** The engine needs a *fixed* set of assets across
  all windows, so any ticker missing more than 5% of rows over the chosen range is dropped.
  With the default ~20-year window only ~48 of the 65 tickers survive (newer listings such as
  TSLA, META, AVGO, CRWD, IBIT are excluded). **Shorten the date range** (e.g.
  `--start 2016-01-01`) to retain more of the mega-caps. The list of dropped assets is
  printed at runtime.
- **Pre-2015 signals are approximate** — the Nasdaq's constituents drift over two decades, so
  the older end of the cloud is directional rather than exact.

---

## Configuration

All knobs live in `src/config.py`: the ticker basket (`TDA_TICKERS`), `BENCHMARK_INDEX`,
default `START_DATE`/`END_DATE`, `WINDOW_SIZE` (40 trading days), `STEP_SIZE`,
`MISSING_THRESHOLD` (0.05), and `THRESHOLD_SIGMA` (2.0).

## Project layout

```
src/
  config.py         # tickers, benchmark, dates, window + threshold params
  db.py             # SQLite cache (stocks.db)
  data_fetcher.py   # Module 1: fetch -> aligned daily log returns
  tda_engine.py     # Module 2: correlation -> distance -> persistence -> H1 entropy
  main.py           # Module 3: orchestrate + threshold + dual-panel chart
tests/              # offline unit tests
docs/               # PRD, SPEC, portfolio definition
requirements.txt
```

`stocks.db`, `results/`, and `.venv/` are gitignored.
