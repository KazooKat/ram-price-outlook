"""Monthly English Wikipedia pageviews for component-related articles.

Attention proxy: how many people (user agent only, bots excluded) read each
article per month. Output: data/raw/wikipedia_pageviews/pageviews_monthly.csv
in tidy form (date, term, metric, value).
"""
from __future__ import annotations

import datetime as dt
import time
from urllib.parse import quote

import pandas as pd

from fetch._common import get, raw_dir, write_source_note

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


def fetch_article(article: str, end: str) -> pd.DataFrame:
    url = API.format(article=quote(article, safe=""), start=START, end=end)
    try:
        items = get(url).json()["items"]
    except Exception as e:  # 404 when an article has no views in range
        print(f"  {article}: failed ({e})")
        return pd.DataFrame()
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
    frames = []
    for a in ARTICLES:
        df = fetch_article(a, end)
        print(f"  {a}: {len(df)} months")
        frames.append(df)
        time.sleep(0.5)
    for target in WITH_REDIRECTS:
        parts = [frames[ARTICLES.index(target)]]
        for rd in redirects_to(target):
            df = fetch_article(rd, end)
            if len(df):
                parts.append(df.assign(metric="pageviews_user_redirect"))
                frames.append(parts[-1])
            time.sleep(1.5)
        total = pd.concat(parts).groupby("date", as_index=False)["value"].sum()
        frames.append(total.assign(term=target + "+redirects", metric="pageviews_user_all_titles"))
        print(f"  {target}: {len(parts) - 1} redirect titles with views")
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
""",
    )


if __name__ == "__main__":
    main()
