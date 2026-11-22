"""Backtest of the pre-open screener EXACTLY as it trades (screener/preopen_screener.py).

- Universe: per trade day, mean turnover over the previous 60 *sessions* (min 40 present), top 250, prev close >= 50.
- Signal: gap = open / prev_close - 1 (open = final pre-open auction price = IEP at 09:08); rel gap vs universe median.
- Picks: up to 10 with 1% <= gap < 15%, highest rel gap.  Short at the open (auction fill).
- Sizing: capital/10 per name (fixed slots; idle cash when fewer picks).  No leverage.
- Exit: 15:15-15:20.  Proxies: NSE LAST price (15:30 last trade) over the full period; exact 15:15 price from
  Yahoo hourly bars (rescaled to NSE prices) over the last ~2 years.
- Costs: Zerodha MIS equity schedule (brokerage min(Rs20, 0.03%) per order, STT 0.025% sell, NSE txn 0.00297%,
  SEBI Rs10/cr, GST 18%, stamp 0.003% buy) + exit slippage.
"""
import sys
import numpy as np, pandas as pd
from bhav_load import load_raw

pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300); pd.set_option("display.max_columns", 30)
S = "/tmp/claude-0/-home-user-Trading-Setup/04cd1917-3f1d-54b6-ab52-ada8d9151cf0/scratchpad"
K, GMIN, GMAX, TOPN = 10, 0.01, 0.15, 250


def zerodha_cost(notional, slip=0.0003):
    brok = np.minimum(20, 0.0003 * notional) * 2
    txn = 0.0000297 * notional * 2
    sebi = 0.000001 * notional * 2
    gst = 0.18 * (brok + txn + sebi)
    stt = 0.00025 * notional
    stamp = 0.00003 * notional
    return brok + txn + sebi + gst + stt + stamp + slip * notional


def build():
    d = load_raw()
    d = d[(d.open > 0) & (d.prev_close > 0)].copy()
    tv = d.pivot(index="day", columns="sym", values="turnover").sort_index()
    tv60 = tv.rolling(60, min_periods=40).mean().shift(1)   # sessions = rows of the date index
    rk = tv60.rank(axis=1, ascending=False)
    rk = rk.stack().rename("rank").reset_index()
    d = d.merge(rk, on=["day", "sym"], how="left")
    d["univ"] = (d["rank"] <= TOPN) & (d.prev_close >= 50)
    d["gap"] = d.open / d.prev_close - 1
    return d


def select(d, noise=0.0, seed=0):
    u = d[d.univ & (d.gap.abs() < 0.5)].copy()
    sig = u.gap
    if noise:
        sig = sig + np.random.default_rng(seed).normal(0, noise, len(u))
    u["sig"] = sig
    u["rel"] = u.sig - u.groupby("day").sig.transform("median")
    c = u[(u.sig >= GMIN) & (u.sig < GMAX)]
    c = c.assign(r=c.groupby("day").rel.rank(ascending=False, method="first"))
    return c[c.r <= K].copy()


def simulate(p, capital, exit_col="last", stop=None, slip=0.0003, all_days=None):
    p = p.copy()
    slot = capital / K
    p["qty"] = np.floor(slot / p.open)
    p = p[p.qty > 0]
    p["notional"] = p.qty * p.open
    ex = p[exit_col]
    if stop is not None:
        stop_px = p.open * (1 + stop)
        hit = p.high >= stop_px
        ex = np.where(hit, stop_px * (1 + 0.001), ex)   # 0.1% extra slippage on stop fills
        p["stopped"] = hit
    p["exit"] = ex
    p["gross"] = p.qty * (p.open - p.exit)
    p["cost"] = zerodha_cost(p.notional, slip)
    p["pnl"] = p.gross - p.cost
    p["ret"] = p.pnl / p.notional
    daily = p.groupby("day").pnl.sum()
    if all_days is not None:
        daily = daily.reindex(all_days, fill_value=0.0)
    return p, daily


