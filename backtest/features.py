import sys, pandas as pd, numpy as np, engine
from engine import load
from strategies import orb
S=sys.argv[1]; COST=0.0006
pd.set_option("display.width",220)
def feat(df):
    d=df.groupby("day").agg(o=("open","first"),h=("high","max"),l=("low","min"),c=("close","last"))
    d["pc"]=d.c.shift(1); d["gap"]=(d.o/d.pc-1)*100
    d["rng"]=(d.h-d.l)/d.c*100; d["atr"]=d.rng.rolling(14).mean().shift(1)
    d["nr7"]=(d.rng.shift(1)==d.rng.shift(1).rolling(7).min())
    d["prev_ret"]=(d.c/d.pc-1).shift(1)*100
    d["ma20"]=(d.c>d.c.rolling(20).mean()).shift(1)
    d["dow"]=pd.to_datetime(d.index).dayofweek
    return d
for name in ["nifty","banknifty"]:
    df=load(f"{S}/data/{name}_5m.csv"); F=feat(df)
    for om in [15,30]:
        tr=orb(df,om,None,"range",last_entry="13:00")
        tr=tr.join(F,on="day")
        tr["net"]=(tr.side*(tr.exit-tr.entry)-COST*tr.entry)/tr.entry*100
        tr["R"]=(tr.side*(tr.exit-tr.entry)-COST*tr.entry)/tr.risk
        tr["orw"]=tr.risk/tr.entry*100/tr.atr  # OR width rel to ATR (approx)
        tr["is"]=pd.to_datetime(tr.day).dt.year<=2023
        tr["gapdir"]=np.sign(tr.gap)==tr.side
        tr["trend"]=(tr.ma20==(tr.side==1))
        tr["orwq"]=pd.qcut(tr.orw,4,labels=False)
        tr["atrq"]=pd.qcut(tr.atr,3,labels=False)
        print(f"===== {name} ORB{om}  all: n={len(tr)} net%/tr={tr.net.mean():.3f}")
        for f in ["gapdir","trend","nr7","orwq","atrq","dow","side"]:
            g=tr.groupby([f,"is"]).agg(n=("net","size"),net=("net","mean"),win=("net",lambda x:(x>0).mean()),R=("R","mean")).round(3).unstack("is")
            print(g.to_string()); print()
