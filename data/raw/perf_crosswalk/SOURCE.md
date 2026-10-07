# Performance per launch dollar, high-end desktop CPUs and GPUs (derived)

Fetched: 2026-10-06

Sources:
- data/raw/perf_wikipedia/ (launch MSRP, release date, FP32)
- data/raw/perf_blender/ (Blender Open Data median scores, CC0)

Derived from the two raw sources above; nothing fetched here. Tier membership and the
Blender device-name regex for each model are listed in fetch/perf_crosswalk.py (TIERS).

- blender_score: Blender 4.5.0 median, best backend (CPU / OPTIX / CUDA / HIP)
  among backends with >= 5 runs; *_alt columns use Blender 4.2.0.
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
