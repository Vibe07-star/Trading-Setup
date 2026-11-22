import sys, itertools, pandas as pd
from sip_orb import run, summarize
S = sys.argv[1]
pd.set_option("display.width", 250)
m = pd.read_csv(f"{S}/data/n500_m5.csv.gz").dropna(subset=["Open"])
m = m.rename(columns={"Ticker": "symbol", "Datetime": "date", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
m["date"] = pd.to_datetime(m.date, utc=True).dt.tz_convert("Asia/Kolkata")
m["day"] = m.date.dt.date
d = pd.read_csv(f"{S}/data/n500_d1.csv.gz").dropna(subset=["Open"])
d = d.rename(columns={"Ticker": "symbol", "Date": "day", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
d["day"] = pd.to_datetime(d.day).dt.date
print("first-bar zero-volume share:", (m[m.date.dt.strftime('%H:%M') == '09:15'].volume == 0).mean())
rows = []
for orb, top, sa, cost, sm in itertools.product([1, 3], [5, 20], [0.1, 0.25, 0.5], [0.0, 0.0012], ["atr"]):
    tr = run(m, d, or_bars=orb, top_n=top, stop_atr=sa, cost_pct=cost, stop_mode=sm)
    rows.append(summarize(tr, f"OR{orb*5}m top{top} stop{sa}ATR cost{cost}"))
print(pd.DataFrame(rows).to_string(index=False))
