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
