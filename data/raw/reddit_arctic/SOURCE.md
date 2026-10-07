# Reddit RAM-price discussion volume and keyword sentiment (Arctic Shift)

Fetched: 2026-10-06

Sources:
- https://arctic-shift.photon-reddit.com/api/posts/search
- https://arctic-shift.photon-reddit.com/api/time_series
- https://github.com/ArthurHeitmann/arctic_shift/blob/master/api/README.md

Subreddits: buildapc, pcmasterrace, hardware. Title keyword searched server-side: ram. From 2024-01.
posts/<sub>_<kw>_<YYYY-MM>.jsonl.gz: id, created_utc, title, score, num_comments (score and
num_comments as of archive time). Titles only; post bodies and comments are not used.

Local classification (lowercased title, regexes in fetch/sentiment_reddit.py):
- ram_posts: title matches \b(ram|rams|dram|ddr4|ddr5)\b (all fetched titles contain "ram", so this is ~all of them)
- ram_price: also matches the price-word regex
- ram_neg / ram_pos: matches the price-up/pain list or the price-relief list
- ram_price_neg / ram_price_pos: same, restricted to ram_price titles
- ram_wait: buy-or-wait language
- *_per_1k: per 1,000 posts in the subreddit that month (posts_total, Arctic Shift time_series)
- ram_net_tone = (ram_pos - ram_neg) / (ram_pos + ram_neg), blank when both are 0
- ram_price_vader_mean: mean VADER compound score (vaderSentiment 3.3.2) of ram_price titles. VADER is a
  general-purpose lexicon that does not know "cheaper" is good news for a buyer; prefer ram_net_tone.
term=ALL sums the subreddits, only for months where every subreddit was fetched.

Scope and caveats:
- Scope was reduced after testing on 2026-10-06: title searches for r/Amd, r/intel, r/nvidia and for
  "dram" on r/hardware were refused on every try, and multi-month windows hit the server's ~7 s
  query timeout. Titles that say "DDR5"/"memory" without "RAM" are therefore not counted.
- Months the archive refused for ~15 minutes are skipped and have no rows (never zero-filled);
  re-running fills them in. Skipped on the last run: none.
- "ram" also matches e.g. the truck brand; the current month is partial; archive coverage of a month
  can be incomplete.
