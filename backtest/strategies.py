import numpy as np
import pandas as pd
from engine import simulate


def orb(df, or_min=15, rr=2.0, stop_mode="range", direction="both", last_entry="11:00",
        min_or_pct=0.0, max_or_pct=9.9, filt=None):
    """Opening-range breakout. Range = first `or_min` minutes from 09:15.
    Signal: a 5m bar CLOSES outside the range -> enter next bar open.
    stop_mode: 'range' = opposite side of range, 'mid' = range midpoint.
    rr: target as multiple of initial risk (None -> hold to EOD)."""
    n_or = or_min // 5
    out = []
    for day, b in df.groupby("day", sort=True):
        b = b.reset_index(drop=True)
        if len(b) < 60:
            continue
        rng = b.iloc[:n_or]
        hi, lo = rng.high.max(), rng.low.min()
        width = (hi - lo) / b.open[0] * 100
        if width < min_or_pct or width > max_or_pct:
            continue
        for i in range(n_or, len(b) - 1):
            if b.t[i] > last_entry:
                break
            side = 1 if b.close[i] > hi else (-1 if b.close[i] < lo else 0)
            if side == 0 or (direction == "long" and side < 0) or (direction == "short" and side > 0):
                continue
            if filt is not None and not filt(day, side):
                break
            e = b.open[i + 1]
            if stop_mode == "range":
                stop = lo if side == 1 else hi
            else:
                stop = (hi + lo) / 2
            risk = side * (e - stop)
            if risk <= 0:
                break
            tgt = None if rr is None else e + side * rr * risk
            entry, ex, why = simulate(b, side, i + 1, stop, tgt)
            out.append(dict(day=day, side=side, entry=entry, exit=ex, risk=risk, reason=why))
            break
    return pd.DataFrame(out)


def noise_boundary(df, lookback=14, check_every=30, vm=1.0, use_vwap_trail=True):
    """Zarattini/Aziz/Barbon (2024) 'Beat the Market' intraday momentum, adapted to NSE.
    Noise area at time t = open * (1 +/- vm * avg_{last N days}|close_t/open - 1|).
    Checked every `check_every` minutes: long above upper band, short below lower.
    Trailing stop = the band (and intraday running mean price as VWAP proxy, since
    index data has no volume). Exit at EOD. Uses previous close-to-open gap adjust:
    upper uses max(open, prev_close), lower uses min(open, prev_close)."""
    df = df.copy()
    days = sorted(df.day.unique())
    piv = df.pivot_table(index="day", columns="t", values="close")
    opens = df.groupby("day").open.first()
    move = (piv.div(opens, axis=0) - 1).abs()
    sigma = move.rolling(lookback).mean().shift(1)  # use only past days
    prev_close = df.groupby("day").close.last().shift(1)
    out = []
    for day, b in df.groupby("day", sort=True):
        if day not in sigma.index or sigma.loc[day].isna().all() or pd.isna(prev_close.get(day)):
            continue
        b = b.reset_index(drop=True)
        o = b.open[0]
        up_ref, dn_ref = max(o, prev_close[day]), min(o, prev_close[day])
        sig = sigma.loc[day]
        pos, entry, risk0, trades_today = 0, None, None, []
        run_mean = b.close.expanding().mean().values
        for i in range(len(b) - 1):
            t = b.t[i]
            s = sig.get(t, np.nan)
            if np.isnan(s):
                continue
            ub, lb = up_ref * (1 + vm * s), dn_ref * (1 - vm * s)
            c = b.close[i]
            # trailing exit evaluated every bar close
            if pos == 1:
                trail = max(ub, run_mean[i]) if use_vwap_trail else ub
                if c < trail or t >= "15:15":
                    trades_today.append(dict(day=day, side=1, entry=entry, exit=b.open[i + 1] if t < "15:15" else c, risk=risk0, reason="trail" if t < "15:15" else "eod"))
                    pos = 0
            elif pos == -1:
                trail = min(lb, run_mean[i]) if use_vwap_trail else lb
                if c > trail or t >= "15:15":
                    trades_today.append(dict(day=day, side=-1, entry=entry, exit=b.open[i + 1] if t < "15:15" else c, risk=risk0, reason="trail" if t < "15:15" else "eod"))
                    pos = 0
            if t >= "15:15":
                break
            mins = int(t[:2]) * 60 + int(t[3:]) - (9 * 60 + 15) + 5  # minutes elapsed at bar close
            if pos == 0 and mins % check_every == 0:
                if c > ub:
                    pos, entry = 1, b.open[i + 1]
                    risk0 = max(entry - max(ub, run_mean[i]), entry * 0.001)
                elif c < lb:
                    pos, entry = -1, b.open[i + 1]
                    risk0 = max(min(lb, run_mean[i]) - entry, entry * 0.001)
        out += trades_today
    return pd.DataFrame(out)
