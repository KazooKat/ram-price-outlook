"""Shared helpers for fetch scripts.

Every fetch script writes to data/raw/<source>/ and records where the data
came from and when in data/raw/<source>/SOURCE.md.
"""
from __future__ import annotations

import datetime as dt
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

USER_AGENT = "ram-price-outlook research (github.com/KazooKat/ram-price-outlook)"

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT


def raw_dir(source: str) -> Path:
    d = RAW / source
    d.mkdir(parents=True, exist_ok=True)
    return d


def get(url: str, *, params=None, headers=None, retries: int = 4, backoff: float = 3.0,
        timeout: float = 60.0) -> requests.Response:
    """GET with retry on 429/5xx and connection errors."""
    last = None
    for attempt in range(retries):
        try:
            r = _session.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504):
                last = RuntimeError(f"HTTP {r.status_code} for {r.url}")
                time.sleep(backoff * (2 ** attempt))
                continue
            r.raise_for_status()
            return r
        except requests.ConnectionError as e:
            last = e
            time.sleep(backoff * (2 ** attempt))
    raise RuntimeError(f"GET failed after {retries} tries: {url}") from last


def write_source_note(source: str, *, title: str, urls: list[str], notes: str = "") -> None:
    """Record provenance for a raw dataset."""
    d = raw_dir(source)
    lines = [
        f"# {title}",
        "",
        f"Fetched: {dt.date.today().isoformat()}",
        "",
        "Sources:",
        *[f"- {u}" for u in urls],
    ]
    if notes:
        lines += ["", notes.strip()]
    (d / "SOURCE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
