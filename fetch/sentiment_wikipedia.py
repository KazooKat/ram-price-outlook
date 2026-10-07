"""Monthly English Wikipedia pageviews for component-related articles.

Attention proxy: how many people (user agent only, bots excluded) read each
article per month. Output: data/raw/wikipedia_pageviews/pageviews_monthly.csv
in tidy form (date, term, metric, value).
"""
from __future__ import annotations

import sys
from pathlib import Path
import datetime as dt
import time
from urllib.parse import quote

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetch._common import get, raw_dir, write_source_note  # noqa: E402

SOURCE = "wikipedia_pageviews"
API = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
       "en.wikipedia/all-access/user/{article}/monthly/{start}/{end}")
START = "2015070100"  # first month the pageviews API covers

ARTICLES = [
    "Dynamic_random-access_memory",
    "Random-access_memory",
    "DDR4_SDRAM",
    "DDR5_SDRAM",
    "High_Bandwidth_Memory",
    "Flash_memory",
    "Solid-state_drive",
    "Graphics_processing_unit",
    "Central_processing_unit",
    "Chip_shortage",
    "2020–2023_global_chip_shortage",
    "2025–present_global_memory_supply_shortage",
]
# This article was created 2025-12-16 and renamed several times; views under its
# former titles are counted under those titles, so also fetch every redirect to it.
WITH_REDIRECTS = ["2025–present_global_memory_supply_shortage"]


def redirects_to(article: str) -> list[str]:
    r = get("https://en.wikipedia.org/w/api.php", params={
        "action": "query", "prop": "redirects", "rdlimit": "max", "titles": article.replace("_", " "),
        "format": "json",
    })
    pages = r.json()["query"]["pages"].values()
    return sorted({x["title"].replace(" ", "_") for p in pages for x in p.get("redirects", [])})


def fetch_article(article: str, end: str, **retry) -> pd.DataFrame | None:
    """Monthly views; an empty frame when the API has no data (404), None on a transient failure."""
    url = API.format(article=quote(article, safe=""), start=START, end=end)
    try:
        items = get(url, **retry).json()["items"]
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return pd.DataFrame()
        print(f"  {article}: failed ({e})")
        return None
    except RuntimeError as e:  # _common.get gave up on repeated 429/5xx
        print(f"  {article}: failed ({e})")
        return None
    df = pd.DataFrame(items)
    return pd.DataFrame({
        "date": pd.to_datetime(df["timestamp"].str[:8]).dt.strftime("%Y-%m-%d"),
        "term": article,
        "metric": "pageviews_user",
        "value": df["views"].astype(int),
    })


def main() -> None:
    out = raw_dir(SOURCE)
    end = dt.date.today().strftime("%Y%m%d") + "00"
    frames, missing = [], []

    def fetch_all(titles: list[str]) -> dict[str, pd.DataFrame]:
        got, retry = {}, []
        for t in titles:
            df = fetch_article(t, end)
            if df is None:
                retry.append(t)
            else:
                got[t] = df
            time.sleep(1.0)
        # Wikimedia answers bursts with transient 429s; retry those once more, slowly.
        for t in retry:
            time.sleep(10)
            df = fetch_article(t, end, retries=6, backoff=10)
            if df is None:
                missing.append(t)
            else:
                got[t] = df
        return got

    main_views = fetch_all(ARTICLES)
    for a in ARTICLES:
        print(f"  {a}: {len(main_views.get(a, []))} months")
        if a in main_views:
            frames.append(main_views[a])
    for target in WITH_REDIRECTS:
        rd_views = {t: df for t, df in fetch_all(redirects_to(target)).items() if len(df)}
        parts = [main_views.get(target, pd.DataFrame())]
        for df in rd_views.values():
            parts.append(df.assign(metric="pageviews_user_redirect"))
            frames.append(parts[-1])
        total = pd.concat(parts).groupby("date", as_index=False)["value"].sum()
        frames.append(total.assign(term=target + "+redirects", metric="pageviews_user_all_titles"))
        print(f"  {target}: {len(rd_views)} redirect titles with views")
    print(f"  still failing after retry: {missing or 'none'}")
    tidy = pd.concat(frames, ignore_index=True).sort_values(["term", "date"])
    tidy.to_csv(out / "pageviews_monthly.csv", index=False)
    print(f"wrote {len(tidy)} rows")
    write_source_note(
        SOURCE,
        title="Wikipedia pageviews (English, user agents, monthly)",
        urls=["https://wikimedia.org/api/rest_v1/ (Pageviews per-article API)"],
        notes=f"""
Articles: {', '.join(ARTICLES)}.
- agent=user excludes self-identified bots/spiders; automated traffic not flagged as such can still leak in.
- Counts views of the exact title only; views of redirects are not included.
- The API starts 2015-07. The current month is partial (to the fetch date).
- An article created recently (e.g. the 2025 memory shortage article) has no rows before creation.
- The memory-shortage article (created 2025-12-16 as a draft, renamed several times) also has
  metric=pageviews_user_redirect rows for each redirect/former title, and a summed series
  term="<article>+redirects", metric=pageviews_user_all_titles. Use the summed series for that article.
- Re-running re-downloads everything (one request per article).
- Titles that still failed (transient HTTP 429/5xx) after a slow retry on the last run, so are
  missing from that run's data: {missing or 'none'}.
""",
    )


if __name__ == "__main__":
    main()
