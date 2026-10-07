"""GDELT DOC 2.0 news volume and average tone for component-price queries (2017-present).

For each query:
- mode=timelinevolraw: number of matching articles per day ("Article Count"), plus
  GDELT's total monitored articles per day ("Total Monitored Articles");
- mode=timelinetone: average tone of matching articles per day ("Average Tone";
  roughly -10..+10, negative = more negative wording).

Each successful API response is cached as data/raw/gdelt/cache/<term>__<mode>.csv.
A re-run reuses responses younger than MAX_AGE_DAYS and requests the rest; when
GDELT refuses one (it rate-limits hard, HTTP 429), an older cached response is used
if there is one, and the note says so. Run it again to fill gaps.

Output (tidy: date, term, metric, value):
- data/raw/gdelt/gdelt_daily.csv   as returned by the API (metric = mode:series)
- data/raw/gdelt/gdelt_monthly.csv articles summed per month, share = articles / total
  monitored, tone averaged per month weighted by that day's article count.
GDELT asks for at most one request per 5 seconds.
"""
from __future__ import annotations

import sys
from pathlib import Path
import datetime as dt
import argparse
import io
import re
import time

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetch._common import _session, raw_dir, write_source_note  # noqa: E402

SOURCE = "gdelt"
API = "https://api.gdeltproject.org/api/v2/doc/doc"
START = "20170101000000"  # DOC 2.0 timelines begin 2017-01-01
PAUSE = 10  # seconds between requests (GDELT's stated limit is 1 per 5 s; it refused faster pacing)
MAX_AGE_DAYS = 7  # cached responses younger than this are reused without a request

QUERIES = {  # most important first: GDELT often refuses the later ones in a run
    "RAM prices": '"RAM prices"',
    "memory shortage": '("memory shortage" OR "memory chip shortage" OR "DRAM shortage")',
    "DRAM prices": '"DRAM prices"',
    "memory prices": '"memory prices"',
    "memory chip prices": '"memory chip prices"',
    "HBM": '"high bandwidth memory"',
    "NAND prices": '"NAND prices"',
    "SSD prices": '"SSD prices"',
    "GPU prices": '("GPU prices" OR "graphics card prices")',
}
MODES = {"timelinevolraw": "volraw", "timelinetone": "tone"}


def fetch(query: str, mode: str, end: str) -> str:
    """Raw CSV text for one query/mode; RuntimeError if GDELT keeps refusing."""
    params = {"query": query, "mode": mode, "format": "csv",
              "startdatetime": START, "enddatetime": end}
    for wait in (0, 30, 90):
        time.sleep(wait or PAUSE)
        try:
            # (connect, read) timeouts: GDELT can be slow even to refuse (a 429 took ~11 s in testing).
            r = _session.get(API, params=params, timeout=(10, 60))
        except requests.RequestException as e:
            print(f"    {type(e).__name__}; retrying", flush=True)
            continue
        text = r.text.lstrip("﻿")
        if r.status_code == 200 and text.startswith("Date"):
            return text
        print(f"    HTTP {r.status_code}: {text[:60]!r}; retrying", flush=True)
    raise RuntimeError(f"GDELT kept refusing {mode} {query}")