def metrics(daily, capital, label):
    r = daily / capital
    eq = capital + daily.cumsum()
    dd = (eq / eq.cummax() - 1)
    traded = r[r != 0]
    yrs = len(r) / 248
    comp = (1 + r).prod() ** (1 / yrs) - 1
    worst_month = r.groupby(r.index.to_period("M")).sum().min()
    return dict(label=label, days=len(r), trade_days=len(traded), avg_day_pct=round(r.mean() * 100, 3),
                simple_ann_pct=round(r.mean() * 248 * 100, 1), cagr_comp_pct=round(comp * 100, 1),
                sharpe=round(r.mean() / r.std() * np.sqrt(248), 2), win_days_pct=round((traded > 0).mean() * 100, 1),
                maxDD_pct=round(dd.min() * 100, 1), worst_day_pct=round(r.min() * 100, 2),
                worst_month_pct=round(worst_month * 100, 1))


def exit_1515(p):
    """Exact 15:15 price on NSE basis: NSE LAST * (Yahoo price at 15:15 / Yahoo final close). Yahoo 1h bars."""
    h = pd.read_csv(f"{S}/yf_h1.csv.gz").dropna(subset=["Close"])
    h["sym"] = h.Ticker.str.replace(".NS", "", regex=False)
    t = pd.to_datetime(h.Datetime, utc=True).dt.tz_convert("Asia/Kolkata")
    h["day"] = pd.to_datetime(t.dt.date); h["t"] = t.dt.strftime("%H:%M")
    c = h.pivot_table(index=["sym", "day"], columns="t", values="Close")
    ratio = (c["14:15"] / c["15:15"]).rename("r1515")  # bar 14:15-15:15 close vs last bar close
    p = p.join(ratio, on=["sym", "day"], how="inner")
    p["x1515"] = p["last"] * p.r1515
    return p


