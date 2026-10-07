# John C. McCallum - historical memory, disk, flash and SSD prices

Fetched: 2026-10-06

Sources:
- http://web.archive.org/web/20250716092935id_/http://jcmit.net/memoryprice.htm
- http://web.archive.org/web/20250614051021id_/http://jcmit.net/diskprice.htm
- http://web.archive.org/web/20250614035024id_/http://jcmit.net/flashprice.htm
- (original, now hijacked) https://jcmit.net/memoryprice.htm

Original site jcmit.net now redirects to an unrelated casino site (checked 2026-10-06);
data read from the last genuine Wayback captures. Data ends 2024-07-28.

Columns: price = McCallum's listed US$/MB (nominal, not inflation-adjusted);
usd_per_mb_recomputed = item_cost_usd / size_mb as a cross-check. Rows are single
retail listings, generally the cheapest price per MB McCallum found that month
(Newegg since ~2009), so the product mix shifts over time (DIMM vs SO-DIMM,
DDR3 -> DDR4, capacity). Sampling is irregular: roughly annual pre-1975, then
monthly-ish. series: memory (DRAM), disk (HDD), flash (USB/cards, ends 2017),
ssd (from 2013). Dates come from the Year/Month columns; decimal-year column has typos.
cost_column_mismatch=True marks rows whose cost/size columns disagree with the listed
$/MB (3 memory rows, 2017-05, 2017-09, 2018-12); the listed $/MB matches the row's
description text in each case, so `price` is trustworthy there. SSD sizes use binary GB
in usd_per_mb_recomputed while McCallum used decimal, hence a ~2.5% gap.
