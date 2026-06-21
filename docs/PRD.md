# Product Requirements Document (PRD)

## Project Name
**TDA-RiskPulse**: High-Dimensional Topological Risk Indicator for Equity Indices

## 1. Executive Summary & Objective
Traditional financial risk metrics (e.g., VIX, Rolling Correlation, Volatility) are lagging indicators that fail to capture non-linear, structural shifts in equity markets prior to sudden liquidations. 

**TDA-RiskPulse** is an advanced market-regime and risk-monitoring tool. It utilizes Topological Data Analysis (TDA)—specifically **Persistent Homology** and **Topological Entropy**—to analyze the structural deformation of a high-dimensional point cloud composed of asset returns. The objective is to identify hidden "structural embrittlement" (the formation of persistent $H_1$ topological loops/holes) and generate a leading stress-warning indicator days or weeks before a major market drop (e.g., Nasdaq crash).

---

## 2. Target Users
* **Quantitative Risk Managers:** Seeking leading, non-linear indicators to adjust portfolio leverage or hedging ratios dynamically.
* **Systemic Macro Traders:** Seeking to identify regime shifts from orderly, uncorrelated markets to highly compressed, systemically brittle environments.

---

## 3. Scope of Core Features
* **Data Ingestion Engine:** Automated fetching, cleaning, and alignment of historical daily OHLC data for a customizable basket of equities (default: Top 50 stratified Nasdaq components).
* **Sliding Window Transformer:** Converting absolute price series into stationary log-return matrices over a configurable rolling time frame.
* **TDA Compute Engine:**
    * Constructing distance matrices based on non-linear mapping of Pearson correlations.
    * Computing Vietoris-Rips filtrations across Homology Dimensions 0 ($H_0$, clusters) and 1 ($H_1$, loops).
    * Extracting Persistence Diagrams and calculating normalized **Topological Entropy**.
* **Analytics & Visualizer:** A dual-panel time-series visualization comparing the benchmark index price against the rolling $H_1$ Topological Entropy to isolate historical leading divergence signals.

---

## 4. User Workflow & Experience
1.  The user defines a list of tickers, a benchmark ticker (e.g., `^IXIC`), and a historical date range (e.g., 15–20 years).
2.  The application runs headless calculations across the rolling timeline.
3.  The application outputs a high-resolution chart showing:
    * Top Panel: Benchmark index price with critical structural shift zones marked.
    * Bottom Panel: $H_1$ Topological Entropy line with a statistical threshold (e.g., 2 standard deviations above rolling mean) acting as a crisis trigger.

---

## 5. Non-Functional Requirements & Constraints
* **Algorithmic Efficiency:** TDA calculations scale exponentially with the number of assets ($N$). The codebase must optimize memory usage and leverage multi-core processing (`n_jobs=-1`) where possible.
* **Data Integrity:** Must seamlessly handle trading halts, corporate actions (stock splits via adjusted close), and missing row alignments without corrupting the rolling geometric structures.
* **Modularity:** The mathematical engine must be entirely decoupled from the data fetching and plotting logic to allow for future real-time pipeline integrations.