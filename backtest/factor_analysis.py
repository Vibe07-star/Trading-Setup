"""Do news, external/macro factors or stock characteristics improve the gap-up fade?

Per-trade net returns come from screener_backtest (Rs 5L, exit at LAST, Zerodha costs).
Every feature uses only information available before the pre-open order cut-off (09:07 IST) on the trade day.

News      : NSE corporate announcements per stock with timestamps (prev session 15:30 -> 09:07 today = overnight news).
External  : US indices / VIX / crude / USDINR / DXY / US10Y (last close dated before the trade day), India VIX,
            Nifty trend, FII index-futures positioning (NSE participant-wise OI, previous day), market median gap.
Stock     : F&O membership & sector (current NSE lists -> mild look-ahead), size rank, gap size, prior volume spike.
Validation: fit 2021-2024 vs test 2025-2026, and a walk-forward ridge model (train on prior years, predict next year).
"""
import glob, json, os
import numpy as np, pandas as pd
from screener_backtest import build, select, simulate
from bhav_load import load_raw

pd.set_option("display.width", 250); pd.set_option("display.max_rows", 400); pd.set_option("display.max_columns", 30)
E = "/tmp/claude-0/-home-user-Trading-Setup/04cd1917-3f1d-54b6-ab52-ada8d9151cf0/scratchpad/ext"

RESULTS = {"Financial Result Updates", "Outcome of Board Meeting", "Integrated Filing- Financial", "Investor Presentation"}
MATERIAL = {"Press Release", "Press Release (Revised)", "Acquisition", "Bagging/Receiving of orders/contracts", "Amalgamation/Merger",
            "Scheme of Arrangement", "Credit Rating", "Monthly Business Updates", "Disclosure of other UPSI/material event",
            "Action(s) taken or orders passed", "Action(s) initiated or orders passed", "Issue of Securities",
            "Qualified Institutional Placement", "Pendency of Litigation(s)/dispute(s) or the outcome impacting the Company",
            "Dividend", "Buyback", "Capacity addition", "Change in Management", "Resignation"}


def news_features(tr, days):
    prev = pd.Series(days[:-1], index=days[1:])
    rows = []
    for f in glob.glob(f"{E}/ann/*.json"):
        sym = os.path.basename(f)[:-5]
        for x in json.load(open(f)):
            t = pd.to_datetime(x["an_dt"], format="%d-%b-%Y %H:%M:%S", errors="coerce")
            if pd.isna(t):
                continue
            desc = x["desc"] or ""
            txt = (x.get("attchmntText") or "").lower()
            if desc in RESULTS or "financial result" in txt:
                cat = "results"
            elif desc in MATERIAL:
                cat = "material"
            else:
                cat = "routine"
            rows.append((sym, t, cat))
    a = pd.DataFrame(rows, columns=["sym", "t", "cat"])
    out = tr[["sym", "day"]].copy()
    out["prev"] = out.day.map(prev)
    m = out.merge(a, on="sym")
    lo = m.prev + pd.Timedelta(hours=15, minutes=30)
    hi = m.day + pd.Timedelta(hours=9, minutes=7)
    on = m[(m.t > lo) & (m.t <= hi)]
    dprev = m[(m.t > m.prev + pd.Timedelta(hours=9)) & (m.t <= lo)]
    f = pd.DataFrame(index=pd.MultiIndex.from_frame(out[["sym", "day"]]))
    for c in ("results", "material", "routine"):
        f[f"on_{c}"] = on[on.cat == c].groupby(["sym", "day"]).size().reindex(f.index, fill_value=0) > 0
        f[f"prevday_{c}"] = dprev[dprev.cat == c].groupby(["sym", "day"]).size().reindex(f.index, fill_value=0) > 0
    f["news_overnight"] = np.select([f.on_results, f.on_material, f.on_routine], ["results", "material", "routine"], "none")
    return f.reset_index()


