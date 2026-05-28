# test_bridge_live.py
# Real handshake test — requires MT5 running with KronosEA attached to a chart.
#
# What this tests:
#   1. Writes a flat signal.json directly to the MT5 Common Files folder
#   2. Waits up to 30 seconds for the EA to read it and write signal_ack.json back
#   3. Reports whether the full file handshake worked
#
# A flat signal is used so no order is placed on the live or demo account.
# Watch the MT5 Journal tab — you should see the EA log the signal as it arrives.

import sys
import os
import json
import time

# Resolve config from project root
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import SIGNAL_FILE, SIGNAL_ACK_FILE, MT5_COMMON_FILES
from execution import write_signal, read_acknowledgement

print("\n" + "=" * 60)
print("Kronos Live Bridge Test (Real MT5 Handshake)")
print("=" * 60)
print(f"\nMT5 Common Files folder:\n  {MT5_COMMON_FILES}\n")

# Confirm the folder exists before proceeding
if not os.path.isdir(MT5_COMMON_FILES):
    print(f"FAIL: MT5 Common Files folder not found at:\n  {MT5_COMMON_FILES}")
    print("Check that MT5 is installed and has been opened at least once.")
    sys.exit(1)

print(f"✓ MT5 Common Files folder exists\n")

# Clean up any leftover files from a previous run
for f in [SIGNAL_FILE, SIGNAL_ACK_FILE]:
    if os.path.exists(f):
        os.remove(f)
        print(f"Cleaned up leftover: {f}")

# ── Step 1: Write flat signal to MT5 Common Files ────────────────
print("Step 1: Writing flat signal to MT5 Common Files folder...")
print(f"  Path: {SIGNAL_FILE}\n")

test_signal = {
    "pair":           "BTCUSD.m",
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

write_signal(dict(test_signal), path=SIGNAL_FILE)

if not os.path.exists(SIGNAL_FILE):
    print("FAIL: signal.json was not written to the MT5 Common Files folder.")
    sys.exit(1)

print("  ✓ signal.json written to MT5 Common Files folder")
print("\n  >> Now watch the MT5 Journal tab — the EA should log:")
print('     "KronosEA: Signal received | direction=flat ..."')
print('     "KronosEA: direction=flat — no order placed."')
print('     "KronosEA: Acknowledgement written to signal_ack.json"\n')

# ── Step 2: Wait for EA to respond ───────────────────────────────
print("Step 2: Waiting up to 30 seconds for EA acknowledgement...")

result = read_acknowledgement(path=SIGNAL_ACK_FILE, timeout_seconds=30)

print()
if result:
    print("  ✓ EA acknowledged the signal — file handshake WORKS")
    print("  ✓ No order was placed (flat signal)")
    print("\n" + "=" * 60)
    print("PHASE 5 COMPLETE — file bridge confirmed working end-to-end.")
    print("=" * 60)
else:
    print("  FAIL: EA did not respond within 30 seconds.")
    print("\n  Troubleshooting:")
    print("  1. Check the MT5 Journal tab for error messages")
    print("  2. Confirm AutoTrading is enabled in MT5 (toolbar button)")
    print("  3. Confirm the EA shows a smiley face on the BTCUSD chart")
    print(f"  4. Check signal.json exists: {os.path.exists(SIGNAL_FILE)}")
