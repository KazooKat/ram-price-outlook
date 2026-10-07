# GDELT DOC 2.0 news volume and tone

Fetched: 2026-10-07

Sources:
- https://api.gdeltproject.org/api/v2/doc/doc
- https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/

Queries (GDELT query syntax): {'RAM prices': '"RAM prices"', 'memory shortage': '("memory shortage" OR "memory chip shortage" OR "DRAM shortage")', 'DRAM prices': '"DRAM prices"', 'memory prices': '"memory prices"', 'memory chip prices': '"memory chip prices"', 'HBM': '"high bandwidth memory"', 'NAND prices': '"NAND prices"', 'SSD prices': '"SSD prices"', 'GPU prices': '("GPU prices" OR "graphics card prices")'}
Window 20170101 to fetch time, daily resolution. Modes: timelinevolraw (article counts + total
monitored), timelinetone. gdelt_daily.csv keeps the API output; gdelt_monthly.csv: articles = monthly
sum, share_of_monitored = articles / total monitored articles, avg_tone = article-weighted mean of
daily average tone (months with no matching articles have no tone; a tone series whose volume
  series is missing is kept in gdelt_daily.csv only, since zero-article days report tone 0).
- GDELT searches its global news crawl (machine-translated non-English included); its source list
  changes over time, so use share_of_monitored for trends, not raw article counts.
- GDELT rate-limits hard (HTTP 429 even at 10 s spacing in testing). cache/ holds each query's last
  successful response; refused queries fall back to it.
- Last run: fresh 0; from cache: ['RAM prices/volraw (cached 2026-10-07)', 'RAM prices/tone (cached 2026-10-07)', 'memory shortage/volraw (cached 2026-10-07)', 'memory shortage/tone (cached 2026-10-07)', 'DRAM prices/volraw (cached 2026-10-07)', 'memory prices/volraw (cached 2026-10-07)', 'memory chip prices/volraw (cached 2026-10-07)', 'memory chip prices/tone (cached 2026-10-07)', 'HBM/volraw (cached 2026-10-07)', 'NAND prices/tone (cached 2026-10-07)']; missing (never fetched): ['DRAM prices/tone', 'memory prices/tone', 'HBM/tone', 'NAND prices/volraw', 'SSD prices/volraw', 'SSD prices/tone', 'GPU prices/volraw', 'GPU prices/tone'].
