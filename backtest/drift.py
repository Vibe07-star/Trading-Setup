"""Decompose gap-fade P&L: market intraday drift vs stock-relative reversal, by year and half-year."""
import numpy as np, pandas as pd
from bhav_load import panel
from bhav_strats import add_features
from gap_fade import picks
pd.set_option("display.width", 250)
d = add_features(panel())
u = d[d.univ & (d.gap.abs() < .15)]
mkt = u.groupby("day").agg(m_o2c=("o2c", "mean"), m_gap=("gap", "mean"))
for k, gmin in [(10, 0.0), (10, 0.01), (5, 0.01), (20, 0.01)]:
    p = picks(d, k, gmin=gmin)
    s = p.groupby("day").o2c.mean().to_frame("pick").join(mkt)
    s["short_raw"] = -s.pick
    s["hedged"] = -(s.pick - s.m_o2c)          # short picks, long equal-weight universe (proxy for index futures hedge)
    s["mkt_long"] = s.m_o2c
    h = s.groupby(s.index.to_period("Q"))[["short_raw", "hedged", "mkt_long"]].mean() * 1e4
    print(f"\n=== k={k} gap>={gmin*100:.0f}%  gross bps/day by quarter (no costs)")
    print(h.round(1).T.to_string())
