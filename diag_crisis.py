"""Diagnostic: what does H1 topology actually do during the 2008 / 2020 crashes?

Throwaway evidence-gathering for the 'crashes aren't flagged' investigation.
Reuses the real engine so we measure exactly what main.py measures.
"""
import numpy as np
import pandas as pd

import config
import db
import data_fetcher
import tda_engine
from gtda.homology import VietorisRipsPersistence

conn = db.connect(config.DB_PATH)
returns, benchmark_price, kept = data_fetcher.build_returns(conn)
conn.close()

mats, dates = tda_engine.build_distance_matrices(returns)
dates = pd.DatetimeIndex(dates)

vr = VietorisRipsPersistence(metric="precomputed",
                             homology_dimensions=[0, 1], n_jobs=-1)
diagrams = vr.fit_transform(mats)

# Per-window H1 stats
births = diagrams[:, :, 0]
deaths = diagrams[:, :, 1]
dims = diagrams[:, :, 2]
h1_life = np.where((dims == 1) & ((deaths - births) > 0.0), deaths - births, 0.0)

M = np.sum(h1_life > 0, axis=1)                 # number of H1 bars
S = h1_life.sum(axis=1)                          # total H1 persistence
maxlife = h1_life.max(axis=1)                    # most persistent loop
E = tda_engine.normalized_h1_entropy(diagrams)   # the headline signal

df = pd.DataFrame({"E": E, "M": M, "S": S, "maxlife": maxlife}, index=dates)

# Benchmark drawdown context (forward 60d) just to sanity-check we hit the crash
bench = benchmark_price.reindex(dates).ffill()
df["bench"] = bench.values

def summary(name, mask):
    sub = df[mask]
    print(f"\n=== {name}  (n={len(sub)}) ===")
    for col in ["E", "M", "S", "maxlife"]:
        print(f"  {col:8s} mean={sub[col].mean():.4f}  "
              f"min={sub[col].min():.4f}  max={sub[col].max():.4f}")

print("FULL SAMPLE distribution of E:")
print(df["E"].describe(percentiles=[.01, .05, .25, .5, .75, .95, .99]).round(4))

threshold_up = df.loc[df.E > 0, "E"].mean() + 2 * df.loc[df.E > 0, "E"].std()
print(f"\nUpper crisis threshold (mu+2sigma) = {threshold_up:.4f}")

summary("FULL SAMPLE", df.index == df.index)
# 2008 GFC: Lehman Sep 2008 -> trough Mar 2009
summary("2008 GFC (2008-09-01..2009-03-31)",
        (df.index >= "2008-09-01") & (df.index <= "2009-03-31"))
# 2020 COVID crash: Feb 20 -> Mar 23 2020
summary("2020 COVID (2020-02-15..2020-04-15)",
        (df.index >= "2020-02-15") & (df.index <= "2020-04-15"))

# Where do the crisis windows rank in the E distribution?
for label, lo, hi in [("2008 GFC", "2008-09-01", "2009-03-31"),
                      ("2020 COVID", "2020-02-15", "2020-04-15")]:
    crisis_E = df.loc[(df.index >= lo) & (df.index <= hi), "E"]
    pct = (df["E"] < crisis_E.mean()).mean() * 100
    print(f"\n{label}: mean E={crisis_E.mean():.4f}  min E={crisis_E.min():.4f} "
          f"-> mean sits at the {pct:.1f}th percentile of all windows")
    n_above = (crisis_E > threshold_up).sum()
    print(f"   windows above upper threshold: {n_above}/{len(crisis_E)}")

# Does a MAGNITUDE signal separate crises better than entropy?
# Test S (total H1 persistence) and maxlife on the LOWER tail.
print("\n" + "=" * 60)
print("MAGNITUDE SIGNALS — would a LOWER-tail flag catch the crashes?")
for col in ["S", "maxlife"]:
    lo_thr = df[col].mean() - 2 * df[col].std()
    print(f"\n  {col}: full mean={df[col].mean():.4f}  lower thr(mu-2sd)={lo_thr:.4f}")
    for label, a, b in [("2008 GFC", "2008-09-01", "2009-03-31"),
                        ("2020 COVID", "2020-02-15", "2020-04-15")]:
        c = df.loc[(df.index >= a) & (df.index <= b), col]
        pct = (df[col] < c.mean()).mean() * 100
        print(f"    {label:11s} mean={c.mean():.4f} -> {pct:.1f}th pctile, "
              f"min={c.min():.4f}")

