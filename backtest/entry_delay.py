"""Does the gap fade survive realistic entry timing?  Uses Yahoo 5m (last 60d) and 1h (last ~2y)
bars for the stocks picked by the daily rule (signal = bhavcopy gap at the open).
For each pick: short return from various entry times to the close (15:15 bar close and official close).
"""
import numpy as np, pandas as pd
from bhav_load import panel
from bhav_strats import add_features
from gap_fade import picks

S = "/tmp/claude-0/-home-user-Trading-Setup/04cd1917-3f1d-54b6-ab52-ada8d9151cf0/scratchpad"
pd.set_option("display.width", 250)


def load_yf(name):
    m = pd.read_csv(f"{S}/yf_{name}.csv.gz").dropna(subset=["Open"])
    m["sym"] = m.Ticker.str.replace(".NS", "", regex=False)
    m["dt"] = pd.to_datetime(m.Datetime, utc=True).dt.tz_convert("Asia/Kolkata")
    m["day"] = pd.to_datetime(m.dt.dt.date)
    m["t"] = m.dt.dt.strftime("%H:%M")
    return m


def entry_table(m, pk, times, exit_t):
    px_open = m.pivot_table(index=["sym", "day"], columns="t", values="Open")
    px_close = m.pivot_table(index=["sym", "day"], columns="t", values="Close")
    j = pk.set_index(["sym", "day"]).join(px_open[times], how="inner").join(px_close[[exit_t]].rename(columns={exit_t: "xc"}))
    res = {}
    for t in times:
        res[f"enter {t} ->close"] = -(j.close / j[t] - 1)
        res[f"enter {t} ->{exit_t}c"] = -(j.xc / j[t] - 1)
    res["bhav open->close"] = -(j.close / j.open - 1)
    r = pd.DataFrame(res)
    return r, j


def summarize(r, cost):
    g = r.groupby(level="day").mean() - cost
    out = pd.DataFrame({"bps/day": (g.mean() * 1e4).round(1), "sharpe": (g.mean() / g.std() * np.sqrt(250)).round(2),
                        "hit%": ((g > 0).mean() * 100).round(1)})
    out["days"] = len(g)
    return out


if __name__ == "__main__":
    d = add_features(panel())
    for k, gmin in [(10, 0.0), (10, 0.01), (5, 0.01)]:
        pk = picks(d, k, gmin=gmin)[["sym", "day", "open", "close", "gap"]]
        m5 = load_yf("m5")
        r, j = entry_table(m5, pk, ["09:15", "09:20", "09:25", "09:30", "09:45", "10:00"], "15:15")
        print(f"\n=== 5-minute data, k={k} gap>={gmin*100:.0f}%, cost 0.12% ({j.index.get_level_values('day').min().date()} .. {j.index.get_level_values('day').max().date()}), picks matched {len(j)}/{len(pk[pk.day>=j.index.get_level_values('day').min()])}")
        print(summarize(r, 0.0012).to_string())
        h1 = load_yf("h1")
        r, j = entry_table(h1, pk, ["09:15", "10:15", "11:15"], "15:15")
        print(f"--- 1-hour data k={k} gap>={gmin*100:.0f}% ({j.index.get_level_values('day').min().date()} .. {j.index.get_level_values('day').max().date()}), picks {len(j)}")
        print(summarize(r, 0.0012).to_string())
