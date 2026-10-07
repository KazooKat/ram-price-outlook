"""Performance per launch dollar for high-end desktop CPUs and GPUs, by generation.

Derived dataset: joins perf_wikipedia (launch MSRP, release date, FP32) to
perf_blender (measured Cycles render score). No new external data is fetched; run
perf_wikipedia and perf_blender first.

The model list below is the definition of "high-end tier" per generation. Each
model maps to its Blender Open Data device name by an explicit regex, so the
join is auditable.

Output (data/raw/perf_crosswalk/):
  perf_per_launch_dollar.csv  one row per model: price, date, Blender score, score/$, FP32/$
  gen_over_gen.csv            per vendor+tier, change vs the previous generation
  summary.csv                 per vendor+tier, geometric-mean and annualised change
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from fetch._common import RAW, raw_dir, write_source_note

SOURCE = "perf_crosswalk"
REF_VERSION = "4.5.0"      # most runs; covers RTX 50 / RX 9000
ALT_VERSION = "4.2.0"      # robustness check
MIN_RUNS = 5

# (kind, vendor, tier, wikipedia family, wikipedia model, Blender device-name regex)
TIERS = [
    # CPUs: top mainstream-socket desktop SKU at each generation's launch
    ("cpu", "AMD", "flagship", "Ryzen 3000 (Zen 2)", "3950X", r"^AMD Ryzen 9 3950X 16-Core Processor$"),
    ("cpu", "AMD", "flagship", "Ryzen 5000 (Zen 3)", "5950X", r"^AMD Ryzen 9 5950X 16-Core Processor$"),
    ("cpu", "AMD", "flagship", "Ryzen 7000 (Zen 4)", "7950X", r"^AMD Ryzen 9 7950X 16-Core Processor$"),
    ("cpu", "AMD", "flagship", "Ryzen 9000 (Zen 5)", "9950X", r"^AMD Ryzen 9 9950X 16-Core Processor$"),
    ("cpu", "AMD", "8-core", "Ryzen 3000 (Zen 2)", "3700X", r"^AMD Ryzen 7 3700X 8-Core Processor$"),
    ("cpu", "AMD", "8-core", "Ryzen 5000 (Zen 3)", "5800X", r"^AMD Ryzen 7 5800X 8-Core Processor$"),
    ("cpu", "AMD", "8-core", "Ryzen 7000 (Zen 4)", "7700X", r"^AMD Ryzen 7 7700X 8-Core Processor$"),
    ("cpu", "AMD", "8-core", "Ryzen 9000 (Zen 5)", "9700X", r"^AMD Ryzen 7 9700X 8-Core Processor$"),
    ("cpu", "Intel", "flagship", "Core 10th gen (Comet Lake)", "10900K", r"^Intel Core i9-10900K CPU @"),
    ("cpu", "Intel", "flagship", "Core 11th gen (Rocket Lake)", "11900K", r"^Intel Core i9-11900K @"),
    ("cpu", "Intel", "flagship", "Core 12th gen (Alder Lake)", "12900K", r"^Intel Core i9-12900K$"),
    ("cpu", "Intel", "flagship", "Core 13th gen (Raptor Lake)", "13900K", r"^13th Gen Intel Core i9-13900K$"),
    ("cpu", "Intel", "flagship", "Core 14th gen (Raptor Lake Refresh)", "14900K", r"^Intel Core i9-14900K$"),
    ("cpu", "Intel", "flagship", "Core Ultra 200S (Arrow Lake)", "285K", r"^Intel Core Ultra 9 285K$"),
    ("cpu", "Intel", "i7-class", "Core 10th gen (Comet Lake)", "10700K", r"^Intel Core i7-10700K CPU @"),
    ("cpu", "Intel", "i7-class", "Core 11th gen (Rocket Lake)", "11700K", r"^Intel Core i7-11700K @"),
    ("cpu", "Intel", "i7-class", "Core 12th gen (Alder Lake)", "12700K", r"^Intel Core i7-12700K$"),
    ("cpu", "Intel", "i7-class", "Core 13th gen (Raptor Lake)", "13700K", r"^13th Gen Intel Core i7-13700K$"),
    ("cpu", "Intel", "i7-class", "Core 14th gen (Raptor Lake Refresh)", "14700K", r"^Intel Core i7-14700K$"),
    ("cpu", "Intel", "i7-class", "Core Ultra 200S (Arrow Lake)", "265K", r"^Intel Core Ultra 7 265K$"),
    ("cpu", "Intel", "i7-class", "Core Ultra 200S Plus (Arrow Lake Refresh)", "270K Plus", r"^Intel Core Ultra 7 270K Plus$"),
    # GPUs
    ("gpu", "Nvidia", "halo (x80 Ti/x90)", "GeForce 10 (Pascal)", "GeForce GTX 1080 Ti", r"^NVIDIA GeForce GTX 1080 Ti$"),
    ("gpu", "Nvidia", "halo (x80 Ti/x90)", "GeForce RTX 20 (Turing)", "GeForce RTX 2080 Ti", r"^NVIDIA GeForce RTX 2080 Ti$"),
    ("gpu", "Nvidia", "halo (x80 Ti/x90)", "GeForce RTX 30 (Ampere)", "GeForce RTX 3090", r"^NVIDIA GeForce RTX 3090$"),
    ("gpu", "Nvidia", "halo (x80 Ti/x90)", "GeForce RTX 40 (Ada Lovelace)", "GeForce RTX 4090", r"^NVIDIA GeForce RTX 4090$"),
    ("gpu", "Nvidia", "halo (x80 Ti/x90)", "GeForce RTX 50 (Blackwell)", "GeForce RTX 5090", r"^NVIDIA GeForce RTX 5090$"),
    ("gpu", "Nvidia", "x80", "GeForce 10 (Pascal)", "GeForce GTX 1080", r"^NVIDIA GeForce GTX 1080$"),
    ("gpu", "Nvidia", "x80", "GeForce RTX 20 (Turing)", "GeForce RTX 2080", r"^NVIDIA GeForce RTX 2080$"),
    ("gpu", "Nvidia", "x80", "GeForce RTX 30 (Ampere)", "GeForce RTX 3080", r"^NVIDIA GeForce RTX 3080$"),
    ("gpu", "Nvidia", "x80", "GeForce RTX 40 (Ada Lovelace)", "GeForce RTX 4080", r"^NVIDIA GeForce RTX 4080$"),
    ("gpu", "Nvidia", "x80", "GeForce RTX 50 (Blackwell)", "GeForce RTX 5080", r"^NVIDIA GeForce RTX 5080$"),
    ("gpu", "Nvidia", "x70", "GeForce 10 (Pascal)", "GeForce GTX 1070", r"^NVIDIA GeForce GTX 1070$"),
    ("gpu", "Nvidia", "x70", "GeForce RTX 20 (Turing)", "GeForce RTX 2070", r"^NVIDIA GeForce RTX 2070$"),
    ("gpu", "Nvidia", "x70", "GeForce RTX 30 (Ampere)", "GeForce RTX 3070", r"^NVIDIA GeForce RTX 3070$"),
    ("gpu", "Nvidia", "x70", "GeForce RTX 40 (Ada Lovelace)", "GeForce RTX 4070", r"^NVIDIA GeForce RTX 4070$"),
    ("gpu", "Nvidia", "x70", "GeForce RTX 50 (Blackwell)", "GeForce RTX 5070", r"^NVIDIA GeForce RTX 5070$"),
    ("gpu", "AMD", "top", "Radeon RX 5000 (RDNA)", "Radeon RX 5700 XT", r"^AMD Radeon RX 5700 XT$"),
    ("gpu", "AMD", "top", "Radeon RX 6000 (RDNA 2)", "Radeon RX 6900 XT", r"^AMD Radeon RX 6900 XT$"),
    ("gpu", "AMD", "top", "Radeon RX 7000 (RDNA 3)", "Radeon RX 7900 XTX", r"^AMD Radeon RX 7900 XTX$"),
    ("gpu", "AMD", "top", "Radeon RX 9000 (RDNA 4)", "Radeon RX 9070 XT", r"^AMD Radeon RX 9070 XT$"),
]


def blender_score(b: pd.DataFrame, pattern: str, version: str) -> dict:
    """Best backend (highest median) among rows with >= MIN_RUNS runs."""
    s = b[(b.blender_version == version) & b.device_name.str.contains(pattern, regex=True)
          & ~b.device_name.str.contains(r"ZLUDA|Laptop", regex=True)]
    names = sorted(s.device_name.unique())
    if len(names) > 1:
        raise RuntimeError(f"{pattern!r} matches several Blender devices: {names}")
    ok = s[s.n_benchmarks >= MIN_RUNS]
    if ok.empty:
        return dict(score=np.nan, backend=None, runs=int(s.n_benchmarks.sum()) if len(s) else 0,
                    device=names[0] if names else None)
    best = ok.loc[ok.median_score.idxmax()]
    return dict(score=best.median_score, backend=best.compute_type, runs=int(best.n_benchmarks),
                device=best.device_name)


def main() -> None:
    out = raw_dir(SOURCE)
    cpu = pd.read_csv(RAW / "perf_wikipedia" / "cpu_desktop.csv")
    gpu = pd.read_csv(RAW / "perf_wikipedia" / "gpu_desktop.csv")
    b = pd.read_csv(RAW / "perf_blender" / "blender_median_scores.csv", dtype={"blender_version": str})

    rows = []
    for kind, vendor, tier, family, model, pattern in TIERS:
        w = (cpu if kind == "cpu" else gpu)
        w = w[(w.family == family) & (w.model == model)].sort_values("release_date")
        if w.empty:
            raise RuntimeError(f"{family} / {model} not in perf_wikipedia")
        w = w.iloc[0]  # earliest listing = launch (later rows are price cuts / memory refreshes)
        ref, alt = blender_score(b, pattern, REF_VERSION), blender_score(b, pattern, ALT_VERSION)
        price = w.launch_price_usd
        rows.append(dict(
            kind=kind, vendor=vendor, tier=tier, family=family, model=model,
            release_date=w.release_date, launch_price_usd=price,
            cores=w.get("cores") if kind == "cpu" else np.nan,
            fp32_gflops=w.get("fp32_gflops_boost") if kind == "gpu" else np.nan,
            blender_device=ref["device"] or alt["device"],
            blender_score=ref["score"], blender_backend=ref["backend"], blender_runs=ref["runs"],
            blender_score_alt=alt["score"], blender_backend_alt=alt["backend"], blender_runs_alt=alt["runs"],
            score_per_100usd=ref["score"] / price * 100 if price else np.nan,
            score_alt_per_100usd=alt["score"] / price * 100 if price else np.nan,
            fp32_gflops_per_usd=(w.get("fp32_gflops_boost") / price) if kind == "gpu" and price else np.nan,
            price_source_url=w.source_url,
        ))
    df = pd.DataFrame(rows)
    df.to_csv(out / "perf_per_launch_dollar.csv", index=False)

    g = []
    for (kind, vendor, tier), grp in df.groupby(["kind", "vendor", "tier"], sort=False):
        grp = grp.sort_values("release_date").reset_index(drop=True)
        for i in range(1, len(grp)):
            p, c = grp.iloc[i - 1], grp.iloc[i]
            years = (pd.Timestamp(c.release_date) - pd.Timestamp(p.release_date)).days / 365.25
            g.append(dict(
                kind=kind, vendor=vendor, tier=tier, from_model=p.model, to_model=c.model,
                from_date=p.release_date, to_date=c.release_date, years=round(years, 2),
                price_change_pct=(c.launch_price_usd / p.launch_price_usd - 1) * 100,
                score_change_pct=(c.blender_score / p.blender_score - 1) * 100,
                score_per_usd_change_pct=(c.score_per_100usd / p.score_per_100usd - 1) * 100,
                score_alt_per_usd_change_pct=(c.score_alt_per_100usd / p.score_alt_per_100usd - 1) * 100,
                fp32_per_usd_change_pct=(c.fp32_gflops_per_usd / p.fp32_gflops_per_usd - 1) * 100
                if kind == "gpu" else np.nan,
            ))
    gg = pd.DataFrame(g)
    gg.to_csv(out / "gen_over_gen.csv", index=False)

    # Averages per vendor+tier: geometric mean of gen-over-gen ratios, and the same
    # change annualised over the launch-date span (endpoint CAGR).
    s = []
    for (kind, vendor, tier), grp in gg.groupby(["kind", "vendor", "tier"], sort=False):
        def geo(col):
            r = 1 + grp[col].dropna() / 100
            return (r.prod() ** (1 / len(r)) - 1) * 100 if len(r) else np.nan
        steps = grp.dropna(subset=["score_per_usd_change_pct"])
        span = steps.years.sum()
        total = (1 + steps.score_per_usd_change_pct / 100).prod()
        s.append(dict(
            kind=kind, vendor=vendor, tier=tier, first_model=grp.from_model.iloc[0],
            last_model=grp.to_model.iloc[-1], n_steps=len(steps), years=round(span, 1),
            geo_mean_price_change_pct=geo("price_change_pct"),
            geo_mean_score_change_pct=geo("score_change_pct"),
            geo_mean_score_per_usd_change_pct=geo("score_per_usd_change_pct"),
            annualized_score_per_usd_change_pct=(total ** (1 / span) - 1) * 100 if span else np.nan,
            geo_mean_fp32_per_usd_change_pct=geo("fp32_per_usd_change_pct") if kind == "gpu" else np.nan,
        ))
    pd.DataFrame(s).to_csv(out / "summary.csv", index=False)
    print(f"perf_per_launch_dollar.csv: {len(df)} rows; gen_over_gen.csv: {len(gg)} rows; summary.csv: {len(s)} rows")

    write_source_note(
        SOURCE,
        title="Performance per launch dollar, high-end desktop CPUs and GPUs (derived)",
        urls=["data/raw/perf_wikipedia/ (launch MSRP, release date, FP32)",
              "data/raw/perf_blender/ (Blender Open Data median scores, CC0)"],
        notes=f"""
