"""Load NSE sec_bhavdata_full daily files into one panel (EQ series only).

Every row is one stock-day with: open, high, low, close, prev_close (NSE-adjusted for
corporate actions on ex-dates), vwap (AVG_PRICE), volume, turnover (Rs), delivery %.
Derived columns:
  gap  = open / prev_close - 1        (overnight return, known at 09:15 after pre-open)
  o2c  = close / open - 1             (the intraday trade: buy open, sell close)
  o2v  = vwap / open - 1              (proxy for exiting through the day at VWAP)
Universe flag `univ`: top N by trailing 60-day mean turnover (lagged one day) and price >= 50
-> point-in-time proxy for large + midcap (Nifty 100 + Midcap 150 ~ 250 names).
"""
import glob, os, sys
import numpy as np, pandas as pd

BHAV = os.environ.get("BHAV_DIR", "/tmp/claude-0/-home-user-Trading-Setup/04cd1917-3f1d-54b6-ab52-ada8d9151cf0/scratchpad/bhav")
CACHE = os.path.join(os.path.dirname(BHAV), "panel.parquet")


def load_raw():
    if os.path.exists(CACHE) and os.path.getmtime(CACHE) > max(os.path.getmtime(f) for f in glob.glob(BHAV + "/*.csv")):
        return pd.read_parquet(CACHE)
    fr = []
    for f in sorted(glob.glob(BHAV + "/*.csv")):
        x = pd.read_csv(f, skipinitialspace=True)
        x.columns = [c.strip() for c in x.columns]
        x = x[x.SERIES.str.strip() == "EQ"]
        fr.append(x)
    d = pd.concat(fr, ignore_index=True)
    d = d.rename(columns={"SYMBOL": "sym", "DATE1": "day", "PREV_CLOSE": "prev_close", "OPEN_PRICE": "open",
                          "HIGH_PRICE": "high", "LOW_PRICE": "low", "LAST_PRICE": "last", "CLOSE_PRICE": "close",
                          "AVG_PRICE": "vwap", "TTL_TRD_QNTY": "volume", "TURNOVER_LACS": "turnover",
                          "NO_OF_TRADES": "trades", "DELIV_PER": "deliv"})
    d["day"] = pd.to_datetime(d.day.str.strip(), format="%d-%b-%Y")
    for c in ["prev_close", "open", "high", "low", "last", "close", "vwap", "volume", "turnover", "trades", "deliv"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["turnover"] *= 1e5
    d = d[["sym", "day", "prev_close", "open", "high", "low", "last", "close", "vwap", "volume", "turnover", "trades", "deliv"]]
    d = d.dropna(subset=["open", "close", "prev_close"]).drop_duplicates(["sym", "day"]).sort_values(["sym", "day"])
    d.reset_index(drop=True).to_parquet(CACHE)
    return d


def panel(top_n=250, min_px=50):
    d = load_raw().copy()
    d = d[(d.open > 0) & (d.prev_close > 0)]
    d["gap"] = d.open / d.prev_close - 1
    d["o2c"] = d.close / d.open - 1
    d["o2v"] = d.vwap / d.open - 1
    d["c2c"] = d.close / d.prev_close - 1
    g = d.groupby("sym")
    d["tv60"] = g.turnover.transform(lambda s: s.rolling(60, min_periods=40).mean().shift(1))
    d["rank_tv"] = d.groupby("day").tv60.rank(ascending=False)
    d["univ"] = (d.rank_tv <= top_n) & (d.prev_close >= min_px)
    return d


if __name__ == "__main__":
    d = panel()
    print(d.day.min(), d.day.max(), d.day.nunique(), "days", d.sym.nunique(), "symbols")
    print(d[d.univ].groupby(d.day.dt.year).sym.nunique())
