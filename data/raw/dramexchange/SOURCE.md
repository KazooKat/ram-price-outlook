# DRAMeXchange / TrendForce free spot & contract memory prices (via Wayback Machine)

Fetched: 2026-10-06

Sources:
- https://www.dramexchange.com/
- https://www.trendforce.com/price/dram/dram_spot
- https://www.trendforce.com/price/dram/dram_contract
- http://web.archive.org/cdx/search/cdx (captures of the pages above)
- page sampled: dramexchange.com/
- page sampled: dramexchange.com/default2.asp
- page sampled: dramexchange.com/default.asp
- page sampled: dramexchange.com/default.aspx
- page sampled: dramexchange.com/Common/Json/PriceOpt.aspx?type=NationalDramSpot
- page sampled: trendforce.com/price
- page sampled: trendforce.com/price/dram
- page sampled: trendforce.com/price/dram/dram_spot
- page sampled: trendforce.com/price/dram/dram_contract
- page sampled: trendforce.com/price/dram/module_spot
- page sampled: trendforce.com/price/flash
- page sampled: trendforce.com/price/flash/flash_spot
- page sampled: trendforce.com/price/flash/flash_contract
- page sampled: trendforce.com/price/flash/ssd_street
- page sampled: trendforce.com/price/flash/pcc_oem_ssd_contract

Only the current day's prices are free on these pages; history is member-only. Each
Wayback capture is one observation. Captures sampled: ~2/month (4/month from 2024 for
the dramexchange homepage). Coverage has gaps: 2009-2015 the homepage loaded tables by
AJAX (only 11 AJAX captures exist), so those years are thin.

price = the table's (Session) Average in USD: per chip for DRAM/NAND spot & contract
(e.g. "DDR4 8Gb (1Gx8) 3200" = one 8-gigabit chip), per module for module spot/contract
(e.g. "DDR5 UDIMM 16GB"), per drive for SSD street price. high/low = daily (spot) or
period (contract) range. date = the table's own "Last Update" date when parseable
(date_from=last_update), else the capture date. Spot prices are a thin secondary
market and are more volatile than contract prices (where most volume trades).
DXI (section dxi_index) is DRAMeXchange's DRAM price index; its composition/base is
not documented on the page, so treat levels across decades with caution.
section is assigned from the nearest table heading, then corrected by reclassify()
(NAND/microSD rows mislabelled DRAM on some pages, share-price rows dropped);
section_as_parsed keeps the raw label. DXI is only captured to 2020-12: from ~2021 the
homepage keeps the DXI value inside an HTML comment (not displayed), so it is not parsed.
Item names change as products roll (SDRAM -> DDR -> DDR2 -> DDR3 -> DDR4 -> DDR5),
so long series must be chained across items.
