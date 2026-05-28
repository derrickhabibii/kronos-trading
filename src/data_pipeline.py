# data_pipeline.py
# Pulls 2 years of H1 (1-hour) candle data for all 4 trading pairs via yfinance.
# Saves clean OHLC-only CSV files to data/raw/ — one file per pair.
# No volume column — forex pairs have no real volume on yfinance, and Kronos
# works correctly with OHLC only (see prediction_wo_vol_example.py in the repo).
# Run this script any time you need to refresh the historical data.

import yfinance as yf
import pandas as pd
import os

# Map our internal pair names to yfinance ticker symbols.
# XAUUSD uses the Gold futures ticker (GC=F) — closest available proxy for spot gold.
PAIRS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "JPY=X",
    "XAUUSD": "GC=F"
}

# Output folder — relative to the project root (kronos/)
OUTPUT_DIR = "data/raw"


def pull_and_save(pair_name, ticker):
    """Download 2 years of hourly OHLC data for one pair and save it as a CSV.
    Returns the number of rows saved, or 0 if something went wrong."""

    print(f"Pulling {pair_name} ({ticker})...")

    # Download 2 years of 1-hour candles from yfinance
    df = yf.download(ticker, period="2y", interval="1h", progress=False)

    if df.empty:
        print(f"  WARNING: No data returned for {pair_name}. Skipping.")
        return 0

    # yfinance returns multi-level column headers like ('Close', 'EURUSD=X').
    # Flatten them to simple lowercase names: close, high, low, open, volume.
    df.columns = [col[0].lower() for col in df.columns]

    # Keep OHLC only — drop volume (always zero for forex) and any other columns.
    df = df[["open", "high", "low", "close"]]

    # Drop any rows that have missing values in any column.
    before = len(df)
    df.dropna(inplace=True)
    dropped = before - len(df)
    if dropped > 0:
        print(f"  Dropped {dropped} rows with null values.")

    # Save to CSV. The index (Datetime) is included as the first column.
    out_path = os.path.join(OUTPUT_DIR, f"{pair_name}_H1.csv")
    df.to_csv(out_path)

    print(f"  {pair_name}: {len(df)} rows saved -> {out_path}")
    print(f"  Date range: {df.index[0]} to {df.index[-1]}")
    return len(df)


def run_quality_check(pair_name):
    """Read back the saved CSV and confirm it looks correct — right columns,
    no nulls, prices in a sensible range."""

    path = os.path.join(OUTPUT_DIR, f"{pair_name}_H1.csv")
    df = pd.read_csv(path, index_col=0, parse_dates=True)

    nulls = df.isnull().sum().sum()
    print(f"  {pair_name} quality check — rows: {len(df)}, nulls: {nulls}, "
          f"close range: {df['close'].min():.5f} to {df['close'].max():.5f}")


if __name__ == "__main__":
    # Make sure the output directory exists before writing anything
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=== Kronos Data Pipeline — pulling H1 OHLC for all 4 pairs ===\n")

    results = {}
    for pair_name, ticker in PAIRS.items():
        count = pull_and_save(pair_name, ticker)
        results[pair_name] = count
        print()

    print("=== Quality check (reading back saved files) ===")
    for pair_name in PAIRS:
        if results[pair_name] > 0:
            run_quality_check(pair_name)

    print("\n=== Summary ===")
    for pair_name, count in results.items():
        status = f"{count} rows" if count > 0 else "FAILED"
        print(f"  {pair_name}: {status}")
