"""EU imports by CN8 product from Eurostat Comext (keyless API): DRAM, flash, other
memories, memory modules, processors, SSD/storage units and computer parts.

CN8 is finer than HS6: it separates DRAM (>512 Mbit and <=512 Mbit), flash E2PROM,
and "stack D-RAMs and modules" (memory modules), with supplementary quantities
(item counts) for most codes, so value / supplementary quantity gives a monthly
EUR-per-item unit value for each.

Output (data/raw/official_eurostat_comext/):
  comext_eu_imports.csv  date, reporter, partner, product, value_eur, supp_qty,
                         qty_100kg, eur_per_item, eur_per_kg
  comext_products.csv    product, product_desc (Eurostat labels)
"""
from __future__ import annotations

import itertools
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetch._common import get, raw_dir, write_source_note  # noqa: E402

SOURCE = "official_eurostat_comext"
API = "https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/DS-045409"
SINCE = "2013-01"
REPORTER = "EU27_2020"
# Extra-EU total plus the main Asian / US origins
PARTNERS = ["EXT_EU27_2020", "KR", "TW", "CN", "JP", "MY", "US"]
PRODUCTS = [
    # memories (HS 854232 and CN8 children)
    "854232", "85423210", "85423231", "85423239", "85423245", "85423255",
    "85423261", "85423269", "85423275", "85423290",
    # processors and controllers (HS 854231)
    "854231", "85423111", "85423119", "85423190",
    # solid-state storage (HS 852351) and ADP storage units (HS 847170)
    "852351", "85235110", "85235190",
    "847170", "84717020", "84717030", "84717050", "84717070", "84717080", "84717098",
    # other ADP units, parts and electronic assemblies (graphics cards, boards, modules)
    "847180", "847330", "84733020", "84733080",
]
INDICATORS = {"VALUE_IN_EUROS": "value_eur", "SUPPLEMENTARY_QUANTITY": "supp_qty",
              "QUANTITY_IN_100KG": "qty_100kg"}


def _jsonstat_to_frame(j: dict) -> pd.DataFrame:
    dims = j["id"]
    cats = [sorted(j["dimension"][d]["category"]["index"].items(), key=lambda kv: kv[1]) for d in dims]
    values = j.get("value") or {}
    rows = []
    for flat, combo in enumerate(itertools.product(*cats)):
        v = values.get(str(flat))
        if v is not None:
            rows.append({**{d: c[0] for d, c in zip(dims, combo)}, "value": v})
    return pd.DataFrame(rows)


def main() -> None:
    out = raw_dir(SOURCE)
    frames, labels = [], {}
    for partner in PARTNERS:
        params = [("format", "JSON"), ("lang", "en"), ("freq", "M"), ("reporter", REPORTER),
                  ("partner", partner), ("flow", "1"), ("sinceTimePeriod", SINCE)]
        params += [("product", p) for p in PRODUCTS] + [("indicators", i) for i in INDICATORS]
        j = get(API, params=params, timeout=180).json()
        if "error" in j:
            raise RuntimeError(f"Comext error for partner {partner}: {j['error']}")
        labels.update(j["dimension"]["product"]["category"]["label"])
        df = _jsonstat_to_frame(j)
        print(f"{partner}: {len(df)} non-empty cells, updated {j.get('updated')}")
        frames.append(df)
        time.sleep(1)

    long = pd.concat(frames, ignore_index=True)
    wide = (long.pivot_table(index=["time", "reporter", "partner", "product"],
                             columns="indicators", values="value", aggfunc="first")
            .rename(columns=INDICATORS).reset_index())
    for col in INDICATORS.values():
        if col not in wide:
            wide[col] = pd.NA
    wide["date"] = pd.to_datetime(wide["time"], format="%Y-%m").dt.strftime("%Y-%m-%d")
    wide["eur_per_item"] = (wide["value_eur"] / wide["supp_qty"]).where(wide["supp_qty"] > 0)
    wide["eur_per_kg"] = (wide["value_eur"] / (wide["qty_100kg"] * 100)).where(wide["qty_100kg"] > 0)
    wide = wide[["date", "reporter", "partner", "product", "value_eur",
                 "supp_qty", "qty_100kg", "eur_per_item", "eur_per_kg"]]
    wide = wide.sort_values(["partner", "product", "date"]).reset_index(drop=True)
    wide.to_csv(out / "comext_eu_imports.csv", index=False)
    (pd.DataFrame(sorted(labels.items()), columns=["product", "product_desc"])
     .to_csv(out / "comext_products.csv", index=False))
    print(f"wrote {len(wide)} rows; dates {wide['date'].min()}..{wide['date'].max()}")

    write_source_note(
        SOURCE,
        title="Eurostat Comext: EU27 imports by CN8 (memory, processors, storage, computer parts)",
        urls=[API + "?format=JSON&lang=en&freq=M&reporter=EU27_2020&partner=<P>&flow=1"
                    "&product=<CN8>...&indicators=VALUE_IN_EUROS&indicators=SUPPLEMENTARY_QUANTITY"
                    f"&indicators=QUANTITY_IN_100KG&sinceTimePeriod={SINCE}"],
        notes=f"""
Keyless Eurostat Comext dissemination API, dataset DS-045409 (EU trade since 1988 by
HS2-4-6 and CN8), monthly, reporter EU27_2020, flow 1 = imports.
Partners: {', '.join(PARTNERS)} (EXT_EU27_2020 = all extra-EU origins).
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
""",
    )


if __name__ == "__main__":
    main()
