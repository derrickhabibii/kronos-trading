# Kronos Trading System

An end-to-end automated algorithmic trading system built on **Kronos** — a financial foundation model developed by Tsinghua University, trained on 12 billion candles across 45 global exchanges.

The system ingests live market data, runs model inference, generates trade decisions, and executes orders on MetaTrader 5 fully autonomously. No manual intervention during trades.

---

## Architecture

```
Market Data → Kronos Inference → Signal Layer → Execution Bridge → MT5 Live Orders
      ↓              ↓                ↓                ↓
  yfinance      Fine-tuned        Confidence-      MQL5 Expert
  H4 OHLC      Kronos-small       weighted          Advisor
                  (MPS)           lot sizing       (KronosEA)
```

Each component is modular and independently testable. The system runs on a timed H4 loop, processes one decision per candle, and logs every action to CSV.

---

## Components

| File | Description |
|---|---|
| `src/main.py` | Trading loop — wakes on H4 boundary, orchestrates full cycle |
| `src/forecast.py` | Loads Kronos model, runs Monte Carlo inference on OHLC data |
| `src/data_pipeline.py` | Pulls and validates live candle data via yfinance |
| `src/execution.py` | Python side of the MT5 file bridge — writes signals, reads acknowledgements |
| `src/KronosEA.mq5` | MQL5 Expert Advisor — reads signal files and places orders with SL/TP |
| `config.py` | Paths, symbol settings, spread config |

> Signal generation and model fine-tuning logic are proprietary and not included in this repository.

---

## Key Engineering Problems Solved

**1. Two unfixed bugs in the Kronos repo**
Before running a single line of inference, two bugs in the open-source Kronos codebase were identified and patched manually:
- `KronosTokenizer.__init__()` missing required positional arguments — documented in GitHub Issues since August 2025, README still broken
- `top_k` called as a function at `model/kronos.py:382` where it is an integer in that scope — fix exists in an unmerged PR (#232)

Both were patched before any production use.

**2. Cross-platform execution bridge**
The MetaTrader 5 Python API is Windows-only. This system runs on macOS (Apple Silicon). Rather than spinning up a Windows VM, a lightweight file bridge was engineered: Python writes a signal JSON to MT5's shared Common Files directory, and a custom MQL5 Expert Advisor reads and executes it on a 5-second timer.

Two encoding bugs were found and fixed during live handshake testing:
- MQL5 `FILE_TXT` mode mishandles Unix `\n` line endings under Wine — fixed by switching to `FILE_BIN` with raw byte reading
- MQL5 writes UTF-16 LE with BOM; Python's default UTF-8 reader fails silently — fixed by specifying `encoding='utf-16'`

**3. Apple Silicon inference**
Kronos inference runs on Apple MPS (Metal Performance Shaders) — GPU-accelerated on M-series without CUDA. Device detection is automatic with CPU fallback.

---

## Tech Stack

- **Model:** Kronos-small (NeoQuasar/Kronos on HuggingFace) — fine-tuned on domain-specific data
- **Inference:** PyTorch with Apple MPS acceleration
- **Data:** yfinance (Phases 1–4), MetaTrader 5 API (Phase 5+)
- **Execution:** MQL5 Expert Advisor via file bridge
- **Broker:** Just Markets MT5 — Standard account, swap-free
- **Language:** Python 3.12, MQL5

---

## Project Status

- [x] Environment setup and bug patching
- [x] Data pipeline (H1 / H4 / D1 OHLC across multiple instruments)
- [x] Model fine-tuning and validation
- [x] Signal layer with confidence-weighted position sizing
- [x] MT5 execution layer (file bridge + MQL5 EA)
- [x] Automated trading loop
- [x] Paper run — completed 14-day live demo run, net positive, all go-live criteria passed
- [ ] Live account deployment

---

## Setup

```bash
# Clone this repo
git clone https://github.com/YOUR_USERNAME/kronos-trading

# Install dependencies
pip install torch transformers pandas numpy yfinance

# Clone Kronos and apply patches (see Known Issues below)
git clone https://github.com/shiyu-coder/Kronos
```

> **Important:** The Kronos repo has two known bugs that must be patched before running. See the Known Issues section in the project blueprint.

Run the system:
```bash
python3 -u src/main.py
```

Prerequisites before each run:
1. MT5 terminal open and connected
2. KronosEA attached to the target symbol chart
3. AutoTrading enabled in MT5 toolbar

---

## Disclaimer

This system is built for research and personal use. Past performance on a demo account does not guarantee future results. Nothing in this repository constitutes financial advice.
