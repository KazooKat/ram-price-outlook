# SEC 10-Q/10-K XBRL instances - revenue by product / segment

Fetched: 2026-10-06

Sources:
- https://data.sec.gov/submissions/CIK0000723125.json
- https://data.sec.gov/submissions/CIK0001045810.json
- https://data.sec.gov/submissions/CIK0000106040.json
- https://data.sec.gov/submissions/CIK0002023554.json
- https://www.sec.gov/Archives/edgar/data/<cik>/<accession>/<instance>.xml

Dimensional (segment / product) revenue from SEC 10-Q and 10-K XBRL instances.

companyfacts omits dimensional facts, so this script downloads the XBRL instance of
every 10-Q/10-K and keeps revenue facts qualified by a product or segment axis:
- Micron (MU): revenue by technology (DRAM / NAND / Other, srt:ProductOrServiceAxis)
  and by business unit (StatementBusinessSegmentsAxis; units were reorganised in
  FY2023 and FY2026, so member names change over time).
- Nvidia (NVDA): revenue by market platform (Data Center, Gaming, ...) and segment.
- Western Digital (WDC) / Sandisk (SNDK): revenue by end market / product.

Output: data/raw/sec_segments/segment_revenue.csv - one row per company x axis x
member x fiscal quarter. Discrete quarters for Q4 (10-K reports only full year) are
derived as FY - 9M YTD, flagged derivation="ytd_diff". Per period the most recently
filed value wins (restatements/recasts replace originals).

Caveats
- Member names are the filer's own (e.g. mu:DRAMProductsMember, nvda:DataCenterMember);
  business-unit structures change (Micron FY2023 and FY2026 reorganisations), and recast
  history appears only as far back as the recasting filing presented it.
- Only single-axis facts are kept (plus ConsolidationItemsAxis), so cross-tabs such as
  segment x geography are excluded.
- The newest quarter appears only after its 10-Q/10-K is filed; Micron's FQ4 FY2026
  10-K was not yet filed on the fetch date (see data/raw/micron_ir for FQ4 figures from
  the prepared remarks).
