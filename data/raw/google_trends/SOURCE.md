# Google Trends search interest (monthly)

Fetched: 2026-10-06

Sources:
- https://trends.google.com/trends/ (via pytrends 4.9.2, unofficial client)

Groups (each fetched as one comparison, so terms share a scale): {'memory': ['RAM prices', 'RAM shortage', 'DDR5', 'DDR4', 'memory prices'], 'components': ['RAM prices', 'GPU prices', 'SSD prices', 'CPU prices', 'GPU shortage']}.
Geos: US and worldwide. Timeframe 2016-01-01 to fetch date; Google returns monthly points for spans over 5 years.
- Values are relative (0-100) within one group+geo request, not absolute search counts.
- Google samples the underlying data, so a re-fetch can shift values by a few points; the whole file is re-downloaded each run.
- Search terms (not topics) are used, so matching is on the literal query text in any language region.
- is_partial marks the current, incomplete month.
