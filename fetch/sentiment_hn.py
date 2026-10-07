"""Monthly Hacker News story/comment counts mentioning component-price phrases.

Uses the HN Algolia search API (keyless). For each phrase and month we ask for
hitsPerPage=0 and read nbHits, so only counts are stored.

Denominator: Algolia's nbHits for an empty query is an approximation
(exhaustiveNbHits=false) and was badly wrong in testing (e.g. 3.4M "stories" in
2026-09). HN item ids are sequential across all item types, so the total number
of items created in a month is instead measured as the id of the last item
before the month ends minus the same for the previous month.

Output: data/raw/hn_algolia/hn_monthly.csv (date, term, metric, value, exact)
metric: stories / comments (phrase matches), total_items (term=ALL, id span).
exact: Algolia's exhaustiveNbHits for that count (blank for total_items).
"""
from __future__ import annotations

import datetime as dt
import time

import pandas as pd

from fetch._common import get, raw_dir, write_source_note

SOURCE = "hn_algolia"
API = "https://hn.algolia.com/api/v1/search_by_date"
START = dt.date(2015, 1, 1)

# Phrases in quotes are exact-phrase matches (Algolia advancedSyntax).
TERMS = [
    '"RAM prices"',
    '"DRAM prices"',
    '"memory prices"',
    '"memory shortage"',
    '"RAM shortage"',
    '"DRAM"',
    '"HBM"',
    '"DDR5"',
    '"SSD prices"',
    '"NAND"',
    '"GPU prices"',
    '"GPU shortage"',
]
TAGS = {"stories": "story", "comments": "comment"}
COLS = ["date", "term", "metric", "value", "exact"]


def months(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        nxt = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        yield d, nxt
        d = nxt


def ts(d: dt.date) -> int:
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp())


def count(query: str, tag: str, a: dt.date, b: dt.date) -> tuple[int, bool]:
    j = get(API, params={
        "query": query,
        "advancedSyntax": "true",
        "tags": tag,
        "hitsPerPage": 0,
        "typoTolerance": "false",
        "numericFilters": f"created_at_i>={ts(a)},created_at_i<{ts(b)}",
    }).json()
    return int(j["nbHits"]), bool(j.get("exhaustiveNbHits"))


def last_id_before(b: dt.date) -> int:
    """Id of the newest story or comment created before date b."""
    j = get(API, params={
        "tags": "(story,comment)",
        "hitsPerPage": 1,
        "numericFilters": f"created_at_i<{min(ts(b), int(time.time()))}",
    }).json()
    return int(j["hits"][0]["objectID"])


def main() -> None:
    out = raw_dir(SOURCE)
    path = out / "hn_monthly.csv"
    today = dt.date.today()
    cur_month = today.replace(day=1)
    # Re-fetch the last two months (still filling in); keep older cached rows.
    refresh_from = (cur_month - dt.timedelta(days=1)).replace(day=1)
    cache = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=COLS)
    if list(cache.columns) != COLS:  # older layout without the exact column
        cache = pd.DataFrame(columns=COLS)
    cache = cache[pd.to_datetime(cache["date"]).dt.date < refresh_from]
    have = set(zip(cache["date"], cache["term"], cache["metric"]))

    rows = []

    def save() -> pd.DataFrame:
        tidy = pd.concat([cache, pd.DataFrame(rows, columns=COLS)], ignore_index=True)
        tidy = tidy.sort_values(["term", "metric", "date"])
        tidy.to_csv(path, index=False)
        return tidy

    prev_last = None
    for a, b in months(START, cur_month):
        ds = a.isoformat()
        if (ds, "ALL", "total_items") not in have:
            if prev_last is None:
                prev_last = last_id_before(a)
            last = last_id_before(b)
            rows.append({"date": ds, "term": "ALL", "metric": "total_items", "value": last - prev_last, "exact": None})
            prev_last = last
        else:
            prev_last = None  # recompute from the API when the next uncached month needs it
        for q in TERMS:
            term = q.strip('"')
            for metric, tag in TAGS.items():
                if (ds, term, metric) in have:
                    continue
                n, exact = count(q, tag, a, b)
                rows.append({"date": ds, "term": term, "metric": metric, "value": n, "exact": exact})
                time.sleep(0.1)
        if a.month == 12:  # checkpoint once a year so an interrupted run resumes
            save()
            print(f"  through {ds}", flush=True)
    tidy = save()
    n_inexact = int((tidy["exact"].astype(str) == "False").sum())
    print(f"wrote {len(tidy)} rows ({len(rows)} new); approximate (non-exhaustive) counts: {n_inexact}")
    write_source_note(
        SOURCE,
        title="Hacker News mentions of component-price phrases (monthly counts)",
        urls=[API, "https://hn.algolia.com/api"],
        notes=f"""
Terms (exact phrase, case-insensitive, typo tolerance off): {', '.join(TERMS)}.
metric: stories / comments = items matching the phrase that month (Algolia nbHits);
exact = Algolia's exhaustiveNbHits flag for that count.
metric total_items (term=ALL) = HN item-id span for the month (all stories, comments, polls, jobs),
used as the normalizing denominator. Empty-query nbHits was not used: it is approximate and was
wildly wrong in testing (e.g. 3.4M stories reported for 2026-09 vs ~25k normal).
- Story matches are on title, URL and story text as indexed by Algolia; comments on comment text.
- "DRAM", "HBM", "NAND", "DDR5" also match non-price discussion; treat as broad attention, not price talk.
- The current month is partial. The last two months are re-fetched on each run; older months are cached.
""",
    )


if __name__ == "__main__":
    main()
