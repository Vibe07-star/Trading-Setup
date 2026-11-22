#!/usr/bin/env python3
"""Daily pre-open screener for the large/midcap GAP-UP FADE (see backtest/RESULTS.md, round 2).

Rule (identical to the backtest):
  universe : top 250 NSE EQ stocks by mean traded value over the last 60 sessions, prev close >= Rs 50
  gap      : pre-open IEP / previous close - 1
  rel gap  : gap - median gap of the universe
  picks    : 10 highest rel gap with 1% <= raw gap < 15%
  trade    : SHORT (MIS) equal amounts inside the pre-open auction (order entry closes 09:07-09:08 IST),
             cover everything 15:15-15:20.

Usage
  python3 preopen_screener.py                      # one snapshot now (run ~09:06-09:07 IST)
  python3 preopen_screener.py --watch              # refresh every 20s from 09:00 until 09:08, then stop
  python3 preopen_screener.py --capital 500000     # also show quantities for Rs 5 lakh split over the picks
  python3 preopen_screener.py --review 2026-11-20  # after ~18:00: P&L of that day's logged picks from NSE bhavcopy
  python3 preopen_screener.py --file po.json       # run on a saved pre-open JSON (testing)

Every snapshot's picks are written to screener/logs/YYYY-MM-DD.csv (the last one of the day wins), so you
can paper-trade and later compare with --review.  Research tool only, not investment advice.
"""
import argparse, datetime as dt, io, json, os, sys, time
from zoneinfo import ZoneInfo

import pandas as pd
import requests

IST = ZoneInfo("Asia/Kolkata")
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
LOGS = os.path.join(HERE, "logs")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
PREOPEN_URL = "https://www.nseindia.com/api/market-data-pre-open?key=ALL"
BHAV_URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{:%d%m%Y}.csv"

TOP_N, MIN_PX, LOOKBACK = 250, 50.0, 60
K, GAP_MIN, GAP_MAX = 10, 0.01, 0.15

S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})


