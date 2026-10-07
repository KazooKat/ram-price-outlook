"""Our World in Data grapher series on long-run memory / storage prices.

1. historical-cost-of-computer-memory-and-storage: McCallum's data, annual, in
   constant 2020 US$ per TB, but as a *running minimum* ("cheapest price recorded
   until that year"), so it cannot show price spikes. Useful only as an
   inflation-adjusted envelope.
2. costs-of-66-different-technologies-over-time, entities DRAM / Hard disk drive /
   Transistor: Santa Fe Institute Performance Curve Database (Nagy et al. 2013),
   annual, not a running minimum, so it does show e.g. the 1988 DRAM spike.

Output: data/raw/owid/*.csv (tidy: date, series, price, currency, unit, url_of_snapshot)
"""
from __future__ import annotations

import io
import json
import time

import pandas as pd

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from fetch._common import get, raw_dir, write_source_note  # noqa: E402

SOURCE = "owid"
BASE = "https://ourworldindata.org/grapher/"
CSV_Q = "?v=1&csvType=full&useColumnShortNames=false"


def _fetch(slug: str) -> tuple[pd.DataFrame, dict]:
    df = pd.read_csv(io.StringIO(get(BASE + slug + ".csv" + CSV_Q).text))
    time.sleep(1)
    meta = json.loads(get(BASE + slug + ".metadata.json" + CSV_Q).text)
    time.sleep(1)
    return df, meta


def main() -> None:
    d = raw_dir(SOURCE)
    out = []

    slug = "historical-cost-of-computer-memory-and-storage"
    df, meta = _fetch(slug)
    (d / f"{slug}.metadata.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    long = df.melt(id_vars=["Entity", "Code", "Year"], var_name="series", value_name="price").dropna()
    for r in long.itertuples():
        out.append({"date": f"{r.Year}-12-31", "dataset": slug, "series": r.series.lower(),
                    "price": r.price, "currency": "USD (constant 2020)",
                    "unit": "US$ per TB, running minimum to date", "url_of_snapshot": BASE + slug})

    slug = "costs-of-66-different-technologies-over-time"
    df, meta = _fetch(slug)
    keep = ["DRAM", "Hard disk drive", "Transistor"]
    cols = meta.get("columns", {})
    unit = next(iter(cols.values()), {}).get("unit", "") if cols else ""
    (d / f"{slug}.metadata.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    val = [c for c in df.columns if c not in ("Entity", "Code", "Year")][0]
    for _, r in df[df.Entity.isin(keep)].iterrows():
        out.append({"date": f"{r.Year}-12-31", "dataset": slug, "series": r.Entity.lower(),
                    "price": r[val],
                    "currency": "USD (per PCDB; see metadata)",
                    "unit": unit or "technology-specific unit (see metadata json)",
                    "url_of_snapshot": BASE + slug})

    res = pd.DataFrame(out).sort_values(["dataset", "series", "date"])
    res.to_csv(d / "owid_memory_storage.csv", index=False)
    for (ds, s), g in res.groupby(["dataset", "series"]):
        print(f"{ds[:30]:30s} {s:16s} n={len(g):3d} {g.date.min()[:4]}..{g.date.max()[:4]} "
              f"{g.price.min():.4g}..{g.price.max():.4g}")
    write_source_note(
        SOURCE,
        title="Our World in Data - historical memory/storage prices",
        urls=[BASE + "historical-cost-of-computer-memory-and-storage",
              BASE + "costs-of-66-different-technologies-over-time"],
        notes="""
historical-cost-of-computer-memory-and-storage: derived from McCallum (ends 2023),
deflated to constant 2020 US$ with US CPI, and expressed as the cheapest price seen
up to each year (a running minimum). It therefore never rises and cannot be used to
date cycle peaks; use data/raw/mccallum instead for cycles.

costs-of-66-different-technologies-over-time (DRAM, Hard disk drive, Transistor):
Santa Fe Institute Performance Curve Database (Nagy, Farmer, Bui, Trancik 2013).
Annual. DRAM runs 1971-2007. Units are as stored in OWID metadata json alongside.
""",
    )


if __name__ == "__main__":
    main()
