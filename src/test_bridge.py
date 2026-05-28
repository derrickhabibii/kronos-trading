# test_bridge.py
# Tests the Python side of the file bridge (execution.py) end-to-end.
#
# What this tests:
#   1. write_signal() correctly writes a signal dict to signal.json
#   2. The written JSON has "consumed": false and a string timestamp
#   3. read_acknowledgement() picks up a simulated EA response file
#   4. read_acknowledgement() returns True and cleans up the ack file
#
# What this does NOT test:
#   The MQL5 EA side. To test that, load KronosEA.mq5 in MT5, configure the
#   file paths to match, and verify the EA logs show it reading the file and
#   writing back signal_ack.json without placing an order (flat signal).
#
# No live orders are placed. File read/write only.

import sys
import os
import json

# Add src/ to path so execution.py is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from execution import write_signal, read_acknowledgement

# Use test-specific file names — do not overwrite the real signal files
SIGNAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "test_signal.json")
ACK_PATH    = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "test_signal_ack.json")

# Normalise paths
SIGNAL_PATH = os.path.normpath(SIGNAL_PATH)
ACK_PATH    = os.path.normpath(ACK_PATH)

# Clean up any leftover files from a previous test run
for f in [SIGNAL_PATH, ACK_PATH]:
    if os.path.exists(f):
        os.remove(f)
        print(f"Cleaned up leftover file: {f}")

print("\n" + "=" * 60)
print("Kronos File Bridge Test")
print("=" * 60 + "\n")


# ── Step 1: Write a flat signal ──────────────────────────────────
# Use a realistic flat signal — the kind that should produce no order.
print("Step 1: write_signal() — writing flat signal to:")
print(f"  {SIGNAL_PATH}\n")

test_signal = {
    "pair":           "BTCUSD",
    "timestamp":      "2026-04-14 04:00:00",
    "direction":      "flat",
    "confidence":     0.0,
    "predicted_high": 74512.16,
    "predicted_low":  74323.30,
    "target_price":   None,
    "stop_price":     None,
    "predicted_move": 0.0,
    "lot_size":       0.0,
    "spread_filter":  False,
}

# Pass a copy so the original test_signal dict is not mutated
write_signal(dict(test_signal), path=SIGNAL_PATH)

# Read back and verify
assert os.path.exists(SIGNAL_PATH), "FAIL: signal file was not created"
with open(SIGNAL_PATH) as f:
    written = json.load(f)

print("  Written file contents:")
print(json.dumps(written, indent=2))
print()

assert written["direction"] == "flat",      f"FAIL: direction should be flat, got {written['direction']}"
assert written["consumed"]  == False,        f"FAIL: consumed should be False, got {written['consumed']}"
assert isinstance(written["timestamp"], str), f"FAIL: timestamp should be a string"
print("  ✓ signal.json written correctly")
print("  ✓ 'consumed' is False")
print("  ✓ timestamp is a string\n")


# ── Step 2: Simulate the MT5 EA acknowledging the signal ─────────
# In production, KronosEA.mq5 writes this after processing the signal.
# For a flat signal the EA places no order, so ticket=0.
print("Step 2: Simulating MT5 EA acknowledgement (flat signal → no order)...")

ack_content = {
    "status":       "executed",
    "order_ticket": 0
}
with open(ACK_PATH, "w") as f:
    json.dump(ack_content, f, indent=2)

print(f"  Written to: {ACK_PATH}")
print(f"  Contents:   {json.dumps(ack_content)}\n")


# ── Step 3: read_acknowledgement() picks it up ───────────────────
print("Step 3: read_acknowledgement() — polling for ack file (timeout=5s)...")
result = read_acknowledgement(path=ACK_PATH, timeout_seconds=5)
print(f"  Result: {result}\n")

assert result == True,                   f"FAIL: read_acknowledgement should return True, got {result}"
assert not os.path.exists(ACK_PATH),     f"FAIL: ack file should be deleted after reading, still exists"
print("  ✓ read_acknowledgement returned True")
print("  ✓ signal_ack.json deleted after reading\n")


# ── Cleanup ───────────────────────────────────────────────────────
if os.path.exists(SIGNAL_PATH):
    os.remove(SIGNAL_PATH)

print("=" * 60)
print("All bridge tests passed.")
print("=" * 60)
print()
print("Next step (manual — requires MT5 running):")
print("  1. Copy signal.json to the MT5 Common Files folder")
print("  2. Verify KronosEA.mq5 logs show it reading the file")
print("  3. Verify signal_ack.json is written back by the EA")
print("  4. Confirm no order was placed (direction was flat)")
