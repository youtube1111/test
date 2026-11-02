#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
YouTube view‑simulation script (Python 3.11+)

Features
--------
•  Scrapes free public HTTP/HTTPS proxies from proxyscan.io
•  Health‑checks each proxy (simple GET to https://www.google.com)
•  Rotates realistic User‑Agent strings
•  Uses aiohttp for concurrent HTTP requests
•  Handles 403/timeout errors and retries with a fresh proxy
•  Logs every step in a clear, timestamped format
•  Works with both HTTP and HTTPS proxies

Requirements
------------
pip install aiohttp requests tqdm beautifulsoup4
"""

import asyncio
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import aiohttp
import requests
from tqdm import tqdm

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
MAX_CONCURRENCY = 5          # number of simultaneous requests
PROXY_TIMEOUT  = 10          # seconds to wait for a proxy test
VIEW_TIMEOUT   = 30          # seconds to wait for a view request
RETRY_LIMIT    = 3           # how many times to retry a video with a new proxy
VIDEO_IDS      = [           # list of YouTube video IDs to view
    "2BdoajgFDtc",
    "ueZLEXwFlDM",
    "3k6FYvrUQkQ",
    "y0hCW06P4nc",
    "5XeLdcNrSo4",
]  # replace or extend this list as needed

# realistic user‑agents (Chrome/Edge/Firefox on Windows 10)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:119.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edge/121.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
]

# --------------------------------------------------------------------------- #
# Logging helpers
# --------------------------------------------------------------------------- #
def log(msg: str) -> None:
    """Print a timestamped log line."""
    print(f"{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} - {msg}")


# --------------------------------------------------------------------------- #
# Proxy utilities
# --------------------------------------------------------------------------- #
async def fetch_proxies() -> List[str]:
    """
    Scrape HTTPS and HTTP proxies from proxyscan.io.

    The function uses a context‑managed ClientSession so the session
    is closed automatically.  A realistic User‑Agent header is added
    to avoid being blocked.
    """
    urls = [
        "https://www.proxyscan.io/proxy/list?type=https",
        "https://www.proxyscan.io/proxy/list?type=http",
    ]

    proxies: List[str] = []

    for url in urls:
        try:
            # Context‑managed session – it will be closed automatically
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=15,
                    headers={"User-Agent": random.choice(USER_AGENTS)},
                ) as r:
                    text = await r.text()
        except Exception as exc:
            log(f"⚠️  Failed to fetch proxy list from {url}: {exc}")
            continue

        # -------------------------------------------------------------------
        # 1️⃣  Regex approach – works for the current layout of proxyscan.io
        # -------------------------------------------------------------------
        found = re.findall(r'(\d{1,3}(?:\.\d{1,3}){3}:\d{1,5})', text)
        proxies.extend(found)

        # -------------------------------------------------------------------
        # 2️⃣  BeautifulSoup fallback (uncomment if the regex returns 0)
        # -------------------------------------------------------------------
        # from bs4 import BeautifulSoup
        # soup = BeautifulSoup(text, "html.parser")
        # rows = soup.select("table.proxylist tr")   # adjust selector if needed
        # for row in rows:
        #     cells = row.find_all("td")
        #     if len(cells) >= 2:
        #         ip = cells[0].get_text(strip=True)
        #         port = cells[1].get_text(strip=True)
        #         proxies.append(f"{ip}:{port}")

    # Deduplicate and return
    unique = list(set(proxies))
    log(f"✅  Fetched {len(unique)} raw proxies")
    return unique


def test_proxy(proxy: str) -> bool:
    """
    Return True if the proxy can fetch https://www.google.com.
    (Synchronous version – uses requests.)
    """
    try:
        resp = requests.get(
            "https://www.google.com",
            proxies={"http": f"http://{proxy}", "https": f"http://{proxy}"},
            timeout=PROXY_TIMEOUT,
        )
        return resp.status_code == 200
    except Exception:
        return False


async def filter_proxies(raw_proxies: List[str]) -> List[str]:
    """
    Filter the raw proxy list to only those that are alive.
    Uses an async health‑check against https://www.google.com.
    """
    log("🔎  Testing proxies for liveliness (may take a few minutes)...")

    alive: List[str] = []
    async with aiohttp.ClientSession() as session:
        for proxy in tqdm(raw_proxies, desc="Proxy tests", unit="proxy"):
            try:
                async with session.get(
                    "https://www.google.com",
                    proxy=f"http://{proxy}",
                    timeout=aiohttp.ClientTimeout(total=PROXY_TIMEOUT),
                ) as resp:
                    if resp.status == 200:
                        alive.append(proxy)
            except Exception:
                pass

    log(f"✅  {len(alive)} proxies are alive")
    return alive


# --------------------------------------------------------------------------- #
# View simulation
# --------------------------------------------------------------------------- #
async def view_video(
    session: aiohttp.ClientSession,
    video_id: str,
    proxy: str,
    attempt: int = 1,
) -> Optional[str]:
    """Try to view a YouTube video once using the given proxy."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Referer": "https://www.youtube.com/",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        async with session.get(
            url,
            headers=headers,
            proxy=f"http://{proxy}",
            timeout=aiohttp.ClientTimeout(total=VIEW_TIMEOUT),
        ) as resp:
            if resp.status == 200:
                log(f"✅ Success: {video_id} (Proxy: {proxy})")
                return proxy
            else:
                log(f"⚠️  {video_id} returned {resp.status} (attempt {attempt})")
                return None

    except Exception as exc:
        log(f"❌  Error fetching {video_id} with {proxy}: {exc}")
        return None


async def run_view_cycle(proxies: List[str]) -> None:
    """Run the view simulation for all VIDEO_IDS using the provided proxies."""
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    async def worker(video_id: str):
        for attempt in range(1, RETRY_LIMIT + 1):
            async with sem:
                proxy = random.choice(proxies)
                result = await view_video(session, video_id, proxy, attempt)
                if result:
                    return
        log(f"❌  Failed to view {video_id} after {RETRY_LIMIT} attempts")

    async with aiohttp.ClientSession() as session:
        tasks = [worker(v) for v in VIDEO_IDS]
        await asyncio.gather(*tasks)


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #
async def main() -> None:
    log("🚀  Starting YouTube view simulation script")

    # 1. Grab raw proxies
    raw = await fetch_proxies()
    if not raw:
        log("❌  No proxies fetched – aborting")
        return

    # 2. Filter for alive proxies
    alive = await filter_proxies(raw)
    if not alive:
        log("❌  No alive proxies – aborting")
        return

    # 3. Run the view cycle
    await run_view_cycle(alive)

    log("🎉  Cycle complete – script finished.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("🛑  Script interrupted by user")
