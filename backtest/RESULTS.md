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

## Do news, fundamentals or external factors help? (`factor_analysis.py`)

Data added (all known before 09:07 IST): 359k NSE corporate announcements with timestamps for the 668 traded stocks
(results / material event / routine, released between the previous close and the pre-open); S&P 500, Nasdaq, VIX,
crude, gold, USD/INR, dollar index, US 10y (last close before the session); India VIX, Nifty trend; FII index-futures
long ratio (NSE participant OI); F&O membership and sector (current NSE lists).
Method: per-trade net return by bucket in 2021-24 vs 2025-26, yearly rank correlation, walk-forward ridge model.

Findings
- News: no stable effect. Overnight results news: +0.56%/trade vs +0.41% without (2021-24) but +0.21% vs +0.26% (2025-26).
  Gaps on news fade about as much as gaps without news in large/midcaps. Filtering on news lowers returns (62-45%/yr vs 72%).
- External factors: every correlation is tiny (|IC| < 0.1). Most consistent: higher India VIX = better (6/6 years),
  crude up overnight = worse (5/6), gold up = worse (5/6), Nifty up yesterday = worse (5/6).
- Walk-forward model on all features: dropping its worst-predicted third reduced returns in 4 of 5 years.
- Stock traits: Metals & Mining loses in both periods (−0.15%/trade): their gaps carry real overnight commodity news.
  F&O-only names avoid circuit risk but return far less (27%/yr, 2026 −15%).

Simple rules vs base (72%/yr, Sharpe 3.3, DD −15.7%, last 12m +13%):
| Rule | Return/yr | Sharpe | Max DD | 2026 YTD | Last 12m | Circuit-stress worst month |
|---|---|---|---|---|---|---|
| Skip Metals & Mining | 74% | 3.5 | −12.4% | +12.9% | +18.2% | −18.2% |
| Skip days crude > +2% overnight | 67% | 3.3 | −10.3% | +8.2% | +13.0% | −13.4% |
| Skip days India VIX < 12 | 69% | 3.4 | −15.7% | +14.1% | +15.0% | −25.6% |
| All three | 63% | 3.5 | −9.5% | +11.8% | +13.2% | −11.6% |
Caveat: these rules were chosen after looking at the full sample (both periods), so expect less in live trading.
