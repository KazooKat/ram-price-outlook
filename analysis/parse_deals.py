"""Parse r/buildapcsales deal titles into structured RAM / SSD / CPU / GPU prices.

Input:  data/raw/buildapcsales/YYYY-MM.jsonl.gz  (fetch/deals_buildapcsales.py)
Output: data/processed/deals_parsed.csv    accepted rows, one per deal post
        data/processed/deals_rejected.csv  category-matched rows that were rejected, with reason
        data/processed/deals_monthly.csv   long format: month, series, median, p25, p75, n

Precision over recall: any title that is ambiguous (several prices, several capacities or
models, bundles, non-USD, used/refurb/open-box) is rejected rather than guessed.

Usage: python analysis/parse_deals.py [--validate]
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "buildapcsales"
OUT = ROOT / "data" / "processed"

# ---------------------------------------------------------------- category

TAG_RE = re.compile(r"^\s*[\[\(]([^\]\)]{1,40})[\]\)]\s*")
CAT_PATTERNS = {
    "RAM": re.compile(r"\b(ram|memory|ddr[345]|dimm|so-?dimm)\b", re.I),
    "SSD": re.compile(r"\b(ssd|nvme|m\.2)\b", re.I),
    "CPU": re.compile(r"\b(cpu|processor|apu)\b", re.I),
    "GPU": re.compile(r"\b(gpu|video ?card|graphics ?card|vga)\b", re.I),
}
FLAIR_MAP = {
    "ram": "RAM", "memory": "RAM",
    "ssd": "SSD", "ssd - m.2": "SSD", "ssd - sata": "SSD", "m.2 ssd": "SSD", "nvme": "SSD",
    "cpu": "CPU", "processor": "CPU",
    "gpu": "GPU", "video card": "GPU", "graphics card": "GPU",
}
OTHER_TAG_RE = re.compile(r"\b(bundle|combo|cooler|cooling|mobo|motherboard|prebuilt|laptop|"
                          r"hdd|external|portable|psu|case|monitor)\b", re.I)

NOT_DEAL_TAG_RE = re.compile(r"\b(meta|psa|question|discussion|iso|wtb|wts|help)\b", re.I)
ACCESSORY_TAG_RE =re.compile(r"\b(block|bracket|riser|cable|support|fans?|backplate|mount|adapter|"
                              r"enclosure|heatsink|holder|stand|external|portable|sd|card reader|dock|"
                              r"cooler|cooling|thermal|paste|pad)\b", re.I)


def categorize(title: str, flair: str | None) -> tuple[str | None, str, bool]:
    """Return (category, title without tag, multi_category_tag)."""
    m = TAG_RE.match(title)
    if m:
        tag = m.group(1)
        if ACCESSORY_TAG_RE.search(tag):  # "[GPU Block]", "[M.2 to PCIe Adapter]", "[Micro SD]"
            return None, title[m.end():], False
        if NOT_DEAL_TAG_RE.search(tag):  # "[GPU META POST]", "[ISO]"
            return None, title[m.end():], False
        hits = [c for c, rx in CAT_PATTERNS.items() if rx.search(tag)]
        body = title[m.end():]
        # "[CPU Cooler]", "[External SSD]", "[CPU/Mobo]" etc. are not the bare component.
        multi = len(hits) > 1 or bool(re.search(r"[/+&]", tag)) or bool(OTHER_TAG_RE.search(tag))
        if hits:
            return hits[0], body, multi
        if OTHER_TAG_RE.search(tag):
            return None, body, False
    # no category tag (or a product name in brackets, e.g. "[AMD Ryzen 5 5600x]"): keep the full title
    body = title
    f = (flair or "").strip().lower()
    return FLAIR_MAP.get(f), body, False


# ---------------------------------------------------------------- filters

NON_USD_RE = re.compile(
    r"(\bCAD\b|\bCDN\b|(?<![A-Za-z])C\$|CA\$|CAN\$|\bAUD\b|(?<![A-Za-z])AU?\$|\bNZD\b|NZ\$|£|€|"
    r"\bGBP\b|\bEUR\b|\bINR\b|₹|\bCanada\b|\bCanadian\b|[\[\(](?:CA|CAN|AU|UK|EU|DE)[\]\)]|"
    r"\bUK\b|\bAustralia)", re.I)
NON_US_DOMAINS = (".ca", ".co.uk", ".uk", ".com.au", ".au", ".de", ".fr", ".it", ".es", ".nl",
                  ".in", ".co.nz", ".nz", ".ie", ".jp", ".mx", ".se", ".pl", ".be", ".at", ".ch")
NON_US_SITES = {"memoryexpress.com", "canadacomputers.com", "ebuyer.com", "ldlc.com",
                "pccasegear.com", "mightyape.co.nz"}
USED_RE = re.compile(r"\b(used|refurb\w*|renewed|recertified|re-certified|pre-?owned|like[- ]new|"
                     r"\bb\s?-?\s?stock|grade [abc]\b|reconditioned|second-?hand|ex-?lease|pulls?\b|"
                     r"warehouse|scratch (?:and|&) dent|damaged box)", re.I)
OPEN_BOX_RE = re.compile(r"open[- ]?box", re.I)
RANGE_RE = re.compile(r"\b(starting at|starts at|start at|(?:starting|prices?|starts?) from|as low as|up to \$|various|"
                      r"multiple|assorted|select (?:models|sizes|items)|all sizes|several|lots of|"
                      r"sale on|deals on|price drops? on|\d+% off (?:all|select|sitewide))", re.I)
PACK_RE = re.compile(r"\b(pack of|\d+[- ]?pack\b|lot of|bulk|qty\.? ?\d|x\s?\d+ units)", re.I)
NOT_DEAL_RE = re.compile(r"^\s*(selling|wts\b|wtb\b|fs:|for sale|psa\b|meta\b|question\b)|\bselling my\b|"
                         r"\[(?:iso|meta|psa|wtb|question)\]",
                         re.I)
PREBUILT_RE = re.compile(r"\b(laptop|notebook|prebuilt|pre-built|gaming pc|gaming desktop|desktop pc|"
                         r"mini pc|steam deck|handheld)\b(?!\s?(?:processor|cpu))", re.I)
# eBay listings in this sub are a mix of used, third-party and outright scams (e.g. the 2019 wave of
# "$63 Ryzen 7 2700X" listings that dominated that model's monthly median), so they are excluded.
SUSPECT_RE = re.compile(r"\bebay\b|\bscam\b|too good to be true|is this (?:real|legit)|legit\?|\bfake\b|"
                        r"\bstolen\b|price (?:error|mistake)|pricing error|mispric", re.I)
NOT_DRAM_RE = re.compile(r"\b(sdxc|sdhc|sd card|micro ?sd|flash|usb|memory card|thumb ?drive|optane)\b", re.I)
CONDITIONAL_RE = re.compile(r"\b(with (?:the )?purchase of|when (?:you )?(?:buy|bought|purchas)|"
                            r"add any|with any)\b", re.I)

# Other-hardware words that, when present in a given category's title, indicate a bundle.
BUNDLE_HW = {
    "RAM": r"\b(motherboard|mobo|cpu|processor|ryzen|core i[3579]|ssd|nvme|gpu|graphics card|rtx|gtx)\b",
    "SSD": r"\b(motherboard|mobo|cpu|processor|ryzen|gpu|graphics card|rtx \d|ddr[45] (?:ram|memory)|"
           r"memory kit|enclosure)\b",
    "CPU": r"\b(motherboard|mobo|[abxz][4-9][0-9]0[a-z]?\b(?!3d)|b[4-8]50|ddr[45]|\bram\b|memory|ssd|nvme|gpu|"
           r"graphics card|rtx \d|gtx \d|geforce|radeon rx|radeon \d{3,4}|rx \d{3,4}|aio|liquid cooler|liquid freezer|kraken|coreliquid|hyper 212|noctua|"
           r"peerless|assassin)\b",
    "GPU": r"\b(motherboard|mobo|cpu|processor|ryzen [3579]|core i[3579]|psu|power supply|monitor|"
           r"\bram\b|ddr[45]|ssd|nvme|prebuilt)\b",
}
BUNDLE_HW = {k: re.compile(v, re.I) for k, v in BUNDLE_HW.items()}
COMBO_RE = re.compile(r"\b(combo|bundled? with (?:a |an )?(?:motherboard|mobo|cpu|ram|ssd))\b", re.I)


def domain_non_us(domain: str) -> bool:
    d = (domain or "").lower()
    return d in NON_US_SITES or any(d.endswith(s) for s in NON_US_DOMAINS)


# ---------------------------------------------------------------- price

NUM = r"(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2})|,(\d{2})(?!\d))?"
MONEY_RE = re.compile(r"(?:US\s?\$|USD\s?\$?|\$)\s?" + NUM, re.I)
# postfix dollars ("20$", "20 USD"); "$" must touch the number so "M.2 2280 $54" is not read as 2280
POST_MONEY_RE = re.compile(r"(?<![\w.])" + NUM + r"(?:\$|\s?usd\b|\s?dollars\b)", re.I)
# no "$" anywhere: fall back to decimal amounts like "- 639.99" or "(89.99)"
BARE_RE = re.compile(r"(?<![\w.$,])(\d{1,3}(?:,\d{3})+|\d{1,5})\.(\d{2})(?![\d%])"
                     r"(?!\s?(?:gb|tb|mb|ghz|mhz|v\b|w\b|mm|in\b|\"|inch|ms|hz))()", re.I)
# "= $519.99" / "= 519.99" is the poster's computed final price ("code=72ABC" is not)
EQUALS_RE = re.compile(r"=\s*(?:US\s?)?(?:\$\s?" + NUM + r"|(\d{1,5})\.(\d{2})(?!\d)())")
DISCOUNT_AFTER = re.compile(
    r"^\s*(?:usd\s*)?(?:off|mir|rebate|mail|coupon|promo|instant|gift|gc\b|credit|back|cash ?back|"
    r"shipping|s&h|ship|savings|discount|reward|store credit|in rewards|e-?gift|cheaper|less\b|more\b|"
    r"amazon credit|bonus|for (?:new|first))"
    r"|^\s*(?:(?!(?:with|w|after|using|via|when|at|in|and|before|including|incl|plus)\b)[\w.&'-]+\s){1,2}"
    r"(?:gift ?card|gc\b|credit|rebate|reward|mir\b|discount|off\b)", re.I)
DISCOUNT_BEFORE = re.compile(
    r"(?:save|saving|savings|was|(?:reg\.?|regular|list|retail|orig\.?|original)(?:\s?price)?|regularly|msrp|"
    r"normally|norm|extra|additional|minus|less|\+|plus|get|earn|receive|from|ship(?:ping)?|s&h|after|w/|with|"
    r"by|down from|instead of|vs\.?|compared to|lowest|previous(?:ly)?|usually|typically|avg)\s*:?\s*$",
    re.I)


def _val(m: re.Match, g0: int = 1) -> float:
    whole = m.group(g0).replace(",", "")
    cents = m.group(g0 + 1) or m.group(g0 + 2) or ""
    return float(whole + ("." + cents if cents else ""))


def _paren_depth(s: str) -> list[int]:
    depth, out = 0, []
    for ch in s:
        if ch in "([{":
            depth += 1
        out.append(depth)
        if ch in ")]}":
            depth = max(0, depth - 1)
    return out


def parse_price(t: str) -> tuple[float | None, str | None]:
    """Return (price, reject_reason). The sub's convention is '<item> - $<final price>';
    a trailing '= $X' is the computed final price and wins."""
    eq = list(EQUALS_RE.finditer(t))
    if eq:
        m = eq[-1]
        return (_val(m, 1) if m.group(1) else _val(m, 4)), None

    toks = [(m.start(), m.end(), _val(m)) for m in MONEY_RE.finditer(t)]
    toks += [(m.start(), m.end(), _val(m)) for m in POST_MONEY_RE.finditer(t)
             if not any(s <= m.start() < e for s, e, _ in toks)]
    if not toks:
        toks = [(m.start(), m.end(), _val(m)) for m in BARE_RE.finditer(t)]
    toks.sort()
    if not toks:
        return None, "no_price"

    depth = _paren_depth(t)
    inside, outside, computed = [], [], []
    prev_end, head, chain, subtracted = None, None, None, False  # chain: running "$A - $B - $C"
    for s, e, v in toks:
        before, after = t[max(0, s - 25):s], t[e:e + 25]
        discount = bool(DISCOUNT_AFTER.match(after)) or bool(DISCOUNT_BEFORE.search(before))
        gap = t[prev_end:s] if prev_end is not None else None
        if gap is not None and re.fullmatch(r"\s*[-–]\s*", gap):
            # "$A - $B": B is a subtraction, not a second price
            discount = True
            if chain is not None:
                chain, subtracted = chain - v, True
        elif re.search(r"[-–]$", before) and (inside or outside):
            # "after -$10 promo" (dash touching the amount) following an earlier price is a subtraction
            discount = True
        else:
            if chain is not None and subtracted:
                computed.append((head, round(chain, 2)))
            head = chain = None if discount else v
            subtracted = False
        if after.lstrip().startswith("%"):
            discount = True
        prev_end = e
        if discount:
            continue
        (inside if depth[s] > 0 else outside).append(v)
    if chain is not None and subtracted:
        computed.append((head, round(chain, 2)))

    for group in (outside, inside):
        vals = sorted(set(group))
        if len(vals) == 1:
            # a lone "$A - $B - $C" chain: the poster's arithmetic gives the final price
            res = [c for h, c in computed if h == vals[0]]
            if res:
                return (res[0], None) if 0.3 * vals[0] < res[0] else (None, "ambiguous_price")
            return vals[0], None
        if len(vals) > 1:
            # "($125) ($150 - $25)": accept when one candidate is the others' computed result
            agreed = [v for v in vals if any(abs(v - c) < 0.02 for _, c in computed)]
            if len(agreed) == 1:
                return agreed[0], None
            return None, "ambiguous_price"
    return None, "no_price"


# ---------------------------------------------------------------- RAM

RAM_SIZES = {2, 4, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256}
KIT_NFIRST = re.compile(r"\b([1-8])\s?(?:pcs?\s?)?[x×\*]\s?(\d{1,3})\s?(?:gb|g)?\b", re.I)
KIT_SFIRST = re.compile(r"\b(\d{1,3})\s?(?:gb|g)?\s?[x×\*]\s?([1-8])\b(?!\s?(?:gb|g)\b)", re.I)
GB_RE = re.compile(r"\b(\d{1,4}(?:\.\d)?)\s?(gb|tb)\b(?!\s?/s)", re.I)
DDR_RE = re.compile(r"(?<!lp)(?<!g)ddr\s?-?([345])(?!\d)|\bpc([345])-?\s?\d{5}", re.I)
SPEED_PATTERNS = [
    re.compile(r"ddr[345]\s?(?:-|\s)?\s?(\d{4})\b", re.I),
    re.compile(r"\b(\d{4})\s?(?:mhz|mt/?s|mts|mt)\b", re.I),
    re.compile(r"\b(\d{4})\s?/?\s?c(?:l)?\s?\d{2}\b", re.I),
]
KNOWN_SPEEDS = {1600, 1866, 2133, 2400, 2666, 2667, 2800, 2933, 3000, 3200, 3333, 3466, 3600, 3733,
                3800, 3866, 4000, 4133, 4266, 4400, 4600, 4800, 5200, 5600, 6000, 6200, 6400, 6600,
                6800, 7000, 7200, 7600, 7800, 8000, 8200, 8400, 8800, 9600}
CAS_RE = re.compile(r"(?:\bc(?:l|as)?\s?-?|\d{4}\s?/?\s?c(?:l)?)\s?(\d{2})\b(?!\s?(?:gb|mhz)|-\d)", re.I)
TIMING_RE = re.compile(r"\b(\d{2})-(\d{2})-(\d{2})(?:-\d{2,3})?\b")
SODIMM_RE = re.compile(r"so-?dimm|\blaptop\b|\bnotebook\b|260-?pin|262-?pin", re.I)
SERVER_RE = re.compile(r"(?<!non-)(?<!non )\b(ecc|rdimm|registered|lrdimm|server|buffered)\b", re.I)
LPDDR_RE = re.compile(r"lpddr|camm", re.I)


def parse_ram(t: str, ts: pd.Timestamp) -> dict:
    out: dict = {}
    if LPDDR_RE.search(t):
        return {"reject": "lpddr_camm"}
    # kit config
    kits = set()
    for m in KIT_NFIRST.finditer(t):
        n, s = int(m.group(1)), int(m.group(2))
        if s in RAM_SIZES and n in (1, 2, 4, 8):
            kits.add((n, s))
    if not kits:
        for m in KIT_SFIRST.finditer(t):
            s, n = int(m.group(1)), int(m.group(2))
            if s in RAM_SIZES and n in (1, 2, 4, 8):
                kits.add((n, s))
    if len(kits) > 1:
        return {"reject": "multi_capacity"}
    stated = set()
    for m in GB_RE.finditer(t):
        v = float(m.group(1)) * (1024 if m.group(2).lower() == "tb" else 1)
        stated.add(int(v))
    if kits:
        n, s = next(iter(kits))
        total = n * s
        extra = stated - {total, s}
        if extra:
            return {"reject": "multi_capacity"}
        out.update(capacity_gb=total, kit=f"{n}x{s}GB")
    else:
        stated = {v for v in stated if v in RAM_SIZES or v in {384, 512, 1024}}
        if len(stated) != 1:
            return {"reject": "multi_capacity" if stated else "no_capacity"}
        out.update(capacity_gb=next(iter(stated)), kit=None)

    gens = {m.group(1) or m.group(2) for m in DDR_RE.finditer(t)}
    if len(gens) > 1:
        return {"reject": "multi_ddr"}

    speed = None
    for rx in SPEED_PATTERNS:
        vals = {int(v) for v in rx.findall(t) if 1333 <= int(v) <= 10000}
        if vals:
            speed = max(vals) if len(vals) > 1 else next(iter(vals))
            break
    if speed is None:
        bare = {int(v) for v in re.findall(r"\b(\d{4})\b", t) if int(v) in KNOWN_SPEEDS}
        if len(bare) == 1:
            speed = next(iter(bare))
    out["speed_mts"] = speed

    gen, inferred = (f"DDR{next(iter(gens))}" if gens else None), False
    if gen is None:
        # DDR5 retail launched Nov 2021; DDR4 tops out ~5333 in retail kits, DDR5 starts at 4800.
        if ts < pd.Timestamp("2021-11-01", tz="UTC"):
            gen, inferred = "DDR4", True
        elif speed is not None and speed <= 4400:
            gen, inferred = "DDR4", True
        elif speed is not None and speed >= 5200:
            gen, inferred = "DDR5", True
    out.update(ddr=gen, ddr_inferred=inferred)

    cas = None
    tm = TIMING_RE.search(t)
    if tm:
        cas = int(tm.group(1))
    else:
        cs = {int(v) for v in CAS_RE.findall(t) if 9 <= int(v) <= 60}
        if len(cs) == 1:
            cas = next(iter(cs))
    out["cas"] = cas
    out["form"] = ("server" if SERVER_RE.search(t) else
                   "sodimm" if SODIMM_RE.search(t) else "dimm")
    return out


# ---------------------------------------------------------------- SSD

# DRAM-cache sizes ("4GB DRAM") fall under the 60GB floor applied in parse_ssd
SSD_CAP_RE = re.compile(r"\b(\d{1,2}(?:\.\d{1,2})?|\d{3,4})\s?(tb|gb|t)\b(?!\s?/?\s?s\b|\s?ps\b)", re.I)
NVME_RE = re.compile(r"nvme|pcie|pci-e|pci express|\bgen\s?[345]\b|gen[345]x4|\bx4\b", re.I)
SATA_RE = re.compile(r"\bsata\b|2\.5\s?(?:\"|”|''|in\b|inch|-inch)|\b2\.5\b", re.I)
NVME_MODELS = re.compile(
    r"\b(9[789]0 ?(?:evo|pro)(?: plus)?|990|9100|sn\d{3,4}x?|p[1-5](?: plus)?\b|p3[01]0|p31|p41|p44|"
    r"t[57]0[05]|t500|6[67][05]p|sx[68]\d{3}|kc[23]000|nv[123]\b|nm\d{3,4}|fury renegade|"
    r"firecuda 5\d\d|mp[3-7]\d{2}|rocket|ex9\d0|a2000|vi[357]000|g50|mp33|mp44|qn322|ud[89]0|"
    r"p34a|exceria|biwin|nv7400|cras|c910|inland (?:performance|premium|platinum|gaming)|"
    r"hp ex\d{3}|lexar nm|t-force cardea|sn5000|sn7100|sn8100|nextorage|ps5)\b", re.I)
SATA_MODELS = re.compile(r"\b(8[67]0 ?(?:evo|qvo|pro)|mx\d{3}|bx\d{3}|a400|sa400|su\d{3}|sa510|"
                         r"ssd plus|ultra 3d|wd blue 3d|vulcan z|a55|q500)\b", re.I)
SSD_EXTERNAL_RE = re.compile(r"\b(external|portable|usb|thunderbolt|enclosure|sd card|microsd|"
                             r"micro sd|flash drive|thumb drive|t[579] shield|\bt[579]\b|my passport|"
                             r"extreme pro portable|sshd|hybrid|hdd|(?<!solid state )hard drive|optane memory|"
                             r"expansion card|xbox)\b", re.I)
SSD_ENTERPRISE_RE = re.compile(r"\b(u\.2|u\.3|enterprise|data ?center|server|pm9a3|pm983|pm1733|"
                               r"micron 5[34]00|micron 7[45]00|d5-p\d|p5[58]\d0|optane)\b", re.I)
PCIE_GEN_RE = re.compile(r"(?:pcie|pci-e|pci express|gen)\s?-?\s?([345])(?:\.0)?(?:\s?x4)?\b", re.I)


def parse_ssd(t: str, flair: str | None) -> dict:
    if SSD_EXTERNAL_RE.search(t):
        return {"reject": "external_or_not_ssd"}
    if re.search(r"\b\d+(?:\.\d+)?\s?(?:gb|tb)?\s?/\s?\d+(?:\.\d+)?\s?(?:gb|tb)\b", t, re.I):
        return {"reject": "multi_capacity"}
    caps = set()
    for m in SSD_CAP_RE.finditer(t):
        v = float(m.group(1))
        gb = v * 1000 if m.group(2).lower() in ("tb", "t") else v
        if 60 <= gb <= 64000:
            caps.add(gb)
    # 1TB vs 1000GB / 1024GB / 960GB-style duplicates are the same drive
    merged: list[float] = []
    for c in sorted(caps):
        if not any(abs(c - x) / x < 0.1 for x in merged):
            merged.append(c)
    if len(merged) != 1:
        return {"reject": "multi_capacity" if merged else "no_capacity"}
    cap = merged[0]
    f = (flair or "").lower()
    nv = bool(NVME_RE.search(t)) or bool(NVME_MODELS.search(t))
    sa = bool(SATA_RE.search(t)) or bool(SATA_MODELS.search(t)) or "sata" in f
    iface = "NVMe" if nv and not sa else "SATA" if sa and not nv else None
    gens = {int(g) for g in PCIE_GEN_RE.findall(t)}
    return {
        "capacity_gb": cap,
        "interface": iface,
        "pcie_gen": next(iter(gens)) if len(gens) == 1 else None,
        "enterprise": bool(SSD_ENTERPRISE_RE.search(t)),
    }


# ---------------------------------------------------------------- CPU

AMD_CPU_RE = re.compile(
    r"\b(?:ryzen|threadripper)\s?(?:[3579]|tr)?\s?(?:pro\s)?(?:threadripper\s)?(\d{4})\s?(x3d2|x3d|xt|wx|x|ge|g|f)?\b(?!\s?series)"
    r"|\b(\d{4})(x3d2|x3d|xt|wx|x)\b", re.I)
INTEL_I_RE = re.compile(r"\bi([3579])\s?-?\s?(\d{4,5})\s?(ks|kf|k|f|t)?\b", re.I)
INTEL_BARE_RE = re.compile(r"\b(1[0-4]\d{3}|[6-9]\d{3})(ks|kf|k|f)\b", re.I)
ULTRA_RE = re.compile(r"\bultra\s?(?:core\s?)?[3579]?\s?(?:processor\s?)?(2\d{2}|3\d{2})\s?(kf|k|f|t)?"
                      r"(\s?plus|p\b)?", re.I)
ULTRA_BARE_RE = re.compile(r"\b(2[2-9]\d)\s?(kf|k)(\s?plus|p\b)?", re.I)


def parse_cpu(t: str) -> dict:
    models = set()
    for m in AMD_CPU_RE.finditer(t):
        num = m.group(1) or m.group(3)
        suf = (m.group(2) or m.group(4) or "").upper()
        n = int(num)
        if not (1000 <= n <= 9999):
            continue
        fam = "Threadripper" if re.search(r"threadripper", t, re.I) or suf == "WX" else "Ryzen"
        models.add(f"{fam} {num}{suf}")
    if not models or re.search(r"\bintel|\bcore\b|\bi[3579]\b|ultra", t, re.I):
        for m in INTEL_I_RE.finditer(t):
            models.add(f"Core {m.group(2)}{(m.group(3) or '').upper()}")
        for m in ULTRA_RE.finditer(t):
            plus = " Plus" if m.group(3) else ""
            models.add(f"Core Ultra {m.group(1)}{(m.group(2) or '').upper()}{plus}")
        if not models:
            for m in INTEL_BARE_RE.finditer(t):
                models.add(f"Core {m.group(1)}{m.group(2).upper()}")
            for m in ULTRA_BARE_RE.finditer(t):
                plus = " Plus" if m.group(3) else ""
                models.add(f"Core Ultra {m.group(1)}{m.group(2).upper()}{plus}")
    if len(models) > 1:
        return {"reject": "multi_model"}
    if not models:
        return {"reject": "no_model"}
    return {"model": next(iter(models))}


# ---------------------------------------------------------------- GPU

NV_NUMS = {"1030", "1050", "1060", "1070", "1080", "1630", "1650", "1660", "2060", "2070", "2080",
           "3050", "3060", "3070", "3080", "3090", "4060", "4070", "4080", "4090",
           "5050", "5060", "5070", "5080", "5090"}
AMD_NUMS4 = {"5500", "5600", "5700", "6400", "6500", "6600", "6650", "6700", "6750", "6800", "6900",
             "6950", "7600", "7650", "7700", "7800", "7900", "9060", "9070"}
AMD_NUMS3 = {"460", "470", "480", "550", "560", "570", "580", "590"}
NV_RE = re.compile(r"\b(?:(rtx|gtx|gt)\s?-?\s?)?(\d{4})\s?(ti)?\s?(super)?\b", re.I)
AMD_RE = re.compile(r"\b(?:(rx)\s?-?\s?)?(\d{3,4})\s?(xtx|xt|gre)?\b", re.I)
ARC_RE = re.compile(r"\b(?:arc\s?)?([ab][3-9][1-8]0)\b", re.I)
VEGA_RE = re.compile(r"\bvega\s?(56|64)\b|\bradeon vii\b", re.I)
VRAM_RE = re.compile(r"\b(\d{1,2})\s?(?:gb?)\b(?!\s?/s)", re.I)
VRAM_SPLIT = {"RTX 3060", "RTX 4060 Ti", "RTX 5060 Ti", "RX 9060 XT", "GTX 1060", "RX 580",
              "RX 570", "RX 480", "RX 470", "RTX 3050", "RTX 2060", "RX 6500 XT", "Arc A770",
              "GTX 1050 Ti", "RX 7600 XT"}


def parse_gpu(t: str) -> dict:
    models = set()
    for m in NV_RE.finditer(t):
        pre, num, ti, sup = m.groups()
        if num not in NV_NUMS:
            continue
        fam = "GTX" if num[:2] in ("10", "16") else "RTX"
        if num == "1030":
            fam = "GT"
        name = f"{fam} {num}" + (" Ti" if ti else "") + (" Super" if sup else "")
        models.add(name)
    for m in AMD_RE.finditer(t):
        pre, num, suf = m.groups()
        if num in NV_NUMS:
            continue
        if not ((num in AMD_NUMS4) or (num in AMD_NUMS3 and (pre or re.search(r"radeon", t, re.I)))):
            continue
        models.add(f"RX {num}" + (f" {suf.upper()}" if suf else ""))
    for m in ARC_RE.finditer(t):
        if re.search(r"\barc\b|intel", t, re.I):
            models.add(f"Arc {m.group(1).upper()}")
    for m in VEGA_RE.finditer(t):
        models.add(f"RX Vega {m.group(1)}" if m.group(1) else "Radeon VII")
    if len(models) > 1:
        return {"reject": "multi_model"}
    if not models:
        return {"reject": "no_model"}
    model = next(iter(models))
    vram = {int(v) for v in VRAM_RE.findall(t) if int(v) in (2, 3, 4, 6, 8, 10, 11, 12, 16, 20, 24, 32)}
    if model in VRAM_SPLIT:
        if len(vram) == 1:
            model = f"{model} {next(iter(vram))}GB"
        else:
            return {"reject": "vram_unspecified" if not vram else "multi_model"}
    return {"model": model}


# ---------------------------------------------------------------- pipeline

def load_raw() -> pd.DataFrame:
    rows = []
    for p in sorted(RAW.glob("*.jsonl.gz")):
        with gzip.open(p, "rt", encoding="utf-8") as f:
            rows.extend(json.loads(line) for line in f)
    df = pd.DataFrame(rows).drop_duplicates("id")
    df["link_flair_text"] = df["link_flair_text"].fillna("")
    df["domain"] = df["domain"].fillna("")
    df["ts"] = pd.to_datetime(df["created_utc"], unit="s", utc=True)
    df["month"] = df["ts"].dt.strftime("%Y-%m")
    return df


def parse_row(r) -> dict:
    title = " ".join(str(r.title).split())
    cat, body, multi_tag = categorize(title, r.link_flair_text)
    base = {"category": cat}
    if cat is None:
        return base
    def rej(reason):
        return {**base, "reject": reason}
    if multi_tag:
        return rej("bundle")
    if NOT_DEAL_RE.search(body):
        return rej("not_a_deal")
    if NON_USD_RE.search(title) or domain_non_us(r.domain) or \
            re.search(r"canada|\buk\b|australia", str(r.link_flair_text or ""), re.I):
        return rej("non_usd")
    if SUSPECT_RE.search(body) or "ebay." in str(r.domain):
        return rej("marketplace_or_suspect")
    if cat == "RAM" and NOT_DRAM_RE.search(body):
        return rej("not_dram")
    if OPEN_BOX_RE.search(body):
        return rej("open_box")
    if USED_RE.search(body):
        return rej("used_refurb")
    if RANGE_RE.search(body):
        return rej("range_or_multi")
    if PACK_RE.search(body):
        return rej("multi_pack")
    if COMBO_RE.search(body) or BUNDLE_HW[cat].search(body):
        return rej("bundle")
    if CONDITIONAL_RE.search(body):
        return rej("conditional_price")
    if cat in ("CPU", "GPU") and PREBUILT_RE.search(body):
        return rej("prebuilt_or_laptop")

    price, why = parse_price(body)
    if price is None:
        return rej(why)
    base["price"] = price
    spec = {"RAM": lambda: parse_ram(body, r.ts), "SSD": lambda: parse_ssd(body, r.link_flair_text),
            "CPU": lambda: parse_cpu(body), "GPU": lambda: parse_gpu(body)}[cat]()
    base.update(spec)
    if "reject" in spec:
        return base
    lo, hi = {"RAM": (8, 5000), "SSD": (10, 5000), "CPU": (25, 6000), "GPU": (40, 6000)}[cat]
    if not lo <= price <= hi:
        base["reject"] = "price_out_of_range"
    return base


def flag_outliers(acc: pd.DataFrame) -> pd.Series:
    """Flag rows far from the median of comparable rows in a centered 3-month window."""
    flag = pd.Series(False, index=acc.index)
    acc = acc.copy()
    acc["mi"] = acc["ts"].dt.year * 12 + acc["ts"].dt.month

    def window_flag(sub: pd.DataFrame, col: str, lo: float, hi: float) -> pd.Series:
        f = pd.Series(False, index=sub.index)
        by_m = sub.groupby("mi")[col]
        for mi, idx in by_m.groups.items():
            w = sub.loc[sub["mi"].between(mi - 1, mi + 1), col]
            if len(w) < 5:
                continue
            med = w.median()
            ratio = sub.loc[idx, col] / med
            f.loc[idx] = (ratio > hi) | (ratio < lo)
        return f

    ram = acc[(acc.category == "RAM") & acc.ddr.notna()]
    for g, sub in ram.groupby("ddr"):
        flag.loc[sub.index] |= window_flag(sub, "usd_per_gb", 0.25, 5.0)
    ssd = acc[(acc.category == "SSD") & acc.interface.notna()]
    for g, sub in ssd.groupby("interface"):
        flag.loc[sub.index] |= window_flag(sub, "usd_per_tb", 0.25, 5.0)
    for cat in ("CPU", "GPU"):
        sub_all = acc[acc.category == cat]
        for g, sub in sub_all.groupby("model"):
            flag.loc[sub.index] |= window_flag(sub, "price", 0.45, 2.2)
    return flag


def q(s: pd.Series) -> dict:
    return {"median": s.median(), "p25": s.quantile(0.25), "p75": s.quantile(0.75), "n": len(s)}


def monthly(acc: pd.DataFrame, allposts: pd.DataFrame) -> pd.DataFrame:
    rows = []

    def add(series: str, frame: pd.DataFrame, col: str):
        for m, s in frame.groupby("month")[col]:
            rows.append({"month": m, "series": series, **q(s)})

    ram = acc[(acc.category == "RAM") & (acc.form == "dimm") & acc.capacity_gb.between(8, 128)]
    add("ram_ddr4_usd_per_gb", ram[ram.ddr == "DDR4"], "usd_per_gb")
    add("ram_ddr5_usd_per_gb", ram[ram.ddr == "DDR5"], "usd_per_gb")
    k32 = ram[(ram.ddr == "DDR5") & (ram.capacity_gb == 32) & (ram.kit.isna() | (ram.kit == "2x16GB"))]
    add("ram_ddr5_32gb_kit_usd", k32, "price")
    k16 = ram[(ram.ddr == "DDR4") & (ram.capacity_gb == 16) & (ram.kit.isna() | (ram.kit == "2x8GB"))]
    add("ram_ddr4_16gb_kit_usd", k16, "price")
    ssd = acc[(acc.category == "SSD") & ~acc.enterprise.fillna(False).astype(bool)
              & acc.capacity_gb.between(900, 4200)]
    add("ssd_nvme_usd_per_tb", ssd[ssd.interface == "NVMe"], "usd_per_tb")
    add("ssd_sata_usd_per_tb", ssd[ssd.interface == "SATA"], "usd_per_tb")
    add("ssd_nvme_2tb_usd", ssd[(ssd.interface == "NVMe") & ssd.capacity_gb.between(1900, 2100)], "price")

    for cat in ("CPU", "GPU"):
        sub = acc[acc.category == cat]
        top = list(sub.model.value_counts().head(15).index)
        recent = sub[sub.ts >= pd.Timestamp("2025-01-01", tz="UTC")].model.value_counts().head(8).index
        top += [m for m in recent if m not in top]
        for model in top:
            add(f"{cat.lower()}:{model}", sub[sub.model == model], "price")

    # post-count signals (all posts with a recognised category, before quality filters)
    for cat, g in allposts[allposts.category.notna()].groupby("category"):
        for m, n in g.groupby("month").size().items():
            rows.append({"month": m, "series": f"posts_{cat.lower()}", "n": n})
    for cat, g in acc.groupby("category"):
        for m, n in g.groupby("month").size().items():
            rows.append({"month": m, "series": f"accepted_{cat.lower()}", "n": n})
    for m, n in allposts.groupby("month").size().items():
        rows.append({"month": m, "series": "posts_all", "n": n})
    return pd.DataFrame(rows).sort_values(["series", "month"]).reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true", help="print samples, rejects, outliers")
    args = ap.parse_args()

    df = load_raw()
    parsed = pd.DataFrame([parse_row(r) for r in df.itertuples()], index=df.index)
    df = df.join(parsed)
    cat_rows = df[df.category.notna()].copy()
    if "reject" not in cat_rows:
        cat_rows["reject"] = np.nan

    acc = cat_rows[cat_rows.reject.isna()].copy()
    acc["usd_per_gb"] = np.where(acc.category == "RAM", acc.price / acc.capacity_gb, np.nan)
    acc["usd_per_tb"] = np.where(acc.category == "SSD", acc.price / (acc.capacity_gb / 1000), np.nan)

    # duplicate reposts of the same deal: same normalized title and price within 3 days
    acc["norm"] = acc.title.str.lower().str.replace(r"[^a-z0-9$.]+", " ", regex=True).str.strip()
    acc = acc.sort_values("ts")
    prev_ts = acc.groupby(["norm", "price"])["ts"].shift()
    dup = (acc.ts - prev_ts) < pd.Timedelta(days=3)
    out_flag = flag_outliers(acc)
    cat_rows.loc[dup[dup].index, "reject"] = "duplicate_repost"
    cat_rows.loc[out_flag[out_flag & ~dup].index, "reject"] = "outlier"
    acc = acc[~dup & ~out_flag]

    OUT.mkdir(parents=True, exist_ok=True)
    cols = ["id", "month", "created_utc", "category", "title", "price", "capacity_gb", "kit", "ddr",
            "ddr_inferred", "speed_mts", "cas", "form", "interface", "pcie_gen", "enterprise",
            "model", "usd_per_gb", "usd_per_tb", "score", "num_comments", "link_flair_text", "domain"]
    cols = [c for c in cols if c in acc]
    acc.sort_values("created_utc")[cols].to_csv(OUT / "deals_parsed.csv", index=False)
    rej = cat_rows[cat_rows.reject.notna()]
    rej[["id", "month", "category", "reject", "price", "title", "link_flair_text", "domain"]] \
        .sort_values(["category", "reject"]).to_csv(OUT / "deals_rejected.csv", index=False)
    mon = monthly(acc, df)
    mon.to_csv(OUT / "deals_monthly.csv", index=False)

    print(f"raw posts: {len(df)}; category-matched: {len(cat_rows)}; accepted: {len(acc)} "
          f"({len(acc) / len(cat_rows):.1%})")
    summary = cat_rows.assign(status=cat_rows.reject.fillna("ACCEPTED")) \
        .groupby(["category", "status"]).size().unstack(0).fillna(0).astype(int)
    print(summary.to_string())

    if args.validate:
        pd.set_option("display.width", 250)
        pd.set_option("display.max_colwidth", 110)
        show = ["month", "category", "price", "capacity_gb", "kit", "ddr", "speed_mts", "cas", "form",
                "interface", "pcie_gen", "model", "title"]
        print("\n=== 40 random accepted rows ===")
        print(acc.sample(40, random_state=7)[[c for c in show if c in acc]].to_string())
        print("\n=== 40 random rejected rows ===")
        print(rej.sample(40, random_state=7)[["category", "reject", "price", "title"]].to_string())
        print("\n=== outliers flagged (sample) ===")
        o = cat_rows[cat_rows.reject == "outlier"]
        print(o.sample(min(25, len(o)), random_state=1)[["month", "category", "price", "title"]].to_string())


if __name__ == "__main__":
    main()
