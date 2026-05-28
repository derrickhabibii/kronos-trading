# execution.py
# Python side of the file bridge between Kronos and MetaTrader5.
#
# Architecture (Path B — Mac file bridge):
#   Python writes a signal dict to signal.json
#   → KronosEA.mq5 (running inside MT5) reads the file every 5 seconds
#   → EA places the order, writes signal_ack.json to confirm
#   → Python reads the acknowledgement and continues
#
# This is the only file that triggers real trades.
# Everything above this layer (forecast.py, trade_signal.py) only generates signals.
#
# IMPORTANT — file path coordination:
#   write_signal() writes to the path you specify (default: "signal.json").
#   KronosEA.mq5 reads from the MT5 Common Files folder (FILE_COMMON flag).
#   For the bridge to work, these must point to the same physical file.
#   MT5 Common Files on Mac: ~/Library/Application Support/MetaQuotes/Terminal/Common/Files/
#   Set the path parameter in write_signal() to that directory before paper run.


def write_signal(signal_dict, path=None):
    """Write a Kronos signal dict to a JSON file for the MT5 EA to consume.

    Adds a 'consumed' field set to False so the EA knows this is a fresh signal.
    Converts the timestamp to a string so it serialises cleanly.
    Never mutates the caller's dict.

    Args:
        signal_dict — output dict from generate_signal()
        path        — file path to write to. Defaults to SIGNAL_FILE from config.
    """
    import json, sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from config import SIGNAL_FILE

    if path is None:
        path = SIGNAL_FILE

    output = dict(signal_dict)                  # never mutate the caller's dict
    output["consumed"] = False
    output["timestamp"] = str(output["timestamp"])

    with open(path, "w") as f:
        json.dump(output, f, indent=2)


def read_acknowledgement(path=None, timeout_seconds=30):
    """Wait for the MT5 EA to confirm it processed the signal.

    The EA writes signal_ack.json with {"status": "executed", "order_ticket": <n>}
    after it places (or skips) an order. This function polls for that file.
    Deletes the ack file after reading it so it does not get picked up twice.

    Args:
        path            — path to the acknowledgement file the EA writes
        timeout_seconds — how long to wait before giving up (default: 30s)

    Returns:
        True  — EA confirmed the signal was processed
        False — timed out without receiving confirmation
    """
    import json, os, sys, time
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from config import SIGNAL_ACK_FILE

    if path is None:
        path = SIGNAL_ACK_FILE

    start = time.time()
    while time.time() - start < timeout_seconds:
        if os.path.exists(path):
            with open(path, encoding='utf-16') as f:
                ack = json.load(f)
            if ack.get("status") == "executed":
                os.remove(path)   # clean up so it does not get re-read
                return True
        time.sleep(1)

    # Timed out — EA did not respond within the window
    return False