# ---------------------------------------------------------------- data
def bhav(day):
    """One day's sec_bhavdata_full (EQ rows) or None if no file (holiday / not yet published)."""
    os.makedirs(CACHE, exist_ok=True)
    f = os.path.join(CACHE, f"{day:%Y%m%d}.csv")
    if not os.path.exists(f):
        for attempt in range(3):
            try:
                r = S.get(BHAV_URL.format(day), timeout=20)
                break
            except requests.RequestException:
                time.sleep(2 * (attempt + 1))
        else:
            return None
        if r.status_code != 200 or not r.text.startswith("SYMBOL"):
            return None
        open(f, "w").write(r.text)
    x = pd.read_csv(f, skipinitialspace=True)
    x.columns = [c.strip() for c in x.columns]
    # On holidays NSE serves a file that repeats the previous session; trust DATE1 inside the file.
    if pd.to_datetime(str(x.DATE1.iloc[0]).strip(), format="%d-%b-%Y").date() != day:
        return None
    x = x[x.SERIES.str.strip() == "EQ"].copy()
    x["SYMBOL"] = x.SYMBOL.str.strip()
    for c in ("PREV_CLOSE", "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "LAST_PRICE", "CLOSE_PRICE", "TURNOVER_LACS"):
        x[c] = pd.to_numeric(x[c], errors="coerce")
    x["day"] = day
    return x


def universe(asof):
    """Top-N symbols by mean turnover over the LOOKBACK sessions strictly before `asof`."""
    frames, day = [], asof - dt.timedelta(days=1)
    tries = 0
    while len(frames) < LOOKBACK and tries < LOOKBACK * 2:
        if day.weekday() < 5:
            x = bhav(day)
            if x is not None:
                frames.append(x[["SYMBOL", "TURNOVER_LACS", "CLOSE_PRICE"]].assign(day=day))
        day -= dt.timedelta(days=1); tries += 1
    if len(frames) < 40:
        sys.exit(f"Only {len(frames)} bhavcopy days available - cannot build universe.")
    p = pd.concat(frames)
    tv = p.groupby("SYMBOL").TURNOVER_LACS.agg(["mean", "count"])
    tv = tv[tv["count"] >= 40]["mean"].sort_values(ascending=False)
    return set(tv.index[:TOP_N]), len(frames), max(f.day.iloc[0] for f in frames)


def fetch_preopen(path=None):
    if path:
        return json.load(open(path))
    for attempt in range(4):
        try:
            if attempt:
                S.get("https://www.nseindia.com/market-data/pre-open-market-cm-and-emerge-market", timeout=15)
            r = S.get(PREOPEN_URL, timeout=20, headers={"Accept": "application/json",
                      "Referer": "https://www.nseindia.com/market-data/pre-open-market-cm-and-emerge-market"})
            if r.status_code == 200 and r.text.startswith("{"):
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(2 * (attempt + 1))
    sys.exit("Could not fetch NSE pre-open data.")


# ---------------------------------------------------------------- screen
def screen(po, univ):
    rows = []
    for item in po["data"]:
        m = item["metadata"]
        if m.get("series") != "EQ":
            continue
        rows.append(dict(symbol=m["symbol"], prev_close=m.get("previousClose"), iep=m.get("iep") or m.get("lastPrice"),
                         qty=m.get("finalQuantity") or 0))
    df = pd.DataFrame(rows)
    df = df[df.symbol.isin(univ)].copy()
    df["prev_close"] = pd.to_numeric(df.prev_close, errors="coerce")
    df["iep"] = pd.to_numeric(df.iep, errors="coerce")
    df = df[(df.prev_close >= MIN_PX) & (df.iep > 0)]
    df["gap"] = df.iep / df.prev_close - 1
    live = df[df.qty > 0]                       # stocks with a discovered auction price
    med = live.gap.median()
    df["rel_gap"] = df.gap - med
    cand = df[(df.qty > 0) & (df.gap >= GAP_MIN) & (df.gap < GAP_MAX)]
    picks = cand.sort_values("rel_gap", ascending=False).head(K).reset_index(drop=True)
    return picks, med, len(df), len(live)


def show(picks, med, n_univ, n_live, stamp, capital):
    print(f"\nNSE pre-open snapshot {stamp}  |  universe matched {n_univ} (with IEP {n_live})  |  median gap {med*100:+.2f}%")
    if picks.empty:
        print("No stock meets the rule (raw gap >= 1%). -> NO TRADE today.")
        return picks
    p = picks.copy()
    if capital:
        alloc = capital / K                      # fixed 1/K of capital per name, as in the backtest
        p["short_qty"] = (alloc // p.iep).astype(int)
        p["notional"] = (p.short_qty * p.iep).round(0)
    out = p.assign(gap_pct=(p.gap * 100).round(2), rel_gap_pct=(p.rel_gap * 100).round(2))
    cols = ["symbol", "prev_close", "iep", "gap_pct", "rel_gap_pct", "qty"] + (["short_qty", "notional"] if capital else [])
    out.index = out.index + 1
    print(out[cols].rename(columns={"qty": "auction_qty"}).to_string())
    if len(p) < K:
        print(f"Only {len(p)} names qualify. Sizing here stays at 1/{K} of capital per name (more conservative); "
              "the backtest returns assume the capital is split across however many names qualify.")
    print("Action: SELL (MIS, market/limit) each name before pre-open order entry closes (~09:07); "
          "cover all at 15:15-15:20.")
    return p


def log(picks, day, stamp):
    os.makedirs(LOGS, exist_ok=True)
    picks.assign(snapshot=stamp).to_csv(os.path.join(LOGS, f"{day:%Y-%m-%d}.csv"), index=False)


# ---------------------------------------------------------------- review
def review(day, cost):
    f = os.path.join(LOGS, f"{day:%Y-%m-%d}.csv")
    if not os.path.exists(f):
        sys.exit(f"No log for {day}: {f}")
    picks = pd.read_csv(f)
    b = bhav(day)
    if b is None:
        sys.exit(f"Bhavcopy for {day} not published yet (usually after ~18:00 IST).")
    j = picks.merge(b[["SYMBOL", "OPEN_PRICE", "LAST_PRICE", "CLOSE_PRICE", "HIGH_PRICE"]], left_on="symbol", right_on="SYMBOL")
    j["open_vs_iep_pct"] = (j.OPEN_PRICE / j.iep - 1) * 100
    j["short_ret_pct"] = -(j.CLOSE_PRICE / j.OPEN_PRICE - 1) * 100
    j["worst_pct"] = -(j.HIGH_PRICE / j.OPEN_PRICE - 1) * 100
    j.index = j.index + 1
    print(j[["symbol", "iep", "OPEN_PRICE", "open_vs_iep_pct", "HIGH_PRICE", "CLOSE_PRICE", "short_ret_pct", "worst_pct"]].round(2).to_string())
    gross = j.short_ret_pct.mean()
    print(f"\n{day}: {len(j)} picks | avg short return open->close {gross:+.2f}% gross, {gross - cost*100:+.2f}% after "
          f"{cost*100:.2f}% costs | winners {int((j.short_ret_pct > 0).sum())}/{len(j)}")
    if "notional" in j:
        pnl = (j.notional * (j.short_ret_pct / 100 - cost)).sum()
        print(f"Rupee P&L on logged quantities after costs: Rs {pnl:,.0f}")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--watch", action="store_true", help="refresh every 20s until 09:08 IST")
    ap.add_argument("--capital", type=float, default=0, help="capital to split equally across the picks")
    ap.add_argument("--file", help="saved pre-open JSON instead of fetching live")
    ap.add_argument("--asof", help="trade date YYYY-MM-DD for universe (default: today IST / snapshot date)")
    ap.add_argument("--review", help="YYYY-MM-DD: P&L of logged picks using that day's bhavcopy")
    ap.add_argument("--cost", type=float, default=0.0012, help="round-trip cost fraction for --review (default 0.12%%)")
    a = ap.parse_args()

    if a.review:
        return review(dt.date.fromisoformat(a.review), a.cost)

    po = fetch_preopen(a.file)
    stamp = po.get("timestamp", "")
    snap_day = dt.datetime.strptime(stamp.split()[0], "%d-%b-%Y").date() if stamp else dt.datetime.now(IST).date()
    asof = dt.date.fromisoformat(a.asof) if a.asof else snap_day
    univ, ndays, last = universe(asof)
    print(f"Universe: top {TOP_N} by {ndays}-session mean turnover up to {last} ({len(univ)} names)")
    now = dt.datetime.now(IST)
    if not a.file and snap_day != now.date():
        print(f"NOTE: NSE is serving the pre-open snapshot of {snap_day} (no pre-open session yet today). "
              "Run between 09:00 and 09:08 IST on a trading day for live picks.")
    while True:
        picks, med, n_univ, n_live = screen(po, univ)
        p = show(picks, med, n_univ, n_live, stamp, a.capital)
        log(p, snap_day, stamp)
        now = dt.datetime.now(IST)
        if not a.watch or a.file or now.time() >= dt.time(9, 8) or snap_day != now.date():
            break
        time.sleep(20)
        po = fetch_preopen()
        stamp = po.get("timestamp", "")


if __name__ == "__main__":
    main()
