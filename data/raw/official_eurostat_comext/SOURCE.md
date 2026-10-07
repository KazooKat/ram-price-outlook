# Eurostat Comext: EU27 imports by CN8 (memory, processors, storage, computer parts)

Fetched: 2026-10-06

Sources:
- https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/DS-045409?format=JSON&lang=en&freq=M&reporter=EU27_2020&partner=<P>&flow=1&product=<CN8>...&indicators=VALUE_IN_EUROS&indicators=SUPPLEMENTARY_QUANTITY&indicators=QUANTITY_IN_100KG&sinceTimePeriod=2013-01

Keyless Eurostat Comext dissemination API, dataset DS-045409 (EU trade since 1988 by
HS2-4-6 and CN8), monthly, reporter EU27_2020, flow 1 = imports.
Partners: EXT_EU27_2020, KR, TW, CN, JP, MY, US (EXT_EU27_2020 = all extra-EU origins).
Products: HS6 totals and CN8 subheadings; labels in comext_products.csv.

Columns: value_eur (EUR, nominal), supp_qty (supplementary quantity in the CN
supplementary unit for that code -- item counts for the 8542 memory codes per the CN
nomenclature; not every code has one), qty_100kg (net mass in 100 kg),
eur_per_item = value_eur / supp_qty, eur_per_kg = value_eur / (qty_100kg * 100).

Caveats:
- Values in EUR: convert with a EUR/USD series before comparing with USD data.
- CN8 codes are revised in some years; a code can start or stop mid-history.
- Unit values are mix-sensitive (capacity per chip rises over time) -- they are price
  proxies, not like-for-like prices. Small partner/product cells are noisy.
- Recent months are provisional and revised; confidential trade can be suppressed.
- Products absent from a partner's rows had no reported trade (empty cells are dropped).
