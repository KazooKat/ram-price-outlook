"""SSD, GPU and CPU: how far each is from normal, and when it gets back.

SSD   same method as RAM (forecast.py) with NAND fall rates.
GPU   how much of the price rise is memory cost vs everything else.
CPU/GPU  price as a share of launch price by age, compared with how products
      normally age (deal prices before the spike), so an older chip getting
      cheaper is not mistaken for a market returning to normal.

Outputs (data/processed/):
  ssd_forecast.csv, gpu_memory_cost.csv, aging_reference.csv, aging_now.csv
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

import series as S
from forecast import ASOF, MODERN_FROM, load_cycles

OUT = S.PROC
PRE_SPIKE = ("2024-01-01", "2025-06-01")
# GPU retail was distorted by the 2020-22 crypto/pandemic shortage; exclude it from "normal aging"
GPU_SHORTAGE = ("2020-09-01", "2022-06-30")
NOW_WINDOW = ("2026-06-01", "2026-10-31")


# --- SSD ---

def ssd_forecast(bias_m: int) -> pd.DataFrame:
    cyc = load_cycles()
    nand = cyc[cyc.series.isin(["nand_spot_chain", "nand_512_wafer", "retail_ssd_mccallum"])
               & (cyc.peak >= MODERN_FROM)].dropna(subset=["fall_rate"])
    fq = np.quantile(nand.fall_rate, [0.25, 0.5, 0.75])

    ratios = {}
    for name in ["990 Pro", "SN850X"]:
        s = S.basket(name)
        pre = s[PRE_SPIKE[0]:PRE_SPIKE[1]].mean()
        now = s[s.index >= "2026-06-01"].mean()
        ratios[name] = now / pre
    dq = S.deals_quarterly("ssd_nvme_usd_per_tb")
    ratios["deals NVMe $/TB"] = dq.loc["2026Q2":"2026Q3", "median"].mean() / dq.loc["2024Q1":"2025Q2", "median"].median()
    brand_ratio = float(np.mean([ratios["990 Pro"], ratios["SN850X"]]))

    # 512Gb TLC wafer spot peaked in 2026-03; OEM SSD contract prices were still rising in 2026-08.
    # Fast: retail has peaked. Base: one more quarter, as contract momentum fades. Slow: DRAM base-case peak + 3 months.
    peaks = {"fast": ASOF + pd.DateOffset(months=1), "base": pd.Timestamp("2027-01-01"),
             "slow": pd.Timestamp("2027-05-01")}
    rates = {"fast": fq[2], "base": fq[1], "slow": fq[0]}
    rows = []
    for sc in ["fast", "base", "slow"]:
        r = dict(scenario=sc, peak=peaks[sc].date(), fall_rate=rates[sc], ratio_now_brand=brand_ratio,
                 ratio_now_deals=ratios["deals NVMe $/TB"])
        for tgt in (1.5, 1.2, 1.0):
            m = max(np.log(brand_ratio / tgt), 0) / rates[sc]
            r[f"date_{tgt}x_adj"] = (peaks[sc] + pd.DateOffset(months=int(round(m)) + bias_m)).date()
        rows.append(r)
    out = pd.DataFrame(rows)
    out.attrs["ratios"] = ratios
    out.attrs["fall_rates"] = nand[["series", "peak", "rise_x", "fall_rate"]]
    return out


# --- GPU memory cost ---

def gpu_memory_cost() -> pd.DataFrame:
    """Extra memory cost per card from the GDDR6 8Gb spot price (1 GB per chip).

    No public GDDR7 price series exists, so GDDR6 stands in for GDDR7 cards; this
    understates GDDR7 cards if GDDR7 rose more.
    """
    g6 = S.gddr6_spot()
    pre = g6[PRE_SPIKE[0]:PRE_SPIKE[1]].mean()
    now = g6[g6.index >= "2026-06-01"].mean()
    per_gb = now - pre
    deals = pd.read_csv(OUT / "deals_monthly.csv")
    cards = {"RTX 5090": 32, "RTX 5080": 16, "RTX 5070 Ti": 16, "RTX 5070": 12,
             "RX 9070 XT": 16, "RX 9070": 16, "RX 9060 XT 16GB": 16, "Arc B580": 12}
    p = pd.read_csv(OUT / "deals_parsed.csv")
    rows = []
    for card, gb in cards.items():
        x = p[(p.category == "GPU") & (p.model == card)]
        before = x[(x.month >= "2025-04") & (x.month <= "2025-08")].price
        after = x[(x.month >= NOW_WINDOW[0][:7]) & (x.month <= NOW_WINDOW[1][:7])].price
        rows.append(dict(card=card, vram_gb=gb, deal_before=before.median(), n_before=len(before),
                         deal_now=after.median(), n_now=len(after),
                         change=after.median() - before.median(),
                         memory_cost_change=per_gb * gb))
    out = pd.DataFrame(rows)
    out["memory_share_of_change"] = out.memory_cost_change / out.change
    out.attrs["gddr6_pre"] = pre
    out.attrs["gddr6_now"] = now
    return out


# --- Aging curves ---

def _norm(m: str) -> str:
    m = str(m).lower()
    for w in ("geforce ", "radeon ", "ryzen 9 ", "ryzen 7 ", "ryzen 5 ", "ryzen ", "core ultra ", "core i9-",
              "core i7-", "core i5-", "core ", "intel arc ", "arc "):
        m = m.replace(w, "")
    return re.sub(r"\s+", "", m)


def launch_table(kind: str) -> pd.DataFrame:
    f = S.RAW / "perf_wikipedia" / ("cpu_desktop.csv" if kind == "CPU" else "gpu_desktop.csv")
    d = pd.read_csv(f)
    d = d.dropna(subset=["launch_price_usd", "release_date"])
    d["key"] = d.model.map(_norm)
    d = d.sort_values("release_date").drop_duplicates("key", keep="first")
    return d[["key", "model", "release_date", "launch_price_usd"]]


def aging(kind: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    p = pd.read_csv(OUT / "deals_parsed.csv")
    p = p[p.category == kind].copy()
    p["key"] = p.model.map(_norm)
    lt = launch_table(kind)
    x = p.merge(lt, on="key", how="inner", suffixes=("", "_launch"))
    x["age_m"] = ((pd.to_datetime(x.month + "-01") - pd.to_datetime(x.release_date)).dt.days / 30.44).round()
    x = x[x.age_m >= 0]
    x["ratio"] = x.price / x.launch_price_usd
    x["age_bin"] = (x.age_m // 6 * 6).astype(int)
    ref = x[x.month < "2025-07"]
    if kind == "GPU":
        ref = ref[~ref.month.between(GPU_SHORTAGE[0][:7], GPU_SHORTAGE[1][:7])]
    ref_curve = ref.groupby("age_bin").ratio.agg(["median", "size"]).rename(columns={"median": "ref_ratio", "size": "ref_n"})
    now = x[x.month.between(NOW_WINDOW[0][:7], NOW_WINDOW[1][:7])].merge(ref_curve, on="age_bin", how="left")
    # thin reference bins are noise; the 5800X3D was re-released in 2026 at a new price
    now = now[(now.ref_n >= 20) & (now.model != "Ryzen 5800X3D")]
    # each post vs the normal ratio for its own age, then one row per model
    now["rel"] = np.log(now.ratio / now.ref_ratio)
    now = (now.groupby("model").agg(rel=("rel", "median"), n=("rel", "size"), age_m=("age_m", "median"),
                                    launch=("launch_price_usd", "first"), price=("price", "median"),
                                    ratio=("ratio", "median"))
           .reset_index())
    now["vs_normal_pct"] = 100 * (np.exp(now.rel) - 1)
    return ref_curve.reset_index().assign(kind=kind), now.assign(kind=kind)


def main():
    bt = pd.read_csv(OUT / "forecast_dates.csv")
    bias = int(bt.backtest_bias_months.iloc[0])

    ssd = ssd_forecast(bias)
    ssd.to_csv(OUT / "ssd_forecast.csv", index=False)
    print("SSD ratios now vs pre-spike:", {k: round(v, 2) for k, v in ssd.attrs["ratios"].items()})
    print("NAND fall rates:\n", ssd.attrs["fall_rates"].round(3).to_string())
    print(ssd.round(3).to_string())

    g = gpu_memory_cost()
    g.to_csv(OUT / "gpu_memory_cost.csv", index=False)
    print(f"\nGDDR6 8Gb spot: pre {g.attrs['gddr6_pre']:.2f} -> now {g.attrs['gddr6_now']:.2f}")
    print(g.round(2).to_string())

    refs, nows = [], []
    for kind in ("CPU", "GPU"):
        r, n = aging(kind)
        refs.append(r)
        nows.append(n)
        print(f"\n{kind} reference (price / launch price by age, pre-spike):\n", r.round(2).to_string())
        print(f"{kind} now:\n", n[n.n >= 3].sort_values("n", ascending=False).round(2).to_string())
        w = n[n.n >= 3]
        print(f"{kind} weighted mean vs normal: {np.average(w.vs_normal_pct, weights=w.n):.1f}%  (models={len(w)}, posts={w.n.sum()})")
    pd.concat(refs).to_csv(OUT / "aging_reference.csv", index=False)
    pd.concat(nows).to_csv(OUT / "aging_now.csv", index=False)


if __name__ == "__main__":
    main()
