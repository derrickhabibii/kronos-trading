# forecast.py
# Zero-shot directional accuracy test for Kronos on EUR/USD H1 data.
# Walks through the last 200 candles of the dataset, asks Kronos to predict
# each one using the 200 candles before it as context, then checks whether
# Kronos got the direction right (up or down from the previous close).
# This is Phase 3 validation — if directional accuracy is above 52% on 3 of 4
# pairs, zero-shot passes and we proceed to the signal layer.

import sys
import time

# IMPORTANT: Remove src/ from sys.path before any other imports.
# Python automatically adds the script's own directory (src/) to sys.path[0] when
# running a file. Our src/signal.py stub shadows Python's stdlib signal module,
# which causes torch to crash on import. Removing src/ from the path here fixes it.
# Long-term fix: rename src/signal.py to src/trade_signal.py (flagged for Hans).
sys.path = [p for p in sys.path if not p.endswith("/src")]

# Add the cloned Kronos repo to the Python path so its model package is importable
sys.path.insert(0, "/Users/derrickchuaa/Kronos/Kronos")

import pandas as pd
import numpy as np

# KronosPredictor lives in model/kronos.py and is re-exported via model/__init__.py.
# The brief referenced model.predictor which does not exist — corrected here.
from model import Kronos, KronosTokenizer, KronosPredictor

# ── Config ──
LOOKBACK     = 200   # number of historical candles fed to Kronos as context
TEST_SIZE    = 200   # number of candles to predict (walk-forward test)
PRED_LEN     = 1     # predict 1 candle ahead — never ask Kronos for more than 3
T            = 0.8   # temperature — controls randomness of sampling
TOP_P        = 0.9   # nucleus sampling threshold
SAMPLE_COUNT = 4     # number of Monte Carlo samples averaged per prediction

TOKENIZER_PATH = "/Users/derrickchuaa/Kronos/model/Kronos-Tokenizer-base"
MODEL_PATH     = "/Users/derrickchuaa/Kronos/model/Kronos-small"
DATA_PATH      = "/Users/derrickchuaa/Kronos/data/raw/EURUSD_H1.csv"

# ── Load model ──
print("Loading tokenizer and model from local files...")
tokenizer = KronosTokenizer.from_pretrained(TOKENIZER_PATH)
model     = Kronos.from_pretrained(MODEL_PATH)
predictor = KronosPredictor(model, tokenizer, max_context=512)
print(f"Model loaded. Running on: {predictor.device}\n")

# ── Load data ──
df = pd.read_csv(DATA_PATH, index_col=0)
df.index = pd.to_datetime(df.index)

print(f"Data loaded: {len(df)} rows, {df.index[0]} to {df.index[-1]}")
print(f"Running {TEST_SIZE} predictions (lookback={LOOKBACK}, pred_len={PRED_LEN})...\n")

# ── Test loop ──
# Walk forward through the last TEST_SIZE candles of the dataset.
# For each candle, use the preceding LOOKBACK candles as context and predict it.
# Then compare the predicted direction to what actually happened.
results = []
total   = len(df)
start   = time.time()

for i in range(TEST_SIZE):
    # Work out which slice of the dataframe is context vs target
    ctx_end   = total - TEST_SIZE + i  # index of the candle we are predicting
    ctx_start = ctx_end - LOOKBACK     # first candle of the context window

    context    = df.iloc[ctx_start:ctx_end]  # 200 candles of input
    actual_row = df.iloc[ctx_end]            # the candle Kronos is predicting

    # Build timestamp series — Kronos uses these to compute time embeddings
    x_timestamp = context.index.to_series()
    y_timestamp = pd.Series([actual_row.name])

    # Run the prediction — OHLC only, no volume column
    pred_df = predictor.predict(
        df=context[["open", "high", "low", "close"]],
        x_timestamp=x_timestamp,
        y_timestamp=y_timestamp,
        pred_len=PRED_LEN,
        T=T,
        top_p=TOP_P,
        sample_count=SAMPLE_COUNT,
        verbose=False
    )

    # Extract the three prices we need for the directional check
    last_close      = context.iloc[-1]["close"]   # last known price
    predicted_close = pred_df["close"].iloc[0]    # what Kronos thinks comes next
    actual_close    = actual_row["close"]          # what actually happened

    # Directional accuracy: did Kronos predict the right direction?
    predicted_up = predicted_close > last_close
    actual_up    = actual_close    > last_close
    correct      = predicted_up == actual_up

    results.append({
        "datetime":        actual_row.name,
        "last_close":      round(last_close, 5),
        "predicted_close": round(predicted_close, 5),
        "actual_close":    round(actual_close, 5),
        "predicted_dir":   "UP" if predicted_up else "DOWN",
        "actual_dir":      "UP" if actual_up    else "DOWN",
        "correct":         correct
    })

    # Print progress every 20 predictions so we know it's still running
    if (i + 1) % 20 == 0:
        elapsed = time.time() - start
        rate    = (i + 1) / elapsed
        eta     = (TEST_SIZE - (i + 1)) / rate
        print(f"Progress: {i+1}/{TEST_SIZE} — {elapsed:.0f}s elapsed, ~{eta:.0f}s remaining")

# ── Results ──
elapsed    = time.time() - start
results_df = pd.DataFrame(results)
accuracy   = results_df["correct"].mean() * 100

print(f"\nTotal time: {elapsed:.0f}s ({elapsed/TEST_SIZE:.1f}s per prediction)")
print(f"\nEURUSD Directional Accuracy: {accuracy:.1f}%")
print(f"Correct: {results_df['correct'].sum()} / {TEST_SIZE}")
print(f"\nLast 10 predictions:")
print(results_df.tail(10).to_string(index=False))
