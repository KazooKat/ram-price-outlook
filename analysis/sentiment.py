"""Attention and tone around RAM prices, measured, and how they lined up with prices before.

Hacker News: comments containing "RAM prices" per 100k HN items (normalizes for site growth).
Google Trends: "RAM prices", US, components comparison group (0-100 within the request;
  in the memory group DDR5 sets the scale and squashes "RAM prices").
Reddit: RAM-price titles per 1k posts and keyword tone in r/buildapc, r/pcmasterrace, r/hardware (2025+).
GDELT: news articles matching "memory shortage" as a share of all monitored articles, and news tone.

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
    g = g[(g.geo == "US") & (g.group == "components")]
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


def gdelt() -> pd.DataFrame:
    f = S.RAW / "gdelt" / "gdelt_monthly.csv"
    if not f.exists():
        return pd.DataFrame()
    g = pd.read_csv(f)
    out = {}
    for term in ["memory shortage", "RAM prices", "memory prices"]:
        sh = g[(g.term == term) & (g.metric == "share_of_monitored")].set_index("date").value
        out[f"gdelt_{term.replace(' ', '_').lower()}_per_m"] = 1e6 * sh
        tone = g[(g.term == term) & (g.metric == "avg_tone")].set_index("date").value
        if len(tone):
            out[f"gdelt_{term.replace(' ', '_').lower()}_tone"] = tone
    df = pd.DataFrame(out)
    df.index = pd.to_datetime(df.index)
    return df


def main():
    df = pd.concat([hn(), trends(), reddit(), gdelt()], axis=1).sort_index()
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
    for col in ["reddit_ram_price_per_1k", "gdelt_memory_shortage_per_m"]:
        x = df[col].dropna()
        x = x[x.index < x.index.max()]  # current month is partial
        print(f"{col}: peak {x.max():.1f} in {x.idxmax():%Y-%m}; last full month {x.iloc[-1]:.1f} ({x.index[-1]:%Y-%m})")
    cols = ["reddit_ram_price_per_1k", "reddit_ram_net_tone", "gdelt_memory_shortage_per_m", "gdelt_ram_prices_tone"]
    print(df.loc["2025-06-01":, [c for c in cols if c in df]].round(2).to_string())


if __name__ == "__main__":
    main()
