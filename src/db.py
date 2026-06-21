"""
db.py
SQLite caching layer for raw daily OHLCV.

Schema is taken verbatim from todo.md:

    CREATE TABLE data (
        stock  TEXT,
        DT     INT,
        Date   TEXT,
        Open   REAL,
        Close  REAL,
        High   REAL,
        Low    REAL,
        Volume REAL,
        PRIMARY KEY(DT, stock)
    );

Conventions:
    * `DT`   is an integer date key in YYYYMMDD form (e.g. 20240115).
    * `Date` is the human-readable "YYYY-MM-DD" string.
    * `Close` is stored split/dividend-ADJUSTED (yfinance auto_adjust=True),
      which satisfies the SPEC's "adjusted close" requirement without needing
      a separate Adj Close column.
    * The benchmark (^IXIC) is stored just like any other `stock`.

The cache lets us fetch the 65-asset x ~20y history once and reuse it across
runs, dodging yfinance throttling.
"""

from __future__ import annotations

import sqlite3
from typing import Iterable, Optional

import pandas as pd

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS data (
    stock  TEXT,
    DT     INT,
    Date   TEXT,
    Open   REAL,
    Close  REAL,
    High   REAL,
    Low    REAL,
    Volume REAL,
    PRIMARY KEY(DT, stock)
);
"""

CREATE_INDEX_SQL = "CREATE INDEX IF NOT EXISTS idx_data_stock ON data(stock);"


def connect(db_path: str) -> sqlite3.Connection:
    """Open (or create) the SQLite database and ensure the schema exists."""
    conn = sqlite3.connect(db_path)
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create the `data` table and supporting index if absent."""
    conn.execute(CREATE_TABLE_SQL)
    conn.execute(CREATE_INDEX_SQL)
    conn.commit()


def upsert_prices(conn: sqlite3.Connection, stock: str, df: pd.DataFrame) -> int:
    """
    Insert/replace daily OHLCV rows for a single `stock`.

    `df` must be indexed by a DatetimeIndex and contain the columns
    Open/High/Low/Close/Volume (missing columns are written as NULL).
    Returns the number of rows written. Idempotent: re-running with overlapping
    dates simply overwrites those rows (INSERT OR REPLACE on the PK).
    """
    if df is None or df.empty:
        return 0

    rows = []
    for ts, row in df.iterrows():
        dt_int = int(pd.Timestamp(ts).strftime("%Y%m%d"))
        date_str = pd.Timestamp(ts).strftime("%Y-%m-%d")
        rows.append(
            (
                stock,
                dt_int,
                date_str,
                _opt(row.get("Open")),
                _opt(row.get("Close")),
                _opt(row.get("High")),
                _opt(row.get("Low")),
                _opt(row.get("Volume")),
            )
        )

    conn.executemany(
        "INSERT OR REPLACE INTO data "
        "(stock, DT, Date, Open, Close, High, Low, Volume) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def get_latest_dt(conn: sqlite3.Connection, stock: str) -> Optional[int]:
    """Return the most recent DT (YYYYMMDD int) cached for `stock`, or None."""
    cur = conn.execute("SELECT MAX(DT) FROM data WHERE stock = ?", (stock,))
    result = cur.fetchone()[0]
    return int(result) if result is not None else None


def distinct_stocks(conn: sqlite3.Connection) -> list[str]:
    """Return the sorted list of stocks currently held in the cache."""
    cur = conn.execute("SELECT DISTINCT stock FROM data ORDER BY stock")
    return [r[0] for r in cur.fetchall()]


def load_panel(
    conn: sqlite3.Connection,
    tickers: Iterable[str],
    start: str,
    end: str,
) -> pd.DataFrame:
    """
    Load cached ADJUSTED CLOSE for the given tickers into a wide DataFrame.

    Returns a DataFrame indexed by a DatetimeIndex (Date) with one column per
    ticker. Missing (stock, date) combinations appear as NaN; alignment and
    cleaning are the caller's responsibility (see data_fetcher.build_returns).
    """
    tickers = list(tickers)
    if not tickers:
        return pd.DataFrame()

    start_dt = int(pd.Timestamp(start).strftime("%Y%m%d"))
    end_dt = int(pd.Timestamp(end).strftime("%Y%m%d"))
    placeholders = ",".join("?" for _ in tickers)

    query = (
        f"SELECT stock, Date, Close FROM data "
        f"WHERE stock IN ({placeholders}) AND DT >= ? AND DT <= ?"
    )
    params = [*tickers, start_dt, end_dt]
    long_df = pd.read_sql_query(query, conn, params=params, parse_dates=["Date"])

    if long_df.empty:
        return pd.DataFrame()

    wide = long_df.pivot(index="Date", columns="stock", values="Close")
    wide = wide.sort_index()
    # Preserve the requested ticker ordering where present.
    ordered = [t for t in tickers if t in wide.columns]
    return wide[ordered]


def _opt(value):
    """Coerce a pandas/NumPy scalar to a plain float, or None if missing."""
    if value is None or pd.isna(value):
        return None
    return float(value)
