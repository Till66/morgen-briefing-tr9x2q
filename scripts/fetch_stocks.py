#!/usr/bin/env python3
"""
Fetches current quotes + a short price history (for sparkline charts) for
a curated list of major world stocks/indices from Stooq's free, no-API-key
CSV endpoints, and writes stocks.json for the dashboard's ticker section.

Runs server-side (GitHub Actions), so there's no CORS concern - the
frontend just reads the resulting static JSON file.
"""
import csv
import io
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

USER_AGENT = "Mozilla/5.0 (compatible; MorningNewsDashboard/1.0)"

# symbol -> display name. Feel free to add/remove tickers here; the
# frontend renders whatever ends up in stocks.json automatically.
SYMBOLS = [
    ("^spx", "S&P 500"),
    ("^dji", "Dow Jones"),
    ("^ndq", "Nasdaq Composite"),
    ("^dax", "DAX"),
    ("^nkx", "Nikkei 225"),
    ("^hsi", "Hang Seng"),
    ("aapl.us", "Apple"),
    ("msft.us", "Microsoft"),
    ("googl.us", "Alphabet (Google)"),
    ("amzn.us", "Amazon"),
    ("nvda.us", "Nvidia"),
    ("tsla.us", "Tesla"),
    ("meta.us", "Meta"),
]


def fetch_url(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_quotes(symbols):
    # Symbols like "^spx" contain characters (^) that must be percent-encoded
    # for the querystring, otherwise Stooq responds with a bare 404.
    joined = ",".join(urllib.parse.quote(s, safe="") for s, _ in symbols)
    url = f"https://stooq.com/q/l/?s={joined}&f=sd2t2ohlcv&h&e=csv"
    text = fetch_url(url)
    reader = csv.DictReader(io.StringIO(text))
    quotes = {}
    for row in reader:
        symbol = (row.get("Symbol") or "").lower()
        close = row.get("Close")
        open_ = row.get("Open")
        if not symbol or close in (None, "N/D"):
            continue
        try:
            close_f = float(close)
            open_f = float(open_) if open_ not in (None, "N/D") else close_f
        except ValueError:
            continue
        quotes[symbol] = {
            "price": close_f,
            "open": open_f,
            "change_pct": round((close_f - open_f) / open_f * 100, 2) if open_f else 0,
        }
    return quotes


def fetch_history(symbol, days=30):
    d2 = datetime.now(timezone.utc).date()
    d1 = d2 - timedelta(days=days * 2)  # extra buffer for weekends/holidays
    url = (
        f"https://stooq.com/q/d/l/?s={urllib.parse.quote(symbol, safe='')}&i=d"
        f"&d1={d1.strftime('%Y%m%d')}&d2={d2.strftime('%Y%m%d')}"
    )
    try:
        text = fetch_url(url)
        reader = csv.DictReader(io.StringIO(text))
        closes = []
        for row in reader:
            close = row.get("Close")
            if close in (None, "N/D", ""):
                continue
            try:
                closes.append(float(close))
            except ValueError:
                continue
        return closes[-days:]
    except Exception as exc:
        print(f"Warning: failed to fetch history for {symbol}: {exc}", file=sys.stderr)
        return []


def main():
    try:
        quotes = fetch_quotes(SYMBOLS)
    except Exception as exc:
        print(f"Warning: failed to fetch quotes: {exc}", file=sys.stderr)
        quotes = {}

    stocks = []
    for symbol, name in SYMBOLS:
        q = quotes.get(symbol)
        if not q:
            continue
        history = fetch_history(symbol)
        stocks.append({
            "symbol": symbol.upper(),
            "name": name,
            "price": q["price"],
            "change_pct": q["change_pct"],
            "history": history,
        })

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stocks": stocks,
    }

    with open("stocks.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(stocks)} stocks to stocks.json")


if __name__ == "__main__":
    main()
