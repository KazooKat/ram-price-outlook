"""Retail price histories for a basket of popular PC parts, rebuilt from Wayback
Machine captures of PCPartPicker (US) product pages.

Each PCPartPicker product page lists current prices from several US retailers
(Amazon, Newegg, Best Buy, B&H, ...) in server-rendered HTML, so one archived capture
gives a multi-retailer price snapshot. We take ~1 capture per product per month.

Outputs (data/raw/pcpartpicker_products/):
  merchant_prices.csv  one row per retailer per capture
  basket_prices.csv    one row per capture: lowest in-stock price, median, counts
Parsed rows are cached per capture in _cache.jsonl.gz so re-runs only fetch new ones.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import re
import sys
import time
from collections import defaultdict

import lxml.html
import pandas as pd

from fetch._common import get, raw_dir, write_source_note

SOURCE = "pcpartpicker_products"
CDX = "http://web.archive.org/cdx/search/cdx"
START = "201901"
PARSER_VERSION = 1
MAX_TRIES = 3  # captures tried per month when the nearest one is a stub/redirect or fails

# (pcpartpicker id, category, product)
PRODUCTS = [
    ("p6RFf7", "ram", "Corsair Vengeance LPX 16GB (2x8GB) DDR4-3200 CL16 CMK16GX4M2B3200C16"),
    ("W6ndnQ", "ram", "Corsair Vengeance LPX 32GB (2x16GB) DDR4-3200 CL16 CMK32GX4M2E3200C16"),
    ("nvjNnQ", "ram", "G.Skill Ripjaws V 32GB (2x16GB) DDR4-3600 CL18 F4-3600C18D-32GVK"),
    ("LBstt6", "ram", "G.Skill Flare X5 32GB (2x16GB) DDR5-6000 CL30 F5-6000J3038F16GX2-FX5"),
    ("JkfxFT", "ram", "Corsair Vengeance 32GB (2x16GB) DDR5-6000 CL30 CMK32GX5M2B6000C30"),
    ("CXKKHx", "ram", "G.Skill Trident Z5 Neo RGB 32GB (2x16GB) DDR5-6000 CL30 F5-6000J3038F16GX2-TZ5NR"),
    ("34ytt6", "ssd", "Samsung 990 Pro 2TB NVMe PCIe 4.0 MZ-V9P2T0B"),
    ("crKKHx", "ssd", "WD_Black SN850X 2TB NVMe PCIe 4.0 WDS200T2X0E"),
    ("yGZ9TW", "ssd", "Crucial P3 Plus 2TB NVMe PCIe 4.0 CT2000P3PSSD8"),
    ("Zxw7YJ", "ssd", "Samsung 970 Evo Plus 1TB NVMe PCIe 3.0 MZ-V7S1T0B"),
    ("h3tQzy", "ssd", "Crucial MX500 1TB 2.5in SATA CT1000MX500SSD1"),
    ("3hyH99", "cpu", "AMD Ryzen 7 7800X3D"),
    ("fPyH99", "cpu", "AMD Ryzen 7 9800X3D"),
    ("BmWJ7P", "cpu", "Intel Core i7-14700K"),
    ("g94BD3", "cpu", "AMD Ryzen 5 5600X"),
    ("pD8bt6", "gpu", "MSI Ventus 2X 12G OC GeForce RTX 3060 12GB"),
    ("NHzXsY", "gpu", "MSI Ventus 2X OC GeForce RTX 4070 12GB"),
    ("PxG2FT", "gpu", "Gigabyte Windforce OC SFF GeForce RTX 5070 12GB"),
    ("rB2WGX", "gpu", "Asus TUF Gaming OC GeForce RTX 4090 24GB"),
    ("2Ftkcf", "gpu", "Asus TUF Gaming OC GeForce RTX 5090 32GB"),
    ("fcBzK8", "gpu", "Sapphire Pulse Radeon RX 7800 XT 16GB"),
    ("Bvjv6h", "gpu", "Sapphire Pulse Radeon RX 9070 XT 16GB"),
]

MONEY_RE = re.compile(r"\$\s*([\d,]+\.\d{2})")


def _money(s: str) -> float | None:
    m = MONEY_RE.search(s or "")
    return float(m.group(1).replace(",", "")) if m else None


def parse(html: bytes) -> tuple[str, list[dict]]:
    doc = lxml.html.fromstring(html)
    h1 = doc.xpath("//h1[contains(@class,'pageTitle')]") or doc.xpath("//h1")
    title = re.sub(r"\s+", " ", h1[0].text_content()).strip() if h1 else ""
    rows = []
    for tr in doc.xpath("//tr[td[contains(@class,'td__finalPrice')]]"):
        cells = {}
        for td in tr.xpath("./td"):
            cls = (td.get("class") or "").split()
            key = next((c for c in cls if c.startswith("td__")), None)
            if key:
                cells[key] = re.sub(r"\s+", " ", td.text_content()).strip()
                if key == "td__availability":
                    cells["avail_class"] = " ".join(cls)
        merchant = (tr.xpath(".//td[contains(@class,'td__logo')]//img/@alt") or [""])[0].strip()
        final = _money(cells.get("td__finalPrice", ""))
        if final is None:
            continue
        avail = cells.get("td__availability", "")
        rows.append({
            "merchant": merchant,
            "base_price": _money(cells.get("td__base", "")),
            "promo": cells.get("td__promo", ""),
            "shipping": cells.get("td__shipping", ""),
            "availability": avail,
            "in_stock": ("inStock" in cells.get("avail_class", "")) or avail.lower().startswith("in stock"),
            "price": final,
            "price_excludes_tax_or_shipping": cells.get("td__finalPrice", "").endswith("+"),
        })
    return title, rows


def pick_captures(pid: str) -> dict[str, list[tuple[str, str]]]:
    """Month -> captures of the main product page, nearest the 15th first."""
    r = get(CDX, params={"url": f"pcpartpicker.com/product/{pid}", "matchType": "prefix",
                         "output": "json", "filter": "statuscode:200", "fl": "timestamp,original"})
    caps = [x for x in r.json()[1:] if re.search(rf"/product/{pid}(/[^/?]*)?/?(\?.*)?$", x[1])]
    by_month = defaultdict(list)
    for t, orig in caps:
        if t[:6] >= START:
            by_month[t[:6]].append((t, orig))
    return {m: sorted(lst, key=lambda x: abs(int(x[0][6:8]) - 15)) for m, lst in sorted(by_month.items())}


def _usable(rec: dict) -> bool:
    # an untitled page is a Wayback stub/redirect, not a product page
    return rec["status"] == "ok" and bool(rec["title"])


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    d = raw_dir(SOURCE)
    cache_path = d / "_cache.jsonl.gz"
    cache = {}
    if cache_path.exists():
        with gzip.open(cache_path, "rt", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if rec.get("parser") == PARSER_VERSION and rec["status"] == "ok":  # errors are retried
                    cache[(rec["pid"], rec["ts"])] = rec
    chosen = {}  # (pid, month) -> cache key used for the summary
    for pid, cat, name in PRODUCTS:
        try:
            months = pick_captures(pid)
        except Exception as e:
            print(f"CDX failed for {pid}: {e}")
            continue
        fetched = 0
        for month, cands in months.items():
            for t, orig in cands[:MAX_TRIES]:
                if (pid, t) not in cache:
                    try:
                        title, rows = parse(get(f"http://web.archive.org/web/{t}id_/{orig}", timeout=90).content)
                        status = "ok"
                    except Exception as e:
                        title, rows, status = "", [], f"error: {e}"[:200]
                    rec = {"pid": pid, "ts": t, "orig": orig, "title": title, "status": status,
                           "parser": PARSER_VERSION, "rows": rows}
                    if status == "ok":
                        cache[(pid, t)] = rec
                        with gzip.open(cache_path, "at", encoding="utf-8") as f:
                            f.write(json.dumps(rec) + "\n")
                    fetched += 1
                    time.sleep(1.5)
                if (pid, t) in cache and _usable(cache[(pid, t)]):
                    chosen[(pid, month)] = (pid, t)
                    break
        print(f"{pid} {name[:45]:45s} months={len(months):3d} usable={sum(k[0] == pid for k in chosen):3d} "
              f"fetched={fetched}", flush=True)
        time.sleep(1.5)
    with gzip.open(cache_path, "wt", encoding="utf-8") as f:
        for rec in cache.values():
            f.write(json.dumps(rec) + "\n")

    meta = {pid: (cat, name) for pid, cat, name in PRODUCTS}
    merch, summ = [], []
    for (pid, t) in sorted(chosen.values()):
        rec = cache[(pid, t)]
        cat, name = meta[pid]
        date = f"{t[:4]}-{t[4:6]}-{t[6:8]}"
        snap = f"http://web.archive.org/web/{t}/{rec['orig']}"
        for r in rec["rows"]:
            merch.append({"date": date, "category": cat, "product": name, "pcpp_id": pid, **r,
                          "currency": "USD", "page_title": rec["title"], "url_of_snapshot": snap})
        prices = [r["price"] for r in rec["rows"]]
        instock = [r["price"] for r in rec["rows"] if r["in_stock"]]
        summ.append({
            "date": date, "category": cat, "product": name, "pcpp_id": pid,
            "price": min(instock) if instock else None,
            "price_basis": "lowest in-stock retailer price" if instock else "no in-stock listing",
            "min_any_listing": min(prices) if prices else None,
            "median_listing": float(pd.Series(prices).median()) if prices else None,
            "n_listings": len(prices), "n_in_stock": len(instock), "currency": "USD",
            "status": rec["status"], "url_of_snapshot": snap,
        })
    pd.DataFrame(merch).to_csv(d / "merchant_prices.csv", index=False)
    s = pd.DataFrame(summ)
    s.to_csv(d / "basket_prices.csv", index=False)
    ok = s[s.n_listings > 0]
    print(f"product-months={len(s)} with listings={len(ok)} with in-stock price={s.price.notna().sum()} "
          f"merchant rows={len(merch)}")
    print(ok.groupby("product").agg(n=("price", "size"), first=("date", "min"), last=("date", "max"),
                                    lo=("price", "min"), hi=("price", "max")).to_string())
    write_source_note(
        SOURCE,
        title="PCPartPicker (US) product pages via Wayback Machine - retail price basket",
        urls=[f"https://pcpartpicker.com/product/{pid}" for pid, _, _ in PRODUCTS]
             + ["http://web.archive.org/cdx/search/cdx"],
        notes="""
One Wayback capture per product per month (nearest the 15th; if that capture is a
stub/redirect page or fails, the next-nearest of up to 3), Jan 2019 (or first capture)
to present. Months where the product page had no retailer listings at all (pre-launch,
discontinued) are kept with n_listings=0. Each capture lists US retailer prices as PCPartPicker showed them
when the crawler visited. price (basket_prices.csv) = lowest in-stock retailer final
price (after promo, incl. shipping where shown, excl. tax); blank when nothing was in
stock. merchant_prices.csv keeps every listing (in- and out-of-stock).

Caveats: capture timing is whatever the Wayback crawler chose, so months can be
missing and a single capture can catch a one-day sale. Marketplace sellers (Amazon
3rd-party, Walmart marketplace, MemoryC) sometimes list far above MSRP during
shortages; use the in-stock minimum or merchant filters accordingly. Prices are
nominal USD.
""",
    )


if __name__ == "__main__":
    main()
