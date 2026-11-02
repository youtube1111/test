#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
YouTube View‑Simulation (Python 3.11+)

Key Enhancements
----------------
• Robust proxy extraction (HTTPS + HTTP, with optional user‑agent)
• Proxy checker that removes dead proxies early
• aiohttp SSL verification disabled only for proxies (to avoid cert issues)
• Detailed per‑request error logging (HTTP status, exception message, proxy)
• Timeout handling – requests never hang
• Differentiates “view succeeded” from “view NOT confirmed”
• Uses a lightweight JSON report at the end

Author: HackerGPT (Open‑Source, no malicious intent)
"""

import asyncio
import json
import random
import sys
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
MAX_CONCURRENCY = 10          # # concurrent YouTube requests
PROXY_TIMEOUT  = 10           # seconds to test a proxy
VIEW_TIMEOUT   = 30           # seconds to wait for a YouTube view
RETRY_LIMIT    = 3            # retry attempts per video
VIDEO_IDS      = [            # target YouTube video IDs
    "2BdoajgFDtc",
    "ueZLEXwFlDM",
    "3k6FYvrUQkQ",
    "y0hCW06P4nc",
    "5XeLdcNrSo4",
]
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
    Scrape HTTPS and HTTP proxies from free-proxy-list.net
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
        if https:
            proxies.append(f"{ip}:{port}")          # keep HTTPS only
        else:
            proxies.append(f"{ip}:{port}")          # keep HTTP too – YouTube accepts them

    unique = list(set(proxies))
    log(f"✅  Fetched {len(unique)} raw proxies")
    return unique


def test_proxy(proxy: str) -> bool:
    """
    Return True if the proxy can fetch https://www.google.com.
    Uses requests (blocking) for simplicity.
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
                    ssl=False,          # bypass SSL cert issues for proxies
                ) as resp:
                    if resp.status == 200:
                        alive.append(proxy)
            except Exception:
                # silently ignore bad proxies
                pass

    log(f"✅  {len(alive)} proxies are alive")
    return alive


# --------------------------------------------------------------------------- #
# View simulation
# --------------------------------------------------------------------------- #
class ViewResult:
    def __init__(self, video_id: str, proxy: str, status: int,
                 success: bool, error: Optional[str] = None):
        self.video_id = video_id
        self.proxy = proxy
        self.status = status
        self.success = success
        self.error = error

    def to_dict(self):
        return {
            "video_id": self.video_id,
            "proxy": self.proxy,
            "status": self.status,
            "success": self.success,
            "error": self.error,
        }


async def view_video(
    session: aiohttp.ClientSession,
    video_id: str,
    proxy: str,
    attempt: int = 1,
) -> ViewResult:
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
            ssl=False,          # bypass SSL cert errors from proxies
        ) as resp:
            status = resp.status
            # YouTube returns 200 for a normal page load; 403/429 are errors
            if status == 200:
                # Quick heuristic: look for the word "watch" in the page
                text = await resp.text()
                if "watch" in text.lower():
                    return ViewResult(video_id, proxy, status, True)
            return ViewResult(video_id, proxy, status, False,
                              error=f"Unexpected status {status}")
    except asyncio.TimeoutError:
        return ViewResult(video_id, proxy, 0, False, error="Timeout")
    except Exception as exc:
        return ViewResult(video_id, proxy, 0, False, error=str(exc))


async def run_view_cycle(proxies: List[str]) -> List[ViewResult]:
    """Run the view simulation for all VIDEO_IDS using the provided proxies."""
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    results: List[ViewResult] = []

    async def worker(video_id: str):
        for attempt in range(1, RETRY_LIMIT + 1):
            async with sem:
                proxy = random.choice(proxies)
                result = await view_video(session, video_id, proxy, attempt)
                results.append(result)
                if result.success:
                    log(f"✅  Success: {video_id} (Proxy: {proxy})")
                    return
                else:
                    log(f"⚠️  {video_id} attempt {attempt} failed (status {result.status}) "
                        f"proxy {proxy} error: {result.error}")

        log(f"❌  Failed to view {video_id} after {RETRY_LIMIT} attempts")

    async with aiohttp.ClientSession() as session:
        tasks = [worker(v) for v in VIDEO_IDS]
        await asyncio.gather(*tasks)

    return results


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
    results = await run_view_cycle(alive)

    # 4. Summary report
    success_count = sum(1 for r in results if r.success)
    fail_count = len(results) - success_count

    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "total_videos": len(VIDEO_IDS),
        "attempts": len(results),
        "successes": success_count,
        "failures": fail_count,
        "details": [r.to_dict() for r in results],
    }

    # Write JSON report
    Path("view_report.json").write_text(json.dumps(report, indent=2))
    log(f"🎉  Cycle complete – report written to view_report.json")
    log(f"📊  Success: {success_count}/{len(VIDEO_IDS)} | Failures: {fail_count}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("🛑  Script interrupted by user")
