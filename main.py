#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
YouTube view‑simulation script (Python 3.11+)

Features
--------
• Scrapes free public HTTP/HTTPS proxies from free-proxy-list.net
• Health‑checks each proxy (simple GET to https://www.google.com)
• Rotates realistic User‑Agent strings
• Uses aiohttp for concurrent HTTP requests
• Handles 403/timeout errors and retries with a fresh proxy
• Logs every step in a clear, timestamped format
• Works with both HTTP and HTTPS proxies

Requirements
------------
pip install aiohttp requests bs4 tqdm
"""

import asyncio
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import aiohttp
import requests
from bs4 import BeautifulSoup
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
    Scrape HTTPS and HTTP proxies from free-proxy-list.net.
    Returns a list of strings in the form 'ip:port'.
    """
    url = "https://free-proxy-list.net/"
    proxies: List[str] = []

    # Cloudflare protection – send a realistic User‑Agent
    headers = {"User-Agent": random.choice(USER_AGENTS)}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=15) as r:
                text = await r.text()
    except Exception as exc:
        log(f"⚠️  Failed to fetch proxy list from {url}: {exc}")
        return proxies

    soup = BeautifulSoup(text, "html.parser")
    rows = soup.select("#proxylisttable tbody tr")
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 7:
            continue
        ip = cols[0].text.strip()
        port = cols[1].text.strip()
        https = cols[6].text.strip().lower() == "yes"
        if https:  # keep only HTTPS proxies – they usually work with YouTube
            proxies.append(f"{ip}:{port}")

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
    if not raw_proxies:
        return []

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
            proxy=f"http://{proxy}",  # use HTTP proxy (works for HTTPS URLs)
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
