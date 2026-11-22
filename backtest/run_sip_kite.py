import sys, glob, os, itertools, pandas as pd
from sip_orb import run, summarize
S = sys.argv[1]
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
fr = []
for f in glob.glob(f"{S}/kite/out/*.csv"):
    x = pd.read_csv(f); x["symbol"] = os.path.basename(f)[:-4]; fr.append(x)
m = pd.concat(fr).drop_duplicates(["symbol", "date"])
m["date"] = pd.to_datetime(m.date, utc=True).dt.tz_convert("Asia/Kolkata")
m["day"] = m.date.dt.date
# daily bars built from the same 5m data (consistent volume); ATR uses prior 14 days
d = m.groupby(["symbol", "day"]).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum")).reset_index()
print("symbols", m.symbol.nunique(), "days", m.day.nunique(), m.day.min(), m.day.max())
mid = sorted(m.day.unique())[len(m.day.unique()) // 2]
grid = list(itertools.product([1, 3], [3, 5, 10], [("atr", 0.1), ("atr", 0.25), ("atr", 0.5), ("or", None)], [None, 3]))
rows = []
for orb, top, (sm, sa), tgt in grid:
    tr = run(m, d, or_bars=orb, top_n=top, stop_atr=sa or 0, stop_mode=sm, target_r=tgt, cost_pct=0.0015, min_tv=5e8)
    if len(tr) == 0: continue
    lab = f"OR{orb*5} top{top} stop={sm}{sa or ''} tgt={tgt}"
    s = summarize(tr, lab)
    tr2 = tr.copy(); tr2["R"] = tr2.gross_R - 0.0008 * tr2.entry / tr2.risk
    s["netR@0.08%"] = round(tr2.R.mean(), 3)
    s["H1 netR"] = round(tr[tr.day < mid].R.mean(), 3); s["H2 netR"] = round(tr[tr.day >= mid].R.mean(), 3)
    rows.append(s)
print(pd.DataFrame(rows).sort_values("netR/tr", ascending=False).to_string(index=False))
