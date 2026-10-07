"""Chained DRAM price indices from archived DRAMeXchange tables.

DRAMeXchange quotes individual chips (e.g. "DDR4 8Gb (1Gx8) 3200"). Chips are
replaced as generations change, so a single item never covers more than a few
years. We build a matched-model chain index: the change between two observed
months is the median log change across items quoted in both, and the index is
the running product of those changes. Gaps in the archive (months with no
capture) are bridged by linking the nearest observed months.

We also compute $/Gb per item so the long-run level is visible, and a
generation-specific series for DDR4 8Gb and DDR5 16Gb.

Outputs (data/processed/):
  dram_spot_index.csv       month, index (2019-01 = 100), n_items, $/Gb median
  dram_contract_index.csv   same for contract prices (2007+)
  dram_spot_items.csv       month, item, generation, density_gb, price, usd_per_gb
  nand_spot_index.csv       NAND chip spot (2007-2018) chained into TLC wafer spot (2019+)
  dramexchange_monthly.csv  monthly median per item, all sections (the published form of the raw captures)
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "dramexchange" / "dramexchange_prices.csv"
OUT = ROOT / "data" / "processed"

GEN_RE = re.compile(r"\b(SDRAM|RDRAM|DDR5|DDR4|DDR3|DDR2|DDR)\b", re.I)
# chip density: "8Gb", "16G (", "256Mb", "1Gb"; module sizes ("8GB SO-DIMM") are capital B
DENS_RE = re.compile(r"(\d+)\s*(G|M)b?\b(?!\s*(?:SO-DIMM|U-DIMM|DIMM|RIMM))")


def parse_item(item: str):
    g = GEN_RE.search(item)
    gen = g.group(1).upper() if g else None
    # modules quoted in GB are not chip prices; contract "based on 8GB module" rows are chips
    if re.search(r"\d+\s*GB\s*(SO-DIMM|U-DIMM|DIMM|RIMM)", item) or "RIMM" in item:
        return gen, None
    m = DENS_RE.search(item)
    if not m:
        return gen, None
    n, unit = int(m.group(1)), m.group(2).upper()
    gb = n if unit == "G" else n / 1024
    return gen, gb


def item_key(item: str) -> str:
    """Collapse cosmetic name variants ("1333 MHz" vs "1333MHz", "1G*8" vs "1Gx8")."""
    k = re.sub(r"\s+", "", item).lower()
    k = k.replace("*", "x").replace("mbps", "").replace("mhz", "")
    return k


def drop_stale(d: pd.DataFrame, min_run: int = 3) -> pd.DataFrame:
    """Drop archive captures that repeat a frozen page.

    Spot prices move daily. When an item's price is identical across 3+
    consecutive monthly captures, the archived page was not updating (seen on
    trendforce.com/price from 2012-11 to 2013-09). Keep the first value of
    each run and drop the repeats.
    """
    d = d.sort_values(["key", "date"]).copy()
    same = d.groupby("key")["p"].transform(lambda s: s.ne(s.shift()).cumsum())
    run_len = d.groupby(["key", same])["p"].transform("size")
    first_in_run = ~d.duplicated(subset=["key"]) | d["p"].ne(d.groupby("key")["p"].shift())
    stale = (run_len >= min_run) & ~first_in_run
    return d[~stale]


MONTHLY = OUT / "dramexchange_monthly.csv"


def build_monthly() -> None:
    """Monthly median per item from the raw captures.

    The raw daily captures are not redistributed; this monthly file is, and
    everything downstream reads it.
    """
    d = pd.read_csv(RAW)
    # use the published average; fall back to the high/low midpoint
    mid = (d["high"] + d["low"]) / 2
    d["p"] = d["price"].where(d["price"].notna(), mid)
    d = d[d["p"] > 0].copy()
    d["key"] = d["item"].map(item_key)
    d["month"] = d["date"].str[:7]
    m = (d.sort_values("date").groupby(["section", "key", "month"], as_index=False)
           .agg(p=("p", "median"), item=("item", "last"), date=("date", "last"), n=("p", "size")))
    m.to_csv(MONTHLY, index=False)
    print(f"dramexchange monthly: {len(m)} item-months")


def monthly_items(section: str | list[str], keep=None) -> pd.DataFrame:
    sections = [section] if isinstance(section, str) else section
    d = pd.read_csv(MONTHLY)
    d = d[d.section.isin(sections)].copy()
    if keep is not None:
        d = d[d.apply(keep, axis=1)]
    if section in ("dram_spot", ["flash_spot", "wafer_spot"]):
        before = len(d)
        d = drop_stale(d)
        print(f"{sections}: dropped {before - len(d)} stale item-months")
    parsed = d["item"].map(parse_item)
    d["generation"] = [p[0] for p in parsed]
    d["density_gb"] = [p[1] for p in parsed]
    m = d.rename(columns={"p": "price", "n": "n_obs"})[
        ["month", "key", "item", "price", "generation", "density_gb", "n_obs"]]
    m["usd_per_gb"] = m["price"] / m["density_gb"]
    return m


def chain_index(m: pd.DataFrame, base_month: str) -> pd.DataFrame:
    months = sorted(m["month"].unique())
    wide = m.pivot_table(index="month", columns="key", values="price").reindex(months)
    level = [0.0]
    n_link = [np.nan]
    for prev, cur in zip(months[:-1], months[1:]):
        both = wide.loc[[prev, cur]].dropna(axis=1)
        if both.shape[1] == 0:
            # no overlap: carry level forward and flag
            level.append(level[-1])
            n_link.append(0)
            continue
        r = np.log(both.loc[cur] / both.loc[prev])
        level.append(level[-1] + float(np.median(r)))
        n_link.append(both.shape[1])
    idx = pd.DataFrame({"month": months, "log_level": level, "n_link_items": n_link})
    base = idx.loc[idx.month == base_month, "log_level"]
    if base.empty:
        raise ValueError(f"base month {base_month} not observed")
    idx["index"] = 100 * np.exp(idx["log_level"] - base.iloc[0])
    per_gb = m.dropna(subset=["usd_per_gb"]).groupby("month")["usd_per_gb"].agg(["median", "min", "size"])
    per_gb.columns = ["usd_per_gb_median", "usd_per_gb_min", "n_items"]
    return idx.merge(per_gb, on="month", how="left")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if RAW.exists():
        build_monthly()
    else:
        print("raw DRAMeXchange captures not present; using", MONTHLY.name)
    spot = monthly_items("dram_spot")
    spot.to_csv(OUT / "dram_spot_items.csv", index=False)
    si = chain_index(spot, "2019-01")
    si.to_csv(OUT / "dram_spot_index.csv", index=False)
    print("spot index:", si.month.min(), "->", si.month.max(), len(si), "months;",
          "zero-overlap links:", int((si.n_link_items == 0).sum()))

    con = monthly_items("dram_contract")
    con = con[con.month >= "2006-11"]  # earlier contract rows have no average
    ci = chain_index(con, "2019-02")
    ci.to_csv(OUT / "dram_contract_index.csv", index=False)
    print("contract index:", ci.month.min(), "->", ci.month.max(), len(ci), "months;",
          "zero-overlap links:", int((ci.n_link_items == 0).sum()))

    # NAND: chip spot through 2018, TLC wafer spot from 2019 (the 2019+ flash_spot
    # items are legacy MLC/SLC parts used in cards and embedded devices, not SSDs)
    def nand_keep(r):
        if r.section == "wafer_spot":
            return True
        return r.date < "2019-02"
    nand = monthly_items(["flash_spot", "wafer_spot"], keep=nand_keep)
    ni = chain_index(nand, "2019-01")
    ni.to_csv(OUT / "nand_spot_index.csv", index=False)
    print("nand spot index:", ni.month.min(), "->", ni.month.max(), len(ni), "months;",
          "zero-overlap links:", int((ni.n_link_items == 0).sum()))


if __name__ == "__main__":
    main()