def market_features(days):
    c = pd.read_csv(f"{E}/ext_close.csv", index_col=0, parse_dates=True).sort_index()
    ret = c.pct_change()
    feats = {}
    ret = c.apply(lambda s: s.dropna().pct_change())
    for col, name in [("^GSPC", "spx_ret"), ("^IXIC", "ndx_ret"), ("CL=F", "crude_ret"), ("INR=X", "usdinr_ret"),
                      ("DX-Y.NYB", "dxy_ret"), ("GC=F", "gold_ret")]:
        feats[name] = ret[col]
    feats["us10y_chg"] = c["^TNX"].dropna().diff()
    feats["vix"] = c["^VIX"]
    n = c["^NSEI"].dropna(); iv = c["^INDIAVIX"].dropna()
    feats["nifty_ret1"] = n.pct_change(); feats["nifty_ret5"] = n.pct_change(5)
    feats["nifty_vs_50dma"] = n / n.rolling(50).mean() - 1
    feats["indiavix"] = iv; feats["indiavix_chg"] = iv.pct_change()
    F = pd.DataFrame(feats)
    # value known before 09:07 IST on day t = last observation dated strictly before t
    F = F.reindex(F.index.union(days)).sort_index().ffill().shift(1).reindex(days)
    # FII index futures positioning from participant OI (previous session)
    rows = []
    for f in glob.glob(f"{E}/poi/*.csv"):
        try:
            x = pd.read_csv(f, skiprows=1)
            x.columns = [s.strip() for s in x.columns]
            r = x[x["Client Type"].str.strip() == "FII"].iloc[0]
            L, S = float(r["Future Index Long"]), float(r["Future Index Short"])
            rows.append((pd.to_datetime(os.path.basename(f)[:8], format="%d%m%Y"), L / (L + S)))
        except Exception:
            pass
    fii = pd.Series(dict(rows)).sort_index()
    fii = fii[~fii.index.duplicated()]
    F["fii_long_ratio"] = fii.reindex(fii.index.union(days)).ffill().shift(1).reindex(days)
    F["fii_ratio_chg5"] = F.fii_long_ratio - F.fii_long_ratio.shift(5)
    return F


def bucket_table(df, col, q=None, bins=None, target="ret"):
    x = df.copy()
    if q:
        x[col] = pd.qcut(x[col], q, duplicates="drop")
    elif bins is not None:
        x[col] = pd.cut(x[col], bins)
    t = x.groupby([col, "per"], observed=True)[target].agg(["size", "mean"])
    t["mean"] = (t["mean"] * 100).round(3)
    return t.unstack("per")


