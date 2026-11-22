# Intraday strategy search — results (Nov 2026)

Target: net-profitable intraday strategy with average win / average loss > 2.
All tests: entry on the next bar or a stop order, pessimistic fills (same-bar stop assumed hit first), exit by 15:15.

| # | Strategy | Data | Best net result | Verdict |
|---|----------|------|-----------------|---------|
| 1 | Opening Range Breakout 5/15/30 min, stop = range / mid, targets 1.5R–4R / EOD | NIFTY & BANKNIFTY 5m, 2021–2026 (1,460 days) | ORB30 NIFTY ≈ breakeven at 0.04% cost; gross +8.9%/yr, wiped out by costs (futures STT 0.05% since Apr 2026) | Fail |
| 2 | Noise-boundary intraday momentum (Zarattini/Aziz/Barbon 2024) | same | W/L 2.3–2.7 but win rate 21–27%, PF 0.67–0.87 | Fail |
| 3 | ORB + filters (gap dir, 20DMA trend, NR7, OR width, ATR regime, weekday) | same, 2021–23 fit vs 2024–26 test | No filter positive in both periods | Fail (overfit) |
| 4 | Stocks-in-Play 5m ORB (Zarattini/Barbon/Aziz 2024, the paper rules: RVOL top-N, 10% ATR stop) | 119 most liquid NSE stocks, Kite 5m, Nov 2025–Nov 2026 | Paper rules: −0.9 to −1.1 R/trade (W/L 4–5 but win rate 6%) | Fail |
| 4b | Stocks-in-Play variants (0.25/0.5 ATR or OR stop, 3R target, top 3/5/10) | same | Best: OR5 top3, 0.5 ATR stop, 3R target: +0.033 R/trade net, PF 1.06, W/L 1.5, 2nd half −0.006 R | Fail (not robust) |

Cost assumptions: index futures 0.04% round trip (current reality ≈0.065%); stocks MIS 0.15% (fees+slippage), also shown at 0.08%.
Universe for #4 chosen by recent turnover → mild survivorship/look-ahead bias, which flatters results.

Key observation: every configuration with avg-win/avg-loss > 2 had a win rate too low to be profitable after Indian costs.

---

## Round 2 (Nov 2026): open-to-close cross-sectional tests on NSE bhavcopy, Oct 2020 – Nov 2026

Data: official NSE `sec_bhavdata_full` daily files (1,590 days, all EQ stocks; incl. VWAP, delivery %).
Universe: point-in-time top 250 by trailing 60-day turnover, price >= Rs 50 (≈ Nifty 100 + Midcap 150, no survivorship bias).
Trade: enter at the official open (pre-open auction price), exit at the close. Scripts: `bhav_load.py`, `bhav_strats.py`, `gap_fade.py`.

| Family (k = names per side) | Net @0.10%/position | Verdict |
|---|---|---|
| Gap continuation ("gap and go") | −35 to −47 bps/day, loses every year | Strongly negative |
| Intraday persistence (Lou-Polk-Skouras), prev-day / 5-day reversal, delivery spike | −2 to −13 bps/day | Fail |
| Overnight-momentum reversal | +1 to +5 bps/day, Sharpe < 1 | Weak |
| **Gap reversal, short-only (short biggest relative gap-ups at open, cover at close)** | **+25 to +41 bps/day, Sharpe 3.3–3.6, positive every year** | **Best found** |
| Gap reversal long-short | +15 to +27 bps/day, Sharpe 3.6–5.4, 2026 ≈ 0 | Good until 2026 |

Best simple rule (k=10, raw gap >= 1%, cost 0.15%): 36 bps/day net, Sharpe 3.2, 58% winning days, max DD −22%;
by year (bps/day): 2021 43, 2022 37, 2023 30, 2024 37, 2025 51, 2026 11.
Gap-bucket table: open->close falls monotonically with the size of the gap-up (−14 bps at 0–0.5% gap, −35 at 2–3%, −113 at >5%).

Execution checks (Yahoo intraday, `entry_delay.py`, `exit_time.py`):
- Entering at Yahoo's 09:15 first-bar open instead of the auction price costs ~15 bps/day: 2y result 17.8 bps/day net @0.12%,
  but only ~2 bps/day in the last 12 months. Entering at 10:15 or later: no edge. => must be executed IN the pre-open auction.
- Exit at 15:15 is as good as / better than the official close; exiting at day VWAP is much worse.
- No feature filter (prior returns, volume, trend, 52w high, delivery, weekday, market gap) is stable across 2020-24 vs 2025-26.
- Gross edge positive in 24/25 quarters; weak 2026 Q2–Q3 (+16, +7 bps/day gross), Q4-to-date +38.
