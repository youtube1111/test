#!/usr/bin/env python3
import os
import random
import time
import logging
import asyncio
import aiohttp
import sys
from urllib.parse import urljoin

# ------------------------------------------------------------------
# تنظیمات
# ------------------------------------------------------------------
YOUTUBE_BASE = "https://www.youtube.com/watch?v="
PROXY_FILE   = "proxies.txt"
DEFAULT_TIMEOUT = 30
VIEW_DURATION = 300          # 5 دقیقه به ثانیه (برای هر ویدیو)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def load_proxies() -> list[str]:
    if not os.path.exists(PROXY_FILE):
        logging.warning(f"Proxy file {PROXY_FILE} not found.")
        return []
    with open(PROXY_FILE) as f:
        return [line.strip() for line in f if line.strip()]

def get_random_proxy(proxies: list[str]) -> str | None:
    return random.choice(proxies) if proxies else None

async def fetch_video(video_id: str, proxy: str | None, session: aiohttp.ClientSession) -> bool:
    url = f"{YOUTUBE_BASE}{video_id}"
    proxy_url = f"http://{proxy}" if proxy else None
    headers = {
        "User-Agent": random.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        ])
    }

    try:
        logging.info(f"🚀 Starting view simulation for {video_id}…")
        async with session.get(url, proxy=proxy_url, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)) as resp:
            if resp.status == 200:
                logging.info(f"✅ Success: {video_id} (Proxy: {proxy or 'Direct'})")
                logging.info(f"⏳ Waiting {VIEW_DURATION // 60} minutes for {video_id} to register as a view…")
                await asyncio.sleep(VIEW_DURATION)      # 5 دقیقه
                return True
            else:
                logging.warning(f"⚠️ {video_id} returned status {resp.status}")
                return False
    except Exception as exc:
        logging.error(f"❌ Error fetching {video_id}: {exc}")
        return False

async def run_cycle(video_ids: list[str], proxies: list[str]):
    async with aiohttp.ClientSession() as session:
        tasks = [asyncio.create_task(fetch_video(vid, get_random_proxy(proxies), session))
                 for vid in video_ids]
        await asyncio.gather(*tasks)

def main():
    video_ids = ["2BdoajgFDtc", "ueZLEXwFlDM", "3k6FYvrUQkQ",
                 "y0hCW06P4nc", "5XeLdcNrSo4"]
    proxies = load_proxies()

    logging.info("Starting automated view script with 5‑minute duration per video.")
    try:
        # یک چرخه فقط
        asyncio.run(run_cycle(video_ids, proxies))
        logging.info("Cycle complete – script finished.")
    except KeyboardInterrupt:
        logging.info("Script stopped by user.")
    finally:
        sys.exit(0)          # خروج صریح

if __name__ == "__main__":
    main()
