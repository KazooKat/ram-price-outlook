# Our World in Data - historical memory/storage prices

Fetched: 2026-10-06

Sources:
- https://ourworldindata.org/grapher/historical-cost-of-computer-memory-and-storage
- https://ourworldindata.org/grapher/costs-of-66-different-technologies-over-time

historical-cost-of-computer-memory-and-storage: derived from McCallum (ends 2023),
deflated to constant 2020 US$ with US CPI, and expressed as the cheapest price seen
up to each year (a running minimum). It therefore never rises and cannot be used to
date cycle peaks; use data/raw/mccallum instead for cycles.

costs-of-66-different-technologies-over-time (DRAM, Hard disk drive, Transistor):
Santa Fe Institute Performance Curve Database (Nagy, Farmer, Bui, Trancik 2013).
Annual. DRAM runs 1971-2007. Units are as stored in OWID metadata json alongside.
