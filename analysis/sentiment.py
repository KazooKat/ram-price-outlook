"""Attention and tone around RAM prices, measured, and how they lined up with prices before.

Hacker News: comments containing "RAM prices" per 100k HN items (normalizes for site growth).
Google Trends: "RAM prices", US, memory comparison group (0-100 within the request).
Reddit: RAM-price titles per 1k posts and keyword tone in r/buildapc, r/pcmasterrace, r/hardware (2024+).

Outputs: data/processed/sentiment_monthly.csv, charts/sentiment-*.png
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import series as S


def hn() -> pd.DataFrame:
    h = pd.read_csv(S.RAW / "hn_algolia" / "hn_monthly.csv")
    tot = h[(h.term == "ALL") & (h.metric == "total_items")].set_index("date").value
    out = {}
    for term in ["RAM prices", "RAM shortage", "DRAM prices", "memory shortage"]:
        c = h[(h.term == term) & (h.metric == "comments")].set_index("date").value
        out[f"hn_{term.replace(' ', '_').lower()}_per_100k"] = 1e5 * c / tot
    df = pd.DataFrame(out)
    df.index = pd.to_datetime(df.index)
    return df


def trends() -> pd.DataFrame:
    g = pd.read_csv(S.RAW / "google_trends" / "trends_monthly.csv")
    g = g[(g.geo == "US") & (g.group == "memory")]
    df = g.pivot_table(index="date", columns="term", values="value")
    df.columns = [f"gt_{c.replace(' ', '_').lower()}" for c in df.columns]
    df.index = pd.to_datetime(df.index)
    return df


def reddit() -> pd.DataFrame:
    f = S.RAW / "reddit_arctic" / "reddit_monthly.csv"
    if not f.exists():
        return pd.DataFrame()
    r = pd.read_csv(f)
    r = r[r.term == "ALL"]
    df = r.pivot_table(index="date", columns="metric", values="value")
    df.columns = [f"reddit_{c}" for c in df.columns]
    df.index = pd.to_datetime(df.index)
    return df


def main():
    df = pd.concat([hn(), trends(), reddit()], axis=1).sort_index()
    df.to_csv(S.PROC / "sentiment_monthly.csv", index_label="month")

    q = df.resample("QS").mean()
    k = "hn_ram_prices_per_100k"
    pre = q.loc["2016-01-01":"2019-12-31", k]
    cur = q.loc["2025-01-01":, k]
    print(f"HN 'RAM prices' per 100k items: 2016-19 peak {pre.max():.2f} in {pre.idxmax():%Y-%m}; "
          f"current-cycle peak {cur.max():.2f} in {cur.idxmax():%Y-%m}; latest {q[k].dropna().iloc[-1]:.2f}")
    g = df["gt_ram_prices"].dropna()
    print(f"Google 'RAM prices' US: peak {g.max():.0f} in {g.idxmax():%Y-%m}; latest {g.iloc[-1]:.0f} ({g.index[-1]:%Y-%m})")
    spot = S.ddr4_8gb_spot()
    print(f"DDR4 8Gb spot peak in 2016-19: {spot['2016':'2019'].idxmax():%Y-%m}")
    rc = [c for c in df.columns if c.startswith("reddit_")]
    if rc:
        print(df[rc].dropna(how="all").round(2).to_string())


if __name__ == "__main__":
    main()
