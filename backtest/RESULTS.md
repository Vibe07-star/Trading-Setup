# Gap-up fade: backtest of the pre-open screener

Strategy (traded by `screener/preopen_screener.py`): each morning, short up to 10 large/midcap NSE stocks with the
biggest gap-up in the pre-open auction, cover at 15:15–15:20.

Earlier rounds (opening range breakout, stocks-in-play ORB, intraday momentum/persistence, prev-day reversal,
delivery spikes, gap-and-go) all lost money after Indian costs; the gap-up fade was the only robust edge found.
Those scripts were removed; they remain in git history.

## Setup (`screener_backtest.py`)
- Data: official NSE `sec_bhavdata_full` daily files, Oct 2020 – Nov 2026 (loaded by `bhav_load.py`; set `BHAV_DIR`
  to the folder of downloaded CSVs). Exact 15:15 exit check uses Yahoo 1-hour bars (last ~2 years).
- Universe: top 250 NSE EQ stocks by mean turnover over the previous 60 sessions, previous close >= Rs 50.
- Picks: up to 10 with raw gap 1–15%, ranked by gap minus the universe median gap.
- Sizing: capital/10 per name, no leverage. Fill at the auction open; exit at LAST (≈15:30) or exact 15:15.
- Costs: full Zerodha MIS charges (brokerage min(Rs20, 0.03%), STT 0.025% sell, NSE txn, SEBI, GST, stamp) + 0.03% exit slippage.
- Dec 2020 – Nov 2026: 1,466 sessions, 1,443 trade days, 11,605 trades.

## Results (Rs 5 lakh, no stop)

| Metric | Value |
|---|---|
| Avg return per session (of capital) | +0.29% |
| Simple annual return | 72% |
| Sharpe | 3.3 |
| Winning days / positive months | 59.5% / 60 of 72 |
| Max drawdown (of starting capital) | −15.7% |
| Worst day / worst month | −5.8% / −8.4% |
| Trade win rate / avg win / avg loss | 59.8% / +2.39% / −2.63% |
| Avg all-in cost per trade | 0.136% |

By year (% of capital): 2021 +100, 2022 +85, 2023 +49, 2024 +90, 2025 +82, **2026 YTD +8.6** (max DD −10.5%).
Last 12 months: +13% (Sharpe 0.7, 7 of 13 months positive); with exact 15:15 exit +6.7%.

## Sensitivities
- Capital Rs 2L / 10L / 25L: 71% / 77% / 83% per year (brokerage cap).
- Exit slippage 0.10% instead of 0.03%: 59% per year.
- Noisy 09:03 signal (sd 0.5% on the gap): 0.26%/day vs 0.29%.
- Missing 25% of days at random: 55% per year.

## Stop-losses (assumed hit whenever the day's high reaches them)

| Rule | Return / yr | Max DD | Last 12 months (LAST / 15:15 exit) |
|---|---|---|---|
| No stop | 72% | −15.7% | +13% / +6.7% |
| 5% stop | 69% | −13.9% | +3.9% / −2.0% |
| 3% stop | 62% | −10.8% | +6.8% / −5.9% |

## Risks
- Edge has faded in 2026 (single-digit returns vs ~80%/yr before).
- Upper-circuit lock: 80 trades (7–23/yr) closed locked at the high after a ≥9.5% rise. If each settled in the
  short-delivery auction at close+20%: 43%/yr, worst month −25.6%. A 5% stop exits 85% of those first.
- Needs the auction fill (entering after 09:15 removed most of the edge) and intraday shortability of each name.

Recommendation: paper-trade first, use a 5% stop, judge on rolling 3–6 months, stop if a 3-month window is negative after costs.
