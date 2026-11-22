"""Open-to-close (pure intraday) cross-sectional strategies on large+midcap NSE stocks.

Each strategy produces, per day, a set of long and/or short names entered at the open
(pre-open auction price) and closed at the close.  Daily strategy return = mean of the leg
returns (long-short: average of long-leg and short-leg return, i.e. 50/50 gross exposure).
Costs are charged per unit of traded notional (round trip) on every position.

Signals use ONLY information available before 09:15 on the trade day:
  - today's gap (open vs prev close) is published in pre-open (09:00-09:08)
  - every trailing feature is shifted by one day.
"""
import sys
import numpy as np, pandas as pd
from bhav_load import panel

pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)


def add_features(d):
    g = d.groupby("sym")
    for w in (5, 20, 60, 120):
        d[f"io{w}"] = g.o2c.transform(lambda s: s.rolling(w, min_periods=int(w * .7)).mean().shift(1))  # past intraday
        d[f"on{w}"] = g.gap.transform(lambda s: s.rolling(w, min_periods=int(w * .7)).mean().shift(1))  # past overnight
    d["r1"] = g.c2c.shift(1)
    d["r5"] = g.c2c.transform(lambda s: s.rolling(5).sum().shift(1))
    d["vol20"] = g.o2c.transform(lambda s: s.rolling(20, min_periods=14).std().shift(1))
    d["deliv1"] = g.deliv.shift(1)
    d["deliv_z"] = (d.deliv1 - g.deliv.transform(lambda s: s.rolling(20, min_periods=14).mean().shift(2))) / \
                   g.deliv.transform(lambda s: s.rolling(20, min_periods=14).std().shift(2))
    d["mkt_gap"] = d.groupby("day").gap.transform(lambda s: s[d.loc[s.index, "univ"]].median())
    d["rgap"] = d.gap - d.mkt_gap
    d["gap_z"] = d.rgap / d.vol20
    return d


def xs(d, col, k=10, side="ls", ascending_long=True, cost=0.001, ret="o2c", mask=None):
    """Long the k names with the LOWEST `col` (if ascending_long) and short the k highest."""
    u = d[d.univ & d[col].notna() & d[ret].notna() & (d.gap.abs() < 0.15)]
    if mask is not None:
        u = u[mask(u)]
    r = u.groupby("day")[col].rank(method="first", ascending=ascending_long)
    n = u.groupby("day")[col].transform("count")
    longs = u[r <= k]; shorts = u[r > n - k]
    L = longs.groupby("day")[ret].mean() - cost
    S = -shorts.groupby("day")[ret].mean() - cost
    if side == "l":
        return L
    if side == "s":
        return S
    return pd.concat([L, S], axis=1).mean(axis=1)


def report(r, label):
    r = r.dropna()
    yrs = r.groupby(r.index.year)
    ann = r.mean() * 250
    sh = r.mean() / r.std() * np.sqrt(250) if r.std() > 0 else np.nan
    eq = r.cumsum()
    row = dict(label=label, days=len(r), bps_day=round(r.mean() * 1e4, 1), ann_pct=round(ann * 100, 1),
               sharpe=round(sh, 2), hit=round((r > 0).mean() * 100, 1), maxDD_pct=round((eq - eq.cummax()).min() * 100, 1))
    for y, x in yrs:
        row[str(y)] = round(x.mean() * 1e4, 1)
    return row


if __name__ == "__main__":
    cost = float(sys.argv[1]) if len(sys.argv) > 1 else 0.001
    d = add_features(panel())
    rows = []
    for k in (5, 10, 25):
        rows.append(report(xs(d, "rgap", k, cost=cost), f"gap reversal LS k={k}"))
        rows.append(report(xs(d, "rgap", k, side="l", cost=cost), f"gap reversal long-only k={k}"))
        rows.append(report(xs(d, "rgap", k, side="s", cost=cost), f"gap reversal short-only k={k}"))
        rows.append(report(xs(d, "gap_z", k, cost=cost), f"gap-z reversal LS k={k}"))
        rows.append(report(xs(d, "rgap", k, ascending_long=False, cost=cost), f"gap CONTINUATION LS k={k}"))
        for w in (20, 60, 120):
            rows.append(report(xs(d, f"io{w}", k, ascending_long=False, cost=cost), f"intraday persistence io{w} LS k={k}"))
            rows.append(report(xs(d, f"on{w}", k, cost=cost), f"overnight-mom reversal on{w} LS k={k}"))
        rows.append(report(xs(d, "r1", k, cost=cost), f"prev-day reversal LS k={k}"))
        rows.append(report(xs(d, "r5", k, cost=cost), f"5d reversal LS k={k}"))
        rows.append(report(xs(d, "deliv_z", k, ascending_long=False, cost=cost), f"delivery spike LS k={k}"))
    out = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    print(f"cost per position round trip = {cost*100:.2f}%")
    print(out.to_string(index=False))
