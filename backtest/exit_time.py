"""Gap fade: entry 09:15/09:20 (Yahoo bar open), exit at various bar closes, plus stop-loss variants.
All prices from Yahoo for both legs (consistent adjustment)."""
import numpy as np, pandas as pd
from bhav_load import panel
from bhav_strats import add_features
from gap_fade import picks
from entry_delay import load_yf

pd.set_option("display.width", 250)


def run(m, pk, entry_t, exit_ts, cost):
    O = m.pivot_table(index=["sym", "day"], columns="t", values="Open")
    C = m.pivot_table(index=["sym", "day"], columns="t", values="Close")
    j = pk.set_index(["sym", "day"]).join(O[[entry_t]].rename(columns={entry_t: "e"}), how="inner").join(C[exit_ts])
    rows = {}
    for x in exit_ts:
        g = (-(j[x] / j.e - 1)).groupby(level="day").mean() - cost
        rows[f"{entry_t}->{x}"] = dict(bps_day=round(g.mean() * 1e4, 1), sharpe=round(g.mean() / g.std() * np.sqrt(250), 2),
                                       hit=round((g > 0).mean() * 100, 1), days=len(g),
                                       H1=round(g[: len(g) // 2].mean() * 1e4, 1), H2=round(g[len(g) // 2:].mean() * 1e4, 1))
    return pd.DataFrame(rows).T, j


if __name__ == "__main__":
    d = add_features(panel())
    m5, h1 = load_yf("m5"), load_yf("h1")
    # sanity: Yahoo first-bar open vs NSE official open
    chk = m5[m5.t == "09:15"].merge(d[["sym", "day", "open", "close"]], on=["sym", "day"])
    print("Yahoo 09:15 open / NSE open - 1 (bps): median", round(((chk.Open / chk.open - 1) * 1e4).median(), 2),
          " |diff|>10bps share", round((((chk.Open / chk.open - 1).abs()) > 0.001).mean(), 3))
    for k, gmin in [(10, 0.0), (10, 0.01), (5, 0.01), (5, 0.02)]:
        pk = picks(d, k, gmin=gmin)[["sym", "day", "gap"]]
        t, _ = run(h1, pk, "09:15", ["09:15", "10:15", "11:15", "12:15", "13:15", "14:15", "15:15"], 0.0012)
        print(f"\n### k={k} gap>={gmin*100:.0f}%  1h bars (~2y)  cost 0.12%  (exit = close of bar starting at)")
        print(t.to_string())
        for e in ("09:15", "09:20"):
            t, _ = run(m5, pk, e, ["09:25", "09:40", "10:10", "10:25", "11:10", "12:10", "13:10", "15:10"], 0.0012)
            print(f"--- 5m bars (60d) entry {e}")
            print(t.to_string())
