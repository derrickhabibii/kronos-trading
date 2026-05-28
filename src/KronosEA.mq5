//+------------------------------------------------------------------+
//| KronosEA.mq5                                                     |
//| Kronos Trading System — MT5 Expert Advisor (file bridge)         |
//|                                                                  |
//| What this does:                                                  |
//|   Runs on a 5-second timer inside MT5. Checks for a signal.json |
//|   file written by the Python system. If a new (unconsumed)      |
//|   signal is found, places the order with SL/TP, writes an       |
//|   acknowledgement file, and marks the signal as consumed.        |
//|                                                                  |
//| Setup — BEFORE attaching this EA to a chart:                    |
//|   1. Set SignalFile and AckFile to filenames inside MT5's Common |
//|      Files folder. On Mac this is:                               |
//|      ~/Library/Application Support/MetaQuotes/Terminal/          |
//|                                        Common/Files/             |
//|   2. Set the same path in Python's write_signal() call in        |
//|      main.py so both sides point to the same physical file.      |
//|   3. Attach this EA to any chart for the instrument you trade.   |
//|      The pair to trade comes from the signal file itself, not    |
//|      the chart symbol.                                           |
//|                                                                  |
//| IMPORTANT — symbol name:                                         |
//|   The "pair" field in signal.json must match the exact symbol    |
//|   name in your MT5 (e.g. "BTCUSD" or "BTCUSD."). Check your     |
//|   broker's symbol list and update config.py if needed.           |
//+------------------------------------------------------------------+
#property copyright "Kronos Trading System"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

//── Input parameters ──────────────────────────────────────────────
// These are shown in the EA settings panel when you attach it to a chart.
// SignalFile: filename (relative to MT5 Common Files folder) that Python writes to.
// AckFile:    filename the EA writes back to confirm the signal was processed.
input string SignalFile = "signal.json";       // Signal file Python writes
input string AckFile    = "signal_ack.json";   // Acknowledgement file EA writes back

//── Trade object ──────────────────────────────────────────────────
// CTrade handles order placement — cleaner than OrderSend() directly.
CTrade trade;


//+------------------------------------------------------------------+
//| EA initialisation — called once when EA starts                   |
//+------------------------------------------------------------------+
int OnInit()
{
    // Start the 5-second timer
    EventSetTimer(5);
    Print("KronosEA started. Watching: ", SignalFile);
    return INIT_SUCCEEDED;
}


//+------------------------------------------------------------------+
//| EA cleanup — called when EA is removed or terminal closes        |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    EventKillTimer();
    Print("KronosEA stopped.");
}


//+------------------------------------------------------------------+
//| Timer callback — fires every 5 seconds                           |
//+------------------------------------------------------------------+
void OnTimer()
{
    ProcessSignalFile();
}


//+------------------------------------------------------------------+
//| Extract a field value from a simple flat JSON string.            |
//|                                                                  |
//| Handles two value types:                                         |
//|   String values:   "key": "value"  → returns value              |
//|   Numeric/boolean: "key": 1.23     → returns "1.23"             |
//|                                                                  |
//| Does not handle nested objects or arrays — not needed here.      |
//+------------------------------------------------------------------+
string ExtractField(const string json, const string key)
{
    // Look for "key": (with space, as Python's json.dump produces)
    string pattern = "\"" + key + "\": ";
    int pos = StringFind(json, pattern, 0);

    if (pos < 0)
    {
        // Try without space — handle compact JSON just in case
        pattern = "\"" + key + "\":";
        pos = StringFind(json, pattern, 0);
        if (pos < 0) return "";
    }

    // Move past the pattern to the start of the value
    int val_start = pos + StringLen(pattern);

    // If the value starts with a quote, it is a string
    if (StringSubstr(json, val_start, 1) == "\"")
    {
        // Find the closing quote — value is between the two quotes
        int val_end = StringFind(json, "\"", val_start + 1);
        if (val_end < 0) return "";
        return StringSubstr(json, val_start + 1, val_end - val_start - 1);
    }

    // Otherwise numeric, boolean, or null — read until a delimiter
    int val_end = val_start;
    int json_len = StringLen(json);
    while (val_end < json_len)
    {
        string ch = StringSubstr(json, val_end, 1);
        if (ch == "," || ch == "}" || ch == "\r" || ch == "\n")
            break;
        val_end++;
    }

    string result = StringSubstr(json, val_start, val_end - val_start);
    StringTrimRight(result);
    StringTrimLeft(result);
    return result;
}


