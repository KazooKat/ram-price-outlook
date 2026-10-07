# Korea monthly IC / memory export values (UN Comtrade)

Fetched: 2026-10-06

Sources:
- https://comtradeapi.un.org/public/v1/preview/C/M/HS
- https://comtradeplus.un.org/

UN Comtrade keyless "preview" endpoint, reporter 410 (Republic of Korea),
partner 0 (World), flow X (exports), monthly, HS classification as reported
(H5/H6 depending on year). Values are FOB USD as reported by Korea Customs to
the UN.

HS codes:
- 854232: Electronic integrated circuits: memories
- 8542: Electronic integrated circuits (all)
- 852351: Semiconductor media: solid-state non-volatile storage devices (SSD/flash cards)
- 847330: Parts and accessories of computers (HS 8471); includes memory modules

Caveats:
- Comtrade monthly data lags several months; months not yet published are
  simply absent (re-run to extend).
- HS 854232 is the closest customs category to "memory chips" (DRAM, NAND,
  HBM die/stacks, MCPs). Memory modules usually fall under 847330 (mixed with
  other computer parts) and SSDs under 852351 - both are noisy proxies.
- Korea's own MOTIE/KITA "semiconductor" figures use MTI product codes, not HS,
  so they will not match these numbers exactly.
- The keyless preview API is rate-limited (~1 call / few seconds) AND has a
  call-volume quota (~40 calls, then a 403 with a reset timer of up to ~1h).
  The script paces, sleeps through quota resets, checkpoints after every month
  and on re-run only refetches the most recent 18 months. A full fresh-clone
  run (~135 months) therefore takes a few hours of mostly sleeping.
