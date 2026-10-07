"""Reddit discussion volume and keyword sentiment about RAM prices (Arctic Shift archive).

Step 1 (fetch, cached): for each subreddit and month, page through every post
(Arctic Shift subreddit listing, limit=auto, ~500 posts per call) and keep only
posts whose title matches KEEP_RE (RAM/memory words): id, created_utc, title,
score, num_comments. One gzip JSONL file per subreddit/month under
data/raw/reddit_arctic/posts/, plus <sub>_<YYYY-MM>.meta.json with the number of
posts scanned (coverage check against the archive's own monthly total).
Completed months are skipped on re-run; the current month is refreshed at most
daily. Newest months first. A month the archive keeps refusing is skipped and
left uncovered (reported, never filled with zeros).

Why not server-side title search: in testing (2026-10-06) Arctic Shift title
searches on these subreddits mostly failed (HTTP 422 "Timeout"), multi-month
windows hit its ~7 s query limit, and one month of r/buildapc took ~25 minutes.

Step 2 (denominator): monthly total posts per subreddit from Arctic Shift's
/api/time_series (r/<sub>/posts/count).

Step 3 (measure): classify each title with the transparent regex lists below
and count per month. VADER compound score on RAM-price titles as a secondary measure.

Output: data/raw/reddit_arctic/reddit_monthly.csv (date, term, metric, value);
term is the subreddit or ALL (sum over subreddits, only for months all are covered).
"""
from __future__ import annotations

import sys
from pathlib import Path
import argparse
import datetime as dt
import gzip
import json
import re
import time

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetch._common import get, raw_dir, write_source_note  # noqa: E402

SOURCE = "reddit_arctic"
BASE = "https://arctic-shift.photon-reddit.com"
SEARCH = BASE + "/api/posts/search"
SERIES = BASE + "/api/time_series"
FIELDS = "id,created_utc,title,score,num_comments"
START = "2025-01"
SLEEP = 1.5
RETRY_WAIT = 8      # seconds, grows every 5 refusals
MAX_ATTEMPTS = 25   # per request (~10 min of refusals) before the month is skipped

# Every post is scanned, so each subreddit costs ~1 call per 500 posts; these three cover
# buyers (buildapc), enthusiasts (pcmasterrace) and industry news (hardware).
SUBREDDITS = ["buildapc", "pcmasterrace", "hardware"]
# Titles kept from the scan (everything else is only counted).
KEEP_RE = r"\b(ram|rams|dram|ddr4|ddr5|memory)\b"

# Local classification of titles (lowercased). Keep these lists the single source of truth.
RAM_RE = r"\b(ram|rams|dram|ddr4|ddr5)\b"
PRICE_RE = (r"\b(price|prices|priced|pricing|cost|costs|costly|expensive|cheap|cheaper|cheapest|"
            r"overpriced|afford|affordable|msrp|shortage|shortages|inflation|inflated|gouging|scalp\w*)\b")
# Price going up / pain.
NEG_TERMS = [
    r"price (hike|hikes|increase|increases|surge|spike|spikes|jump)", r"prices? (went|going|are going|keep going) up",
    r"\bsky ?rocket\w*", r"\bshortage", r"\bexpensive\b", r"\boverpriced\b", r"\binsane\b", r"\bridiculous\b",
    r"\bcrazy\b", r"\babsurd\b", r"\bgouging\b", r"\bscalp\w*", r"\binflat\w*", r"\brising\b", r"\bdoubled\b",
    r"\btripled\b", r"can'?t afford", r"\bcrisis\b", r"\bexplod\w*", r"through the roof", r"\bspik\w*", r"\bsurg\w*",
    r"higher prices?", r"prices? (are |is )?(so |still |too )?high\b", r"\bworsen\w*",
]
# Price coming down / relief.
POS_TERMS = [
    r"\bcheaper\b", r"\bcheap\b", r"price (drop|drops|dropped|cut|cuts|fall|falling)", r"prices? (dropp?\w*|fell|falling|crash\w*)",
    r"(came|coming|going|come|go) (back )?down", r"back to normal", r"\bfinally\b", r"(good|great) deal", r"\bsteal\b",
    r"all[- ]time low", r"lowest price", r"\bon sale\b",
]
# Buy-or-wait deliberation.
WAIT_TERMS = [
    r"\bwait\b", r"\bwaiting\b", r"hold off", r"\bbuy (it )?now\b", r"now or later", r"should i (buy|get) (it |ram |this )?now",
    r"when will", r"will (ram |memory |ddr\d )?prices", r"\bhedge\b", r"before prices", r"will .{0,40}(go|come) (back )?down",
]
# Note: categories overlap by design (e.g. "wait for prices to come back down" is both wait and pos).


