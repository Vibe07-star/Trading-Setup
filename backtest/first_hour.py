"""First-hour-only version of the gap-up fade: short in the pre-open auction, cover at 10:15 (or other times).

Entry : NSE official open (auction price) for the screener's picks (with metal + crude filters).
Exit  : price at time T on NSE basis = NSE LAST * (Yahoo price at T / Yahoo final close of the day).
        Yahoo 1h bars (last ~2y): close of bar starting 09:15 = price at 10:15, 10:15 bar -> 11:15, ... 14:15 bar -> 15:15.
        Yahoo 5m bars (last ~60 sessions) for 09:30 / 09:45 / 10:00 / 10:15.
Stops : first-hour stop counted as hit whenever the first-hour high reaches it.
Costs : Zerodha MIS schedule + exit slippage (0.05% in the first hour, 0.03% later).
"""
import numpy as np, pandas as pd
from screener_backtest import build, select, zerodha_cost

pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
S = "/tmp/claude-0/-home-user-Trading-Setup/04cd1917-3f1d-54b6-ab52-ada8d9151cf0/scratchpad"
E = S + "/ext"
CAP, K = 500000, 10


def yahoo(name):
    h = pd.read_csv(f"{S}/yf_{name}.csv.gz").dropna(subset=["Close"])
    h["sym"] = h.Ticker.str.replace(".NS", "", regex=False)
    t = pd.to_datetime(h.Datetime, utc=True).dt.tz_convert("Asia/Kolkata")
    h["day"] = pd.to_datetime(t.dt.date); h["t"] = t.dt.strftime("%H:%M")
    return h


def apply_filters(p, days):
    n5 = pd.read_csv(f"{E}/ind_nifty500list.csv")
    metals = set(n5[n5.Industry == "Metals & Mining"].Symbol)
    c = pd.read_csv(f"{E}/ext_close.csv", index_col=0, parse_dates=True)["CL=F"].dropna()
    cr = c.pct_change()
    cr = cr.reindex(cr.index.union(days)).ffill().shift(1).reindex(days)
    bad_days = set(cr[cr > 0.02].index)
    return p[~p.sym.isin(metals) & ~p.day.isin(bad_days)]


def run(q, exit_col, slip, stop=None, high_col=None, days=None):
    q = q.copy()
    q["qty"] = np.floor(CAP / K / q.open); q = q[q.qty > 0]
    q["notional"] = q.qty * q.open
    ex = q[exit_col].values
    if stop is not None:
        sp = q.open * (1 + stop)
        hit = q[high_col] >= sp
        ex = np.where(hit, sp * 1.001, ex)
    q["pnl"] = q.qty * (q.open - ex) - zerodha_cost(q.notional, slip)
    q["ret"] = q.pnl / q.notional
    dl = q.groupby("day").pnl.sum().reindex(days, fill_value=0)
    return q, dl


def stats(q, dl, label):
    r = dl / CAP; e = dl.cumsum(); h = len(r) // 2
    l12 = r[r.index > r.index[-1] - pd.Timedelta(days=365)]
    return dict(label=label, trades=len(q), win_trade_pct=round((q.ret > 0).mean() * 100, 1),
                avg_trade_pct=round(q.ret.mean() * 100, 3), ann_pct=round(r.mean() * 248 * 100, 1),
                sharpe=round(r.mean() / r.std() * np.sqrt(248), 2), win_days_pct=round((r[r != 0] > 0).mean() * 100, 1),
                maxDD_cap_pct=round((e - e.cummax()).min() / CAP * 100, 1), worst_day_pct=round(r.min() * 100, 2),
                first_yr_pct=round(r.iloc[:h].sum() * 100, 1), last_12m_pct=round(l12.sum() * 100, 1))


if __name__ == "__main__":
    d = build()
    alldays = pd.Index(sorted(d.day.unique()))
    p = select(d)
    p = apply_filters(p, alldays)

    # ---- hourly, ~2 years
    h = yahoo("h1")
    C = h.pivot_table(index=["sym", "day"], columns="t", values="Close")
    H = h.pivot_table(index=["sym", "day"], columns="t", values="High")
    ratio = pd.DataFrame({"x1015": C["09:15"], "x1115": C["10:15"], "x1215": C["11:15"], "x1515": C["14:15"],
                          "h1": H["09:15"]}).div(C["15:15"], axis=0)
    q = p.join(ratio, on=["sym", "day"], how="inner").dropna(subset=["x1015", "x1515", "h1"])
    for c in ("x1015", "x1115", "x1215", "x1515", "h1"):
        q[c] = q["last"] * q[c]
    days = alldays[alldays >= q.day.min()]
    print(f"Hourly test: {days[0].date()} .. {days[-1].date()}, {len(q)} trades (metal + crude filters on), Rs 5L, 10 slots\n")
    rows = []
    for col, lab, slip in (("x1015", "cover 10:15 (first hour only)", 0.0005), ("x1115", "cover 11:15", 0.0003),
                           ("x1215", "cover 12:15", 0.0003), ("x1515", "cover 15:15 (current setup)", 0.0003)):
        rows.append(stats(*run(q, col, slip, days=days), lab))
    for st in (0.01, 0.015, 0.02, 0.03):
        rows.append(stats(*run(q, "x1015", 0.0005, stop=st, high_col="h1", days=days), f"10:15 exit + {st*100:.1f}% stop"))
    print(pd.DataFrame(rows).to_string(index=False))

    # gross move by window (bps, per trade, before costs)
    g = pd.DataFrame({"open->10:15": -(q.x1015 / q.open - 1), "10:15->15:15": -(q.x1515 / q.x1015 - 1),
                      "open->15:15": -(q.x1515 / q.open - 1)})
    g["half"] = np.where(q.day < days[len(days) // 2], "first year", "last year")
    print("\nAverage short gross move per trade (%), before costs:")
    print((g.groupby("half").mean() * 100).round(3).to_string())

    # yearly / monthly for the 10:15 version
    qq, dl = run(q, "x1015", 0.0005, days=days)
    r = dl / CAP
    print("\nCover at 10:15 - monthly % of capital:")
    print((r.groupby(r.index.to_period("M")).sum() * 100).round(2).to_frame("pct").T.to_string())

    # ---- 5-minute, last ~60 sessions
    m = yahoo("m5")
    C5 = m.pivot_table(index=["sym", "day"], columns="t", values="Close")
    last5 = C5.ffill(axis=1).iloc[:, -1]
    cols = {"x0930": "09:25", "x0945": "09:40", "x1000": "09:55", "x1015": "10:10", "x1515": "15:10"}
    r5 = pd.DataFrame({k: C5[v] for k, v in cols.items()}).div(last5, axis=0)
    q5 = p.join(r5, on=["sym", "day"], how="inner").dropna()
    for c in cols:
        q5[c] = q5["last"] * q5[c]
    d5 = alldays[alldays >= q5.day.min()]
    rows = [stats(*run(q5, c, 0.0005 if c != "x1515" else 0.0003, days=d5), f"cover {c[1:3]}:{c[3:]}")
            for c in cols]
    print(f"\n5-minute check {d5[0].date()} .. {d5[-1].date()} ({len(d5)} sessions, {len(q5)} trades):")
    print(pd.DataFrame(rows).drop(columns=["first_yr_pct", "last_12m_pct"]).to_string(index=False))
