# UN Comtrade monthly HS6 trade: memory ICs, processors, SSD/storage, computer parts

Fetched: 2026-10-06

Sources:
- https://comtradeapi.un.org/public/v1/preview/C/M/HS?reporterCode=<R>&period=<YYYYMM>&partnerCode=<P,...>&cmdCode=854232,854231,852351,847170,847180,847330&flowCode=<M|X>
- https://comtradeapi.un.org/public/v1/getDA/C/M/HS?reporterCode=<R>
- https://comtradeapi.un.org/files/v1/app/reference/HS.json
- https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json
- https://comtradeapi.un.org/files/v1/app/reference/QuantityUnits.json

Keyless public preview API (one period per call, max 500 rows per call).
Reporters/flows: USA imports (partners [0, 410, 490, 156, 458, 704, 392]); KOR exports (partners [0]); JPN exports (partners [0]); MYS exports (partners [0]).
Partner 0 = World; 490 = "Other Asia, nes" (Taiwan in Comtrade).
HS6 codes: 847170 - Units of automatic data processing machines; storage units; 847180 - Units of automatic data processing machines; n.e.c. in item no. 8471.50, 8471.60 or 8471.70; 847330 - Machinery; parts and accessories (other than covers, carrying cases and the like) of the machines of heading no. 8471; 852351 - Semiconductor media; solid-state non-volatile storage devices, whether or not recorded, excluding products of Chapter 37; 854231 - Electronic integrated circuits; processors and controllers, whether or not combined with memories, converters, logic circuits, amplifiers, clock and timing circuits, or other circuits; 854232 - Electronic integrated circuits; memories.

Columns: value_usd = primaryValue (US imports: customs value; exports: FOB), qty in
qty_unit ('u' = number of items, 'kg', 'N/A'), net_weight_kg. usd_per_unit only where
qty_unit == 'u' and qty > 0; usd_per_kg where net weight > 0.

Caveats:
- Unit values are mix-sensitive proxies, not prices: one HS6 code spans cheap NOR flash
  to HBM stacks. Korea and Japan report weight, not item counts, so only $/kg exists there.
- qty = 0 with qty_unit 'N/A' means quantity not reported that month, not zero trade.
- Finished PC parts may sit outside 8542.32: memory modules can be classed as computer
  parts (8473.30) or as memories (the EU CN label for 8542.32.90 names "modules"), and
  graphics cards / SSDs as 8473.30 / 8471.70 / 8471.80 -- classification practice varies
  by country and was not verified here.
- US 854232 item counts have breaks (e.g. 2023-2024 counts several times higher than
  before/after, and qty missing in some months such as 2022 and 2026-07), so US memory
  usd_per_unit is not a consistent series; compare value_usd instead.
- Reporting lags differ (max date per reporter in the CSV); recent periods are revised,
  so the last 12 periods are re-fetched when older than 7 days.
- Coverage depends on how far a quota-limited run got: periods are filled newest-first,
  USA and KOR before JPN and MYS. Check min(date) per reporter; re-run to extend.
