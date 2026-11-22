import sys, itertools, pandas as pd
from engine import load, stats
from strategies import orb, noise_boundary
S = sys.argv[1]
pd.set_option("display.width", 200); pd.set_option("display.max_rows", 500)
for name in ["nifty", "banknifty"]:
    df = load(f"{S}/data/{name}_5m.csv")
    rows = []
    for or_min, rr, sm, d in itertools.product([5, 15, 30], [1.5, 2, 3, 4, None], ["range", "mid"], ["both"]):
        tr = orb(df, or_min, rr, sm, d)
        rows.append(stats(tr, f"ORB{or_min} rr={rr} stop={sm}"))
    for ce, vm in itertools.product([15, 30, 60], [1.0, 1.25]):
        tr = noise_boundary(df, check_every=ce, vm=vm)
        rows.append(stats(tr, f"NOISE every={ce} vm={vm}"))
    print("=====", name)
    print(pd.DataFrame(rows).to_string(index=False))
