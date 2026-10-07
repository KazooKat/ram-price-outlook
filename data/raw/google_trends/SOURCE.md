# Google Trends search interest (monthly)

Fetched: 2026-10-07

Sources:
- https://trends.google.com/trends/ (via pytrends 4.9.2, unofficial client)

Groups (each fetched as one comparison, so terms share a scale): {'memory': ['RAM prices', 'RAM shortage', 'DDR5', 'DDR4', 'memory prices'], 'components': ['RAM prices', 'GPU prices', 'SSD prices', 'CPU prices', 'GPU shortage']}.
Geos: US and worldwide. Timeframe 2016-01-01 to fetch date; Google returns monthly points for spans over 5 years.
- Values are relative (0-100) within one group+geo request, not absolute search counts.
- Google samples the underlying data, so a re-fetch can shift values by a few points; the whole file is re-downloaded each run.
- Search terms (not topics) are used, so matching is on the literal query text in any language region.
- is_partial marks the current, incomplete month.
- For "RAM prices" use group=components: in group=memory, DDR5 sets the 100 so "RAM prices" is squeezed
  into a few integer steps (1-17 in 2025-26), losing resolution.
- Worldwide "RAM prices" jumped in 2025-08/09 (to ~30) while the US stayed at 6-8; a region breakdown to
  explain it was rate-limited (HTTP 429) and not obtained. A non-PC meaning of the literal query
  (e.g. livestock or the Ram truck brand) is possible but unconfirmed.
