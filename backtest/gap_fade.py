"""Deep-dive: large/midcap gap-up fade (short at open, cover at close).

Rule family: at the open, among the ~250 most liquid NSE stocks (large+midcap proxy),
take the k names with the largest overnight gap relative to the market's median gap
(optionally scaled by the stock's own volatility), subject to min/max raw gap.
Short at the open, cover at the close (or at day VWAP / last traded price).
"""
import sys
import numpy as np, pandas as pd
from bhav_load import panel
from bhav_strats import add_features, report

pd.set_option("display.width", 260); pd.set_option("display.max_rows", 500)


def picks(d, k=10, col="rgap", gmin=0.0, gmax=0.15, side=-1):
    u = d[d.univ & d[col].notna() & d.o2c.notna() & (d.gap.abs() < gmax)]
    u = u[(u.gap >= gmin)] if side == -1 else u[(u.gap <= -gmin)]
    r = u.groupby("day")[col].rank(method="first", ascending=(side == 1))
    return u[r <= k]


def daily(p, cost, ret="o2c", side=-1):
    return (side * p.groupby("day")[ret].mean() - cost)


if __name__ == "__main__":
    d = add_features(panel())
    d["o2l"] = d["last"] / d.open - 1
    rows = []
    base = picks(d, 10)
    for cost in (0.0006, 0.001, 0.0015, 0.002):
        rows.append(report(daily(base, cost), f"k10 rgap cost={cost*100:.2f}% exit=close"))
    rows.append(report(daily(base, 0.001, "o2l"), "k10 rgap cost=0.10% exit=LAST"))
    rows.append(report(daily(base, 0.001, "o2v"), "k10 rgap cost=0.10% exit=VWAP(day)"))
    for k in (3, 5, 10, 15, 20):
        for gmin in (0.0, 0.01, 0.02, 0.03):
            p = picks(d, k, gmin=gmin)
            rows.append(report(daily(p, 0.0015), f"k={k} gap>={gmin*100:.0f}% cost0.15"))
    for k in (5, 10):
        p = picks(d, k, col="gap_z")
        rows.append(report(daily(p, 0.0015), f"k={k} gap_z cost0.15"))
    # universe size sensitivity
    for n in (100, 150, 250, 400):
        dd = d.copy(); dd["univ"] = (dd.rank_tv <= n) & (dd.prev_close >= 50)
        rows.append(report(daily(picks(dd, 10), 0.0015), f"univ top{n} k10 cost0.15"))
    out = pd.DataFrame(rows)
    print(out.to_string(index=False))

    # gap bucket profile (all universe stock-days)
    u = d[d.univ & (d.gap.abs() < 0.15)].copy()
    u["gb"] = pd.cut(u.gap * 100, [-15, -5, -3, -2, -1, -0.5, 0, 0.5, 1, 2, 3, 5, 15])
    print("\nopen->close (bps) by raw gap bucket, all large+mid stock-days")
    print(u.groupby("gb", observed=True).agg(n=("o2c", "size"), o2c_bps=("o2c", lambda x: round(x.mean() * 1e4, 1)),
                                              o2v_bps=("o2v", lambda x: round(x.mean() * 1e4, 1)),
                                              hit_dn=("o2c", lambda x: round((x < 0).mean() * 100, 1))).to_string())
    # 2026 by month for base rule
    r = daily(base, 0.0015)
    print("\nbase k10 cost0.15 by month, last 18 months (bps/day)")
    print((r[r.index >= "2025-06-01"].groupby(r[r.index >= "2025-06-01"].index.to_period("M")).mean() * 1e4).round(1).to_string())
