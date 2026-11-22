import sys, pandas as pd, numpy as np, engine
from engine import load, stats
from strategies import orb
S=sys.argv[1]
pd.set_option("display.width",200)
for name in ["nifty","banknifty"]:
    df=load(f"{S}/data/{name}_5m.csv")
    rows=[]
    for c in [0.0, 0.0004]:
        engine.COST_PCT=c
        for om in [15,30]:
            tr=orb(df,om,None,"range")
            rows.append(stats(tr,f"cost={c} ORB{om} EOD"))
            # fade: invert side
            f=tr.copy(); f["side"]*=-1
            rows.append(stats(f,f"cost={c} FADE-ORB{om} EOD (mirror)"))
    print("====",name); print(pd.DataFrame(rows).to_string(index=False))