def tidy(text: str, term: str, short: str) -> pd.DataFrame:
    # Layout seen 2026-10-07: columns Date, Series, Value; volraw has two series per day
    # ("Article Count", "Total Monitored Articles"), tone has one ("Average Tone").
    df = pd.read_csv(io.StringIO(text)).rename(columns=str.strip)
    return pd.DataFrame({
        "date": pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d"),
        "term": term,
        "metric": short + ":" + df["Series"].str.strip(),
        "value": df["Value"],
    })


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="no requests; rebuild outputs from cache/ only")
    args = ap.parse_args()
    out = raw_dir(SOURCE)
    cache = out / "cache"
    cache.mkdir(exist_ok=True)
    end = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    frames, fresh, stale, missing = [], [], [], []
    refused_in_a_row = 4 if args.offline else 0
    for term, q in QUERIES.items():
        for mode, short in MODES.items():
            f = cache / f"{re.sub(r'[^a-z0-9]+', '_', term.lower())}__{short}.csv"
            label = f"{term}/{short}"
            if f.exists() and time.time() - f.stat().st_mtime < MAX_AGE_DAYS * 86400:
                frames.append(tidy(f.read_text(encoding="utf-8"), term, short))
                stale.append(f"{label} (cached {dt.date.fromtimestamp(f.stat().st_mtime)})")
                print(f"  {label}: {len(frames[-1])} rows (cache < {MAX_AGE_DAYS} days old)", flush=True)
                continue
            try:
                if refused_in_a_row >= 4:  # blocked for now; don't spend an hour on refusals
                    raise RuntimeError("skipped: offline, or 4 refusals in a row")
                text = fetch(q, mode, end)
                f.write_text(text, encoding="utf-8")
                fresh.append(label)
                refused_in_a_row = 0
            except RuntimeError:
                refused_in_a_row += 1
                if not f.exists():
                    print(f"  {label}: FAILED, no cached copy", flush=True)
                    missing.append(label)
                    continue
                text = f.read_text(encoding="utf-8")
                stale.append(f"{label} (cached {dt.date.fromtimestamp(f.stat().st_mtime)})")
            frames.append(tidy(text, term, short))
            print(f"  {label}: {len(frames[-1])} rows ({'fresh' if fresh and fresh[-1] == label else 'cached'})", flush=True)
    if not frames:
        # Exit 0 so run.py --fetch carries on with the other sources; nothing is written.
        print("WARNING: GDELT refused every request and nothing is cached; no GDELT data written")
        return
    daily = pd.concat(frames, ignore_index=True)
    daily.to_csv(out / "gdelt_daily.csv", index=False)
    monthly = to_monthly(daily)
    monthly.to_csv(out / "gdelt_monthly.csv", index=False)
    print(f"wrote {len(daily)} daily rows, {len(monthly)} monthly rows; fresh {len(fresh)}, "
          f"cached {len(stale)}, missing {missing or 'none'}")
    write_source_note(
        SOURCE,
        title="GDELT DOC 2.0 news volume and tone",
        urls=[API, "https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/"],
        notes=f"""
Queries (GDELT query syntax): {QUERIES}
Window {START[:8]} to fetch time, daily resolution. Modes: timelinevolraw (article counts + total
monitored), timelinetone. gdelt_daily.csv keeps the API output; gdelt_monthly.csv: articles = monthly
sum, share_of_monitored = articles / total monitored articles, avg_tone = article-weighted mean of
daily average tone (months with no matching articles have no tone; a tone series whose volume
  series is missing is kept in gdelt_daily.csv only, since zero-article days report tone 0).
- GDELT searches its global news crawl (machine-translated non-English included); its source list
  changes over time, so use share_of_monitored for trends, not raw article counts.
- GDELT rate-limits hard (HTTP 429 even at 10 s spacing in testing). cache/ holds each query's last
  successful response; refused queries fall back to it.
- Last run: fresh {len(fresh)}; from cache: {stale or 'none'}; missing (never fetched): {missing or 'none'}.
""",
    )


def to_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    d = daily.copy()
    d["month"] = pd.to_datetime(d["date"]).dt.to_period("M").dt.to_timestamp().dt.strftime("%Y-%m-%d")
    w = d.pivot_table(index=["term", "date", "month"], columns="metric", values="value", aggfunc="first")
    w = w.reset_index()
    cnt, tot, tone = "volraw:Article Count", "volraw:Total Monitored Articles", "tone:Average Tone"
    rows = []
    for (term, month), g in w.groupby(["term", "month"]):
        # The pivot has every metric column for every term; only use the ones this term really has.
        has = {c for c in (cnt, tot, tone) if c in g and g[c].notna().any()}
        if cnt not in has:
            continue
        n = g[cnt].sum()
        rows.append((month, term, "articles", n))
        if tot in has and g[tot].sum() > 0:
            rows.append((month, term, "share_of_monitored", n / g[tot].sum()))
        # GDELT reports tone 0.0 on days with no matching articles, so a plain mean would be pulled
        # toward neutral; tone is only aggregated when the volume series is there to weight it.
        m = g[[tone, cnt]].dropna() if tone in has else g.iloc[0:0]
        m = m[m[cnt] > 0]
        if len(m):
            rows.append((month, term, "avg_tone", (m[tone] * m[cnt]).sum() / m[cnt].sum()))
    return pd.DataFrame(rows, columns=["date", "term", "metric", "value"])


if __name__ == "__main__":
    main()
