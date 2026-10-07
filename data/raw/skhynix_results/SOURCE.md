# SK hynix quarterly results (company earnings press releases)

Fetched: 2026-10-06

Sources:
- https://news.skhynix.com/en/wp-json/wp/v2/posts?search=results
- https://news.skhynix.com/en/

Parsed from SK hynix's official English earnings press releases (newsroom).
DART (Korea FSS) was not used because its API requires a key.

- revenue / operating_profit / net_profit: KRW trillion, K-IFRS consolidated,
  for the quarter (Q4 releases also state full-year figures; the parser skips
  sentences framed as annual). Losses are negative.
- dram_/nand_ bit_shipments_qoq_pct and asp_qoq_pct: quarter-over-quarter
  changes as stated in the release (mostly 2015-2020 releases; later releases
  stopped giving numeric ASP/bit figures). Company-stated, rounded.
- source_text holds the sentence each value was parsed from - audit there.
- Regex extraction from prose: a quarter missing a metric means the parser
  did not find a matching sentence, not that the value is zero.
- SK hynix listed ADRs on Nasdaq in July 2026 (CIK 2120882) and now files 6-Ks
  on EDGAR; quarterly history before that is only on the company site / DART.