if __name__ == "__main__":
    d = build()
    days = pd.Index(sorted(d.day.unique())); days = days[days >= "2020-12-15"]
    p = select(d); p = p[p.day >= days[0]]
    tr, dl = simulate(p, 500000, "last", all_days=days)
    tr = tr.reset_index(drop=True)
    tr["per"] = np.where(tr.day < "2025-01-01", "fit_21-24", "test_25-26")

    # ---- stock features
    raw = load_raw()
    g = raw.groupby("sym")
    raw["vr1"] = raw.volume.groupby(raw.sym).shift(1) / g.volume.transform(lambda s: s.rolling(20, min_periods=14).mean().shift(2))
    tr = tr.merge(raw[["sym", "day", "vr1"]], on=["sym", "day"], how="left")
    fo = pd.read_csv(f"{E}/fo_mktlots.csv", skipinitialspace=True)
    fo_syms = set(fo.iloc[:, 1].astype(str).str.strip())
    tr["fno"] = tr.sym.isin(fo_syms)
    n5 = pd.read_csv(f"{E}/ind_nifty500list.csv")
    tr = tr.merge(n5[["Symbol", "Industry"]].rename(columns={"Symbol": "sym", "Industry": "sector"}), on="sym", how="left")
    tr["sector"] = tr.sector.fillna("not in N500 now")
    nf = news_features(tr, days)
    tr = tr.merge(nf, on=["sym", "day"], how="left")
    mf = market_features(days)
    tr = tr.merge(mf, left_on="day", right_index=True, how="left")
    tr["mkt_gap"] = tr.day.map(d[d.univ].groupby("day").gap.median())

    print(f"trades {len(tr)}  |  avg net return per trade: fit {tr[tr.per.str.startswith('fit')].ret.mean()*100:.3f}%  "
          f"test {tr[tr.per.str.startswith('test')].ret.mean()*100:.3f}%")
    print("\n#################  1. NEWS (per-trade avg net return %, size)")
    print(bucket_table(tr, "news_overnight").to_string())
    for c in ("on_results", "on_material", "prevday_results", "prevday_material"):
        print(bucket_table(tr, c).to_string())
    print("\n#################  2. STOCK CHARACTERISTICS")
    print(bucket_table(tr, "fno").to_string())
    print(bucket_table(tr, "rank", bins=[0, 50, 100, 150, 200, 250]).to_string())
    print(bucket_table(tr, "gap", bins=[0.01, 0.02, 0.03, 0.05, 0.08, 0.15]).to_string())
    print(bucket_table(tr, "vr1", bins=[0, 0.8, 1.2, 2, 4, 1000]).to_string())
    sec = bucket_table(tr, "sector"); sec = sec[sec[("size", "fit_21-24")] >= 150]
    print(sec.sort_values(("mean", "fit_21-24")).to_string())

    print("\n#################  3. EXTERNAL / MARKET (per-trade, quintiles)")
    for c in ("spx_ret", "ndx_ret", "vix", "crude_ret", "usdinr_ret", "dxy_ret", "us10y_chg", "gold_ret", "indiavix",
              "indiavix_chg", "nifty_ret1", "nifty_ret5", "nifty_vs_50dma", "fii_long_ratio", "fii_ratio_chg5", "mkt_gap"):
        print(f"\n-- {c}"); print(bucket_table(tr, c, q=5).to_string())

    # ---- 4. correlation stability: Spearman IC of each numeric feature with trade return, by year
    num = ["gap", "rel", "rank", "vr1", "spx_ret", "ndx_ret", "vix", "crude_ret", "usdinr_ret", "dxy_ret", "us10y_chg",
           "gold_ret", "indiavix", "indiavix_chg", "nifty_ret1", "nifty_ret5", "nifty_vs_50dma", "fii_long_ratio",
           "fii_ratio_chg5", "mkt_gap"]
    tr["yr"] = tr.day.dt.year
    ic = pd.DataFrame({c: tr.groupby("yr").apply(lambda x: x[c].astype(float).rank().corr(x.ret.rank())) for c in num + ["on_results", "on_material"]}).T
    ic["same_sign_yrs"] = (np.sign(ic[[2021, 2022, 2023, 2024, 2025, 2026]]) == np.sign(ic[[2021, 2022, 2023, 2024, 2025, 2026]].mean(axis=1)).values[:, None]).sum(axis=1)
    print("\n#################  4. Rank correlation (IC) of each feature with trade return, by year")
    print(ic.drop(columns=[2020], errors="ignore").round(3).to_string())

    # ---- 5. walk-forward model: ridge on standardized features, train on all prior years, predict next year
    feats = num + ["on_results", "on_material", "on_routine", "prevday_results", "prevday_material", "fno"]
    X = tr[feats].astype(float)
    X = X.fillna(X.median())
    res = []
    for yr in range(2022, 2027):
        trn, tst = tr.yr < yr, tr.yr == yr
        mu, sd = X[trn].mean(), X[trn].std().replace(0, 1)
        A = ((X[trn] - mu) / sd).values; y = tr.loc[trn, "ret"].values
        lam = 50.0
        w = np.linalg.solve(A.T @ A + lam * np.eye(A.shape[1]), A.T @ (y - y.mean()))
        pred = ((X[tst] - mu) / sd).values @ w
        t = tr[tst].assign(pred=pred)
        t["pq"] = t.groupby("day").pred.rank(pct=True)
        base = t.groupby("day").pnl.sum().reindex(days[days.year == yr], fill_value=0)
        keep = t[t.pred >= np.quantile(pred, 1 / 3)]          # drop the worst-predicted third
        filt = keep.groupby("day").pnl.sum().reindex(days[days.year == yr], fill_value=0)
        top = t[t.pred >= np.quantile(pred, 2 / 3)].groupby("day").pnl.sum().reindex(days[days.year == yr], fill_value=0)
        res.append(dict(year=yr, base_ret_pct=round(base.sum() / 5e3, 1), base_sharpe=round(base.mean() / base.std() * np.sqrt(248), 2),
                        drop_worst_third_pct=round(filt.sum() / 5e3, 1), dwt_sharpe=round(filt.mean() / filt.std() * np.sqrt(248), 2),
                        top_third_only_pct=round(top.sum() / 5e3, 1),
                        pred_ic=round(pd.Series(pred).rank().corr(pd.Series(t.ret.values).rank()), 3)))
    print("\n#################  5. Walk-forward ridge model using ALL features (returns % of Rs5L capital)")
    print(pd.DataFrame(res).to_string(index=False))
    coef_names = feats
    print("last-fit standardized weights (bps per 1 sd):", {k: round(v * 1e4, 1) for k, v in sorted(zip(coef_names, w), key=lambda z: -abs(z[1]))[:10]})
    tr.to_parquet(f"{E}/trades_features.parquet")
