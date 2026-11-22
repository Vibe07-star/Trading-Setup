"""Stocks-in-Play Opening Range Breakout (after Zarattini, Barbon & Aziz 2024), adapted to NSE.

Input: 5-minute bars for many stocks (columns: symbol,date,open,high,low,close,volume)
       and daily bars (symbol,day,open,high,low,close,volume) for ATR / liquidity.
Rules per day:
  1. Eligible: prev-14d avg traded value >= MIN_TV (Rs), open >= MIN_PX.
  2. RVOL = volume of first OR bars / mean of same over previous 14 sessions; need >= RVOL_MIN.
  3. Take top-N by RVOL.  Direction = colour of the opening range (close vs open); doji skipped.
  4. Entry: stop order at OR high (long) / OR low (short); fills at level, or at bar open if gapped.
  5. Stop loss: STOP_ATR * ATR14 from entry (or other mode).  Exit at 15:15 bar close.
  Same-bar entry & stop -> assume stopped (pessimistic).
Costs: COST_PCT round trip of entry notional (brokerage+STT+fees+slippage).
"""
import numpy as np, pandas as pd


def prep_daily(d):
    d = d.sort_values(["symbol", "day"]).copy()
    g = d.groupby("symbol")
    pc = g.close.shift(1)
    tr = np.maximum(d.high - d.low, np.maximum((d.high - pc).abs(), (d.low - pc).abs()))
    d["atr14"] = tr.groupby(d.symbol).transform(lambda s: s.rolling(14).mean().shift(1))
    d["tv14"] = (d.close * d.volume).groupby(d.symbol).transform(lambda s: s.rolling(14).mean().shift(1))
    return d[["symbol", "day", "atr14", "tv14"]]


def first_bars(m, or_bars):
    m = m.sort_values(["symbol", "date"])
    m["k"] = m.groupby(["symbol", "day"]).cumcount()
    o = m[m.k < or_bars].groupby(["symbol", "day"]).agg(
        o=("open", "first"), h=("high", "max"), l=("low", "min"), c=("close", "last"), v=("volume", "sum")).reset_index()
    o = o.sort_values(["symbol", "day"])
    o["v14"] = o.groupby("symbol").v.transform(lambda s: s.rolling(14, min_periods=10).mean().shift(1))
    o["rvol"] = o.v / o.v14
    return m, o


def run(m, daily, or_bars=1, top_n=20, rvol_min=1.0, stop_atr=0.10, min_tv=2e8, min_px=50,
        cost_pct=0.0012, last_t="15:15", target_r=None, stop_mode="atr"):
    m = m.copy()
    m["t"] = m.date.dt.strftime("%H:%M")
    m, o = first_bars(m, or_bars)
    o = o.merge(prep_daily(daily), on=["symbol", "day"], how="left")
    o = o[(o.tv14 >= min_tv) & (o.o >= min_px) & (o.rvol >= rvol_min) & o.atr14.notna()]
    o = o[o.c != o.o]
    o["rank"] = o.groupby("day").rvol.rank(ascending=False, method="first")
    o = o[o["rank"] <= top_n]
    sel = o.set_index(["symbol", "day"])
    mm = m.set_index(["symbol", "day"]).loc[sel.index.unique()].reset_index()
    out = []
    for (sym, day), b in mm.groupby(["symbol", "day"], sort=False):
        r = sel.loc[(sym, day)]
        side = 1 if r.c > r.o else -1
        lvl = r.h if side == 1 else r.l
        b = b[b.k >= or_bars]
        O, H, L, C, T = b.open.values, b.high.values, b.low.values, b.close.values, b.t.values
        entry = None
        for i in range(len(b)):
            if T[i] > last_t:
                break
            if entry is None:
                if T[i] >= "15:00":
                    break
                hit = H[i] >= lvl if side == 1 else L[i] <= lvl
                if not hit:
                    continue
                entry = max(O[i], lvl) if side == 1 else min(O[i], lvl)
                if stop_mode == "atr":
                    risk = stop_atr * r.atr14
                else:  # opposite side of opening range
                    risk = abs(r.h - r.l)
                stop = entry - side * risk
                tgt = None if target_r is None else entry + side * target_r * risk
                # same bar: stop touched after entry?
                if (side == 1 and L[i] <= stop) or (side == -1 and H[i] >= stop):
                    out.append((sym, day, side, entry, stop, risk, "stop")); break
                if tgt is not None and ((side == 1 and C[i] >= tgt) or (side == -1 and C[i] <= tgt)):
                    out.append((sym, day, side, entry, tgt, risk, "target")); break
                continue
            if side == 1:
                if O[i] <= stop: out.append((sym, day, side, entry, O[i], risk, "stop")); break
                if L[i] <= stop: out.append((sym, day, side, entry, stop, risk, "stop")); break
                if tgt is not None and H[i] >= tgt: out.append((sym, day, side, entry, max(tgt, O[i]), risk, "target")); break
            else:
                if O[i] >= stop: out.append((sym, day, side, entry, O[i], risk, "stop")); break
                if H[i] >= stop: out.append((sym, day, side, entry, stop, risk, "stop")); break
                if tgt is not None and L[i] <= tgt: out.append((sym, day, side, entry, min(tgt, O[i]), risk, "target")); break
            if T[i] >= last_t:
                out.append((sym, day, side, entry, C[i], risk, "eod")); break
    tr = pd.DataFrame(out, columns=["symbol", "day", "side", "entry", "exit", "risk", "reason"])
    if len(tr):
        tr["gross_R"] = tr.side * (tr.exit - tr.entry) / tr.risk
        tr["cost_R"] = cost_pct * tr.entry / tr.risk
        tr["R"] = tr.gross_R - tr.cost_R
    return tr


def summarize(tr, label=""):
    if len(tr) == 0:
        return dict(label=label, n=0)
    w, l = tr[tr.R > 0], tr[tr.R <= 0]
    daily = tr.groupby("day").R.mean()  # equal risk per trade, averaged per day
    days = tr.day.nunique()
    eq = tr.groupby("day").R.sum().cumsum()
    return dict(label=label, n=len(tr), days=days, **{
        "win%": round(100 * len(w) / len(tr), 1),
        "avgW_R": round(w.R.mean(), 2) if len(w) else 0,
        "avgL_R": round(l.R.mean(), 2) if len(l) else 0,
        "W/L": round(w.R.mean() / -l.R.mean(), 2) if len(l) and len(w) else np.nan,
        "PF": round(w.R.sum() / -l.R.sum(), 2) if len(l) else np.inf,
        "grossR/tr": round(tr.gross_R.mean(), 3),
        "costR/tr": round(tr.cost_R.mean(), 3),
        "netR/tr": round(tr.R.mean(), 3),
        "totR": round(tr.R.sum(), 1),
        "maxDD_R": round((eq - eq.cummax()).min(), 1),
    })
