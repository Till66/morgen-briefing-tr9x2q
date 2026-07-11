#!/usr/bin/env python3
"""
Fetches current quotes + a short price history (for sparkline charts) for
a curated list of major world stocks/indices from Yahoo Finance's free,
no-API-key chart endpoint, and writes stocks.json for the dashboard's
ticker section.

Runs server-side (GitHub Actions), so there's no CORS concern - the
frontend just reads the resulting static JSON file.

(Previously used Stooq's CSV endpoints, but Stooq's quote endpoint now
returns "Access denied" for server-side/automated requests, so we moved
to Yahoo Finance's chart API, which returns both the current price and a
ready-made close-price history in a single request per symbol.)
"""
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# Yahoo Finance symbol -> display name. Feel free to add/remove tickers
# here; the frontend renders whatever ends up in stocks.json automatically.
SYMBOLS = [
    ("^GSPC", "S&P 500"),
    ("^DJI", "Dow Jones"),
    ("^IXIC", "Nasdaq Composite"),
    ("^GDAXI", "DAX"),
    ("^N225", "Nikkei 225"),
    ("^HSI", "Hang Seng"),
    ("AAPL", "Apple"),
    ("MSFT", "Microsoft"),
    ("GOOGL", "Alphabet (Google)"),
    ("AMZN", "Amazon"),
    ("NVDA", "Nvidia"),
    ("TSLA", "Tesla"),
    ("META", "Meta"),
]


def fetch_url(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_symbol(symbol, days=30):
    """Returns (price, change_pct, history) for one symbol via Yahoo
    Finance's chart endpoint, or None on failure."""
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(symbol, safe='')}?range=3mo&interval=1d"
    )
    try:
        data = json.loads(fetch_url(url))
        result = (data.get("chart") or {}).get("result") or []
        if not result:
            return None
        r = result[0]
        meta = r.get("meta") or {}
        price = meta.get("regularMarketPrice")
        if price is None:
            return None

        closes = []
        quotes = (r.get("indicators") or {}).get("quote") or []
        if quotes:
            closes = [c for c in (quotes[0].get("close") or []) if c is not None]
        history = closes[-days:] if closes else []

        # Use yesterday's close (second-to-last daily close in the series)
        # for the day-over-day change, not "chartPreviousClose" - that field
        # is the close at the START of the whole requested range (here: ~3
        # months ago), which produces wildly inflated percentages.
        prev_close = closes[-2] if len(closes) >= 2 else meta.get("previousClose")
        change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0
        return {"price": price, "change_pct": change_pct, "history": history}
    except Exception as exc:
        print(f"Warning: failed to fetch {symbol}: {exc}", file=sys.stderr)
        return None


def main():
    stocks = []
    for symbol, name in SYMBOLS:
        q = fetch_symbol(symbol)
        if not q:
            continue
        stocks.append({
            "symbol": symbol.lstrip("^"),
            "name": name,
            "price": q["price"],
            "change_pct": q["change_pct"],
            "history": q["history"],
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
