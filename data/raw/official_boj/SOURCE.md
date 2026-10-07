# Bank of Japan CGPI (2020 base): memory IC, IC, storage and PC price indices

Fetched: 2026-10-06

Sources:
- https://www.stat-search.boj.or.jp/api/v1/getDataCode?format=csv&lang=en&db=PR01&startDate=200001&code=<SERIES_CODES>
- https://www.stat-search.boj.or.jp/api/v1/getMetadata?format=csv&lang=en&db=PR01

Keyless BOJ Time-Series Data Search API. All series are monthly, CY2020 average = 100,
not seasonally adjusted. Columns: date (first of month), series_id (BOJ code), value,
name, category (index type), unit, last_update (BOJ release stamp).

Index types:
- Import / Export Price Index (contract currency basis): prices in the invoicing currency
  (mostly USD for chips) -- best proxy for global contract prices, free of JPY moves.
- Import / Export Price Index (yen basis): same goods converted to JPY.
- Producer Price Index: Japanese domestic producer prices.

Caveats: commodity-level series start between 2000 and 2015 depending on the item;
class/subgroup-level series start 2020. Recent months are preliminary and revised at
the next release. "MOS memory integrated circuits" is a single BOJ commodity covering
memory chips generally (no DRAM vs NAND split); its weight is in the BOJ metadata.
