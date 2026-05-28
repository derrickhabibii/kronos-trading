# main.py
# The main loop that runs the full Kronos trading system end to end.
# Order of operations: pull data → run Kronos forecast → generate signal → execute trade.
# This is the file Derrick runs to start the bot. All other files are called from here.

import os
import sys


def _next_wake_time():
    """Return the UTC datetime (timezone-naive) to sleep until before the next cycle.

    H4 candles close at 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC.
    We target 5 minutes after each close so yfinance has time to publish the
    completed candle.

    If the system starts within 5 minutes of a just-closed boundary (i.e., the candle
    may not yet be fully visible in yfinance), we skip that candle and wait for the next.
    """
    import datetime

    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)

    # Find the start of the current 4-hour epoch (floor to nearest H4 boundary).
    # Example: now = 07:43 → h4_epoch = 4 → current_boundary = today 04:00
    h4_epoch         = (now.hour // 4) * 4
    current_boundary = now.replace(hour=h4_epoch, minute=0, second=0, microsecond=0)

    # Our target is always: next_boundary + 5 minutes
    candidate = current_boundary + datetime.timedelta(hours=4)
    target    = candidate + datetime.timedelta(minutes=5)

    # Edge case: if now is already at or past that target (system restarted late),
    # advance by one more period so we never sleep a negative or zero duration.
    if now >= target:
        target += datetime.timedelta(hours=4)

    return target


def _append_log(log_path, row):
    """Append one row to the paper run CSV log. Creates the file and header if needed.

    Each row records one H4 candle cycle: what signal was produced, whether the EA
    acknowledged it, and when the event happened. Writing one row per candle gives
    Derrick and Hans a clean audit trail for the paper run review.
    """
    import csv

    COLUMNS = [
        "logged_at_utc",
        "candle_close_utc",
        "pair",
        "direction",
        "confidence",
        "lot_size",
        "predicted_high",
        "predicted_low",
        "target_price",
        "stop_price",
        "predicted_move",
        "ack_received",
    ]

    file_exists = os.path.isfile(log_path)
    with open(log_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def run_live():
    """Main trading loop. Runs forever, waking every 4 hours to generate and execute a signal.

    Each cycle:
      1. Sleep until 5 minutes after the next H4 candle close
      2. Pull 60 days of BTC H4 data from yfinance
      3. Run Kronos forecast on the last 200 candles
      4. Convert the forecast to a trade signal (long / short / flat)
      5. Write the signal file for the MT5 EA to consume
      6. Wait up to 30 seconds for the EA to acknowledge
      7. Append the result to logs/paper_run_log.csv
    """
    import datetime
    import time

    # ── sys.path setup ──
    # Remove any auto-added /src path. Python inserts the script's own directory at
    # sys.path[0] when running a file — that would make "from model import ..." find
    # the local model/ folder instead of the Kronos model package.
    # We then explicitly add the three directories we need in priority order:
    #   KRONOS_REPO → highest priority, so the Kronos model package wins over local model/
    #   PROJECT_ROOT → for config.py
    #   SRC          → for trade_signal.py and execution.py
    sys.path = [p for p in sys.path if not p.endswith("/src")]

    _SRC          = os.path.dirname(os.path.abspath(__file__))           # .../Kronos/src
    _PROJECT_ROOT = os.path.dirname(_SRC)                                # .../Kronos
    _KRONOS_REPO  = os.path.join(_PROJECT_ROOT, "Kronos")                # .../Kronos/Kronos

    # Insert in reverse priority order — each insert goes to index 0, so the last
    # insert ends up at the front. Final order: KRONOS_REPO, PROJECT_ROOT, SRC, rest.
    for _p in [_SRC, _PROJECT_ROOT, _KRONOS_REPO]:
        if _p not in sys.path:
            sys.path.insert(0, _p)

    # ── Imports (after sys.path is correct) ──
    import yfinance as yf
    import pandas as pd
    import torch
    from model import Kronos, KronosTokenizer, KronosPredictor
    from trade_signal import generate_signal
    from execution import write_signal, read_acknowledgement
    from config import SYMBOL, SIGNAL_FILE, SIGNAL_ACK_FILE  # noqa: F401 — imported for clarity

    # ── Constants ──
    TOKENIZER_PATH = os.path.join(_PROJECT_ROOT, "model", "Kronos-Tokenizer-base")
    FINETUNED_PATH = os.path.join(_PROJECT_ROOT, "model", "finetuned", "btc_h4_v1")
    LOG_DIR        = os.path.join(_PROJECT_ROOT, "logs")
    LOG_PATH       = os.path.join(LOG_DIR, "paper_run_log.csv")

    # Inference parameters — same as Phase 3 production config. Do not change.
    LOOKBACK     = 200
    PRED_LEN     = 1
    T            = 0.8
    TOP_P        = 0.9
    SAMPLE_COUNT = 4

    # Create logs/ directory if it does not exist yet
    os.makedirs(LOG_DIR, exist_ok=True)

    # ── Load finetuned Kronos model once at startup ──
    # Loading takes a few seconds. We do it once here and keep the predictor in memory
    # for the entire session — not every candle cycle.
    print("Loading finetuned Kronos model (epoch 3 checkpoint)...")
    tokenizer = KronosTokenizer.from_pretrained(TOKENIZER_PATH)
    model_obj = Kronos.from_pretrained(FINETUNED_PATH)

    # Device detection: prefer Apple Metal GPU, then CUDA, fall back to CPU
    if torch.backends.mps.is_available():
        device = torch.device("mps")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")

    model_obj.to(device).eval()
    predictor = KronosPredictor(model_obj, tokenizer, max_context=512)

    # ── Startup message ──
    first_wake = _next_wake_time()
    mins_away  = (first_wake - datetime.datetime.now(datetime.UTC).replace(tzinfo=None)).total_seconds() / 60
    print(f"Model loaded. Device:    {predictor.device}")
    print(f"Symbol:                  {SYMBOL}")
    print(f"Next wake (UTC):         {first_wake.strftime('%Y-%m-%d %H:%M:%S')}"
          f"  ({mins_away:.1f} min from now)")
    print("-" * 60)

    # ── Main loop ──
    while True:

        # a. Calculate next H4 close + 5 min, then sleep
        wake_time        = _next_wake_time()
        candle_close_utc = wake_time - datetime.timedelta(minutes=5)
        next_candle_ts   = candle_close_utc + datetime.timedelta(hours=4)
        sleep_secs       = max(0.0, (wake_time - datetime.datetime.now(datetime.UTC).replace(tzinfo=None)).total_seconds())

        print(f"\n[{datetime.datetime.now(datetime.UTC).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')} UTC]  "
              f"Sleeping {sleep_secs:.0f}s  →  candle close "
              f"{candle_close_utc.strftime('%Y-%m-%d %H:%M')} UTC")
        time.sleep(sleep_secs)

        # Timestamp written to every log row for this cycle
        logged_at_utc = datetime.datetime.now(datetime.UTC).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{logged_at_utc} UTC]  Processing candle "
              f"{candle_close_utc.strftime('%Y-%m-%d %H:%M')} UTC ...")

        try:

            # b. Pull BTC H4 data via yfinance
            raw = yf.download("BTC-USD", period="60d", interval="4h", progress=False)

            # Flatten MultiIndex columns if yfinance returned them
            # (yfinance sometimes wraps columns in a two-level MultiIndex)
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)

            # Lowercase all column names and keep only the four OHLC columns
            raw.columns = [c.lower() for c in raw.columns]
            df = raw[["open", "high", "low", "close"]].copy()

            # Strip timezone from the index — our finetuning data was timezone-naive
            if df.index.tz is not None:
                df.index = df.index.tz_convert(None)
            else:
                df.index = df.index.tz_localize(None)

            df = df.dropna()

            # c. Sanity check: must have at least LOOKBACK + 1 rows
            # LOOKBACK rows for context, plus at least 1 to confirm the data is fresh
            if len(df) < LOOKBACK + 1:
                raise ValueError(
                    f"Insufficient data: {len(df)} rows downloaded, need ≥{LOOKBACK + 1}"
                )

            # d. Run Kronos forecast on the last LOOKBACK rows as context
            # x_ts: timestamps of the context window (Kronos uses these for time embeddings)
            # y_ts: timestamp of the candle we are predicting (next H4 open)
            context = df.iloc[-LOOKBACK:]
            x_ts    = context.index.to_series()
            y_ts    = pd.Series([next_candle_ts])

            pred_df = predictor.predict(
                df          = context,
                x_timestamp = x_ts,
                y_timestamp = y_ts,
                pred_len    = PRED_LEN,
                T           = T,
                top_p       = TOP_P,
                sample_count= SAMPLE_COUNT,
                verbose     = False,
            )

            last_close = float(context.iloc[-1]["close"])
            pred_high  = float(pred_df["high"].iloc[0])
            pred_low   = float(pred_df["low"].iloc[0])

            # e. Convert forecast to trade signal
            signal = generate_signal(SYMBOL, next_candle_ts, last_close, pred_high, pred_low)

            # f. Print signal to terminal
            print(f"  last_close:  ${last_close:,.2f}")
            print(f"  pred_high:   ${pred_high:,.2f}   pred_low: ${pred_low:,.2f}")
            print(f"  direction:   {signal['direction']}")
            print(f"  confidence:  {signal['confidence']:.4f}")
            print(f"  lot_size:    {signal['lot_size']}")

            # g. Write signal file for the EA
            write_signal(signal)

            # h. Wait for EA acknowledgement (up to 30 seconds)
            ack = read_acknowledgement(timeout_seconds=30)

            # i. Append one row to the paper run log
            _append_log(LOG_PATH, {
                "logged_at_utc":    logged_at_utc,
                "candle_close_utc": candle_close_utc.strftime("%Y-%m-%d %H:%M:%S"),
                "pair":             signal["pair"],
                "direction":        signal["direction"],
                "confidence":       signal["confidence"],
                "lot_size":         signal["lot_size"],
                "predicted_high":   signal["predicted_high"],
                "predicted_low":    signal["predicted_low"],
                "target_price":     signal["target_price"],
                "stop_price":       signal["stop_price"],
                "predicted_move":   signal["predicted_move"],
                "ack_received":     ack,
            })

            # j. Print ack result
            print(f"  EA ack:      {'CONFIRMED' if ack else 'TIMEOUT — no response from EA within 30s'}")

        except Exception as e:
            # If anything fails: print the error, log an error row, continue to next candle.
            # One bad cycle does not stop the bot.
            print(f"  [ERROR] {e}")

            _append_log(LOG_PATH, {
                "logged_at_utc":    logged_at_utc,
                "candle_close_utc": candle_close_utc.strftime("%Y-%m-%d %H:%M:%S"),
                "pair":             SYMBOL,
                "direction":        "error",
                "confidence":       None,
                "lot_size":         None,
                "predicted_high":   None,
                "predicted_low":    None,
                "target_price":     None,
                "stop_price":       None,
                "predicted_move":   None,
                "ack_received":     False,
            })


if __name__ == "__main__":
    import subprocess

    # ── Keep macOS awake for the entire session ──
    # caffeinate -i prevents the machine from sleeping while the process is alive.
    # The finally block ensures it is killed cleanly whether the bot stops normally
    # or crashes — no zombie caffeinate processes left behind.
    _caffeinate = subprocess.Popen(['caffeinate', '-i'])

    try:
        run_live()

    finally:
        # Always kill caffeinate on exit — clean shutdown
        _caffeinate.terminate()
