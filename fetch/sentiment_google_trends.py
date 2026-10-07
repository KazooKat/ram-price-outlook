"""Google Trends search interest (monthly, 2016-present) via the unofficial pytrends.

Each group of up to 5 terms is fetched in one request so the terms share one
0-100 scale (100 = the highest month of any term in that group and geo).
Values are not comparable across groups or geos except via the shared anchor
term "RAM prices", which appears in every group.

Output: data/raw/google_trends/trends_monthly.csv
(date, term, metric, value, geo, group, is_partial)
"""
from __future__ import annotations

import sys
from pathlib import Path
import datetime as dt
import time

import pandas as pd
from pytrends.request import TrendReq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetch._common import raw_dir, write_source_note  # noqa: E402

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
            try:
                df = fetch(terms, geo, timeframe)
            except RuntimeError as e:
                # Google rate-limits the unofficial endpoint; keep the last complete file rather than
                # write a partial one, and exit 0 so run.py --fetch carries on with other sources.
                prev = out / "trends_monthly.csv"
                kept = f"kept previous file ({dt.date.fromtimestamp(prev.stat().st_mtime)})" if prev.exists() else "no file written"
                print(f"WARNING: {e} ({e.__cause__!r}); {kept}")
                return
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
- For "RAM prices" use group=components: in group=memory, DDR5 sets the 100 so "RAM prices" is squeezed
  into a few integer steps (1-17 in 2025-26), losing resolution.
- Worldwide "RAM prices" jumped in 2025-08/09 (to ~30) while the US stayed at 6-8; a region breakdown to
  explain it was rate-limited (HTTP 429) and not obtained. A non-PC meaning of the literal query
  (e.g. livestock or the Ram truck brand) is possible but unconfirmed.
""",
    )


if __name__ == "__main__":
    main()
