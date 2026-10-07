# Hacker News mentions of component-price phrases (monthly counts)

Fetched: 2026-10-07

Sources:
- https://hn.algolia.com/api/v1/search_by_date
- https://hn.algolia.com/api

Terms (exact phrase, case-insensitive, typo tolerance off): "RAM prices", "DRAM prices", "memory prices", "memory shortage", "RAM shortage", "DRAM", "HBM", "DDR5", "SSD prices", "NAND", "GPU prices", "GPU shortage".
metric: stories / comments = items matching the phrase that month (Algolia nbHits);
exact = Algolia's exhaustiveNbHits flag for that count.
metric total_items (term=ALL) = HN item-id span for the month (all stories, comments, polls, jobs),
used as the normalizing denominator. Empty-query nbHits was not used: it is approximate and was
wildly wrong in testing (e.g. 3.4M stories reported for 2026-09 vs ~25k normal).
- Story matches are on title, URL and story text as indexed by Algolia; comments on comment text.
- "DRAM", "HBM", "NAND", "DDR5" also match non-price discussion; treat as broad attention, not price talk.
- The current month is partial. The last two months are re-fetched on each run; older months are cached.
