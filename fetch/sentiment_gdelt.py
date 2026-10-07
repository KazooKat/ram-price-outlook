"""GDELT DOC 2.0 news volume and average tone for component-price queries (2017-present).

For each query:
- mode=timelinevolraw: number of matching articles per day, plus GDELT's total
  monitored articles per day (for normalization);
- mode=timelinetone: average tone of matching articles per day
  (GDELT tone: roughly -10..+10, negative = more negative wording).

Output (tidy: date, term, metric, value):
- data/raw/gdelt/gdelt_daily.csv   as returned by the API
- data/raw/gdelt/gdelt_monthly.csv articles summed per month, share = articles / total
  monitored, tone averaged per month weighted by that day's article count.
GDELT asks for at most one request per 5 seconds.
"""
from __future__ import annotations

import datetime as dt
import io
import time

import pandas as pd
import requests

from fetch._common import _session, raw_dir, write_source_note

SOURCE = "gdelt"
API = "https://api.gdeltproject.org/api/v2/doc/doc"
START = "20170101000000"  # DOC 2.0 timelines begin 2017-01-01
PAUSE = 6  # seconds between requests (GDELT limit: 1 per 5 s)

QUERIES = {
    "DRAM prices": '"DRAM prices"',
    "memory chip prices": '"memory chip prices"',
    "memory prices": '"memory prices"',
    "RAM prices": '"RAM prices"',
    "memory shortage": '("memory shortage" OR "memory chip shortage" OR "DRAM shortage")',
    "HBM": '"high bandwidth memory"',
    "NAND prices": '"NAND prices"',
    "SSD prices": '"SSD prices"',
    "GPU prices": '("GPU prices" OR "graphics card prices")',
}
MODES = {"timelinevolraw": "volraw", "timelinetone": "tone"}


def fetch(query: str, mode: str, end: str) -> pd.DataFrame:
    params = {"query": query, "mode": mode, "format": "csv",
              "startdatetime": START, "enddatetime": end}
    for wait in (0, 15, 45, 120, 300):
        time.sleep(wait or PAUSE)
        try:
            r = _session.get(API, params=params, timeout=180)
        except requests.RequestException as e:
            print(f"    {e!r}; retrying")
            continue
        text = r.text.lstrip("﻿")
        if r.status_code == 200 and text.startswith("Date"):
            return pd.read_csv(io.StringIO(text))
        print(f"    HTTP {r.status_code}: {text[:80]!r}; retrying")
    raise RuntimeError(f"GDELT kept refusing {mode} {query}")


def main() -> None:
    out = raw_dir(SOURCE)
    end = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    frames, failed = [], []
    for term, q in QUERIES.items():
        for mode, short in MODES.items():
            try:
                df = fetch(q, mode, end)
            except RuntimeError as e:
                print(f"  {term}/{short}: FAILED ({e})")
                failed.append(f"{term}/{short}")
                if not frames:  # refused from the start: the IP is blocked; don't spend hours retrying
                    raise SystemExit("GDELT: first request refused after all retries; nothing written")
                continue
            # Columns: Date, Series, Value. volraw Series = "Article Count"; the
            # total-monitored count comes back as a separate column "Total Monitored Articles".
            df = df.rename(columns=str.strip)
            long = df.melt(id_vars=["Date", "Series"], var_name="col", value_name="value")
            long["metric"] = (short + ":" + long["Series"].str.strip() + ":" + long["col"]).str.replace(
                ":Value", "", regex=False)
            long = long.rename(columns={"Date": "date"}).assign(term=term)
            long["date"] = pd.to_datetime(long["date"]).dt.strftime("%Y-%m-%d")
            frames.append(long[["date", "term", "metric", "value"]])
            print(f"  {term}/{short}: {len(df)} rows; metrics {sorted(long['metric'].unique())}")
    if not frames:
        raise SystemExit("GDELT: no data fetched (all requests refused); nothing written")
    daily = pd.concat(frames, ignore_index=True)
    daily.to_csv(out / "gdelt_daily.csv", index=False)
    monthly = to_monthly(daily)
    monthly.to_csv(out / "gdelt_monthly.csv", index=False)
    print(f"wrote {len(daily)} daily rows, {len(monthly)} monthly rows; failed: {failed or 'none'}")
    write_source_note(
        SOURCE,
        title="GDELT DOC 2.0 news volume and tone",
        urls=[API, "https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/"],
        notes=f"""
Queries (GDELT query syntax): {QUERIES}
Window {START[:8]} to fetch time. Modes: timelinevolraw (article counts + total monitored), timelinetone.
gdelt_daily.csv keeps the API output; gdelt_monthly.csv: articles = monthly sum, share = articles /
total monitored articles, tone = article-weighted mean of daily average tone.
- GDELT searches its global news crawl (machine-translated non-English included); coverage of
  sources changes over time, so use the share (normalized) series for trends.
- Re-running re-downloads everything (2 requests per query, >=6 s apart).
- Failed on last run: {failed or 'none'}.
""",
    )


def to_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    d = daily.copy()
    d["month"] = pd.to_datetime(d["date"]).dt.to_period("M").dt.to_timestamp().dt.strftime("%Y-%m-%d")
    w = d.pivot_table(index=["term", "date", "month"], columns="metric", values="value", aggfunc="first").reset_index()
    cnt = next((c for c in w.columns if c.startswith("volraw") and "Article Count" in c and "Total" not in c), None)
    tot = next((c for c in w.columns if c.startswith("volraw") and "Total" in c), None)
    tone = next((c for c in w.columns if c.startswith("tone")), None)
    rows = []
    for (term, month), g in w.groupby(["term", "month"]):
        if cnt:
            n = g[cnt].sum()
            rows.append((month, term, "articles", n))
            if tot and g[tot].sum() > 0:
                rows.append((month, term, "share_of_monitored", n / g[tot].sum()))
        if tone and g[tone].notna().any():
            if cnt and g[cnt].sum() > 0:
                m = g[[tone, cnt]].dropna()
                val = (m[tone] * m[cnt]).sum() / m[cnt].sum() if m[cnt].sum() > 0 else float("nan")
            else:
                val = g[tone].mean()
            rows.append((month, term, "avg_tone", val))
    return pd.DataFrame(rows, columns=["date", "term", "metric", "value"])


if __name__ == "__main__":
    main()
