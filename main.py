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
from bs4 import BeautifulSoup

# ------------------------------------------------------------------
# تنظیمات
# ------------------------------------------------------------------
YOUTUBE_BASE   = "https://www.youtube.com/watch?v="
DEFAULT_TIMEOUT = 30          # seconds
VIEW_DURATION   = 300         # 5 minutes per video
MAX_CONCURRENCY = 100         # تعداد هم‌زمانی برای چک کردن پراکسی‌ها
PROXY_TIMEOUT   = 10          # timeout برای تست پراکسی

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ------------------------------------------------------------------
# Helpers – دریافت پراکسی از منابع مختلف
# ------------------------------------------------------------------
async def fetch_proxies_from_url(session: aiohttp.ClientSession, url: str) -> list[str]:
    """برگرداندن لیست `ip:port` از جدول موجود در صفحه."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                logging.warning(f"URL {url} returned {resp.status}")
                return []

            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")
            table = soup.find("table")
            if not table:
                logging.warning(f"No table found on {url}")
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
        logging.error(f"Failed to fetch proxies from {url}: {exc}")
        return []

async def gather_all_proxies() -> list[str]:
    urls = [
        "https://free-proxy-list.net/ssl-proxy.html",          # HTTPS
        "https://free-proxy-list.net/anonymous-proxy.html",   # HTTP
        "https://www.sslproxies.org/",                       # HTTPS
        "https://www.us-proxy.org/",                          # HTTP
        "https://www.proxyscan.io/proxy/list?type=https",    # HTTPS (API)
        "https://www.proxyscan.io/proxy/list?type=http",     # HTTP
    ]

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_proxies_from_url(session, url) for url in urls]
        results = await asyncio.gather(*tasks)

    # همگن‌سازی و حذف duplicate
    all_proxies = {p for sublist in results for p in sublist}
    logging.info(f"Fetched {len(all_proxies)} proxies from the web")
    return list(all_proxies)

# ------------------------------------------------------------------
# Helpers – چک کردن صحت پراکسی (به‌صورت موازی)
# ------------------------------------------------------------------
async def is_proxy_working(proxy: str, session: aiohttp.ClientSession) -> bool:
    """
    تست یک پراکسی با ارسال درخواست به https://api.ipify.org?format=json
    و بررسی اینکه آیا وضعیت 200 برگردانده می‌شود یا نه.
    """
    # فرض: پراکسی HTTP. اگر پراکسی HTTPS باشد، این کد را تغییر دهید.
    proxy_url = f"http://{proxy}"
    test_url = "https://api.ipify.org?format=json"

    try:
        async with session.get(
            test_url,
            proxy=proxy_url,
            timeout=aiohttp.ClientTimeout(total=PROXY_TIMEOUT),
            ssl=False          # برای پراکسی‌های self‑signed
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                logging.debug(f"Proxy {proxy} works → IP {data.get('ip')}")
                return True
            logging.debug(f"Proxy {proxy} returned status {resp.status}")
            return False
    except Exception as exc:
        logging.debug(f"Proxy {proxy} failed: {exc}")
        return False

async def check_proxies_concurrently(proxies: list[str]) -> list[str]:
    """چک کردن پراکسی‌ها با حداکثر MAX_CONCURRENCY هم‌زمان."""
    valid = []

    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENCY, verify_ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        # ایجاد tasks برای چک کردن همه پراکسی‌ها
        tasks = [asyncio.create_task(is_proxy_working(p, session)) for p in proxies]

        # در حین اجرای tasks، می‌توان خروجی را پردازش کرد
        for proxy, task in zip(proxies, tasks):
            if await task:
                valid.append(proxy)

    logging.info(f"{len(valid)} proxies are working out of {len(proxies)}")
    return valid

# ------------------------------------------------------------------
# Helpers – دانلود ویدیو (شبیه‌سازی view)
# ------------------------------------------------------------------
async def fetch_video(video_id: str, proxy: str | None, session: aiohttp.ClientSession) -> bool:
    url = f"{YOUTUBE_BASE}{video_id}"
    proxy_url = f"http://{proxy}" if proxy else None

    logging.info(f"🚀 Starting view simulation for {video_id}…")
    headers = {
        "User-Agent": random.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        ]),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
    }

    try:
        async with session.get(
            url,
            proxy=proxy_url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
            ssl=False          # برای پراکسی‌های self‑signed
        ) as resp:
            if resp.status == 200:
                logging.info(f"✅ Success: {video_id} (Proxy: {proxy or 'Direct'})")
                # انتظار 5 دقیقه برای ثبت view
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
# Helpers – اجرای هم‌زمان (5 view هم‌زمان، 100 چک پراکسی)
# ------------------------------------------------------------------
async def run_cycle(video_ids: list[str], proxies: list[str]):
    semaphore = asyncio.Semaphore(5)   # حداکثر 5 view هم‌زمان

    # چک کردن پراکسی‌ها (با concurrency بالا)
    valid_proxies = await check_proxies_concurrently(proxies)

    if not valid_proxies:
        logging.warning("No working proxies found – falling back to direct connections.")
        valid_proxies = [None]

    async with aiohttp.ClientSession() as session:
        async def sem_task(vid):
            async with semaphore:
                proxy = random.choice(valid_proxies) if valid_proxies else None
                return await fetch_video(vid, proxy, session)

        tasks = [asyncio.create_task(sem_task(v)) for v in video_ids]
        await asyncio.gather(*tasks)

# ------------------------------------------------------------------
# main()
# ------------------------------------------------------------------
def main():
    # دریافت پراکسی‌های تازه
    proxies = asyncio.run(gather_all_proxies())

    # لیست ویدیوهای مورد نظر
    video_ids = [
        "2BdoajgFDtc", "ueZLEXwFlDM", "3k6FYvrUQkQ",
        "y0hCW06P4nc", "5XeLdcNrSo4"
    ]

    # چاپ متغیرهای محیطی (اگر در دسترس باشد)
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
