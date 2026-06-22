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
./.venv/bin/python 
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

## Deploying on an Ubuntu 22.04 server (automated daily runs)

Run the daily daemon `run.py` on a headless server to import the latest prices and drop a
dated snapshot **`results/YYYY_MM_DD.png`** each weekday, so you can open the latest image to
check the day's status. The daily job runs the **magnitude-pulse** analysis (see
`docs/concept_zh.md`), which is the improved signal — not the entropy chart.

### 1. Copy the project to the server

```bash
# from your local machine — exclude the venv and caches (rebuilt on the server):
rsync -av --exclude .venv --exclude __pycache__ --exclude .git \
    TopologicalRiskIndicator/  user@server:~/TopologicalRiskIndicator/
```

- **Do** copy `stocks.db` (~31 MB) for a warm start; otherwise the first run backfills ~20
  years of prices (slow, one network call per symbol).
- **Don't** copy `.venv/` / `__pycache__/` — they are platform-specific.

### 2. Install Python 3.10 + dependencies

Ubuntu 22.04 ships Python 3.10, which `giotto-tda==0.6.2` supports directly (manylinux
wheels — no compiler needed).

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip
cd ~/TopologicalRiskIndicator

python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt

./.venv/bin/python -c "import gtda, yfinance, matplotlib; print('OK')"   # sanity check
```

### 3. Verify it works

```bash
./.venv/bin/python -m pytest tests -q                    # offline unit tests -> all passed

# produce one snapshot from the cache (no network) to confirm the pipeline:
./.venv/bin/python run.py --run-once --utc --no-fetch
ls results/                                              # -> a YYYY_MM_DD.png appears
```

If you did **not** copy `stocks.db`, build the cache first (needs internet, slow once):

```bash
./.venv/bin/python src/data_fetcher.py --build-db
```

### 4. Set the server clock to UTC

```bash
sudo timedatectl set-timezone UTC
timedatectl                                              # confirm "Time zone: UTC"
```

### 5. Schedule the daily run at 22:00 UTC, Mon–Fri (cron)

22:00 UTC is ~1–2 h after the US close (20:00–21:00 UTC), so the day's prices are available.
`1-5` restricts it to Monday–Friday, which satisfies the Sat/Sun filter.

```bash
crontab -e
```

Add one line (replace the path with your actual location):

```cron
0 22 * * 1-5  cd /home/USER/TopologicalRiskIndicator && ./.venv/bin/python run.py --run-once --utc >> results/cron.log 2>&1
```

- `0 22 * * 1-5` — 22:00 UTC, Monday–Friday.
- `run.py --run-once --utc` — import latest prices → run analysis → save `results/<UTC-date>.png`.
- stdout/errors are appended to `results/cron.log`.

Each weekday a fresh `results/YYYY_MM_DD.png` appears.

### Alternative: resident daemon (instead of cron)

`run.py` also has a built-in scheduler, if you prefer one long-lived process:

```bash
nohup ./.venv/bin/python run.py --utc --run-hour 22 >> results/run.log 2>&1 &
```

It checks every 30 min and fires once per weekday after 22:00 UTC. cron is simpler and
survives reboots; for an auto-starting daemon use a `systemd` service.

---

## Configuration

All knobs live in `src/config.py`: the ticker basket (`TDA_TICKERS`), `BENCHMARK_INDEX`,
default `START_DATE`/`END_DATE`, `WINDOW_SIZE` (40 trading days), `STEP_SIZE`,
`MISSING_THRESHOLD` (0.05), and `THRESHOLD_SIGMA` (2.0).

## Project layout

```
run.py              # daily daemon: import prices -> analyse -> results/YYYY_MM_DD.png
src/
  config.py         # tickers, benchmark, dates, window + threshold params
  db.py             # SQLite cache (stocks.db)
  data_fetcher.py   # Module 1: fetch -> aligned daily log returns
  tda_engine.py     # Module 2: correlation -> distance -> persistence (H1 entropy + magnitude S)
  main.py           # Module 3 (entropy): orchestrate + threshold + dual-panel chart
  analysis.py       # signal helpers: percentile level, trend slope, drawdown events
  magnitude_pulse.py# magnitude (S) analysis: build detector + event study + 3-panel chart
tests/              # offline unit tests
docs/               # PRD, SPEC, concept_zh, portfolio definition
requirements.txt
```

`stocks.db`, `results/`, and `.venv/` are gitignored.
