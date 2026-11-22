# Pre-open gap-fade screener

Implements the best intraday rule from `backtest/RESULTS.md` (round 2): short the large/midcap stocks with the
biggest gap-up at the open, cover before the close.

## Daily routine (IST)

| Time | Step |
|---|---|
| 09:00 | `python3 screener/preopen_screener.py --watch --capital 500000` (refreshes every 20 s until 09:08) |
| ~09:06 | Take the latest list. Place **SELL, MIS** orders for each name (market, or limit at/below the IEP) |
| 09:07–09:08 | Pre-open order entry closes (random). Orders fill at the opening auction price |
| 15:15–15:20 | Cover (buy back) every position |
| after 18:00 | `python3 screener/preopen_screener.py --review YYYY-MM-DD` to log the day's result from NSE bhavcopy |

No list / "NO TRADE" means no stock gapped up >= 1%: stay flat that day.

## Rule
- Universe: top 250 NSE EQ stocks by mean traded value over the last 60 sessions, previous close >= Rs 50.
- Gap = pre-open IEP / previous close − 1; relative gap = gap − median gap of the universe.
- Picks: up to 10 names with the highest relative gap and raw gap between +1% and +15%.
- Size: equal rupees per name (default 1/10 of `--capital`).

## Requirements
Python 3.9+, `pandas`, `requests`. The first run downloads ~60 bhavcopy files from nsearchives.nseindia.com into `screener/cache/`.

## Caveats
- The backtest edge was weak in 2026 Q2–Q3; paper-trade first and use `--review` to track real results.
- The edge depends on getting the auction price. Entering after 09:15 removed most of it in testing.
- Check that your broker allows MIS shorts in the pre-open session and for each symbol (some stocks are blocked for intraday shorting).
- Research tool, not investment advice.
