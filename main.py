#!/usr/bin/env python3
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
PROXY_FILE     = "proxies.txt"
DEFAULT_TIMEOUT = 30
VIEW_DURATION   = 300          # 5 دقیقه به ثانیه (برای هر ویدیو)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def load_proxies() -> list[str]:
    """خواندن فایل proxy و برگرداندن لیست خطوط پاک‌شده."""
    if not os.path.exists(PROXY_FILE):
        logging.warning(f"Proxy file {PROXY_FILE} not found.")
        return []
    with open(PROXY_FILE) as f:
        proxies = [line.strip() for line in f if line.strip()]
    logging.info(f"Loaded {len(proxies)} proxies.")
    return proxies

async def is_proxy_working(proxy: str, session: aiohttp.ClientSession) -> bool:
    """
    یک درخواست کوچک به یک سرویس عمومی (ipify) می‌فرستد
    تا ببینیم پروکسی کار می‌کند یا نه.
    """
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
                # اگر IP برگشت داده شد، پروکسی سالم است
                logging.debug(f"Proxy {proxy} returned IP {data.get('ip')}")
                return True
            else:
                logging.debug(f"Proxy {proxy} returned status {resp.status}")
                return False
    except Exception as e:
        logging.debug(f"Proxy {proxy} failed: {e}")
        return False

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
                await asyncio.sleep(VIEW_DURATION)      # 5 دقیقه
                return True
            else:
                logging.warning(f"⚠️ {video_id} returned status {resp.status}")
                return False
    except Exception as exc:
        logging.error(f"❌ Error fetching {video_id}: {exc}")
        logging.debug(traceback.format_exc())
        return False

async def run_cycle(video_ids: list[str], proxies: list[str]):
    semaphore = asyncio.Semaphore(5)  # حداکثر 5 درخواست همزمان

    async with aiohttp.ClientSession() as session:
        # ------------------------------------------------------------------
        # 1️⃣  پیش‌بررسی تمام پروکسی‌ها (اختیاری ولی بهتر)
        # ------------------------------------------------------------------
        valid_proxies = []
        for p in proxies:
            if await is_proxy_working(p, session):
                valid_proxies.append(p)
            else:
                logging.info(f"Proxy {p} discarded – not working")
        if not valid_proxies:
            logging.warning("No working proxies found – falling back to direct connections.")
            valid_proxies = [None]   # استفاده از اتصال مستقیم

        # ------------------------------------------------------------------
        # 2️⃣  اجرای واقعی
        # ------------------------------------------------------------------
        async def sem_task(vid):
            async with semaphore:
                # انتخاب پروکسی تصادفی از فهرست معتبر
                proxy = random.choice(valid_proxies) if valid_proxies else None
                return await fetch_video(vid, proxy, session)

        tasks = [asyncio.create_task(sem_task(vid)) for vid in video_ids]
        await asyncio.gather(*tasks)

def main():
    video_ids = [
        "2BdoajgFDtc", "ueZLEXwFlDM", "3k6FYvrUQkQ",
        "y0hCW06P4nc", "5XeLdcNrSo4"
    ]
    proxies = load_proxies()

    # چاپ متغیرهای محیطی مهم برای تشخیص مشکل
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
        sys.exit(0)          # خروج صریح

if __name__ == "__main__":
    main()
