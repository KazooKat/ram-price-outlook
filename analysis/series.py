"""Load the monthly series the analysis uses, from raw and processed files.

Every loader returns a pandas Series indexed by month-start Timestamp, named
after the series. Keep all source-specific cleaning here so the analysis
modules only see tidy series.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"


def _month(s) -> pd.DatetimeIndex:
    return pd.to_datetime(pd.Series(s).astype(str).str[:7] + "-01").values


def _series(df: pd.DataFrame, date_col: str, val_col: str, name: str) -> pd.Series:
    s = pd.Series(df[val_col].values, index=pd.DatetimeIndex(_month(df[date_col])), name=name)
    s = s.groupby(level=0).median().sort_index()
    return s.dropna()


# --- DRAM chip prices (DRAMeXchange / TrendForce public tables, via Wayback) ---

@lru_cache
def _spot_items() -> pd.DataFrame:
    return pd.read_csv(PROC / "dram_spot_items.csv")


def spot_chip(pattern: str, name: str, exclude: str = "ett") -> pd.Series:
    """Median monthly spot price across item keys matching a regex (same chip, different bins)."""
    d = _spot_items()
    m = d[d["key"].str.contains(pattern, regex=True) & ~d["key"].str.contains(exclude)]
    return _series(m, "month", "price", name)


def ddr4_8gb_spot() -> pd.Series:
    return spot_chip(r"^ddr48g.*1gx8", "DDR4 8Gb spot ($/chip)")


def ddr5_16gb_spot() -> pd.Series:
    return spot_chip(r"^ddr516g", "DDR5 16Gb spot ($/chip)")


def spot_index() -> pd.Series:
    d = pd.read_csv(PROC / "dram_spot_index.csv")
    return _series(d, "month", "index", "DRAM spot chain index (2019-01=100)")


def nand_index() -> pd.Series:
    d = pd.read_csv(PROC / "nand_spot_index.csv")
    return _series(d, "month", "index", "NAND spot chain index (2019-01=100)")


def contract_index() -> pd.Series:
    d = pd.read_csv(PROC / "dram_contract_index.csv")
    return _series(d, "month", "index", "DRAM contract chain index")


@lru_cache
def _dx() -> pd.DataFrame:
    """DRAMeXchange monthly medians per item (built by dram_index.py)."""
    return pd.read_csv(PROC / "dramexchange_monthly.csv")


def dx_item(section: str, item_regex: str, name: str) -> pd.Series:
    d = _dx()
    m = d[(d.section == section) & d["item"].str.contains(item_regex, regex=True, flags=re.I)]
    return _series(m, "month", "p", name)


def ddr5_sodimm_contract() -> pd.Series:
    return dx_item("dram_contract", r"^DDR5 8GB SO-DIMM", "DDR5 8GB SO-DIMM contract ($/module)")


def ddr4_8gb_contract() -> pd.Series:
    return dx_item("dram_contract", r"^DDR4 8Gb 1Gx8", "DDR4 8Gb contract ($/chip)")


def ddr5_udimm_module_spot() -> pd.Series:
    return dx_item("module_spot", r"^DDR5 UDIMM 16GB", "DDR5 16GB UDIMM module spot ($)")


def gddr6_spot() -> pd.Series:
    return dx_item("gddr_spot", r"^GDDR6 8Gb", "GDDR6 8Gb spot ($/chip)")


def nand_wafer_512() -> pd.Series:
    return dx_item("wafer_spot", r"^512Gb TLC", "NAND 512Gb TLC wafer spot ($/die-equiv)")


def ssd_oem_contract() -> pd.Series:
    d = _dx()
    m = d[d.section.str.contains("oem_ssd", na=False) & d["item"].str.contains("1TB", na=False)
          & d["item"].str.contains("PCIe", case=False, na=False)]
    return _series(m, "month", "p", "OEM 1TB PCIe SSD contract ($)")


# --- Official indices ---

@lru_cache
def _boj() -> pd.DataFrame:
    return pd.read_csv(RAW / "official_boj" / "boj_cgpi.csv")


def boj(series_id: str, name: str) -> pd.Series:
    d = _boj()
    return _series(d[d.series_id == series_id], "date", "value", name)


def boj_memory_import() -> pd.Series:
    """Japan import price index, MOS memory ICs, contract currency (mostly USD). CY2020=100."""
    return boj("PRCG20_2500850005", "Japan import price: memory ICs (2020=100)")


def boj_memory_export() -> pd.Series:
    return boj("PRCG20_2300550006", "Japan export price: memory ICs (2020=100)")


@lru_cache
def _fred() -> pd.DataFrame:
    return pd.read_csv(RAW / "official_fred" / "fred_series.csv")


def fred(series_id: str, name: str | None = None) -> pd.Series:
    d = _fred()
    d = d[d.series_id == series_id]
    return _series(d, "date", "value", name or series_id)


# --- Retail ---

def mccallum_memory() -> pd.Series:
    d = pd.read_csv(RAW / "mccallum" / "mccallum_prices.csv")
    d = d[d.series == "memory"]
    # cheapest listing per month = the series McCallum tracks
    s = pd.Series(d["price"].values, index=pd.DatetimeIndex(_month(d["date"])))
    return s.groupby(level=0).min().sort_index().rename("Retail memory $/MB (McCallum)")


def mccallum(kind: str) -> pd.Series:
    d = pd.read_csv(RAW / "mccallum" / "mccallum_prices.csv")
    d = d[d.series == kind]
    s = pd.Series(d["price"].values, index=pd.DatetimeIndex(_month(d["date"])))
    return s.groupby(level=0).min().sort_index().rename(f"Retail {kind} $/MB (McCallum)")


@lru_cache
def _deals() -> pd.DataFrame:
    return pd.read_csv(PROC / "deals_monthly.csv")


def deals(series: str, stat: str = "median") -> pd.Series:
    d = _deals()
    return _series(d[d.series == series], "month", stat, series)


def deals_quarterly(series: str) -> pd.DataFrame:
    """Pool deal posts by quarter (monthly n is thin in 2026). Uses the parsed rows."""
    p = pd.read_csv(PROC / "deals_parsed.csv")
    sel = {
        "ram_ddr5_32gb_kit_usd": (p.category == "RAM") & (p.ddr == "DDR5") & (p.capacity_gb == 32)
        & (p.form == "dimm"),
        "ram_ddr5_usd_per_gb": (p.category == "RAM") & (p.ddr == "DDR5") & (p.form == "dimm"),
        "ssd_nvme_usd_per_tb": (p.category == "SSD") & (p.interface == "NVMe")
        & p.capacity_gb.between(900, 4200) & (p.enterprise != True),
    }[series]
    col = {"ram_ddr5_32gb_kit_usd": "price", "ram_ddr5_usd_per_gb": "usd_per_gb",
           "ssd_nvme_usd_per_tb": "usd_per_tb"}[series]
    x = p[sel].copy()
    x["q"] = pd.PeriodIndex(x["month"], freq="Q")
    return x.groupby("q")[col].agg(["median", "size"]).rename(columns={"size": "n"})


def basket(product_regex: str) -> pd.Series:
    d = pd.read_csv(RAW / "pcpartpicker_products" / "basket_prices.csv")
    d = d[d["product"].str.contains(product_regex, regex=True) & d["price"].notna()]
    return _series(d, "date", "price", product_regex)


def basket_ddr5_32gb() -> pd.Series:
    """Mean of the three 2x16GB DDR5-6000 CL30 kits, per month (each kit's lowest in-stock price)."""
    d = pd.read_csv(RAW / "pcpartpicker_products" / "basket_prices.csv")
    d = d[d["product"].str.contains(r"32GB \(2x16GB\) DDR5-6000") & d["price"].notna()]
    d["m"] = _month(d["date"])
    per_kit = d.groupby(["m", "product"])["price"].median().unstack()
    return per_kit.mean(axis=1).rename("2x16GB DDR5-6000 kit, lowest in-stock (PCPartPicker)")


# --- Company data ---

def taiwan_revenue(company: str) -> pd.Series:
    d = pd.read_csv(RAW / "taiwan_monthly_revenue" / "monthly_revenue.csv")
    d = d[d.company == company]
    return _series(d, "period", "value", f"{company} monthly revenue (TWD k)")


def sec_quarterly(company: str, metric: str) -> pd.Series:
    d = pd.read_csv(RAW / "sec_companyfacts" / "quarterly_financials.csv")
    d = d[(d.company == company) & (d.metric == metric)]
    d = d.sort_values("filed").drop_duplicates("period_end", keep="last")
    return _series(d, "period_end", "value", f"{company} {metric}")


def micron_gross_margin() -> pd.Series:
    """Quarterly GAAP gross margin %, press releases (includes the latest quarter before the 10-K)."""
    d = pd.read_csv(RAW / "micron_ir" / "press_release_results.csv")
    return d


def log_ratio(a: float, b: float) -> float:
    return float(np.log(a / b))