Derived from the two raw sources above; nothing fetched here. Tier membership and the
Blender device-name regex for each model are listed in fetch/perf_crosswalk.py (TIERS).

- blender_score: Blender {REF_VERSION} median, best backend (CPU / OPTIX / CUDA / HIP)
  among backends with >= {MIN_RUNS} runs; *_alt columns use Blender {ALT_VERSION}.
- score_per_100usd = blender_score / launch_price_usd * 100. Launch price is the
  nominal launch MSRP (Intel: recommended customer price), not inflation-adjusted and
  not the street price at any point in time.
- fp32_gflops_per_usd: theoretical FP32 at boost / launch price (GPUs only).
  Ampere (RTX 30) doubled FP32 lanes per SM, which inflates its FP32 jump.
- gen_over_gen: each row compares a model with the previous generation's model in
  the same vendor+tier, by release date.
- Blender Cycles rewards ray-tracing hardware (OPTIX on RTX). The GTX 10 -> RTX 20
  step therefore shows a larger jump than gaming benchmarks would.
- summary: geo_mean_* = geometric mean of the gen-over-gen ratios;
  annualized_score_per_usd_change_pct = total change over the tier's launch-date span,
  annualised. A step is skipped when either end lacks a Blender score.
- AMD GPU "top" tier: RX 9070 XT ($599) is AMD's top RDNA 4 card but sits a class
  below the RX 7900 XTX ($999); AMD did not release a higher RDNA 4 card.
- Nvidia RTX 2080 Ti: MSRP $999 is used; the Founders Edition launched at $1,199.
- The Wikipedia row used is the earliest listing of the model (later rows are price
  cuts or memory refreshes).
""",
    )


if __name__ == "__main__":
    main()