//+------------------------------------------------------------------+
//| Read the full contents of a file from the MT5 Common Files folder|
//|                                                                  |
//| Uses binary mode (FILE_BIN) to read raw bytes and converts to   |
//| string. This avoids FILE_TXT line-ending issues on Wine/Mac      |
//| where Unix \n line endings can cause FileReadString to misbehave.|
//+------------------------------------------------------------------+
string ReadFile(const string filename)
{
    int fh = FileOpen(filename, FILE_READ | FILE_BIN | FILE_COMMON);
    if (fh == INVALID_HANDLE)
        return "";

    ulong file_size = FileSize(fh);
    if (file_size == 0)
    {
        FileClose(fh);
        return "";
    }

    uchar buf[];
    ArrayResize(buf, (int)file_size);
    FileReadArray(fh, buf, 0, (int)file_size);
    FileClose(fh);

    return CharArrayToString(buf, 0, (int)file_size);
}


//+------------------------------------------------------------------+
//| Write a string to a file in the MT5 Common Files folder          |
//+------------------------------------------------------------------+
bool WriteFile(const string filename, const string text)
{
    int fh = FileOpen(filename, FILE_WRITE | FILE_TXT | FILE_COMMON);
    if (fh == INVALID_HANDLE)
    {
        Print("KronosEA: Could not open ", filename, " for writing. Error=", GetLastError());
        return false;
    }
    FileWriteString(fh, text);
    FileClose(fh);
    return true;
}


//+------------------------------------------------------------------+
//| Main logic — check for a signal file and act on it               |
//+------------------------------------------------------------------+
void ProcessSignalFile()
{
    // Try to read the signal file — returns "" if the file does not exist yet
    string content = ReadFile(SignalFile);
    if (content == "")
        return;   // No signal file yet — nothing to do

    // Check if this signal has already been processed
    string consumed = ExtractField(content, "consumed");
    if (consumed == "true")
        return;   // Already handled — do nothing until Python writes a new signal

    // Parse the fields needed to place the order
    string direction = ExtractField(content, "direction");
    string pair      = ExtractField(content, "pair");
    double lot_size  = StringToDouble(ExtractField(content, "lot_size"));
    double target    = StringToDouble(ExtractField(content, "target_price"));
    double stop      = StringToDouble(ExtractField(content, "stop_price"));

    Print("KronosEA: Signal received | direction=", direction,
          " pair=", pair, " lots=", lot_size,
          " target=", target, " stop=", stop);

    long   ticket       = 0;
    bool   order_placed = false;

    // One position at a time — no stacking
    if (PositionsTotal() > 0 && direction != "flat")
    {
        Print("KronosEA: ", PositionsTotal(), " position(s) already open. Signal skipped — no stacking.");
        order_placed = true;
    }
    else if (direction == "flat")
    {
        // No trade on a flat signal — just acknowledge so Python can move on
        Print("KronosEA: direction=flat — no order placed.");
        order_placed = true;
    }
    else if (direction == "long")
    {
        // BUY market order — target is take profit, stop is stop loss
        // stop=0 means use market price; SL and TP are set explicitly
        if (trade.Buy(lot_size, pair, 0, stop, target, "Kronos"))
        {
            ticket = trade.ResultOrder();
            order_placed = true;
            Print("KronosEA: BUY placed. Ticket=", ticket);
        }
        else
        {
            Print("KronosEA: BUY failed. Error=", GetLastError(),
                  " RetCode=", trade.ResultRetcode());
        }
    }
    else if (direction == "short")
    {
        // SELL market order — target is take profit, stop is stop loss
        if (trade.Sell(lot_size, pair, 0, stop, target, "Kronos"))
        {
            ticket = trade.ResultOrder();
            order_placed = true;
            Print("KronosEA: SELL placed. Ticket=", ticket);
        }
        else
        {
            Print("KronosEA: SELL failed. Error=", GetLastError(),
                  " RetCode=", trade.ResultRetcode());
        }
    }
    else
    {
        Print("KronosEA: Unknown direction '", direction, "' — skipping.");
        return;
    }

    // If the order failed (long/short only) — do not acknowledge.
    // Python will time out and can retry on the next candle.
    if (!order_placed)
        return;

    //── Write acknowledgement file ────────────────────────────────
    // Python's read_acknowledgement() polls for this file.
    // ticket=0 for flat signals (no order placed).
    string ack = "{\n  \"status\": \"executed\",\n  \"order_ticket\": "
                 + IntegerToString(ticket) + "\n}\n";

    if (WriteFile(AckFile, ack))
        Print("KronosEA: Acknowledgement written to ", AckFile);

    //── Mark signal as consumed ───────────────────────────────────
    // Rewrite signal.json with "consumed": true so the EA ignores it
    // on the next timer tick while Python processes the acknowledgement.
    string updated = content;
    StringReplace(updated, "\"consumed\": false", "\"consumed\": true");
    WriteFile(SignalFile, updated);
}
