# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---


## What this project is

**TDA-RiskPulse**: a leading market-risk indicator that applies Topological Data Analysis (Persistent Homology + Topological Entropy) to a high-dimensional point cloud of equity/cross-asset returns. The thesis: structural "embrittlement" of the market manifests as persistent $H_1$ topological loops in the correlation geometry *before* a major drawdown (e.g. a Nasdaq crash), giving a leading stress signal that lagging metrics (VIX, rolling correlation, volatility) miss.

The authoritative design lives in `docs/`:
- `docs/PRD.md` — product objective, scope, workflow, non-functional constraints.
- `docs/SPEC.md` — math framework + the intended 3-module implementation blueprint. **Read this before writing engine code.**
- `docs/nasdaq_tda_portfolio.md` — the 65-asset `TDA_TICKERS` list (copy-paste ready) and `BENCHMARK_INDEX = "^IXIC"`.

## Architecture (the 3-module pipeline)

The SPEC's blueprint is implemented as decoupled modules under `src/` (data I/O ↔ math engine ↔ plotting are kept separate):

- **`config.py`** — single source of truth: the 65 `TDA_TICKERS`, `BENCHMARK_INDEX="^IXIC"`, `START_DATE`/`END_DATE` (~20y), `WINDOW_SIZE=40`, `STEP_SIZE=1`, `MISSING_THRESHOLD=0.05`, `THRESHOLD_SIGMA=2.0`, paths.
- **`db.py`** — SQLite cache. Exact `todo.md` schema: `data(stock, DT, Date, Open, Close, High, Low, Volume)`, `PRIMARY KEY(DT, stock)`. `DT`=`YYYYMMDD` int. `Close` is stored split/dividend-adjusted (yfinance `auto_adjust=True`), so no separate Adj Close column. `init_db / upsert_prices (INSERT OR REPLACE) / get_latest_dt / load_panel`.
- **`data_fetcher.py`** (Module 1) — cache-aware incremental fetch of all 66 symbols, then `build_returns()`: align on the benchmark calendar, drop assets with >`MISSING_THRESHOLD` missing rows, ffill short gaps, drop remaining NaN rows, compute log returns $R_{i,t}=\ln(P_{i,t}/P_{i,t-1})$.
- **`tda_engine.py`** (Module 2) — `build_distance_matrices` (Pearson ρ → $D=\sqrt{2(1-\rho)}$), then **one batched** `VietorisRipsPersistence(metric="precomputed", homology_dimensions=[0,1], n_jobs=-1).fit_transform` over all windows, then `normalized_h1_entropy`. Output: `[Date, H1_Entropy]`.
- **`main.py`** (Module 3) — orchestrate, compute threshold $\mu+2\sigma$ (over non-zero entropy), render the dual-panel chart to `outputs/risk_pulse.png`.

## Critical correctness rules — read before touching the engine

- **Entropy is computed by hand, NOT via giotto's `PersistenceEntropy(normalize=True)`.** giotto normalizes by $\ln(\sum \text{lifetimes})$, not $\ln M$ as SPEC §2 specifies — that is unbounded and produced O(1000) values on real data. `tda_engine.normalized_h1_entropy` implements the SPEC formula $E=-\frac{1}{\ln M}\sum p_k\ln p_k$ directly, bounded in [0,1]. Don't "simplify" it back to giotto's version.
- **`<2` H1 bars ⇒ entropy `0.0`** (the $1/\ln M$ factor is undefined for M<2). Enforced inside `normalized_h1_entropy`.
- **Fixed N, not per-slice substitution.** Batched giotto requires a constant point-cloud size across windows, so SPEC §4's per-slice asset substitution is replaced by a panel-level coverage filter in `build_returns`. Consequence: with the default ~20y window, only ~48 of 65 assets survive (post-2006 IPOs like TSLA/META/AVGO/CRWD/IBIT are dropped). Shorten the horizon to keep more mega-caps. This is an intentional, documented deviation.
- **Strict matrix alignment**: all surviving assets share one NaN-free date index (handled in `build_returns`); misalignment silently corrupts the correlation matrices.

## Environment & commands

Use the **Python 3.10** venv (`giotto-tda==0.6.2` has no 3.12 wheels — building from source on Windows is painful). All commands below assume `.venv\Scripts\python.exe`.

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

.\.venv\Scripts\python.exe src\data_fetcher.py --build-db   # backfill stocks.db (~66 symbols, slow once)
.\.venv\Scripts\python.exe -m pytest tests -q               # offline unit tests (entropy edge cases, distance, alignment)
.\.venv\Scripts\python.exe src\main.py --no-fetch           # compute + chart from cache → outputs/risk_pulse.png
.\.venv\Scripts\python.exe src\main.py                      # refresh cache (incremental) then run
```

`stocks.db`, `outputs/`, and `.venv/` are gitignored. `git` history note: the old `src/data_fetcher.py` was a single-asset OHLCV→CSV dumper; it was rewritten to Module 1.
