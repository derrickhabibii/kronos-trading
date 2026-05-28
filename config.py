# config.py
# Central configuration file for the Kronos trading system.
# All settings live here — pairs, paths, thresholds, MT5 credentials, Kronos parameters.
# Change values here to affect the whole system. Do not hardcode settings inside other files.

# ── Spread costs per instrument (in USD) ──
# These are the estimated cost to enter a trade. A signal is only valid if the
# predicted price move is large enough to beat this cost by the multiplier below.
# BTCUSD: ~$50 placeholder — confirm actual spread from Just Markets before paper run.
SPREAD_USD = {
    "BTCUSD.m": 15.0   # confirmed April 14 2026 — observed $12.58 (bid/ask at time of check)
                        # set to $15 as a conservative buffer for spread widening during volatility
}

# ── Instrument symbol ──
# Just Markets uses "BTCUSD.m" on their demo account (confirmed April 14 2026).
# Update to "BTCUSD" if the live account uses a different symbol.
SYMBOL = "BTCUSD.m"

# ── Spread multiplier ──
# A signal only fires if the predicted move exceeds the spread × this value.
# At 1.5x, a $50 BTC spread requires a $75+ predicted move to produce a signal.
# Anything smaller is not worth the entry cost.
SPREAD_MULTIPLIER = 1.5

# ── MT5 file bridge paths ──
# The EA reads/writes from the MT5 Common Files folder via FILE_COMMON.
# Python must write to the same physical folder on disk.
# These paths are confirmed for Derrick's Mac setup.
import os as _os
MT5_COMMON_FILES = _os.path.expanduser(
    "~/Library/Application Support/net.metaquotes.wine.metatrader5"
    "/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files"
)
SIGNAL_FILE = _os.path.join(MT5_COMMON_FILES, "signal.json")
SIGNAL_ACK_FILE = _os.path.join(MT5_COMMON_FILES, "signal_ack.json")
