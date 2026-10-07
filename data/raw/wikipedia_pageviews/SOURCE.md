# Wikipedia pageviews (English, user agents, monthly)

Fetched: 2026-10-06

Sources:
- https://wikimedia.org/api/rest_v1/ (Pageviews per-article API)

Articles: Dynamic_random-access_memory, Random-access_memory, DDR4_SDRAM, DDR5_SDRAM, High_Bandwidth_Memory, Flash_memory, Solid-state_drive, Graphics_processing_unit, Central_processing_unit, Chip_shortage, 2020–2023_global_chip_shortage, 2025–present_global_memory_supply_shortage.
- agent=user excludes self-identified bots/spiders; automated traffic not flagged as such can still leak in.
- Counts views of the exact title only; views of redirects are not included.
- The API starts 2015-07. The current month is partial (to the fetch date).
- An article created recently (e.g. the 2025 memory shortage article) has no rows before creation.
- The memory-shortage article (created 2025-12-16 as a draft, renamed several times) also has
  metric=pageviews_user_redirect rows for each redirect/former title, and a summed series
  term="<article>+redirects", metric=pageviews_user_all_titles. Use the summed series for that article.
- Re-running re-downloads everything (one request per article).
