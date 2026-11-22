"""Simple, conservative intraday backtest engine for 5-minute index data.

Conventions (deliberately pessimistic):
- Signals are evaluated on a bar's CLOSE; entry is at the NEXT bar's OPEN.
- If stop and target are both touched in the same bar, the STOP is assumed hit first.
- Stops gap: if a bar opens beyond the stop, fill at that bar's open.
- Any open position is closed at the close of the 15:15 bar (exits by 15:20).
- Round-trip cost is charged in price terms: COST_PCT * entry price
  (covers brokerage, STT, exchange fees, stamp duty and slippage on index futures).
"""
import numpy as np
import pandas as pd

COST_PCT = 0.0004  # 0.04% round trip ~ 10 Nifty pts at 25k (conservative)


def load(path):
    df = pd.read_csv(path, parse_dates=["date"])
    df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_convert("Asia/Kolkata")
    df["day"] = df["date"].dt.date
    df["t"] = df["date"].dt.strftime("%H:%M")
    return df


def simulate(bars, side, entry_idx, stop, target, last_t="15:15"):
    """bars: one day's dataframe (reset index). side: +1 long, -1 short.
    Returns (entry, exit, exit_reason)."""
    o, h, l, c, t = (bars[k].values for k in ("open", "high", "low", "close", "t"))
    entry = o[entry_idx]
    for i in range(entry_idx, len(bars)):
        if side == 1:
            if o[i] <= stop and i > entry_idx:
                return entry, o[i], "stop"
            if l[i] <= stop:
                return entry, stop, "stop"
            if target is not None and h[i] >= target:
                return entry, max(target, o[i]) if i > entry_idx else target, "target"
        else:
            if o[i] >= stop and i > entry_idx:
                return entry, o[i], "stop"
            if h[i] >= stop:
                return entry, stop, "stop"
            if target is not None and l[i] <= target:
                return entry, min(target, o[i]) if i > entry_idx else target, "target"
        if t[i] >= last_t:
            return entry, c[i], "eod"
    return entry, c[-1], "eod"


def stats(trades, label=""):
    """trades: DataFrame with columns day, side, entry, exit, risk (points), reason."""
    if len(trades) == 0:
        return {"label": label, "n": 0}
    tr = trades.copy()
    tr["cost"] = COST_PCT * tr["entry"]
    tr["pnl"] = tr["side"] * (tr["exit"] - tr["entry"]) - tr["cost"]
    tr["pnl_pct"] = tr["pnl"] / tr["entry"] * 100
    tr["R"] = tr["pnl"] / tr["risk"]
    wins, losses = tr[tr.pnl > 0], tr[tr.pnl <= 0]
    avg_w = wins.pnl.mean() if len(wins) else 0
    avg_l = -losses.pnl.mean() if len(losses) else np.nan
    eq = tr.pnl_pct.cumsum()
    dd = (eq - eq.cummax()).min()
    years = (pd.to_datetime(tr.day.max()) - pd.to_datetime(tr.day.min())).days / 365.25
    return {
        "label": label,
        "n": len(tr),
        "win%": round(100 * len(wins) / len(tr), 1),
        "avgW/avgL": round(avg_w / avg_l, 2) if avg_l else np.inf,
        "PF": round(wins.pnl.sum() / -losses.pnl.sum(), 2) if len(losses) else np.inf,
        "expR": round(tr.R.mean(), 3),
        "sum%": round(tr.pnl_pct.sum(), 1),
        "%/yr": round(tr.pnl_pct.sum() / max(years, 1e-9), 1),
        "maxDD%": round(dd, 1),
    }


def yearly(trades):
    tr = trades.copy()
    tr["pnl"] = tr["side"] * (tr["exit"] - tr["entry"]) - COST_PCT * tr["entry"]
    tr["pnl_pct"] = tr.pnl / tr.entry * 100
    tr["yr"] = pd.to_datetime(tr.day).dt.year
    g = tr.groupby("yr")
    return pd.DataFrame({
        "n": g.size(),
        "win%": g.apply(lambda x: round(100 * (x.pnl > 0).mean(), 1)),
        "sum%": g.pnl_pct.sum().round(1),
        "PF": g.apply(lambda x: round(x[x.pnl > 0].pnl.sum() / max(-x[x.pnl <= 0].pnl.sum(), 1e-9), 2)),
    })
