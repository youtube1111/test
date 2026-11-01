#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import random
import time
import logging
import asyncio
import aiohttp
import sys
import traceback
from urllib.parse import urljoin

# ------------------------------------------------------------------
# تنظیمات
# ------------------------------------------------------------------
YOUTUBE_BASE   = "https://www.youtube.com/watch?v="
DEFAULT_TIMEOUT = 30
VIEW_DURATION   = 300          # 5 دقیقه به ثانیه (برای هر ویدیو)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ------------------------------------------------------------------
# Helpers – دریافت پراکسی از free‑proxy‑list.net
# ------------------------------------------------------------------
from bs4 import BeautifulSoup

async def fetch_proxies_from_url(session: aiohttp.ClientSession, url: str) -> list[str]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                print(f"[WARN] {url} returned {resp.status}")
                return []

            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            table = soup.find("table")
            if not table:
                print(f"[WARN] No table found on {url}")
                return []

            proxies = []
            for row in table.tbody.find_all("tr"):
                cols = row.find_all("td")
                if len(cols) < 2:
                    continue
                ip = cols[0].text.strip()
                port = cols[1].text.strip()
                proxies.append(f"{ip}:{port}")

            return proxies
    except Exception as exc:
        print(f"[ERROR] Failed to fetch proxies from {url}: {exc}")
        return []

async def gather_all_proxies() -> list[str]:
    urls = [
        "https://free-proxy-list.net/ssl-proxy.html",  # HTTPS proxies
        "https://free-proxy-list.net/",                # HTTP proxies
    ]

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_proxies_from_url(session, url) for url in urls]
        results = await asyncio.gather(*tasks)

    all_proxies = {p for sublist in results for p in sublist}
    return list(all_proxies)

def load_proxies() -> list[str]:
    """تابع هم‌زمان که در main() فراخوانی می‌شود."""
    return asyncio.run(load_proxies_async())

async def load_proxies_async() -> list[str]:
    proxies = await gather_all_proxies()
    print(f"[INFO] Fetched {len(proxies)} proxies from the web")
    return proxies

# ------------------------------------------------------------------
# Helpers – بررسی صحت پراکسی
# ------------------------------------------------------------------
async def is_proxy_working(proxy: str, session: aiohttp.ClientSession) -> bool:
    test_url = "https://api.ipify.org?format=json"
    proxy_url = f"http://{proxy}"          # فرضی: فقط http://host:port

    try:
        async with session.get(
            test_url,
            proxy=proxy_url,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                logging.debug(f"Proxy {proxy} returned IP {data.get('ip')}")
                return True
            else:
                logging.debug(f"Proxy {proxy} returned status {resp.status}")
                return False
    except Exception as e:
        logging.debug(f"Proxy {proxy} failed: {e}")
        return False

# ------------------------------------------------------------------
# Helpers – دانلود ویدیو (شبیه‌سازی view)
# ------------------------------------------------------------------
async def fetch_video(video_id: str, proxy: str | None, session: aiohttp.ClientSession) -> bool:
    url = f"{YOUTUBE_BASE}{video_id}"
    proxy_url = f"http://{proxy}" if proxy else None

    logging.info(f"🚀 Starting view simulation for {video_id}…")
    logging.debug(f"    Proxy URL: {proxy_url}")

    headers = {
        "User-Agent": random.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        ])
    }

    try:
        async with session.get(
            url,
            proxy=proxy_url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)
        ) as resp:
            if resp.status == 200:
                logging.info(f"✅ Success: {video_id} (Proxy: {proxy or 'Direct'})")
                logging.info(f"⏳ Waiting {VIEW_DURATION // 60} minutes for {video_id} to register as a view…")
                await asyncio.sleep(VIEW_DURATION)
                return True
            else:
                logging.warning(f"⚠️ {video_id} returned status {resp.status}")
                return False
    except Exception as exc:
        logging.error(f"❌ Error fetching {video_id}: {exc}")
        logging.debug(traceback.format_exc())
        return False

# ------------------------------------------------------------------
# Helpers – اجرای هم‌زمان
# ------------------------------------------------------------------
async def run_cycle(video_ids: list[str], proxies: list[str]):
    semaphore = asyncio.Semaphore(5)  # حداکثر 5 درخواست همزمان

    async with aiohttp.ClientSession() as session:
        # 1️⃣  پیش‌بررسی تمام پراکسی‌ها
        valid_proxies = []
        for p in proxies:
            if await is_proxy_working(p, session):
                valid_proxies.append(p)
            else:
                logging.info(f"Proxy {p} discarded – not working")

        if not valid_proxies:
            logging.warning("No working proxies found – falling back to direct connections.")
            valid_proxies = [None]

        # 2️⃣  اجرای واقعی
        async def sem_task(vid):
            async with semaphore:
                proxy = random.choice(valid_proxies) if valid_proxies else None
                return await fetch_video(vid, proxy, session)

        tasks = [asyncio.create_task(sem_task(vid)) for vid in video_ids]
        await asyncio.gather(*tasks)

# ------------------------------------------------------------------
# main()
# ------------------------------------------------------------------
def main():
    # 1️⃣  دریافت پراکسی‌های تازه از وب
    proxies = load_proxies()

    # 2️⃣  لیست ویدیوهای مورد نظر
    video_ids = [
        "2BdoajgFDtc", "ueZLEXwFlDM", "3k6FYvrUQkQ",
        "y0hCW06P4nc", "5XeLdcNrSo4"
    ]

    # 3️⃣  چاپ متغیرهای محیطی برای تشخیص مشکل
    logging.debug(f"HTTP_PROXY={os.getenv('HTTP_PROXY')}")
    logging.debug(f"HTTPS_PROXY={os.getenv('HTTPS_PROXY')}")
    logging.debug(f"ALL_PROXY={os.getenv('ALL_PROXY')}")

    logging.info("Starting automated view script with 5‑minute duration per video.")
    try:
        asyncio.run(run_cycle(video_ids, proxies))
        logging.info("Cycle complete – script finished.")
    except KeyboardInterrupt:
        logging.info("Script stopped by user.")
    finally:
        sys.exit(0)

if __name__ == "__main__":
    main()
