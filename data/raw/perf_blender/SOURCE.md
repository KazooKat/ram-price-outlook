# Blender Open Data benchmark medians (CPU and GPU)

Fetched: 2026-10-06

Sources:
- https://opendata.blender.org/benchmarks/query/?group_by=device_name&group_by=compute_type&group_by=blender_version&response_type=datatables
- https://opendata.blender.org/about/
- https://opendata.blender.org/download/ (CC0 licence; full daily snapshot)

Score: "the estimated number of samples per minute, summed for all benchmark scenes"
(Cycles path tracing; opendata.blender.org/about). Higher is better.

- One row per device_name x compute_type (CPU, CUDA, OPTIX, HIP, ONEAPI, METAL)
  x blender_version, with the median over all user-submitted runs and the run count.
- Compare scores only within one blender_version. 4.5.0 has the most runs and covers
  RTX 50 / RX 9000; it is the suggested reference version.
- User-submitted runs: no control over clocks, cooling, OS or drivers. Prefer devices
  with n_benchmarks >= 5. Medians, not means, so single outliers don't dominate.
- GPU backends differ: OPTIX uses Nvidia RT cores, so RTX cards score far above GTX
  cards on OPTIX. This favours hardware ray tracing more than games do.
- CPU device names are as the OS reports them (e.g. "AMD Ryzen 9 7950X 16-Core
  Processor", "13th Gen Intel Core i9-13900K"); match to models with care.
- Rows with an empty device name are dropped.