def any_re(terms: list[str]) -> re.Pattern:
    # Make every group non-capturing so pandas str.contains doesn't warn about match groups.
    return re.compile("|".join(f"(?:{re.sub(r'\((?!\?)', '(?:', t)})" for t in terms))


def api_json(url: str, params: dict) -> dict:
    """Arctic Shift answers overload with HTTP 422 {"error": "Timeout. Maybe slow down a bit"};
    the same request usually succeeds on a later try, so pause and retry."""
    for attempt in range(MAX_ATTEMPTS):
        try:
            r = get(url, params=params, timeout=180)
            body = r.json()
        except requests.HTTPError as e:
            if e.response is None or e.response.status_code != 422:
                raise
            body = {"data": None, "error": e.response.text[:80]}
        except (RuntimeError, ValueError) as e:
            body = {"data": None, "error": repr(e)[:80]}
        if body.get("data") is not None:
            return body
        if attempt % 5 == 4:
            print(f"    {attempt + 1} refusals for {params.get('key') or params.get('subreddit')} "
                  f"{params.get('after', '')}; last {body.get('error')!r}", flush=True)
        time.sleep(RETRY_WAIT * (1 + attempt // 5))
    raise RuntimeError(f"Arctic Shift kept failing for {params}")


def fetch_month(sub: str, ym: str) -> tuple[list[dict], int]:
    """All posts of one subreddit-month; returns (posts whose title matches KEEP_RE, posts scanned)."""
    lo, hi = month_bounds(ym)
    keep_re = re.compile(KEEP_RE)
    seen: set[str] = set()
    kept: list[dict] = []
    after = lo - 1  # 'after' is exclusive; dedupe on id covers boundary repeats
    while True:
        batch = api_json(SEARCH, {"subreddit": sub, "after": after, "before": hi, "sort": "asc",
                                  "limit": "auto", "fields": FIELDS})["data"]
        new = 0
        for p in batch:
            if p["id"] in seen or not lo <= int(p["created_utc"]) < hi:
                continue
            seen.add(p["id"])
            new += 1
            if keep_re.search((p.get("title") or "").lower()):
                kept.append({k: p.get(k) for k in FIELDS.split(",")})
        time.sleep(SLEEP)
        if not batch or new == 0:
            break
        last = max(int(p["created_utc"]) for p in batch)
        # Step back one second so posts sharing the boundary timestamp are not skipped.
        after = last - 1 if last - 1 > after else last
    return sorted(kept, key=lambda p: p["created_utc"]), len(seen)


def month_list(start: str, end: dt.date) -> list[str]:
    y, m = map(int, start.split("-"))
    out = []
    while (y, m) <= (end.year, end.month):
        out.append(f"{y:04d}-{m:02d}")
        y, m = y + (m == 12), m % 12 + 1
    return out


def month_bounds(ym: str) -> tuple[int, int]:
    y, m = map(int, ym.split("-"))
    lo = dt.datetime(y, m, 1, tzinfo=dt.timezone.utc)
    hi = dt.datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=dt.timezone.utc)
    return int(lo.timestamp()), int(hi.timestamp())


def fetch_posts(months: list[str]) -> list[str]:
    pdir = raw_dir(SOURCE) / "posts"
    pdir.mkdir(exist_ok=True)
    cur = dt.date.today().strftime("%Y-%m")
    failed = []
    for ym in sorted(months, reverse=True):
        for sub in SUBREDDITS:
            f = pdir / f"{sub}_{ym}.jsonl.gz"
            meta = pdir / f"{sub}_{ym}.meta.json"
            # Completed months never change; the current month is refreshed at most daily.
            if meta.exists() and (ym < cur or time.time() - meta.stat().st_mtime < 86400):
                continue
            t0 = time.time()
            try:
                kept, scanned = fetch_month(sub, ym)
            except RuntimeError as e:
                print(f"  {sub} {ym}: SKIPPED ({e})", flush=True)
                failed.append(f"{sub}/{ym}")
                continue
            with gzip.open(f, "wt", encoding="utf-8") as fh:
                for p in kept:
                    fh.write(json.dumps(p, ensure_ascii=False) + "\n")
            meta.write_text(json.dumps({"scanned": scanned, "kept": len(kept)}), encoding="utf-8")
            print(f"  {sub} {ym}: scanned {scanned}, kept {len(kept)} ({time.time() - t0:.0f}s)", flush=True)
    return failed


def fetch_totals(start: str) -> pd.DataFrame:
    rows = []
    for sub in SUBREDDITS:
        data = api_json(SERIES, {"key": f"r/{sub}/posts/count", "precision": "month", "after": start + "-01"})["data"]
        for d in data:
            t = dt.datetime.fromtimestamp(int(d["date"]), dt.timezone.utc)
            rows.append({"date": f"{t.year:04d}-{t.month:02d}-01", "term": sub, "metric": "posts_total",
                         "value": int(d["value"])})
        time.sleep(SLEEP)
    return pd.DataFrame(rows)


def load_posts() -> tuple[pd.DataFrame, set[tuple[str, str]], pd.DataFrame]:
    """Cached kept posts, the covered (subreddit, month) pairs, and the scan counts."""
    recs, covered, scans = [], set(), []
    pdir = raw_dir(SOURCE) / "posts"
    for meta in sorted(pdir.glob("*.meta.json")):
        sub, ym = meta.name.removesuffix(".meta.json").rsplit("_", 1)
        if sub not in SUBREDDITS:
            continue
        covered.add((sub, ym + "-01"))
        scans.append({"date": ym + "-01", "term": sub, **json.loads(meta.read_text(encoding="utf-8"))})
        with gzip.open(pdir / f"{sub}_{ym}.jsonl.gz", "rt", encoding="utf-8") as fh:
            recs += [dict(json.loads(line), sub=sub) for line in fh]
    df = pd.DataFrame(recs, columns=FIELDS.split(",") + ["sub"]).drop_duplicates("id")
    df["date"] = pd.to_datetime(df["created_utc"], unit="s", utc=True).dt.strftime("%Y-%m-01")
    return df, covered, pd.DataFrame(scans, columns=["date", "term", "scanned", "kept"])


def measure(posts: pd.DataFrame, totals: pd.DataFrame, covered: set[tuple[str, str]]) -> pd.DataFrame:
    t = posts["title"].fillna("").str.lower()
    wait = t.str.contains(any_re(WAIT_TERMS))
    ram = posts.assign(
        ram_posts=t.str.contains(any_re([RAM_RE])),
        ram_price=t.str.contains(any_re([PRICE_RE])),
        ram_neg=t.str.contains(any_re(NEG_TERMS)),
        # Hoping prices fall ("wait for prices to come back down") is not relief: pos excludes wait titles.
        ram_pos=t.str.contains(any_re(POS_TERMS)) & ~wait,
        ram_wait=wait,
    )
    ram = ram[ram["ram_posts"]].copy()
    ram["ram_price_neg"] = ram["ram_price"] & ram["ram_neg"]
    ram["ram_price_pos"] = ram["ram_price"] & ram["ram_pos"]
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        sia = SentimentIntensityAnalyzer()
        ram["vader"] = [sia.polarity_scores(x)["compound"] if p else float("nan")
                        for x, p in zip(ram["title"].fillna(""), ram["ram_price"])]
    except ImportError:
        ram["vader"] = float("nan")

    flags = ["ram_posts", "ram_price", "ram_price_neg", "ram_price_pos", "ram_neg", "ram_pos", "ram_wait"]
    agg = {f: "sum" for f in flags} | {"vader": "mean"}
    per_sub = ram.groupby(["date", "sub"]).agg(agg).reset_index().rename(columns={"sub": "term"})
    tot = totals.rename(columns={"value": "posts_total"})[["date", "term", "posts_total"]]
    # Grid of covered (subreddit, month) pairs: a covered month with no RAM posts is a real zero.
    grid = pd.DataFrame(sorted(covered), columns=["term", "date"]).merge(tot, on=["date", "term"], how="left")
    wide = grid.merge(per_sub, on=["date", "term"], how="left")
    wide[flags] = wide[flags].fillna(0)

    # ALL: only months where every subreddit is covered.
    full = wide.groupby("date").filter(lambda g: set(g["term"]) == set(SUBREDDITS))
    all_rows = full.groupby("date")[flags + ["posts_total"]].sum(min_count=1).reset_index().assign(term="ALL")
    all_vader = ram[ram["date"].isin(all_rows["date"])].groupby("date")["vader"].mean()
    all_rows["vader"] = all_rows["date"].map(all_vader)
    wide = pd.concat([wide, all_rows], ignore_index=True).rename(columns={"vader": "ram_price_vader_mean"})

    per1k = wide["posts_total"] / 1000
    for f in ["ram_posts", "ram_price", "ram_price_neg", "ram_neg", "ram_wait"]:
        wide[f + "_per_1k"] = wide[f] / per1k
    denom = wide["ram_neg"] + wide["ram_pos"]
    wide["ram_net_tone"] = (wide["ram_pos"] - wide["ram_neg"]) / denom.where(denom > 0)
    long = wide.melt(id_vars=["date", "term"], var_name="metric", value_name="value").dropna(subset=["value"])
    return long.sort_values(["term", "metric", "date"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=START, help="first month, YYYY-MM")
    ap.add_argument("--measure-only", action="store_true", help="skip fetching; recompute from cached posts")
    args = ap.parse_args()
    out = raw_dir(SOURCE)
    failed = [] if args.measure_only else fetch_posts(month_list(args.start, dt.date.today()))
    totals = fetch_totals(args.start)
    totals.to_csv(out / "subreddit_post_totals.csv", index=False)
    posts, covered, scans = load_posts()
    tidy = measure(posts, totals, covered)
    # Coverage: posts the scan saw vs the archive's own monthly count (current month differs by timing).
    cov = scans.merge(totals.rename(columns={"value": "archive_total"})[["date", "term", "archive_total"]],
                      on=["date", "term"], how="left")
    cov["scan_ratio"] = (cov["scanned"] / cov["archive_total"]).round(3)
    cov.sort_values(["term", "date"]).to_csv(out / "coverage.csv", index=False)
    tidy = pd.concat([tidy, cov.melt(id_vars=["date", "term"], value_vars=["scanned", "scan_ratio"],
                                     var_name="metric", value_name="value")], ignore_index=True)
    tidy.to_csv(out / "reddit_monthly.csv", index=False)
    months_cov = sorted({d for _, d in covered})
    print(f"{len(posts)} kept posts; scan_ratio range {cov['scan_ratio'].min()}..{cov['scan_ratio'].max()}; {len(covered)} subreddit-months covered "
          f"({months_cov[0] if months_cov else '-'}..{months_cov[-1] if months_cov else '-'}); "
          f"skipped this run: {failed or 'none'}; wrote {len(tidy)} rows")
    write_source_note(
        SOURCE,
        title="Reddit RAM-price discussion volume and keyword sentiment (Arctic Shift)",
        urls=[SEARCH, SERIES, "https://github.com/ArthurHeitmann/arctic_shift/blob/master/api/README.md"],
        notes=f"""
Subreddits: {', '.join(SUBREDDITS)}. From {args.start}. Every post in each subreddit-month is scanned
(subreddit listing); titles matching {KEEP_RE} are kept in posts/<sub>_<YYYY-MM>.jsonl.gz
(id, created_utc, title, score, num_comments; score/num_comments as of archive time) and the scan
count is in <sub>_<YYYY-MM>.meta.json. Titles only; post bodies and comments are not used.

Local classification (lowercased title, regexes in fetch/sentiment_reddit.py):
- ram_posts: title matches {RAM_RE} ("memory" alone is kept in the cache but not counted, since in
  these subreddits it often means VRAM or memory usage)
- ram_price: RAM title that also matches the price-word regex
- ram_neg / ram_pos: RAM title matching the price-up/pain list or the price-relief list (pos excludes
  titles with buy-or-wait language, which express hoped-for, not actual, declines)
- ram_price_neg / ram_price_pos: same, restricted to ram_price titles
- ram_wait: RAM title with buy-or-wait language
- *_per_1k: per 1,000 posts in the subreddit that month (posts_total = Arctic Shift time_series)
- ram_net_tone = (ram_pos - ram_neg) / (ram_pos + ram_neg), blank when both are 0
- ram_price_vader_mean: mean VADER compound score (vaderSentiment 3.3.2) of ram_price titles. VADER is a
  general-purpose lexicon that does not know "cheaper" is good news for a buyer; prefer ram_net_tone.
- scanned / scan_ratio: posts the scan saw, and that divided by posts_total (coverage check; also in coverage.csv)
term=ALL sums the subreddits, only for months where every subreddit was fetched.

Scope and caveats:
- Server-side title search was tried first and abandoned (mostly HTTP 422 "Timeout", ~25 min per
  subreddit-month). Full scans cost ~1 request per ~500 posts, so the window starts at {args.start};
  r/Amd, r/intel, r/nvidia were left out to keep the run within hours. Re-run with --start to extend.
- Months the archive refused for ~10 minutes are skipped and have no rows (never zero-filled);
  re-running fills them in. Skipped on the last run: {failed or 'none'}.
- "ram" also matches e.g. the truck brand; the current month is partial; the archive may miss
  posts removed before it captured them.
""",
    )


if __name__ == "__main__":
    main()
