"""Google Trends search interest (monthly, 2016-present) via the unofficial pytrends.

Each group of up to 5 terms is fetched in one request so the terms share one
0-100 scale (100 = the highest month of any term in that group and geo).
Values are not comparable across groups or geos except via the shared anchor
term "RAM prices", which appears in every group.

Output: data/raw/google_trends/trends_monthly.csv
(date, term, metric, value, geo, group, is_partial)
"""
from __future__ import annotations

import datetime as dt
import time

import pandas as pd
from pytrends.request import TrendReq

from fetch._common import raw_dir, write_source_note

SOURCE = "google_trends"
START = "2016-01-01"
GROUPS = {
    "memory": ["RAM prices", "RAM shortage", "DDR5", "DDR4", "memory prices"],
    "components": ["RAM prices", "GPU prices", "SSD prices", "CPU prices", "GPU shortage"],
}
GEOS = {"US": "US", "world": ""}


def fetch(terms: list[str], geo: str, timeframe: str) -> pd.DataFrame:
    last = None
    for attempt in range(4):
        try:
            # pytrends retries=0 avoids its urllib3<2-only Retry(method_whitelist=...) call.
            # A fresh client per request: reusing one returned the previous geo's data in testing.
            pt = TrendReq(hl="en-US", tz=0)
            pt.build_payload(terms, timeframe=timeframe, geo=geo)
            return pt.interest_over_time()
        except Exception as e:  # 429 / transient Google errors
            last = e
            time.sleep(20 * (attempt + 1))
    raise RuntimeError(f"Google Trends failed for {terms} {geo or 'world'}") from last


def main() -> None:
    out = raw_dir(SOURCE)
    timeframe = f"{START} {dt.date.today().isoformat()}"
    frames = []
    for group, terms in GROUPS.items():
        for geo_name, geo in GEOS.items():
            df = fetch(terms, geo, timeframe)
            partial = df["isPartial"].astype(bool)
            long = (df.drop(columns="isPartial").assign(is_partial=partial)
                      .reset_index().melt(id_vars=["date", "is_partial"], var_name="term", value_name="value"))
            long["date"] = pd.to_datetime(long["date"]).dt.strftime("%Y-%m-%d")
            long["metric"] = "search_interest_0_100"
            long["geo"] = geo_name
            long["group"] = group
            frames.append(long)
            print(f"  {group}/{geo_name}: {len(df)} months")
            time.sleep(8)
    tidy = pd.concat(frames, ignore_index=True)[
        ["date", "term", "metric", "value", "geo", "group", "is_partial"]
    ].sort_values(["group", "geo", "term", "date"])
    tidy.to_csv(out / "trends_monthly.csv", index=False)
    print(f"wrote {len(tidy)} rows")
    write_source_note(
        SOURCE,
        title="Google Trends search interest (monthly)",
        urls=["https://trends.google.com/trends/ (via pytrends 4.9.2, unofficial client)"],
        notes=f"""
Groups (each fetched as one comparison, so terms share a scale): {GROUPS}.
Geos: US and worldwide. Timeframe {START} to fetch date; Google returns monthly points for spans over 5 years.
- Values are relative (0-100) within one group+geo request, not absolute search counts.
- Google samples the underlying data, so a re-fetch can shift values by a few points; the whole file is re-downloaded each run.
- Search terms (not topics) are used, so matching is on the literal query text in any language region.
- is_partial marks the current, incomplete month.
""",
    )


if __name__ == "__main__":
    main()