if __name__ == "__main__":
    d = build()
    days = pd.Index(sorted(d.day.unique()))
    days = days[days >= "2020-12-15"]          # first day with a full 40-session universe
    p = select(d)
    p = p[p.day >= days[0]]
    CAP = 500000
    print(f"Period {days[0].date()} .. {days[-1].date()}  sessions {len(days)}  trade days {p.day.nunique()}  trades {len(p)}"
          f"  avg picks/trade-day {len(p)/p.day.nunique():.1f}")

    rows = []
    for cap in (200000, 500000, 1000000, 2500000):
        tr, dl = simulate(p, cap, "last", all_days=days)
        rows.append(metrics(dl, cap, f"capital Rs{cap/1e5:.0f}L exit=LAST slip0.03%"))
    for slip in (0.0, 0.0005, 0.001):
        tr, dl = simulate(p, CAP, "last", slip=slip, all_days=days)
        rows.append(metrics(dl, CAP, f"Rs5L exit=LAST slip{slip*100:.2f}%"))
    tr, dl = simulate(p, CAP, "close", all_days=days); rows.append(metrics(dl, CAP, "Rs5L exit=official close"))
    for st in (0.02, 0.03, 0.05):
        tr, dl = simulate(p, CAP, "last", stop=st, all_days=days)
        rows.append(metrics(dl, CAP, f"Rs5L stop-loss {st*100:.0f}% above entry"))
    print("\n## Summary (fixed capital, no compounding of position size; cagr_comp = if returns were compounded)")
    print(pd.DataFrame(rows).to_string(index=False))

    # base case detail
    tr, dl = simulate(p, CAP, "last", all_days=days)
    r = dl / CAP
    print("\n## Base case Rs5L, exit at LAST: by year")
    y = pd.DataFrame({"return_pct": r.groupby(r.index.year).sum() * 100,
                      "maxDD_pct": r.groupby(r.index.year).apply(lambda x: ((CAP + (x * CAP).cumsum()) / (CAP + (x * CAP).cumsum()).cummax() - 1).min() * 100),
                      "trade_days": (r != 0).groupby(r.index.year).sum(),
                      "win_days_pct": r[r != 0].groupby(r[r != 0].index.year).apply(lambda x: (x > 0).mean() * 100),
                      "pnl_Rs": dl.groupby(dl.index.year).sum()}).round(1)
    print(y.to_string())
    print("\n## Monthly return % of capital (base case)")
    m = r.groupby([r.index.year, r.index.month]).sum().unstack() * 100
    m["year"] = m.sum(axis=1)
    print(m.round(1).to_string())
    pos_m = (r.groupby(r.index.to_period("M")).sum() > 0)
    print(f"positive months: {pos_m.sum()}/{len(pos_m)}")

    print("\n## Trade-level (base case)")
    w, l = tr[tr.pnl > 0], tr[tr.pnl <= 0]
    print(f"trades {len(tr)} | win rate {len(w)/len(tr)*100:.1f}% | avg win {w.ret.mean()*100:.2f}% | avg loss {l.ret.mean()*100:.2f}% "
          f"| payoff {w.ret.mean()/-l.ret.mean():.2f} | avg trade {tr.ret.mean()*100:.3f}% | avg cost/trade {(tr.cost/tr.notional).mean()*100:.3f}%")
    print(f"worst trade {tr.ret.min()*100:.1f}% | trades losing >5%: {(tr.ret<-0.05).sum()} | >10%: {(tr.ret<-0.10).sum()}")
    adverse = (tr.high / tr.open - 1)
    print(f"max adverse move intraday (high vs entry): median {adverse.median()*100:.2f}%, 90th pct {adverse.quantile(.9)*100:.2f}%, 99th {adverse.quantile(.99)*100:.2f}%")
    lock = (tr.close >= tr.high * 0.999) & ((tr.close / tr.prev_close - 1) >= 0.095)
    print(f"possible upper-circuit closes (close==high & day >= +9.5%): {lock.sum()} of {len(tr)} trades")
    print("\nworst 10 days:"); print((r.nsmallest(10) * 100).round(2).to_string())
    s = (r < 0).astype(int); grp = (s != s.shift()).cumsum(); print("longest losing streak (sessions):", s.groupby(grp).sum().max())
    eq = CAP + dl.cumsum(); dd = eq / eq.cummax() - 1; trough = dd.idxmin(); peak = eq[:trough].idxmax()
    rec = eq[trough:][eq[trough:] >= eq[peak]]
    print(f"max drawdown {dd.min()*100:.1f}% from {peak.date()} to {trough.date()}, recovered {rec.index[0].date() if len(rec) else 'NOT YET'}")
    print(f"current drawdown {dd.iloc[-1]*100:.1f}%")

    print("\n## Last 12 months, monthly % (base)")
    print((r[r.index >= r.index[-1] - pd.Timedelta(days=365)].groupby(lambda x: x.strftime("%Y-%m")).sum() * 100).round(2).to_string())

    # exact 15:15 exit (Yahoo, ~2y)
    q = exit_1515(p)
    dd2 = days[days >= q.day.min()]
    rows = []
    for col, lab in (("x1515", "exit 15:15 (exact)"), ("last", "exit LAST"), ("close", "exit close")):
        tr2, dl2 = simulate(q, CAP, col, all_days=dd2)
        rows.append(metrics(dl2, CAP, f"{lab} {dd2[0].date()}..{dd2[-1].date()}"))
        if col == "x1515":
            h = len(dd2) // 2
            rows.append(metrics(dl2.iloc[:h], CAP, "  15:15 first half")); rows.append(metrics(dl2.iloc[h:], CAP, "  15:15 second half"))
    print("\n## Exit-time check on the ~2y with intraday data (trades matched to Yahoo:", len(q), ")")
    print(pd.DataFrame(rows).to_string(index=False))

    # signal noise: 09:03 snapshot differs from final auction price
    rows = []
    for nz in (0.0, 0.002, 0.005):
        res = []
        for seed in range(10):
            pn = select(d, nz, seed); pn = pn[pn.day >= days[0]]
            _, dln = simulate(pn, CAP, "last", all_days=days)
            res.append(dln)
        mm = [metrics(x, CAP, "") for x in res]
        rows.append(dict(noise_sd_pct=nz * 100, avg_day_pct=np.mean([x["avg_day_pct"] for x in mm]).round(3),
                         sharpe=np.mean([x["sharpe"] for x in mm]).round(2), maxDD=np.mean([x["maxDD_pct"] for x in mm]).round(1)))
    print("\n## Selection with a noisy 09:03 gap estimate (10 seeds each; fills still at the auction price)")
    print(pd.DataFrame(rows).to_string(index=False))
    # missed days
    rng = np.random.default_rng(1)
    for miss in (0.1, 0.25):
        keep = pd.Index(rng.choice(days, int(len(days) * (1 - miss)), replace=False))
        _, dlm = simulate(p[p.day.isin(keep)], CAP, "last", all_days=days)
        print(metrics(dlm, CAP, f"miss {int(miss*100)}% of days at random"))
