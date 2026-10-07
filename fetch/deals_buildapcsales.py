"""Fetch r/buildapcsales post metadata (2019-01 .. present) from the Arctic Shift archive.

Arctic Shift (https://github.com/ArthurHeitmann/arctic_shift) is a free, keyless
Reddit archive API. PullPush was tried and refuses unauthenticated scraping
("Rate limit exceeded ... paid scraping service"), so it is not used.

Output: data/raw/buildapcsales/YYYY-MM.jsonl.gz, one post per line with
id, created_utc, title, score, num_comments, link_flair_text, domain.
Completed months are skipped on re-run; the current month is always re-fetched.

Also writes data/raw/buildapcsales/coverage.csv comparing fetched posts per month
against Arctic Shift's own aggregate count for the subreddit.

Usage: python fetch/deals_buildapcsales.py [--start 2019-01] [--refetch YYYY-MM ...]
"""
from __future__ import annotations

import argparse
import calendar
import csv
import datetime as dt
import gzip
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get, raw_dir, write_source_note  # noqa: E402

SOURCE = "buildapcsales"
BASE = "https://arctic-shift.photon-reddit.com/api/posts/search"
AGG = BASE + "/aggregate"
FIELDS = "id,created_utc,title,score,num_comments,link_flair_text,url"
SLEEP = 1.5  # seconds between calls; the API also returns X-RateLimit-* headers


def month_bounds(ym: str) -> tuple[int, int]:
    y, m = map(int, ym.split("-"))
    start = dt.datetime(y, m, 1, tzinfo=dt.timezone.utc)
    end = dt.datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=dt.timezone.utc)
    return int(start.timestamp()), int(end.timestamp())


def months(start: str, end: dt.date) -> list[str]:
    y, m = map(int, start.split("-"))
    out = []
    while (y, m) <= (end.year, end.month):
        out.append(f"{y:04d}-{m:02d}")
        y, m = y + (m == 12), m % 12 + 1
    return out


def api_json(url: str, params: dict) -> dict:
    """Arctic Shift returns {"data": null, "error": "Timeout..."} or a transient HTTP 422
    under load; the same request succeeds on retry, so back off and retry those."""
    for attempt in range(6):
        try:
            r = get(url, params=params, timeout=120)
        except requests.HTTPError as e:
            if e.response is None or e.response.status_code != 422:
                raise
            body = {"data": None, "error": f"HTTP 422 {e.response.text[:100]}"}
        else:
            body = r.json()
        if body.get("data") is not None:
            remaining = r.headers.get("X-RateLimit-Remaining")
            if remaining is not None and int(remaining) < 5:
                time.sleep(float(r.headers.get("X-RateLimit-Reset", 10)))
            return body
        wait = 5 * (2 ** attempt)
        print(f"  API error {body.get('error')!r}; sleeping {wait}s", flush=True)
        time.sleep(wait)
    raise RuntimeError(f"Arctic Shift kept failing for {params}")


def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except ValueError:  # some archived urls are malformed (e.g. stray '[' in the host)
        return ""


def slim(p: dict) -> dict:
    return {
        "id": p["id"],
        "created_utc": int(p["created_utc"]),
        "title": p.get("title") or "",
        "score": p.get("score"),
        "num_comments": p.get("num_comments"),
        "link_flair_text": p.get("link_flair_text"),
        "domain": domain_of(p.get("url") or ""),
    }


def fetch_month(ym: str) -> list[dict]:
    lo, hi = month_bounds(ym)
    seen: dict[str, dict] = {}
    after = lo - 1  # 'after' is treated as exclusive; dedupe on id covers either case
    while True:
        body = api_json(BASE, {
            "subreddit": SOURCE, "after": after, "before": hi, "sort": "asc",
            "limit": "auto", "fields": FIELDS,
        })
        batch = body["data"]
        new = 0
        for p in batch:
            if p["id"] not in seen and lo <= int(p["created_utc"]) < hi:
                seen[p["id"]] = slim(p)
                new += 1
        time.sleep(SLEEP)
        if not batch or new == 0:
            break
        last = max(int(p["created_utc"]) for p in batch)
        # Step back one second so posts sharing the boundary timestamp are not skipped.
        after = last - 1 if last - 1 > after else last
    return sorted(seen.values(), key=lambda p: p["created_utc"])


def archive_counts(years: list[int]) -> dict[str, int]:
    """Arctic Shift's own monthly totals. Buckets are labelled in server-local time
    (e.g. 2019-01-31T23:00Z == Feb), so map each bucket to the UTC month 12h later."""
    out = {}
    for y in years:
        body = api_json(AGG, {
            "aggregate": "created_utc", "frequency": "month", "subreddit": SOURCE,
            "after": f"{y}-01-01", "before": f"{y + 1}-01-01",
        })
        for row in body["data"]:
            t = dt.datetime.fromisoformat(row["created_utc"].replace("Z", "+00:00"))
            t += dt.timedelta(hours=12)
            out[f"{t.year:04d}-{t.month:02d}"] = int(row["count"])
        time.sleep(SLEEP)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2019-01")
    ap.add_argument("--refetch", nargs="*", default=[])
    args = ap.parse_args()

    out_dir = raw_dir(SOURCE)
    today = dt.datetime.now(dt.timezone.utc).date()
    current = f"{today.year:04d}-{today.month:02d}"
    fetched: dict[str, int] = {}
    for ym in months(args.start, today):
        path = out_dir / f"{ym}.jsonl.gz"
        if path.exists() and ym != current and ym not in args.refetch:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                fetched[ym] = sum(1 for _ in f)
            continue
        t0 = time.time()
        posts = fetch_month(ym)
        with gzip.open(path, "wt", encoding="utf-8") as f:
            for p in posts:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
        fetched[ym] = len(posts)
        print(f"{ym}: {len(posts)} posts ({time.time() - t0:.0f}s)", flush=True)

    ref = archive_counts(sorted({int(ym[:4]) for ym in fetched}))
    with open(out_dir / "coverage.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["month", "fetched", "archive_aggregate", "ratio"])
        for ym, n in fetched.items():
            a = ref.get(ym)
            w.writerow([ym, n, a if a is not None else "", f"{n / a:.3f}" if a else ""])

    write_source_note(
        SOURCE,
        title="r/buildapcsales post metadata (Arctic Shift archive)",
        urls=[BASE, AGG, "https://github.com/ArthurHeitmann/arctic_shift/blob/master/api/README.md"],
        notes=(
            "Fields kept: id, created_utc, title, score, num_comments, link_flair_text, "
            "domain (derived from the post url). Score/num_comments are as of the archive's "
            "retrieval time, not final. One gzip JSONL file per UTC month. coverage.csv compares "
            "posts fetched per month with the archive's aggregate count (it matches exactly), "
            "but that only proves we pulled everything Arctic Shift holds; completeness against "
            "Reddit itself was not verifiable because reddit.com JSON returns 403 to "
            "unauthenticated clients. PullPush (api.pullpush.io) was tried first and rejected "
            "unauthenticated requests."
        ),
    )


if __name__ == "__main__":
    main()
