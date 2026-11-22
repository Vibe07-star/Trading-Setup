"""Which conditions make the gap-up fade work in BOTH the fit period (2020-10..2024) and the test period (2025-2026)?
Analysis on per-trade short returns (open->close, bps, before cost) of the top-k relative gap-ups."""
import numpy as np, pandas as pd
from bhav_load import panel
from bhav_strats import add_features
from gap_fade import picks

pd.set_option("display.width", 250); pd.set_option("display.max_rows", 400)

d = add_features(panel())
g = d.groupby("sym")
d["vr1"] = d.volume.groupby(d.sym).shift(1) / g.volume.transform(lambda s: s.rolling(20, min_periods=14).mean().shift(2))
d["ma20d"] = d.prev_close / g.close.transform(lambda s: s.rolling(20, min_periods=14).mean().shift(1)) - 1
d["hi52"] = d.prev_close / g.close.transform(lambda s: s.rolling(250, min_periods=120).max().shift(1)) - 1
d["dow"] = d.day.dt.dayofweek
d["mkt_o2c_prev"] = d.groupby("day").o2c.transform("median")
md = d[d.univ].groupby("day").agg(mkt_gap=("gap", "median"), mkt_o2c=("o2c", "median")).sort_index()
md["mkt_prev"] = md.mkt_o2c.shift(1)
md["mkt_gap_q"] = pd.qcut(md.mkt_gap, 5, labels=False)
d = d.drop(columns=["mkt_gap"]).merge(md[["mkt_gap", "mkt_prev", "mkt_gap_q"]], left_on="day", right_index=True)

p = picks(d, 10, gmin=0.01).copy()
p["ret"] = -p.o2c * 1e4
p["per"] = np.where(p.day < "2025-01-01", "fit", "test")
p["gapq"] = pd.qcut(p.gap, 4, labels=False)


def tab(col, bins=None):
    x = p.copy()
    if bins is not None:
        x[col] = pd.cut(x[col], bins)
    t = x.groupby([col, "per"], observed=True).ret.agg(["size", "mean"]).round(1).unstack("per")
    print(f"\n-- {col}"); print(t.to_string())


tab("gapq")
tab("r1", [-1, -0.03, -0.01, 0, 0.01, 0.03, 1])
tab("r5", [-1, -0.05, 0, 0.05, 0.1, 1])
tab("vr1", [0, 0.7, 1, 1.5, 2.5, 100])
tab("ma20d", [-1, -0.05, 0, 0.05, 0.1, 1])
tab("hi52", [-1, -0.2, -0.1, -0.03, 0.001])
tab("deliv1", [0, 30, 45, 60, 100])
tab("dow")
tab("mkt_gap_q")
tab("mkt_prev", [-1, -0.005, 0, 0.005, 1])
tab("vol20", [0, 0.012, 0.018, 0.025, 1])
