# Reddit RAM-price discussion volume and keyword sentiment (Arctic Shift)

Fetched: 2026-10-07

Sources:
- https://arctic-shift.photon-reddit.com/api/posts/search
- https://arctic-shift.photon-reddit.com/api/time_series
- https://github.com/ArthurHeitmann/arctic_shift/blob/master/api/README.md

Subreddits: buildapc, pcmasterrace, hardware. From 2025-01. Every post in each subreddit-month is scanned
(subreddit listing); titles matching \b(ram|rams|dram|ddr4|ddr5|memory)\b are kept in posts/<sub>_<YYYY-MM>.jsonl.gz
(id, created_utc, title, score, num_comments; score/num_comments as of archive time) and the scan
count is in <sub>_<YYYY-MM>.meta.json. Titles only; post bodies and comments are not used.

Local classification (lowercased title, regexes in fetch/sentiment_reddit.py):
- ram_posts: title matches \b(ram|rams|dram|ddr4|ddr5)\b ("memory" alone is kept in the cache but not counted, since in
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
  subreddit-month). Full scans cost ~1 request per ~500 posts, so the window starts at 2025-01;
  r/Amd, r/intel, r/nvidia were left out to keep the run within hours. Re-run with --start to extend.
- Months the archive refused for ~10 minutes are skipped and have no rows (never zero-filled);
  re-running fills them in. Skipped on the last run: none.
- "ram" also matches e.g. the truck brand; the current month is partial; the archive may miss
  posts removed before it captured them.
